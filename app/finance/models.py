"""Payment model — tracks all payments across contacts.

Supports both one-time and subscription payments.
Links to contacts (who paid), jobs (what was billed), and external billing
systems via first-class indexed columns (no JSONB for hot-path lookups).

Data chain: tracking_number → call → prospect → lead → job → payment → invoice
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Text, Numeric, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Payment(Base):
    """A single payment — one-time or recurring subscription."""
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Linked entities ──
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Payment details ──
    amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False,
    )
    payment_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )  # subscription, one_time

    frequency: Mapped[Optional[str]] = mapped_column(String(20))
    # monthly, annual, quarterly — only for subscriptions

    provider: Mapped[Optional[str]] = mapped_column(String(50))
    # stripe, square, cash, check, zelle, venmo, other

    # How this payment record was created
    source: Mapped[Optional[str]] = mapped_column(String(50))
    # stripe_sync, manual_upload, manual_entry, quickbooks_import, etc.

    # Optional link to the interaction (call) that drove this payment
    interaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="completed",
    )  # pending, completed, failed, refunded

    # ── Stripe integration (first-class indexed columns) ──
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True,
    )  # cus_xxx — Stripe customer
    stripe_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True,
    )  # in_xxx — one-time invoice
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True,
    )  # sub_xxx — recurring subscription
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True,
    )  # pi_xxx — the actual charge

    # ── Overflow for non-Stripe providers (QuickBooks, Square, etc.) ──
    billing_ref: Mapped[Optional[dict]] = mapped_column(JSONB)

    # ── Notes ──
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Timestamps ──
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )

    # ── Relationships ──
    business = relationship("Business", foreign_keys=[business_id])
    contact = relationship("Contact", foreign_keys=[contact_id])
    job = relationship("Job", foreign_keys=[job_id])
