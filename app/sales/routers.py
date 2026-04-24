"""
Sales Router — Pipeline, Customers, Jobs, and Sales summary endpoints.

Pipeline flow:
  New (unreviewed calls) → Lead (qualified) → Converted (job created)
  or → No Lead (with reason)

Endpoints:
  GET    /sales/prospects              — List unreviewed Sales calls
  PATCH  /sales/prospects/{id}/qualify — Mark Lead or No-Lead
  POST   /sales/leads/{id}/convert     — Convert lead to Job in Operations
  GET    /sales/pipeline-summary       — Pipeline KPI summary
  GET    /sales/customers              — List customers/prospects
  POST   /sales/customers              — Create a customer manually
  PATCH  /sales/customers/{id}         — Update customer details/status
  GET    /sales/jobs                   — List jobs (optionally by customer)
  POST   /sales/jobs                   — Create a job
  PATCH  /sales/jobs/{id}              — Update job details/status
  GET    /sales/summary                — KPI summary for the Sales tab
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.marketing.models import Contact, Interaction
from app.operations.models import Job
from app.finance.models import Payment
from app.core.models.user import User
from app.core.services.auth_service import get_current_user_id
from app.core.services.phone_utils import normalize_phone
from app.sales.schemas import (
    CustomerItem,
    CustomerListResponse,
    CreateCustomerRequest,
    UpdateCustomerRequest,
    JobItem,
    JobListResponse,
    CreateJobRequest,
    UpdateJobRequest,
    SalesSummary,
    ProspectItem,
    ProspectsResponse,
    QualifyRequest,
    QualifyResponse,
    ConvertToJobRequest,
    ConvertToJobResponse,
    CloseLeadRequest,
    CloseLeadResponse,
    PipelineSummary,
    ReviewItem,
    ReviewResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sales", tags=["sales"])


# ── Pipeline: Prospects (unreviewed Sales calls) ──


@router.get("/prospects", response_model=ProspectsResponse)
async def list_prospects(
    business_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List unreviewed calls routed to Sales — the 'New' pipeline column."""
    from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE

    # Find call interactions routed to Sales that haven't been reviewed yet
    base = (
        select(Interaction)
        .where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
            or_(
                Interaction.metadata_["department_context"].astext == "Sales",
                Interaction.metadata_["routed_to_department"].astext == "Sales",
            ),
            or_(
                Interaction.metadata_["disposition"].astext == "unreviewed",
                Interaction.metadata_["disposition"].astext == "",
                ~Interaction.metadata_.has_key("disposition"),
            ),
        )
    )

    # Count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch
    rows = (
        await db.execute(
            base.order_by(Interaction.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    if not rows:
        return ProspectsResponse(prospects=[], total=total)

    # Batch-load contact names for linked contacts
    contact_ids = {r.contact_id for r in rows if r.contact_id}
    contact_map: dict[UUID, Contact] = {}
    if contact_ids:
        c_result = await db.execute(
            select(Contact).where(Contact.id.in_(contact_ids))
        )
        for c in c_result.scalars():
            contact_map[c.id] = c

    prospects = []
    for i in rows:
        meta = i.metadata_ or {}
        # Try to get caller info from contact or from metadata
        contact = contact_map.get(i.contact_id) if i.contact_id else None
        prospects.append(
            ProspectItem(
                interaction_id=i.id,
                contact_id=i.contact_id,
                caller_name=meta.get("ivr_caller_name") or (contact.full_name if contact else None),
                caller_phone=meta.get("from") or (contact.phone if contact else None),
                call_summary=meta.get("summary") or i.subject,
                transcript=i.body,
                call_category=meta.get("call_category"),
                suggested_action=meta.get("suggested_action"),
                score=meta.get("score"),
                duration_s=meta.get("duration_s"),
                recording_url=meta.get("recording_url"),
                campaign_name=meta.get("campaign_name"),
                created_at=i.created_at,
            )
        )

    return ProspectsResponse(prospects=prospects, total=total)


@router.patch("/prospects/{interaction_id}/qualify", response_model=QualifyResponse)
async def qualify_prospect(
    interaction_id: UUID,
    payload: QualifyRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Qualify a prospect as Lead or No-Lead.

    AI pre-generates the reason/summary — user edits then confirms.
    """
    result = await db.execute(
        select(Interaction).where(
            Interaction.id == interaction_id,
            Interaction.business_id == business_id,
        )
    )
    interaction = result.scalar_one_or_none()
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")

    meta = dict(interaction.metadata_ or {})

    if payload.decision == "lead":
        meta["disposition"] = "lead"
        if payload.lead_summary:
            meta["lead_summary"] = payload.lead_summary

        # Find or create a Contact linked to this call
        caller_phone = normalize_phone(meta.get("from"))
        contact_id = interaction.contact_id

        if not contact_id and caller_phone:
            # Try to find existing contact by normalized phone
            existing = await db.execute(
                select(Contact).where(
                    Contact.business_id == business_id,
                    Contact.phone == caller_phone,
                )
            )
            contact = existing.scalar_one_or_none()

            if not contact:
                # Create new contact
                contact = Contact(
                    business_id=business_id,
                    full_name=meta.get("ivr_caller_name"),
                    phone=caller_phone,
                    status="prospect",
                    source_channel="call",
                    acquisition_campaign=meta.get("campaign_name"),
                    acquisition_channel="call",
                    customer_type="new",
                    first_contact_date=interaction.created_at,
                    touchpoint_count=1,
                )
                db.add(contact)
                await db.flush()

            contact_id = contact.id
            interaction.contact_id = contact_id

        # Promote contact to prospect (lead) — skip if already a customer
        if contact_id:
            c_result = await db.execute(
                select(Contact).where(Contact.id == contact_id)
            )
            contact = c_result.scalar_one_or_none()
            if contact and contact.status not in ("active_customer",):
                contact.status = "prospect"  # "new" → "prospect" = qualified as lead

        interaction.metadata_ = meta
        await db.flush()

        return QualifyResponse(
            status="qualified",
            decision="lead",
            contact_id=contact_id,
        )

    elif payload.decision == "no_lead":
        meta["disposition"] = "other"
        if payload.reason:
            meta["no_lead_reason"] = payload.reason
        interaction.metadata_ = meta

        # Update contact status so they don't appear in Leads column
        if interaction.contact_id:
            c_result = await db.execute(
                select(Contact).where(Contact.id == interaction.contact_id)
            )
            contact = c_result.scalar_one_or_none()
            if contact and contact.status in ("prospect", "new"):
                contact.status = "other"

        await db.flush()

        return QualifyResponse(
            status="qualified",
            decision="no_lead",
            contact_id=interaction.contact_id,
        )

    else:
        raise HTTPException(status_code=400, detail="decision must be 'lead' or 'no_lead'")


@router.post("/leads/{contact_id}/convert", response_model=ConvertToJobResponse)
async def convert_to_job(
    contact_id: UUID,
    payload: ConvertToJobRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Convert a qualified lead to a Job in Operations.

    AI pre-generates title + description from call context.
    User reviews/edits, then confirms.
    """
    # Verify contact
    c_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.business_id == business_id,
        )
    )
    contact = c_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Detect returning customer — check if another active_customer shares phone or email
    is_returning = False
    match_filters = []
    if contact.phone:
        match_filters.append(Contact.phone == contact.phone)
    if contact.email:
        match_filters.append(Contact.email == contact.email)

    if match_filters:
        existing_customer = await db.execute(
            select(Contact.id).where(
                Contact.business_id == business_id,
                Contact.status == "active_customer",
                Contact.id != contact_id,
                or_(*match_filters),
            ).limit(1)
        )
        if existing_customer.scalar_one_or_none():
            is_returning = True

    customer_type = "returning" if is_returning else "new"

    # Fetch latest Sales call interaction for this contact to carry context forward
    call_context: dict = {}
    latest_call = await db.execute(
        select(Interaction)
        .where(
            Interaction.contact_id == contact_id,
            Interaction.business_id == business_id,
            Interaction.type == "call",
        )
        .order_by(Interaction.created_at.desc())
        .limit(1)
    )
    call_interaction = latest_call.scalar_one_or_none()
    if call_interaction:
        imeta = dict(call_interaction.metadata_ or {})
        call_context = {
            "call_summary": imeta.get("summary"),
            "call_category": imeta.get("call_category"),
            "suggested_action": imeta.get("suggested_action"),
            "lead_notes": contact.notes,
        }

    # Create job in Operations
    job = Job(
        business_id=business_id,
        contact_id=contact_id,
        title=payload.title,
        description=payload.description,
        status="new",
        amount_quoted=payload.estimate,
        metadata_={
            "source": "sales_pipeline",
            "converted_by": str(current_user_id),
            **{k: v for k, v in call_context.items() if v},
        },
        created_by=current_user_id,
    )
    db.add(job)

    # Update contact lifecycle
    contact.status = "active_customer"
    contact.customer_type = customer_type

    # Mark all Sales lead interactions for this contact as converted
    lead_interactions = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.contact_id == contact_id,
            Interaction.type == "call",
            Interaction.metadata_["disposition"].astext == "lead",
        )
    )
    for li in lead_interactions.scalars():
        meta = dict(li.metadata_ or {})
        meta["disposition"] = "converted"
        meta["converted_job_id"] = str(job.id)
        meta["customer_type"] = customer_type
        li.metadata_ = meta

    await db.flush()
    await db.refresh(job)

    return ConvertToJobResponse(
        status="converted",
        job_id=job.id,
        contact_id=contact_id,
    )


