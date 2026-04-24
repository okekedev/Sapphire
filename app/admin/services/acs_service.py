"""
Azure Communication Services — phone numbers, SMS, and call automation.

Auth: DefaultAzureCredential (az login locally, Managed Identity in production).
No API keys or connected_accounts rows needed — managed identity handles auth.

ACS Resource to provision:
  az communication create --name acs-sapphire-prod \\
    --resource-group rg-sapphire-prod --location eastus2 --data-location unitedstates
  az role assignment create \\
    --assignee <CA_MI_OBJECT_ID> --role "Contributor" \\
    --scope $(az communication show -n acs-sapphire-prod -g rg-sapphire-prod --query id -o tsv)

Event Grid subscription (set up once — routes all inbound calls to the app):
  az eventgrid event-subscription create \\
    --source-resource-id <ACS_RESOURCE_ID> \\
    --name acs-incoming-calls \\
    --endpoint https://<BACKEND_URL>/api/v1/acs/incoming \\
    --endpoint-type webhook \\
    --event-delivery-schema cloudeventschemav1_0 \\
    --included-event-types Microsoft.Communication.IncomingCall

Set in Container App env vars:
  ACS_ENDPOINT=https://acs-sapphire-prod.communication.azure.com
"""

import logging
from uuid import UUID

from azure.identity.aio import DefaultAzureCredential
from azure.communication.phonenumbers.aio import PhoneNumbersClient
from azure.communication.phonenumbers import (
    PhoneNumberCapabilities,
    PhoneNumberCapabilityType,
    PhoneNumberType,
    PhoneNumberAssignmentType,
)
from azure.communication.callautomation.aio import CallAutomationClient
from azure.communication.callautomation import (
    PhoneNumberIdentifier,
    TextSource,
    RecognizeInputType,
    ServerCallLocator,
    RecordingContent,
    RecordingChannel,
    RecordingFormat,
)
from azure.communication.sms.aio import SmsClient

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# Default ACS neural TTS voice
DEFAULT_VOICE = "en-US-NancyNeural"


