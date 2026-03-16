"""Conversation models — persist chat threads.

Supports conversation types:
- **user_chat** (source="user_chat"): User ↔ assistant for onboarding
- **department_chat** (source="department_chat"): User ↔ department head

Proposals are stored as JSON metadata on assistant messages.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, String, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    """A chat conversation — either with the assistant or a department head."""
    __tablename__ = "conversations"

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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(255),
    )  # Auto-generated from first user message

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active",
    )  # active, archived, approved

    # Which employee is the assistant (NULL = onboarding assistant)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
    )

    # Conversation type: "user_chat" or "department_chat"
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="user_chat",
    )

    # False for new conversations (drives notification badge)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true",
    )

    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    business = relationship("Business", foreign_keys=[business_id])
    user = relationship("User", foreign_keys=[user_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at.asc()",
    )


class ConversationMessage(Base):
    """A single message in a conversation."""
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )  # "user" or "assistant"

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Store proposal JSON if this assistant message contains one
    proposal: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Store delivery content on assistant messages
    delivery_content: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Message status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="complete",
    )  # "complete", "error"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
