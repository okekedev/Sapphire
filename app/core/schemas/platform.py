"""Pydantic schemas for platform connections and OAuth flows."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

class OAuthInitRequest(BaseModel):
    """Request to start an OAuth flow for a platform."""
    platform: str           # e.g. "google_search_console"
    business_id: UUID
    department_id: UUID | None = None  # Optional — NULL = shared/business-wide


class OAuthInitResponse(BaseModel):
    """The authorization URL the frontend should redirect to."""
    auth_url: str
    state: str


# ---------------------------------------------------------------------------
# API key connection
# ---------------------------------------------------------------------------

class ApiKeyConnectRequest(BaseModel):
    """Connect a platform that uses an API key (Ahrefs, SEMrush, etc.)."""
    platform: str
    business_id: UUID
    api_key: str
    department_id: UUID | None = None  # Optional — NULL = shared/business-wide


# ---------------------------------------------------------------------------
# Connected account responses
# ---------------------------------------------------------------------------

class ConnectedAccountOut(BaseModel):
    """Public view of a connected platform account."""
    id: UUID
    business_id: UUID
    department_id: UUID | None = None
    platform: str
    auth_method: str
    scopes: str | None = None
    external_account_id: str | None = None
    status: str
    token_expires_at: datetime | None = None
    connected_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DisconnectRequest(BaseModel):
    """Request to disconnect a platform."""
    platform: str
    business_id: UUID
    department_id: UUID | None = None  # Optional — NULL = shared/business-wide


# ---------------------------------------------------------------------------
# Google Search Console data
# ---------------------------------------------------------------------------

class GSCPropertyOut(BaseModel):
    """A verified property in Google Search Console."""
    site_url: str
    permission_level: str


class GSCQueryRow(BaseModel):
    """A single row from the GSC search analytics report."""
    keys: list[str]           # [query, page, country, device, date]
    clicks: float
    impressions: float
    ctr: float
    position: float


class GSCReportRequest(BaseModel):
    """Request parameters for a GSC search analytics query."""
    business_id: UUID
    site_url: str
    start_date: str           # YYYY-MM-DD
    end_date: str             # YYYY-MM-DD
    dimensions: list[str] = ["query", "page"]
    row_limit: int = 1000


class GSCReportResponse(BaseModel):
    """Response from GSC search analytics."""
    rows: list[GSCQueryRow]
    response_aggregation_type: str | None = None


# ---------------------------------------------------------------------------
# Google Analytics data
# ---------------------------------------------------------------------------

class GAPropertyOut(BaseModel):
    """A GA4 property."""
    property_id: str
    display_name: str


class GAReportRequest(BaseModel):
    """Request parameters for a GA4 report."""
    business_id: UUID
    property_id: str
    start_date: str
    end_date: str
    metrics: list[str] = ["sessions", "totalUsers", "screenPageViews"]
    dimensions: list[str] = ["date"]


class GAReportRow(BaseModel):
    """A single row from GA4."""
    dimension_values: list[str]
    metric_values: list[str]


class GAReportResponse(BaseModel):
    """Response from GA4 reporting API."""
    rows: list[GAReportRow]
    row_count: int
    metadata: dict | None = None
