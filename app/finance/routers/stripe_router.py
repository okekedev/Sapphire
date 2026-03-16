"""
Stripe Router — bring-your-own-account billing integration.

Endpoints (all JWT-authenticated):
  POST   /stripe/connect      — Store Stripe secret key (verifies with Stripe first)
  GET    /stripe/status       — Get connection status for the Connections page
  DELETE /stripe/disconnect   — Revoke stored credentials
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.services.auth_service import get_current_user_id
from app.finance.services.stripe_service import stripe_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["Stripe"])


# ── Request / Response Schemas ──

class StripeConnectRequest(BaseModel):
    business_id: str
    secret_key: str


class StripeConnectResponse(BaseModel):
    connected: bool
    account_name: str
    account_id: str
    message: str


class StripeStatusResponse(BaseModel):
    platform: str
    connected: bool
    status: str
    account_name: str | None
    account_id: str | None
    connected_at: str | None


# ── Endpoints ──

@router.post("/connect", response_model=StripeConnectResponse)
async def connect_stripe(
    payload: StripeConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Connect a Stripe account by storing the secret key.
    Verifies the key is valid before storing.
    """
    # Verify credentials first
    try:
        verified = await stripe_service.verify_credentials(payload.secret_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    business_id = UUID(payload.business_id)
    await stripe_service.store_credentials(
        db=db,
        business_id=business_id,
        secret_key=payload.secret_key,
        account_name=verified.get("account_name", ""),
        account_id=verified.get("account_id", ""),
    )
    await db.commit()

    logger.info(
        f"Stripe connected for business {business_id}: "
        f"account={verified.get('account_id')}"
    )

    return StripeConnectResponse(
        connected=True,
        account_name=verified.get("account_name", ""),
        account_id=verified.get("account_id", ""),
        message="Stripe connected successfully.",
    )


@router.get("/status", response_model=StripeStatusResponse)
async def get_stripe_status(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """Return connection status for the Connections page Stripe card."""
    status = await stripe_service.get_status(db, UUID(business_id))
    return StripeStatusResponse(**status)


@router.delete("/disconnect")
async def disconnect_stripe(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """Revoke the stored Stripe credentials for a business."""
    success = await stripe_service.disconnect(db, UUID(business_id))
    await db.commit()

    if not success:
        raise HTTPException(status_code=404, detail="No Stripe connection found for this business")

    return {"status": "disconnected", "message": "Stripe disconnected."}
