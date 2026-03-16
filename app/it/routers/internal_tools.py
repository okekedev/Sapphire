"""
Internal Tools Router — Generic credential proxy + discovery for AI employees.

Employees are Claude CLI agents invoked via `claude -p --tools Bash`.
Instead of hardcoded endpoints per platform action, employees:
  1. Call GET /tools/available to discover connected platforms
  2. Use WebSearch to find current platform API docs
  3. Call POST /tools/proxy to execute API calls (credentials injected automatically)

This makes employees self-documenting — they figure out the right API calls
by reading current docs, and we just handle credential injection.

Dedicated endpoints are kept only for operations with DB side effects:
  - Twilio provision/release (creates/updates BusinessPhoneLine records)

These endpoints are INTERNAL ONLY — called by employee agents running
on the same machine. They are NOT user-facing.
"""

import json
import logging
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.core.models.connected_account import ConnectedAccount
from app.core.services.oauth_service import OAuthService
from app.admin.services.twilio_service import twilio_service

logger = logging.getLogger(__name__)
oauth = OAuthService()

router = APIRouter(prefix="/tools", tags=["Internal Tools"])


# ══════════════════════════════════════════════════════════════════════
# Auth injection patterns per platform
# ══════════════════════════════════════════════════════════════════════

# Defines how the proxy injects credentials into outbound requests.
# "oauth" platforms use OAuthService.get_valid_access_token().
# "service" platforms use their dedicated service's get_credentials().
AUTH_PATTERNS = {
    # OAuth platforms — token from OAuthService
    "facebook":                 {"source": "oauth", "inject": "query_param", "param": "access_token"},
    "google_analytics":         {"source": "oauth", "inject": "bearer"},
    "google_search_console":    {"source": "oauth", "inject": "bearer"},
    "google_business_profile":  {"source": "oauth", "inject": "bearer"},
    "youtube":                  {"source": "oauth", "inject": "bearer"},
    "pinterest":                {"source": "oauth", "inject": "bearer"},
    "twitter":                  {"source": "oauth", "inject": "bearer"},
    "linkedin":                 {"source": "oauth", "inject": "bearer"},
    "tiktok":                   {"source": "oauth", "inject": "bearer"},
    # API-key platforms — credentials from platform-specific service
    "stripe":                   {"source": "service", "service": "stripe_service", "inject": "bearer", "field": "secret_key"},
    "twilio":                   {"source": "service", "service": "twilio_service", "inject": "basic", "fields": ["account_sid", "auth_token"]},
}

# Security: only allow proxying to known platform hosts.
# Prevents employees from accidentally sending credentials to arbitrary domains.
ALLOWED_HOSTS = {
    "facebook":                 ["graph.facebook.com"],
    "google_analytics":         ["analyticsdata.googleapis.com", "analytics.googleapis.com"],
    "google_search_console":    ["searchconsole.googleapis.com", "www.googleapis.com"],
    "google_business_profile":  ["mybusiness.googleapis.com", "mybusinessbusinessinformation.googleapis.com"],
    "youtube":                  ["www.googleapis.com", "youtube.googleapis.com"],
    "pinterest":                ["api.pinterest.com"],
    "twitter":                  ["api.twitter.com", "api.x.com"],
    "linkedin":                 ["api.linkedin.com"],
    "tiktok":                   ["open.tiktokapis.com", "business-api.tiktok.com"],
    "stripe":                   ["api.stripe.com"],
    "twilio":                   ["api.twilio.com"],
}

