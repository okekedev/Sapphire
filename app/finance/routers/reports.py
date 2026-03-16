"""
Reports Router — Campaign ROI, customer lifecycle, department performance, pipeline funnel.

Combines data from:
  - Interactions (call history, campaign attribution)
  - Contacts (identity, stripe_customer_id)
  - Jobs (operations work)
  - Payments (local revenue records)
  - Stripe (invoice/subscription data, when connected)

Endpoints:
  GET  /reports/campaign-roi           — ROI per campaign (calls → revenue)
  GET  /reports/customer-lifecycle     — New vs. returning customer analysis
  GET  /reports/department-performance — Calls + revenue per department
  GET  /reports/pipeline-funnel        — Full pipeline attribution funnel
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.marketing.models import Interaction, Contact
from app.operations.models import Job
from app.finance.models import Payment
from app.core.services.auth_service import get_current_user_id
from app.finance.schemas.reports import (
    CampaignROIItem,
    CustomerLifecycleItem,
    DepartmentPerformanceItem,
    FunnelStage,
    CampaignAttribution,
    PipelineFunnelResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/campaign-roi", response_model=list[CampaignROIItem])
async def campaign_roi(
    business_id: UUID = Query(...),
    days: int = Query(30, ge=1, le=365),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Campaign ROI: for each campaign, how many calls, how many converted to
    paying customers, and how much revenue was generated.

    Links: campaign_name (from interaction metadata) → contact → payments.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Get all call interactions in date range
    result = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
            Interaction.created_at >= since,
        )
    )
    calls = result.scalars().all()

    # Group by campaign, collect contact_ids per campaign
    campaign_contacts: dict[str, set[UUID]] = defaultdict(set)
    campaign_calls: dict[str, int] = defaultdict(int)

    for call in calls:
        meta = call.metadata_ or {}
        campaign = meta.get("campaign_name") or "Direct / Unknown"
        campaign_calls[campaign] += 1
        if call.contact_id:
            campaign_contacts[campaign].add(call.contact_id)

    # Get revenue per contact from local Payment records
    all_contact_ids = set()
    for ids in campaign_contacts.values():
        all_contact_ids.update(ids)

    contact_revenue: dict[UUID, float] = defaultdict(float)
    contact_is_customer: dict[UUID, bool] = {}

    if all_contact_ids:
        # Payments linked to these contacts
        pay_result = await db.execute(
            select(Payment).where(
                Payment.business_id == business_id,
                Payment.contact_id.in_(all_contact_ids),
                Payment.status == "completed",
            )
        )
        for p in pay_result.scalars():
            if p.contact_id:
                contact_revenue[p.contact_id] += float(p.amount or 0)
                contact_is_customer[p.contact_id] = True

        # Also check contact status
        c_result = await db.execute(
            select(Contact).where(Contact.id.in_(all_contact_ids))
        )
        for c in c_result.scalars():
            if c.status == "active_customer":
                contact_is_customer[c.id] = True

    # Build ROI items
    items = []
    for campaign in sorted(campaign_calls, key=lambda c: -campaign_calls[c]):
        contact_ids = campaign_contacts[campaign]
        total_calls = campaign_calls[campaign]
        converted = sum(1 for cid in contact_ids if contact_is_customer.get(cid))
        revenue = sum(contact_revenue.get(cid, 0) for cid in contact_ids)
        conv_rate = (converted / total_calls * 100) if total_calls else 0
        avg_deal = (revenue / converted) if converted else 0

        items.append(
            CampaignROIItem(
                campaign_name=campaign,
                calls_generated=total_calls,
                contacts_created=len(contact_ids),
                customers_converted=converted,
                revenue_attributed=round(revenue, 2),
                conversion_rate=round(conv_rate, 1),
                avg_deal_size=round(avg_deal, 2),
            )
        )

    return items


@router.get("/customer-lifecycle", response_model=list[CustomerLifecycleItem])
async def customer_lifecycle(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    For each contact with billing data: compare first call date vs. first invoice.
    If invoice >= first call → new customer acquired via campaigns.
    If invoice < first call → existing/returning customer.
    """
    # Get all contacts for this business
    c_result = await db.execute(
        select(Contact).where(Contact.business_id == business_id)
    )
    contacts = c_result.scalars().all()
    if not contacts:
        return []

    contact_ids = [c.id for c in contacts]

    # Get earliest call interaction per contact
    first_calls: dict[UUID, datetime] = {}
    i_result = await db.execute(
        select(
            Interaction.contact_id,
            func.min(Interaction.created_at).label("first_call"),
        )
        .where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
            Interaction.contact_id.in_(contact_ids),
        )
        .group_by(Interaction.contact_id)
    )
    for row in i_result:
        first_calls[row.contact_id] = row.first_call

    # Get total revenue per contact from local Payments
    pay_result = await db.execute(
        select(
            Payment.contact_id,
            func.coalesce(func.sum(Payment.amount), 0).label("total_rev"),
            func.min(Payment.created_at).label("first_pay"),
        )
        .where(
            Payment.business_id == business_id,
            Payment.contact_id.in_(contact_ids),
            Payment.status == "completed",
        )
        .group_by(Payment.contact_id)
    )
    contact_rev: dict[UUID, float] = {}
    first_invoice: dict[UUID, datetime] = {}
    for row in pay_result:
        contact_rev[row.contact_id] = float(row.total_rev)
        first_invoice[row.contact_id] = row.first_pay

    items = []
    for c in contacts:
        fc = first_calls.get(c.id)
        fi = first_invoice.get(c.id)
        rev = contact_rev.get(c.id, 0)

        # Determine new vs. returning
        is_new = True
        if fc and fi:
            is_new = fi >= fc  # invoice came after (or same day as) first call → new
        elif fi and not fc:
            is_new = False  # has invoices but never called → pre-existing customer

        items.append(
            CustomerLifecycleItem(
                contact_id=c.id,
                contact_name=c.full_name,
                contact_phone=c.phone,
                contact_email=c.email,
                first_call_date=fc,
                first_invoice_date=fi,
                is_new_customer=is_new,
                lifetime_revenue=round(rev, 2),
                status=c.status,
            )
        )

    # Sort: customers with revenue first, then by revenue descending
    items.sort(key=lambda x: (-x.lifetime_revenue, x.contact_name or ""))
    return items


