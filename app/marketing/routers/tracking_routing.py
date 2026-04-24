"""
Tracking & Routing Router — Call log, aggregation, phone settings, and department context endpoints.

Reads from the Interaction model (type='call') where all call data lives
in the metadata_ JSONB column (campaign_name, ivr_caller_name, summary,
recording_url, duration_s, routed_to_department, department_context, etc.).

Endpoints:
  GET   /tracking-routing/calls                     — Paginated call log
  GET   /tracking-routing/department-calls           — Calls filtered by department_context
  GET   /tracking-routing/department-summary         — Aggregated by department
  GET   /tracking-routing/campaign-summary           — Aggregated by campaign
  PATCH /tracking-routing/calls/{id}/disposition     — Set call disposition
  PATCH /tracking-routing/calls/{id}/reroute         — Re-assign call to different department
  POST  /tracking-routing/calls/{id}/process         — Invoke AI employee to process call
  GET   /tracking-routing/settings                   — Phone settings (greeting, routing, etc.)
  PUT   /tracking-routing/settings                   — Update phone settings
"""

import logging
import re
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.marketing.models import Interaction, Contact
from app.core.models.business import Business
from app.admin.models import PhoneSettings
from app.core.services.auth_service import get_current_user_id
from app.marketing.schemas.tracking_routing import (
    CallLogItem,
    CallLogResponse,
    DepartmentSummaryItem,
    CampaignSummaryItem,
    RerouteCallRequest,
    ProcessCallResponse,
)
from app.admin.schemas.phone_settings import PhoneSettingsRead, PhoneSettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tracking-routing", tags=["tracking-routing"])


def _extract_meta(meta: dict | None, key: str, default=None):
    """Safely extract a value from interaction metadata."""
    if not meta:
        return default
    return meta.get(key, default)


