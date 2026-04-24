"""
Dashboard Router — home screen summary for action cards.

Endpoints:
  GET /dashboard/summary — unreviewed calls, open leads, overdue jobs, recent activity
"""

import logging
from uuid import UUID
from datetime import datetime, timezone, timedelta, date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, AliasChoices
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.marketing.models import Contact, Interaction
from app.operations.models import Job
from app.core.services.auth_service import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class RecentActivityItem(BaseModel):
    interaction_id: UUID
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    type: str
    direction: Optional[str] = None
    subject: Optional[str] = None
    metadata: Optional[dict] = Field(
        None,
        validation_alias=AliasChoices("metadata_", "metadata"),
    )
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class DashboardSummary(BaseModel):
    unreviewed_calls: int = 0
    open_leads: int = 0
    overdue_jobs: int = 0
    recent_activity: list[RecentActivityItem] = []


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    business_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return action card counts and recent activity for the dashboard."""

    # 1. Unreviewed calls routed to Sales
    unreviewed_q = select(func.count(Interaction.id)).where(
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
    unreviewed_calls = (await db.execute(unreviewed_q)).scalar_one()

    # 2. Open leads (prospects not yet converted)
    open_leads = (await db.execute(
        select(func.count(Contact.id)).where(
            Contact.business_id == business_id,
            Contact.status == "prospect",
        )
    )).scalar_one()

    # 3. Overdue jobs (new or in_progress, older than 7 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    overdue_jobs = (await db.execute(
        select(func.count(Job.id)).where(
            Job.business_id == business_id,
            Job.status.in_(["new", "in_progress"]),
            Job.created_at < cutoff,
        )
    )).scalar_one()

    # 4. Recent activity (last 10 interactions, any type)
    activity_rows = (await db.execute(
        select(Interaction)
        .where(Interaction.business_id == business_id)
        .order_by(Interaction.created_at.desc())
        .limit(10)
    )).scalars().all()

    # Batch-load contact names
    contact_ids = {r.contact_id for r in activity_rows if r.contact_id}
    contact_map: dict[UUID, Contact] = {}
    if contact_ids:
        contacts = (await db.execute(
            select(Contact).where(Contact.id.in_(contact_ids))
        )).scalars().all()
        contact_map = {c.id: c for c in contacts}

    recent_activity = [
        RecentActivityItem(
            interaction_id=r.id,
            contact_id=r.contact_id,
            contact_name=contact_map[r.contact_id].full_name if r.contact_id and r.contact_id in contact_map else None,
            type=r.type,
            direction=r.direction,
            subject=r.subject,
            metadata_=r.metadata_,
            created_at=r.created_at,
        )
        for r in activity_rows
    ]

    return DashboardSummary(
        unreviewed_calls=unreviewed_calls,
        open_leads=open_leads,
        overdue_jobs=overdue_jobs,
        recent_activity=recent_activity,
    )
