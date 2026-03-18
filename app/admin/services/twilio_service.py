"""
Twilio Service — bring-your-own-account call, SMS, and tracking number management.

The user connects their own Twilio account (Account SID + Auth Token).
Credentials are encrypted with AES-256-GCM and stored in connected_accounts,
exactly the same pattern as the Claude CLI token.

Inbound call flow (AI IVR):
  1. Customer calls a tracking number
  2. Twilio POSTs to /api/v1/twilio/voice
  3. We look up the tracking number → attribution + company name
  4. Return TwiML: AI IVR greeting asks for name + reason via <Gather input="speech">
  5. Twilio POSTs speech result to /api/v1/twilio/voice-gather
  6. We parse the caller's name + reason, SMS the forwarding number with that info
  7. Play recording disclaimer, then <Dial> to forward to owner's number with recording
  8. When the call ends, Twilio POSTs to /api/v1/twilio/call-status
  9. We store the interaction (duration, recording URL, transcription, AI summary)
"""

import json
import logging
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.connected_account import ConnectedAccount
from app.core.services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)

PLATFORM = "twilio"
encryption = EncryptionService()


class TwilioService:
    """Per-business Twilio credential management and call helpers."""

    # ── Credential storage ──

    async def store_credentials(
        self,
        db: AsyncSession,
        business_id: UUID,
        account_sid: str,
        auth_token: str,
        phone_number: str | None = None,
        account_name: str | None = None,
    ) -> ConnectedAccount:
        """Encrypt and persist Twilio credentials for a business."""
        cred_json = json.dumps({
            "account_sid": account_sid,
            "auth_token": auth_token,
            "phone_number": phone_number or "",
            "account_name": account_name or "",
        })
        encrypted = encryption.encrypt(cred_json)

        # Upsert
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            account.encrypted_credentials = encrypted
            account.status = "active"
            account.external_account_id = account_sid
        else:
            account = ConnectedAccount(
                business_id=business_id,
                platform=PLATFORM,
                auth_method="api_key",
                encrypted_credentials=encrypted,
                status="active",
                external_account_id=account_sid,
            )
            db.add(account)

        await db.flush()
        return account

    async def get_credentials(
        self, db: AsyncSession, business_id: UUID
    ) -> dict | None:
        """Retrieve and decrypt Twilio credentials, or None if not connected."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
            ConnectedAccount.status == "active",
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return None
        return json.loads(encryption.decrypt(account.encrypted_credentials))

    async def disconnect(self, db: AsyncSession, business_id: UUID) -> bool:
        """Revoke stored credentials for a business."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return False
        account.status = "revoked"
        await db.flush()
        return True

    # ── Status ──

    async def get_status(self, db: AsyncSession, business_id: UUID) -> dict:
        """Return connection status for the Connections page card."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if not account or account.status == "revoked":
            return {
                "platform": "twilio",
                "connected": False,
                "account_sid": None,
                "phone_number": None,
                "account_name": None,
                "twilio_status": None,
                "connected_at": None,
            }

        creds = json.loads(encryption.decrypt(account.encrypted_credentials))
        return {
            "platform": "twilio",
            "connected": account.status == "active",
            "account_sid": creds.get("account_sid", "")[:6] + "****",  # Masked
            "phone_number": creds.get("phone_number", ""),
            "account_name": creds.get("account_name", ""),
            "twilio_status": account.status,
            "connected_at": account.connected_at.isoformat() if account.connected_at else None,
        }

    # ── Twilio API helpers ──

    def _get_client(self, creds: dict):
        """Return a Twilio REST client from decrypted credentials."""
        from twilio.rest import Client
        return Client(creds["account_sid"], creds["auth_token"])

    async def verify_credentials(self, account_sid: str, auth_token: str) -> dict:
        """
        Test credentials by fetching account info from Twilio.
        Returns {"valid": True, "account_name": "...", "status": "active"} on success.
        Raises ValueError on invalid credentials.
        """
        try:
            from twilio.rest import Client
            from twilio.base.exceptions import TwilioRestException
            client = Client(account_sid, auth_token)
            acct = client.api.accounts(account_sid).fetch()
            return {
                "valid": True,
                "account_name": acct.friendly_name,
                "status": acct.status,
            }
        except Exception as e:
            raise ValueError(f"Invalid Twilio credentials: {e}")

    async def list_phone_numbers(self, db: AsyncSession, business_id: UUID) -> list[dict]:
        """List the Twilio phone numbers in the connected account."""
        creds = await self.get_credentials(db, business_id)
        if not creds:
            return []
        try:
            client = self._get_client(creds)
            numbers = client.incoming_phone_numbers.list(limit=50)
            return [
                {
                    "sid": n.sid,
                    "phone_number": n.phone_number,
                    "friendly_name": n.friendly_name,
                    "capabilities": {
                        "voice": n.capabilities.get("voice", False),
                        "sms": n.capabilities.get("sms", False),
                    },
                }
                for n in numbers
            ]
        except Exception as e:
            logger.warning(f"Failed to list Twilio numbers for {business_id}: {e}")
            return []

    async def configure_webhook(
        self,
        db: AsyncSession,
        business_id: UUID,
        number_sid: str,
        voice_url: str,
        status_callback_url: str,
    ) -> bool:
        """Point a Twilio number's voice webhook at our inbound handler."""
        creds = await self.get_credentials(db, business_id)
        if not creds:
            return False
        try:
            client = self._get_client(creds)
            client.incoming_phone_numbers(number_sid).update(
                voice_url=voice_url,
                voice_method="POST",
                status_callback=status_callback_url,
                status_callback_method="POST",
            )
            return True
        except Exception as e:
            logger.error(f"Failed to configure webhook for {number_sid}: {e}")
            return False

    # ── TwiML generation ──

    def build_ivr_greeting_twiml(
        self,
        company_name: str,
        gather_callback_url: str,
        greeting_text: str | None = None,
        voice: str = "Google.en-US-Chirp3-HD-Aoede",
    ) -> str:
        """
        Build the AI IVR greeting TwiML for inbound calls.

        Flow:
          1. Natural voice greeting asking for name + reason for calling
          2. <Gather> with speech recognition captures the caller's response
          3. On timeout/no-input, falls through to a polite retry or forward

        Args:
            greeting_text: Custom greeting with {company_name} variable. Uses default if None.
            voice: Twilio voice name (e.g. Google.en-US-Chirp3-HD-Aoede).
        """
        if not greeting_text:
            greeting_text = (
                "Thank you for calling {company_name}. "
                "May I get your name and reason for calling so I can best route your call?"
            )
        # Interpolate variables and sanitize
        safe_name = company_name.replace("&", "and").replace("<", "").replace(">", "")
        greeting = greeting_text.replace("{company_name}", safe_name)
        greeting = greeting.replace("&", "and").replace("<", "").replace(">", "")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" timeout="5" speechTimeout="auto" action="{gather_callback_url}" method="POST">
    <Say voice="{voice}">{greeting}</Say>
  </Gather>
  <Redirect>{gather_callback_url}&amp;no_input=true</Redirect>
