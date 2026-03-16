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

    # ── OAuth: Google ──
    # Covers: AdSense, Trends, Business Profile, YouTube, Analytics,
    #         Search Console, Ads — all under one Google OAuth consent screen
    # Client ID: 501086967643-a96jcc6l0co2a0klqcc2241s14p6qv6s.apps.googleusercontent.com
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Meta ──
    # Covers: Facebook Pages, Instagram, Messenger DMs, Ads
    # App: "SEO James Pro" (Business type) — App ID: 1449449336687986
    # Instagram App: SEO James Pro-IG — ID: 2237350143463367
    # Business Portfolio: Okeke LLC (ID: 1559764275248518)
    # Facebook Page: Okeke LLC (ID: 1003866996143356)
    # Old Business Portfolio: Falls Tech Solutions (ID: 393867682122027)
    # Permissions (Standard access): pages_manage_posts, pages_messaging,
    #   pages_read_engagement, instagram_basic, instagram_manage_insights,
    #   pages_manage_metadata, pages_show_list, read_insights
    # Old Consumer app (deprecated): 26076940461942180
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Microsoft ──
    # Covers: Bing Webmaster Tools, Bing Ads, Microsoft Advertising
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Twitter/X (requires elevated access approval) ──
    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    twitter_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: TikTok (requires app review approval) ──
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: LinkedIn (requires Marketing Developer Platform approval) ──
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Snapchat (requires Snap Kit app approval) ──
    snapchat_client_id: str = ""
    snapchat_client_secret: str = ""
    snapchat_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Reddit (requires app approval for ads/moderation scopes) ──
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_redirect_uri: str = "http://localhost:8000/api/v1/oauth/callback"

    # ── OAuth: Pinterest ──
    # Requires a Pinterest Developer app with "Ads" access + "Organic content" access
    # Scopes: boards:read, boards:write, pins:read, pins:write, user_accounts:read
    pinterest_client_id: str = ""
    pinterest_client_secret: str = ""
    pinterest_redirect_uri: str = "http://localhost:8000/api/v1/platforms/callback/pinterest"

    # ── API Key: Yelp Fusion (pending approval) ──
    yelp_api_key: str = ""

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

    # ── AI Provider (CLI only — uses Claude Max subscription) ──
    provider_mode: str = "cli"  # Only "cli" supported — uses `claude` CLI with Max subscription
    claude_cli_timeout: int = 300  # Seconds before a CLI call times out

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

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _load_from_keyvault(s: "Settings") -> "Settings":
    """Overlay Key Vault secrets on top of settings loaded from .env.

    Only runs if AZURE_KEYVAULT_URL is set. Uses DefaultAzureCredential
    so it works with `az login` locally and Managed Identity in production.
    Secret names map directly to setting names (underscores → hyphens).

    Secrets managed in Key Vault:
      database-url, secret-key, jwt-secret-key, encryption-key
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
