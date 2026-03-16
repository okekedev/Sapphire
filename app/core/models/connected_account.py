"""
ConnectedAccount model — encrypted credentials for platform integrations.

Department-scoped: each connection belongs to a department (Stripe→Finance,
Facebook→Marketing, etc.). Shared connections (Twilio, Claude) use
department_id=NULL.

Supported platforms:
  OAuth: facebook, instagram, google_analytics, pinterest
  API-key/token: twilio, stripe, ngrok
  CLI token: claude

Additional OAuth platforms (no action handlers yet):
  google_search_console, google_business, linkedin, twitter,
  yelp, tiktok, youtube, nextdoor
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, LargeBinary, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "platform", "department_id",
            name="uq_business_platform_dept",
        ),
        Index("ix_connected_accounts_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )  # NULL = shared/business-wide (twilio, claude); UUID = department-scoped
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "facebook", "google_search_console"
    auth_method: Mapped[str] = mapped_column(String(20), nullable=False)  # "oauth" | "api_key"
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    scopes: Mapped[str | None] = mapped_column(String(1000))
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), server_default="active")  # active | expired | revoked
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