</Response>"""

    def build_ivr_forward_twiml(
        self,
        forward_to: str,
        status_callback_url: str,
        dial_action_url: str,
        voice: str = "Google.en-US-Chirp3-HD-Aoede",
        ring_timeout: int = 30,
        recording_enabled: bool = True,
        hold_message: str | None = None,
        caller_id: str | None = None,
    ) -> str:
        """
        Build TwiML for the second step of the IVR:
          1. Play hold/routing message (customizable)
          2. Dial the forwarding number with recording enabled

        Args:
            forward_to: E.164 phone number to forward to.
            status_callback_url: URL for recording status callbacks.
            dial_action_url: URL Twilio POSTs to after the dial ends (answered or not).
            voice: Voice name for the hold message.
            ring_timeout: Seconds to ring before falling through.
            recording_enabled: Whether to record the call.
            hold_message: Custom hold message. Falls back to default if None.
            caller_id: E.164 number to show as caller ID on the outbound leg.
                Pass the original caller's number so the forwarding phone sees
                who's really calling (helps avoid spam filters).
        """
        record_attr = 'record="record-from-answer"' if recording_enabled else ""
        caller_id_attr = f'callerId="{caller_id}"' if caller_id else ""
        if hold_message:
            hold_message = hold_message.replace("&", "and").replace("<", "").replace(">", "")
            say_twiml = f'  <Say voice="{voice}">{hold_message}</Say>\n'
        else:
            say_twiml = ""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
{say_twiml}  <Dial {record_attr} {caller_id_attr}
        timeout="{ring_timeout}"
        recordingStatusCallback="{status_callback_url}"
        recordingStatusCallbackMethod="POST"
        action="{dial_action_url}"
        method="POST">
    <Number>{forward_to}</Number>
  </Dial>
</Response>"""

    def build_voice_twiml(
        self,
        company_name: str,
        forward_to: str,
        status_callback_url: str,
    ) -> str:
        """
        Legacy TwiML response for inbound calls (simple greeting + forward).
        Kept as fallback if IVR is disabled.
        """
        safe_name = company_name.replace("&", "and").replace("<", "").replace(">", "")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Google.en-US-Chirp3-HD-Aoede">Hi, you've reached {safe_name}. Please hold while we connect your call.</Say>
  <Dial record="record-from-answer"
        recordingStatusCallback="{status_callback_url}"
        recordingStatusCallbackMethod="POST"
        action="{status_callback_url}"
        method="POST">
    <Number>{forward_to}</Number>
  </Dial>
