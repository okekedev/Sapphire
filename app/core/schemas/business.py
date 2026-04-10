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
    narrative: str | None = None
    source: str | None = None  # onboarding | manual_edit


class CompanyProfileOut(BaseModel):
    narrative: str | None = None

    model_config = {"from_attributes": True}


class BusinessOut(BaseModel):
    id: UUID
    name: str
    website: str | None
    industry: str | None
    plan: str
    narrative: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
