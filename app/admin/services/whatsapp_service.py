"""WhatsApp Sender registration via Twilio Senders API v2.

Handles registering Twilio phone numbers as WhatsApp senders,
verification (OTP), status polling, and test messages.

API: POST/GET https://messaging.twilio.com/v2/Channels/Senders
"""

import logging
import httpx
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.organization import Department
from app.admin.services.twilio_service import twilio_service

logger = logging.getLogger(__name__)

SENDERS_BASE = "https://messaging.twilio.com/v2/Channels/Senders"


class WhatsAppError(Exception):
    pass


class WhatsAppService:
    """Manage WhatsApp sender registration per department."""

    async def _get_auth(self, db: AsyncSession, business_id: UUID) -> tuple[str, str]:
        """Get Twilio account_sid + auth_token for HTTP basic auth."""
        creds = await twilio_service.get_credentials(db, business_id)
        if not creds:
            raise WhatsAppError("No Twilio credentials configured")
        return creds["account_sid"], creds["auth_token"]

    async def list_senders(self, db: AsyncSession, business_id: UUID) -> list[dict]:
        """List all WhatsApp senders on this Twilio account."""
        account_sid, auth_token = await self._get_auth(db, business_id)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                SENDERS_BASE,
                params={"Channel": "whatsapp", "PageSize": 50},
                auth=(account_sid, auth_token),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("senders", [])

    async def register_sender(
        self,
        db: AsyncSession,
        business_id: UUID,
        department_id: UUID,
        phone_number: str,
        display_name: str,
    ) -> dict:
        """Register a Twilio number as a WhatsApp sender for a department.

        Args:
            phone_number: E.164 Twilio number (e.g. +19403082696)
            display_name: Business name shown on WhatsApp (Meta reviews this)
        """
        dept = await db.get(Department, department_id)
        if not dept:
            raise WhatsAppError("Department not found")

        account_sid, auth_token = await self._get_auth(db, business_id)

        # Normalize phone number
        digits = "".join(c for c in phone_number if c.isdigit())
        if len(digits) == 10:
            digits = f"1{digits}"
        sender_id = f"whatsapp:+{digits}"

        payload = {
            "sender_id": sender_id,
            "profile": {
                "name": display_name,
            },
            "configuration": {
                "verification_method": "sms",
            },
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SENDERS_BASE,
                json=payload,
                auth=(account_sid, auth_token),
            )
            if resp.status_code >= 400:
                body = resp.text
                logger.error(f"[WA] Register sender failed ({resp.status_code}): {body}")
                raise WhatsAppError(f"Twilio API error: {body}")

            data = resp.json()

        # Save sender SID + status on department
        dept.whatsapp_sender_sid = data.get("sid")
        dept.whatsapp_sender_status = data.get("status", "CREATING")
        dept.whatsapp_enabled = False  # Not enabled until ONLINE
        await db.commit()

        logger.info(
            f"[WA] Registered sender {sender_id} for dept {dept.name}: "
            f"sid={dept.whatsapp_sender_sid} status={dept.whatsapp_sender_status}"
        )
        return data

    async def verify_sender(
        self,
        db: AsyncSession,
        business_id: UUID,
        department_id: UUID,
        verification_code: str,
    ) -> dict:
        """Submit OTP verification code for a pending sender."""
        dept = await db.get(Department, department_id)
        if not dept or not dept.whatsapp_sender_sid:
            raise WhatsAppError("No WhatsApp sender registered for this department")

        account_sid, auth_token = await self._get_auth(db, business_id)

        payload = {
            "configuration": {
                "verification_code": verification_code,
            },
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SENDERS_BASE}/{dept.whatsapp_sender_sid}",
                json=payload,
                auth=(account_sid, auth_token),
            )
            if resp.status_code >= 400:
                body = resp.text
                logger.error(f"[WA] Verify sender failed ({resp.status_code}): {body}")
                raise WhatsAppError(f"Verification failed: {body}")

            data = resp.json()

        dept.whatsapp_sender_status = data.get("status", "VERIFYING")
        await db.commit()

        logger.info(f"[WA] Verified sender {dept.whatsapp_sender_sid}: status={dept.whatsapp_sender_status}")
        return data

    async def refresh_status(
        self,
        db: AsyncSession,
        business_id: UUID,
        department_id: UUID,
    ) -> dict:
        """Poll Twilio for the current sender status."""
        dept = await db.get(Department, department_id)
        if not dept or not dept.whatsapp_sender_sid:
            raise WhatsAppError("No WhatsApp sender registered for this department")

        account_sid, auth_token = await self._get_auth(db, business_id)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SENDERS_BASE}/{dept.whatsapp_sender_sid}",
                auth=(account_sid, auth_token),
            )
            if resp.status_code >= 400:
                body = resp.text
                logger.error(f"[WA] Fetch sender failed ({resp.status_code}): {body}")
                raise WhatsAppError(f"Status check failed: {body}")

            data = resp.json()

        new_status = data.get("status", dept.whatsapp_sender_status)
        dept.whatsapp_sender_status = new_status

        # Auto-enable WhatsApp when sender goes ONLINE
        if new_status == "ONLINE" and not dept.whatsapp_enabled:
            dept.whatsapp_enabled = True
            logger.info(f"[WA] Sender {dept.whatsapp_sender_sid} is ONLINE — auto-enabled WhatsApp for {dept.name}")

        await db.commit()
        return data

    async def send_test(
        self,
        db: AsyncSession,
        business_id: UUID,
        department_id: UUID,
    ) -> bool:
        """Send a test WhatsApp message to the department's forward number."""
        dept = await db.get(Department, department_id)
        if not dept:
            raise WhatsAppError("Department not found")
        if not dept.whatsapp_enabled or dept.whatsapp_sender_status != "ONLINE":
            raise WhatsAppError("WhatsApp sender is not ONLINE")
        if not dept.forward_number:
            raise WhatsAppError("No forwarding number configured")

        # The sender_id stored in Twilio is like "whatsapp:+19403082696"
        # We need the raw number for send_whatsapp
        account_sid, auth_token = await self._get_auth(db, business_id)

        # Get the sender's phone number from the SID
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SENDERS_BASE}/{dept.whatsapp_sender_sid}",
                auth=(account_sid, auth_token),
            )
            resp.raise_for_status()
            sender_data = resp.json()

        sender_phone = sender_data.get("sender_id", "").replace("whatsapp:", "")
        if not sender_phone:
            raise WhatsAppError("Could not determine sender phone number")

        return await twilio_service.send_whatsapp(
            db=db,
            business_id=business_id,
            to=dept.forward_number,
            from_number=sender_phone,
            body=f"✅ WhatsApp test from Workforce — {dept.name} department is connected!",
        )

    async def get_department_status(
        self,
        db: AsyncSession,
        department_id: UUID,
    ) -> dict:
        """Get the WhatsApp status for a department (no Twilio call)."""
        dept = await db.get(Department, department_id)
        if not dept:
            raise WhatsAppError("Department not found")
        return {
            "department_id": str(dept.id),
            "department_name": dept.name,
            "whatsapp_enabled": dept.whatsapp_enabled,
            "whatsapp_sender_sid": dept.whatsapp_sender_sid,
            "whatsapp_sender_status": dept.whatsapp_sender_status or "none",
        }


whatsapp_service = WhatsAppService()