@router.get("/calls", response_model=CallLogResponse)
async def list_calls(
    business_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    campaign_name: str | None = Query(None),
    status: str | None = Query(None),
    hide_dispositioned: bool = Query(False),
    sort_by: str = Query("date"),
    sort_order: str = Query("desc"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Paginated call log. Returns call interactions with metadata flattened
    into CallLogItem fields for easy rendering.

    Supports sorting by date, caller, campaign, status, duration.
    Supports filtering out dispositioned calls via hide_dispositioned=true.
    """
    # Base query: all call interactions for this business
    base = select(Interaction).where(
        Interaction.business_id == business_id,
        Interaction.type == "call",
    )

    # Optional filters via JSONB
    if campaign_name:
        base = base.where(
            Interaction.metadata_["campaign_name"].astext == campaign_name
        )
    if status:
        base = base.where(
            Interaction.metadata_["pipeline_status"].astext == status
        )
    if hide_dispositioned:
        # Only show calls with disposition "unreviewed" or no disposition set
        from sqlalchemy import or_
        base = base.where(
            or_(
                Interaction.metadata_["disposition"].astext == "unreviewed",
                Interaction.metadata_["disposition"] == None,
            )
        )

    # Total count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sorting
    from sqlalchemy import asc as sa_asc
    order_dir = sa_asc if sort_order == "asc" else desc
    if sort_by == "duration":
        order_col = Interaction.metadata_["duration_s"]
    elif sort_by == "campaign":
        order_col = Interaction.metadata_["campaign_name"]
    elif sort_by == "status":
        order_col = Interaction.metadata_["pipeline_status"]
    else:
        order_col = Interaction.created_at

    # Fetch page
    rows_q = base.order_by(order_dir(order_col)).offset(offset).limit(limit)
    rows = (await db.execute(rows_q)).scalars().all()

    # Batch-load contacts for caller name
    contact_ids = {r.contact_id for r in rows if r.contact_id}
    contacts_map: dict[UUID, Contact] = {}
    if contact_ids:
        c_result = await db.execute(
            select(Contact).where(Contact.id.in_(contact_ids))
        )
        for c in c_result.scalars():
            contacts_map[c.id] = c

    calls = []
    for r in rows:
        meta = r.metadata_ or {}
        contact = contacts_map.get(r.contact_id) if r.contact_id else None

        # Derive caller name: IVR capture → contact name → phone
        caller_name = (
            meta.get("ivr_caller_name")
            or (contact.full_name if contact else None)
            or meta.get("from")
        )
        caller_phone = meta.get("from") or (contact.phone if contact else None)

        # Derive status: pipeline_status → call status → infer from duration
        call_status = meta.get("pipeline_status")
        if not call_status:
            twilio_status = meta.get("status", "")
            duration = meta.get("duration_s", 0) or 0
            if twilio_status in ("completed",) and duration > 10:
                call_status = "completed"
            elif twilio_status in ("no-answer", "busy", "failed") or duration < 5:
                call_status = "dropped"
            else:
                call_status = "followup"

        calls.append(
            CallLogItem(
                id=r.id,
                contact_id=r.contact_id,
                caller_name=caller_name,
                caller_phone=caller_phone,
                campaign_name=meta.get("campaign_name"),
                channel=meta.get("channel"),
                summary=meta.get("summary") or r.subject,
                routed_to=meta.get("routed_to_department"),
                status=call_status,
                score=meta.get("score"),
                next_step=meta.get("next_step"),
                duration_s=meta.get("duration_s"),
                recording_url=meta.get("recording_url"),
                disposition=meta.get("disposition", "unreviewed"),
                department_context=meta.get("department_context"),
                call_category=meta.get("call_category"),
                suggested_action=meta.get("suggested_action"),
                ai_processed=bool(meta.get("ai_processed")),
                ai_process_output=meta.get("ai_process_output"),
                created_at=r.created_at,
            )
        )

    return CallLogResponse(calls=calls, total=total)


class DispositionCallRequest(BaseModel):
    disposition: str = "other"  # lead | spam | other | unreviewed


@router.patch("/calls/{call_id}/disposition")
async def disposition_call(
    call_id: UUID,
    payload: DispositionCallRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Set the disposition of a call (lead/spam/other/unreviewed).

    When disposition is 'lead', auto-creates or links a Contact record
    and sets the contact status to 'prospect'.
    """
    valid_dispositions = {"unreviewed", "lead", "spam", "other"}
    if payload.disposition not in valid_dispositions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid disposition. Must be one of: {', '.join(valid_dispositions)}",
        )

    result = await db.execute(
        select(Interaction).where(
            Interaction.id == call_id,
            Interaction.business_id == business_id,
            Interaction.type == "call",
        )
    )
    interaction = result.scalar_one_or_none()
    if not interaction:
        raise HTTPException(status_code=404, detail="Call not found")

    meta = dict(interaction.metadata_ or {})
    old_disposition = meta.get("disposition", "unreviewed")
    meta["disposition"] = payload.disposition
    meta["disposition_by"] = str(current_user_id)
    interaction.metadata_ = meta

    contact_id = interaction.contact_id

    # If marking as lead, ensure a Contact record exists
    if payload.disposition == "lead":
        caller_phone = meta.get("from")
        caller_name = meta.get("ivr_caller_name")

        if not contact_id and caller_phone:
            # Try to find existing contact by phone
            existing = await db.execute(
                select(Contact).where(
                    Contact.business_id == business_id,
                    Contact.phone == caller_phone,
                )
            )
            contact = existing.scalar_one_or_none()

            if not contact:
                # Create new contact — starts as "new", promoted to "prospect" on lead qualification
                contact = Contact(
                    business_id=business_id,
                    full_name=caller_name,
                    phone=caller_phone,
                    status="new",
                    source_channel="call",
                    acquisition_campaign=meta.get("campaign_name"),
                    acquisition_channel="call",
                    first_contact_date=interaction.created_at,
                )
                db.add(contact)
                await db.flush()

            # Link interaction to contact
            interaction.contact_id = contact.id
            contact_id = contact.id

        elif contact_id:
            # Contact already linked — leave status as-is (qualify endpoint handles promotion)
            pass

    await db.flush()

    return {
        "status": "ok",
        "disposition": payload.disposition,
        "contact_id": str(contact_id) if contact_id else None,
    }


# ── Department Context Calling ──


@router.get("/department-calls", response_model=CallLogResponse)
async def list_department_calls(
    business_id: UUID = Query(...),
    department: str = Query(..., description="Department name: Sales, Operations, Finance, Marketing, Admin"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_unrouted: bool = Query(False, description="Include calls with no department_context"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Calls filtered by department_context. Used by Sales, Operations, Finance tabs
    to show only the calls relevant to that department.

    Also includes calls where routed_to_department matches but department_context
    hasn't been set yet (backward compatibility with existing calls).
    """
    from sqlalchemy import or_

    base = select(Interaction).where(
        Interaction.business_id == business_id,
        Interaction.type == "call",
    )

    # Filter by department_context OR legacy routed_to_department
    dept_filter = or_(
        Interaction.metadata_["department_context"].astext == department,
        Interaction.metadata_["routed_to_department"].astext == department,
    )
    if include_unrouted:
        dept_filter = or_(
            dept_filter,
            Interaction.metadata_["department_context"] == None,
        )
    base = base.where(dept_filter)

    # Count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch
    rows_q = base.order_by(desc(Interaction.created_at)).offset(offset).limit(limit)
    rows = (await db.execute(rows_q)).scalars().all()

    # Load contacts
    contact_ids = {r.contact_id for r in rows if r.contact_id}
    contacts_map: dict[UUID, Contact] = {}
    if contact_ids:
        c_result = await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
        for c in c_result.scalars():
            contacts_map[c.id] = c

    calls = []
    for r in rows:
        meta = r.metadata_ or {}
        contact = contacts_map.get(r.contact_id) if r.contact_id else None
        caller_name = (
            meta.get("ivr_caller_name")
            or (contact.full_name if contact else None)
            or meta.get("from")
        )
        caller_phone = meta.get("from") or (contact.phone if contact else None)

        call_status = meta.get("pipeline_status")
        if not call_status:
            twilio_status = meta.get("status", "")
            duration = meta.get("duration_s", 0) or 0
            if twilio_status in ("completed",) and duration > 10:
                call_status = "completed"
            elif twilio_status in ("no-answer", "busy", "failed") or duration < 5:
                call_status = "dropped"
            else:
                call_status = "followup"

        calls.append(
            CallLogItem(
                id=r.id,
                contact_id=r.contact_id,
                caller_name=caller_name,
                caller_phone=caller_phone,
                campaign_name=meta.get("campaign_name"),
                channel=meta.get("channel"),
                summary=meta.get("summary") or r.subject,
                routed_to=meta.get("routed_to_department"),
                status=call_status,
                score=meta.get("score"),
                next_step=meta.get("next_step"),
                duration_s=meta.get("duration_s"),
                recording_url=meta.get("recording_url"),
                disposition=meta.get("disposition", "unreviewed"),
                department_context=meta.get("department_context"),
                call_category=meta.get("call_category"),
                suggested_action=meta.get("suggested_action"),
                ai_processed=bool(meta.get("ai_processed")),
                ai_process_output=meta.get("ai_process_output"),
                created_at=r.created_at,
            )
        )

    return CallLogResponse(calls=calls, total=total)


@router.patch("/calls/{call_id}/reroute")
async def reroute_call(
    call_id: UUID,
    payload: RerouteCallRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-assign a call to a different department (human review step).
    Updates both department_context and routed_to_department.
    """
    from app.core.services.org_graph import org_graph
    await org_graph.load(db)

    if payload.department not in org_graph.valid_departments:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid department. Must be one of: {', '.join(sorted(org_graph.valid_departments))}",
        )

    result = await db.execute(
        select(Interaction).where(
            Interaction.id == call_id,
            Interaction.business_id == business_id,
            Interaction.type == "call",
        )
    )
    interaction = result.scalar_one_or_none()
    if not interaction:
        raise HTTPException(status_code=404, detail="Call not found")

    meta = dict(interaction.metadata_ or {})
    old_dept = meta.get("department_context")
    meta["department_context"] = payload.department
    meta["routed_to_department"] = payload.department
    meta["rerouted_by"] = str(current_user_id)
    meta["rerouted_from"] = old_dept
    # Reset AI processing since department changed
    meta["ai_processed"] = False
    meta["ai_process_output"] = None
    interaction.metadata_ = meta

    await db.flush()

    return {
        "status": "ok",
        "department_context": payload.department,
        "previous_department": old_dept,
    }


@router.post("/calls/{call_id}/process", response_model=ProcessCallResponse)
async def process_call_with_ai(
    call_id: UUID,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Invoke the department's AI employee to process a reviewed call.

    Requires that department_context is set (either by AI analysis or human reroute).
    This is the "Process with AI" button action.
    """
    from app.marketing.services.call_analysis_service import call_analysis

    result = await db.execute(
        select(Interaction).where(
            Interaction.id == call_id,
            Interaction.business_id == business_id,
            Interaction.type == "call",
        )
    )
    interaction = result.scalar_one_or_none()
    if not interaction:
        raise HTTPException(status_code=404, detail="Call not found")

    meta = interaction.metadata_ or {}
    department = meta.get("department_context") or meta.get("routed_to_department")
    if not department:
        raise HTTPException(
            status_code=400,
            detail="Call has no department_context. Route to a department first.",
        )

    # Process with the department's AI employee
    output = await call_analysis.process_with_employee(
        business_id=business_id,
        department=department,
        caller_name=meta.get("ivr_caller_name"),
        reason=meta.get("ivr_reason"),
        summary=meta.get("summary"),
        category=meta.get("call_category", "general_inquiry"),
        contact_id=interaction.contact_id,
        interaction_id=interaction.id,
        db=db,
    )

    # Update interaction metadata with AI processing result
    updated_meta = dict(meta)
    updated_meta["ai_processed"] = True
    updated_meta["ai_process_output"] = output.get("output")
    updated_meta["ai_processed_by"] = output.get("employee")
    interaction.metadata_ = updated_meta
    await db.flush()

    return ProcessCallResponse(**output)


@router.get("/department-summary", response_model=list[DepartmentSummaryItem])
async def department_summary(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate call data by routed-to department."""
    result = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
        )
    )
    rows = result.scalars().all()

    # Aggregate in Python (JSONB grouping is complex in SQL)
    dept_data: dict[str, dict] = defaultdict(
        lambda: {
            "total": 0,
            "durations": [],
            "completed": 0,
            "followup": 0,
            "campaigns": defaultdict(int),
        }
    )

    for r in rows:
        meta = r.metadata_ or {}
        dept = meta.get("routed_to_department") or "Unrouted"
        d = dept_data[dept]
        d["total"] += 1

        dur = meta.get("duration_s")
        if dur:
            d["durations"].append(int(dur))

        status = meta.get("pipeline_status", "")
        if status == "completed":
            d["completed"] += 1
        elif status in ("followup", ""):
            d["followup"] += 1

        campaign = meta.get("campaign_name")
        if campaign:
            d["campaigns"][campaign] += 1

    items = []
    for dept, d in sorted(dept_data.items(), key=lambda x: -x[1]["total"]):
        durations = d["durations"]
        avg_dur = sum(durations) / len(durations) if durations else 0
        total = d["total"]
        completed = d["completed"]
        pct = (completed / total * 100) if total else 0

        # Top campaign
        top_campaign = None
        top_count = 0
        for cname, cnt in d["campaigns"].items():
            if cnt > top_count:
                top_campaign = cname
                top_count = cnt

        items.append(
            DepartmentSummaryItem(
                department=dept,
                total_calls=total,
                avg_duration_s=round(avg_dur, 1),
                completed_count=completed,
                completed_pct=round(pct, 1),
                followup_count=d["followup"],
                top_campaign=top_campaign,
                top_campaign_count=top_count,
            )
        )

    return items


@router.get("/campaign-summary", response_model=list[CampaignSummaryItem])
async def campaign_summary(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate call data by campaign/tracking source."""
    result = await db.execute(
        select(Interaction).where(
            Interaction.business_id == business_id,
            Interaction.type == "call",
        )
    )
    rows = result.scalars().all()

    camp_data: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "completed": 0, "followup": 0, "dropped": 0, "durations": []}
    )

    for r in rows:
        meta = r.metadata_ or {}
        campaign = meta.get("campaign_name") or "Direct / Unknown"
        c = camp_data[campaign]
        c["total"] += 1

        dur = meta.get("duration_s")
        if dur:
            c["durations"].append(int(dur))

        status = meta.get("pipeline_status", "")
        if status == "completed":
            c["completed"] += 1
        elif status == "dropped":
            c["dropped"] += 1
        else:
            c["followup"] += 1

    items = []
    for camp, c in sorted(camp_data.items(), key=lambda x: -x[1]["total"]):
        durations = c["durations"]
        avg_dur = sum(durations) / len(durations) if durations else 0
        items.append(
            CampaignSummaryItem(
                campaign_name=camp,
                total_calls=c["total"],
                completed_count=c["completed"],
                followup_count=c["followup"],
                dropped_count=c["dropped"],
                avg_duration_s=round(avg_dur, 1),
            )
        )

    return items


# ── Phone Settings ──


DEFAULT_GREETING = (
    "Thank you for calling {company_name}. "
    "May I get your name and reason for calling so I can best route your call?"
)

DEFAULT_HOLD_MESSAGE = (
    "Thank you, please hold while I connect your call. "
    "This call may be recorded for quality purposes."
)


async def _build_departments_config(db: AsyncSession, business_id: UUID):
    """Build departments_config list from the departments table."""
    from app.core.models.organization import Department as DeptModel
    from app.admin.schemas.phone_settings import DepartmentRoutingRule

    dept_result = await db.execute(
        select(DeptModel)
        .where(DeptModel.business_id.is_(None))
        .order_by(DeptModel.display_order, DeptModel.name)
    )
    departments = dept_result.scalars().all()
    return [
        DepartmentRoutingRule(
            name=d.name,
            department_id=d.id,
            forward_number=d.forward_number,
            enabled=d.enabled,
            sms_enabled=d.sms_enabled,
        )
        for d in departments
    ]


@router.get("/settings", response_model=PhoneSettingsRead)
async def get_phone_settings(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve phone settings for a business. Auto-creates defaults if none exist."""
    result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = PhoneSettings(
            business_id=business_id,
            greeting_text=DEFAULT_GREETING,
            hold_message=DEFAULT_HOLD_MESSAGE,
            voice_name="Google.en-US-Chirp3-HD-Aoede",
            recording_enabled=True,
            transcription_enabled=False,
            forward_all_calls=True,
            ring_timeout_s=30,
            after_hours_enabled=False,
        )
        db.add(settings)
        await db.flush()
        await db.refresh(settings)

    # Build departments_config from departments table
    dept_config = await _build_departments_config(db, business_id)

    return PhoneSettingsRead(
        business_id=settings.business_id,
        greeting_text=settings.greeting_text,
        hold_message=settings.hold_message,
        voice_name=settings.voice_name,
        recording_enabled=settings.recording_enabled,
        transcription_enabled=settings.transcription_enabled,
        forward_all_calls=settings.forward_all_calls,
        default_forward_number=settings.default_forward_number,
        ring_timeout_s=settings.ring_timeout_s,
        business_hours_start=settings.business_hours_start.strftime("%H:%M") if settings.business_hours_start else None,
        business_hours_end=settings.business_hours_end.strftime("%H:%M") if settings.business_hours_end else None,
        business_timezone=settings.business_timezone,
        after_hours_enabled=settings.after_hours_enabled,
        after_hours_action=settings.after_hours_action,
        after_hours_message=settings.after_hours_message,
        after_hours_forward_number=settings.after_hours_forward_number,
        departments_config=dept_config,
    )


@router.put("/settings", response_model=PhoneSettingsRead)
async def update_phone_settings(
    payload: PhoneSettingsUpdate,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update phone settings. Department routing updates are written to the departments table."""
    from app.core.models.organization import Department as DeptModel

    result = await db.execute(
        select(PhoneSettings).where(PhoneSettings.business_id == business_id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = PhoneSettings(business_id=business_id)
        db.add(settings)

    update_data = payload.model_dump(exclude_unset=True, mode="json")

    # Extract departments_config and write to departments table
    dept_updates = update_data.pop("departments_config", None)
    if dept_updates is not None:
        for rule in dept_updates:
            dept_id = rule.get("department_id")
            if not dept_id:
                continue
            dept = await db.get(DeptModel, dept_id)
            if dept:
                fwd = rule.get("forward_number")
                enabled = rule.get("enabled", True)
                # Can't enable a department without a forward number
                if enabled and not fwd:
                    enabled = False
                dept.forward_number = fwd
                dept.enabled = enabled
                if "sms_enabled" in rule:
                    dept.sms_enabled = rule["sms_enabled"]

    # Convert time strings ("HH:MM") to Python time objects before applying
    from datetime import time as dt_time
    for time_field in ("business_hours_start", "business_hours_end"):
        if time_field in update_data:
            val = update_data[time_field]
            if val and isinstance(val, str):
                try:
                    h, m = val.split(":")
                    update_data[time_field] = dt_time(int(h), int(m))
                except (ValueError, AttributeError):
                    update_data.pop(time_field)
            elif not val:
                update_data[time_field] = None

    # Apply remaining fields to phone_settings
    for field, value in update_data.items():
        setattr(settings, field, value)

    # ── Auto-correct: ensure routing config is coherent ──
    # If forward_all_calls is ON, transcription/recording don't matter — calls go
    # straight to default_forward_number.  If forward_all is OFF, IVR must work.
    if not settings.forward_all_calls:
        # IVR mode: transcription is required
        if not settings.transcription_enabled:
            settings.transcription_enabled = True
            settings.recording_enabled = True
    else:
        # Forward-all mode: if there's no default number, can't forward — force off
        if not settings.default_forward_number:
            settings.forward_all_calls = False
            # Fall back to IVR
            settings.transcription_enabled = True
            settings.recording_enabled = True

    # Can't enable after-hours without hours — force it back off
    if settings.after_hours_enabled:
        if not settings.business_hours_start or not settings.business_hours_end:
            settings.after_hours_enabled = False
        # "message" action requires a message; "forward" action requires a number
        elif settings.after_hours_action == "message" and not settings.after_hours_message:
            settings.after_hours_enabled = False
        elif settings.after_hours_action == "forward" and not settings.after_hours_forward_number:
            settings.after_hours_enabled = False

    await db.flush()
    await db.refresh(settings)

    # Build departments_config from departments table for the response
    dept_config = await _build_departments_config(db, business_id)

    return PhoneSettingsRead(
        business_id=settings.business_id,
        greeting_text=settings.greeting_text,
        hold_message=settings.hold_message,
        voice_name=settings.voice_name,
        recording_enabled=settings.recording_enabled,
        transcription_enabled=settings.transcription_enabled,
        forward_all_calls=settings.forward_all_calls,
        default_forward_number=settings.default_forward_number,
        ring_timeout_s=settings.ring_timeout_s,
        business_hours_start=settings.business_hours_start.strftime("%H:%M") if settings.business_hours_start else None,
        business_hours_end=settings.business_hours_end.strftime("%H:%M") if settings.business_hours_end else None,
        business_timezone=settings.business_timezone,
        after_hours_enabled=settings.after_hours_enabled,
        after_hours_action=settings.after_hours_action,
        after_hours_message=settings.after_hours_message,
        after_hours_forward_number=settings.after_hours_forward_number,
        departments_config=dept_config,
    )