</Response>"""

    def build_reject_twiml(self) -> str:
        """TwiML to reject a call gracefully."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Reject />
</Response>"""

    async def parse_caller_speech(
        self,
        speech_result: str,
        db: "AsyncSession | None" = None,
        business_id: "UUID | None" = None,
    ) -> dict:
        """
        Parse the caller's spoken response using Ivy (Director of Administration).

        Sends the raw speech-to-text to Claude (Sonnet) with Ivy's system prompt
        to extract a clean caller_name and reason. Falls back to a simple regex
        if the Claude call fails or takes too long.

        Returns {"caller_name": str|None, "reason": str|None, "raw": str}
        """
        if not speech_result or not speech_result.strip():
            return {"caller_name": None, "reason": None, "raw": ""}

        raw = speech_result.strip()

        # Try Claude-powered normalization via Ivy
        try:
            from app.core.services.anthropic_service import claude_cli
            from app.core.models.organization import Employee
            from sqlalchemy import select
            from sqlalchemy.ext.asyncio import AsyncSession

            # Look up Ivy employee from database to get system prompt
            if db and isinstance(db, AsyncSession):
                result = await db.execute(
                    select(Employee).where(Employee.file_stem == "ivy_director_of_administration")
                )
                ivy_emp = result.scalar_one_or_none()
                if not ivy_emp:
                    # Fallback: use regex if Ivy not found
                    return self._parse_caller_speech_regex(raw)
                ivy_system = ivy_emp.system_prompt
            else:
                # No database available, use regex fallback
                return self._parse_caller_speech_regex(raw)

            result_text = await claude_cli._run_claude(
                system_prompt=ivy_system,
                message=raw,
                label="Ivy (Director of Administration)",
                model="claude-sonnet-4-6",
                db=db,
                business_id=business_id,
            )

            if result_text:
                import json as _json
                # Ivy returns raw JSON — parse it
                cleaned = result_text.strip()
                # Strip markdown code fences if present
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                parsed = _json.loads(cleaned)
                return {
                    "caller_name": parsed.get("caller_name"),
                    "reason": parsed.get("reason"),
                    "raw": raw,
                }
        except Exception as e:
            logger.warning(f"Ivy speech parse failed, falling back to regex: {e}")

        # Fallback: simple regex extraction
        return self._parse_caller_speech_regex(raw)

    def _parse_caller_speech_regex(self, raw: str) -> dict:
        """Fallback regex parser for caller speech when Claude is unavailable."""
        import re

        caller_name = None
        reason = None

        noise = {"and", "the", "a", "an", "i", "my", "to", "is", "am", "or", "but", "for", "calling", "about"}

        name_patterns = [
            r"(?:my name is|this is|i'm|i am)\s+(\w+(?:\s+\w+)?(?:\s+\w+)?)",
            r"^(\w+(?:\s+\w+)?)\s*[,.]\s",
            r"^(\w+(?:\s+\w+)?)\s+calling\b",
        ]
        for pat in name_patterns:
            match = re.search(pat, raw, re.IGNORECASE)
            if match:
                words = match.group(1).strip().split()
                name_words = []
                for w in words:
                    if w.lower() in noise:
                        break
                    name_words.append(w)
                if name_words:
                    candidate = " ".join(name_words)
                    skip_words = {"i", "we", "it", "yes", "no", "hi", "hello", "calling"}
                    if candidate.lower() not in skip_words:
                        caller_name = candidate.title()
                break

        reason_patterns = [
            r"(?:calling about|about|for|regarding|need|interested in)\s+(.+)",
            r"(?:calling|called)\s+(?:to|because)\s+(.+)",
        ]
        for pat in reason_patterns:
            match = re.search(pat, raw, re.IGNORECASE)
            if match:
                reason = match.group(1).strip().rstrip(".")
                break

        if not reason and len(raw) > 5:
            reason = raw

        return {"caller_name": caller_name, "reason": reason, "raw": raw}

    # ── Number search & provisioning ──

    async def search_available_numbers(
        self,
        db: AsyncSession,
        business_id: UUID,
        country: str = "US",
        area_code: str | None = None,
        contains: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Search Twilio's inventory for available phone numbers to buy.

        Args:
            country: ISO country code (default "US")
            area_code: Filter by area code (e.g. "415")
            contains: Pattern to search for in number (e.g. "555")
            limit: Max results to return (default 10)

        Returns list of available numbers with monthly cost and capabilities.
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            return []
        try:
            client = self._get_client(creds)
            kwargs: dict = {"limit": min(limit, 30)}
            if area_code:
                kwargs["area_code"] = area_code
            if contains:
                kwargs["contains"] = contains
            numbers = client.available_phone_numbers(country).local.list(**kwargs)
            return [
                {
                    "phone_number": n.phone_number,
                    "friendly_name": n.friendly_name,
                    "locality": n.locality,
                    "region": n.region,
                    "capabilities": {
                        "voice": n.capabilities.get("voice", False),
                        "sms": n.capabilities.get("sms", False),
                    },
                }
                for n in numbers
            ]
        except Exception as e:
            logger.warning(f"Failed to search available numbers for {business_id}: {e}")
            return []

    async def provision_number(
        self,
        db: AsyncSession,
        business_id: UUID,
        phone_number: str,
        campaign_name: str,
        channel: str | None = None,
        ad_account_id: str | None = None,
        voice_url: str | None = None,
        status_callback_url: str | None = None,
    ) -> dict | None:
        """
        Buy a Twilio phone number and create a BusinessPhoneLine record.

        Args:
            phone_number: The E.164 number to purchase (from search_available_numbers)
            campaign_name: Campaign this tracking number is attributed to
            channel: Source channel (google_ads, facebook_ads, direct_mail, etc.)
            ad_account_id: Optional ad account ID for the campaign
            voice_url: Webhook URL for inbound voice (auto-configured if provided)
            status_callback_url: Webhook URL for call status updates

        Returns the created phone line dict, or None on failure.
        """
        from app.marketing.models import BusinessPhoneLine

        creds = await self.get_credentials(db, business_id)
        if not creds:
            logger.warning(f"provision_number: no Twilio creds for business {business_id}")
            return None
        try:
            client = self._get_client(creds)
            # Purchase the number from Twilio
            kwargs: dict = {"phone_number": phone_number}
            if voice_url:
                kwargs["voice_url"] = voice_url
                kwargs["voice_method"] = "POST"
            if status_callback_url:
                kwargs["status_callback"] = status_callback_url
                kwargs["status_callback_method"] = "POST"

            purchased = client.incoming_phone_numbers.create(**kwargs)

            # Create the phone line record in DB
            tracking = BusinessPhoneLine(
                business_id=business_id,
                twilio_number=purchased.phone_number,
                twilio_number_sid=purchased.sid,
                campaign_name=campaign_name,
                channel=channel,
                ad_account_id=ad_account_id,
                active=True,
            )
            db.add(tracking)
            await db.flush()

            logger.info(
                f"Provisioned tracking number {purchased.phone_number} "
                f"(SID: {purchased.sid}) for campaign '{campaign_name}' "
                f"business={business_id}"
            )

            return {
                "tracking_number_id": str(tracking.id),
                "phone_number": purchased.phone_number,
                "twilio_sid": purchased.sid,
                "campaign_name": campaign_name,
                "channel": channel or "",
                "ad_account_id": ad_account_id or "",
            }
        except Exception as e:
            logger.error(f"Failed to provision number {phone_number} for {business_id}: {e}")
            # Re-raise with the actual error so callers can see the real reason
            raise RuntimeError(f"Twilio provision failed: {e}") from e

    # ── Number release (deprovision) ──

    async def release_number(
        self,
        db: AsyncSession,
        business_id: UUID,
        number_sid: str,
    ) -> dict:
        """
        Release (deprovision) a Twilio phone number and deactivate the phone line record.

        Args:
            number_sid: The Twilio number SID (e.g. "PN...") to release
        Returns:
            {"released": True, "phone_number": str, "sid": str} on success
        Raises:
            RuntimeError on failure
        """
        from app.marketing.models import BusinessPhoneLine

        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise RuntimeError("No Twilio credentials configured for this business")

        try:
            client = self._get_client(creds)
            # Get the number details before releasing
            number = client.incoming_phone_numbers(number_sid).fetch()
            phone_number = number.phone_number

            # Release the number from Twilio
            client.incoming_phone_numbers(number_sid).delete()

            # Deactivate the phone line record in DB
            from sqlalchemy import update as sql_update
            stmt = (
                sql_update(BusinessPhoneLine)
                .where(
                    BusinessPhoneLine.business_id == business_id,
                    BusinessPhoneLine.twilio_number_sid == number_sid,
                )
                .values(active=False)
            )
            await db.execute(stmt)
            await db.flush()

            logger.info(
                f"Released number {phone_number} (SID: {number_sid}) "
                f"for business={business_id}"
            )
            return {
                "released": True,
                "phone_number": phone_number,
                "sid": number_sid,
            }
        except Exception as e:
            logger.error(f"Failed to release number {number_sid} for {business_id}: {e}")
            raise RuntimeError(f"Twilio release failed: {e}") from e

    # ── SMS / WhatsApp Notifications ──

    async def send_sms(
        self,
        db: AsyncSession,
        business_id: UUID,
        to: str,
        from_number: str,
        body: str,
    ) -> bool:
        """Send a plain SMS message via Twilio.

        Args:
            to: Phone number of the recipient (department forward_number).
            from_number: Twilio number the call came in on (sender).
            body: Message text.

        Returns False if creds are missing or send fails.
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            logger.warning(f"send_sms: no Twilio creds for business {business_id}")
            return False

        def _e164(num: str) -> str:
            num = num.strip()
            if num.startswith("+"):
                return num
            digits = "".join(c for c in num if c.isdigit())
            if len(digits) == 10:
                return f"+1{digits}"
            return f"+{digits}"

        try:
            client = self._get_client(creds)
            msg = client.messages.create(
                to=_e164(to),
                from_=_e164(from_number),
                body=body,
            )
            logger.info(f"send_sms: sent {msg.sid} to {_e164(to)}")
            return True
        except Exception as e:
            logger.error(f"send_sms failed (to={to} from={from_number}): {e}")
            return False

    async def send_whatsapp(
        self,
        db: AsyncSession,
        business_id: UUID,
        to: str,
        from_number: str,
        body: str,
    ) -> bool:
        """Send a WhatsApp message via Twilio.

        Args:
            to: Phone number of the recipient (department forward_number).
            from_number: Twilio number connected to WhatsApp (the number the call came in on).
            body: Message text.

        Returns False if creds are missing or send fails.
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            logger.warning(f"send_whatsapp: no Twilio creds for business {business_id}")
            return False

        # Normalize: ensure digits start with +
        def _e164(num: str) -> str:
            num = num.strip()
            if num.startswith("+"):
                return num
            # Assume US if 10 digits
            digits = "".join(c for c in num if c.isdigit())
            if len(digits) == 10:
                return f"+1{digits}"
            return f"+{digits}"

        try:
            client = self._get_client(creds)
            msg = client.messages.create(
                to=f"whatsapp:{_e164(to)}",
                from_=f"whatsapp:{_e164(from_number)}",
                body=body,
            )
            logger.info(f"send_whatsapp: sent {msg.sid} to whatsapp:{_e164(to)}")
            return True
        except Exception as e:
            logger.error(f"send_whatsapp failed (to={to} from={from_number}): {e}")
            return False

    # ── Twilio ↔ DB sync ──

    async def sync_numbers(
        self,
        db: AsyncSession,
        business_id: UUID,
    ) -> dict:
        """
        Reconcile business_phone_lines (DB) with the actual Twilio account.

        Runs on a cadence (and manually) so the DB never drifts from reality.
        Three cases:
          1. DB says active but Twilio doesn't have it → deactivate in DB
          2. Twilio has a number not in DB → log it (don't auto-create — we don't
             know the campaign / department assignment)
          3. Both agree → no-op
        """
        from app.marketing.models import BusinessPhoneLine
        from sqlalchemy import update as sql_update

        creds = await self.get_credentials(db, business_id)
        if not creds:
            return {"synced": False, "reason": "no_credentials"}

        try:
            client = self._get_client(creds)
            twilio_numbers = client.incoming_phone_numbers.list(limit=100)
            twilio_sids = {n.sid for n in twilio_numbers}

            # Get all active phone line records for this business
            stmt = select(BusinessPhoneLine).where(
                BusinessPhoneLine.business_id == business_id,
                BusinessPhoneLine.active == True,
            )
            result = await db.execute(stmt)
            db_records = result.scalars().all()

            deactivated = []
            untracked = []

            # Case 1: DB active but not in Twilio → deactivate
            for rec in db_records:
                if rec.twilio_number_sid and rec.twilio_number_sid not in twilio_sids:
                    await db.execute(
                        sql_update(BusinessPhoneLine)
                        .where(BusinessPhoneLine.id == rec.id)
                        .values(active=False)
                    )
                    deactivated.append(rec.twilio_number)
                    logger.info(
                        f"Sync: deactivated {rec.twilio_number} "
                        f"(SID {rec.twilio_number_sid} no longer in Twilio)"
                    )

            # Case 2: Twilio has numbers not tracked in DB → log for awareness
            db_sids = {
                rec.twilio_number_sid
                for rec in db_records
                if rec.twilio_number_sid
            }
            for n in twilio_numbers:
                if n.sid not in db_sids:
                    untracked.append(n.phone_number)
                    logger.info(
                        f"Sync: Twilio number {n.phone_number} ({n.sid}) "
                        f"not tracked in DB for business {business_id}"
                    )

            if deactivated:
                await db.flush()

            logger.info(
                f"Twilio sync for business {business_id}: "
                f"{len(deactivated)} deactivated, "
                f"{len(untracked)} untracked in Twilio"
            )

            return {
                "synced": True,
                "deactivated": deactivated,
                "untracked_in_twilio": untracked,
                "active_count": len(db_records) - len(deactivated),
            }

        except Exception as e:
            logger.error(f"Twilio sync failed for business {business_id}: {e}")
            return {"synced": False, "reason": str(e)}


twilio_service = TwilioService()
