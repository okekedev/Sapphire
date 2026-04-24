"""Pydantic schemas for the CRM: organizations, contacts, interactions."""

from uuid import UUID
from typing import Optional
from datetime import datetime, date

from pydantic import BaseModel, Field, AliasChoices


# ─────────────────────────────────────────
# Organization
# ─────────────────────────────────────────

class OrganizationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    address_line1: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    address_line1: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)


class OrganizationOut(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    contact_count: int = 0

    model_config = {"from_attributes": True}


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationOut]
    total: int


# ─────────────────────────────────────────
# Interaction
# ─────────────────────────────────────────

class InteractionCreate(BaseModel):
    contact_id: UUID
    type: str = Field(
        ...,
        pattern="^(call|email|form_submit|sms|fb_message|payment|note)$",
    )
    direction: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    metadata: Optional[dict] = None


class InteractionOut(BaseModel):
    id: UUID
    business_id: UUID
    contact_id: UUID
    type: str
    direction: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    # ORM stores this as metadata_ (Python attr) / metadata (DB column).
    # Use validation_alias so Pydantic reads metadata_ from the ORM object
    # and serializes it as "metadata" in JSON responses.
    metadata: Optional[dict] = Field(
        None,
        validation_alias=AliasChoices("metadata_", "metadata"),
    )
    created_by: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class InteractionListResponse(BaseModel):
    interactions: list[InteractionOut]
    total: int


# ─────────────────────────────────────────
# Contact
# ─────────────────────────────────────────

class ContactCreate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    status: str = Field(
        default="new",
        pattern="^(new|prospect|active_customer|no_conversion|churned|other)$",
    )
    source_channel: Optional[str] = Field(None, max_length=100)
    campaign_id: Optional[str] = Field(None, max_length=255)
    utm_source: Optional[str] = Field(None, max_length=255)
    utm_medium: Optional[str] = Field(None, max_length=255)
    utm_campaign: Optional[str] = Field(None, max_length=255)
    stripe_customer_id: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    birthday: Optional[date] = None
    notes: Optional[str] = None
    organization_id: Optional[UUID] = None
    contact_role: Optional[str] = Field(None, max_length=100)


class ContactUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    phone_verified: Optional[bool] = None
    email: Optional[str] = Field(None, max_length=255)
    email_verified: Optional[bool] = None
    status: Optional[str] = Field(
        None,
        pattern="^(new|prospect|active_customer|no_conversion|churned|other)$",
    )
    source_channel: Optional[str] = Field(None, max_length=100)
    campaign_id: Optional[str] = Field(None, max_length=255)
    utm_source: Optional[str] = Field(None, max_length=255)
    utm_medium: Optional[str] = Field(None, max_length=255)
    utm_campaign: Optional[str] = Field(None, max_length=255)
    stripe_customer_id: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    birthday: Optional[date] = None
    notes: Optional[str] = None
    organization_id: Optional[UUID] = None
    contact_role: Optional[str] = Field(None, max_length=100)


class ContactStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        pattern="^(new|prospect|active_customer|no_conversion|churned|other)$",
    )


class ContactOut(BaseModel):
    id: UUID
    business_id: UUID
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    phone_verified: bool
    email: Optional[str] = None
    email_verified: bool
    status: str
    source_channel: Optional[str] = None
    campaign_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    birthday: Optional[date] = None
    notes: Optional[str] = None
    organization_id: Optional[UUID] = None
    organization_name: Optional[str] = None
    contact_role: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactWithInteractions(ContactOut):
    """Contact with recent interactions included."""
    interactions: list[InteractionOut] = []


class ContactListResponse(BaseModel):
    contacts: list[ContactOut]
    total: int


class CRMSummary(BaseModel):
    """Top-level CRM counts."""
    prospects: int = 0
    active_customers: int = 0
    churned: int = 0
    total: int = 0
    interactions_today: int = 0
