"""Pydantic schemas for payments."""

from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class PaymentCreate(BaseModel):
    amount: float
    payment_type: str = "one_time"
    frequency: str | None = None
    provider: str | None = None
    source: str | None = None
    status: str = "completed"
    notes: str | None = None
    paid_at: datetime | None = None
    contact_id: UUID | None = None
    interaction_id: UUID | None = None
    job_id: UUID | None = None
    # Stripe IDs — set when payment originates from Stripe
    stripe_customer_id: str | None = None
    stripe_invoice_id: str | None = None
    stripe_subscription_id: str | None = None
    stripe_payment_intent_id: str | None = None
    # Overflow for non-Stripe providers
    billing_ref: dict | None = None


class PaymentUpdate(BaseModel):
    amount: float | None = None
    payment_type: str | None = None
    frequency: str | None = None
    provider: str | None = None
    source: str | None = None
    status: str | None = None
    notes: str | None = None
    paid_at: datetime | None = None
    contact_id: UUID | None = None
    interaction_id: UUID | None = None
    job_id: UUID | None = None
    stripe_customer_id: str | None = None
    stripe_invoice_id: str | None = None
    stripe_subscription_id: str | None = None
    stripe_payment_intent_id: str | None = None
    billing_ref: dict | None = None


class PaymentOut(BaseModel):
    id: UUID
    business_id: UUID
    contact_id: UUID | None = None
    interaction_id: UUID | None = None
    job_id: UUID | None = None
    amount: float
    payment_type: str
    frequency: str | None = None
    provider: str | None = None
    source: str | None = None
    status: str
    stripe_customer_id: str | None = None
    stripe_invoice_id: str | None = None
    stripe_subscription_id: str | None = None
    stripe_payment_intent_id: str | None = None
    billing_ref: dict | None = None
    notes: str | None = None
    paid_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    payments: list[PaymentOut]
    total: int
