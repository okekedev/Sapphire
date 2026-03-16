"""Admin models — PhoneSettings.

PhoneSettings: Per-business mainline greeting, voice, routing, transcription config.
Also stores Twilio A2P 10DLC SIDs (messaging_service_sid, brand_registration_sid)
for querying campaign status via Twilio API. Registration itself is done in Twilio Console.

Department-level call routing (forward_number, enabled, sms_enabled) lives on the
departments table, NOT here. See Department model in organization.py.
"""

import uuid
from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Boolean, Text, ForeignKey, Time, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PhoneSettings(Base):
    """
    Per-business Twilio mainline configuration.

    Stores greeting customization, voice selection, recording/transcription toggles,
    and forwarding rules. Department routing (forward_number, enabled) is on the
    departments table directly.
    """
    __tablename__ = "phone_settings"

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
        unique=True,
        index=True,
    )

    # ── Greeting ──
    greeting_text: Mapped[Optional[str]] = mapped_column(Text)
    voice_name: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="Google.en-US-Chirp3-HD-Aoede",
    )

    # ── Hold / Routing Message (plays after caller states their reason) ──
    hold_message: Mapped[Optional[str]] = mapped_column(
        Text,
        server_default="Thank you, please hold while I connect your call. This call may be recorded for quality purposes.",
    )

    # ── Recording & Transcription ──
    recording_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true",
    )
    transcription_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )

    # ── Forwarding Rules ──
    forward_all_calls: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true",
    )
    default_forward_number: Mapped[Optional[str]] = mapped_column(String(20))
    ring_timeout_s: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30",
    )

    # ── Business Hours & After-Hours ──
    business_hours_start: Mapped[Optional[time]] = mapped_column(Time)
    business_hours_end: Mapped[Optional[time]] = mapped_column(Time)
    business_timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="America/Chicago",
    )
    after_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    after_hours_action: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="message",
    )  # "message" (play after-hours message + hangup) or "forward" (forward to number)
    after_hours_message: Mapped[Optional[str]] = mapped_column(Text)
    after_hours_forward_number: Mapped[Optional[str]] = mapped_column(String(20))

    # ── A2P 10DLC (registration done in Twilio Console, SIDs stored for API queries) ──
    messaging_service_sid: Mapped[Optional[str]] = mapped_column(
        String(50),
    )  # Twilio Messaging Service SID — used to check campaign status + add new numbers
    brand_registration_sid: Mapped[Optional[str]] = mapped_column(
        String(50),
    )  # TCR brand SID — used to verify numbers are branded

    # ── SMS Toggle (legacy — unused) ──
    sms_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )

    # ── WhatsApp (legacy columns — WhatsApp config moved to departments table) ──
    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    whatsapp_from_number: Mapped[Optional[str]] = mapped_column(String(20))

    # ── Webhook URL (ngrok tunnel or production domain — persisted across restarts) ──
    webhook_base_url: Mapped[str] = mapped_column(
        String(500), nullable=False, server_default="",
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
