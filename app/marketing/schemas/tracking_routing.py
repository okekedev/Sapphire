"""Pydantic schemas for Tracking & Routing tab: call log + aggregations.

Includes department-context fields for the context calling system:
  department_context — which department tab this call appears in
  call_category — AI-determined category (inquiry, job_request, payment_inquiry, etc.)
  ai_processed — whether an AI employee has processed this call after human review
"""

from uuid import UUID
from typing import Optional
from datetime import datetime

from pydantic import BaseModel


class CallLogItem(BaseModel):
    """One call row in the Calls by Campaign table."""
    id: UUID
    contact_id: Optional[UUID] = None
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    campaign_name: Optional[str] = None
    channel: Optional[str] = None
    summary: Optional[str] = None
    routed_to: Optional[str] = None
    status: Optional[str] = None  # completed | followup | dropped
    score: Optional[str] = None
    next_step: Optional[str] = None
    duration_s: Optional[int] = None
    recording_url: Optional[str] = None
    disposition: str = "unreviewed"  # unreviewed | lead | spam | other
    # Department context calling fields
    department_context: Optional[str] = None  # Sales | Operations | Finance | Marketing | Admin
    call_category: Optional[str] = None  # inquiry, job_request, payment_inquiry, etc.
    suggested_action: Optional[str] = None  # AI-suggested next action
    ai_processed: bool = False  # True after "Process with AI" button is clicked
    ai_process_output: Optional[str] = None  # Output from AI employee processing
    created_at: datetime


class CallLogResponse(BaseModel):
    calls: list[CallLogItem]
    total: int


class DepartmentSummaryItem(BaseModel):
    """One row in the Summary by Department table."""
    department: str
    total_calls: int = 0
    avg_duration_s: float = 0
    completed_count: int = 0
    completed_pct: float = 0
    followup_count: int = 0
    top_campaign: Optional[str] = None
    top_campaign_count: int = 0


class CampaignSummaryItem(BaseModel):
    """One row in the Campaign summary table."""
    campaign_name: str
    total_calls: int = 0
    completed_count: int = 0
    followup_count: int = 0
    dropped_count: int = 0
    avg_duration_s: float = 0


# ── Department Context Calling schemas ──


class RerouteCallRequest(BaseModel):
    """Re-assign a call to a different department."""
    department: str  # Sales | Operations | Finance | Marketing | Admin


class ProcessCallRequest(BaseModel):
    """Trigger AI processing of a reviewed call."""
    pass  # No extra fields needed — department_context is already set


class ProcessCallResponse(BaseModel):
    """Response from AI employee processing."""
    status: str  # processed | error
    employee: Optional[str] = None
    department: Optional[str] = None
    output: Optional[str] = None
    message: Optional[str] = None
