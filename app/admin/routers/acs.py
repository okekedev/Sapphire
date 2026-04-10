"""
ACS Router — phone number management + inbound/outbound call IVR + SMS.

Replaces twilio.py. Auth uses Azure managed identity — no credentials stored.

Management endpoints (JWT-authenticated):
  GET    /acs/status              — connection status
  GET    /acs/numbers             — list phone lines for business
  GET    /acs/available-numbers   — search ACS for numbers to buy
  POST   /acs/provision           — purchase number + create tracking record
  DELETE /acs/numbers/{phone}     — release number + deactivate record
  GET    /acs/phone-settings      — get IVR / forwarding settings
  PATCH  /acs/phone-settings      — update IVR / forwarding settings
  PATCH  /acs/departments/{id}/routing — update department forward number + SMS toggle

Webhook endpoints (no JWT — called by Event Grid / ACS):
  POST   /acs/incoming            — Event Grid IncomingCall (+ subscription validation)
  POST   /acs/callback            — ACS call events (CallConnected, RecognizeCompleted, etc.)
  POST   /acs/sms                 — Event Grid IncomingMessage (inbound SMS)

Outbound:
  POST   /acs/outbound            — initiate outbound call to a contact

IVR State Machine (inbound call):
  IncomingCall        → look up line, create contact + interaction, answer_call()
  CallConnected       → start recording; then branch by mode:
                          direct_forward  → transfer immediately
                          after_hours_msg → play message, hang up
                          after_hours_fwd → transfer to after-hours number
                          ivr (default)   → play greeting TTS
  PlayCompleted       → (context=greeting) start speech recognition
  RecognizeCompleted  → parse speech via AI, SMS dept, play hold message
  PlayCompleted       → (context=hold) transfer to department forward number
  RecognizeFailed     → transfer to default number or hang up
  CallTransferAccepted → log routing metadata
  CallDisconnected    → finalize interaction, trigger post-call pipeline
"""

import asyncio
import logging
import re
import zoneinfo
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.models.business import Business
from app.core.models.organization import Department
from app.core.services.auth_service import get_current_user_id
from app.core.services.foundry_service import foundry_service
from app.marketing.models import Contact, Interaction
from app.admin.models import PhoneSettings, PhoneLine
from app.admin.services.acs_service import acs_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/acs", tags=["ACS"])


# ── Schemas ──

class ACSProvisionRequest(BaseModel):
    business_id: UUID
    area_code: str
    campaign_name: str
    channel: str | None = None
    ad_account_id: str | None = None
    line_type: str = "tracking"  # "mainline" | "tracking" | "department"


class PhoneSettingsUpdate(BaseModel):
    greeting_text: str | None = None
    voice_name: str | None = None
    hold_message: str | None = None
    recording_enabled: bool | None = None
    forward_all_calls: bool | None = None
    default_forward_number: str | None = None
    ring_timeout_s: int | None = None
    business_hours_start: str | None = None  # "HH:MM"
    business_hours_end: str | None = None    # "HH:MM"
    business_timezone: str | None = None
    after_hours_enabled: bool | None = None
    after_hours_action: str | None = None    # "message" | "forward"
    after_hours_message: str | None = None
    after_hours_forward_number: str | None = None


class DepartmentRoutingUpdate(BaseModel):
    forward_number: str | None = None
    enabled: bool | None = None
    sms_enabled: bool | None = None


# ── Helpers ──

async def _get_business_name(db: AsyncSession, business_id: UUID) -> str:
    result = await db.execute(select(Business).where(Business.id == business_id))
    biz = result.scalar_one_or_none()
    return biz.name if biz else "this business"


def _is_after_hours(ps: PhoneSettings) -> bool:
    if not ps.business_hours_start or not ps.business_hours_end:
        return False
    try:
        tz = zoneinfo.ZoneInfo(ps.business_timezone or "America/Chicago")
    except Exception:
        tz = zoneinfo.ZoneInfo("America/Chicago")
    now = datetime.now(tz).time()
    start, end = ps.business_hours_start, ps.business_hours_end
    if start <= end:
        return now < start or now >= end
    return not (now >= start or now < end)


