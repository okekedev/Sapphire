"""
Contacts Router — CRM CRUD for contacts, interactions, and phone lines.

Endpoints:
  GET    /contacts/summary                — CRM counts per status
  GET    /contacts                        — list contacts (filter by status)
  POST   /contacts                        — create contact
  GET    /contacts/{contact_id}           — get contact with interactions
  PATCH  /contacts/{contact_id}           — update contact
  PATCH  /contacts/{contact_id}/status    — quick status transition
  DELETE /contacts/{contact_id}           — delete contact

  GET    /contacts/{contact_id}/interactions         — list interactions
  POST   /contacts/{contact_id}/interactions         — log interaction

  GET    /phone-lines                — list phone lines
  POST   /phone-lines               — create phone line
  PATCH  /phone-lines/{id}          — update phone line
  DELETE /phone-lines/{id}          — delete phone line
"""

import logging
from uuid import UUID
from typing import Optional
from datetime import datetime, timezone, date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.config import settings as app_settings
from app.database import get_db
from app.marketing.models import Contact, Interaction, BusinessPhoneLine
from app.admin.services.twilio_service import twilio_service
from app.marketing.schemas.contact import (
    ContactCreate,
    ContactUpdate,
    ContactStatusUpdate,
    ContactOut,
    ContactWithInteractions,
    ContactListResponse,
    CRMSummary,
    InteractionCreate,
    InteractionOut,
    InteractionListResponse,
    PhoneLineCreate,
    PhoneLineUpdate,
    PhoneLineOut,
)
from app.core.services.auth_service import get_current_user_id

router = APIRouter(prefix="/contacts", tags=["Contacts"])
phone_lines_router = APIRouter(prefix="/phone-lines", tags=["Phone Lines"])


# ── Helpers ──

async def _get_contact_or_404(
    contact_id: UUID, business_id: UUID, db: AsyncSession
) -> Contact:
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.business_id == business_id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


# ── CRM Summary ──

