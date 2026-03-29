"""
Authentication routes — registration, login, token refresh, Azure AD SSO.
"""

from datetime import datetime, timedelta, timezone

import httpx
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.models.user import User
from app.core.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
import structlog
from app.core.services.auth_service import AuthService
from app.config import settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth")
auth_service = AuthService()


def _msal_app():
    """MSAL app using UAMI federated credential — no client secret.

    The user-assigned MI (uami-sapphire-prod) is configured as a federated
    identity credential on the Sapphire App Registration. MSAL acquires an
    MI token for audience api://AzureADTokenExchange and presents it as a
    client_assertion. Requires msal>=1.29.0.
    """
    import msal
    return msal.ConfidentialClientApplication(
        settings.azure_ad_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}",
        client_credential=msal.UserAssignedManagedIdentity(
            client_id=settings.uami_client_id,
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account."""
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email,
        password_hash=auth_service.hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()

    tokens = auth_service.create_tokens(user_id=str(user.id))
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return JWT tokens."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not auth_service.verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    tokens = auth_service.create_tokens(user_id=str(user.id))
    return tokens


@router.get("/microsoft/login")
async def microsoft_login():
    """Return the Azure AD authorization URL. Frontend redirects the user there."""
    if not settings.azure_ad_client_id or not settings.azure_ad_tenant_id:
        raise HTTPException(status_code=503, detail="Azure AD not configured")

    auth_url = _msal_app().get_authorization_request_url(
        scopes=["User.Read"],
        redirect_uri=settings.azure_ad_redirect_uri,
        state="sapphire",
    )
    return {"auth_url": auth_url}


@router.get("/microsoft/exchange", response_model=TokenResponse)
async def microsoft_exchange(
    code: str,
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Exchange an Azure AD authorization code for app JWT tokens.

    Called via fetch() from the frontend /auth/callback page after Microsoft
    redirects the browser there with ?code=...&state=... The redirect_uri is
    the frontend route itself (not an /api/ path) so SWA serves index.html for
    the navigation, and React makes this as a normal XHR/fetch request.
    """
    result = _msal_app().acquire_token_by_authorization_code(
        code,
        scopes=["User.Read"],
        redirect_uri=settings.azure_ad_redirect_uri,
    )
    if "error" in result:
        log.error(
            "msal_exchange_failed",
            error=result.get("error"),
            error_description=result.get("error_description"),
            correlation_id=result.get("correlation_id"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.get("error_description", "Azure AD authentication failed"),
        )

    claims = result.get("id_token_claims", {})
    email = claims.get("preferred_username") or claims.get("email", "")
    name = claims.get("name") or email
    user_oid = claims.get("oid", "")

    if not email:
        raise HTTPException(status_code=400, detail="No email in Azure AD token claims")

    # Validate group membership via Managed Identity → Microsoft Graph
    if settings.azure_ad_group_id and user_oid:
        async_credential = AsyncDefaultAzureCredential()
        try:
            token = await async_credential.get_token("https://graph.microsoft.com/.default")
            async with httpx.AsyncClient() as http:
                r = await http.post(
                    f"https://graph.microsoft.com/v1.0/users/{user_oid}/checkMemberGroups",
                    headers={"Authorization": f"Bearer {token.token}"},
                    json={"groupIds": [settings.azure_ad_group_id]},
                )
            if settings.azure_ad_group_id not in r.json().get("value", []):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: not a member of the Sapphire Users group",
                )
        finally:
            await async_credential.close()

    existing = await db.execute(select(User).where(User.email == email))
    user = existing.scalar_one_or_none()
    if not user:
        user = User(email=email, password_hash="", full_name=name)
        db.add(user)
        await db.flush()

    return auth_service.create_tokens(user_id=str(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for new access + refresh tokens."""
    payload = auth_service.decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Verify user still exists
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    tokens = auth_service.create_tokens(user_id=str(user.id))
    return tokens