@router.get("/department-performance", response_model=list[DepartmentPerformanceItem])
async def department_performance(
    business_id: UUID = Query(...),
    days: int = Query(30, ge=1, le=365),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Calls handled + revenue attributed per department."""
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
            Interaction.created_at >= since,
        )
    )
    calls = result.scalars().all()

    # Group by department
    dept_data: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "contact_ids": set(), "durations": []}
    )
    for call in calls:
        meta = call.metadata_ or {}
        dept = meta.get("routed_to_department") or "Unrouted"
        d = dept_data[dept]
        d["calls"] += 1
        if call.contact_id:
            d["contact_ids"].add(call.contact_id)
        dur = meta.get("duration_s")
        if dur:
            d["durations"].append(int(dur))

    # Get revenue per contact
    all_contact_ids = set()
    for d in dept_data.values():
        all_contact_ids.update(d["contact_ids"])

    contact_revenue: dict[UUID, float] = defaultdict(float)
    if all_contact_ids:
        pay_result = await db.execute(
            select(Payment).where(
                Payment.business_id == business_id,
                Payment.contact_id.in_(all_contact_ids),
                Payment.status == "completed",
            )
        )
        for p in pay_result.scalars():
            if p.contact_id:
                contact_revenue[p.contact_id] += float(p.amount or 0)

    items = []
    for dept, d in sorted(dept_data.items(), key=lambda x: -x[1]["calls"]):
        durations = d["durations"]
        avg_dur = sum(durations) / len(durations) if durations else 0
        revenue = sum(contact_revenue.get(cid, 0) for cid in d["contact_ids"])
        items.append(
            DepartmentPerformanceItem(
                department=dept,
                calls_handled=d["calls"],
                contacts_generated=len(d["contact_ids"]),
                revenue_attributed=round(revenue, 2),
                avg_duration_s=round(avg_dur, 1),
            )
        )

    return items


@router.get("/pipeline-funnel", response_model=PipelineFunnelResponse)
async def pipeline_funnel(
    business_id: UUID = Query(...),
    days: int = Query(30, ge=1, le=365),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Full pipeline funnel: inbound calls → qualified leads → jobs → completed → revenue.

    At each stage, splits by new vs returning customer and tracked (campaign) vs manual source.
    Also returns per-campaign attribution breakdown.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # ── 1. Get all call interactions in date range ──
    call_result = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
            Interaction.created_at >= since,
        )
    )
    calls = call_result.scalars().all()

    # Collect unique contact_ids and campaign info per call
    all_contact_ids: set[UUID] = set()
    call_contact_campaigns: dict[UUID, str] = {}  # contact_id → first campaign seen
    campaign_call_counts: dict[str, int] = defaultdict(int)
    campaign_contact_ids: dict[str, set[UUID]] = defaultdict(set)

    for call in calls:
        meta = call.metadata_ or {}
        campaign = meta.get("campaign_name") or ""
        campaign_key = campaign if campaign else "Direct / Manual"
        campaign_call_counts[campaign_key] += 1

        if call.contact_id:
            all_contact_ids.add(call.contact_id)
            campaign_contact_ids[campaign_key].add(call.contact_id)
            if call.contact_id not in call_contact_campaigns:
                call_contact_campaigns[call.contact_id] = campaign_key

    # ── 2. Get contact details (customer_type, status) ──
    contact_type: dict[UUID, str] = {}  # contact_id → "new" | "returning"
    contact_status: dict[UUID, str] = {}
    contact_has_campaign: dict[UUID, bool] = {}

    if all_contact_ids:
        c_result = await db.execute(
            select(Contact).where(Contact.id.in_(all_contact_ids))
        )
        for c in c_result.scalars():
            contact_type[c.id] = c.customer_type or "new"
            contact_status[c.id] = c.status or "prospect"
            camp = call_contact_campaigns.get(c.id, "Direct / Manual")
            contact_has_campaign[c.id] = camp != "Direct / Manual"

    # Contacts that became leads (disposition = "lead" or status != "other")
    lead_contact_ids: set[UUID] = set()
    for call in calls:
        meta = call.metadata_ or {}
        disp = meta.get("disposition", "")
        if disp == "lead" and call.contact_id:
            lead_contact_ids.add(call.contact_id)
    # Also count contacts with status=prospect or active_customer as leads
    for cid in all_contact_ids:
        st = contact_status.get(cid, "prospect")
        if st in ("prospect", "active_customer"):
            lead_contact_ids.add(cid)

    # ── 3. Get jobs for these contacts ──
    job_contact_ids: set[UUID] = set()
    completed_job_contact_ids: set[UUID] = set()

    if all_contact_ids:
        job_result = await db.execute(
            select(Job).where(
                Job.business_id == business_id,
                Job.contact_id.in_(all_contact_ids),
            )
        )
        for j in job_result.scalars():
            job_contact_ids.add(j.contact_id)
            if j.status in ("completed", "billed"):
                completed_job_contact_ids.add(j.contact_id)

    # ── 4. Get payments (completed) ──
    contact_revenue: dict[UUID, float] = defaultdict(float)
    revenue_contact_ids: set[UUID] = set()

    if all_contact_ids:
        pay_result = await db.execute(
            select(Payment).where(
                Payment.business_id == business_id,
                Payment.contact_id.in_(all_contact_ids),
                Payment.status == "completed",
            )
        )
        for p in pay_result.scalars():
            if p.contact_id:
                contact_revenue[p.contact_id] += float(p.amount or 0)
                revenue_contact_ids.add(p.contact_id)

    # ── 5. Build funnel stages ──
    def _split(ids: set[UUID]):
        """Split a set of contact IDs into new/returning and campaign/manual counts."""
        new_ct = sum(1 for cid in ids if contact_type.get(cid, "new") == "new")
        ret_ct = len(ids) - new_ct
        camp_ct = sum(1 for cid in ids if contact_has_campaign.get(cid, False))
        manual_ct = len(ids) - camp_ct
        rev = sum(contact_revenue.get(cid, 0) for cid in ids)
        return new_ct, ret_ct, camp_ct, manual_ct, round(rev, 2)

    total_calls = len(calls)
    # For calls: count by campaign presence, not contact type (many calls have no contact)
    calls_from_campaign = sum(1 for c in calls if (c.metadata_ or {}).get("campaign_name"))
    calls_manual = total_calls - calls_from_campaign

    stages = []

    # Stage 1: Inbound Calls
    stages.append(FunnelStage(
        stage="calls", label="Inbound Calls",
        total=total_calls,
        new_customers=0,  # can't determine at call level
        returning_customers=0,
        from_campaigns=calls_from_campaign,
        manual=calls_manual,
        revenue=0,
        conversion_pct=100.0,
    ))

    # Stage 2: Qualified Leads (contacts from calls)
    l_new, l_ret, l_camp, l_man, l_rev = _split(lead_contact_ids)
    stages.append(FunnelStage(
        stage="leads", label="Qualified Leads",
        total=len(lead_contact_ids),
        new_customers=l_new, returning_customers=l_ret,
        from_campaigns=l_camp, manual=l_man,
        revenue=l_rev,
        conversion_pct=round(len(lead_contact_ids) / total_calls * 100, 1) if total_calls else 0,
    ))

    # Stage 3: Jobs Created
    j_new, j_ret, j_camp, j_man, j_rev = _split(job_contact_ids)
    stages.append(FunnelStage(
        stage="jobs_created", label="Jobs Created",
        total=len(job_contact_ids),
        new_customers=j_new, returning_customers=j_ret,
        from_campaigns=j_camp, manual=j_man,
        revenue=j_rev,
        conversion_pct=round(len(job_contact_ids) / len(lead_contact_ids) * 100, 1) if lead_contact_ids else 0,
    ))

    # Stage 4: Jobs Completed
    jc_new, jc_ret, jc_camp, jc_man, jc_rev = _split(completed_job_contact_ids)
    stages.append(FunnelStage(
        stage="jobs_completed", label="Jobs Completed",
        total=len(completed_job_contact_ids),
        new_customers=jc_new, returning_customers=jc_ret,
        from_campaigns=jc_camp, manual=jc_man,
        revenue=jc_rev,
        conversion_pct=round(len(completed_job_contact_ids) / len(job_contact_ids) * 100, 1) if job_contact_ids else 0,
    ))

    # Stage 5: Revenue Collected
    r_new, r_ret, r_camp, r_man, r_rev = _split(revenue_contact_ids)
    stages.append(FunnelStage(
        stage="revenue", label="Revenue Collected",
        total=len(revenue_contact_ids),
        new_customers=r_new, returning_customers=r_ret,
        from_campaigns=r_camp, manual=r_man,
        revenue=r_rev,
        conversion_pct=round(len(revenue_contact_ids) / len(completed_job_contact_ids) * 100, 1) if completed_job_contact_ids else 0,
    ))

    # ── 6. Build per-campaign attribution ──
    campaigns = []
    for camp_name in sorted(campaign_call_counts, key=lambda c: -campaign_call_counts[c]):
        cids = campaign_contact_ids.get(camp_name, set())
        camp_leads = cids & lead_contact_ids
        camp_jobs = cids & job_contact_ids
        camp_rev = sum(contact_revenue.get(cid, 0) for cid in cids)
        camp_new = sum(1 for cid in cids if contact_type.get(cid, "new") == "new")
        camp_ret = len(cids) - camp_new

        # Try to get channel from any call's metadata
        channel = None
        for call in calls:
            meta = call.metadata_ or {}
            cn = meta.get("campaign_name") or ""
            actual_key = cn if cn else "Direct / Manual"
            if actual_key == camp_name and meta.get("channel"):
                channel = meta["channel"]
                break

        campaigns.append(CampaignAttribution(
            campaign_name=camp_name,
            channel=channel,
            calls=campaign_call_counts[camp_name],
            leads=len(camp_leads),
            jobs=len(camp_jobs),
            revenue=round(camp_rev, 2),
            new_customers=camp_new,
            returning_customers=camp_ret,
        ))

    # ── 7. Totals ──
    total_revenue = sum(contact_revenue.values())
    new_revenue = sum(contact_revenue.get(cid, 0) for cid in revenue_contact_ids if contact_type.get(cid, "new") == "new")
    ret_revenue = total_revenue - new_revenue

    return PipelineFunnelResponse(
        stages=stages,
        campaigns=campaigns,
        totals={
            "total_calls": total_calls,
            "total_leads": len(lead_contact_ids),
            "total_jobs": len(job_contact_ids),
            "total_revenue": round(total_revenue, 2),
            "new_revenue": round(new_revenue, 2),
            "returning_revenue": round(ret_revenue, 2),
        },
        period_days=days,
    )
