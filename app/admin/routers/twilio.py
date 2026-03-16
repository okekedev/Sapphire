"""
Twilio Router — credential management + inbound/outbound call/SMS webhooks.

Management endpoints (JWT-authenticated):
  POST   /twilio/connect            — store Account SID + Auth Token
  GET    /twilio/status             — connection status for Connections page
  DELETE /twilio/disconnect         — revoke stored credentials
  GET    /twilio/numbers            — list phone numbers in connected account
  POST   /twilio/configure/{sid}    — point a number's webhook at our handler
  GET    /twilio/available-numbers  — search Twilio inventory for numbers to buy
  POST   /twilio/provision          — buy a number + create tracking record
  POST   /twilio/sync-numbers       — reconcile DB tracking numbers with Twilio account
  GET    /twilio/client-token       — browser WebRTC token for outbound calls

Webhook endpoints (called by Twilio — no JWT auth, validated by request origin):
  POST   /twilio/voice           — inbound call: AI IVR greeting + speech gather
  POST   /twilio/voice-gather    — IVR step 2: process speech, SMS owner, disclaimer, forward
  POST   /twilio/outbound-voice  — outbound call TwiML (browser WebRTC → target)
  POST   /twilio/dial-complete   — IVR step 3: after dial ends, message if no answer
  POST   /twilio/call-status     — call completion (stores interaction + recording)
  POST   /twilio/recording       — recording ready callback (stores recording URL)
  POST   /twilio/sms             — inbound SMS handler (stores interaction)
"""

import logging
import re
import zoneinfo
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.config import settings
from app.database import get_db
from app.core.models.business import Business
from app.marketing.models import Contact, Interaction, BusinessPhoneLine
from app.admin.models import PhoneSettings
from app.core.services.auth_service import get_current_user_id
from app.admin.services.twilio_service import twilio_service

router = APIRouter(prefix="/twilio", tags=["Twilio"])


# ── Schemas ──

class TwilioConnectRequest(BaseModel):
    business_id: UUID
    account_sid: str
    auth_token: str
    phone_number: str | None = None  # Optional — user can set later


class TwilioProvisionRequest(BaseModel):
    business_id: UUID
    phone_number: str  # E.164 number to purchase
    campaign_name: str  # Campaign this number is attributed to
    channel: str | None = None  # google_ads, facebook_ads, direct_mail, etc.
    ad_account_id: str | None = None


# ── Helpers ──

async def _webhook_base(db: AsyncSession, business_id: UUID, request: Request) -> str:
    """Read the webhook base URL from phone_settings (DB is source of truth).
    Falls back to inferring from request headers if not set."""
    result = await db.execute(
        select(PhoneSettings.webhook_base_url).where(
            PhoneSettings.business_id == business_id
        )
    )
    url = result.scalar_one_or_none()
    if url:
        return url.rstrip("/")
    # Fallback: infer from request headers (works behind reverse proxy / ngrok)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}"


async def _get_business_name(db: AsyncSession, business_id: UUID) -> str:
    """Return the business's display name for TTS greetings."""
    result = await db.execute(
        select(Business).where(Business.id == business_id)
    )
    biz = result.scalar_one_or_none()
    if not biz:
        return "this business"
    return biz.name


def _is_after_hours(ps) -> bool:
    """Check whether the current time (in the business's timezone) is outside business hours."""
    if not ps.business_hours_start or not ps.business_hours_end:
        return False
    try:
        tz = zoneinfo.ZoneInfo(ps.business_timezone or "America/Chicago")
    except Exception:
        tz = zoneinfo.ZoneInfo("America/Chicago")
    now_local = datetime.now(tz).time()
    start = ps.business_hours_start
    end = ps.business_hours_end
    if start <= end:
        # Normal range (e.g. 09:00 – 17:00): after-hours = before start or after end
        return now_local < start or now_local >= end
    else:
        # Overnight range (e.g. 22:00 – 06:00): in-hours when now >= start OR now < end
        return not (now_local >= start or now_local < end)


async def _get_forward_number(db: AsyncSession, business_id: UUID) -> str | None:
    """
    Return the default forward-to number for this business.

    Checks (in order):
    1. PhoneSettings.default_forward_number (explicit mainline config)
    2. Twilio creds phone_number (legacy owner's number)
    3. Any department with a forward_number on the departments table

    If ANY forward path exists, the IVR greeting should play.
    """
    from app.core.models.organization import Department

    # 1. Check PhoneSettings
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = ps_result.scalar_one_or_none()
    logger.warning(f"[FWD-LOOKUP] PhoneSettings exists={ps is not None}")
    if ps:
        logger.warning(f"[FWD-LOOKUP] default_forward_number={ps.default_forward_number!r}")
    if ps and ps.default_forward_number:
        logger.warning(f"[FWD-LOOKUP] Returning default_forward_number: {ps.default_forward_number}")
        return ps.default_forward_number

    # 2. Check Twilio creds
    creds = await twilio_service.get_credentials(db, business_id)
    if creds and creds.get("phone_number"):
        logger.warning(f"[FWD-LOOKUP] Returning creds phone_number: {creds['phone_number']}")
        return creds["phone_number"]

    # 3. Check departments table for any department with a forward_number
    dept_result = await db.execute(
        select(Department).where(
            Department.business_id.is_(None),
            Department.enabled == True,
            Department.forward_number.isnot(None),
            Department.forward_number != "",
        ).limit(1)
    )
    dept = dept_result.scalar_one_or_none()
    if dept and dept.forward_number:
        logger.warning(f"[FWD-LOOKUP] Returning dept forward_number: {dept.forward_number}")
        return dept.forward_number

    logger.warning(f"[FWD-LOOKUP] No forward number found for business {business_id}")
    return None


async def _find_or_create_contact(
    db: AsyncSession,
    business_id: UUID,
    phone: str,
    tracking_number_id: UUID | None,
    campaign_name: str | None,
    channel: str = "call",
) -> tuple[Contact, bool]:
    """Find an existing contact by phone or create a new prospect.

    Returns (contact, is_new) — is_new=True if this is first-ever interaction.
    Updates lifecycle fields: touchpoint_count, first_contact_date, acquisition_*.
    Phone is normalized to E.164 (+1XXXXXXXXXX) for consistent dedup.
    """
    from datetime import datetime, timezone
    from app.core.services.phone_utils import normalize_phone

    phone = normalize_phone(phone) or phone  # fallback to raw if normalization fails

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
            full_name=phone,  # placeholder until IVR captures their name
            phone=phone,
            status="new",  # starts as "new" — promoted to "prospect" when qualified as lead
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

    # Existing contact — increment touchpoint, mark returning
    contact.touchpoint_count = (contact.touchpoint_count or 0) + 1
    if contact.customer_type != "returning":
        contact.customer_type = "returning"
    # Backfill first_contact_date if missing (legacy contacts)
    if not contact.first_contact_date:
        contact.first_contact_date = contact.created_at or now
    # Keep original acquisition_campaign — don't overwrite
    await db.flush()
    return contact, False


