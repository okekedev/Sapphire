"""
OAuth2 service — handles authorization URL generation, token exchange,
credential encryption/storage, and token refresh for all OAuth platforms.

Supports PKCE (Google) and non-PKCE (Meta) flows.
State is stored in Redis (Upstash) with a 10-minute TTL.
"""

import hashlib
import json
import secrets
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.models.connected_account import ConnectedAccount
from app.core.services.encryption_service import EncryptionService

# ---------------------------------------------------------------------------
# Platform OAuth configurations
# ---------------------------------------------------------------------------

PLATFORM_CONFIGS: dict[str, dict] = {
    # ── Google Business Profile ──
    "google_business_profile": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/business.manage"],
        "supports_pkce": True,
        "client_id_setting": "google_client_id",
        "client_secret_setting": "google_client_secret",
        "redirect_uri_setting": "google_redirect_uri",
    },
    # ── Google Ads ──
    "google_ads": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/adwords"],
        "supports_pkce": True,
        "client_id_setting": "google_client_id",
        "client_secret_setting": "google_client_secret",
        "redirect_uri_setting": "google_redirect_uri",
    },
    # ── Meta (Facebook Pages, Instagram, Ads) ──
    # App: "SEO James Pro" — App ID: 1449449336687986
    # Uses Facebook Login for Business with Login Configuration instead of scopes.
    # Config "SEO James User" (User access token) — ID: 1494948712209393
    "facebook": {
        "auth_url": "https://www.facebook.com/v21.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v21.0/oauth/access_token",
        "scopes": [],
        "config_id": "1494948712209393",
        "supports_pkce": False,
        "client_id_setting": "meta_app_id",
        "client_secret_setting": "meta_app_secret",
        "redirect_uri_setting": "meta_redirect_uri",
    },
    # ── Microsoft Bing Ads ──
    "bing": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": [
            "https://ads.microsoft.com/msads.manage",
            "offline_access",
        ],
        "supports_pkce": True,
        "client_id_setting": "microsoft_client_id",
        "client_secret_setting": "microsoft_client_secret",
        "redirect_uri_setting": "microsoft_redirect_uri",
    },
    # ── LinkedIn ──
    "linkedin": {
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["openid", "profile", "email", "w_member_social"],
        "supports_pkce": False,
        "client_id_setting": "linkedin_client_id",
        "client_secret_setting": "linkedin_client_secret",
        "redirect_uri_setting": "linkedin_redirect_uri",
    },
}

SUPPORTED_PLATFORMS = set(PLATFORM_CONFIGS.keys())


