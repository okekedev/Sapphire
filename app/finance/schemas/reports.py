"""Pydantic schemas for Reports tab: campaign ROI, customer lifecycle, department performance."""

from uuid import UUID
from typing import Optional
from datetime import datetime

from pydantic import BaseModel


class CampaignROIItem(BaseModel):
    """One campaign's ROI metrics."""
    campaign_name: str
    calls_generated: int = 0
    contacts_created: int = 0
    customers_converted: int = 0
    revenue_attributed: float = 0
    conversion_rate: float = 0
    avg_deal_size: float = 0


class CustomerLifecycleItem(BaseModel):
    """One contact's lifecycle analysis: first call vs. first invoice."""
    contact_id: UUID
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    first_call_date: Optional[datetime] = None
    first_invoice_date: Optional[datetime] = None
    is_new_customer: bool = True  # True if first invoice >= first call
    lifetime_revenue: float = 0
    status: Optional[str] = None  # prospect | active_customer | churned


class DepartmentPerformanceItem(BaseModel):
    """One department's performance metrics."""
    department: str
    calls_handled: int = 0
    contacts_generated: int = 0
    revenue_attributed: float = 0
    avg_duration_s: float = 0


# ── Pipeline Funnel ──


class FunnelStage(BaseModel):
    """Metrics for one pipeline stage."""
    stage: str  # calls | leads | jobs_created | jobs_completed | revenue
    label: str  # Human-readable label
    total: int = 0
    new_customers: int = 0
    returning_customers: int = 0
    from_campaigns: int = 0  # Attributed to a tracking number / campaign
    manual: int = 0  # No campaign attribution (manual entry, walk-in, etc.)
    revenue: float = 0  # Revenue attributed to contacts at this stage
    conversion_pct: float = 0  # % of previous stage that reached this stage


class CampaignAttribution(BaseModel):
    """Per-campaign pipeline attribution."""
    campaign_name: str
    channel: Optional[str] = None
    calls: int = 0
    leads: int = 0
    jobs: int = 0
    revenue: float = 0
    new_customers: int = 0
    returning_customers: int = 0


class PipelineFunnelResponse(BaseModel):
    """Complete pipeline funnel with attribution."""
    stages: list[FunnelStage]
    campaigns: list[CampaignAttribution]
    totals: dict[str, float]  # total_calls, total_leads, total_revenue, new_revenue, returning_revenue
    period_days: int