@router.get("/summary", response_model=CRMSummary)
async def get_crm_summary(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return counts of contacts by status and today's interaction count."""
    # Status breakdown
    status_result = await db.execute(
        select(Contact.status, func.count(Contact.id).label("cnt"))
        .where(Contact.business_id == business_id)
        .group_by(Contact.status)
    )
    counts = {row.status: row.cnt for row in status_result.all()}

    # Interactions today
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    interaction_result = await db.execute(
        select(func.count(Interaction.id))
        .where(
            Interaction.business_id == business_id,
            Interaction.created_at >= today_start,
        )
    )
    interactions_today = interaction_result.scalar_one()

    total = sum(counts.values())
    return CRMSummary(
        prospects=counts.get("prospect", 0),
        active_customers=counts.get("active_customer", 0),
        churned=counts.get("churned", 0),
        total=total,
        interactions_today=interactions_today,
    )


# ── Contacts CRUD ──

@router.get("", response_model=ContactListResponse)
async def list_contacts(
    business_id: UUID,
    status: Optional[str] = Query(
        None,
        pattern="^(prospect|active_customer|churned)$",
    ),
    source_channel: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search name, phone, or email"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List contacts, optionally filtered by status or searched by name/phone/email."""
    q = select(Contact).where(Contact.business_id == business_id)

    if status:
        q = q.where(Contact.status == status)
    if source_channel:
        q = q.where(Contact.source_channel == source_channel)
    if search:
        pattern = f"%{search}%"
        from sqlalchemy import or_
        q = q.where(
            or_(
                Contact.full_name.ilike(pattern),
                Contact.phone.ilike(pattern),
                Contact.email.ilike(pattern),
            )
        )

    q = q.order_by(Contact.updated_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    contacts = result.scalars().all()

    # Total
    count_q = select(func.count(Contact.id)).where(Contact.business_id == business_id)
    if status:
        count_q = count_q.where(Contact.status == status)
    if search:
        pattern = f"%{search}%"
        from sqlalchemy import or_
        count_q = count_q.where(
            or_(
                Contact.full_name.ilike(pattern),
                Contact.phone.ilike(pattern),
                Contact.email.ilike(pattern),
            )
        )
    total = (await db.execute(count_q)).scalar_one()

    return ContactListResponse(contacts=list(contacts), total=total)


@router.post("", response_model=ContactOut, status_code=201)
async def create_contact(
    business_id: UUID,
    payload: ContactCreate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new contact (prospect or customer)."""
    contact = Contact(
        business_id=business_id,
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        status=payload.status,
        source_channel=payload.source_channel,
        campaign_id=payload.campaign_id,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        stripe_customer_id=payload.stripe_customer_id,
        address_line1=payload.address_line1,
        city=payload.city,
        state=payload.state,
        zip_code=payload.zip_code,
        country=payload.country,
        birthday=payload.birthday,
        notes=payload.notes,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactWithInteractions)
async def get_contact(
    contact_id: UUID,
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a contact with their recent interaction history."""
    result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.interactions))
        .where(Contact.id == contact_id, Contact.business_id == business_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: UUID,
    business_id: UUID,
    payload: ContactUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update contact fields."""
    contact = await _get_contact_or_404(contact_id, business_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return contact


@router.patch("/{contact_id}/status", response_model=ContactOut)
async def update_contact_status(
    contact_id: UUID,
    business_id: UUID,
    payload: ContactStatusUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Quick prospect → customer (or churn) transition."""
    contact = await _get_contact_or_404(contact_id, business_id, db)
    contact.status = payload.status
    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: UUID,
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a contact (cascades to interactions)."""
    contact = await _get_contact_or_404(contact_id, business_id, db)
    await db.delete(contact)
    await db.commit()


# ── Interactions ──

@router.get("/{contact_id}/interactions", response_model=InteractionListResponse)
async def list_interactions(
    contact_id: UUID,
    business_id: UUID,
    type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List interactions for a contact."""
    await _get_contact_or_404(contact_id, business_id, db)

    q = select(Interaction).where(
        Interaction.contact_id == contact_id,
        Interaction.business_id == business_id,
    )
    if type:
        q = q.where(Interaction.type == type)
    q = q.order_by(Interaction.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    interactions = result.scalars().all()

    count_q = select(func.count(Interaction.id)).where(
        Interaction.contact_id == contact_id
    )
    total = (await db.execute(count_q)).scalar_one()

    return InteractionListResponse(interactions=list(interactions), total=total)


@router.post("/{contact_id}/interactions", response_model=InteractionOut, status_code=201)
async def log_interaction(
    contact_id: UUID,
    business_id: UUID,
    payload: InteractionCreate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Log a new interaction for a contact."""
    await _get_contact_or_404(contact_id, business_id, db)

    interaction = Interaction(
        business_id=business_id,
        contact_id=contact_id,
        type=payload.type,
        direction=payload.direction,
        subject=payload.subject,
        body=payload.body,
        metadata_=payload.metadata,
        created_by=current_user_id,
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)
    return interaction


# ── Phone Lines (mounted separately in main.py) ──

@phone_lines_router.get("", response_model=list[PhoneLineOut])
async def list_phone_lines(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessPhoneLine)
        .where(BusinessPhoneLine.business_id == business_id)
        .order_by(BusinessPhoneLine.created_at.desc())
    )
    return list(result.scalars().all())


@phone_lines_router.post("", response_model=PhoneLineOut, status_code=201)
async def create_phone_line(
    business_id: UUID,
    payload: PhoneLineCreate,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    line = BusinessPhoneLine(
        business_id=business_id,
        twilio_number=payload.twilio_number,
        twilio_number_sid=payload.twilio_number_sid,
        friendly_name=payload.friendly_name,
        campaign_name=payload.campaign_name,
        ad_account_id=payload.ad_account_id,
        channel=payload.channel,
        line_type=payload.line_type,
        department_id=payload.department_id,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)

    # Auto-configure Twilio webhook so inbound calls route to our IVR
    if payload.twilio_number_sid:
        try:
            # Read webhook URL from DB (phone_settings is source of truth)
            from app.admin.models import PhoneSettings
            ps_result = await db.execute(
                select(PhoneSettings.webhook_base_url).where(
                    PhoneSettings.business_id == business_id
                )
            )
            webhook_base = ps_result.scalar_one_or_none() or str(request.base_url).rstrip("/")
            voice_url = f"{webhook_base}{app_settings.api_prefix}/twilio/voice?business_id={business_id}"
            status_url = f"{webhook_base}{app_settings.api_prefix}/twilio/call-status?business_id={business_id}"
            await twilio_service.configure_webhook(
                db=db,
                business_id=business_id,
                number_sid=payload.twilio_number_sid,
                voice_url=voice_url,
                status_callback_url=status_url,
            )
            logger.info(f"Auto-configured webhook for {payload.twilio_number} → {voice_url}")
        except Exception as e:
            logger.warning(f"Failed to auto-configure webhook for {payload.twilio_number}: {e}")

    return line


@phone_lines_router.patch("/{line_id}", response_model=PhoneLineOut)
async def update_phone_line(
    line_id: UUID,
    business_id: UUID,
    payload: PhoneLineUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessPhoneLine).where(
            BusinessPhoneLine.id == line_id,
            BusinessPhoneLine.business_id == business_id,
        )
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status_code=404, detail="Phone line not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(line, field, value)

    await db.commit()
    await db.refresh(line)
    return line


@phone_lines_router.delete("/{line_id}", status_code=204)
async def delete_phone_line(
    line_id: UUID,
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessPhoneLine).where(
            BusinessPhoneLine.id == line_id,
            BusinessPhoneLine.business_id == business_id,
        )
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status_code=404, detail="Phone line not found")
    await db.delete(line)
    await db.commit()
