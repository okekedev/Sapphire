"""
Platform connection routes — OAuth flow + credential management.

Handles:
  - OAuth initiation & callback for all platforms
  - API key connections
  - Connected account listing and management
  - Token refresh

Credentials are tied to businesses and scoped per department.
When an employee needs a platform, the system checks if the business
has an active connection for that platform.
"""

import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.models.connected_account import ConnectedAccount
from app.core.schemas.platform import (
    ApiKeyConnectRequest,
    ConnectedAccountOut,
    DisconnectRequest,
    OAuthInitRequest,
    OAuthInitResponse,
)
from app.core.schemas.common import Envelope
from app.core.services.auth_service import get_current_user_id
from app.core.services.oauth_service import OAuthService

router = APIRouter()

# In-memory PKCE verifier store (short-lived, keyed by state).
# Each entry: (code_verifier, expires_at). Entries expire after 10 minutes.
# Production upgrade: move to Redis with TTL for multi-instance deployments.
_PKCE_TTL = 600  # seconds
_pkce_store: dict[str, tuple[str, float]] = {}


# ── OAuth Flow ──


@router.post(
    "/platforms/connect/oauth",
    response_model=Envelope[OAuthInitResponse],
    summary="Start OAuth flow",
)
async def initiate_oauth(
    body: OAuthInitRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Generate an authorization URL for the given platform.

    Optional department_id creates a department-scoped connection.
    If not provided, creates a business-wide (NULL) connection.
    """
    oauth = OAuthService()
    try:
        auth_url, state, code_verifier = oauth.generate_auth_url(
            body.platform, body.business_id, body.department_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if code_verifier:
        # Purge expired entries on each write to prevent unbounded growth
        now = time.monotonic()
        expired = [k for k, (_, exp) in _pkce_store.items() if exp <= now]
        for k in expired:
            del _pkce_store[k]
        _pkce_store[state] = (code_verifier, now + _PKCE_TTL)

    return Envelope(data=OAuthInitResponse(auth_url=auth_url, state=state))


@router.get(
    "/oauth/callback",
    summary="OAuth callback (redirected by platform)",
    include_in_schema=False,
)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle the OAuth callback — exchange code for tokens and store."""
    oauth = OAuthService()

    try:
        state_data = oauth.decrypt_state(state)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    business_id = UUID(state_data["business_id"])
    platform = state_data["platform"]
    department_id = UUID(state_data["department_id"]) if state_data.get("department_id") else None

    entry = _pkce_store.pop(state, None)
    code_verifier = entry[0] if entry and entry[1] > time.monotonic() else None

    try:
        tokens = await oauth.exchange_code(platform, code, code_verifier)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {e}")

    from app.core.services.oauth_service import PLATFORM_CONFIGS
    config = PLATFORM_CONFIGS.get(platform, {})
    scopes = " ".join(config.get("scopes", []))

    try:
        await oauth.store_credentials(
            db, business_id, platform, tokens, scopes, department_id,
        )
        await db.flush()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to store credentials: {e}")

    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:3000"
    return RedirectResponse(
        f"{frontend_url}/connections?platform={platform}&status=success"
    )


# ── API Key Connections ──


@router.post(
    "/platforms/connect/api-key",
    response_model=Envelope[ConnectedAccountOut],
    summary="Connect API key platform",
)
async def connect_api_key(
    body: ApiKeyConnectRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Store an encrypted API key for platforms like Ahrefs, SEMrush.

    Optional department_id creates a department-scoped connection.
    If not provided, creates a business-wide (NULL) connection.
    """
    oauth = OAuthService()
    try:
        account = await oauth.store_api_key(
            db, body.business_id, body.platform, body.api_key, body.department_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Envelope(data=ConnectedAccountOut.model_validate(account))


# ── Account Management ──


@router.get(
    "/platforms/connections",
    response_model=Envelope[list[ConnectedAccountOut]],
    summary="List connected platforms",
)
async def list_connections(
    business_id: UUID = Query(...),
    department_id: UUID | None = Query(None),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all connected platform accounts for a business.

    Optional department_id filters to only that department's connections.
    If not provided, returns ALL connections (business-wide + any departments).
    """
    stmt = (
        select(ConnectedAccount)
        .where(ConnectedAccount.business_id == business_id)
    )
    if department_id is not None:
        stmt = stmt.where(ConnectedAccount.department_id == department_id)
    stmt = stmt.order_by(ConnectedAccount.connected_at.desc())
    result = await db.execute(stmt)
    accounts = result.scalars().all()
    return Envelope(data=[ConnectedAccountOut.model_validate(a) for a in accounts])


@router.post(
    "/platforms/disconnect",
    response_model=Envelope[dict],
    summary="Disconnect a platform",
)
async def disconnect_platform(
    body: DisconnectRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a platform connection.

    If department_id is provided, disconnects only that department's connection.
    If department_id is None, disconnects any business-wide (NULL) connection.
    """
    oauth = OAuthService()
    removed = await oauth.disconnect(db, body.business_id, body.platform, body.department_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Connection not found")
    return Envelope(data={"platform": body.platform, "status": "disconnected"})


@router.post(
    "/platforms/refresh",
    response_model=Envelope[dict],
    summary="Force-refresh an OAuth token",
)
async def refresh_platform_token(
    body: DisconnectRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a token refresh for a platform.

    If department_id is provided, refreshes only that department's token.
    If department_id is None, refreshes any business-wide (NULL) token.
    """
    oauth = OAuthService()
    try:
        await oauth.refresh_token(db, body.business_id, body.platform, body.department_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Envelope(data={"platform": body.platform, "status": "refreshed"})


# ── Connection Testing ──


@router.get(
    "/platforms/test/{platform}",
    response_model=Envelope[dict],
    summary="Test a platform connection with a real API call",
)
async def test_connection(
    platform: str,
    business_id: UUID = Query(...),
    department_id: UUID | None = Query(None),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Make a lightweight API call to verify the stored token actually works.

    Optional department_id tests only that department's connection.
    If not provided, tests any business-wide (NULL) connection.
    """
    import httpx

    oauth = OAuthService()
    try:
        token = await oauth.get_valid_access_token(db, business_id, platform, department_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    test_results: dict = {"platform": platform, "token_valid": False}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if platform == "facebook":
                resp = await client.get(
                    "https://graph.facebook.com/v21.0/me",
                    params={"access_token": token, "fields": "id,name,email"},
                )
                resp.raise_for_status()
                data = resp.json()
                test_results.update({
                    "token_valid": True,
                    "account_name": data.get("name"),
                    "account_id": data.get("id"),
                    "email": data.get("email"),
                })

                # Also try to list pages
                pages_resp = await client.get(
                    "https://graph.facebook.com/v21.0/me/accounts",
                    params={"access_token": token, "fields": "id,name,category"},
                )
                if pages_resp.status_code == 200:
                    pages_data = pages_resp.json().get("data", [])
                    test_results["pages"] = [
                        {"id": p["id"], "name": p["name"], "category": p.get("category")}
                        for p in pages_data
                    ]
                    test_results["page_count"] = len(pages_data)

            elif platform.startswith("google"):
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/tokeninfo",
                    params={"access_token": token},
                )
                resp.raise_for_status()
                data = resp.json()
                test_results.update({
                    "token_valid": True,
                    "scope": data.get("scope"),
                    "expires_in": data.get("expires_in"),
                    "email": data.get("email"),
                })
            else:
                test_results["message"] = f"No test endpoint configured for {platform}"
                test_results["token_valid"] = True

    except httpx.HTTPStatusError as e:
        test_results["error"] = f"API returned {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        test_results["error"] = str(e)

    return Envelope(data=test_results)
