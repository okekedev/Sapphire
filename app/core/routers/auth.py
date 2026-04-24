"""
Authentication routes — registration, login, token refresh, Azure AD SSO.
"""

from datetime import datetime, timedelta, timezone

import httpx
from azure.identity.aio import ManagedIdentityCredential as AsyncManagedIdentityCredential
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
    MeResponse,
)
import structlog
from app.core.services.auth_service import AuthService
from app.config import settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth")
auth_service = AuthService()


async def _get_uami_assertion() -> str:
    """Acquire a client assertion token from UAMI via IMDS (production only)."""
    async with AsyncManagedIdentityCredential(client_id=settings.uami_client_id) as cred:
        token = await cred.get_token("api://AzureADTokenExchange")
    return token.token


async def _get_client_credential():
    """Return the MSAL client_credential dict/string.

    Production (UAMI set + is_production): federated assertion via IMDS — no secret ever stored.
    Local dev: plain client secret loaded from Key Vault via az login.
    """
    if settings.uami_client_id and settings.is_production:
        assertion = await _get_uami_assertion()
        return {"client_assertion": assertion}
    if settings.azure_ad_client_secret:
        return settings.azure_ad_client_secret
    raise HTTPException(
        status_code=503,
        detail="Azure AD not configured: set UAMI_CLIENT_ID (prod) or AZURE_AD_CLIENT_SECRET (local)",
    )


def _msal_app(client_credential):
    """MSAL ConfidentialClientApplication."""
    import msal
    return msal.ConfidentialClientApplication(
        settings.azure_ad_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}",
        client_credential=client_credential,
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

    credential = await _get_client_credential()
    auth_url = _msal_app(credential).get_authorization_request_url(
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

    Azure AD is used for authentication only. Authorization is role-based
    via our own roles + business_member_roles tables.

    First login: user gets global_admin if no roles in token (local dev),
    otherwise gets the matching system role(s) from the Azure AD claim.

    Azure AD role claim → system role mapping:
      Admin      → global_admin
      Sales      → sales_executive
      Marketing  → marketing_manager
      Billing    → billing_manager
      Operations → ops_manager
    """
    from app.core.models.business import Business, BusinessMember
    from app.core.models.role import Role, BusinessMemberRole

    # Azure AD app role → system role name(s)
    AZURE_ROLE_MAP: dict[str, list[str]] = {
        "Admin":      ["global_admin"],
        "Sales":      ["sales_executive"],
        "Marketing":  ["marketing_manager"],
        "Billing":    ["billing_manager"],
        "Operations": ["ops_manager"],
    }

    credential = await _get_client_credential()
    result = _msal_app(credential).acquire_token_by_authorization_code(
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
    azure_roles: list[str] = claims.get("roles", [])

    if not email:
        raise HTTPException(status_code=400, detail="No email in Azure AD token claims")

    # ── Derive system role names from Azure AD claims ──
    # No roles in token = local dev or app roles not configured → global_admin
    system_role_names: list[str] = []
    is_owner = False

    if azure_roles:
        seen: set[str] = set()
        for ar in azure_roles:
            for sr in AZURE_ROLE_MAP.get(ar, []):
                if sr not in seen:
                    system_role_names.append(sr)
                    seen.add(sr)
        if not system_role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: your account has no recognised Sapphire roles",
            )
        is_owner = "global_admin" in system_role_names
    else:
        system_role_names = ["global_admin"]
        is_owner = True

    # ── Find or create user ──
    existing = await db.execute(select(User).where(User.email == email))
    user = existing.scalar_one_or_none()
    if not user:
        user = User(email=email, password_hash="", full_name=name)
        db.add(user)
        await db.flush()
    elif not user.full_name and name:
        user.full_name = name

    # ── Load system roles by name ──
    roles_result = await db.execute(
        select(Role).where(Role.name.in_(system_role_names), Role.business_id.is_(None))
    )
    role_objs = {r.name: r for r in roles_result.scalars().all()}

    # ── Sync business_members + role assignments for every business ──
    all_businesses = await db.execute(select(Business))
    businesses = all_businesses.scalars().all()

    if businesses:
        existing_result = await db.execute(
            select(BusinessMember).where(
                BusinessMember.user_id == user.id,
                BusinessMember.business_id.in_([b.id for b in businesses]),
            )
        )
        existing_map = {m.business_id: m for m in existing_result.scalars().all()}

        for biz in businesses:
            member = existing_map.get(biz.id)
            if not member:
                member = BusinessMember(
                    business_id=biz.id,
                    user_id=user.id,
                    is_owner=is_owner,
                )
                db.add(member)
                await db.flush()  # get member.id
            else:
                member.is_owner = is_owner

            # Sync roles: remove old, add new system roles
            existing_bmr = await db.execute(
                select(BusinessMemberRole).where(
                    BusinessMemberRole.member_id == member.id
                )
            )
            existing_role_ids = {r.role_id for r in existing_bmr.scalars().all()}
            target_role_ids = {role_objs[n].id for n in system_role_names if n in role_objs}

            for role_id in target_role_ids - existing_role_ids:
                db.add(BusinessMemberRole(member_id=member.id, role_id=role_id))

    await db.flush()
    return auth_service.create_tokens(user_id=str(user.id))


@router.get("/me", response_model=MeResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    user_id=Depends(auth_service.get_current_user_id_dep),
):
    """Return the current user's profile, roles, and permissions for a given business."""
    from app.core.models.business import BusinessMember
    from app.core.models.role import Role, BusinessMemberRole
    from uuid import UUID
    from fastapi import Query

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get roles + permissions across all businesses this user belongs to
    roles_result = await db.execute(
        select(Role.name, Role.permissions)
        .join(BusinessMemberRole, BusinessMemberRole.role_id == Role.id)
        .join(BusinessMember, BusinessMember.id == BusinessMemberRole.member_id)
        .where(BusinessMember.user_id == user_id)
        .distinct()
    )
    role_names: list[str] = []
    all_permissions: set[str] = set()
    for name, perms in roles_result.all():
        role_names.append(name)
        if "*" in perms:
            from app.core.models.role import ALL_PERMISSIONS
            all_permissions = ALL_PERMISSIONS | {"*"}
        else:
            all_permissions.update(perms)

    return MeResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        roles=role_names,
        permissions=sorted(all_permissions),
    )


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
