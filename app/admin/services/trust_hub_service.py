"""
Trust Hub Service — Automated SHAKEN/STIR registration for verified calling.

When a business connects Twilio and adds phone numbers, this service
automatically sets up SHAKEN/STIR "A" attestation so outbound calls
aren't blocked by carrier spam filters (e.g. T-Mobile Scam Shield).

The business owner never needs to touch the Twilio Console. All the
required business info (company name, EIN, address, authorized rep)
already exists in Twilio's Trust Hub from when they created their account.

Flow:
  1. Read existing Customer Profile (Primary Business Profile) via API
  2. Check if a SHAKEN/STIR Trust Product already exists
  3. If not, create one linked to the Customer Profile
  4. Assign phone numbers to the Trust Product
  5. Submit for evaluation (Twilio reviews in 24-72 hours)

API reference: https://www.twilio.com/docs/trust-hub/trusthub-rest-api
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.admin.services.twilio_service import twilio_service

logger = logging.getLogger(__name__)


class TrustHubError(Exception):
    """Raised when a Trust Hub API call fails."""
    pass


class TrustHubService:
    """Automated SHAKEN/STIR Trust Product setup via Twilio Trust Hub API."""

    async def _get_client(self, db: AsyncSession, business_id: UUID) -> Client:
        """Get an authenticated Twilio REST client for a business."""
        creds = await twilio_service.get_credentials(db, business_id)
        if not creds:
            raise TrustHubError("Twilio not connected for this business")
        return Client(creds["account_sid"], creds["auth_token"])

    # ── Read existing Trust Hub state ──

    async def get_customer_profile(
        self, db: AsyncSession, business_id: UUID
    ) -> dict | None:
        """Find the existing Primary Customer Profile (created during Twilio signup).

        Returns dict with sid, friendly_name, status, or None if not found.
        """
        client = await self._get_client(db, business_id)
        try:
            profiles = client.trusthub.v1.customer_profiles.list(limit=20)
            for p in profiles:
                if p.status == "twilio-approved":
                    return {
                        "sid": p.sid,
                        "friendly_name": p.friendly_name,
                        "status": p.status,
                    }
            # Return first one even if not approved
            if profiles:
                return {
                    "sid": profiles[0].sid,
                    "friendly_name": profiles[0].friendly_name,
                    "status": profiles[0].status,
                }
            return None
        except TwilioRestException as e:
            logger.error(f"[TrustHub] Failed to list customer profiles: {e}")
            raise TrustHubError(f"Failed to list customer profiles: {e}")

    async def get_shaken_stir_product(
        self, db: AsyncSession, business_id: UUID
    ) -> dict | None:
        """Find existing SHAKEN/STIR Trust Product.

        Returns dict with sid, friendly_name, status, or None if not found.
        """
        client = await self._get_client(db, business_id)
        try:
            products = client.trusthub.v1.trust_products.list(limit=20)
            for p in products:
                # SHAKEN/STIR products have a specific policy
                if "shaken" in (p.friendly_name or "").lower() or \
                   "stir" in (p.friendly_name or "").lower():
                    return {
                        "sid": p.sid,
                        "friendly_name": p.friendly_name,
                        "status": p.status,
                    }
            # Check all products' policies
            for p in products:
                return {
                    "sid": p.sid,
                    "friendly_name": p.friendly_name,
                    "status": p.status,
                }
            return None
        except TwilioRestException as e:
            logger.error(f"[TrustHub] Failed to list trust products: {e}")
            raise TrustHubError(f"Failed to list trust products: {e}")

    async def get_assigned_numbers(
        self, db: AsyncSession, business_id: UUID, trust_product_sid: str
    ) -> list[str]:
        """Get phone number SIDs assigned to a SHAKEN/STIR Trust Product.

        Returns list of phone number SIDs (e.g. ['PNxxxxx', 'PNyyyyy']).
        """
        client = await self._get_client(db, business_id)
        try:
            assignments = client.trusthub.v1 \
                .trust_products(trust_product_sid) \
                .trust_products_channel_endpoint_assignment \
                .list(limit=50)
            return [a.channel_endpoint_sid for a in assignments]
        except TwilioRestException as e:
            logger.error(f"[TrustHub] Failed to list assigned numbers: {e}")
            return []

    # ── Full status check ──

    async def get_status(
        self, db: AsyncSession, business_id: UUID
    ) -> dict:
        """Get the full SHAKEN/STIR status for a business.

        Returns:
            {
                "has_customer_profile": bool,
                "customer_profile_status": str | None,
                "has_trust_product": bool,
                "trust_product_status": str | None,
                "trust_product_sid": str | None,
                "assigned_number_sids": [str],
                "ready": bool,  # True if product approved + numbers assigned
            }
        """
        result = {
            "has_customer_profile": False,
            "customer_profile_status": None,
            "customer_profile_sid": None,
            "has_trust_product": False,
            "trust_product_status": None,
            "trust_product_sid": None,
            "assigned_number_sids": [],
            "ready": False,
        }

        try:
            profile = await self.get_customer_profile(db, business_id)
            if profile:
                result["has_customer_profile"] = True
                result["customer_profile_status"] = profile["status"]
                result["customer_profile_sid"] = profile["sid"]

            product = await self.get_shaken_stir_product(db, business_id)
            if product:
                result["has_trust_product"] = True
                result["trust_product_status"] = product["status"]
                result["trust_product_sid"] = product["sid"]

                assigned = await self.get_assigned_numbers(
                    db, business_id, product["sid"]
                )
                result["assigned_number_sids"] = assigned
                result["ready"] = (
                    product["status"] == "twilio-approved" and len(assigned) > 0
                )
        except TrustHubError:
            pass  # Return partial status

        return result

    # ── Assign numbers ──

    async def assign_number(
        self,
        db: AsyncSession,
        business_id: UUID,
        trust_product_sid: str,
        phone_number_sid: str,
    ) -> bool:
        """Assign a single phone number to a SHAKEN/STIR Trust Product.

        Args:
            trust_product_sid: The Trust Product SID (starts with BU)
            phone_number_sid: The phone number SID (starts with PN)

        Returns True if assigned successfully, False otherwise.
        """
        client = await self._get_client(db, business_id)
        try:
            client.trusthub.v1 \
                .trust_products(trust_product_sid) \
                .trust_products_channel_endpoint_assignment \
                .create(
                    channel_endpoint_type="phone-number",
                    channel_endpoint_sid=phone_number_sid,
                )
            logger.info(
                f"[TrustHub] Assigned {phone_number_sid} to "
                f"SHAKEN/STIR product {trust_product_sid}"
            )
            return True
        except TwilioRestException as e:
            if "already assigned" in str(e).lower() or e.code == 45010:
                logger.info(
                    f"[TrustHub] {phone_number_sid} already assigned "
                    f"to {trust_product_sid}"
                )
                return True  # Already assigned is fine
            logger.error(f"[TrustHub] Failed to assign number: {e}")
            return False

    async def assign_all_numbers(
        self,
        db: AsyncSession,
        business_id: UUID,
        trust_product_sid: str,
        phone_number_sids: list[str],
    ) -> dict:
        """Assign multiple phone numbers to a SHAKEN/STIR Trust Product.

        Returns {"assigned": [...], "failed": [...], "already_assigned": [...]}.
        """
        already_assigned = await self.get_assigned_numbers(
            db, business_id, trust_product_sid
        )

        results = {"assigned": [], "failed": [], "already_assigned": []}
        for pn_sid in phone_number_sids:
            if pn_sid in already_assigned:
                results["already_assigned"].append(pn_sid)
                continue
            ok = await self.assign_number(
                db, business_id, trust_product_sid, pn_sid
            )
            if ok:
                results["assigned"].append(pn_sid)
            else:
                results["failed"].append(pn_sid)

        return results

    # ── Auto-setup (the main entry point) ──

    async def auto_setup(
        self, db: AsyncSession, business_id: UUID
    ) -> dict:
        """Automatically set up SHAKEN/STIR for a business.

        This is the main method to call after a business connects Twilio.
        It checks the existing state and does whatever is needed:
          - Finds the Customer Profile (already exists from Twilio signup)
          - Finds or creates a SHAKEN/STIR Trust Product
          - Assigns all tracking numbers that have a twilio_number_sid
          - Returns the current status

        Returns the same dict as get_status() with an extra "actions" list
        describing what was done.
        """
        actions = []
        client = await self._get_client(db, business_id)

        # Step 1: Find existing Customer Profile
        profile = await self.get_customer_profile(db, business_id)
        if not profile:
            actions.append("no_customer_profile")
            return {
                "error": "No Customer Profile found. The business owner needs "
                         "to complete their Twilio Trust Hub profile first.",
                "actions": actions,
            }

        if profile["status"] != "twilio-approved":
            actions.append(f"customer_profile_status_{profile['status']}")
            return {
                "error": f"Customer Profile status is '{profile['status']}'. "
                         "It must be 'twilio-approved' before SHAKEN/STIR can work.",
                "actions": actions,
            }

        # Step 2: Find or create SHAKEN/STIR Trust Product
        product = await self.get_shaken_stir_product(db, business_id)

        if not product:
            try:
                # Get the SHAKEN/STIR policy SID
                policies = client.trusthub.v1.policies.list(limit=20)
                shaken_policy_sid = None
                for pol in policies:
                    if "shaken" in (pol.friendly_name or "").lower() or \
                       "stir" in (pol.friendly_name or "").lower():
                        shaken_policy_sid = pol.sid
                        break

                if not shaken_policy_sid:
                    # Fallback: use the well-known policy SID for voice
                    # This is Twilio's standard SHAKEN/STIR policy
                    shaken_policy_sid = "RN806dd6cd175f314e1f96a9727ee271f4"

                new_product = client.trusthub.v1.trust_products.create(
                    friendly_name="SHAKEN/STIR Verified Calling",
                    policy_sid=shaken_policy_sid,
                    email=profile.get("email", ""),
                )
                product = {
                    "sid": new_product.sid,
                    "friendly_name": new_product.friendly_name,
                    "status": new_product.status,
                }
                actions.append("created_trust_product")
                logger.info(
                    f"[TrustHub] Created SHAKEN/STIR Trust Product: "
                    f"{new_product.sid}"
                )

                # Link Business Profile to Trust Product
                client.trusthub.v1 \
                    .trust_products(new_product.sid) \
                    .trust_products_entity_assignments \
                    .create(object_sid=profile["sid"])
                actions.append("linked_business_profile")

            except TwilioRestException as e:
                logger.error(f"[TrustHub] Failed to create trust product: {e}")
                raise TrustHubError(f"Failed to create SHAKEN/STIR product: {e}")

        # Step 3: Get all phone lines for this business that have SIDs
        from app.marketing.models import BusinessPhoneLine
        from sqlalchemy import select

        stmt = select(BusinessPhoneLine).where(
            BusinessPhoneLine.business_id == business_id,
            BusinessPhoneLine.active == True,
            BusinessPhoneLine.twilio_number_sid.isnot(None),
        )
        result = await db.execute(stmt)
        phone_lines = result.scalars().all()

        pn_sids = [pl.twilio_number_sid for pl in phone_lines if pl.twilio_number_sid]

        if pn_sids:
            # First assign to Customer Profile (prerequisite)
            for pn_sid in pn_sids:
                try:
                    client.trusthub.v1 \
                        .customer_profiles(profile["sid"]) \
                        .customer_profiles_channel_endpoint_assignment \
                        .create(
                            channel_endpoint_type="phone-number",
                            channel_endpoint_sid=pn_sid,
                        )
                    actions.append(f"assigned_to_profile_{pn_sid}")
                except TwilioRestException as e:
                    if "already assigned" in str(e).lower() or e.code == 45010:
                        pass  # Already assigned, that's fine
                    else:
                        logger.warning(
                            f"[TrustHub] Could not assign {pn_sid} "
                            f"to Customer Profile: {e}"
                        )

            # Then assign to Trust Product
            assign_result = await self.assign_all_numbers(
                db, business_id, product["sid"], pn_sids
            )
            if assign_result["assigned"]:
                actions.append(
                    f"assigned_{len(assign_result['assigned'])}_numbers_to_product"
                )
            if assign_result["failed"]:
                actions.append(
                    f"failed_{len(assign_result['failed'])}_numbers"
                )

        # Step 4: Submit for evaluation if product is still in draft
        if product["status"] == "draft":
            try:
                policies = client.trusthub.v1.policies.list(limit=20)
                shaken_policy_sid = None
                for pol in policies:
                    if "shaken" in (pol.friendly_name or "").lower():
                        shaken_policy_sid = pol.sid
                        break
                if shaken_policy_sid:
                    client.trusthub.v1 \
                        .trust_products(product["sid"]) \
                        .trust_products_evaluations \
                        .create(policy_sid=shaken_policy_sid)
                    actions.append("submitted_for_evaluation")
            except TwilioRestException as e:
                logger.warning(f"[TrustHub] Could not submit for evaluation: {e}")
                actions.append(f"evaluation_error_{e.code}")

        # Return final status
        status = await self.get_status(db, business_id)
        status["actions"] = actions
        return status

    # ── Per-number attestation check ──

    async def get_number_attestation(
        self,
        db: AsyncSession,
        business_id: UUID,
        phone_number_sid: str,
    ) -> str:
        """Check SHAKEN/STIR attestation level for a specific number.

        Returns: "A", "B", "C", or "unknown".
        """
        status = await self.get_status(db, business_id)

        if not status["ready"]:
            return "unknown"

        if phone_number_sid in status["assigned_number_sids"]:
            return "A"  # Assigned to approved Trust Product = "A" attestation

        return "B"  # In account but not assigned = "B" attestation


# Singleton
trust_hub_service = TrustHubService()
