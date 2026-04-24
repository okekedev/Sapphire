"""Pydantic schemas for phone settings endpoints.

Department routing (forward_number, enabled) is read/written on the
departments table directly — no longer stored as JSONB on phone_settings.
"""

from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field


class DepartmentRoutingRule(BaseModel):
    """One department's routing config — read from departments table."""
    name: str
    department_id: UUID
    forward_number: Optional[str] = Field(None, description="Personal phone to forward calls to (E.164)")
    enabled: bool = True
    sms_enabled: bool = False


class PhoneSettingsRead(BaseModel):
    """Phone settings response."""
    business_id: UUID
    greeting_text: Optional[str] = None
    hold_message: Optional[str] = None
    voice_name: str = "Google.en-US-Chirp3-HD-Aoede"
    recording_enabled: bool = True
    transcription_enabled: bool = False
    forward_all_calls: bool = True
    default_forward_number: Optional[str] = None
    ring_timeout_s: int = 30
    business_hours_start: Optional[str] = None
    business_hours_end: Optional[str] = None
    business_timezone: str = "America/Chicago"
    after_hours_enabled: bool = False
    after_hours_action: str = "message"  # "message" or "forward"
    after_hours_message: Optional[str] = None
    after_hours_forward_number: Optional[str] = None
    # Built from departments table (not JSONB)
    departments_config: Optional[list[DepartmentRoutingRule]] = None


class PhoneSettingsUpdate(BaseModel):
    """Phone settings partial update request. Only provided fields are updated."""
    greeting_text: Optional[str] = None
    hold_message: Optional[str] = None
    voice_name: Optional[str] = None
    recording_enabled: Optional[bool] = None
    transcription_enabled: Optional[bool] = None
    forward_all_calls: Optional[bool] = None
    default_forward_number: Optional[str] = None
    ring_timeout_s: Optional[int] = None
    business_hours_start: Optional[str] = None
    business_hours_end: Optional[str] = None
    business_timezone: Optional[str] = None
    after_hours_enabled: Optional[bool] = None
    after_hours_action: Optional[str] = None
    after_hours_message: Optional[str] = None
    after_hours_forward_number: Optional[str] = None
    # Department routing updates — written to departments table
    departments_config: Optional[list[DepartmentRoutingRule]] = None