@router.patch("/leads/{contact_id}/close", response_model=CloseLeadResponse)
async def close_lead(
    contact_id: UUID,
    payload: CloseLeadRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Close a lead as no-conversion — they were qualified but didn't convert."""
    # Verify contact
    c_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.business_id == business_id,
        )
    )
    contact = c_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Update contact status
    contact.status = "no_conversion"

    # Mark all lead interactions for this contact as no_conversion
    lead_interactions = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.contact_id == contact_id,
            Interaction.type == "call",
            Interaction.metadata_["disposition"].astext == "lead",
        )
    )
    for li in lead_interactions.scalars():
        meta = dict(li.metadata_ or {})
        meta["disposition"] = "no_conversion"
        if payload.reason:
            meta["no_conversion_reason"] = payload.reason
        li.metadata_ = meta

    await db.flush()

    return CloseLeadResponse(
        status="closed",
        contact_id=contact_id,
    )


@router.get("/pipeline-summary", response_model=PipelineSummary)
async def pipeline_summary(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """KPI summary for the Sales pipeline header."""

    # New: unreviewed Sales calls
    new_count = (await db.execute(
        select(func.count()).select_from(
            select(Interaction.id).where(
                Interaction.business_id == business_id,
                Interaction.type == "call",
                or_(
                    Interaction.metadata_["department_context"].astext == "Sales",
                    Interaction.metadata_["routed_to_department"].astext == "Sales",
                ),
                or_(
                    Interaction.metadata_["disposition"].astext == "unreviewed",
                    Interaction.metadata_["disposition"].astext == "",
                    ~Interaction.metadata_.has_key("disposition"),
                ),
            ).subquery()
        )
    )).scalar() or 0

    # Leads: Sales calls marked as "lead" (contacts with status=prospect from Sales)
    lead_count = (await db.execute(
        select(func.count()).select_from(
            select(Interaction.id).where(
                Interaction.business_id == business_id,
                Interaction.type == "call",
                or_(
                    Interaction.metadata_["department_context"].astext == "Sales",
                    Interaction.metadata_["routed_to_department"].astext == "Sales",
                ),
                Interaction.metadata_["disposition"].astext == "lead",
            ).subquery()
        )
    )).scalar() or 0

    # Converted: Sales calls that became jobs
    converted_count = (await db.execute(
        select(func.count()).select_from(
            select(Interaction.id).where(
                Interaction.business_id == business_id,
                Interaction.type == "call",
                or_(
                    Interaction.metadata_["department_context"].astext == "Sales",
                    Interaction.metadata_["routed_to_department"].astext == "Sales",
                ),
                Interaction.metadata_["disposition"].astext == "converted",
            ).subquery()
        )
    )).scalar() or 0

    # No-lead count for conversion rate calculation
    no_lead_count = (await db.execute(
        select(func.count()).select_from(
            select(Interaction.id).where(
                Interaction.business_id == business_id,
                Interaction.type == "call",
                or_(
                    Interaction.metadata_["department_context"].astext == "Sales",
                    Interaction.metadata_["routed_to_department"].astext == "Sales",
                ),
                Interaction.metadata_["disposition"].astext == "other",
            ).subquery()
        )
    )).scalar() or 0

    # Conversion rates
    total_reviewed = lead_count + no_lead_count + converted_count
    prospect_to_lead_pct = (
        round((lead_count + converted_count) / total_reviewed * 100, 1)
        if total_reviewed > 0
        else 0
    )
    total_leads_ever = lead_count + converted_count
    lead_to_job_pct = (
        round(converted_count / total_leads_ever * 100, 1)
        if total_leads_ever > 0
        else 0
    )

    return PipelineSummary(
        new_count=new_count,
        lead_count=lead_count,
        converted_count=converted_count,
        prospect_to_lead_pct=prospect_to_lead_pct,
        lead_to_job_pct=lead_to_job_pct,
    )


# ── Review: Historical decisions ──


@router.get("/review", response_model=ReviewResponse)
async def list_reviewed(
    business_id: UUID = Query(...),
    disposition: str | None = Query(None),  # "lead" | "converted" | "other" | "no_conversion" | None (all)
    limit: int = Query(5, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List reviewed Sales interactions with two-column outcome tracking.

    Call Outcome: Lead or No Lead (from initial qualification)
    Lead Outcome: Converted, No Conversion, or Pending (post-qualification)
    """
    base = (
        select(Interaction)
        .where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
            or_(
                Interaction.metadata_["department_context"].astext == "Sales",
                Interaction.metadata_["routed_to_department"].astext == "Sales",
            ),
            # Only reviewed items — exclude unreviewed
            Interaction.metadata_["disposition"].astext.in_(
                ["lead", "converted", "other", "no_conversion"]
            ),
        )
    )

    if disposition:
        base = base.where(Interaction.metadata_["disposition"].astext == disposition)

    # Count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch
    rows = (
        await db.execute(
            base.order_by(Interaction.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    if not rows:
        return ReviewResponse(items=[], total=total)

    # Batch-load contacts
    contact_ids = {r.contact_id for r in rows if r.contact_id}
    contact_map: dict[UUID, Contact] = {}
    if contact_ids:
        c_result = await db.execute(
            select(Contact).where(Contact.id.in_(contact_ids))
        )
        for c in c_result.scalars():
            contact_map[c.id] = c

    items = []
    for i in rows:
        meta = i.metadata_ or {}
        contact = contact_map.get(i.contact_id) if i.contact_id else None
        disp = meta.get("disposition", "other")

        # Compute two-column outcomes
        # Call Outcome: was the initial call qualified as a lead?
        if disp in ("lead", "converted", "no_conversion"):
            call_outcome = "Lead"
        else:
            call_outcome = "No Lead"

        # Lead Outcome: what happened after qualification?
        if disp == "converted":
            lead_outcome = "Converted"
        elif disp == "no_conversion":
            lead_outcome = "No Conversion"
        elif disp == "lead":
            lead_outcome = "Pending"
        else:
            lead_outcome = None  # N/A for no-leads

        # Customer type: from interaction metadata (set at conversion) or from contact
        customer_type = meta.get("customer_type") or (contact.customer_type if contact else None)

        items.append(
            ReviewItem(
                interaction_id=i.id,
                contact_id=i.contact_id,
                caller_name=meta.get("ivr_caller_name") or (contact.full_name if contact else None),
                caller_phone=meta.get("from") or (contact.phone if contact else None),
                call_summary=meta.get("summary") or i.subject,
                lead_summary=meta.get("lead_summary"),
                no_lead_reason=meta.get("no_lead_reason"),
                no_conversion_reason=meta.get("no_conversion_reason"),
                disposition=disp,
                call_outcome=call_outcome,
                lead_outcome=lead_outcome,
                customer_type=customer_type,
                recording_url=meta.get("recording_url"),
                duration_s=meta.get("duration_s"),
                converted_job_id=meta.get("converted_job_id"),
                created_at=i.created_at,
            )
        )

    return ReviewResponse(items=items, total=total)


# ── Customers ──


@router.get("/customers", response_model=CustomerListResponse)
async def list_customers(
    business_id: UUID = Query(...),
    status: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List customers/prospects with job count and revenue totals."""
    base = select(Contact).where(Contact.business_id == business_id)

    if status:
        base = base.where(Contact.status == status)
    if search:
        search_filter = f"%{search}%"
        base = base.where(
            or_(
                Contact.full_name.ilike(search_filter),
                Contact.phone.ilike(search_filter),
                Contact.email.ilike(search_filter),
            )
        )

    # Count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch contacts
    rows = (
        await db.execute(
            base.order_by(Contact.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    if not rows:
        return CustomerListResponse(customers=[], total=total)

    # Batch-load job counts and revenue
    contact_ids = [c.id for c in rows]

    # Job counts
    job_counts: dict[UUID, int] = {}
    jc_result = await db.execute(
        select(Job.contact_id, func.count().label("cnt"))
        .where(Job.business_id == business_id, Job.contact_id.in_(contact_ids))
        .group_by(Job.contact_id)
    )
    for row in jc_result:
        job_counts[row.contact_id] = row.cnt

    # Revenue per contact
    rev_map: dict[UUID, float] = {}
    rev_result = await db.execute(
        select(
            Payment.contact_id,
            func.coalesce(func.sum(Payment.amount), 0).label("total_rev"),
        )
        .where(
            Payment.business_id == business_id,
            Payment.contact_id.in_(contact_ids),
            Payment.status == "completed",
        )
        .group_by(Payment.contact_id)
    )
    for row in rev_result:
        rev_map[row.contact_id] = float(row.total_rev)

    # Batch-load assigned user names
    assigned_user_ids = {c.assigned_to for c in rows if c.assigned_to}
    user_name_map: dict[UUID, str] = {}
    if assigned_user_ids:
        uname_result = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(assigned_user_ids))
        )
        for row in uname_result:
            user_name_map[row.id] = row.full_name or row.id.hex[:8]

    # Batch-load latest Sales call interaction per contact (for lead context)
    call_context_map: dict[UUID, dict] = {}
    if status == "prospect":
        # Only fetch call context for prospects (the leads column)
        call_result = await db.execute(
            select(Interaction)
            .where(
                Interaction.business_id == business_id,
                Interaction.contact_id.in_(contact_ids),
                Interaction.type == "call",
                or_(
                    Interaction.metadata_["department_context"].astext == "Sales",
                    Interaction.metadata_["routed_to_department"].astext == "Sales",
                ),
            )
            .order_by(Interaction.created_at.desc())
        )
        for ci in call_result.scalars():
            # Only keep the latest interaction per contact
            if ci.contact_id not in call_context_map:
                meta = ci.metadata_ or {}
                call_context_map[ci.contact_id] = {
                    "call_summary": meta.get("summary") or ci.subject,
                    "transcript": ci.body,
                    "call_category": meta.get("call_category"),
                    "suggested_action": meta.get("suggested_action"),
                    "score": meta.get("score"),
                    "duration_s": meta.get("duration_s"),
                    "campaign_name": meta.get("campaign_name"),
                }

    customers = []
    for c in rows:
        ctx = call_context_map.get(c.id, {})
        customers.append(
            CustomerItem(
                id=c.id,
                full_name=c.full_name,
                company_name=c.company_name,
                phone=c.phone,
                email=c.email,
                status=c.status,
                source_channel=c.source_channel,
                acquisition_campaign=c.acquisition_campaign,
                total_revenue=rev_map.get(c.id, 0),
                job_count=job_counts.get(c.id, 0),
                notes=c.notes,
                created_at=c.created_at,
                call_summary=ctx.get("call_summary"),
                transcript=ctx.get("transcript"),
                call_category=ctx.get("call_category"),
                suggested_action=ctx.get("suggested_action"),
                score=ctx.get("score"),
                duration_s=ctx.get("duration_s"),
                campaign_name=ctx.get("campaign_name"),
                assigned_to=c.assigned_to,
                assigned_user_name=user_name_map.get(c.assigned_to) if c.assigned_to else None,
            )
        )

    return CustomerListResponse(customers=customers, total=total)


@router.post("/customers", response_model=CustomerItem)
async def create_customer(
    payload: CreateCustomerRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Manually create a customer/prospect."""
    contact = Contact(
        business_id=business_id,
        full_name=payload.full_name,
        company_name=payload.company_name,
        phone=normalize_phone(payload.phone),
        email=payload.email.strip().lower() if payload.email else None,
        status=payload.status,
        source_channel=payload.source_channel or "manual",
        notes=payload.notes,
        first_contact_date=datetime.now(timezone.utc),
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)

    return CustomerItem(
        id=contact.id,
        full_name=contact.full_name,
        company_name=contact.company_name,
        phone=contact.phone,
        email=contact.email,
        status=contact.status,
        source_channel=contact.source_channel,
        acquisition_campaign=contact.acquisition_campaign,
        total_revenue=0,
        job_count=0,
        notes=contact.notes,
        created_at=contact.created_at,
    )


@router.patch("/customers/{customer_id}", response_model=CustomerItem)
async def update_customer(
    customer_id: UUID,
    payload: UpdateCustomerRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a customer's details or status."""
    result = await db.execute(
        select(Contact).where(
            Contact.id == customer_id,
            Contact.business_id == business_id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Customer not found")

    update_data = payload.model_dump(exclude_unset=True)
    # Normalize phone and email before saving
    if "phone" in update_data and update_data["phone"]:
        update_data["phone"] = normalize_phone(update_data["phone"])
    if "email" in update_data and update_data["email"]:
        update_data["email"] = update_data["email"].strip().lower()
    for field, value in update_data.items():
        setattr(contact, field, value)

    # If status changed to "customer", update lifecycle fields
    if "status" in update_data and update_data["status"] == "customer":
        if not contact.customer_type:
            contact.customer_type = "new"
        contact.status = "active_customer"

    await db.flush()
    await db.refresh(contact)

    # Get job count + revenue
    jc = (await db.execute(
        select(func.count()).where(Job.contact_id == customer_id, Job.business_id == business_id)
    )).scalar() or 0
    rev = (await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.contact_id == customer_id, Payment.business_id == business_id, Payment.status == "completed"
        )
    )).scalar() or 0

    # Resolve assigned user name if set
    assigned_user_name: str | None = None
    if contact.assigned_to:
        u_result = await db.execute(select(User.full_name).where(User.id == contact.assigned_to))
        u_name = u_result.scalar_one_or_none()
        assigned_user_name = u_name or None

    return CustomerItem(
        id=contact.id,
        full_name=contact.full_name,
        company_name=contact.company_name,
        phone=contact.phone,
        email=contact.email,
        status=contact.status,
        source_channel=contact.source_channel,
        acquisition_campaign=contact.acquisition_campaign,
        total_revenue=float(rev),
        job_count=jc,
        notes=contact.notes,
        created_at=contact.created_at,
        assigned_to=contact.assigned_to,
        assigned_user_name=assigned_user_name,
    )


# ── Jobs ──


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    business_id: UUID = Query(...),
    contact_id: UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List jobs, optionally filtered by customer or status."""
    base = select(Job).where(Job.business_id == business_id)

    if contact_id:
        base = base.where(Job.contact_id == contact_id)
    if status:
        base = base.where(Job.status == status)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    rows = (
        await db.execute(
            base.order_by(Job.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    # Batch-load contact names
    contact_ids = {j.contact_id for j in rows}
    contact_names: dict[UUID, str] = {}
    contact_phones: dict[UUID, str | None] = {}
    if contact_ids:
        c_result = await db.execute(
            select(Contact.id, Contact.full_name, Contact.phone).where(Contact.id.in_(contact_ids))
        )
        for row in c_result:
            contact_names[row.id] = row.full_name or "Unknown"
            contact_phones[row.id] = row.phone

    # Batch-load assigned staff info
    from app.operations.models import Staff
    staff_ids = {j.assigned_to for j in rows if j.assigned_to}
    staff_map: dict = {}
    if staff_ids:
        s_result = await db.execute(
            select(Staff.id, Staff.first_name, Staff.last_name, Staff.color).where(Staff.id.in_(staff_ids))
        )
        for row in s_result:
            name = f"{row.first_name} {row.last_name or ''}".strip()
            staff_map[row.id] = {"name": name, "color": row.color}

    jobs = []
    for j in rows:
        meta = dict(j.metadata_ or {})
        staff_info = staff_map.get(j.assigned_to, {}) if j.assigned_to else {}
        jobs.append(
            JobItem(
                id=j.id,
                contact_id=j.contact_id,
                contact_name=contact_names.get(j.contact_id),
                contact_phone=contact_phones.get(j.contact_id),
                source=meta.get("source"),
                title=j.title,
                description=j.description,
                status=j.status,
                notes=j.notes,
                amount_quoted=float(j.amount_quoted) if j.amount_quoted else None,
                amount_billed=float(j.amount_billed) if j.amount_billed else None,
                template_id=j.template_id,
                template_data=j.template_data,
                assigned_to=j.assigned_to,
                assigned_staff_name=staff_info.get("name"),
                assigned_staff_color=staff_info.get("color"),
                service_address=j.service_address,
                scheduled_at=j.scheduled_at,
                dispatched_at=j.dispatched_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
                created_at=j.created_at,
                call_summary=meta.get("call_summary"),
                call_category=meta.get("call_category"),
                suggested_action=meta.get("suggested_action"),
                lead_notes=meta.get("lead_notes"),
            )
        )

    return JobListResponse(jobs=jobs, total=total)


@router.post("/jobs", response_model=JobItem)
async def create_job(
    payload: CreateJobRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a job linked to a customer."""
    # Verify contact exists and belongs to this business
    c_result = await db.execute(
        select(Contact).where(
            Contact.id == payload.contact_id,
            Contact.business_id == business_id,
        )
    )
    contact = c_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Customer not found")

    job = Job(
        business_id=business_id,
        contact_id=payload.contact_id,
        title=payload.title,
        description=payload.description,
        notes=payload.notes,
        amount_quoted=payload.amount_quoted,
        template_id=payload.template_id,
        service_address=payload.service_address,
        created_by=current_user_id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    meta = dict(job.metadata_ or {})
    return JobItem(
        id=job.id,
        contact_id=job.contact_id,
        contact_name=contact.full_name,
        contact_phone=contact.phone,
        source=meta.get("source"),
        title=job.title,
        description=job.description,
        status=job.status,
        notes=job.notes,
        amount_quoted=float(job.amount_quoted) if job.amount_quoted else None,
        amount_billed=float(job.amount_billed) if job.amount_billed else None,
        template_id=job.template_id,
        service_address=job.service_address,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        call_summary=meta.get("call_summary"),
        call_category=meta.get("call_category"),
        suggested_action=meta.get("suggested_action"),
        lead_notes=meta.get("lead_notes"),
    )


@router.patch("/jobs/{job_id}", response_model=JobItem)
async def update_job(
    job_id: UUID,
    payload: UpdateJobRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a job's details or status. Fires dispatch SMS when assigned_to is set."""
    from app.operations.models import Staff, JobTemplate
    from app.marketing.models import PhoneLine
    from app.admin.services.acs_service import acs_service

    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = payload.model_dump(exclude_unset=True)
    prev_assigned_to = job.assigned_to

    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == "started" and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        elif new_status == "completed" and not job.completed_at:
            job.completed_at = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(job, field, value)

    # Auto-dispatch: if assigned_to was just set, mark dispatched
    new_assigned = update_data.get("assigned_to")
    if new_assigned and new_assigned != str(prev_assigned_to):
        job.dispatched_at = datetime.now(timezone.utc)
        if job.status == "new":
            job.status = "dispatched"

    await db.flush()
    await db.refresh(job)

    # Fire SMS if newly assigned + staff has a phone number
    if new_assigned and new_assigned != str(prev_assigned_to):
        staff_result = await db.execute(select(Staff).where(Staff.id == job.assigned_to))
        staff = staff_result.scalar_one_or_none()
        if staff and staff.phone:
            # Get mainline number to send from
            mainline_result = await db.execute(
                select(PhoneLine).where(
                    PhoneLine.business_id == business_id,
                    PhoneLine.line_type == "mainline",
                ).limit(1)
            )
            mainline = mainline_result.scalar_one_or_none()
            if mainline:
                scheduled_str = ""
                if job.scheduled_at:
                    scheduled_str = f" on {job.scheduled_at.strftime('%b %-d at %-I:%M %p')}"
                address_str = f" at {job.service_address}" if job.service_address else ""
                sms_body = (
                    f"Hi {staff.first_name}, you've been assigned to: {job.title}"
                    f"{address_str}{scheduled_str}. Reply START when on site."
                )
                import asyncio
                asyncio.create_task(
                    acs_service.send_sms(
                        to=staff.phone,
                        from_number=mainline.phone_number,
                        body=sms_body,
                    )
                )

    # Get contact name + phone
    c_result = await db.execute(select(Contact.full_name, Contact.phone).where(Contact.id == job.contact_id))
    c_row = c_result.one_or_none()

    # Get assigned staff info
    staff_name = None
    staff_color = None
    if job.assigned_to:
        s_result = await db.execute(
            select(Staff.first_name, Staff.last_name, Staff.color).where(Staff.id == job.assigned_to)
        )
        s_row = s_result.one_or_none()
        if s_row:
            staff_name = f"{s_row.first_name} {s_row.last_name or ''}".strip()
            staff_color = s_row.color

    meta = dict(job.metadata_ or {})
    return JobItem(
        id=job.id,
        contact_id=job.contact_id,
        contact_name=c_row.full_name if c_row else None,
        contact_phone=c_row.phone if c_row else None,
        source=meta.get("source"),
        title=job.title,
        description=job.description,
        status=job.status,
        notes=job.notes,
        amount_quoted=float(job.amount_quoted) if job.amount_quoted else None,
        amount_billed=float(job.amount_billed) if job.amount_billed else None,
        template_id=job.template_id,
        template_data=job.template_data,
        assigned_to=job.assigned_to,
        assigned_staff_name=staff_name,
        assigned_staff_color=staff_color,
        service_address=job.service_address,
        scheduled_at=job.scheduled_at,
        dispatched_at=job.dispatched_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        call_summary=meta.get("call_summary"),
        call_category=meta.get("call_category"),
        suggested_action=meta.get("suggested_action"),
        lead_notes=meta.get("lead_notes"),
    )


# ── Summary ──


@router.get("/summary", response_model=SalesSummary)
async def sales_summary(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """KPI summary for the Sales tab header."""
    # Contact counts by status
    prospect_count = (await db.execute(
        select(func.count()).where(
            Contact.business_id == business_id, Contact.status == "prospect"
        )
    )).scalar() or 0

    customer_count = (await db.execute(
        select(func.count()).where(
            Contact.business_id == business_id, Contact.status == "active_customer"
        )
    )).scalar() or 0

    no_conv_count = (await db.execute(
        select(func.count()).where(
            Contact.business_id == business_id, Contact.status == "no_conversion"
        )
    )).scalar() or 0

    # Job counts
    active_jobs = (await db.execute(
        select(func.count()).where(
            Job.business_id == business_id, Job.status.in_(["new", "in_progress"])
        )
    )).scalar() or 0

    completed_jobs = (await db.execute(
        select(func.count()).where(
            Job.business_id == business_id, Job.status.in_(["completed", "billed"])
        )
    )).scalar() or 0

    # Revenue
    total_revenue = (await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.business_id == business_id, Payment.status == "completed"
        )
    )).scalar() or 0

    # Total quoted
    total_quoted = (await db.execute(
        select(func.coalesce(func.sum(Job.amount_quoted), 0)).where(
            Job.business_id == business_id
        )
    )).scalar() or 0

    return SalesSummary(
        total_prospects=prospect_count,
        total_customers=customer_count,
        total_no_conversion=no_conv_count,
        active_jobs=active_jobs,
        completed_jobs=completed_jobs,
        total_revenue=float(total_revenue),
        total_quoted=float(total_quoted),
    )
