"""
Application settings — loaded from .env via pydantic-settings.
Import anywhere with:  from app.config import settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore old .env vars not in this class
    )

    # ── App ──
    app_name: str = "workforce"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me"
    api_prefix: str = "/api/v1"
    base_dir: str = "."  # Root directory for company/ and businesses/ folders

    # ── Database ──
    database_url: str = "postgresql+asyncpg://automation_user:password@localhost:5432/automation_db"
    database_echo: bool = False

    # ── JWT ──
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # ── Encryption ──
    encryption_key: str = "change-me"

    # ── OAuth: Google (Business Profile + Ads) ──
    # Client ID: 501086967643-a96jcc6l0co2a0klqcc2241s14p6qv6s.apps.googleusercontent.com
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Meta (Facebook Pages, Instagram, Ads) ──
    # App: "SEO James Pro" — App ID: 1449449336687986
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Microsoft (Bing Ads) ──
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── Azure AD (user authentication) ──
    # App registration: "Sapphire" in your Azure AD tenant.
    # Redirect URI to register: http://localhost:5173/auth/callback
    azure_ad_tenant_id: str = ""
    azure_ad_client_id: str = ""
    azure_ad_client_secret: str = ""  # Local dev fallback — prod uses UAMI federated assertion
    azure_ad_redirect_uri: str = "http://localhost:5173/auth/callback"
    # App roles are defined in the Entra app registration — no group IDs needed here.
    # Roles arrive in the JWT token claims automatically when assigned in Azure AD.
    # UAMI client ID (not a secret — safe as env var / Container App config)
    # uami-sapphire-prod: 5f9b9f3d-fde9-4cc4-bd37-59b23ad59503
    uami_client_id: str = ""
    frontend_url: str = "http://localhost:5173"

    # ── OAuth: LinkedIn ──
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── Google AI / Imagen ──
    google_ai_api_key: str = ""

    # ── Applyra ASO ──
    applyra_api_key: str = ""
    applyra_base_url: str = "https://www.applyra.io"

    # ── Redis ──
    # Loaded from Key Vault in production; set in .env for local dev.
    redis_url: str = ""

    # ── Email Delivery ──
    email_provider: str = "log"  # "sendgrid" | "smtp" | "log" (dev mode — prints to console)
    email_from_address: str = "outreach@seojames.io"
    email_reply_to: str = ""
    sendgrid_api_key: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # ── Twilio (bring-your-own-account — stored per-business in connected_accounts) ──
    # Users supply their own Account SID + Auth Token via the Connections page.
    # webhook_base_url lives in phone_settings table (per-business, DB is source of truth).

    # ── AI Provider (Azure AI Foundry) ──
    # Auth: DefaultAzureCredential (az login locally, Managed Identity in production).
    foundry_timeout: int = 120  # Seconds before a Foundry call times out

    # ── Stripe (bring-your-own-account — stored per-business in connected_accounts) ──
    # Users supply their own Stripe Secret Key via the Connections page.
    # Supports: customer creation, invoice generation, products, subscriptions.
    stripe_secret_key: str = ""  # Optional global fallback — per-business keys stored encrypted in DB

    # ── CLI Auth (run these on the server once): ──
    # claude login   → Anthropic (AI employees)
    # gh auth login  → GitHub (repos, issues, PRs, Actions)
    # az login       → Azure (cloud resources, deployments)

    # ── CORS ──
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Azure Key Vault ──
    # Set via AZURE_KEYVAULT_URL env var or Container App config.
    # Empty = skip Key Vault (local dev without vault access).
    azure_keyvault_url: str = ""

    # ── Azure AI Services (OpenAI) ──
    foundry_endpoint: str = "https://ai-sapphire-prod.cognitiveservices.azure.com"
    foundry_default_model: str = "haiku"

    # ── Azure Communication Services ──
    # Resource: acs-sapphire-prod (in rg-sapphire-prod)
    # Auth: connection string (dev + prod); MI used for call automation only
    acs_endpoint: str = ""
    acs_connection_string: str = ""

    # ── Azure Maps ──
    # Resource: maps-sapphire-prod (in rg-sapphire-prod)
    azure_maps_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _load_from_keyvault(s: "Settings") -> "Settings":
    """Overlay Key Vault secrets on top of settings loaded from .env.

    Only runs if AZURE_KEYVAULT_URL is set. Uses DefaultAzureCredential
    (az login locally, system-assigned MI in production). No fallback —
    if Key Vault is configured but unreachable the app will not start.

    azure_ad_client_secret is intentionally absent — auth uses UAMI
    federated identity credentials via msal.UserAssignedManagedIdentity.
    uami_client_id is not a secret and is set as an env var.
    """
    if not s.azure_keyvault_url:
        return s

    from app.core.services.keyvault_service import KeyVaultService
    kv = KeyVaultService(s.azure_keyvault_url)

    overrides = {}
    mappings = {
        # database_url is NOT in Key Vault — per-environment config.
        # Set DATABASE_URL in .env (local) or Container App env vars (production).
        "secret-key": "secret_key",
        "jwt-secret-key": "jwt_secret_key",
        "encryption-key": "encryption_key",
        # Google
        "google-client-id": "google_client_id",
        "google-client-secret": "google_client_secret",
        "google-ai-api-key": "google_ai_api_key",
        # Microsoft / Azure AD
        "microsoft-client-id": "microsoft_client_id",
        "microsoft-client-secret": "microsoft_client_secret",
        "azure-ad-client-id": "azure_ad_client_id",
        "azure-ad-client-secret": "azure_ad_client_secret",
        # Meta
        "meta-app-id": "meta_app_id",
        "meta-app-secret": "meta_app_secret",
        # LinkedIn
        "linkedin-client-id": "linkedin_client_id",
        "linkedin-client-secret": "linkedin_client_secret",
        # Infrastructure
        # acs-connection-string: loaded here for local dev only.
        # In production the Container App MI has Contributor on the ACS resource,
        # so acs_connection_string stays empty and DefaultAzureCredential is used.
        "acs-connection-string": "acs_connection_string",
        "redis-url": "redis_url",
        "applyra-api-key": "applyra_api_key",
        "azure-maps-key": "azure_maps_key",
    }
    # Fetch all secrets in parallel to avoid serial HTTPS round-trips (18 × ~2s = 36s)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    def _fetch(item):
        secret_name, attr = item
        return attr, kv.get(secret_name)

    with ThreadPoolExecutor(max_workers=len(mappings)) as pool:
        futures = {pool.submit(_fetch, item): item for item in mappings.items()}
        for future in as_completed(futures):
            attr, value = future.result()
            if value:
                overrides[attr] = value

    if overrides:
        return s.model_copy(update=overrides)
    return s


settings = _load_from_keyvault(Settings())
