"""
Stripe Router — bring-your-own-account billing integration.

Endpoints (all JWT-authenticated):
  POST   /stripe/connect      — Store Stripe secret key (verifies with Stripe first)
  GET    /stripe/status       — Get connection status for the Connections page
  DELETE /stripe/disconnect   — Revoke stored credentials
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.services.auth_service import get_current_user_id
from app.core.services.phone_utils import normalize_phone
from app.finance.services.stripe_service import stripe_service
from app.marketing.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["Stripe"])


# ── Request / Response Schemas ──

class StripeConnectRequest(BaseModel):
    business_id: str
    secret_key: str


class StripeConnectResponse(BaseModel):
    connected: bool
    account_name: str
    account_id: str
    message: str


class StripeStatusResponse(BaseModel):
    platform: str
    connected: bool
    status: str
    account_name: str | None
    account_id: str | None
    connected_at: str | None


# ── Endpoints ──

@router.post("/connect", response_model=StripeConnectResponse)
async def connect_stripe(
    payload: StripeConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Connect a Stripe account by storing the secret key.
    Verifies the key is valid before storing.
    """
    # Verify credentials first
    try:
        verified = await stripe_service.verify_credentials(payload.secret_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    business_id = UUID(payload.business_id)
    await stripe_service.store_credentials(
        db=db,
        business_id=business_id,
        secret_key=payload.secret_key,
        account_name=verified.get("account_name", ""),
        account_id=verified.get("account_id", ""),
    )
    await db.flush()

    logger.info(
        f"Stripe connected for business {business_id}: "
        f"account={verified.get('account_id')}"
    )

    return StripeConnectResponse(
        connected=True,
        account_name=verified.get("account_name", ""),
        account_id=verified.get("account_id", ""),
        message="Stripe connected successfully.",
    )


@router.get("/status", response_model=StripeStatusResponse)
async def get_stripe_status(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """Return connection status for the Connections page Stripe card."""
    status = await stripe_service.get_status(db, UUID(business_id))
    return StripeStatusResponse(**status)


@router.delete("/disconnect")
async def disconnect_stripe(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """Revoke the stored Stripe credentials for a business."""
    success = await stripe_service.disconnect(db, UUID(business_id))
    await db.flush()

    if not success:
        raise HTTPException(status_code=404, detail="No Stripe connection found for this business")

    return {"status": "disconnected", "message": "Stripe disconnected."}


# ── Customer Import ──────────────────────────────────────────────────────────

class ImportResult(BaseModel):
    imported: int
    updated: int
    total: int
    needs_org_review: list[dict]  # [{contact_id, name, email, company}]


@router.post("/import-customers", response_model=ImportResult)
async def import_stripe_customers(
    business_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Paginate all Stripe customers and upsert them as Contacts.

    - Matches on stripe_customer_id first, then email, then creates new.
    - Sets status=active_customer, source_channel=stripe_import.
    - Detects company name from Stripe metadata.company or description.
    - Returns contacts that have a company name but no Organization assigned
      so the frontend can show a review step.
    """
    bid = UUID(business_id)
    creds = await stripe_service.get_credentials(db, bid)
    if not creds:
        raise HTTPException(status_code=400, detail="Stripe not connected")

    import stripe as stripe_sdk
    stripe_sdk.api_key = creds["secret_key"]

    imported = 0
    updated = 0
    needs_org_review: list[dict] = []
    starting_after: str | None = None

    # Fetch existing organizations for this business (for matching)
    org_result = await db.execute(
        select(Organization).where(Organization.business_id == bid)
    )
    existing_orgs: list[Organization] = list(org_result.scalars().all())
    org_name_map = {o.name.lower(): o for o in existing_orgs}

    while True:
        params: dict = {"limit": 100}
        if starting_after:
            params["starting_after"] = starting_after

        page = stripe_sdk.Customer.list(**params)
        customers = page.get("data", [])
        if not customers:
            break

        for cust in customers:
            name = cust.get("name") or ""
            email = cust.get("email") or None
            phone = normalize_phone(cust.get("phone") or "")
            meta = cust.get("metadata") or {}

            # Company detection: metadata.company > description > None
            company = (
                meta.get("company")
                or meta.get("Company")
                or (cust.get("description") if cust.get("description") else None)
            )

            was_new = False
            contact = await stripe_service.sync_stripe_customer(
                db, bid,
                stripe_customer_id=cust["id"],
                name=name or None,
                email=email,
                phone=phone,
            )

            # Track new vs updated
            if contact.source_channel != "stripe_import":
                # First time this contact is being touched by the importer
                was_new = contact.created_at == contact.updated_at if hasattr(contact, 'updated_at') else True

            contact.source_channel = "stripe_import"
            if phone and not contact.phone:
                contact.phone = phone

            # Org matching/flagging
            if company:
                if contact.organization_id is None:
                    company_lower = company.lower()
                    matched_org = org_name_map.get(company_lower)
                    if matched_org:
                        contact.organization_id = matched_org.id
                    else:
                        needs_org_review.append({
                            "contact_id": str(contact.id),
                            "name": name,
                            "email": email,
                            "company": company,
                        })

            imported += 1

        await db.flush()

        if not page.get("has_more"):
            break
        starting_after = customers[-1]["id"]

    await db.flush()

    return ImportResult(
        imported=imported,
        updated=0,
        total=imported,
        needs_org_review=needs_org_review,
    )


class AssignOrgsRequest(BaseModel):
    business_id: str
    assignments: list[dict]  # [{contact_id, organization_id or new_org_name}]


@router.post("/assign-orgs")
async def assign_organizations(
    payload: AssignOrgsRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Apply organization assignments from the post-import review step.

    Each assignment is one of:
      {"contact_id": "...", "organization_id": "existing-uuid"}
      {"contact_id": "...", "new_org_name": "Acme Inc"}
    """
    from datetime import datetime, timezone
    from app.marketing.models import Contact

    bid = UUID(payload.business_id)
    org_cache: dict[str, Organization] = {}

    for item in payload.assignments:
        contact_id = UUID(item["contact_id"])
        contact = await db.get(Contact, contact_id)
        if not contact or contact.business_id != bid:
            continue

        if "organization_id" in item and item["organization_id"]:
            contact.organization_id = UUID(item["organization_id"])

        elif "new_org_name" in item and item["new_org_name"]:
            name = item["new_org_name"].strip()
            if name not in org_cache:
                # Check if it already exists (created by another assignment in this batch)
                result = await db.execute(
                    select(Organization).where(
                        Organization.business_id == bid,
                        Organization.name == name,
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    org_cache[name] = existing
                else:
                    now = datetime.now(timezone.utc)
                    new_org = Organization(
                        business_id=bid,
                        name=name,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(new_org)
                    await db.flush()
                    org_cache[name] = new_org
            contact.organization_id = org_cache[name].id

    await db.flush()
    return {"ok": True, "assigned": len(payload.assignments)}