class ACSService:
    """Phone numbers, SMS, and call automation via ACS connection string."""

    def _credential(self) -> DefaultAzureCredential:
        return DefaultAzureCredential()

    def _phone_client(self) -> PhoneNumbersClient:
        """PhoneNumbersClient — prefers connection string, falls back to MI."""
        if settings.acs_connection_string:
            return PhoneNumbersClient.from_connection_string(settings.acs_connection_string)
        return PhoneNumbersClient(settings.acs_endpoint, self._credential())

    def _sms_client(self) -> SmsClient:
        """SmsClient — prefers connection string, falls back to MI."""
        if settings.acs_connection_string:
            return SmsClient.from_connection_string(settings.acs_connection_string)
        return SmsClient(settings.acs_endpoint, self._credential())

    # ── Status ──

    def get_status(self) -> dict:
        return {
            "connected": bool(settings.acs_connection_string or settings.acs_endpoint),
            "provider": "Azure Communication Services",
            "auth": "connection_string" if settings.acs_connection_string else "managed_identity",
            "endpoint": settings.acs_endpoint or "not configured",
        }

    # ── Phone Number Management ──

    async def search_available_numbers(
        self,
        country: str = "US",
        area_code: str | None = None,
        number_type: str = "local",
        limit: int = 10,
    ) -> list[dict]:
        """Search ACS inventory for available phone numbers to purchase."""
        is_geographic = number_type == "local"
        # Geographic numbers don't support SMS in ACS
        capabilities = PhoneNumberCapabilities(
            calling=PhoneNumberCapabilityType.INBOUND_OUTBOUND,
            sms=PhoneNumberCapabilityType.NONE if is_geographic else PhoneNumberCapabilityType.INBOUND_OUTBOUND,
        )
        try:
            async with self._phone_client() as client:
                poller = await client.begin_search_available_phone_numbers(
                    country_code=country,
                    phone_number_type=(
                        PhoneNumberType.GEOGRAPHIC
                        if is_geographic
                        else PhoneNumberType.TOLL_FREE
                    ),
                    assignment_type=PhoneNumberAssignmentType.APPLICATION,
                    capabilities=capabilities,
                    area_code=area_code,
                    quantity=1 if is_geographic else limit,
                )
                result = await poller.result()
        except Exception as e:
            logger.error(f"[ACS] search_available_numbers failed: {type(e).__name__}: {e}", exc_info=True)
            return []

        return [
            {
                "phone_number": n,
                "cost_monthly": 1.00,
                "country": country,
                "capabilities": ["voice"],
            }
            for n in (result.phone_numbers or [])
        ]

    async def provision_number(
        self,
        db: AsyncSession,
        business_id: UUID,
        area_code: str,
        campaign_name: str,
        channel: str | None = None,
        ad_account_id: str | None = None,
        line_type: str = "tracking",
    ) -> dict | None:
        """Purchase an available number in the given area code and store it in phone_lines."""
        capabilities = PhoneNumberCapabilities(
            calling=PhoneNumberCapabilityType.INBOUND_OUTBOUND,
            sms=PhoneNumberCapabilityType.NONE,
        )
        try:
            async with self._phone_client() as client:
                search_poller = await client.begin_search_available_phone_numbers(
                    country_code="US",
                    phone_number_type=PhoneNumberType.GEOGRAPHIC,
                    assignment_type=PhoneNumberAssignmentType.APPLICATION,
                    capabilities=capabilities,
                    area_code=area_code,
                    quantity=1,
                )
                search_result = await search_poller.result()
                if not search_result.phone_numbers:
                    logger.error(f"[ACS] No numbers available in area code {area_code}")
                    return None

                purchase_poller = await client.begin_purchase_phone_numbers(search_result.search_id)
                await purchase_poller.result()
                provisioned_number = search_result.phone_numbers[0]
        except Exception as e:
            logger.error(f"[ACS] provision_number failed: {e}")
            return None

        from app.admin.models import PhoneLine
        line = PhoneLine(
            business_id=business_id,
            phone_number=provisioned_number,
            line_type=line_type,
            label=campaign_name or line_type,
        )
        db.add(line)
        await db.flush()

        logger.info(f"[ACS] Provisioned {provisioned_number} ({line_type}) for business {business_id}")
        return {
            "phone_number": provisioned_number,
            "campaign_name": campaign_name,
            "line_type": line_type,
        }

    async def release_number(
        self, db: AsyncSession, business_id: UUID, phone_number: str
    ) -> bool:
        """Release a phone number back to ACS and remove from phone_lines."""
        try:
            async with self._phone_client() as client:
                poller = await client.begin_release_phone_number(phone_number)
                await poller.result()
        except Exception as e:
            logger.error(f"[ACS] release_number failed for {phone_number}: {e}")
            return False

        from app.admin.models import PhoneLine
        await db.execute(
            delete(PhoneLine).where(
                PhoneLine.business_id == business_id,
                PhoneLine.phone_number == phone_number,
            )
        )
        await db.flush()
        return True

    async def list_numbers(self, db: AsyncSession, business_id: UUID) -> list[dict]:
        """List purchased numbers from ACS, enriched with metadata from phone_lines table.

        ACS is the source of truth for which numbers are active. Any ACS number not yet
        in phone_lines is auto-added as a tracking line so nothing is orphaned.
        """
        from app.admin.models import PhoneLine

        # Load DB rows for this business
        db_result = await db.execute(
            select(PhoneLine).where(PhoneLine.business_id == business_id)
        )
        db_lines: dict[str, PhoneLine] = {row.phone_number: row for row in db_result.scalars()}

        # ACS is the source of truth
        try:
            async with self._phone_client() as client:
                acs_numbers = [item async for item in client.list_purchased_phone_numbers()]
        except Exception as e:
            logger.error(f"[ACS] list_purchased_phone_numbers failed: {e}")
            return []

        needs_commit = False
        result = []
        for item in acs_numbers:
            pn = item.phone_number
            row = db_lines.get(pn)

            # Auto-seed unknown numbers so they're always tracked
            if not row:
                row = PhoneLine(
                    business_id=business_id,
                    phone_number=pn,
                    line_type="tracking",
                    label=pn,
                )
                db.add(row)
                db_lines[pn] = row
                needs_commit = True

            result.append({
                "phone_number": pn,
                "friendly_name": row.label or pn,
                "campaign_name": row.label or "tracking",
                "channel": None,
                "line_type": row.line_type,
                "line_id": pn,
            })

        if needs_commit:
            await db.flush()

        return result

    # ── SMS ──

    async def send_sms(self, to: str, from_number: str, body: str) -> bool:
        """Send an outbound SMS via ACS."""
        try:
            async with self._sms_client() as client:
                results = await client.send(from_=from_number, to=[to], message=body)
                ok = all(r.successful for r in results)
                if not ok:
                    logger.warning(f"[ACS SMS] Partial failure sending to {to}")
                return ok
        except Exception as e:
            logger.error(f"[ACS SMS] send failed to {to}: {e}")
            return False

    # ── Call Automation ──

    async def answer_call(self, incoming_call_context: str, callback_url: str) -> str | None:
        """Answer an inbound call. Returns call_connection_id."""
        try:
            async with CallAutomationClient(settings.acs_endpoint, self._credential()) as client:
                result = await client.answer_call(
                    incoming_call_context=incoming_call_context,
                    callback_url=callback_url,
                )
                return result.call_connection_id
        except Exception as e:
            logger.error(f"[ACS] answer_call failed: {e}")
            return None

    async def play_tts(
        self,
        call_connection_id: str,
        text: str,
        voice: str = DEFAULT_VOICE,
        operation_context: str = "",
    ) -> bool:
        """Play TTS audio to all call participants."""
        try:
            async with CallAutomationClient(settings.acs_endpoint, self._credential()) as client:
                conn = client.get_call_connection(call_connection_id)
                await conn.play_media(
                    play_source=[TextSource(text=text, voice_name=voice)],
                    play_to=[],  # empty list = play to all participants
                    operation_context=operation_context,
                )
            return True
        except Exception as e:
            logger.error(f"[ACS] play_tts failed: {e}")
            return False

    async def start_speech_recognition(
        self,
        call_connection_id: str,
        caller_phone: str,
        operation_context: str = "gather",
        end_silence_timeout: int = 3,
    ) -> bool:
        """Start speech recognition on the call, targeted at the inbound caller."""
        try:
            async with CallAutomationClient(settings.acs_endpoint, self._credential()) as client:
                conn = client.get_call_connection(call_connection_id)
                await conn.start_recognizing_media(
                    input_type=RecognizeInputType.SPEECH,
                    target_participant=PhoneNumberIdentifier(caller_phone),
                    operation_context=operation_context,
                    end_silence_timeout=end_silence_timeout,
                )
            return True
        except Exception as e:
            logger.error(f"[ACS] start_speech_recognition failed: {e}")
            return False

    async def transfer_call(
        self,
        call_connection_id: str,
        to_number: str,
        operation_context: str = "transfer",
    ) -> bool:
        """Transfer the call to a PSTN number (department forward number)."""
        try:
            async with CallAutomationClient(settings.acs_endpoint, self._credential()) as client:
                conn = client.get_call_connection(call_connection_id)
                await conn.transfer_call_to_participant(
                    target_participant=PhoneNumberIdentifier(to_number),
                    operation_context=operation_context,
                )
            return True
        except Exception as e:
            logger.error(f"[ACS] transfer_call to {to_number} failed: {e}")
            return False

    async def hang_up(self, call_connection_id: str) -> bool:
        """Hang up the call for all participants."""
        try:
            async with CallAutomationClient(settings.acs_endpoint, self._credential()) as client:
                conn = client.get_call_connection(call_connection_id)
                await conn.hang_up(is_for_everyone=True)
            return True
        except Exception as e:
            logger.error(f"[ACS] hang_up failed: {e}")
            return False

    async def start_recording(self, server_call_id: str) -> str | None:
        """Start mixed audio recording. Returns recording_id."""
        try:
            async with CallAutomationClient(settings.acs_endpoint, self._credential()) as client:
                result = await client.start_recording(
                    server_call_id=ServerCallLocator(server_call_id),
                    recording_content_type=RecordingContent.AUDIO,
                    recording_channel_type=RecordingChannel.MIXED,
                    recording_format_type=RecordingFormat.MP3,
                )
                return result.recording_id
        except Exception as e:
            logger.error(f"[ACS] start_recording failed: {e}")
            return None

    async def stop_recording(self, recording_id: str) -> bool:
        """Stop an active call recording."""
        try:
            async with CallAutomationClient(settings.acs_endpoint, self._credential()) as client:
                await client.stop_recording(recording_id=recording_id)
            return True
        except Exception as e:
            logger.error(f"[ACS] stop_recording failed: {e}")
            return False


acs_service = ACSService()
