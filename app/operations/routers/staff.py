"""Staff router — CRUD for human staff members (technicians, dispatchers, admins)."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.services.auth_service import get_current_user_id as get_current_user
from app.operations.models import Staff

router = APIRouter(prefix="/operations/staff", tags=["operations"])


# ── Schemas ──

class StaffOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    first_name: str
    last_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    role: str
    color: Optional[str]
    is_active: bool
    home_address: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class StaffCreate(BaseModel):
    business_id: uuid.UUID
    first_name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str = "technician"
    color: Optional[str] = "#6366f1"
    home_address: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None


class StaffUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    home_address: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None


# ── Endpoints ──

@router.get("", response_model=list[StaffOut])
async def list_staff(
    business_id: uuid.UUID = Query(...),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    q = select(Staff).where(Staff.business_id == business_id)
    if not include_inactive:
        q = q.where(Staff.is_active == True)
    q = q.order_by(Staff.first_name)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=StaffOut, status_code=201)
async def create_staff(
    body: StaffCreate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    member = Staff(**body.model_dump())
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


@router.patch("/{staff_id}", response_model=StaffOut)
async def update_staff(
    staff_id: uuid.UUID,
    body: StaffUpdate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    result = await db.execute(select(Staff).where(Staff.id == staff_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    member.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(member)
    return member


@router.delete("/{staff_id}", status_code=204)
async def delete_staff(
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(get_current_user),
):
    result = await db.execute(select(Staff).where(Staff.id == staff_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")
    member.is_active = False
    member.updated_at = datetime.now(timezone.utc)
    await db.flush()
