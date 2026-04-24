"""Role + BusinessMemberRole models — RBAC."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── System role definitions ──────────────────────────────────────────────────
# Seeded at startup. business_id=NULL means global system role.
# permissions = list of permission strings; ["*"] = all permissions.

SYSTEM_ROLES: list[tuple[str, str, list[str]]] = [
    (
        "global_admin",
        "Full access to everything",
        ["*"],
    ),
    (
        "phone_admin",
        "Manages phone settings, team, and has full pipeline visibility",
        [
            "access_sales", "access_contacts", "access_marketing",
            "access_operations", "access_billing", "access_admin", "access_reports",
            "manage_team", "manage_phone",
            "view_all_leads", "assign_leads",
            "view_all_jobs", "assign_jobs",
            "export_data",
        ],
    ),
    (
        "business_manager",
        "Can edit business profile, services, brand, and goals",
        ["manage_business"],
    ),
    (
        "analyst",
        "Read-only access to all pipeline data and reports",
        ["access_reports", "view_all_leads", "view_all_jobs", "export_data"],
    ),
    (
        "sales_executive",
        "Manages the full sales pipeline — can assign leads and see all leads",
        ["access_sales", "access_contacts", "assign_leads", "view_all_leads", "export_data"],
    ),
    (
        "sales_rep",
        "Works assigned leads only",
        ["access_sales", "access_contacts"],
    ),
    (
        "ops_manager",
        "Manages all jobs and dispatches to techs",
        ["access_operations", "view_all_jobs", "assign_jobs"],
    ),
    (
        "ops_tech",
        "Works own assigned jobs",
        ["access_operations"],
    ),
    (
        "billing_manager",
        "Manages invoices, payments, and Stripe",
        ["access_billing", "manage_billing"],
    ),
    (
        "marketing_manager",
        "Manages contacts, campaigns, and content",
        ["access_marketing"],
    ),
    (
        "legal",
        "Creates, views, and manages documents and e-signatures",
        ["view_documents", "create_documents", "manage_documents"],
    ),
]

# All known permission strings — used for validation
ALL_PERMISSIONS: set[str] = {
    # Tab access
    "access_sales", "access_contacts", "access_marketing",
    "access_operations", "access_billing", "access_admin", "access_reports",
    # Business
    "manage_business",
    # Team
    "manage_team",
    # Phone
    "manage_phone",
    # Sales
    "assign_leads", "view_all_leads",
    # Operations
    "assign_jobs", "view_all_jobs",
    # Billing
    "manage_billing",
    # Data
    "export_data",
    # Legal
    "view_documents", "create_documents", "manage_documents",
}


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_role_business_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4, server_default=text("gen_random_uuid()"),
    )
    # NULL = system role (shared across all businesses)
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # List of permission strings e.g. ["access_sales", "assign_leads"]
    # ["*"] = all permissions (global_admin)
    permissions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    member_roles = relationship("BusinessMemberRole", back_populates="role", cascade="all, delete-orphan")


class BusinessMemberRole(Base):
    """Many-to-many: business_members ↔ roles."""
    __tablename__ = "business_member_roles"
    __table_args__ = (
        UniqueConstraint("member_id", "role_id", name="uq_member_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4, server_default=text("gen_random_uuid()"),
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    role = relationship("Role", back_populates="member_roles")
    member = relationship("BusinessMember", back_populates="roles_assoc")
