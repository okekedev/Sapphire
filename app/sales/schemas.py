"""Pydantic schemas for the Sales tab: customers, jobs, pipeline, and billing.

Pipeline flow:
  New (unreviewed call) → Lead (confirmed prospect) → Converted (job created)
  or → No Lead (with AI-generated reason, editable before confirming)

When qualifying or converting, the AI pre-generates a reason/description
that the user can review, edit, then confirm.
"""

from uuid import UUID
from typing import Optional
from datetime import datetime

from pydantic import BaseModel


# ── Customers ──

class CustomerItem(BaseModel):
    """One customer row in the Customers sub-view."""
    id: UUID
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: str = "new"  # new | prospect | active_customer | no_conversion | other
    source_channel: Optional[str] = None
    acquisition_campaign: Optional[str] = None
    total_revenue: float = 0
    job_count: int = 0
    notes: Optional[str] = None
    created_at: datetime
    # Call context — populated from the latest Sales interaction for leads
    call_summary: Optional[str] = None
    transcript: Optional[str] = None
    call_category: Optional[str] = None
    suggested_action: Optional[str] = None
    score: Optional[str] = None
    duration_s: Optional[int] = None
    campaign_name: Optional[str] = None
    assigned_to: Optional[UUID] = None
    assigned_user_name: Optional[str] = None


class CustomerListResponse(BaseModel):
    customers: list[CustomerItem]
    total: int


class CreateCustomerRequest(BaseModel):
    full_name: str
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: str = "new"
    source_channel: Optional[str] = None
    notes: Optional[str] = None


class UpdateCustomerRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    assigned_to: Optional[UUID] = None


# ── Jobs ──

class JobItem(BaseModel):
    """One job row in the Jobs sub-view."""
    id: UUID
    contact_id: UUID
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    source: Optional[str] = None  # "sales" when converted from lead
    title: str
    description: Optional[str] = None
    status: str = "new"  # new | scheduled | dispatched | started | completed | billing
    notes: Optional[str] = None
    amount_quoted: Optional[float] = None
    amount_billed: Optional[float] = None
    # Template
    template_id: Optional[UUID] = None
    template_data: Optional[dict] = None
    # Assignment + scheduling
    assigned_to: Optional[UUID] = None
    assigned_staff_name: Optional[str] = None
    assigned_staff_color: Optional[str] = None
    service_address: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    # Call context — carried from Sales lead conversion via job.metadata_
    call_summary: Optional[str] = None
    call_category: Optional[str] = None
    suggested_action: Optional[str] = None
    lead_notes: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: list[JobItem]
    total: int


class CreateJobRequest(BaseModel):
    contact_id: UUID
    title: str
    description: Optional[str] = None
    notes: Optional[str] = None
    amount_quoted: Optional[float] = None
    template_id: Optional[UUID] = None
    service_address: Optional[str] = None


class UpdateJobRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    amount_quoted: Optional[float] = None
    amount_billed: Optional[float] = None
    template_id: Optional[UUID] = None
    template_data: Optional[dict] = None
    assigned_to: Optional[UUID] = None
    service_address: Optional[str] = None
    scheduled_at: Optional[datetime] = None


# ── Sales Summary (for dashboard / KPIs) ──

class SalesSummary(BaseModel):
    total_prospects: int = 0
    total_customers: int = 0
    total_no_conversion: int = 0
    active_jobs: int = 0
    completed_jobs: int = 0
    total_revenue: float = 0
    total_quoted: float = 0


# ── Pipeline: Prospects (New unreviewed calls) ──


class ProspectItem(BaseModel):
    """One prospect card — an unreviewed call routed to Sales."""
    interaction_id: UUID
    contact_id: Optional[UUID] = None
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    call_summary: Optional[str] = None
    transcript: Optional[str] = None
    call_category: Optional[str] = None
    suggested_action: Optional[str] = None
    score: Optional[str] = None
    duration_s: Optional[int] = None
    recording_url: Optional[str] = None
    campaign_name: Optional[str] = None
    created_at: datetime


class ProspectsResponse(BaseModel):
    prospects: list[ProspectItem]
    total: int


# ── Pipeline: Qualify (Lead / No-Lead) ──


class QualifyRequest(BaseModel):
    """Qualify a prospect as Lead or No-Lead.

    The AI pre-generates a reason (for no-lead) or lead summary (for lead).
    The user can edit before confirming.
    """
    decision: str  # "lead" | "no_lead"
    reason: Optional[str] = None  # AI-generated, user-editable — why no-lead
    lead_summary: Optional[str] = None  # AI-generated, user-editable — lead context


class QualifyResponse(BaseModel):
    status: str  # "qualified"
    decision: str  # "lead" | "no_lead"
    contact_id: Optional[UUID] = None


# ── Pipeline: Convert to Job ──


class ConvertToJobRequest(BaseModel):
    """Convert a lead to a job in Operations.

    AI pre-generates title + description from the call context.
    User reviews and edits before confirming.
    """
    title: str  # AI-generated, user-editable
    description: Optional[str] = None  # AI-generated, user-editable
    estimate: Optional[float] = None  # dollar amount — stored as amount_quoted on the Job


class ConvertToJobResponse(BaseModel):
    status: str  # "converted"
    job_id: UUID
    contact_id: UUID


class CloseLeadRequest(BaseModel):
    """Close a lead as no-conversion — they were a lead but didn't convert."""
    reason: Optional[str] = None  # why it didn't convert


class CloseLeadResponse(BaseModel):
    status: str  # "closed"
    contact_id: UUID


# ── Pipeline Summary ──


class PipelineSummary(BaseModel):
    """KPI summary for the Sales pipeline header."""
    new_count: int = 0
    lead_count: int = 0
    converted_count: int = 0
    prospect_to_lead_pct: float = 0
    lead_to_job_pct: float = 0


# ── Review: Historical decisions ──


class ReviewItem(BaseModel):
    """A reviewed Sales interaction with two-column outcome tracking.

    Call Outcome: Lead or No Lead (initial qualification decision)
    Lead Outcome: Converted, No Conversion, or Pending (what happened after)
    """
    interaction_id: UUID
    contact_id: Optional[UUID] = None
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    call_summary: Optional[str] = None
    lead_summary: Optional[str] = None
    no_lead_reason: Optional[str] = None
    no_conversion_reason: Optional[str] = None
    disposition: str  # lead | converted | other (no-lead) | no_conversion
    call_outcome: str  # "Lead" | "No Lead"
    lead_outcome: Optional[str] = None  # "Converted" | "No Conversion" | "Pending" | None
    customer_type: Optional[str] = None  # "new" | "returning" | None (not yet converted)
    recording_url: Optional[str] = None
    duration_s: Optional[int] = None
    converted_job_id: Optional[str] = None
    created_at: datetime


class ReviewResponse(BaseModel):
    items: list[ReviewItem]
    total: int