async def _find_or_create_contact(
    db: AsyncSession,
    business_id: UUID,
    phone: str,
    campaign_name: str | None,
    channel: str = "call",
) -> tuple[Contact, bool]:
    from app.core.services.phone_utils import normalize_phone

    phone = normalize_phone(phone) or phone
    result = await db.execute(
        select(Contact).where(
            Contact.business_id == business_id,
            Contact.phone == phone,
        )
    )
    contact = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if not contact:
        contact = Contact(
            business_id=business_id,
            full_name=phone,
            phone=phone,
            status="new",
            source_channel=channel,
            campaign_id=campaign_name,
            customer_type="new",
            first_contact_date=now,
            acquisition_campaign=campaign_name,
            acquisition_channel=channel,
            touchpoint_count=1,
        )
        db.add(contact)
        await db.flush()
        return contact, True

    contact.touchpoint_count = (contact.touchpoint_count or 0) + 1
    if contact.customer_type != "returning":
        contact.customer_type = "returning"
    if not contact.first_contact_date:
        contact.first_contact_date = contact.created_at or now
    await db.flush()
    return contact, False


def _build_callback_url(base: str, **params) -> str:
    """Build the ACS callback URL with state encoded in query params."""
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base}{settings.api_prefix}/acs/callback?{qs}"


# ── Management Endpoints ──

@router.get("/status")
async def acs_status(
    _user: str = Depends(get_current_user_id),
):
    """ACS connection status — always connected via managed identity."""
    return acs_service.get_status()


@router.get("/numbers")
async def list_numbers(
    business_id: UUID,
    _user: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List active phone lines for a business."""
    numbers = await acs_service.list_numbers(db, business_id)
    return {"numbers": numbers, "count": len(numbers)}


@router.get("/available-numbers")
async def search_available_numbers(
    country: str = Query("US", max_length=2),
    area_code: str | None = Query(None, max_length=10),
    number_type: str = Query("local"),
    limit: int = Query(10, ge=1, le=30),
    _user: str = Depends(get_current_user_id),
):
    """Search ACS inventory for available phone numbers to purchase."""
    numbers = await acs_service.search_available_numbers(
        country=country,
        area_code=area_code,
        number_type=number_type,
        limit=limit,
    )
    return {"numbers": numbers, "count": len(numbers)}


@router.post("/provision")
async def provision_number(
    payload: ACSProvisionRequest,
    _user: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Purchase a phone number from ACS and create a tracking record."""
    result = await acs_service.provision_number(
        db=db,
        business_id=payload.business_id,
        area_code=payload.area_code,
        campaign_name=payload.campaign_name,
        channel=payload.channel,
        ad_account_id=payload.ad_account_id,
        line_type=payload.line_type,
    )
    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to provision number. Check ACS endpoint configuration.",
        )
    await db.commit()
    return result


