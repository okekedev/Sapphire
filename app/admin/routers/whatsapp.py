"""WhatsApp sender management endpoints.

Register Twilio numbers as WhatsApp senders, verify them,
poll status, and send test messages.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.services.auth_service import get_current_user_id
from app.admin.services.whatsapp_service import whatsapp_service, WhatsAppError

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


class RegisterRequest(BaseModel):
    business_id: UUID
    department_id: UUID
    phone_number: str  # Twilio number in E.164
    display_name: str  # Business name on WhatsApp


class VerifyRequest(BaseModel):
    business_id: UUID
    department_id: UUID
    verification_code: str


@router.get("/senders")
async def list_senders(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all WhatsApp senders on the Twilio account."""
    try:
        return await whatsapp_service.list_senders(db, business_id)
    except WhatsAppError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register")
async def register_sender(
    payload: RegisterRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Register a Twilio number as a WhatsApp sender for a department."""
    try:
        return await whatsapp_service.register_sender(
            db=db,
            business_id=payload.business_id,
            department_id=payload.department_id,
            phone_number=payload.phone_number,
            display_name=payload.display_name,
        )
    except WhatsAppError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify")
async def verify_sender(
    payload: VerifyRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Submit OTP verification code for a pending WhatsApp sender."""
    try:
        return await whatsapp_service.verify_sender(
            db=db,
            business_id=payload.business_id,
            department_id=payload.department_id,
            verification_code=payload.verification_code,
        )
    except WhatsAppError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/refresh")
async def refresh_status(
    business_id: UUID = Query(...),
    department_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Poll Twilio for current WhatsApp sender status. Auto-enables if ONLINE."""
    try:
        return await whatsapp_service.refresh_status(db, business_id, department_id)
    except WhatsAppError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/test")
async def send_test(
    business_id: UUID = Query(...),
    department_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Send a test WhatsApp message to the department's forwarding number."""
    try:
        ok = await whatsapp_service.send_test(db, business_id, department_id)
        if ok:
            return {"status": "sent"}
        return {"status": "failed", "detail": "send_whatsapp returned False"}
    except WhatsAppError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def get_status(
    department_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get WhatsApp status for a department (no Twilio API call)."""
    try:
        return await whatsapp_service.get_department_status(db, department_id)
    except WhatsAppError as e:
        raise HTTPException(status_code=400, detail=str(e))
