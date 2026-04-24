"""Job Templates router — CRUD for reusable job form templates."""

import uuid
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.services.auth_service import get_current_user_id as get_current_user
from app.operations.models import JobTemplate

router = APIRouter(prefix="/operations/job-templates", tags=["operations"])


# ── Schemas ──

class JobTemplateOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    description: Optional[str]
    requires_scheduling: bool
    requires_assignment: bool
    requires_dispatch: bool
    schema: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: JobTemplate) -> "JobTemplateOut":
        return cls(
            id=obj.id,
            business_id=obj.business_id,
            name=obj.name,
            description=obj.description,
            requires_scheduling=obj.requires_scheduling,
            requires_assignment=obj.requires_assignment,
            requires_dispatch=obj.requires_dispatch,
            schema=obj.schema_,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class JobTemplateCreate(BaseModel):
    business_id: uuid.UUID
    name: str
    description: Optional[str] = None
    requires_scheduling: bool = False
    requires_assignment: bool = False
    requires_dispatch: bool = False
    schema: dict[str, Any] = {"sections": []}


class JobTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    requires_scheduling: Optional[bool] = None
    requires_assignment: Optional[bool] = None
    requires_dispatch: Optional[bool] = None
    schema: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


# ── Endpoints ──

@router.get("", response_model=list[JobTemplateOut])
async def list_job_templates(
    business_id: uuid.UUID = Query(...),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    q = select(JobTemplate).where(JobTemplate.business_id == business_id)
    if not include_inactive:
        q = q.where(JobTemplate.is_active == True)
    q = q.order_by(JobTemplate.name)
    result = await db.execute(q)
    templates = result.scalars().all()
    return [JobTemplateOut.from_orm_obj(t) for t in templates]


@router.post("", response_model=JobTemplateOut, status_code=201)
async def create_job_template(
    body: JobTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    data = body.model_dump()
    schema_val = data.pop("schema")
    template = JobTemplate(**data, schema_=schema_val)
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return JobTemplateOut.from_orm_obj(template)


@router.patch("/{template_id}", response_model=JobTemplateOut)
async def update_job_template(
    template_id: uuid.UUID,
    body: JobTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    result = await db.execute(select(JobTemplate).where(JobTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "schema":
            template.schema_ = value
        else:
            setattr(template, field, value)
    template.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(template)
    return JobTemplateOut.from_orm_obj(template)


@router.delete("/{template_id}", status_code=204)
async def delete_job_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    result = await db.execute(select(JobTemplate).where(JobTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    template.is_active = False
    template.updated_at = datetime.now(timezone.utc)
    await db.flush()
