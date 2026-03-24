"""
Email Router — campaign-routed email sending, inbound webhook, and AI follow-up.

Endpoints:
  POST /email/send              — Send an email from the app (outbound)
  POST /email/inbound-webhook   — Receive inbound emails (SendGrid Inbound Parse)
  POST /email/ai-followup       — Generate AI follow-up draft for a lead
  GET  /email/thread/{contact_id} — Get email thread for a contact
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.marketing.models import Contact, Interaction
from app.core.models.business import Business
from app.core.services.auth_service import get_current_user_id
from app.marketing.services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["email"])


# ── Schemas ──

class EmailSendRequest(BaseModel):
    contact_id: str
    subject: str
    body: str
    from_address: str | None = None
    reply_to: str | None = None
    campaign_slug: str | None = None


class AIFollowupRequest(BaseModel):
    contact_id: str
    tone: str = "professional"
    occasion: str | None = None  # e.g. "birthday", "christmas", "new_year", "check_in"


# ── Endpoints ──

@router.post("/send")
async def send_email(
    payload: EmailSendRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Compose and send an email from within the app."""
    # Look up contact
    result = await db.execute(
        select(Contact).where(
            Contact.id == payload.contact_id,
            Contact.business_id == business_id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if not contact.email:
        raise HTTPException(status_code=400, detail="Contact has no email address")

    # Build from/reply-to using campaign if provided
    from_addr = payload.from_address
    reply_to = payload.reply_to
    if payload.campaign_slug:
        campaign_email = email_service.build_campaign_email(payload.campaign_slug)
        from_addr = from_addr or campaign_email
        reply_to = reply_to or campaign_email

    # Send
    send_result = await email_service.send_email(
        to=contact.email,
        subject=payload.subject,
        body=payload.body,
        from_address=from_addr,
        reply_to=reply_to,
    )

    if not send_result.get("sent"):
        raise HTTPException(status_code=502, detail=f"Email send failed: {send_result.get('error', 'Unknown')}")

    # Log as outbound email interaction
    interaction = Interaction(
        business_id=business_id,
        contact_id=contact.id,
        type="email",
        direction="outbound",
        subject=payload.subject,
        body=payload.body,
        created_by=str(current_user_id),
        metadata_={
            "message_id": send_result.get("message_id"),
            "provider": send_result.get("provider"),
            "from": from_addr,
            "to": contact.email,
        },
    )
    db.add(interaction)
    await db.flush()

    return {
        "sent": True,
        "interaction_id": str(interaction.id),
        "message_id": send_result.get("message_id"),
    }


@router.post("/inbound-webhook")
async def inbound_email_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive inbound emails via SendGrid Inbound Parse.
    Parses the 'to' address to extract campaign slug, finds the linked contact,
    and creates an inbound email interaction.
    """
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid form data")

    to_addr = str(form.get("to", ""))
    from_addr = str(form.get("from", ""))
    subject = str(form.get("subject", ""))
    text = str(form.get("text", ""))
    html = str(form.get("html", ""))

    logger.info(f"[INBOUND EMAIL] From: {from_addr} To: {to_addr} Subject: {subject}")

    # Extract sender email
    sender_email = from_addr
    if "<" in sender_email:
        sender_email = sender_email.split("<")[1].rstrip(">").strip()

    # Find contact by email across all businesses
    result = await db.execute(
        select(Contact).where(Contact.email == sender_email).limit(1)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        logger.warning(f"No contact found for inbound email from {sender_email}")
        return {"status": "no_contact_match", "from": sender_email}

    # Create inbound email interaction
    interaction = Interaction(
        business_id=contact.business_id,
        contact_id=contact.id,
        type="email",
        direction="inbound",
        subject=subject,
        body=text or html,
        metadata_={
            "from": from_addr,
            "to": to_addr,
            "message_id": str(form.get("Message-ID", "")),
            "in_reply_to": str(form.get("In-Reply-To", "")),
        },
    )
    db.add(interaction)
    await db.flush()
    await db.commit()

    return {"status": "received", "interaction_id": str(interaction.id)}


@router.post("/ai-followup")
async def generate_ai_followup(
    payload: AIFollowupRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI follow-up email draft for a lead based on call + email history."""
    # Get contact
    result = await db.execute(
        select(Contact).where(
            Contact.id == payload.contact_id,
            Contact.business_id == business_id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Get interactions for this contact
    int_result = await db.execute(
        select(Interaction)
        .where(Interaction.contact_id == contact.id)
        .order_by(Interaction.created_at.asc())
        .limit(20)
    )
    interactions = int_result.scalars().all()

    # Build thread text
    thread_parts = []
    for i in interactions:
        direction = (i.direction or "").upper()
        itype = (i.type or "").upper()
        thread_parts.append(
            f"[{itype} - {direction}] {i.subject or ''}\n{i.body or ''}"
        )
    thread_text = "\n---\n".join(thread_parts) if thread_parts else "No previous interactions."

    # Get business name for context
    business_name = "Our Team"
    biz_result = await db.execute(
        select(Business).where(Business.id == business_id)
    )
    biz = biz_result.scalar_one_or_none()
    if biz and biz.name:
        business_name = biz.name

    # Generate AI draft — occasion-based or conversation follow-up
    if payload.occasion:
        result = await email_service.generate_occasion_email(
            occasion=payload.occasion,
            business_name=business_name,
            lead_name=contact.full_name or "there",
        )
        return {
            "draft": result["body"],
            "subject": result["subject"],
            "contact_name": contact.full_name,
            "contact_email": contact.email,
        }

    draft = await email_service.generate_followup(
        thread_summary=thread_text,
        business_name=business_name,
        lead_name=contact.full_name or "there",
        tone=payload.tone,
    )

    return {
        "draft": draft,
        "subject": None,
        "contact_name": contact.full_name,
        "contact_email": contact.email,
    }


@router.get("/thread/{contact_id}")
async def get_email_thread(
    contact_id: str,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the full email thread for a contact (all email-type interactions)."""
    result = await db.execute(
        select(Interaction)
        .where(
            Interaction.contact_id == contact_id,
            Interaction.business_id == business_id,
            Interaction.type == "email",
        )
        .order_by(Interaction.created_at.desc())
    )
    interactions = result.scalars().all()

    return {
        "emails": [
            {
                "id": str(i.id),
                "direction": i.direction,
                "subject": i.subject,
                "body": i.body,
                "metadata": i.metadata_,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "created_by": i.created_by,
            }
            for i in interactions
        ]
    }