class OAuthService:
    """Orchestrates OAuth2 flows for all supported platforms."""

    def __init__(self):
        self.encryption = EncryptionService()

    # ------------------------------------------------------------------
    # 1. Generate authorization URL
    # ------------------------------------------------------------------

    def generate_auth_url(
        self, platform: str, business_id: UUID, department_id: UUID | None = None
    ) -> tuple[str, str, str | None]:
        """
        Build the platform authorization URL.

        Args:
            platform: Platform name (e.g. "google_search_console")
            business_id: Business ID
            department_id: Optional department ID (NULL = shared/business-wide)

        Returns:
            (auth_url, state_token, code_verifier | None)
        """
        if platform not in PLATFORM_CONFIGS:
            raise ValueError(f"Unsupported OAuth platform: {platform}")

        config = PLATFORM_CONFIGS[platform]
        client_id = getattr(settings, config["client_id_setting"])
        redirect_uri = getattr(settings, config["redirect_uri_setting"])

        if not client_id:
            raise ValueError(
                f"Missing {config['client_id_setting']} in settings — "
                f"cannot initiate OAuth for {platform}"
            )

        # State token = encrypted JSON blob
        state_payload = json.dumps({
            "business_id": str(business_id),
            "platform": platform,
            "department_id": str(department_id) if department_id else None,
            "csrf": secrets.token_urlsafe(32),
        })
        state = urlsafe_b64encode(
            self.encryption.encrypt(state_payload)
        ).decode()

        params: dict[str, str] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }

        # Facebook Login for Business uses config_id instead of scopes
        if config.get("config_id"):
            params["config_id"] = config["config_id"]
        else:
            params["scope"] = " ".join(config["scopes"])

        # PKCE (Google platforms)
        code_verifier: str | None = None
        if config.get("supports_pkce"):
            code_verifier = secrets.token_urlsafe(64)
            digest = hashlib.sha256(code_verifier.encode()).digest()
            code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        url = f"{config['auth_url']}?{urlencode(params)}"
        return url, state, code_verifier

    # ------------------------------------------------------------------
    # 2. Decrypt & validate state
    # ------------------------------------------------------------------

    def decrypt_state(self, state: str) -> dict:
        """Decrypt the state parameter back to its payload."""
        from base64 import urlsafe_b64decode

        blob = urlsafe_b64decode(state)
        plaintext = self.encryption.decrypt(blob)
        return json.loads(plaintext)

    # ------------------------------------------------------------------
    # 3. Exchange authorization code for tokens
    # ------------------------------------------------------------------

    async def exchange_code(
        self,
        platform: str,
        code: str,
        code_verifier: str | None = None,
    ) -> dict:
        """
        Exchange an authorization code for access + refresh tokens.

        Returns the raw token response dict from the platform.
        """
        config = PLATFORM_CONFIGS[platform]
        client_id = getattr(settings, config["client_id_setting"])
        client_secret = getattr(settings, config["client_secret_setting"])
        redirect_uri = getattr(settings, config["redirect_uri_setting"])

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier and config.get("supports_pkce"):
            payload["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(config["token_url"], data=payload)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # 4. Store encrypted credentials
    # ------------------------------------------------------------------

    async def store_credentials(
        self,
        db: AsyncSession,
        business_id: UUID,
        platform: str,
        tokens: dict,
        scopes: str | None = None,
        department_id: UUID | None = None,
    ) -> ConnectedAccount:
        """Encrypt tokens and upsert a ConnectedAccount row.

        Args:
            db: Database session
            business_id: Business ID
            platform: Platform name
            tokens: Token dict from OAuth provider
            scopes: OAuth scopes as space-separated string
            department_id: Optional department ID (NULL = shared/business-wide)
        """

        cred_json = json.dumps({
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "token_type": tokens.get("token_type", "Bearer"),
        })
        encrypted = self.encryption.encrypt(cred_json)

        expires_in = tokens.get("expires_in")
        token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            if expires_in
            else None
        )

        # Upsert — if a connection already exists for this business+platform+department, update it
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == platform,
            ConnectedAccount.department_id == department_id,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            account.encrypted_credentials = encrypted
            account.token_expires_at = token_expires_at
            account.scopes = scopes
            account.status = "active"
        else:
            account = ConnectedAccount(
                business_id=business_id,
                platform=platform,
                department_id=department_id,
                auth_method="oauth",
                encrypted_credentials=encrypted,
                scopes=scopes,
                token_expires_at=token_expires_at,
                status="active",
            )
            db.add(account)

        await db.flush()
        return account

    async def store_api_key(
        self,
        db: AsyncSession,
        business_id: UUID,
        platform: str,
        api_key: str,
        department_id: UUID | None = None,
    ) -> ConnectedAccount:
        """Encrypt an API key and upsert a ConnectedAccount row.

        Args:
            db: Database session
            business_id: Business ID
            platform: Platform name (e.g. "ahrefs", "semrush")
            api_key: Plain-text API key to encrypt and store
            department_id: Optional department ID (NULL = shared/business-wide)
        """
        cred_json = json.dumps({"api_key": api_key})
        encrypted = self.encryption.encrypt(cred_json)

        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == platform,
            ConnectedAccount.department_id == department_id,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            account.encrypted_credentials = encrypted
            account.status = "active"
        else:
            account = ConnectedAccount(
                business_id=business_id,
                platform=platform,
                department_id=department_id,
                auth_method="api_key",
                encrypted_credentials=encrypted,
                status="active",
            )
            db.add(account)

        await db.flush()
        return account

    # ------------------------------------------------------------------
    # 5. Retrieve decrypted credentials
    # ------------------------------------------------------------------

    async def get_credentials(
        self, db: AsyncSession, business_id: UUID, platform: str, department_id: UUID | None = None
    ) -> dict | None:
        """Load and decrypt credentials for a connected platform.

        Args:
            db: Database session
            business_id: Business ID
            platform: Platform name
            department_id: Optional department ID (if None, finds ANY active connection for platform)

        Returns:
            Decrypted credentials dict or None
        """
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == platform,
            ConnectedAccount.status == "active",
        )
        if department_id is not None:
            stmt = stmt.where(ConnectedAccount.department_id == department_id)
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return None
        return json.loads(self.encryption.decrypt(account.encrypted_credentials))

    # ------------------------------------------------------------------
    # 6. Refresh an expired token
    # ------------------------------------------------------------------

    async def refresh_token(
        self, db: AsyncSession, business_id: UUID, platform: str, department_id: UUID | None = None
    ) -> dict:
        """Refresh an OAuth token and update the stored credentials.

        Args:
            db: Database session
            business_id: Business ID
            platform: Platform name
            department_id: Optional department ID to identify which connection to refresh
        """
        creds = await self.get_credentials(db, business_id, platform, department_id)
        if not creds or not creds.get("refresh_token"):
            raise ValueError(f"No refresh token available for {platform}")

        config = PLATFORM_CONFIGS[platform]
        client_id = getattr(settings, config["client_id_setting"])
        client_secret = getattr(settings, config["client_secret_setting"])

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(config["token_url"], data=payload)
            resp.raise_for_status()
            new_tokens = resp.json()

        # Google doesn't always return a new refresh_token, keep the old one
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = creds["refresh_token"]

        await self.store_credentials(db, business_id, platform, new_tokens, department_id=department_id)
        return new_tokens

    # ------------------------------------------------------------------
    # 7. Get a valid access token (auto-refresh if expired)
    # ------------------------------------------------------------------

    async def get_valid_access_token(
        self, db: AsyncSession, business_id: UUID, platform: str, department_id: UUID | None = None
    ) -> str:
        """
        Return a valid access token, refreshing automatically if expired.
        This is the main entry point for services that need to call platform APIs.

        Args:
            db: Database session
            business_id: Business ID
            platform: Platform name
            department_id: Optional department ID to find the right connection
        """
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == platform,
            ConnectedAccount.status == "active",
        )
        if department_id is not None:
            stmt = stmt.where(ConnectedAccount.department_id == department_id)
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError(f"No active connection for {platform}")

        # Check if token is about to expire (5-minute buffer)
        needs_refresh = (
            account.token_expires_at is not None
            and account.token_expires_at < datetime.now(timezone.utc) + timedelta(minutes=5)
        )

        if needs_refresh:
            new_tokens = await self.refresh_token(db, business_id, platform, department_id)
            return new_tokens["access_token"]

        creds = json.loads(self.encryption.decrypt(account.encrypted_credentials))
        return creds["access_token"]

    # ------------------------------------------------------------------
    # 8. Disconnect a platform
    # ------------------------------------------------------------------

    async def disconnect(
        self, db: AsyncSession, business_id: UUID, platform: str, department_id: UUID | None = None
    ) -> bool:
        """Mark a platform connection as revoked.

        Args:
            db: Database session
            business_id: Business ID
            platform: Platform name
            department_id: Optional department ID to identify which connection to revoke
        """
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == platform,
            ConnectedAccount.department_id == department_id,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return False
        account.status = "revoked"
        await db.flush()
        return True
