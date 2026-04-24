"""
Payments Router — payment CRUD and reporting.

Endpoints:
  GET    /payments              — list payments (optionally filtered)
  POST   /payments              — create a payment
  GET    /payments/{payment_id} — get a single payment
  PATCH  /payments/{payment_id} — update payment fields
  DELETE /payments/{payment_id} — delete payment
"""

import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.database import get_db
from app.finance.models import Payment
from app.finance.schemas.payment import (
    PaymentCreate,
    PaymentUpdate,
    PaymentOut,
    PaymentListResponse,
)
from app.core.services.auth_service import get_current_user_id


router = APIRouter(prefix="/payments", tags=["Payments"])


# ── Helpers ──

async def _get_payment_or_404(payment_id: UUID, business_id: UUID, db: AsyncSession) -> Payment:
    result = await db.execute(
        select(Payment).where(Payment.id == payment_id, Payment.business_id == business_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


# ── Endpoints ──

@router.get("", response_model=PaymentListResponse)
async def list_payments(
    business_id: UUID,
    contact_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, pattern="^(pending|completed|failed|refunded)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List payments for a business, optionally filtered."""
    q = select(Payment).where(Payment.business_id == business_id)
    if contact_id:
        q = q.where(Payment.contact_id == contact_id)
    if status:
        q = q.where(Payment.status == status)
    q = q.order_by(Payment.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    payments = result.scalars().all()

    # Total count
    count_q = select(func.count(Payment.id)).where(Payment.business_id == business_id)
    if contact_id:
        count_q = count_q.where(Payment.contact_id == contact_id)
    if status:
        count_q = count_q.where(Payment.status == status)
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    return PaymentListResponse(payments=list(payments), total=total)


@router.post("", response_model=PaymentOut, status_code=201)
async def create_payment(
    business_id: UUID,
    payload: PaymentCreate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new payment."""
    payment = Payment(
        business_id=business_id,
        amount=payload.amount,
        payment_type=payload.payment_type,
        frequency=payload.frequency,
        provider=payload.provider,
        status=payload.status,
        billing_ref=payload.billing_ref,
        notes=payload.notes,
        paid_at=payload.paid_at,
        contact_id=payload.contact_id,
        interaction_id=payload.interaction_id,
        source=payload.source,
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    return payment


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: UUID,
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a single payment by ID."""
    return await _get_payment_or_404(payment_id, business_id, db)


@router.patch("/{payment_id}", response_model=PaymentOut)
async def update_payment(
    payment_id: UUID,
    business_id: UUID,
    payload: PaymentUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update payment fields."""
    payment = await _get_payment_or_404(payment_id, business_id, db)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(payment, field, value)
    await db.flush()
    await db.refresh(payment)
    return payment


@router.delete("/{payment_id}", status_code=204)
async def delete_payment(
    payment_id: UUID,
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a payment."""
    payment = await _get_payment_or_404(payment_id, business_id, db)
    await db.delete(payment)
    await db.flush()
