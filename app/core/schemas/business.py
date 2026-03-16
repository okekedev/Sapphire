"""Pydantic schemas for business routes."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BusinessCreate(BaseModel):
    name: str
    website: str | None = None
    industry: str | None = None


class BusinessUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    industry: str | None = None


class CompanyProfileInput(BaseModel):
    """Structured company profile — predefined fields synced with DB columns."""
    description: str | None = None
    services: str | None = None
    target_audience: str | None = None
    online_presence: str | None = None
    brand_voice: str | None = None
    goals: str | None = None
    competitive_landscape: str | None = None
    source: str | None = None  # onboarding | manual_edit


class CompanyProfileOut(BaseModel):
    """Company profile response — maps 1:1 with DB columns."""
    description: str | None = None
    services: str | None = None
    target_audience: str | None = None
    online_presence: str | None = None
    brand_voice: str | None = None
    goals: str | None = None
    competitive_landscape: str | None = None
    profile_source: str | None = None

    model_config = {"from_attributes": True}


class BusinessOut(BaseModel):
    id: UUID
    name: str
    website: str | None
    industry: str | None
    plan: str
    # Profile fields inline
    description: str | None = None
    services: str | None = None
    target_audience: str | None = None
    online_presence: str | None = None
    brand_voice: str | None = None
    goals: str | None = None
    competitive_landscape: str | None = None
    profile_source: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
