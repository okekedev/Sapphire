"""
Notifications Router — In-app notification management.

Endpoints:
  - GET  /notifications          — List notifications (with unread count)
  - POST /notifications/read     — Mark one notification as read
  - POST /notifications/read-all — Mark all notifications as read
"""

from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.models.notification import Notification
from app.core.services.auth_service import get_current_user_id

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ── Schemas ──


class NotificationOut(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int


class MarkReadRequest(BaseModel):
    notification_id: UUID


# ── Endpoints ──


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    business_id: UUID = Query(...),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the current user in a business."""
    stmt = (
        select(Notification)
        .where(
            Notification.business_id == business_id,
            Notification.user_id == current_user_id,
        )
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)

    result = await db.execute(stmt)
    items = result.scalars().all()

    # Count unread
    count_stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.business_id == business_id,
            Notification.user_id == current_user_id,
            Notification.is_read == False,
        )
    )
    unread = (await db.execute(count_stmt)).scalar() or 0

    return NotificationListResponse(
        notifications=[NotificationOut.model_validate(n) for n in items],
        unread_count=unread,
    )


@router.post("/read")
async def mark_read(
    payload: MarkReadRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    stmt = select(Notification).where(
        Notification.id == payload.notification_id,
        Notification.user_id == current_user_id,
    )
    notif = (await db.execute(stmt)).scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_read(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read for the current user in a business."""
    stmt = (
        update(Notification)
        .where(
            Notification.business_id == business_id,
            Notification.user_id == current_user_id,
            Notification.is_read == False,
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    return {"message": f"Marked {count} notifications as read", "count": count}
