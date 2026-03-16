"""
Ngrok Router — credential management + tunnel control for local development.

Management endpoints (JWT-authenticated):
  POST   /ngrok/connect          — store auth token
  GET    /ngrok/status            — connection status for Connections page
  DELETE /ngrok/disconnect        — revoke stored credentials
  POST   /ngrok/start-tunnel      — start ngrok tunnel + auto-configure webhooks
  POST   /ngrok/stop-tunnel       — stop ngrok tunnel
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.marketing.models import BusinessPhoneLine
from app.admin.models import PhoneSettings
from app.core.services.auth_service import get_current_user_id
from app.admin.services.ngrok_service import ngrok_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ngrok", tags=["Ngrok"])


# ── Schemas ──

class NgrokConnectRequest(BaseModel):
    business_id: UUID
    auth_token: str


# ── Management Endpoints (authenticated) ──

@router.post("/connect")
async def connect_ngrok(
    payload: NgrokConnectRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Store ngrok auth token encrypted for the business."""
    if not payload.auth_token.strip():
        raise HTTPException(status_code=400, detail="Auth token is required")

    await ngrok_service.store_credentials(
        db=db,
        business_id=payload.business_id,
        auth_token=payload.auth_token.strip(),
    )
    await db.commit()

    return {
        "status": "connected",
        "message": "ngrok auth token saved. Use 'Start Tunnel' to open a tunnel.",
    }


@router.get("/status")
async def get_ngrok_status(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return ngrok connection status for the Connections page."""
    status = await ngrok_service.get_status(db, business_id)

    # Also check if a tunnel is currently running
    active_url = await ngrok_service.get_active_tunnel()
    if active_url:
        status["tunnel_url"] = active_url
        status["tunnel_active"] = True
    else:
        status["tunnel_active"] = False

    return status


@router.delete("/disconnect")
async def disconnect_ngrok(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Revoke stored ngrok credentials and stop any active tunnel."""
    # Stop tunnel first
    await ngrok_service.stop_tunnel()

    disconnected = await ngrok_service.disconnect(db, business_id)
    await db.commit()
    if not disconnected:
        raise HTTPException(status_code=404, detail="No ngrok account connected")
    return {"status": "disconnected"}


@router.post("/start-tunnel")
async def start_tunnel(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Start an ngrok tunnel and auto-configure all tracking number webhooks.

    Flow:
    1. Start ngrok tunnel → get public URL
    2. Persist webhook_base_url to phone_settings (DB)
    3. Configure all active phone lines to use the tunnel URL
    """
    try:
        result = await ngrok_service.start_tunnel(db, business_id, port=8000)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tunnel_url = result["tunnel_url"]

    # Persist webhook base URL to phone_settings (DB is source of truth)
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = ps_result.scalar_one_or_none()
    if ps:
        ps.webhook_base_url = tunnel_url
    else:
        db.add(PhoneSettings(business_id=business_id, webhook_base_url=tunnel_url))
    logger.info(f"webhook_base_url persisted to phone_settings: {tunnel_url}")

    # Auto-configure webhooks for all active phone lines (mainline + tracking)
    configured_numbers = []
    try:
        from app.admin.services.twilio_service import twilio_service

        voice_url = f"{tunnel_url}{settings.api_prefix}/twilio/voice?business_id={business_id}"
        status_url = f"{tunnel_url}{settings.api_prefix}/twilio/call-status?business_id={business_id}"

        # Load all active phone lines from DB (mainline + tracking)
        tn_result = await db.execute(
            select(BusinessPhoneLine).where(
                BusinessPhoneLine.business_id == business_id,
                BusinessPhoneLine.active == True,
            )
        )
        tracking_numbers = tn_result.scalars().all()

        # Auto-resolve any null SIDs by matching phone numbers from Twilio API
        null_sid_numbers = [tn for tn in tracking_numbers if not tn.twilio_number_sid]
        if null_sid_numbers:
            try:
                twilio_numbers = await twilio_service.list_phone_numbers(db, business_id)
                sid_lookup = {n["phone_number"]: n["sid"] for n in twilio_numbers}
                for tn in null_sid_numbers:
                    if tn.twilio_number in sid_lookup:
                        tn.twilio_number_sid = sid_lookup[tn.twilio_number]
                        logger.info(f"Auto-resolved SID for {tn.twilio_number}: {tn.twilio_number_sid}")
            except Exception as e:
                logger.warning(f"Failed to resolve null SIDs from Twilio API: {e}")

        # Configure webhooks for all numbers that have a SID
        for tn in tracking_numbers:
            if tn.twilio_number_sid:
                try:
                    await twilio_service.configure_webhook(
                        db=db,
                        business_id=business_id,
                        number_sid=tn.twilio_number_sid,
                        voice_url=voice_url,
                        status_callback_url=status_url,
                    )
                    configured_numbers.append(tn.twilio_number)
                    logger.info(f"Configured webhook for {tn.twilio_number}: {voice_url}")
                except Exception as e:
                    logger.warning(f"Failed to configure webhook for {tn.twilio_number}: {e}")

    except Exception as e:
        logger.warning(f"Failed to auto-configure webhooks: {e}")

    await db.commit()

    return {
        "status": "running",
        "tunnel_url": tunnel_url,
        "webhook_base_url": tunnel_url,
        "configured_numbers": configured_numbers,
        "message": f"Tunnel active at {tunnel_url}" + (
            f" — configured {len(configured_numbers)} tracking number(s)"
            if configured_numbers else ""
        ),
    }


@router.post("/stop-tunnel")
async def stop_tunnel(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Stop the active ngrok tunnel."""
    await ngrok_service.stop_tunnel()

    # Clear the stored tunnel URL
    await ngrok_service.update_tunnel_url(db, business_id, "")

    # Clear webhook_base_url in phone_settings (DB is source of truth)
    ps_result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    ps = ps_result.scalar_one_or_none()
    if ps:
        ps.webhook_base_url = ""

    await db.commit()

    return {"status": "stopped", "message": "ngrok tunnel stopped"}