# Friendly metadata for discovery endpoint
PLATFORM_INFO = {
    "facebook":                 {"base_url": "https://graph.facebook.com/v21.0", "docs_hint": "Facebook Graph API"},
    "google_analytics":         {"base_url": "https://analyticsdata.googleapis.com/v1beta", "docs_hint": "Google Analytics Data API (GA4)"},
    "google_search_console":    {"base_url": "https://searchconsole.googleapis.com/v1", "docs_hint": "Google Search Console API"},
    "google_business_profile":  {"base_url": "https://mybusiness.googleapis.com/v4", "docs_hint": "Google Business Profile API"},
    "youtube":                  {"base_url": "https://www.googleapis.com/youtube/v3", "docs_hint": "YouTube Data API v3"},
    "pinterest":                {"base_url": "https://api.pinterest.com/v5", "docs_hint": "Pinterest API v5"},
    "twitter":                  {"base_url": "https://api.twitter.com/2", "docs_hint": "Twitter/X API v2"},
    "linkedin":                 {"base_url": "https://api.linkedin.com/v2", "docs_hint": "LinkedIn Marketing API v2"},
    "tiktok":                   {"base_url": "https://open.tiktokapis.com/v2", "docs_hint": "TikTok API"},
    "stripe":                   {"base_url": "https://api.stripe.com/v1", "docs_hint": "Stripe REST API"},
    "twilio":                   {"base_url": "https://api.twilio.com/2010-04-01", "docs_hint": "Twilio REST API"},
}


# ══════════════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════════════

class ProxyRequest(BaseModel):
    business_id: UUID
    platform: str = Field(..., description="Platform name (e.g. 'stripe', 'facebook', 'google_analytics')")
    method: str = Field("GET", description="HTTP method: GET, POST, PUT, PATCH, DELETE")
    url: str = Field(..., description="Full API URL (e.g. 'https://api.stripe.com/v1/customers')")
    headers: Optional[dict] = Field(None, description="Additional headers (Content-Type, etc.)")
    body: Optional[str] = Field(None, description="Request body as string (JSON or form-encoded)")
    department_id: Optional[UUID] = Field(None, description="Optional department ID to scope the connection")


class TwilioProvisionRequest(BaseModel):
    business_id: UUID
    phone_number: str = Field(..., description="E.164 number to purchase (e.g. +14155551234)")
    campaign_name: str = Field(..., description="Campaign this number is attributed to")
    channel: Optional[str] = Field(None, description="Source channel (google_ads, facebook_ads, etc.)")
    ad_account_id: Optional[str] = Field(None, description="Optional ad account ID")


class TwilioReleaseRequest(BaseModel):
    business_id: UUID
    number_sid: str = Field(..., description="Twilio number SID (e.g. PN...)")


class TwilioSyncRequest(BaseModel):
    business_id: UUID


class TwilioSetMainlineRequest(BaseModel):
    business_id: UUID
    phone_number: str = Field(..., description="E.164 number to set as mainline (e.g. +19401234567)")
    friendly_name: Optional[str] = Field("Mainline", description="Friendly name for the number")
    remove_from_tracking: bool = Field(
        False,
        description="If True, remove from tracking_numbers instead of marking as mainline",
    )




# ══════════════════════════════════════════════════════════════════════
# Discovery Endpoint
# ══════════════════════════════════════════════════════════════════════

