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
    # Group: "Sapphire Users" — only members can sign in.
    # Redirect URI to register: http://localhost:8000/api/v1/auth/microsoft/callback
    azure_ad_tenant_id: str = ""
    azure_ad_client_id: str = ""
    # No client secret — auth uses DefaultAzureCredential (federated identity credentials).
    # Managed Identity in production, az login locally. Both registered on the app registration.
    azure_ad_group_id: str = ""  # Object ID of "Sapphire Users" group; empty = skip group check
    azure_ad_redirect_uri: str = "http://localhost:8000/api/v1/auth/microsoft/callback"
    frontend_url: str = "http://localhost:5173"

    # ── OAuth: LinkedIn ──
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

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
    azure_keyvault_url: str = "https://kv-sapphire-okeke.vault.azure.net"

    # ── Azure AI Foundry ──
    foundry_endpoint: str = "https://ai-sapphire-prod.services.ai.azure.com"
    foundry_default_model: str = "claude-haiku-4-5"
    # JSON map of agent name → Foundry agent ID, stored as a single Key Vault secret.
    # Set by deploy_agents.py after first deployment. Example:
    # {"grace":"asst_abc","ivy":"asst_def","quinn":"asst_ghi","luna":"asst_jkl","morgan":"asst_mno","riley":"asst_pqr"}
    foundry_agent_ids: str = "{}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _load_from_keyvault(s: "Settings") -> "Settings":
    """Overlay Key Vault secrets on top of settings loaded from .env.

    Only runs if AZURE_KEYVAULT_URL is set. Uses DefaultAzureCredential
    so it works with `az login` locally and Managed Identity in production.
    Secret names map directly to setting names (underscores → hyphens).

    Secrets managed in Key Vault:
      database-url, secret-key, jwt-secret-key, encryption-key,
      foundry-agent-ids, google-client-id/secret, microsoft-client-id/secret,
      meta-app-id/secret, linkedin-client-id/secret
    """
    if not s.azure_keyvault_url:
        return s

    try:
        from app.core.services.keyvault_service import KeyVaultService
        kv = KeyVaultService(s.azure_keyvault_url)

        overrides = {}
        mappings = {
            "database-url": "database_url",
            "secret-key": "secret_key",
            "jwt-secret-key": "jwt_secret_key",
            "encryption-key": "encryption_key",
            "foundry-agent-ids": "foundry_agent_ids",
            "google-client-id": "google_client_id",
            "google-client-secret": "google_client_secret",
            "microsoft-client-id": "microsoft_client_id",
            "microsoft-client-secret": "microsoft_client_secret",
            "meta-app-id": "meta_app_id",
            "meta-app-secret": "meta_app_secret",
            "linkedin-client-id": "linkedin_client_id",
            "linkedin-client-secret": "linkedin_client_secret",
        }
        for secret_name, attr in mappings.items():
            value = kv.get(secret_name)
            if value:
                overrides[attr] = value

        if overrides:
            return s.model_copy(update=overrides)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Key Vault unavailable, using .env values: {e}")

    return s


settings = _load_from_keyvault(Settings())
