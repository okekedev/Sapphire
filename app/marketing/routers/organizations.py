"""
Organizations Router — B2B account layer above contacts.

Endpoints:
  GET    /organizations              — list orgs with contact count
  POST   /organizations              — create org
  GET    /organizations/{org_id}     — get org with contacts
  PATCH  /organizations/{org_id}     — update org
  DELETE /organizations/{org_id}     — delete org
"""

import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.marketing.models import Organization, Contact
from app.marketing.schemas.contact import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationOut,
    OrganizationListResponse,
    ContactOut,
    ContactListResponse,
)
from app.core.services.auth_service import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


async def _get_org_or_404(org_id: UUID, business_id: UUID, db: AsyncSession) -> Organization:
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.business_id == business_id,
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("", response_model=OrganizationListResponse)
async def list_organizations(
    business_id: UUID,
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List organizations with contact counts."""
    q = select(Organization).where(Organization.business_id == business_id)
    if search:
        q = q.where(Organization.name.ilike(f"%{search}%"))
    q = q.order_by(Organization.name).limit(limit).offset(offset)

    result = await db.execute(q)
    orgs = result.scalars().all()

    # Batch contact counts
    org_ids = [o.id for o in orgs]
    count_map: dict[UUID, int] = {}
    if org_ids:
        counts = await db.execute(
            select(Contact.organization_id, func.count(Contact.id).label("cnt"))
            .where(Contact.organization_id.in_(org_ids))
            .group_by(Contact.organization_id)
        )
        count_map = {row.organization_id: row.cnt for row in counts.all()}

    total_q = select(func.count(Organization.id)).where(Organization.business_id == business_id)
    if search:
        total_q = total_q.where(Organization.name.ilike(f"%{search}%"))
    total = (await db.execute(total_q)).scalar_one()

    items = [
        OrganizationOut(
            id=o.id,
            business_id=o.business_id,
            name=o.name,
            domain=o.domain,
            industry=o.industry,
            website=o.website,
            notes=o.notes,
            address_line1=o.address_line1,
            city=o.city,
            state=o.state,
            zip_code=o.zip_code,
            country=o.country,
            created_at=o.created_at,
            updated_at=o.updated_at,
            contact_count=count_map.get(o.id, 0),
        )
        for o in orgs
    ]
    return OrganizationListResponse(organizations=items, total=total)


@router.post("", response_model=OrganizationOut, status_code=201)
async def create_organization(
    business_id: UUID,
    payload: OrganizationCreate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new organization."""
    org = Organization(
        business_id=business_id,
        name=payload.name,
        domain=payload.domain,
        industry=payload.industry,
        website=payload.website,
        notes=payload.notes,
        address_line1=payload.address_line1,
        city=payload.city,
        state=payload.state,
        zip_code=payload.zip_code,
        country=payload.country,
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return OrganizationOut(
        id=org.id,
        business_id=org.business_id,
        name=org.name,
        domain=org.domain,
        industry=org.industry,
        website=org.website,
        notes=org.notes,
        address_line1=org.address_line1,
        city=org.city,
        state=org.state,
        zip_code=org.zip_code,
        country=org.country,
        created_at=org.created_at,
        updated_at=org.updated_at,
        contact_count=0,
    )


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: UUID,
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get an organization."""
    org = await _get_org_or_404(org_id, business_id, db)
    count = (await db.execute(
        select(func.count(Contact.id)).where(Contact.organization_id == org_id)
    )).scalar_one()
    return OrganizationOut(
        id=org.id,
        business_id=org.business_id,
        name=org.name,
        domain=org.domain,
        industry=org.industry,
        website=org.website,
        notes=org.notes,
        address_line1=org.address_line1,
        city=org.city,
        state=org.state,
        zip_code=org.zip_code,
        country=org.country,
        created_at=org.created_at,
        updated_at=org.updated_at,
        contact_count=count,
    )


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: UUID,
    business_id: UUID,
    payload: OrganizationUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update organization details."""
    org = await _get_org_or_404(org_id, business_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.flush()
    await db.refresh(org)
    count = (await db.execute(
        select(func.count(Contact.id)).where(Contact.organization_id == org_id)
    )).scalar_one()
    return OrganizationOut(
        id=org.id,
        business_id=org.business_id,
        name=org.name,
        domain=org.domain,
        industry=org.industry,
        website=org.website,
        notes=org.notes,
        address_line1=org.address_line1,
        city=org.city,
        state=org.state,
        zip_code=org.zip_code,
        country=org.country,
        created_at=org.created_at,
        updated_at=org.updated_at,
        contact_count=count,
    )


@router.delete("/{org_id}", status_code=204)
async def delete_organization(
    org_id: UUID,
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete an organization (contacts' organization_id set to NULL via FK cascade)."""
    org = await _get_org_or_404(org_id, business_id, db)
    await db.delete(org)
    await db.flush()