# ── Management Endpoints (authenticated) ──

@router.post("/connect")
async def connect_twilio(
    payload: TwilioConnectRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Verify Twilio credentials and store them encrypted for the business."""
    try:
        account_info = await twilio_service.verify_credentials(
            payload.account_sid, payload.auth_token
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await twilio_service.store_credentials(
        db=db,
        business_id=payload.business_id,
        account_sid=payload.account_sid,
        auth_token=payload.auth_token,
        phone_number=payload.phone_number,
        account_name=account_info.get("account_name", ""),
    )
    await db.commit()

    return {
        "status": "connected",
        "account_name": account_info.get("account_name"),
        "twilio_status": account_info.get("status"),
    }


@router.get("/status")
async def get_twilio_status(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return Twilio connection status for the Connections page."""
    return await twilio_service.get_status(db, business_id)


@router.delete("/disconnect")
async def disconnect_twilio(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Revoke stored Twilio credentials for a business."""
    disconnected = await twilio_service.disconnect(db, business_id)
    await db.commit()
    if not disconnected:
        raise HTTPException(status_code=404, detail="No Twilio account connected")
    return {"status": "disconnected"}


@router.get("/numbers")
async def list_phone_numbers(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List phone numbers in the connected Twilio account."""
    numbers = await twilio_service.list_phone_numbers(db, business_id)
    return {"numbers": numbers}


@router.post("/configure/{number_sid}")
async def configure_number_webhook(
    number_sid: str,
    business_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Point a Twilio number's voice webhook at our inbound call handler.
    Call this after connecting Twilio and choosing which number to use for tracking.
    """
    base = await _webhook_base(db, business_id, request)
    voice_url = f"{base}{settings.api_prefix}/twilio/voice?business_id={business_id}"
    status_url = f"{base}{settings.api_prefix}/twilio/call-status?business_id={business_id}"

    ok = await twilio_service.configure_webhook(
        db=db,
        business_id=business_id,
        number_sid=number_sid,
        voice_url=voice_url,
        status_callback_url=status_url,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to configure webhook")

    return {
        "status": "configured",
        "voice_url": voice_url,
        "status_callback_url": status_url,
    }


@router.get("/available-numbers")
async def search_available_numbers(
    business_id: UUID,
    country: str = Query("US", max_length=2),
    area_code: str | None = Query(None, max_length=10),
    contains: str | None = Query(None, max_length=20),
    limit: int = Query(10, ge=1, le=30),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Search Twilio's inventory for available phone numbers to buy."""
    numbers = await twilio_service.search_available_numbers(
        db=db,
        business_id=business_id,
        country=country,
        area_code=area_code,
        contains=contains,
        limit=limit,
    )
    return {"numbers": numbers, "count": len(numbers)}


@router.post("/provision")
async def provision_tracking_number(
    payload: TwilioProvisionRequest,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Buy a Twilio phone number and create a tracking number record for campaign attribution.
    Automatically configures voice webhooks if webhook_base_url is set.
    """
    base = await _webhook_base(db, payload.business_id, request)
    voice_url = f"{base}{settings.api_prefix}/twilio/voice?business_id={payload.business_id}"
    status_url = f"{base}{settings.api_prefix}/twilio/call-status?business_id={payload.business_id}"

    result = await twilio_service.provision_number(
        db=db,
        business_id=payload.business_id,
        phone_number=payload.phone_number,
        campaign_name=payload.campaign_name,
        channel=payload.channel,
        ad_account_id=payload.ad_account_id,
        voice_url=voice_url,
        status_callback_url=status_url,
    )
    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to provision number. Check Twilio credentials and account balance.",
        )

    await db.commit()
    return result


@router.post("/sync-numbers")
async def sync_numbers(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user_id),
):
    """Reconcile DB tracking numbers with the Twilio account.

    Deactivates DB records for numbers no longer in Twilio and
    reports Twilio numbers not tracked in the DB.
    """
    result = await twilio_service.sync_numbers(db, business_id)
    if not result.get("synced"):
        raise HTTPException(status_code=400, detail=result.get("reason", "Sync failed"))
    await db.commit()
    return result


@router.get("/a2p-status")
async def a2p_campaign_status(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user_id),
):
    """Check A2P 10DLC campaign registration status from Twilio.

    Uses messaging_service_sid from phone_settings to query the campaign
    status directly. Registration is done in Twilio Console, not via API.
    """
    creds = await twilio_service.get_credentials(db, business_id)
    if not creds:
        return {"campaign_status": "no_credentials", "ready": False}

    # Get messaging_service_sid from phone_settings
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = ps_result.scalar_one_or_none()
    ms_sid = ps.messaging_service_sid if ps else None

    if not ms_sid:
        return {"campaign_status": "no_messaging_service", "ready": False}

    try:
        client = twilio_service._get_client(creds)

        # Query campaigns on the stored messaging service
        svc = client.messaging.v1.services(ms_sid).fetch()
        campaigns = client.messaging.v1.services(ms_sid).us_app_to_person.list(limit=5)

        for c in campaigns:
            status = c.campaign_status or "unknown"
            return {
                "campaign_status": status.lower(),
                "campaign_id": c.campaign_id,
                "messaging_service_sid": ms_sid,
                "messaging_service_name": svc.friendly_name,
                "ready": status.lower() in ("verified", "approved"),
            }

        return {"campaign_status": "no_campaign", "ready": False}
    except Exception as e:
        logger.error(f"[A2P-STATUS] Error: {e}")
        return {"campaign_status": "error", "ready": False, "detail": str(e)}


# ── Webhook Endpoints (called by Twilio — no JWT) ──

@router.post("/voice", response_class=PlainTextResponse)
async def inbound_voice(
    request: Request,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle an inbound call from Twilio.
    Looks up the tracking number for attribution, finds/creates the contact,
    logs the call start, and returns TwiML to greet and forward the call.
    """
    form = await request.form()
    caller = str(form.get("From", ""))
    called = str(form.get("To", ""))      # The tracking number called
    call_sid = str(form.get("CallSid", ""))

    logger.info(f"Inbound call: {caller} → {called} ({call_sid}) for business {business_id}")

    # Look up tracking number for campaign attribution
    tn_result = await db.execute(
        select(BusinessPhoneLine).where(
            BusinessPhoneLine.business_id == business_id,
            BusinessPhoneLine.twilio_number == called,
            BusinessPhoneLine.active == True,
        )
    )
    tracking = tn_result.scalar_one_or_none()

    # Find or create contact
    contact = None
    interaction = None
    is_new_contact = False
    if caller and caller != "anonymous":
        contact, is_new_contact = await _find_or_create_contact(
            db=db,
            business_id=business_id,
            phone=caller,
            tracking_number_id=tracking.id if tracking else None,
            campaign_name=tracking.campaign_name if tracking else None,
        )

        # Log call interaction with customer_status snapshot
        interaction = Interaction(
            business_id=business_id,
            contact_id=contact.id,
            type="call",
            direction="inbound",
            metadata_={
                "call_sid": call_sid,
                "to": called,
                "from": caller,
                "status": "in_progress",
                "campaign_name": tracking.campaign_name if tracking else None,
                "channel": tracking.channel if tracking else None,
                "customer_status": "new" if is_new_contact else "returning",
            },
        )
        db.add(interaction)
        await db.flush()  # flush only — routing metadata added below before commit

    # Build TwiML — AI IVR greeting with speech gather
    company_name = await _get_business_name(db, business_id)
    base = await _webhook_base(db, business_id, request)
    status_url = f"{base}{settings.api_prefix}/twilio/call-status?business_id={business_id}"

    # Check if Twilio is connected at all (creds exist)
    creds = await twilio_service.get_credentials(db, business_id)
    if not creds:
        # Twilio not connected — can't do anything
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Google.en-US-Chirp3-HD-Aoede">Hi, you've reached {company_name}. We're unable to take your call right now. Please try again later.</Say>
  <Hangup />
</Response>"""
    else:
        # Load phone settings
        ps_result = await db.execute(
            select(PhoneSettings).where(PhoneSettings.business_id == business_id)
        )
        phone_settings = ps_result.scalar_one_or_none()

        # ── Forward All Calls mode: skip IVR, dial default number directly ──
        if phone_settings and phone_settings.forward_all_calls and phone_settings.default_forward_number:
            # Tag interaction with routing info
            if interaction:
                meta = dict(interaction.metadata_ or {})
                meta["routed_to_department"] = "Direct Forward"
                meta["forward_to"] = phone_settings.default_forward_number
                interaction.metadata_ = meta

            dial_action_url = (
                f"{base}{settings.api_prefix}/twilio/dial-complete"
                f"?business_id={business_id}"
            )
            twiml = twilio_service.build_ivr_forward_twiml(
                forward_to=phone_settings.default_forward_number,
                status_callback_url=status_url,
                dial_action_url=dial_action_url,
                voice=phone_settings.voice_name or "Google.en-US-Chirp3-HD-Aoede",
                ring_timeout=phone_settings.ring_timeout_s or 30,
                recording_enabled=phone_settings.recording_enabled,
                hold_message=None,  # no hold message in direct forward mode
                caller_id=called,  # use the Twilio number (not the original caller) for "A" attestation
            )

        # ── After-Hours check: skip IVR, play message or forward ──
        elif phone_settings and phone_settings.after_hours_enabled and _is_after_hours(phone_settings):
            voice = phone_settings.voice_name or "Google.en-US-Chirp3-HD-Aoede"

            # Tag interaction with after-hours routing
            if interaction:
                meta = dict(interaction.metadata_ or {})
                ah_action = phone_settings.after_hours_action
                meta["routed_to_department"] = "After Hours Forward" if ah_action == "forward" else "After Hours"
                if ah_action == "forward":
                    meta["forward_to"] = phone_settings.after_hours_forward_number
                interaction.metadata_ = meta

            if phone_settings.after_hours_action == "forward" and phone_settings.after_hours_forward_number:
                # Forward to after-hours number — no IVR
                dial_action_url = (
                    f"{base}{settings.api_prefix}/twilio/dial-complete"
                    f"?business_id={business_id}"
                )
                twiml = twilio_service.build_ivr_forward_twiml(
                    forward_to=phone_settings.after_hours_forward_number,
                    status_callback_url=status_url,
                    dial_action_url=dial_action_url,
                    voice=voice,
                    ring_timeout=phone_settings.ring_timeout_s or 30,
                    recording_enabled=phone_settings.recording_enabled,
                    hold_message=None,
                    caller_id=called,  # Twilio number for "A" attestation
                )
            else:
                # Play after-hours message — no recording, just inform caller
                msg = phone_settings.after_hours_message or f"Thank you for calling {company_name}. We are currently closed. Please call back during our regular business hours."
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="{voice}">{msg}</Say>
  <Hangup />
</Response>"""

        else:
            # AI IVR mode: greet caller and ask for name + reason via speech recognition
            gather_url = (
                f"{base}{settings.api_prefix}/twilio/voice-gather"
                f"?business_id={business_id}"
            )
            twiml = twilio_service.build_ivr_greeting_twiml(
                company_name=company_name,
                gather_callback_url=gather_url,
                greeting_text=phone_settings.greeting_text if phone_settings else None,
                voice=phone_settings.voice_name if phone_settings else "Google.en-US-Chirp3-HD-Aoede",
            )

    # Single commit for interaction + routing metadata
    await db.commit()

    return PlainTextResponse(content=twiml, media_type="application/xml")


@router.post("/voice-gather", response_class=PlainTextResponse)
async def voice_gather_callback(
    request: Request,
    business_id: UUID = Query(...),
    no_input: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    IVR Step 2 — Process the caller's spoken name + reason.

    Flow:
      1. Parse the speech result from Gather (name + reason for calling)
      2. Send an SMS to the forwarding number with caller info WHILE ringing
      3. Update the contact record with the caller's name if we got one
      4. Play the recording disclaimer
      5. Dial the forwarding number with call recording enabled
    """
    form = await request.form()
    speech_result = str(form.get("SpeechResult", ""))
    confidence = form.get("Confidence", "")
    call_sid = str(form.get("CallSid", ""))
    caller = str(form.get("From", ""))
    called = str(form.get("To", ""))  # the Twilio number — used as callerId for "A" attestation

    logger.warning(
        f"[VOICE-GATHER] CallSid={call_sid} Speech='{speech_result}' "
        f"Confidence={confidence} NoInput={no_input}"
    )

    # Get default forward number (may be None — department routing below can override)
    forward_to = await _get_forward_number(db, business_id)

    # Load phone settings for voice/ring/recording config
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    phone_settings = ps_result.scalar_one_or_none()

    base = await _webhook_base(db, business_id, request)
    status_url = f"{base}{settings.api_prefix}/twilio/call-status?business_id={business_id}"

    # Parse the caller's speech via Ivy (AI employee) to extract name and reason
    caller_name = None
    reason = None
    if speech_result and not no_input:
        parsed = await twilio_service.parse_caller_speech(
            speech_result, db=db, business_id=business_id
        )
        caller_name = parsed.get("caller_name")
        reason = parsed.get("reason")

        # Update the contact record with the caller's name if we got one
        if caller_name and caller:
            try:
                result = await db.execute(
                    select(Contact).where(
                        Contact.business_id == business_id,
                        Contact.phone == caller,
                    )
                )
                contact = result.scalar_one_or_none()
                if contact and not contact.full_name:
                    contact.full_name = caller_name
                    await db.flush()
                    logger.warning(f"[VOICE-GATHER] Updated contact name to '{caller_name}' for {caller}")
            except Exception as e:
                logger.warning(f"Failed to update contact name: {e}")

        # Update the interaction with the caller's stated info
        try:
            int_result = await db.execute(
                select(Interaction).where(
                    Interaction.business_id == business_id,
                    Interaction.type == "call",
                    Interaction.metadata_["call_sid"].as_string() == call_sid,
                )
            )
            interaction = int_result.scalar_one_or_none()
            if interaction and interaction.metadata_:
                updated_meta = dict(interaction.metadata_)
                updated_meta["ivr_speech"] = speech_result
                updated_meta["ivr_caller_name"] = caller_name
                updated_meta["ivr_reason"] = reason
                updated_meta["ivr_confidence"] = str(confidence)
                interaction.metadata_ = updated_meta
                await db.flush()
        except Exception as e:
            logger.warning(f"Failed to update interaction with IVR data: {e}")

    # ── AI-based department routing (reads from business's own departments) ──
    from app.core.models.organization import Department as DeptModel

    dept_result = await db.execute(
        select(DeptModel)
        .where(DeptModel.business_id == business_id, DeptModel.enabled == True)
        .order_by(DeptModel.display_order)
    )
    enabled_depts = dept_result.scalars().all()

    logger.warning(
        f"[VOICE-GATHER] forward_to={forward_to!r} reason={reason!r} "
        f"caller_name={caller_name!r} enabled_depts={[d.name for d in enabled_depts]}"
    )

    routed_department = None
    routed_phone = None
    matched_dept = None
    if enabled_depts and reason:
        # AI-powered smart routing — no keywords needed
        dept_options = ", ".join(d.name for d in enabled_depts)
        routing_prompt = (
            f"A caller said their reason for calling is: \"{reason}\"\n\n"
            f"Available departments: {dept_options}\n\n"
            f"Which single department best matches this caller's need? "
            f"Respond with ONLY the department name, nothing else. "
            f"If none match at all, respond with \"none\"."
        )
        try:
            from app.core.services.claude_cli_service import claude_cli
            from app.core.models.organization import Employee

            # Use Grace (Receptionist) for routing — focused prompt, Haiku speed
            grace_result = await db.execute(
                select(Employee).where(Employee.file_stem == "grace_receptionist")
            )
            grace_emp = grace_result.scalar_one_or_none()
            routing_system = (
                grace_emp.system_prompt
                if grace_emp
                else "You are a call router. Given a caller's reason, pick the best matching department. Respond with only the department name."
            )

            ai_choice = await claude_cli._run_claude(
                system_prompt=routing_system,
                message=routing_prompt,
                label="Grace – Call Router",
                model="claude-haiku-4-5-20251001",
                db=db,
                business_id=business_id,
            )
            ai_choice = (ai_choice or "").strip().lower()
            # Match AI response to a department
            for dept in enabled_depts:
                if dept.name.lower() == ai_choice:
                    routed_department = dept.name
                    break
            # Fuzzy fallback — AI might say "sales department" instead of "sales"
            if not routed_department and ai_choice != "none":
                for dept in enabled_depts:
                    if dept.name.lower() in ai_choice:
                        routed_department = dept.name
                        break
            logger.warning(
                f"[VOICE-GATHER] AI routing: reason=\"{reason}\" "
                f"ai_choice=\"{ai_choice}\" routed_to={routed_department}"
            )
        except Exception as e:
            logger.warning(f"AI routing failed: {e}")

        # If AI didn't match (or failed), route to first enabled dept as fallback
        if not routed_department:
            routed_department = enabled_depts[0].name
            logger.warning(
                f"[VOICE-GATHER] Fallback routing to first enabled dept: {routed_department}"
            )

        # Get the department's forwarding number (personal phone)
        if routed_department:
            matched_dept = next(
                (d for d in enabled_depts if d.name == routed_department), None
            )
            if matched_dept and matched_dept.forward_number:
                # Normalize to E.164
                raw = re.sub(r"\D", "", matched_dept.forward_number)
                if len(raw) == 10:
                    raw = "1" + raw
                routed_phone = f"+{raw}" if raw else None
            logger.warning(
                f"[VOICE-GATHER] Routed to {routed_department} "
                f"({routed_phone}) reason: {reason}"
            )

    # Forward to the department's personal phone if routed, otherwise default
    actual_forward_to = routed_phone if routed_phone else forward_to

    # Update interaction with routing decision
    if routed_department:
        try:
            int_result2 = await db.execute(
                select(Interaction).where(
                    Interaction.business_id == business_id,
                    Interaction.type == "call",
                    Interaction.metadata_["call_sid"].as_string() == call_sid,
                )
            )
            interaction2 = int_result2.scalar_one_or_none()
            if interaction2 and interaction2.metadata_:
                updated_meta2 = dict(interaction2.metadata_)
                updated_meta2["routed_to_department"] = routed_department
                updated_meta2["routed_to_number"] = actual_forward_to
                interaction2.metadata_ = updated_meta2
                await db.flush()
        except Exception as e:
            logger.warning(f"Failed to update interaction routing: {e}")

    await db.commit()

    # Send SMS notification with caller name & reason to the department
    # Only if sms_enabled is turned on for the routed department
    # `called` = the Twilio number the caller dialed (used as SMS sender)
    # `actual_forward_to` = the department's forwarding number (SMS recipient)
    dept_sms_on = matched_dept.sms_enabled if matched_dept else False
    if actual_forward_to and called and dept_sms_on:
        sms_body = f"Incoming call: {caller_name or caller or 'Unknown'} — {reason or 'no reason given'}"
        if routed_department:
            sms_body = f"[{routed_department}] {sms_body}"
        try:
            sms_ok = await twilio_service.send_sms(
                db=db,
                business_id=business_id,
                to=actual_forward_to,
                from_number=called,
                body=sms_body,
            )
            if sms_ok:
                logger.info(f"[IVR-SMS] SMS sent to {actual_forward_to} from {called}")
            else:
                logger.warning(f"[IVR-SMS] send_sms returned False")
        except Exception as e:
            logger.warning(f"[IVR-SMS] SMS exception: {e}")

    # Safety check: if we STILL have no number to forward to, apologize and hang up
    logger.warning(
        f"[VOICE-GATHER] FINAL: routed_phone={routed_phone!r} forward_to={forward_to!r} "
        f"actual_forward_to={actual_forward_to!r} routed_department={routed_department!r}"
    )
    if not actual_forward_to:
        logger.warning(f"No forward number found for business {business_id} — hangup")
        voice = phone_settings.voice_name if phone_settings else "Google.en-US-Chirp3-HD-Aoede"
        return PlainTextResponse(
            content=(
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<Response><Say voice="{voice}">'
                "We're unable to connect your call right now. Please try again later."
                '</Say><Hangup /></Response>'
            ),
            media_type="application/xml",
        )

    # Return TwiML: hold message + forward call
    voice = phone_settings.voice_name if phone_settings else "Google.en-US-Chirp3-HD-Aoede"
    ring_timeout = phone_settings.ring_timeout_s if phone_settings else 30
    recording_on = phone_settings.recording_enabled if phone_settings else True
    hold_msg = phone_settings.hold_message if phone_settings else None
    dial_action_url = (
        f"{base}{settings.api_prefix}/twilio/dial-complete"
        f"?business_id={business_id}"
    )
    twiml = twilio_service.build_ivr_forward_twiml(
        forward_to=actual_forward_to,
        status_callback_url=status_url,
        dial_action_url=dial_action_url,
        voice=voice,
        ring_timeout=ring_timeout,
        recording_enabled=recording_on,
        hold_message=hold_msg,
        caller_id=called,  # Twilio number for "A" attestation
    )
    return PlainTextResponse(content=twiml, media_type="application/xml")


@router.post("/dial-complete", response_class=PlainTextResponse)
async def dial_complete_callback(
    request: Request,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by Twilio after the <Dial> ends (answered, no-answer, busy, failed).

    If the call was answered and completed, just hang up gracefully.
    If nobody answered (no-answer, busy, failed, canceled), play a brief
    message and hang up.
    """
    form = await request.form()
    dial_status = form.get("DialCallStatus", "")
    call_sid = form.get("CallSid", "")

    logger.info(f"[DIAL-COMPLETE] CallSid={call_sid} DialCallStatus={dial_status}")

    # If the call was answered and completed, nothing more to do
    if dial_status == "completed":
        return PlainTextResponse(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup /></Response>',
            media_type="application/xml",
        )

    # Nobody answered — the employee's carrier voicemail normally catches this.
    # This path only fires for actual busy/failed (carrier rejected the call).
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    phone_settings = ps_result.scalar_one_or_none()
    voice = phone_settings.voice_name if phone_settings else "Google.en-US-Chirp3-HD-Aoede"

    return PlainTextResponse(
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Say voice="{voice}">'
            "We're sorry, no one is available to take your call right now. Please try again later."
            f'</Say><Hangup /></Response>'
        ),
        media_type="application/xml",
    )


@router.post("/call-status", response_class=PlainTextResponse)
async def call_status_callback(
    request: Request,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by Twilio when a call ends.
    Pipeline:
      1. Update interaction with duration + recording URL
      2. Claude CLI summary using IVR speech data (name + reason captured at call start)
      3. Invoke Riley (Lead Qualifier) for structured notes + follow-up draft
      4. Auto-create a lead card at lead stage
      5. Send SMS notification to business owner with app link

    No external transcription service needed — the IVR <Gather> already captured
    the caller's name and reason via Twilio's built-in speech recognition.
    The full recording URL is stored for playback if the business owner wants to listen.
    """
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    call_status = str(form.get("CallStatus", ""))
    duration = form.get("CallDuration")
    recording_url = str(form.get("RecordingUrl", ""))
    recording_sid = str(form.get("RecordingSid", ""))

    logger.info(f"Call status: {call_sid} → {call_status} ({duration}s)")

    # Only run the full pipeline on completed calls with a recording
    is_completed = call_status in ("completed", "no-answer", "busy", "failed")

    # Find the interaction for this call
    result = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
            Interaction.metadata_["call_sid"].as_string() == call_sid,
        )
    )
    interaction = result.scalar_one_or_none()

    if interaction and interaction.metadata_:
        updated_meta = dict(interaction.metadata_)
        updated_meta["status"] = call_status
        if duration:
            updated_meta["duration_s"] = int(duration)
        if recording_url:
            updated_meta["recording_url"] = recording_url + ".mp3"
            updated_meta["recording_sid"] = recording_sid
        interaction.metadata_ = updated_meta
        await db.commit()

    # ── Transcription + lead pipeline (fire-and-forget via background task) ──
    if is_completed and recording_url and interaction:
        import asyncio
        asyncio.create_task(
            _process_call_pipeline(
                db_url=str(request.app.state.db_url) if hasattr(request.app.state, "db_url") else None,
                business_id=business_id,
                interaction_id=interaction.id,
                call_sid=call_sid,
                recording_url=recording_url + ".mp3",
                call_duration=int(duration) if duration else 0,
                contact_id=interaction.contact_id,
            )
        )

    return PlainTextResponse(content="", media_type="text/plain")


async def _process_call_pipeline(
    db_url: str | None,
    business_id: UUID,
    interaction_id: UUID,
    call_sid: str,
    recording_url: str,
    call_duration: int,
    contact_id: UUID | None,
) -> None:
    """
    Background task: summarize → Riley → enrich interaction → SMS owner.
    Runs after call-status webhook returns so Twilio isn't kept waiting.

    Uses IVR speech data (caller name + reason) captured by <Gather> at call start.
    No external transcription service needed — recording URL is stored for playback.
    All enrichment data (summary, Riley notes, score, routing) is stored in the
    interaction's metadata_ JSONB column for the Tracking & Routing tab.
    """
    from app.database import async_session_factory

    logger.info(f"Starting call pipeline for {call_sid}")

    try:
        async with async_session_factory() as db:
            # ── Re-fetch interaction + contact ──
            result = await db.execute(
                select(Interaction).where(Interaction.id == interaction_id)
            )
            interaction = result.scalar_one_or_none()
            if not interaction:
                logger.error(f"Pipeline: interaction {interaction_id} not found")
                return

            contact = None
            if contact_id:
                c_result = await db.execute(
                    select(Contact).where(Contact.id == contact_id)
                )
                contact = c_result.scalar_one_or_none()

            creds = await twilio_service.get_credentials(db, business_id)

            # ── 1. Build transcript from IVR speech data ──
            # The IVR <Gather> already captured the caller's name + reason
            # via Twilio's built-in speech recognition at the start of the call.
            # The full recording URL is stored for playback — no need to download/transcribe.
            ivr_speech = None
            ivr_caller_name = None
            ivr_reason = None
            if interaction.metadata_:
                ivr_speech = interaction.metadata_.get("ivr_speech")
                ivr_caller_name = interaction.metadata_.get("ivr_caller_name")
                ivr_reason = interaction.metadata_.get("ivr_reason")

            # Use the IVR speech as our "transcript" for the AI pipeline
            transcript = ivr_speech

            # ── 2. Claude summary (via CLI) ──
            call_summary = None
            if transcript or ivr_caller_name or ivr_reason:
                try:
                    from app.core.services.claude_cli_service import claude_cli
                    call_context = (
                        f"Caller name: {ivr_caller_name or 'Unknown'}\n"
                        f"Reason for calling: {ivr_reason or 'Not stated'}\n"
                        f"Raw speech: {ivr_speech or 'No speech captured'}\n"
                        f"Call duration: {call_duration}s\n"
                        f"Caller phone: {contact.phone if contact else 'Unknown'}"
                    )
                    summary_prompt = (
                        f"Summarize this inbound call in 1-2 sentences for the business owner. "
                        f"Include who called and what they want. Be concise and factual.\n\n"
                        f"{call_context}"
                    )
                    call_summary = await claude_cli._run_claude(
                        system_prompt=(
                            "You summarize inbound sales calls for a small business owner. "
                            "Be concise and factual. Return only the summary — no preamble."
                        ),
                        message=summary_prompt,
                        label="Call Summary",
                        model="claude-haiku-4-5-20251001",
                        db=db,
                        business_id=business_id,
                    )
                    if call_summary:
                        call_summary = call_summary.strip()
                    logger.info(f"Summary generated via Claude CLI for {call_sid}")
                except Exception as e:
                    logger.error(f"Claude summary failed for {call_sid}: {e}")

            # Update interaction with summary
            if interaction.metadata_:
                updated_meta = dict(interaction.metadata_)
                if call_summary:
                    updated_meta["summary"] = call_summary
                interaction.metadata_ = updated_meta
                interaction.subject = call_summary or interaction.subject

            # ── 4. Invoke lead qualifier for structured notes + follow-up draft ──
            riley_output = None
            riley_notes = None
            follow_up_draft = None

            try:
                from app.core.services.claude_cli_service import claude_cli
                from app.core.models.organization import Employee
                from app.core.models.business import Business as BusinessModel

                # Look up a lead qualifier employee to get system prompt
                riley_result = await db.execute(
                    select(Employee).where(Employee.file_stem == "riley_lead_qualifier")
                )
                riley_emp = riley_result.scalar_one_or_none()
                if not riley_emp:
                    logger.warning("Lead qualifier employee not found — skipping structured analysis")
                    raise RuntimeError("skip")  # caught by outer except
                riley_system = riley_emp.system_prompt

                # Get business profile from database
                biz_result = await db.execute(
                    select(BusinessModel).where(BusinessModel.id == business_id)
                )
                biz = biz_result.scalar_one_or_none()
                from app.core.services.claude_cli_service import build_profile_context
                profile_text = build_profile_context(biz) if biz else ""

                riley_task = f"""A new inbound call just ended. Here is everything you know:

## Call Details
- Call SID: {call_sid}
- Duration: {call_duration}s
- Caller phone: {contact.phone if contact else "unknown"}
- Caller name: {ivr_caller_name or (contact.full_name if contact and hasattr(contact, "full_name") else "unknown")}
- Reason for calling: {ivr_reason or "Not stated"}
- Campaign/channel: {interaction.metadata_.get("campaign_name") if interaction.metadata_ else "direct"}

## Caller's Words (from IVR speech recognition)
{ivr_speech or "No speech captured — caller may have skipped the IVR prompt."}

## AI Summary
{call_summary or "No summary available."}

## Business Profile
{profile_text}

---
Produce your full output: lead score, lead card notes (bullet points), follow-up draft, and suggested stage.
Return your output in this exact format:

SCORE: [Hot/Warm/Cold] — [one-sentence reason]

NOTES:
[bullet points]

FOLLOW_UP:
[SMS or email draft]

NEXT_STEP: [suggested action]"""

                riley_output = await claude_cli._run_claude(
                    system_prompt=riley_system,
                    message=riley_task,
                    label="Lead Qualifier",
                    model="claude-haiku-4-5-20251001",
                    db=db,
                    business_id=business_id,
                )
                logger.info(f"Lead qualifier output received for {call_sid}")

                # Parse Riley's output
                if riley_output:
                    lines = riley_output.strip().splitlines()
                    in_notes = False
                    in_followup = False
                    notes_lines = []
                    followup_lines = []
                    for line in lines:
                        if line.startswith("NOTES:"):
                            in_notes = True
                            in_followup = False
                            continue
                        if line.startswith("FOLLOW_UP:"):
                            in_notes = False
                            in_followup = True
                            continue
                        if line.startswith("SCORE:") or line.startswith("NEXT_STEP:"):
                            in_notes = False
                            in_followup = False
                        if in_notes:
                            notes_lines.append(line)
                        if in_followup:
                            followup_lines.append(line)

                    riley_notes = "\n".join(notes_lines).strip() or riley_output
                    follow_up_draft = "\n".join(followup_lines).strip()

            except Exception as e:
                if str(e) != "skip":
                    logger.error(f"Lead qualifier invocation failed for {call_sid}: {e}")

            # ── 5. Enrich interaction metadata with Riley's assessment ──
            # All call data lives in the interaction — no separate Lead record needed.
            # The Tracking & Routing tab reads directly from interaction metadata.
            updated_meta = dict(interaction.metadata_) if interaction.metadata_ else {}
            if riley_notes:
                updated_meta["riley_notes"] = riley_notes
            if follow_up_draft:
                updated_meta["follow_up_draft"] = follow_up_draft
            if riley_output:
                for line in riley_output.strip().splitlines():
                    if line.startswith("SCORE:"):
                        updated_meta["score"] = line.replace("SCORE:", "").strip()
                    if line.startswith("NEXT_STEP:"):
                        updated_meta["next_step"] = line.replace("NEXT_STEP:", "").strip()

            # Set routing recommendation (from Riley or default to "Sales")
            if "routed_to_department" not in updated_meta:
                updated_meta["routed_to_department"] = "Sales"
            updated_meta["pipeline_status"] = "followup"

            interaction.metadata_ = updated_meta
            await db.commit()
            logger.info(f"Interaction enriched for call {call_sid}")

            # ── 5b. Call Analysis — department_context + call_category ──
            # This determines which department tab the call appears in
            # and what category it falls under (inquiry, job_request, etc.)
            try:
                from app.marketing.services.call_analysis_service import call_analysis

                analysis = await call_analysis.analyze_call(
                    caller_name=ivr_caller_name,
                    reason=ivr_reason,
                    summary=call_summary,
                    ivr_speech=ivr_speech,
                    call_duration=call_duration,
                    existing_department=updated_meta.get("routed_to_department"),
                    business_id=business_id,
                    db=db,
                )

                updated_meta = dict(interaction.metadata_) if interaction.metadata_ else {}
                updated_meta["department_context"] = analysis.department
                updated_meta["call_category"] = analysis.category
                updated_meta["analysis_confidence"] = analysis.confidence
                if analysis.suggested_action:
                    updated_meta["suggested_action"] = analysis.suggested_action

                interaction.metadata_ = updated_meta
                await db.commit()
                logger.info(
                    f"Call analysis for {call_sid}: dept={analysis.department} "
                    f"cat={analysis.category} conf={analysis.confidence}"
                )
            except Exception as e:
                logger.error(f"Call analysis failed for {call_sid}: {e}")

    except Exception as e:
        logger.error(f"Call pipeline error for {call_sid}: {e}", exc_info=True)


@router.post("/sms", response_class=PlainTextResponse)
async def inbound_sms(
    request: Request,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle an inbound SMS from Twilio.
    Finds/creates the contact and logs the SMS interaction.
    """
    form = await request.form()
    from_number = str(form.get("From", ""))
    to_number = str(form.get("To", ""))
    body = str(form.get("Body", ""))
    message_sid = str(form.get("MessageSid", ""))

    logger.info(f"Inbound SMS from {from_number}: {body[:50]}")

    # Attribution from tracking number
    tn_result = await db.execute(
        select(BusinessPhoneLine).where(
            BusinessPhoneLine.business_id == business_id,
            BusinessPhoneLine.twilio_number == to_number,
            BusinessPhoneLine.active == True,
        )
    )
    tracking = tn_result.scalar_one_or_none()

    if from_number and from_number != "anonymous":
        contact, is_new = await _find_or_create_contact(
            db=db,
            business_id=business_id,
            phone=from_number,
            tracking_number_id=tracking.id if tracking else None,
            campaign_name=tracking.campaign_name if tracking else None,
            channel="sms",
        )

        interaction = Interaction(
            business_id=business_id,
            contact_id=contact.id,
            type="sms",
            direction="inbound",
            subject=body[:255] if body else None,
            body=body,
            metadata_={
                "message_sid": message_sid,
                "to": to_number,
                "from": from_number,
                "campaign_name": tracking.campaign_name if tracking else None,
                "customer_status": "new" if is_new else "returning",
            },
        )
        db.add(interaction)
        await db.commit()

    # Empty TwiML response (no auto-reply)
    return PlainTextResponse(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )



# ── Outbound Calling (WebRTC) ──

# Two-party consent states — area codes that may require both parties
# to consent before recording. This is a best-effort lookup by area code.
# States with all-party (two-party) consent recording laws:
TWO_PARTY_CONSENT_AREA_CODES: dict[str, str] = {
    # California
    "209": "CA", "213": "CA", "279": "CA", "310": "CA", "323": "CA",
    "341": "CA", "408": "CA", "415": "CA", "424": "CA", "442": "CA",
    "510": "CA", "530": "CA", "559": "CA", "562": "CA", "619": "CA",
    "626": "CA", "628": "CA", "650": "CA", "657": "CA", "661": "CA",
    "669": "CA", "707": "CA", "714": "CA", "747": "CA", "760": "CA",
    "805": "CA", "818": "CA", "831": "CA", "858": "CA", "909": "CA",
    "916": "CA", "925": "CA", "949": "CA", "951": "CA",
    # Connecticut
    "203": "CT", "475": "CT", "860": "CT",
    # Florida
    "239": "FL", "305": "FL", "321": "FL", "352": "FL", "386": "FL",
    "407": "FL", "561": "FL", "727": "FL", "754": "FL", "772": "FL",
    "786": "FL", "813": "FL", "850": "FL", "863": "FL", "904": "FL",
    "941": "FL", "954": "FL",
    # Illinois
    "217": "IL", "224": "IL", "309": "IL", "312": "IL", "331": "IL",
    "618": "IL", "630": "IL", "708": "IL", "773": "IL", "779": "IL",
    "815": "IL", "847": "IL", "872": "IL",
    # Maryland
    "240": "MD", "301": "MD", "410": "MD", "443": "MD", "667": "MD",
    # Massachusetts
    "339": "MA", "351": "MA", "413": "MA", "508": "MA", "617": "MA",
    "774": "MA", "781": "MA", "857": "MA", "978": "MA",
    # Michigan
    "231": "MI", "248": "MI", "269": "MI", "313": "MI", "517": "MI",
    "586": "MI", "616": "MI", "734": "MI", "810": "MI", "906": "MI",
    "947": "MI", "989": "MI",
    # Montana
    "406": "MT",
    # Nevada
    "702": "NV", "725": "NV", "775": "NV",
    # New Hampshire
    "603": "NH",
    # Oregon
    "458": "OR", "503": "OR", "541": "OR", "971": "OR",
    # Pennsylvania
    "215": "PA", "223": "PA", "267": "PA", "272": "PA", "412": "PA",
    "484": "PA", "570": "PA", "610": "PA", "717": "PA", "724": "PA",
    "814": "PA", "878": "PA",
    # Washington
    "206": "WA", "253": "WA", "360": "WA", "425": "WA", "509": "WA",
    "564": "WA",
}

# State name lookup for consent warnings
TWO_PARTY_STATE_NAMES: dict[str, str] = {
    "CA": "California", "CT": "Connecticut", "FL": "Florida",
    "IL": "Illinois", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MT": "Montana", "NV": "Nevada",
    "NH": "New Hampshire", "OR": "Oregon", "PA": "Pennsylvania",
    "WA": "Washington",
}


def _check_two_party_consent(phone: str) -> dict | None:
    """Check if a phone number's area code is in a two-party consent state.

    Returns {"state": "CA", "state_name": "California"} if consent is needed,
    or None if the state is one-party consent (no warning needed).
    """
    # Extract area code from E.164 or raw number
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("1") and len(digits) >= 11:
        area_code = digits[1:4]
    elif len(digits) >= 10:
        area_code = digits[:3]
    else:
        return None

    state = TWO_PARTY_CONSENT_AREA_CODES.get(area_code)
    if state:
        return {
            "state": state,
            "state_name": TWO_PARTY_STATE_NAMES.get(state, state),
        }
    return None


@router.get("/check-consent")
async def check_recording_consent(
    phone_number: str = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """Check if a phone number requires two-party consent for recording.

    Returns the state info if the area code maps to a two-party consent state,
    or null if it's a one-party consent state (no warning needed).
    """
    result = _check_two_party_consent(phone_number)
    return {
        "requires_consent": result is not None,
        "state": result.get("state") if result else None,
        "state_name": result.get("state_name") if result else None,
        "message": (
            f"This number appears to be in {result['state_name']} ({result['state']}), "
            f"which requires all-party consent for recording. "
            f"You should notify the other party that the call is being recorded."
        ) if result else None,
    }


@router.get("/client-token")
async def get_client_token(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Generate a Twilio Client Access Token for browser-based calling.

    The token allows the browser to connect via @twilio/voice-sdk
    and make outbound calls through the business's Twilio account.
    """
    from app.admin.services.twilio_client_service import generate_client_token

    webhook_base = await _webhook_base(db, business_id, request)
    identity = f"user-{current_user_id}"

    try:
        token = await generate_client_token(
            db=db,
            business_id=business_id,
            identity=identity,
            webhook_base_url=webhook_base,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to generate client token: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate call token")

    return {"token": token, "identity": identity}


@router.post("/outbound-voice", response_class=PlainTextResponse)
async def outbound_voice_webhook(
    request: Request,
    business_id: UUID = Query(...),
    department_context: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """TwiML webhook called when browser initiates an outbound call.

    The Twilio Voice SDK sends the 'To' and 'From' parameters
    (set by the browser client). We return TwiML to dial the target
    number using the campaign tracking number as caller ID.

    Recording is enabled so the same pipeline (transcription → AI summary)
    processes the call when it ends.

    department_context: If provided, the call is tagged with this department
    (e.g. "Sales", "Finance") for context calling. Outbound calls initiated
    from a department tab inherit that department.
    """
    form = await request.form()
    to_number = form.get("To", "")
    from_number = form.get("From", "")  # Campaign tracking number
    caller_identity = form.get("Caller", "")
    call_sid = form.get("CallSid", "")
    # Also check form for department_context (Twilio SDK can pass custom params)
    if not department_context:
        department_context = form.get("department_context")

    logger.info(
        "Outbound call: To=%s From=%s CallSid=%s Identity=%s",
        to_number, from_number, call_sid, caller_identity,
    )

    if not to_number:
        return PlainTextResponse(
            content='<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>No phone number provided.</Say></Response>",
            media_type="application/xml",
        )

    # Use the 'From' number (campaign tracking number) as caller ID.
    # If not provided, fall back to the business's default number.
    caller_id = from_number
    if not caller_id:
        creds = await twilio_service.get_credentials(db, business_id)
        caller_id = creds.get("phone_number", "") if creds else ""

    # Look up tracking number for campaign attribution
    tracking = None
    if caller_id:
        result = await db.execute(
            select(BusinessPhoneLine).where(
                BusinessPhoneLine.business_id == business_id,
                BusinessPhoneLine.twilio_number == caller_id,
                BusinessPhoneLine.active == True,
            )
        )
        tracking = result.scalar_one_or_none()

    # Find or create contact for the person being called
    contact = None
    is_new = False
    if to_number:
        contact, is_new = await _find_or_create_contact(
            db=db,
            business_id=business_id,
            phone=to_number,
            tracking_number_id=tracking.id if tracking else None,
            campaign_name=tracking.campaign_name if tracking else None,
        )

    # Log outbound call interaction with department context
    outbound_meta = {
        "call_sid": call_sid,
        "to": to_number,
        "from": caller_id,
        "status": "in_progress",
        "campaign_name": tracking.campaign_name if tracking else None,
        "channel": tracking.channel if tracking else None,
        "customer_status": "new" if is_new else "returning",
    }
    # Tag with department context if provided (outbound from a department tab)
    if department_context:
        outbound_meta["department_context"] = department_context
        outbound_meta["routed_to_department"] = department_context

    # Check for two-party consent recording requirement based on area code
    consent_info = _check_two_party_consent(to_number)
    if consent_info:
        outbound_meta["recording_consent_required"] = True
        outbound_meta["recording_consent_state"] = consent_info["state"]

    interaction = Interaction(
        business_id=business_id,
        contact_id=contact.id if contact else None,
        type="call",
        direction="outbound",
        metadata_=outbound_meta,
    )
    db.add(interaction)
    await db.commit()

    # Build TwiML — dial the target number with recording
    base = await _webhook_base(db, business_id, request)
    status_url = (
        f"{base}{settings.api_prefix}/twilio/call-status"
        f"?business_id={business_id}"
    )

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Dial callerId="{caller_id}" '
        f'record="record-from-answer" '
        f'recordingStatusCallback="{status_url}" '
        f'action="{status_url}" method="POST">'
        f"<Number>{to_number}</Number>"
        "</Dial>"
        "</Response>"
    )

    return PlainTextResponse(content=twiml, media_type="application/xml")
