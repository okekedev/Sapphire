"""CRM models: Contact, Interaction, BusinessPhoneLine.

Contacts is the single source of truth for prospects and customers.
customer_type is set per-interaction context: "new" on first call, "returning"
on subsequent calls. The Contact-level customer_type reflects the latest state.

BusinessPhoneLine maps Twilio phone numbers to campaigns/line types for attribution.
Interactions log every touchpoint: calls, emails, form submits, SMS, payments.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, Date, Boolean, Text, ForeignKey, Numeric, Integer, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contact(Base):
    """A prospect or customer — single record through the full lifecycle.

    DB columns (30): id, business_id, full_name, email, phone, status,
    source_channel, campaign_id, utm_source, utm_medium, utm_campaign,
    stripe_customer_id, customer_type, first_contact_date, first_invoice_date,
    acquisition_campaign, acquisition_channel, revenue_since_contact,
    last_transaction_date, touchpoint_count, address_line1, city, state,
    zip_code, country, phone_verified, email_verified, notes, created_at,
    updated_at
    """
    __tablename__ = "contacts"

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

    # ── Identity ──
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )

    # ── Pipeline status ──
    # new → prospect (qualified lead) → active_customer → churned
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="new", index=True,
    )

    # ── Attribution ──
    source_channel: Mapped[Optional[str]] = mapped_column(String(100))
    # e.g. "call", "web_form", "email", "referral", "facebook_ad", "google_ad"
    campaign_id: Mapped[Optional[str]] = mapped_column(String(255))
    utm_source: Mapped[Optional[str]] = mapped_column(String(255))
    utm_medium: Mapped[Optional[str]] = mapped_column(String(255))
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(255))

    # ── Billing integration ──
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))

    # ── Customer lifecycle ──
    # "new" on first interaction, "returning" on subsequent — set by call pipeline
    customer_type: Mapped[Optional[str]] = mapped_column(String(30))
    # Timestamp of first interaction (call, email, form, etc.)
    first_contact_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
    )
    # Timestamp of first invoice/payment linked to this contact
    first_invoice_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
    )
    # Campaign that originally acquired this contact (from first interaction)
    acquisition_campaign: Mapped[Optional[str]] = mapped_column(String(255))
    # Channel of first contact: "call", "email", "form", "walk_in", etc.
    acquisition_channel: Mapped[Optional[str]] = mapped_column(String(100))
    # Running total of all linked payments
    revenue_since_contact: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), server_default="0",
    )
    # Most recent payment date
    last_transaction_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
    )
    # Count of all interactions (calls, emails, etc.)
    touchpoint_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )

    # ── Location ──
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    zip_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(100))

    # ── Birthday ──
    birthday: Mapped[Optional["date"]] = mapped_column(Date, nullable=True)

    # ── Notes ──
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Timestamps ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ──
    business = relationship("Business", foreign_keys=[business_id])
    interactions = relationship(
        "Interaction",
        back_populates="contact",
        cascade="all, delete-orphan",
        order_by="Interaction.created_at.desc()",
    )


class Interaction(Base):
    """A single touchpoint between the business and a contact.

    DB columns (10): id, business_id, contact_id, type, direction,
    subject, body, metadata, created_by, created_at
    """
    __tablename__ = "interactions"

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
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Interaction type
    type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
    )
    # call, email, form_submit, sms, fb_message, payment, note

    # Direction: inbound, outbound, or null
    direction: Mapped[Optional[str]] = mapped_column(String(20))

    # Subject line for emails, AI summary for calls
    subject: Mapped[Optional[str]] = mapped_column(String(500))

    # Body text (email body, SMS body, note content)
    body: Mapped[Optional[str]] = mapped_column(Text)

    # Type-specific metadata (JSONB — shape varies by type)
    # NOTE: "metadata" is reserved by SQLAlchemy 2.0 — Python attr is metadata_,
    # but the database column is named "metadata".
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    # Who created this interaction (user_id FK)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        index=True,
    )

    # ── Relationships ──
    contact = relationship("Contact", back_populates="interactions")
    business = relationship("Business", foreign_keys=[business_id])


class BusinessPhoneLine(Base):
    """A Twilio phone number for the business — mainline, tracking, or department line.

    DB columns (14): id, business_id, department_id, twilio_number,
    twilio_number_sid, friendly_name, campaign_name, ad_account_id,
    channel, line_type, active, created_at, updated_at
    """
    __tablename__ = "business_phone_lines"

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

    # Optional link to a department — one number per department for IVR routing
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The Twilio number (E.164 format, e.g. "+14155551234")
    twilio_number: Mapped[str] = mapped_column(String(20), nullable=False)
    twilio_number_sid: Mapped[Optional[str]] = mapped_column(String(100))

    # Human-readable label (e.g. "Main Office Line", "Google Ads - Dallas")
    friendly_name: Mapped[Optional[str]] = mapped_column(String(255))

    # Campaign this number is attributed to (nullable — mainline doesn't need one)
    campaign_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ad_account_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Channel context (paid_search, organic, direct, facebook_ads, direct_mail, etc.)
    channel: Mapped[Optional[str]] = mapped_column(String(100))

    # Line type: "mainline", "tracking", or "department"
    line_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="tracking", index=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true",
    )

    # SHAKEN/STIR verification: unverified | pending | verified
    shaken_stir_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="unverified",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ──
    business = relationship("Business", foreign_keys=[business_id])
    department = relationship("Department", foreign_keys=[department_id])


class MediaFile(Base):
    """Uploaded image/media file for use in content posts."""
    __tablename__ = "media_files"

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
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )

    business = relationship("Business", foreign_keys=[business_id])


class ContentPost(Base):
    """A social media post draft or published post."""
    __tablename__ = "content_posts"

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
    content: Mapped[str] = mapped_column(Text, nullable=False)
    platform_targets: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]",
    )
    media_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft", index=True,
    )
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    posted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    platform_results: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