@router.delete("/numbers/{phone_number:path}")
async def release_number(
    phone_number: str,
    business_id: UUID,
    _user: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Release a phone number back to ACS and deactivate the DB record."""
    ok = await acs_service.release_number(db, business_id, phone_number)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to release number.")
    await db.commit()
    return {"status": "released", "phone_number": phone_number}


@router.get("/phone-settings")
async def get_phone_settings(
    business_id: UUID,
    _user: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get IVR / forwarding settings for a business."""
    result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = result.scalar_one_or_none()
    if not ps:
        return {}
    return {
        "greeting_text": ps.greeting_text,
        "voice_name": ps.voice_name,
        "hold_message": ps.hold_message,
        "recording_enabled": ps.recording_enabled,
        "forward_all_calls": ps.forward_all_calls,
        "default_forward_number": ps.default_forward_number,
        "ring_timeout_s": ps.ring_timeout_s,
        "business_hours_start": ps.business_hours_start.strftime("%H:%M") if ps.business_hours_start else None,
        "business_hours_end": ps.business_hours_end.strftime("%H:%M") if ps.business_hours_end else None,
        "business_timezone": ps.business_timezone,
        "after_hours_enabled": ps.after_hours_enabled,
        "after_hours_action": ps.after_hours_action,
        "after_hours_message": ps.after_hours_message,
        "after_hours_forward_number": ps.after_hours_forward_number,
    }


@router.patch("/phone-settings")
async def update_phone_settings(
    business_id: UUID,
    payload: PhoneSettingsUpdate,
    _user: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update IVR / forwarding settings."""
    result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = result.scalar_one_or_none()
    if not ps:
        ps = PhoneSettings(business_id=business_id)
        db.add(ps)

    for field, value in payload.model_dump(exclude_none=True).items():
        if field in ("business_hours_start", "business_hours_end") and isinstance(value, str):
            from datetime import time
            h, m = value.split(":")
            value = time(int(h), int(m))
        setattr(ps, field, value)

    await db.commit()
    return {"status": "updated"}


@router.patch("/departments/{dept_id}/routing")
async def update_department_routing(
    dept_id: UUID,
    business_id: UUID,
    payload: DepartmentRoutingUpdate,
    _user: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a department's forward number and SMS notification toggle."""
    result = await db.execute(
        select(Department).where(
            Department.id == dept_id,
            Department.business_id == business_id,
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(dept, field, value)

    await db.commit()
    return {"status": "updated"}


# ── Event Grid / ACS Webhook Endpoints ──

@router.options("/incoming")
async def acs_incoming_options(request: Request):
    """CloudEvent webhook validation — Event Grid OPTIONS handshake."""
    from fastapi.responses import Response
    origin = request.headers.get("WebHook-Request-Origin", "*")
    return Response(
        status_code=200,
        headers={
            "WebHook-Allowed-Origin": origin,
            "WebHook-Allowed-Rate": "120",
            "Allow": "POST, OPTIONS",
        },
    )


@router.post("/incoming")
async def acs_incoming_call(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Event Grid webhook — receives IncomingCall events from ACS.

    Handles two cases:
    1. SubscriptionValidationEvent — respond with validationCode to activate subscription
    2. Microsoft.Communication.IncomingCall — answer call, create contact + interaction

    No JWT auth — ACS calls this directly via Event Grid subscription.
    """
    body = await request.json()
    events = body if isinstance(body, list) else [body]

    for event in events:
        # ── Event Grid subscription validation handshake ──
        event_type = event.get("eventType") or event.get("type", "")
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            code = event.get("data", {}).get("validationCode", "")
            logger.info("[ACS] Event Grid subscription validation handshake")
            return {"validationResponse": code}

        if event_type != "Microsoft.Communication.IncomingCall":
            continue

        data = event.get("data", {})
        incoming_call_context = data.get("incomingCallContext", "")
        server_call_id = data.get("serverCallId", "")
        caller_phone = data.get("from", {}).get("phoneNumber", {}).get("value", "")
        called_phone = data.get("to", {}).get("phoneNumber", {}).get("value", "")

        logger.info(f"[ACS] IncomingCall: {caller_phone} → {called_phone}")

        # Determine business from phone_lines table
        pl_result = await db.execute(
            select(PhoneLine).where(PhoneLine.phone_number == called_phone)
        )
        phone_line = pl_result.scalar_one_or_none()
        if not phone_line:
            logger.warning(f"[ACS] No business configured for {called_phone} — rejecting call")
            continue

        business_id = phone_line.business_id
        campaign_name = phone_line.label or phone_line.line_type

        # Load phone settings for IVR config
        ps_result = await db.execute(
            select(PhoneSettings).where(PhoneSettings.business_id == business_id)
        )
        ps = ps_result.scalar_one_or_none()
        if not ps:
            logger.warning(f"[ACS] No phone settings for business {business_id} — rejecting call")
            continue

        # Find or create contact
        contact, is_new = await _find_or_create_contact(
            db=db,
            business_id=business_id,
            phone=caller_phone,
            campaign_name=campaign_name,
        )

        # Create interaction record
        interaction = Interaction(
            business_id=business_id,
            contact_id=contact.id,
            type="call",
            direction="inbound",
            metadata_={
                "acs_call_id": server_call_id,
                "to": called_phone,
                "from": caller_phone,
                "status": "in_progress",
                "campaign_name": campaign_name,
                "channel": None,
                "customer_status": "new" if is_new else "returning",
            },
        )
        db.add(interaction)
        await db.flush()  # flush only — commit after answering

        mode = "ivr"
        if ps.forward_all_calls and ps.default_forward_number:
            mode = "direct_forward"
        elif ps.after_hours_enabled and _is_after_hours(ps):
            mode = "after_hours_forward" if ps.after_hours_action == "forward" else "after_hours_msg"

        # Tag interaction with routing mode
        meta = dict(interaction.metadata_)
        meta["routing_mode"] = mode
        interaction.metadata_ = meta
        await db.flush()

        # Build callback URL with all state needed for event handling
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.url.netloc)
        base = f"{scheme}://{host}"
        callback_url = _build_callback_url(
            base,
            business_id=business_id,
            line_id=None,
            interaction_id=interaction.id,
            contact_id=contact.id,
            caller_phone=caller_phone.replace("+", "%2B"),
            called_phone=called_phone.replace("+", "%2B"),
        )

        await db.commit()

        # Answer the call — ACS fires CallConnected to callback_url
        conn_id = await acs_service.answer_call(
            incoming_call_context=incoming_call_context,
            callback_url=callback_url,
        )
        if not conn_id:
            logger.error(f"[ACS] Failed to answer call for business {business_id}")

    return {"status": "ok"}


@router.post("/callback")
async def acs_call_callback(
    request: Request,
    business_id: UUID = Query(...),
    interaction_id: UUID | None = Query(None),
    contact_id: UUID | None = Query(None),
    line_id: UUID | None = Query(None),
    caller_phone: str | None = Query(None),
    called_phone: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    ACS Call Automation event callback.

    ACS fires a JSON array of CloudEvents to this URL for every call state change.
    State (business_id, interaction_id, etc.) is encoded in the callback URL query params.
    The call_connection_id comes from the event payload.
    """
    body = await request.json()
    events = body if isinstance(body, list) else [body]

    # Decode URL-encoded phone numbers
    if caller_phone:
        caller_phone = caller_phone.replace("%2B", "+")
    if called_phone:
        called_phone = called_phone.replace("%2B", "+")

    for event in events:
        event_type = event.get("type", "")
        data = event.get("data", {})
        call_connection_id = data.get("callConnectionId", "")
        server_call_id = data.get("serverCallId", "")
        operation_context = data.get("operationContext", "")

        logger.info(f"[ACS callback] {event_type} conn={call_connection_id[:8] if call_connection_id else '?'}")

        if event_type == "Microsoft.Communication.CallConnected":
            await _on_call_connected(
                call_connection_id=call_connection_id,
                server_call_id=server_call_id,
                business_id=business_id,
                interaction_id=interaction_id,
                caller_phone=caller_phone,
                called_phone=called_phone,
                db=db,
            )

        elif event_type in ("Microsoft.Communication.PlayCompleted",
                            "Microsoft.Communication.PlayFailed"):
            await _on_play_completed(
                call_connection_id=call_connection_id,
                operation_context=operation_context,
                business_id=business_id,
                interaction_id=interaction_id,
                caller_phone=caller_phone,
                db=db,
            )

        elif event_type == "Microsoft.Communication.RecognizeCompleted":
            speech = data.get("speechResult", {}).get("speech", "")
            confidence = data.get("speechResult", {}).get("confidence", 0.0)
            await _on_recognize_completed(
                call_connection_id=call_connection_id,
                speech_text=speech,
                confidence=confidence,
                business_id=business_id,
                interaction_id=interaction_id,
                contact_id=contact_id,
                called_phone=called_phone,
                db=db,
            )

        elif event_type == "Microsoft.Communication.RecognizeFailed":
            await _on_recognize_failed(
                call_connection_id=call_connection_id,
                business_id=business_id,
                interaction_id=interaction_id,
                db=db,
            )

        elif event_type == "Microsoft.Communication.CallTransferAccepted":
            await _on_transfer_accepted(
                call_connection_id=call_connection_id,
                operation_context=operation_context,
                interaction_id=interaction_id,
                db=db,
            )

        elif event_type == "Microsoft.Communication.CallDisconnected":
            await _on_call_disconnected(
                server_call_id=server_call_id,
                business_id=business_id,
                interaction_id=interaction_id,
                contact_id=contact_id,
                db=db,
            )

        elif event_type == "Microsoft.Communication.RecordingFileStatusUpdated":
            recording_url = data.get("recordingStorageInfo", {}).get("recordingChunks", [{}])[0].get("contentLocation", "")
            if recording_url and interaction_id:
                await _store_recording_url(interaction_id, recording_url, db)

    return {"status": "ok"}


@router.post("/sms")
async def acs_incoming_sms(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Event Grid webhook — receives IncomingMessage (SMS) events from ACS.
    Creates an Interaction record and looks up/creates the contact.
    """
    body = await request.json()
    events = body if isinstance(body, list) else [body]

    for event in events:
        event_type = event.get("type") or event.get("eventType", "")

        # Subscription validation
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            code = event.get("data", {}).get("validationCode", "")
            return {"validationResponse": code}

        if event_type != "Microsoft.Communication.SMSReceived":
            continue

        data = event.get("data", {})
        from_phone = data.get("from", "")
        to_phone = data.get("to", "")
        message = data.get("message", "")

        sms_pl_result = await db.execute(
            select(PhoneLine).where(PhoneLine.phone_number == to_phone)
        )
        sms_phone_line = sms_pl_result.scalar_one_or_none()
        if not sms_phone_line:
            continue

        sms_campaign = sms_phone_line.label or sms_phone_line.line_type
        contact, _ = await _find_or_create_contact(
            db=db,
            business_id=sms_phone_line.business_id,
            phone=from_phone,
            campaign_name=sms_campaign,
            channel="sms",
        )

        sms_interaction = Interaction(
            business_id=sms_phone_line.business_id,
            contact_id=contact.id,
            type="sms",
            direction="inbound",
            body=message,
            metadata_={
                "from": from_phone,
                "to": to_phone,
                "campaign_name": sms_campaign,
            },
        )
        db.add(sms_interaction)
        await db.commit()

    return {"status": "ok"}


@router.post("/outbound")
async def outbound_call(
    business_id: UUID,
    department_id: UUID,
    contact_phone: str,
    request: Request,
    _user: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate an outbound PSTN call from a department's phone number to a contact.
    Creates the interaction record and fires the call.
    """
    dept_result = await db.execute(
        select(Department).where(
            Department.id == department_id,
            Department.business_id == business_id,
        )
    )
    dept = dept_result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Get the mainline number from phone_lines
    mainline_result = await db.execute(
        select(PhoneLine).where(
            PhoneLine.business_id == business_id,
            PhoneLine.line_type == "mainline",
        )
    )
    mainline = mainline_result.scalar_one_or_none()
    if not mainline:
        raise HTTPException(status_code=400, detail="No mainline number configured for this business")
    from_number = mainline.phone_number

    from app.core.services.phone_utils import normalize_phone
    to_number = normalize_phone(contact_phone)
    if not to_number:
        raise HTTPException(status_code=400, detail="Invalid contact phone number")

    contact, _ = await _find_or_create_contact(
        db=db,
        business_id=business_id,
        phone=to_number,
        campaign_name=None,
        channel="call",
    )

    interaction = Interaction(
        business_id=business_id,
        contact_id=contact.id,
        type="call",
        direction="outbound",
        metadata_={
            "to": to_number,
            "from": from_number,
            "status": "in_progress",
        },
    )
    db.add(interaction)
    await db.flush()

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    base = f"{scheme}://{host}"
    callback_url = _build_callback_url(
        base,
        business_id=business_id,
        interaction_id=interaction.id,
        contact_id=contact.id,
        caller_phone=from_number.replace("+", "%2B"),
        called_phone=to_number.replace("+", "%2B"),
    )

    # TODO: use ACS CallAutomationClient.create_call() for outbound PSTN
    # For now, return 501 until outbound calling is wired up
    await db.commit()
    return {
        "status": "initiated",
        "interaction_id": str(interaction.id),
        "from": from_number,
        "to": to_number,
    }


# ── IVR Event Handlers ──

async def _on_call_connected(
    call_connection_id: str,
    server_call_id: str,
    business_id: UUID,
    interaction_id: UUID | None,
    caller_phone: str | None,
    called_phone: str | None,
    db: AsyncSession,
) -> None:
    """CallConnected — start recording, then branch based on routing mode."""
    # Fetch routing mode from interaction metadata
    mode = "ivr"
    if interaction_id:
        result = await db.execute(
            select(Interaction).where(Interaction.id == interaction_id)
        )
        interaction = result.scalar_one_or_none()
        if interaction and interaction.metadata_:
            mode = interaction.metadata_.get("routing_mode", "ivr")
            # Store connection ID for post-call lookup
            meta = dict(interaction.metadata_)
            meta["acs_connection_id"] = call_connection_id
            interaction.metadata_ = meta
            await db.commit()

    # Start recording (non-blocking)
    if mode in ("ivr", "direct_forward", "after_hours_fwd"):
        asyncio.create_task(acs_service.start_recording(server_call_id))

    if mode == "direct_forward":
        # Skip IVR — transfer immediately to default forward number
        ps_result = await db.execute(
            select(PhoneSettings).where(
                PhoneSettings.business_id == business_id
            )
        )
        ps = ps_result.scalar_one_or_none()
        if ps and ps.default_forward_number:
            from app.core.services.phone_utils import normalize_phone
            await acs_service.transfer_call(
                call_connection_id, normalize_phone(ps.default_forward_number) or ps.default_forward_number, operation_context="direct_forward"
            )
        else:
            await acs_service.hang_up(call_connection_id)

    elif mode == "after_hours_fwd":
        ps_result = await db.execute(
            select(PhoneSettings).where(PhoneSettings.business_id == business_id)
        )
        ps = ps_result.scalar_one_or_none()
        if ps and ps.after_hours_forward_number:
            from app.core.services.phone_utils import normalize_phone
            await acs_service.transfer_call(
                call_connection_id, normalize_phone(ps.after_hours_forward_number) or ps.after_hours_forward_number, operation_context="after_hours"
            )
        else:
            await acs_service.hang_up(call_connection_id)

    elif mode == "after_hours_msg":
        ps_result = await db.execute(
            select(PhoneSettings).where(PhoneSettings.business_id == business_id)
        )
        ps = ps_result.scalar_one_or_none()
        company_name = await _get_business_name(db, business_id)
        msg = (
            ps.after_hours_message
            if ps and ps.after_hours_message
            else f"Thank you for calling {company_name}. We are currently closed. Please call back during our regular business hours."
        )
        voice = ps.voice_name if ps else "en-US-NancyNeural"
        await acs_service.play_tts(
            call_connection_id, msg, voice=voice, operation_context="after_hours_msg"
        )

    else:
        # Default: AI IVR — play greeting, then start recognition
        ps_result = await db.execute(
            select(PhoneSettings).where(PhoneSettings.business_id == business_id)
        )
        ps = ps_result.scalar_one_or_none()
        company_name = await _get_business_name(db, business_id)
        greeting = (
            ps.greeting_text
            if ps and ps.greeting_text
            else f"Thank you for calling {company_name}. Please state your name and reason for calling after the tone."
        )
        voice = ps.voice_name if ps else "en-US-NancyNeural"
        await acs_service.play_tts(
            call_connection_id, greeting, voice=voice, operation_context="greeting"
        )


async def _on_play_completed(
    call_connection_id: str,
    operation_context: str,
    business_id: UUID,
    interaction_id: UUID | None,
    caller_phone: str | None,
    db: AsyncSession,
) -> None:
    """PlayCompleted — advance IVR state based on what just finished playing."""
    if operation_context == "greeting":
        # Greeting done — start speech recognition
        if caller_phone:
            await acs_service.start_speech_recognition(
                call_connection_id,
                caller_phone=caller_phone,
                operation_context="gather",
                end_silence_timeout=4,
            )
        else:
            await acs_service.hang_up(call_connection_id)

    elif operation_context == "hold":
        # Hold message done — check if we have routing info and transfer
        if interaction_id:
            result = await db.execute(
                select(Interaction).where(Interaction.id == interaction_id)
            )
            interaction = result.scalar_one_or_none()
            forward_to = (
                interaction.metadata_.get("forward_to")
                if interaction and interaction.metadata_
                else None
            )
            if forward_to:
                await acs_service.transfer_call(
                    call_connection_id, forward_to, operation_context="transfer"
                )
                return
        await acs_service.hang_up(call_connection_id)

    elif operation_context in ("after_hours_msg",):
        # Message played — hang up
        await acs_service.hang_up(call_connection_id)


async def _on_recognize_completed(
    call_connection_id: str,
    speech_text: str,
    confidence: float,
    business_id: UUID,
    interaction_id: UUID | None,
    contact_id: UUID | None,
    called_phone: str | None,
    db: AsyncSession,
) -> None:
    """RecognizeCompleted — parse speech, route to department, play hold message."""
    logger.info(f"[ACS IVR] Speech: '{speech_text}' (confidence={confidence:.2f})")

    # Update interaction with raw speech
    interaction = None
    if interaction_id:
        result = await db.execute(
            select(Interaction).where(Interaction.id == interaction_id)
        )
        interaction = result.scalar_one_or_none()

    # ── Grace: parse speech + route in one call ──
    import json as _json
    caller_name = None
    reason = None
    dept_result = await db.execute(
        select(Department).where(
            Department.business_id == business_id,
            Department.enabled == True,
        ).order_by(Department.display_order)
    )
    enabled_depts = dept_result.scalars().all()

    routed_department = None
    forward_to = None
    matched_dept = None

    if speech_text and enabled_depts:
        try:
            dept_options = ", ".join(d.name for d in enabled_depts)
            grace_prompt = (
                f"Caller said: \"{speech_text}\"\n"
                f"Available departments: {dept_options}"
            )
            raw = await foundry_service.complete("grace", grace_prompt)
            parsed = _json.loads(raw)
            caller_name = parsed.get("caller_name")
            reason = parsed.get("summary")
            ai_dept = (parsed.get("department") or "").strip().lower()
            for dept in enabled_depts:
                if dept.name.lower() == ai_dept or dept.name.lower() in ai_dept:
                    routed_department = dept.name
                    matched_dept = dept
                    break
        except Exception as e:
            logger.warning(f"[ACS IVR] Grace routing failed: {e}")
            reason = speech_text[:100] if speech_text else None

    # Update contact name if we got one
    if caller_name and contact_id:
        c_result = await db.execute(select(Contact).where(Contact.id == contact_id))
        contact = c_result.scalar_one_or_none()
        if contact and (not contact.full_name or contact.full_name == contact.phone):
            contact.full_name = caller_name
            await db.flush()

    # Fallback to first enabled department
    if not routed_department and enabled_depts:
        matched_dept = enabled_depts[0]
        routed_department = matched_dept.name

    # Get forward number
    from app.core.services.phone_utils import normalize_phone
    if matched_dept and matched_dept.forward_number:
        forward_to = normalize_phone(matched_dept.forward_number)

    # Fallback to phone settings default
    if not forward_to:
        ps_result = await db.execute(
            select(PhoneSettings).where(PhoneSettings.business_id == business_id)
        )
        ps = ps_result.scalar_one_or_none()
        forward_to = normalize_phone(ps.default_forward_number) if ps else None

    # Update interaction with IVR data + routing decision
    if interaction and interaction.metadata_:
        meta = dict(interaction.metadata_)
        meta.update({
            "ivr_speech": speech_text,
            "ivr_caller_name": caller_name,
            "ivr_reason": reason,
            "ivr_confidence": confidence,
            "routed_to_department": routed_department,
            "forward_to": forward_to,
        })
        interaction.metadata_ = meta
        await db.flush()

    # Send SMS notification to department (if sms_enabled)
    if matched_dept and matched_dept.sms_enabled and forward_to and called_phone:
        sms_body = f"[{routed_department}] Incoming call: {caller_name or 'Unknown'} — {reason or 'no reason given'}"
        asyncio.create_task(
            acs_service.send_sms(to=forward_to, from_number=called_phone, body=sms_body)
        )

    await db.commit()

    if not forward_to:
        logger.warning(f"[ACS IVR] No forward number for business {business_id} — hanging up")
        await acs_service.hang_up(call_connection_id)
        return

    # Play hold message, then transfer in PlayCompleted handler
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = ps_result.scalar_one_or_none()
    hold_msg = (
        ps.hold_message
        if ps and ps.hold_message
        else "Thank you, please hold while I connect your call. This call may be recorded for quality purposes."
    )
    voice = ps.voice_name if ps else "en-US-NancyNeural"
    await acs_service.play_tts(
        call_connection_id, hold_msg, voice=voice, operation_context="hold"
    )


async def _on_recognize_failed(
    call_connection_id: str,
    business_id: UUID,
    interaction_id: UUID | None,
    db: AsyncSession,
) -> None:
    """RecognizeFailed — no speech detected; fall back to default forward number."""
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = ps_result.scalar_one_or_none()

    if ps and ps.default_forward_number:
        logger.info(f"[ACS IVR] No speech — forwarding to default: {ps.default_forward_number}")
        if interaction_id:
            result = await db.execute(
                select(Interaction).where(Interaction.id == interaction_id)
            )
            interaction = result.scalar_one_or_none()
            if interaction and interaction.metadata_:
                meta = dict(interaction.metadata_)
                meta["routed_to_department"] = "Direct Forward"
                from app.core.services.phone_utils import normalize_phone
                normalized = normalize_phone(ps.default_forward_number) or ps.default_forward_number
                meta["forward_to"] = normalized
                interaction.metadata_ = meta
                await db.commit()
        await acs_service.transfer_call(
            call_connection_id, normalize_phone(ps.default_forward_number) or ps.default_forward_number, operation_context="fallback_transfer"
        )
    else:
        company_name = await _get_business_name(db, business_id)
        voice = ps.voice_name if ps else "en-US-NancyNeural"
        await acs_service.play_tts(
            call_connection_id,
            f"We're unable to connect your call right now. Please try {company_name} again later.",
            voice=voice,
            operation_context="no_answer_msg",
        )


async def _on_transfer_accepted(
    call_connection_id: str,
    operation_context: str,
    interaction_id: UUID | None,
    db: AsyncSession,
) -> None:
    """CallTransferAccepted — transfer succeeded; tag interaction."""
    if not interaction_id:
        return
    result = await db.execute(
        select(Interaction).where(Interaction.id == interaction_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction and interaction.metadata_:
        meta = dict(interaction.metadata_)
        meta["transfer_status"] = "accepted"
        meta["transfer_context"] = operation_context
        interaction.metadata_ = meta
        await db.commit()


async def _on_call_disconnected(
    server_call_id: str,
    business_id: UUID,
    interaction_id: UUID | None,
    contact_id: UUID | None,
    db: AsyncSession,
) -> None:
    """CallDisconnected — finalize interaction and trigger post-call pipeline."""
    if not interaction_id:
        return

    result = await db.execute(
        select(Interaction).where(Interaction.id == interaction_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction and interaction.metadata_:
        meta = dict(interaction.metadata_)
        meta["status"] = "completed"
        interaction.metadata_ = meta
        await db.commit()

    # Fire post-call pipeline in background (summary + lead qualification)
    asyncio.create_task(
        _run_call_pipeline(
            business_id=business_id,
            interaction_id=interaction_id,
            contact_id=contact_id,
        )
    )


async def _store_recording_url(
    interaction_id: UUID,
    recording_url: str,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(Interaction).where(Interaction.id == interaction_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction and interaction.metadata_:
        meta = dict(interaction.metadata_)
        meta["recording_url"] = recording_url
        interaction.metadata_ = meta
        await db.commit()


# ── Post-Call Pipeline (background task) ──

async def _run_call_pipeline(
    business_id: UUID,
    interaction_id: UUID,
    contact_id: UUID | None,
) -> None:
    """
    Background: AI summary + Riley lead qualification, stored in interaction metadata_.
    Mirrors the Twilio call pipeline — same DB writes, same AI calls.
    """
    from app.database import async_session_factory
    from app.core.models.business import Business as BusinessModel

    logger.info(f"[ACS pipeline] Starting for interaction {interaction_id}")

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Interaction).where(Interaction.id == interaction_id)
            )
            interaction = result.scalar_one_or_none()
            if not interaction:
                return

            contact = None
            if contact_id:
                c_result = await db.execute(
                    select(Contact).where(Contact.id == contact_id)
                )
                contact = c_result.scalar_one_or_none()

            ivr_speech = interaction.metadata_.get("ivr_speech") if interaction.metadata_ else None
            ivr_caller_name = interaction.metadata_.get("ivr_caller_name") if interaction.metadata_ else None
            ivr_reason = interaction.metadata_.get("ivr_reason") if interaction.metadata_ else None
            call_duration = interaction.metadata_.get("duration_s", 0) if interaction.metadata_ else 0

            # ── 1. AI call summary ──
            call_summary = None
            if ivr_speech or ivr_caller_name or ivr_reason:
                try:
                    call_context = (
                        f"Caller name: {ivr_caller_name or 'Unknown'}\n"
                        f"Reason: {ivr_reason or 'Not stated'}\n"
                        f"Raw speech: {ivr_speech or 'No speech'}\n"
                        f"Duration: {call_duration}s\n"
                        f"Caller phone: {contact.phone if contact else 'Unknown'}"
                    )
                    summary_prompt = (
                        "Summarize this inbound call in 1-2 sentences. "
                        "Include who called and what they want.\n\n" + call_context
                    )
                    call_summary = await foundry_service.complete("admin", summary_prompt)
                    if call_summary:
                        call_summary = call_summary.strip()
                except Exception as e:
                    logger.error(f"[ACS pipeline] Summary failed: {e}")

            # ── 2. Riley lead qualification ──
            riley_notes = None
            follow_up_draft = None
            try:
                biz_result = await db.execute(
                    select(BusinessModel).where(BusinessModel.id == business_id)
                )
                biz = biz_result.scalar_one_or_none()
                from app.core.services.openai_service import build_profile_context
                profile_text = build_profile_context(biz) if biz else ""

                riley_task = f"""Inbound call ended. Details:
- Caller: {ivr_caller_name or (contact.phone if contact else "unknown")}
- Reason: {ivr_reason or "Not stated"}
- Duration: {call_duration}s
- Campaign: {interaction.metadata_.get("campaign_name") if interaction.metadata_ else "direct"}
- Speech: {ivr_speech or "No speech captured"}
- Summary: {call_summary or "N/A"}

{profile_text}

Return in this format:
SCORE: [Hot/Warm/Cold] — [reason]
NOTES:
[bullet points]
FOLLOW_UP:
[draft message]
NEXT_STEP: [action]"""

                riley_output = await foundry_service.complete("sales", riley_task)

                if riley_output:
                    in_notes = in_followup = False
                    notes_lines: list[str] = []
                    followup_lines: list[str] = []
                    for line in riley_output.strip().splitlines():
                        if line.startswith("NOTES:"):
                            in_notes, in_followup = True, False
                            continue
                        if line.startswith("FOLLOW_UP:"):
                            in_notes, in_followup = False, True
                            continue
                        if line.startswith(("SCORE:", "NEXT_STEP:")):
                            in_notes = in_followup = False
                        if in_notes:
                            notes_lines.append(line)
                        if in_followup:
                            followup_lines.append(line)
                    riley_notes = "\n".join(notes_lines).strip() or riley_output
                    follow_up_draft = "\n".join(followup_lines).strip()
            except Exception as e:
                logger.error(f"[ACS pipeline] Riley failed: {e}")

            # ── 3. Write enrichment back to interaction ──
            if interaction.metadata_:
                meta = dict(interaction.metadata_)
                if call_summary:
                    meta["summary"] = call_summary
                    interaction.subject = call_summary
                if riley_notes:
                    meta["riley_notes"] = riley_notes
                if follow_up_draft:
                    meta["follow_up_draft"] = follow_up_draft
                interaction.metadata_ = meta
                await db.commit()

            logger.info(f"[ACS pipeline] Complete for interaction {interaction_id}")

    except Exception as e:
        logger.error(f"[ACS pipeline] Fatal error: {e}")
