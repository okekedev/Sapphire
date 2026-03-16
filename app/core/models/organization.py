"""
Organization models — Departments and Employees.

Business-scoped: each business gets its own copy of departments and
employees (via business_id). Rows with business_id=NULL are global
template data. Employee system prompts and department documentation
are stored in DB columns (sole source of truth).

Departments (6): Marketing, Sales, Operations, Finance, Administration, IT
Employees: 18 total — each with model tier (opus/sonnet/haiku), title,
reports_to hierarchy, and a full system prompt.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, Text, DateTime, ForeignKey, UniqueConstraint,
    Index, text, Boolean, Integer, VARCHAR,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_department_business_name"),
        Index("ix_departments_business_id", "business_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
    )  # NULL = global/template, UUID = business-scoped
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    documentation: Mapped[str | None] = mapped_column(Text)  # Full department reference doc (markdown)
    icon: Mapped[str | None] = mapped_column(String(50))  # e.g. "briefcase", "code"
    display_order: Mapped[int] = mapped_column(default=0, server_default=text("0"))

    # ── Phone routing (per-department) ──
    forward_number: Mapped[str | None] = mapped_column(String(20))  # Personal phone to forward calls to (E.164)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True,
    )  # Whether this department accepts call routing
    sms_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )  # Send SMS notification (caller name + reason) to forward_number when calls are routed here
    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )  # Send WhatsApp call summary to forward_number when calls are routed here
    whatsapp_sender_sid: Mapped[str | None] = mapped_column(String(34))  # XE... SID from Twilio Senders API
    whatsapp_sender_status: Mapped[str | None] = mapped_column(
        String(30), server_default=text("'none'"),
    )  # CREATING, ONLINE, OFFLINE, PENDING_VERIFICATION, VERIFYING, etc.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    employees = relationship("Employee", back_populates="department", lazy="selectin")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("business_id", "file_stem", name="uq_employee_business_file_stem"),
        Index("ix_employees_department_id", "department_id"),
        Index("ix_employees_status", "status"),
        Index("ix_employees_business_id", "business_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
    )  # NULL = global/template, UUID = business-scoped
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_stem: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )  # e.g. "marcus_director_of_seo" — used as filename and employee_id
    model_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'haiku'"),
    )  # opus | sonnet | haiku
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)  # Full .md content
    reports_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'"),
    )  # active | inactive
    capabilities: Mapped[dict | None] = mapped_column(JSONB)  # Structured metadata
    job_skills: Mapped[str | None] = mapped_column(Text, nullable=True)  # High-level skills summary
    is_head: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False,
    )  # True for department heads (CMO, COO, CTO, etc.)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    department = relationship("Department", back_populates="employees")
    supervisor = relationship("Employee", remote_side="Employee.id", lazy="selectin")