@router.get("/available")
async def list_available_platforms(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Discover which platforms this business has connected.

    Returns platform names, base URLs, and docs hints so employees
    can use WebSearch to find current API documentation.

    Employee usage (via Bash):
        curl -s "http://localhost:8000/api/v1/tools/available?business_id=UUID"
    """
    result = await db.execute(
        select(ConnectedAccount.platform, ConnectedAccount.auth_method, ConnectedAccount.status)
        .where(ConnectedAccount.business_id == business_id)
        .where(ConnectedAccount.status == "active")
    )
    rows = result.all()

    platforms = []
    for platform, auth_method, status in rows:
        # Skip the claude CLI token — not a platform employees call
        if platform == "claude":
            continue

        info = PLATFORM_INFO.get(platform, {})
        platforms.append({
            "platform": platform,
            "status": status,
            "auth_method": auth_method,
            "base_url": info.get("base_url", ""),
            "docs_hint": info.get("docs_hint", f"{platform} API"),
            "proxy_supported": platform in AUTH_PATTERNS,
        })

    return {
        "success": True,
        "platforms": platforms,
        "count": len(platforms),
        "proxy_url": "http://localhost:8000/api/v1/tools/proxy",
        "usage": (
            "Use WebSearch to find the API docs for the platform you need. "
            "Then call POST /tools/proxy with your business_id, platform name, "
            "HTTP method, full URL, and body. Auth is injected automatically."
        ),
    }


# ══════════════════════════════════════════════════════════════════════
# Generic Credential Proxy
# ══════════════════════════════════════════════════════════════════════

async def _get_service(service_name: str):
    """Lazy-import platform services to avoid circular imports."""
    if service_name == "stripe_service":
        from app.finance.services.stripe_service import stripe_service
        return stripe_service
    elif service_name == "twilio_service":
        return twilio_service
    raise ValueError(f"Unknown service: {service_name}")


@router.post("/proxy")
async def proxy_request(
    req: ProxyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generic credential proxy — forwards API requests with auth injected.

    Employees use WebSearch to find current platform API docs, construct
    the right request, and route it through this proxy. The proxy:
      1. Validates the target URL against the platform's allowed hosts
      2. Retrieves stored credentials (OAuth token or API key)
      3. Injects authentication into the request
      4. Forwards the request and returns the response

    Employee usage (via Bash):
        curl -s -X POST http://localhost:8000/api/v1/tools/proxy \\
          -H "Content-Type: application/json" \\
          -d '{
            "business_id": "UUID",
            "platform": "stripe",
            "method": "GET",
            "url": "https://api.stripe.com/v1/customers?limit=10",
            "headers": {},
            "body": ""
          }'
    """
    platform = req.platform.lower()
    method = req.method.upper()

    # ── Validate platform is known ──
    if platform not in AUTH_PATTERNS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown platform '{platform}'. Known platforms: {sorted(AUTH_PATTERNS.keys())}",
        )

    # ── Validate URL against allowed hosts ──
    allowed = ALLOWED_HOSTS.get(platform, [])
    parsed = urlparse(req.url)
    if parsed.hostname not in allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                f"URL host '{parsed.hostname}' is not allowed for platform '{platform}'. "
                f"Allowed hosts: {allowed}"
            ),
        )

    # ── Retrieve credentials ──
    pattern = AUTH_PATTERNS[platform]
    headers = dict(req.headers or {})

    try:
        if pattern["source"] == "oauth":
            # OAuth platforms — get access token via OAuthService
            token = await oauth.get_valid_access_token(db, req.business_id, platform, req.department_id)

            if pattern["inject"] == "bearer":
                headers["Authorization"] = f"Bearer {token}"
            elif pattern["inject"] == "query_param":
                # Append token as query parameter
                separator = "&" if "?" in req.url else "?"
                url = f"{req.url}{separator}{pattern['param']}={token}"
            else:
                headers["Authorization"] = f"Bearer {token}"

        elif pattern["source"] == "service":
            # API-key platforms — get credentials from platform service
            service = await _get_service(pattern["service"])
            creds = await service.get_credentials(db, req.business_id)
            if not creds:
                raise HTTPException(
                    status_code=401,
                    detail=f"Platform '{platform}' is not connected. Ask the business owner to connect it.",
                )

            if pattern["inject"] == "bearer":
                token = creds.get(pattern["field"], "")
                headers["Authorization"] = f"Bearer {token}"
            elif pattern["inject"] == "basic":
                import base64
                fields = pattern["fields"]
                user = creds.get(fields[0], "")
                pwd = creds.get(fields[1], "")
                b64 = base64.b64encode(f"{user}:{pwd}".encode()).decode()
                headers["Authorization"] = f"Basic {b64}"

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Proxy: credential retrieval failed for {platform}/{req.business_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve credentials: {e}")

    # ── Use the possibly-modified URL (for query param injection) ──
    final_url = url if (pattern.get("inject") == "query_param" and pattern["source"] == "oauth") else req.url

    # ── Forward the request ──
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=final_url,
                headers=headers,
                content=req.body.encode() if req.body else None,
            )

        # Try to parse as JSON, fall back to text
        try:
            body = response.json()
        except Exception:
            body = response.text

        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "body": body,
        }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Request to {platform} API timed out (30s)")
    except Exception as e:
        logger.error(f"Proxy: request failed for {platform}: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy request failed: {e}")


# ══════════════════════════════════════════════════════════════════════
# Side-Effect Endpoints (DB writes — cannot be proxied generically)
# ══════════════════════════════════════════════════════════════════════

# ── Twilio (provision + release modify TrackingNumber records) ──

