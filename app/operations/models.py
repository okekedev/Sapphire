"""Operations models — Job, Staff, JobTemplate.

Jobs track work/projects linked to customers.
Staff are human employees of the business (technicians, dispatchers) — distinct from AI employees.
JobTemplates define structured form workflows for jobs.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Text, Numeric, Boolean, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Staff(Base):
    """Human staff members of a business (technicians, dispatchers, admins).

    Distinct from the AI `employees` table. These are real people who get
    assigned to jobs and receive SMS dispatch notifications.

    Roles: admin | dispatcher | technician
    """
    __tablename__ = "staff"

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

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(255))

    # admin | dispatcher | technician
    role: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'technician'"),
    )

    # Hex color for calendar/card display
    color: Mapped[Optional[str]] = mapped_column(
        String(7), server_default=text("'#6366f1'"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class JobTemplate(Base):
    """Reusable job form templates with structured field definitions.

    The schema JSONB defines sections and fields (text, checkbox, checklist,
    signature, photo, number, url). Template flags control which workflow
    steps are required for jobs using this template.

    Python attr `schema_` maps to DB column `schema`.
    """
    __tablename__ = "job_templates"

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

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Workflow flags — control which status transitions are enforced
    requires_scheduling: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )
    requires_assignment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )
    requires_dispatch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )

    # Form schema: { "sections": [{ "title": str, "fields": [...] }] }
    schema_: Mapped[dict] = mapped_column(
        "schema", JSONB, nullable=False,
        server_default=text("'{\"sections\":[]}'"),
        default=lambda: {"sections": []},
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Job(Base):
    """A job/project linked to a customer contact.

    Status flow (template-driven):
      new → [scheduled] → [dispatched] → started → completed → billing

    Template flags determine which intermediate states are required.
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

    # ── Template linkage ──
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # ── Assignment + scheduling ──
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_address: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── Job details ──
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Status: new | scheduled | dispatched | started | completed | billing
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="new", index=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text)
    amount_quoted: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    amount_billed: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

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
    template = relationship("JobTemplate", foreign_keys=[template_id])
    assigned_staff = relationship("Staff", foreign_keys=[assigned_to])
