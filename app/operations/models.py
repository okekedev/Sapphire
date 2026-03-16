"""Job model — tracks work/projects linked to customers.

Jobs represent work being done for a customer. Each job has a status
progression: new → in_progress → completed → billed.
Jobs link to a Contact (the customer) and can have associated Payments.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Text, Numeric, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Job(Base):
    """A job/project linked to a customer contact.

    DB columns (14): id, business_id, contact_id, title, description,
    status, notes, amount_quoted, amount_billed, metadata, created_by,
    started_at, completed_at, created_at, updated_at
    """
    __tablename__ = "jobs"

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
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Job details ──
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Status progression: new → in_progress → completed → billed
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="new", index=True,
    )

    # Free-text notes (AI-assisted)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Pricing
    amount_quoted: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    amount_billed: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    # Flexible metadata (extra fields, tags, etc.)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    # Who created this job
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )

    # ── Timestamps ──
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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
    contact = relationship("Contact", foreign_keys=[contact_id])
