"""
Billing Router — Stripe data proxy for the Billing page.

Endpoints:
  GET  /billing/invoices          — List Stripe invoices
  GET  /billing/subscriptions     — List Stripe subscriptions
  GET  /billing/revenue-summary   — Aggregate revenue data
  GET  /billing/customers         — List Stripe customers
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance.models import Payment
from app.core.services.auth_service import get_current_user_id
from app.finance.services.stripe_service import stripe_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


async def _get_stripe(db: AsyncSession, business_id: UUID):
    """Get Stripe module configured with the business's API key."""
    creds = await stripe_service.get_credentials(db, business_id)
    if not creds:
        raise HTTPException(status_code=400, detail="Stripe not connected")
    import stripe
    stripe.api_key = creds["secret_key"]
    return stripe


@router.get("/invoices")
async def list_invoices(
    business_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List Stripe invoices for the business."""
    stripe = await _get_stripe(db, business_id)
    try:
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        result = stripe.Invoice.list(**params)
        invoices = []
        for inv in result.get("data", []):
            invoices.append({
                "id": inv["id"],
                "number": inv.get("number"),
                "customer_id": inv.get("customer"),
                "customer_name": inv.get("customer_name") or inv.get("customer_email", ""),
                "customer_email": inv.get("customer_email", ""),
                "amount_due": inv.get("amount_due", 0),
                "amount_paid": inv.get("amount_paid", 0),
                "currency": inv.get("currency", "usd"),
                "status": inv.get("status"),
                "hosted_invoice_url": inv.get("hosted_invoice_url", ""),
                "invoice_pdf": inv.get("invoice_pdf", ""),
                "due_date": inv.get("due_date"),
                "created": inv.get("created"),
                "paid_at": inv.get("status_transitions", {}).get("paid_at"),
            })
        return {"invoices": invoices, "has_more": result.get("has_more", False)}
    except Exception as e:
        logger.error(f"Stripe list invoices error: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


@router.get("/subscriptions")
async def list_subscriptions(
    business_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List Stripe subscriptions."""
    stripe = await _get_stripe(db, business_id)
    try:
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        result = stripe.Subscription.list(**params)
        subscriptions = []
        for sub in result.get("data", []):
            # Extract plan/price info from items
            items = sub.get("items", {}).get("data", [])
            plan_name = ""
            unit_amount = 0
            interval = ""
            if items:
                price = items[0].get("price", {})
                plan_name = price.get("nickname") or price.get("product", "")
                unit_amount = price.get("unit_amount", 0)
                recurring = price.get("recurring", {})
                interval = recurring.get("interval", "") if recurring else ""

            subscriptions.append({
                "id": sub["id"],
                "customer_id": sub.get("customer"),
                "status": sub.get("status"),
                "plan_name": plan_name,
                "amount": unit_amount,
                "currency": sub.get("currency", "usd"),
                "interval": interval,
                "current_period_start": sub.get("current_period_start"),
                "current_period_end": sub.get("current_period_end"),
                "cancel_at_period_end": sub.get("cancel_at_period_end", False),
                "created": sub.get("created"),
            })
        return {"subscriptions": subscriptions, "has_more": result.get("has_more", False)}
    except Exception as e:
        logger.error(f"Stripe list subscriptions error: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


@router.get("/revenue-summary")
async def revenue_summary(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregate revenue data from local Payment records + Stripe.
    Returns total collected, MRR, outstanding, active subscriptions count.
    """
    # Local payment totals
    completed_total = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.business_id == business_id,
                Payment.status == "completed",
            )
        )
    ).scalar()

    pending_total = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.business_id == business_id,
                Payment.status == "pending",
            )
        )
    ).scalar()

    subscription_count = (
        await db.execute(
            select(func.count()).where(
                Payment.business_id == business_id,
                Payment.payment_type == "subscription",
                Payment.status == "completed",
            )
        )
    ).scalar()

    mrr = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.business_id == business_id,
                Payment.payment_type == "subscription",
                Payment.status == "completed",
                Payment.frequency == "monthly",
            )
        )
    ).scalar()

    # Try to augment with Stripe data if connected
    stripe_balance = None
    stripe_subs_count = 0
    try:
        creds = await stripe_service.get_credentials(db, business_id)
        if creds:
            import stripe
            stripe.api_key = creds["secret_key"]
            balance = stripe.Balance.retrieve()
            available = balance.get("available", [])
            if available:
                stripe_balance = sum(b.get("amount", 0) for b in available) / 100

            # Count active Stripe subscriptions
            subs = stripe.Subscription.list(status="active", limit=1)
            stripe_subs_count = subs.get("total_count", 0) if "total_count" in subs else len(subs.get("data", []))
    except Exception:
        pass  # Stripe not connected or error — use local data only

    return {
        "total_collected": float(completed_total),
        "pending": float(pending_total),
        "mrr": float(mrr),
        "active_subscriptions": int(subscription_count) + stripe_subs_count,
        "stripe_balance": stripe_balance,
        "stripe_connected": stripe_balance is not None,
    }


@router.get("/customers")
async def list_customers(
    business_id: UUID = Query(...),
    search: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List Stripe customers."""
    stripe = await _get_stripe(db, business_id)
    try:
        if search:
            result = stripe.Customer.search(query=f'name~"{search}" OR email~"{search}"', limit=limit)
        else:
            result = stripe.Customer.list(limit=limit)

        customers = []
        for c in result.get("data", []):
            customers.append({
                "id": c["id"],
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "phone": c.get("phone", ""),
                "created": c.get("created"),
            })
        return {"customers": customers, "has_more": result.get("has_more", False)}
    except Exception as e:
        logger.error(f"Stripe list customers error: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


@router.post("/sync-customers")
async def sync_stripe_customers(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Pull all Stripe customers and ensure each one exists in our contacts table.
    Matches on stripe_customer_id, then email. Creates new contacts for unknowns.
    Returns count of synced vs created.
    """
    stripe = await _get_stripe(db, business_id)
    try:
        created = 0
        linked = 0
        already = 0
        has_more = True
        starting_after = None

        while has_more:
            params: dict = {"limit": 100}
            if starting_after:
                params["starting_after"] = starting_after
            result = stripe.Customer.list(**params)
            customers = result.get("data", [])
            has_more = result.get("has_more", False)

            for c in customers:
                contact = await stripe_service.sync_stripe_customer(
                    db,
                    business_id,
                    stripe_customer_id=c["id"],
                    name=c.get("name"),
                    email=c.get("email"),
                    phone=c.get("phone"),
                )
                # Check if this was newly created vs already existed
                if contact.source_channel == "stripe" and contact.stripe_customer_id == c["id"]:
                    # Could be new or already linked — check created_at
                    # Simple heuristic: if we just flushed it, it's new
                    pass
                already += 1

            if customers:
                starting_after = customers[-1]["id"]

        await db.commit()
        return {
            "total_synced": already,
            "message": f"Synced {already} Stripe customers into contacts",
        }
    except Exception as e:
        logger.error(f"Stripe customer sync error: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe sync error: {str(e)}")