@router.post("/twilio/provision")
async def twilio_provision(
    req: TwilioProvisionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Buy a phone number and create a tracking record.

    This is a dedicated endpoint (not proxied) because it creates a
    TrackingNumber record in our database alongside the Twilio API call.

    Employee usage (via Bash):
        curl -s -X POST http://localhost:8000/api/v1/tools/twilio/provision \\
          -H "Content-Type: application/json" \\
          -d '{"business_id":"UUID","phone_number":"+19401234567","campaign_name":"Main Line","channel":"direct"}'
    """
    try:
        result = await twilio_service.provision_number(
            db=db, business_id=req.business_id, phone_number=req.phone_number,
            campaign_name=req.campaign_name, channel=req.channel,
            ad_account_id=req.ad_account_id,
        )
        await db.commit()
        return {"success": True, "result": result}
    except RuntimeError as e:
        logger.error(f"Tool: twilio provision failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Tool: twilio provision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/twilio/release")
async def twilio_release(
    req: TwilioReleaseRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Release a phone number and deactivate its tracking record.

    Dedicated endpoint because it updates TrackingNumber status in our DB.

    Employee usage (via Bash):
        curl -s -X POST http://localhost:8000/api/v1/tools/twilio/release \\
          -H "Content-Type: application/json" \\
          -d '{"business_id":"UUID","number_sid":"PNXXXXXXX"}'
    """
    try:
        result = await twilio_service.release_number(
            db=db, business_id=req.business_id, number_sid=req.number_sid,
        )
        # Run sync immediately after release to reconcile DB ↔ Twilio
        sync_result = await twilio_service.sync_numbers(db=db, business_id=req.business_id)
        await db.commit()
        return {"success": True, "result": result, "sync": sync_result}
    except RuntimeError as e:
        logger.error(f"Tool: twilio release failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Tool: twilio release error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Twilio: sync numbers (reconcile DB ↔ Twilio account) ──

@router.post("/twilio/sync")
async def twilio_sync_numbers(
    req: TwilioSyncRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Reconcile tracking_numbers in DB with the actual Twilio account.

    Deactivates DB records for numbers no longer in Twilio.
    Reports Twilio numbers not tracked in the DB.

    Employee usage (via Bash):
        curl -s -X POST http://localhost:8000/api/v1/tools/twilio/sync \\
          -H "Content-Type: application/json" \\
          -d '{"business_id":"UUID"}'
    """
    try:
        result = await twilio_service.sync_numbers(db=db, business_id=req.business_id)
        if not result.get("synced"):
            raise HTTPException(status_code=400, detail=result.get("reason", "Sync failed"))
        await db.commit()
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool: twilio sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Twilio: set mainline number in credentials ──

@router.post("/twilio/set-mainline")
async def twilio_set_mainline(
    req: TwilioSetMainlineRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Set a phone number as the business mainline.

    Does two things:
    1. Updates the Twilio credentials with the mainline phone_number
    2. Upserts a business_phone_lines record with line_type='mainline' (so the UI reflects the change)

    Employee usage (via Bash):
        curl -s -X POST http://localhost:8000/api/v1/tools/twilio/set-mainline \\
          -H "Content-Type: application/json" \\
          -d '{"business_id":"UUID","phone_number":"+19401234567","friendly_name":"Mainline"}'
    """
    try:
        from app.core.models.connected_account import ConnectedAccount
        from app.marketing.models import BusinessPhoneLine
        from app.core.services.encryption_service import encryption

        # 1. Update Twilio credentials with mainline number
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == req.business_id,
            ConnectedAccount.platform == "twilio",
            ConnectedAccount.status == "active",
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        old_mainline = ""
        if account:
            creds = json.loads(encryption.decrypt(account.encrypted_credentials))
            old_mainline = creds.get("phone_number", "")
            creds["phone_number"] = req.phone_number
            account.encrypted_credentials = encryption.encrypt(json.dumps(creds))

        # 2. Clear any existing mainline flags for this business
        existing_mainlines = await db.execute(
            select(BusinessPhoneLine).where(
                BusinessPhoneLine.business_id == req.business_id,
                BusinessPhoneLine.line_type == "mainline",
            )
        )
        for pl in existing_mainlines.scalars().all():
            pl.line_type = "tracking"

        # 3. Upsert phone line record with line_type='mainline'
        line_stmt = select(BusinessPhoneLine).where(
            BusinessPhoneLine.business_id == req.business_id,
            BusinessPhoneLine.twilio_number == req.phone_number,
        )
        line_result = await db.execute(line_stmt)
        tracking_record = line_result.scalar_one_or_none()

        if tracking_record:
            tracking_record.line_type = "mainline"
            tracking_record.active = True
            if req.friendly_name:
                tracking_record.friendly_name = req.friendly_name
        else:
            tracking_record = BusinessPhoneLine(
                business_id=req.business_id,
                twilio_number=req.phone_number,
                friendly_name=req.friendly_name or "Mainline",
                campaign_name="Mainline",
                line_type="mainline",
                active=True,
            )
            db.add(tracking_record)

        # 4. Auto-resolve twilio_number_sid if missing
        if not tracking_record.twilio_number_sid and account:
            try:
                from app.admin.services.twilio_service import twilio_service
                twilio_numbers = await twilio_service.list_phone_numbers(db, req.business_id)
                for n in twilio_numbers:
                    if n["phone_number"] == req.phone_number:
                        tracking_record.twilio_number_sid = n["sid"]
                        logger.info(f"Auto-resolved SID for mainline {req.phone_number}: {n['sid']}")
                        break
            except Exception as e:
                logger.warning(f"Failed to auto-resolve mainline SID: {e}")

        await db.commit()

        logger.info(
            f"Set mainline for business {req.business_id}: "
            f"{old_mainline} → {req.phone_number}"
        )

        return {
            "success": True,
            "mainline": req.phone_number,
            "previous_mainline": old_mainline or None,
            "tracking_number_id": str(tracking_record.id),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool: set-mainline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ── Self-Documentation ──

LEARNED_NOTES_HEADER = "## Learned Notes"


class SelfDocumentRequest(BaseModel):
    """Employee appends a learned note to their system_prompt."""
    business_id: UUID
    employee_id: str = Field(..., description="File stem of the employee (e.g. 'marcus_director_of_seo')")
    note: str = Field(..., min_length=5, max_length=500, description="What you learned (1-2 sentences)")


class SelfDocumentResponse(BaseModel):
    success: bool
    employee_id: str
    message: str
    notes_count: int


@router.post("/self-document", response_model=SelfDocumentResponse)
async def self_document(
    payload: SelfDocumentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Append a learned note to an employee's system_prompt.

    Employees already see their full system_prompt as context, so they know
    what they've already documented. They should only call this when they
    learn something genuinely new — a pattern, API detail, or approach that
    would help on future tasks.

    The note is appended to a "## Learned Notes" section at the end of the
    prompt. If the section doesn't exist yet, it's created.

    Employee usage (via Bash):
        curl -s -X POST http://localhost:8000/api/v1/tools/self-document \\
          -H "Content-Type: application/json" \\
          -d '{"business_id":"UUID","employee_id":"marcus_director_of_seo","note":"Stripe API v2024-12 requires idempotency keys on all POST requests"}'
    """
    from app.core.models.organization import Employee
    from datetime import datetime, timezone

    # Load business-scoped employee
    stmt = select(Employee).where(
        Employee.file_stem == payload.employee_id,
        Employee.business_id == payload.business_id,
    )
    employee = (await db.execute(stmt)).scalar_one_or_none()

    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee '{payload.employee_id}' not found in business {payload.business_id}",
        )

    prompt = employee.system_prompt or ""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    note_line = f"- [{date_str}] {payload.note}"

    # Append to existing Learned Notes section, or create it
    if LEARNED_NOTES_HEADER in prompt:
        prompt = prompt.rstrip() + f"\n{note_line}\n"
    else:
        prompt = prompt.rstrip() + f"\n\n{LEARNED_NOTES_HEADER}\n\n{note_line}\n"

    employee.system_prompt = prompt
    employee.updated_at = now
    await db.commit()

    # Count total notes
    notes_count = prompt.count("\n- [")

    logger.info(
        f"Self-document: {payload.employee_id} added note in business {payload.business_id}. "
        f"Total notes: {notes_count}"
    )

    return SelfDocumentResponse(
        success=True,
        employee_id=payload.employee_id,
        message=f"Note added. Total learned notes: {notes_count}",
        notes_count=notes_count,
    )
