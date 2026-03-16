"""
Stripe Service — bring-your-own-account billing and invoicing.

The user connects their own Stripe account (Secret Key).
Credentials are encrypted with AES-256-GCM and stored in connected_accounts,
exactly the same pattern as the Twilio and Claude CLI token.

Billing flow:
  1. User connects their Stripe secret key via the Connections page
  2. Harper / Quinn employees output ```json:action blocks
  3. PlatformActionService calls this service to execute Stripe API calls
  4. Results (customer IDs, invoice URLs, etc.) flow back to the caller

Supported Stripe operations:
  - stripe_create_customer       — Create or retrieve a Stripe customer
  - stripe_create_product        — Create a product + price
  - stripe_create_invoice        — Create & finalize a one-time invoice
  - stripe_send_invoice          — Send invoice email to customer
  - stripe_create_subscription   — Subscribe a customer to a recurring price
  - stripe_list_customers        — Search customers by email or name
  - stripe_get_invoice           — Get invoice details and payment status
"""

import json
import logging
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.connected_account import ConnectedAccount
from app.core.services.encryption_service import EncryptionService
from app.marketing.models import Contact
from app.finance.models import Payment

logger = logging.getLogger(__name__)

PLATFORM = "stripe"
encryption = EncryptionService()


class StripeService:
    """Per-business Stripe credential management and billing helpers."""

    # ── Credential storage ──

    async def store_credentials(
        self,
        db: AsyncSession,
        business_id: UUID,
        secret_key: str,
        account_name: str | None = None,
        account_id: str | None = None,
    ) -> ConnectedAccount:
        """Encrypt and persist Stripe secret key for a business."""
        cred_json = json.dumps({
            "secret_key": secret_key,
            "account_name": account_name or "",
            "account_id": account_id or "",
        })
        encrypted = encryption.encrypt(cred_json)

        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            account.encrypted_credentials = encrypted
            account.status = "active"
            account.external_account_id = account_id
            account.connected_at = datetime.now(timezone.utc)
        else:
            account = ConnectedAccount(
                business_id=business_id,
                platform=PLATFORM,
                auth_method="api_key",
                encrypted_credentials=encrypted,
                status="active",
                external_account_id=account_id,
                connected_at=datetime.now(timezone.utc),
            )
            db.add(account)

        await db.flush()
        return account

    async def get_credentials(
        self, db: AsyncSession, business_id: UUID
    ) -> dict | None:
        """Retrieve and decrypt Stripe credentials, or None if not connected."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
            ConnectedAccount.status == "active",
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return None
        return json.loads(encryption.decrypt(account.encrypted_credentials))

    async def disconnect(self, db: AsyncSession, business_id: UUID) -> bool:
        """Revoke stored credentials for a business."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return False
        account.status = "revoked"
        await db.flush()
        return True

    # ── Status ──

    async def get_status(self, db: AsyncSession, business_id: UUID) -> dict:
        """Return connection status for the Connections page card."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if not account or account.status == "revoked":
            return {
                "platform": "stripe",
                "connected": False,
                "status": "disconnected",
                "account_name": None,
                "account_id": None,
                "connected_at": None,
            }

        creds = json.loads(encryption.decrypt(account.encrypted_credentials))
        return {
            "platform": "stripe",
            "connected": True,
            "status": account.status,
            "account_name": creds.get("account_name", ""),
            "account_id": creds.get("account_id", ""),
            "connected_at": account.connected_at.isoformat() if account.connected_at else None,
        }

    # ── Stripe API helpers ──

    def _get_client(self, secret_key: str):
        """Return a configured Stripe module using the given secret key."""
        import stripe
        stripe.api_key = secret_key
        return stripe

    async def verify_credentials(self, secret_key: str) -> dict:
        """
        Test credentials by fetching Stripe account info.
        Returns {"valid": True, "account_name": "...", "account_id": "acct_..."} on success.
        Raises ValueError on invalid credentials.
        """
        try:
            import stripe as stripe_sdk
            stripe_sdk.api_key = secret_key
            account = stripe_sdk.Account.retrieve()
            return {
                "valid": True,
                "account_name": account.get("business_profile", {}).get("name")
                    or account.get("settings", {}).get("dashboard", {}).get("display_name")
                    or account.get("email", "Stripe Account"),
                "account_id": account.get("id", ""),
            }
        except Exception as e:
            raise ValueError(f"Invalid Stripe credentials: {e}")

    # ── Billing operations ──

    async def create_customer(
        self,
        db: AsyncSession,
        business_id: UUID,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """
        Create a new Stripe customer (or retrieve if email already exists).
        Returns customer dict with id, name, email, phone.
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("Stripe not connected for this business")

        stripe = self._get_client(creds["secret_key"])

        # Check for existing customer by email
        if email:
            existing = stripe.Customer.search(query=f'email:"{email}"', limit=1)
            if existing.get("data"):
                c = existing["data"][0]
                return {
                    "id": c["id"],
                    "name": c.get("name", ""),
                    "email": c.get("email", ""),
                    "phone": c.get("phone", ""),
                    "created": c.get("created"),
                    "existing": True,
                }

        params: dict = {"name": name}
        if email:
            params["email"] = email
        if phone:
            params["phone"] = phone
        if metadata:
            params["metadata"] = metadata

        customer = stripe.Customer.create(**params)
        return {
            "id": customer["id"],
            "name": customer.get("name", ""),
            "email": customer.get("email", ""),
            "phone": customer.get("phone", ""),
            "created": customer.get("created"),
            "existing": False,
        }

    async def create_product(
        self,
        db: AsyncSession,
        business_id: UUID,
        name: str,
        price_cents: int,
        currency: str = "usd",
        interval: str | None = None,  # "month", "year", None = one-time
        description: str | None = None,
    ) -> dict:
        """
        Create a Stripe product + price.
        Returns {"product_id": ..., "price_id": ..., "amount": ..., "interval": ...}
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("Stripe not connected for this business")

        stripe = self._get_client(creds["secret_key"])

        product_params: dict = {"name": name}
        if description:
            product_params["description"] = description
        product = stripe.Product.create(**product_params)

        price_params: dict = {
            "product": product["id"],
            "unit_amount": price_cents,
            "currency": currency,
        }
        if interval:
            price_params["recurring"] = {"interval": interval}
        price = stripe.Price.create(**price_params)

        return {
            "product_id": product["id"],
            "product_name": product["name"],
            "price_id": price["id"],
            "amount_cents": price_cents,
            "currency": currency,
            "interval": interval,
        }

    async def create_invoice(
        self,
        db: AsyncSession,
        business_id: UUID,
        customer_id: str,
        line_items: list[dict],  # [{"description": str, "amount_cents": int, "quantity": int}]
        due_days: int = 30,
        notes: str | None = None,
        auto_finalize: bool = True,
        contact_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> dict:
        """
        Create a Stripe invoice with line items for a customer.
        Each line item: {"description": str, "amount_cents": int, "quantity": int (optional)}
        Auto-records a Payment row and syncs the Stripe customer to contacts.
        Returns invoice dict with id, status, hosted_invoice_url, pdf_url.
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("Stripe not connected for this business")

        stripe = self._get_client(creds["secret_key"])

        # Create invoice items
        for item in line_items:
            stripe.InvoiceItem.create(
                customer=customer_id,
                amount=item["amount_cents"],
                currency="usd",
                description=item.get("description", "Service"),
                quantity=item.get("quantity", 1),
            )

        # Create the invoice
        invoice_params: dict = {
            "customer": customer_id,
            "collection_method": "send_invoice",
            "days_until_due": due_days,
        }
        if notes:
            invoice_params["footer"] = notes

        invoice = stripe.Invoice.create(**invoice_params)

        # Finalize (locks the invoice and calculates totals)
        if auto_finalize:
            invoice = stripe.Invoice.finalize_invoice(invoice["id"])

        # Sync Stripe customer → contacts table
        stripe_cust = stripe.Customer.retrieve(customer_id)
        contact = await self.sync_stripe_customer(
            db, business_id,
            stripe_customer_id=customer_id,
            name=stripe_cust.get("name"),
            email=stripe_cust.get("email"),
            phone=stripe_cust.get("phone"),
        )
        resolved_contact_id = contact_id or contact.id

        # Record payment (one-time invoice)
        amount_cents = invoice.get("amount_due", 0)
        await self.record_payment(
            db, business_id,
            contact_id=resolved_contact_id,
            job_id=job_id,
            amount=amount_cents / 100,
            payment_type="one_time",
            status="pending",
            stripe_customer_id=customer_id,
            stripe_invoice_id=invoice["id"],
        )

        return {
            "id": invoice["id"],
            "status": invoice["status"],
            "amount_due": amount_cents,
            "currency": invoice.get("currency", "usd"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url", ""),
            "invoice_pdf": invoice.get("invoice_pdf", ""),
            "customer_id": customer_id,
            "contact_id": str(resolved_contact_id),
            "due_date": invoice.get("due_date"),
            "finalized": auto_finalize,
        }

    async def send_invoice(
        self,
        db: AsyncSession,
        business_id: UUID,
        invoice_id: str,
    ) -> dict:
        """Send a finalized invoice to the customer via email."""
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("Stripe not connected for this business")

        stripe = self._get_client(creds["secret_key"])
        invoice = stripe.Invoice.send_invoice(invoice_id)

        return {
            "id": invoice["id"],
            "status": invoice["status"],
            "hosted_invoice_url": invoice.get("hosted_invoice_url", ""),
        }

    async def create_subscription(
        self,
        db: AsyncSession,
        business_id: UUID,
        customer_id: str,
        price_id: str,
        trial_days: int | None = None,
        contact_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> dict:
        """
        Subscribe a customer to a recurring price.
        Auto-records a Payment row (type=subscription) and syncs customer to contacts.
        Returns subscription dict with id, status, current_period_end.
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("Stripe not connected for this business")

        stripe = self._get_client(creds["secret_key"])

        params: dict = {
            "customer": customer_id,
            "items": [{"price": price_id}],
        }
        if trial_days:
            params["trial_period_days"] = trial_days

        subscription = stripe.Subscription.create(**params)

        # Sync Stripe customer → contacts table
        stripe_cust = stripe.Customer.retrieve(customer_id)
        contact = await self.sync_stripe_customer(
            db, business_id,
            stripe_customer_id=customer_id,
            name=stripe_cust.get("name"),
            email=stripe_cust.get("email"),
            phone=stripe_cust.get("phone"),
        )
        resolved_contact_id = contact_id or contact.id

        # Determine interval/frequency from the price
        items = subscription.get("items", {}).get("data", [])
        interval = ""
        unit_amount = 0
        if items:
            price = items[0].get("price", {})
            unit_amount = price.get("unit_amount", 0)
            recurring = price.get("recurring", {})
            interval = recurring.get("interval", "month") if recurring else "month"

        # Map Stripe interval to our frequency values
        frequency_map = {
            "day": "daily",
            "week": "weekly",
            "month": "monthly",
            "year": "annual",
        }
        frequency = frequency_map.get(interval, "monthly")

        # Record payment (subscription/recurring)
        await self.record_payment(
            db, business_id,
            contact_id=resolved_contact_id,
            job_id=job_id,
            amount=unit_amount / 100,
            payment_type="subscription",
            frequency=frequency,
            status="pending" if trial_days else "completed",
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription["id"],
        )

        return {
            "id": subscription["id"],
            "status": subscription["status"],
            "customer_id": customer_id,
            "contact_id": str(resolved_contact_id),
            "price_id": price_id,
            "amount": unit_amount / 100,
            "frequency": frequency,
            "current_period_start": subscription.get("current_period_start"),
            "current_period_end": subscription.get("current_period_end"),
            "trial_end": subscription.get("trial_end"),
        }

    async def list_customers(
        self,
        db: AsyncSession,
        business_id: UUID,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search or list Stripe customers."""
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("Stripe not connected for this business")

        stripe = self._get_client(creds["secret_key"])

        if query:
            results = stripe.Customer.search(query=query, limit=limit)
            customers = results.get("data", [])
        else:
            results = stripe.Customer.list(limit=limit)
            customers = results.get("data", [])

        return [
            {
                "id": c["id"],
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "phone": c.get("phone", ""),
                "created": c.get("created"),
            }
            for c in customers
        ]

    async def get_invoice(
        self,
        db: AsyncSession,
        business_id: UUID,
        invoice_id: str,
    ) -> dict:
        """Get invoice details and current payment status."""
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("Stripe not connected for this business")

        stripe = self._get_client(creds["secret_key"])
        invoice = stripe.Invoice.retrieve(invoice_id)

        return {
            "id": invoice["id"],
            "status": invoice["status"],
            "amount_due": invoice.get("amount_due", 0),
            "amount_paid": invoice.get("amount_paid", 0),
            "currency": invoice.get("currency", "usd"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url", ""),
            "invoice_pdf": invoice.get("invoice_pdf", ""),
            "due_date": invoice.get("due_date"),
            "paid_at": invoice.get("status_transitions", {}).get("paid_at"),
        }


    # ── Customer sync: Stripe → contacts ──

    async def sync_stripe_customer(
        self,
        db: AsyncSession,
        business_id: UUID,
        stripe_customer_id: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Contact:
        """
        Ensure a Stripe customer exists in our contacts table.
        Matches on stripe_customer_id first, then email, then creates new.
        Returns the Contact row.
        """
        # 1. Already linked?
        stmt = select(Contact).where(
            Contact.business_id == business_id,
            Contact.stripe_customer_id == stripe_customer_id,
        )
        result = await db.execute(stmt)
        contact = result.scalar_one_or_none()
        if contact:
            return contact

        # 2. Match by email?
        if email:
            stmt = select(Contact).where(
                Contact.business_id == business_id,
                Contact.email == email,
            )
            result = await db.execute(stmt)
            contact = result.scalar_one_or_none()
            if contact:
                # Link existing contact to this Stripe customer
                contact.stripe_customer_id = stripe_customer_id
                await db.flush()
                return contact

        # 3. Create new contact from Stripe customer
        contact = Contact(
            business_id=business_id,
            full_name=name or "Unknown",
            email=email,
            phone=phone,
            stripe_customer_id=stripe_customer_id,
            status="active_customer",
            source_channel="stripe",
        )
        db.add(contact)
        await db.flush()
        logger.info(f"Created contact from Stripe customer {stripe_customer_id} → {contact.id}")
        return contact

    async def record_payment(
        self,
        db: AsyncSession,
        business_id: UUID,
        *,
        contact_id: UUID | None = None,
        job_id: UUID | None = None,
        amount: float,
        payment_type: str = "one_time",
        frequency: str | None = None,
        status: str = "pending",
        stripe_customer_id: str | None = None,
        stripe_invoice_id: str | None = None,
        stripe_subscription_id: str | None = None,
        stripe_payment_intent_id: str | None = None,
    ) -> Payment:
        """
        Create a payment record with proper Stripe columns.
        Called after Stripe invoice/subscription creation.
        """
        payment = Payment(
            business_id=business_id,
            contact_id=contact_id,
            job_id=job_id,
            amount=amount,
            payment_type=payment_type,
            frequency=frequency,
            provider="stripe",
            source="stripe_sync",
            status=status,
            stripe_customer_id=stripe_customer_id,
            stripe_invoice_id=stripe_invoice_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_payment_intent_id=stripe_payment_intent_id,
        )
        db.add(payment)
        await db.flush()
        logger.info(f"Recorded {payment_type} payment {payment.id} — invoice={stripe_invoice_id}, sub={stripe_subscription_id}")
        return payment


stripe_service = StripeService()
