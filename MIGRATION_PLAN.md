# Workforce → Azure Marketplace Migration Plan

## Target Stack

| Layer | Current | Target |
|-------|---------|--------|
| AI Provider | `claude -p` CLI subprocess (Max subscription) | `AnthropicFoundry` SDK → Microsoft Foundry (Haiku 4.5) |
| Backend | Local FastAPI + ngrok tunnel | Azure Container Apps |
| Frontend | Local Vite dev server | Azure Static Web Apps |
| Database | Supabase Postgres | Neon Serverless Postgres (Azure region) |
| Telephony | Twilio (via ngrok webhooks) | Twilio (via Azure Container Apps URL) |
| Tunnel | ngrok (dev-only) | Not needed |

---

## Phase 1: Replace Claude CLI with Anthropic SDK

This is the largest code change. The current `claude_cli_service.py` (1302 lines) spawns `claude -p` as a subprocess. Replace it with the `anthropic` Python SDK calling Claude Haiku via Azure Foundry.

### 1.1 Install SDK

**File:** `requirements.txt`

- ADD: `anthropic` (the standard Anthropic SDK includes `AnthropicFoundry` client built-in)
- ADD: `azure-identity` (for Entra ID auth — `DefaultAzureCredential`)
- REMOVE: `pyngrok` (ngrok tunnel library — only needed for dev, optional to keep)

### 1.2 Add SDK Config Settings

**File:** `app/config.py`

REMOVE these settings (lines 118-119):
```python
provider_mode: str = "cli"
claude_cli_timeout: int = 300
```

ADD these settings:
```python
# Microsoft Foundry (Claude via Azure)
# Auth: either API key or Entra ID (managed identity). For marketplace, use Entra ID.
foundry_api_key: str = ""                      # Azure portal → Keys & Endpoint (optional if using Entra ID)
foundry_resource: str = ""                     # Azure resource name, e.g. "workforce-ai"
                                               # Endpoint becomes: https://{resource}.services.ai.azure.com/anthropic/v1/*
foundry_default_model: str = "claude-haiku-4-5"  # Deployment name in Foundry
foundry_use_entra_id: bool = True              # True = managed identity (marketplace), False = API key (dev)
foundry_timeout: int = 120                     # seconds
```

### 1.2a Foundry SDK Usage Reference

The Anthropic Python SDK has a dedicated `AnthropicFoundry` class. Two auth methods:

**API Key (for development):**
```python
from anthropic import AnthropicFoundry

client = AnthropicFoundry(
    api_key=settings.foundry_api_key,
    resource=settings.foundry_resource,
)
```

**Entra ID / Managed Identity (for marketplace production):**
```python
from anthropic import AnthropicFoundry
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)
client = AnthropicFoundry(
    resource=settings.foundry_resource,
    azure_ad_token_provider=token_provider,
)
```

**Making calls (same API as standard Anthropic SDK):**
```python
message = client.messages.create(
    model="claude-haiku-4-5",   # deployment name from Foundry portal
    max_tokens=4096,
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Hello!"}],
)
response_text = message.content[0].text
```

**Available Foundry models:**
- `claude-opus-4-6`, `claude-opus-4-5`, `claude-opus-4-1`
- `claude-sonnet-4-6`, `claude-sonnet-4-5`
- `claude-haiku-4-5`

**Regions:** East US2, Sweden Central

**Environment variables (auto-read by SDK):**
- `ANTHROPIC_FOUNDRY_API_KEY`
- `ANTHROPIC_FOUNDRY_RESOURCE`
- `ANTHROPIC_FOUNDRY_BASE_URL` (alternative to resource name)

### 1.3 Rewrite claude_cli_service.py → anthropic_service.py

**REPLACE:** `app/core/services/claude_cli_service.py` (1302 lines)
**WITH:** `app/core/services/anthropic_service.py` (~300 lines)

The new service must expose the SAME public interface so callers don't break. Here's what each method becomes:

#### Methods to KEEP (same signature, new implementation):

| Method | What Changes |
|--------|-------------|
| `build_profile_context(business)` | No change — pure string builder, no CLI dependency |
| `call_assistant(business_id, message, db)` | Replace `_run_claude()` subprocess with `client.messages.create()` |
| `call_employee(employee_id, business_id, task, db)` | Same — load system prompt from DB, call SDK instead of subprocess |
| `call_employee_inline(...)` | Same pattern |
| `load_employee_from_db(file_stem, business_id, db)` | No change — pure DB query |
| `build_tool_instructions(business_id)` | No change — pure string builder |
| `parse_employee_model_from_tier(model_tier)` | Update MODEL_MAP values if needed for Foundry model strings |
| `get_provider_status(db, business_id)` | Simplify — just check if API key is configured and valid |
| `startup_check()` | Simplify — ping Foundry endpoint instead of checking CLI binary |

#### Methods to REMOVE (CLI-specific, no longer needed):

| Method | Why |
|--------|-----|
| `_clean_env()` | No subprocess = no environment hacking |
| `_run_claude()` | Replaced by `client.messages.create()` |
| `get_business_token(db, business_id)` | No per-business OAuth tokens — single API key |
| `store_business_token(db, business_id, token)` | No per-business OAuth tokens |
| `mark_token_expired(db, business_id)` | No per-business OAuth tokens |
| `verify_token(token)` | No per-business OAuth tokens |
| `start_login(db, business_id)` | No interactive login flow |
| `set_oauth_token(db, business_id, token)` | No per-business OAuth tokens |
| `check_cli_auth()` | No CLI tools to check |
| `list_employees()` | Reads from filesystem — employees are in DB now |
| `write_employee_file(...)` | Filesystem-based — employees are in DB |
| `delete_employee_file(...)` | Filesystem-based — employees are in DB |

#### Exceptions to KEEP:
- `ClaudeCliError` → rename to `AnthropicServiceError`
- `ClaudeCliNotReady` → rename to `AnthropicServiceNotReady`

#### Exception to REMOVE:
- `ClaudeCliTokenExpired` — no per-business tokens

#### Singleton:
- KEEP: `claude_cli = ClaudeCliService()` → rename to `anthropic_service = AnthropicService()`
- UPDATE all imports across the codebase (see Section 1.4)

#### New core method pattern:

```python
from anthropic import AnthropicFoundry
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from app.config import settings

class AnthropicService:
    def __init__(self):
        if settings.foundry_use_entra_id:
            # Marketplace: uses Azure managed identity (no API key needed)
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default"
            )
            self.client = AnthropicFoundry(
                resource=settings.foundry_resource,
                azure_ad_token_provider=token_provider,
            )
        else:
            # Development: uses API key
            self.client = AnthropicFoundry(
                api_key=settings.foundry_api_key,
                resource=settings.foundry_resource,
            )
        self.default_model = settings.foundry_default_model
        self.timeout = settings.foundry_timeout

    async def _call_model(
        self,
        system_prompt: str,
        message: str,
        model: str | None = None,
    ) -> str:
        """Core method replacing _run_claude() subprocess."""
        response = self.client.messages.create(
            model=model or self.default_model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": message}],
        )
        return response.content[0].text
```

#### Tool access consideration:

The current CLI grants employees tools like `Bash`, `WebSearch`, `WebFetch` via `--tools` flag. The Anthropic SDK doesn't have these built-in. Options:

- **Option A (recommended for marketplace):** Remove tool access entirely. Employees respond based on their system prompt + business context. No code execution, no web browsing. Simpler, safer, cheaper.
- **Option B:** Implement tool_use with the SDK's native tool calling. Define tools as functions the model can call (e.g., search, fetch). More complex but preserves current capability.

Decision needed before implementing. Option A is recommended for initial marketplace launch.

### 1.4 Update All Importers

**12 files import from `claude_cli_service`. Update each:**

| File | Line(s) | Change |
|------|---------|--------|
| `app/core/routers/chat.py` | 30, 170 | `from app.core.services.anthropic_service import anthropic_service, AnthropicServiceError, AnthropicServiceNotReady` |
| `app/core/routers/businesses.py` | 31 | Same import update. Line 640: `anthropic_service.call_assistant()` |
| `app/core/routers/cli.py` | 23 | **REMOVE or REFACTOR entire file** — CLI management endpoints no longer needed (see Phase 2) |
| `app/core/routers/organization.py` | 27 | Lines 222, 270: Remove `write_employee_file()` calls (employees managed in DB, not filesystem) |
| `app/main.py` | 57 | Update startup_check import + call |
| `app/admin/routers/twilio.py` | (import) | Update import, verify usage |
| `app/admin/services/twilio_service.py` | 360 | Update lazy import |
| `app/marketing/services/call_analysis_service.py` | (import) | Update import |
| `app/marketing/services/email_service.py` | (import) | Update import |
| `app/it/routers/terminal.py` | 31 | **FILE BEING REMOVED** — no update needed |
| `app/it/routers/internal_tools.py` | (if present) | Update import — this file is being RELOCATED (see Phase 2) |

### 1.5 Remove CLI Router

**DELETE:** `app/core/routers/cli.py` (161 lines)

This file exposes `/api/v1/cli/status`, `/cli/provider`, `/cli/login`, `/cli/set-token` — all CLI management endpoints. None are needed with the SDK.

**File:** `app/main.py` line 26 — remove `cli` from imports:
```python
# BEFORE
from app.core.routers import auth, businesses, chat, cli, health, ...
# AFTER
from app.core.routers import auth, businesses, chat, health, ...
```

**File:** `app/main.py` line 202 — remove router registration:
```python
# REMOVE this line:
app.include_router(cli.router, prefix=settings.api_prefix)
```

### 1.6 Clean Up connected_accounts

After deploying the SDK, run a DB migration to clean up old CLI tokens:

```sql
-- Remove all claude_cli platform entries (no longer used)
DELETE FROM connected_accounts WHERE platform = 'claude_cli';
```

---

## Phase 2: Remove IT Tab + Relocate internal_tools

The IT tab is a dev-ops panel for local development. Not needed for marketplace.

### 2.1 Remove IT Tab Frontend

**DELETE entire directory:** `frontend/src/it/` (contains `pages/it.tsx` — 746 lines)

**File:** `frontend/src/App.tsx`
- Line 15: REMOVE `import ITPage from "@/it/pages/it";`
- Line 43: REMOVE `<Route path="/it" element={<ITPage />} />`

**File:** `frontend/src/shared/components/layout/main-tabs.tsx`
- Remove the IT entry from `EXTRA_TABS` array (around line 18)
- The entry looks like: `{ to: "/it", icon: Monitor, label: "IT" }`
- Also remove the `Monitor` import from lucide-react if it becomes unused

### 2.2 Remove IT Tab Backend — terminal.py

**DELETE:** `app/it/routers/terminal.py` (408 lines)

This is a WebSocket PTY bridge for running `claude setup-token` interactively. No longer needed.

**File:** `app/main.py`
- Line 34: Remove `terminal` from import: `from app.it.routers import internal_tools, terminal` → `from app.it.routers import internal_tools`
- Line 205: REMOVE `app.include_router(terminal.router, prefix=settings.api_prefix)`

### 2.3 Relocate internal_tools.py

**DO NOT DELETE** `app/it/routers/internal_tools.py` (630 lines).

This file has critical endpoints that AI employees use as tools:
- `GET /tools/available` — platform discovery
- `POST /tools/proxy` — credential-injected API proxy
- `POST /tools/twilio/provision` — buy phone number + create DB record
- `POST /tools/twilio/release` — release number + update DB
- `POST /tools/twilio/sync` — sync DB with Twilio
- `POST /tools/twilio/set-mainline` — set mainline number
- `POST /tools/self-document` — employee self-documentation

**MOVE** this file from `app/it/routers/internal_tools.py` → `app/core/routers/internal_tools.py`

Update `app/main.py`:
```python
# BEFORE
from app.it.routers import internal_tools, terminal
# AFTER
from app.core.routers import internal_tools
```

After moving, the `app/it/` directory can be deleted entirely.

---

## Phase 3: Remove ngrok Infrastructure

ngrok is only needed for tunneling localhost to the internet. Azure Container Apps has its own URL.

### 3.1 Remove ngrok Startup Logic

**File:** `app/main.py` lines 74-161

Remove the entire ngrok auto-reconnect block in the `lifespan()` function. This includes:
- Querying `connected_accounts` for ngrok platform
- Starting tunnel
- Updating `phone_settings.webhook_base_url`
- Configuring Twilio webhooks with tunnel URL

Also remove shutdown logic (lines 165-169):
```python
# REMOVE:
try:
    from app.admin.services.ngrok_service import ngrok_service as _ngrok
    await _ngrok.stop_tunnel()
except Exception:
    pass
```

### 3.2 Remove ngrok Backend Files

**DELETE these files:**
- `app/admin/routers/ngrok.py` — ngrok connect/disconnect/tunnel endpoints
- `app/admin/services/ngrok_service.py` — ngrok tunnel management service

**File:** `app/main.py`
- Line 33: Remove `ngrok` from import: `from app.admin.routers import twilio, ngrok, whatsapp` → `from app.admin.routers import twilio, whatsapp`
- Line 227: REMOVE `app.include_router(ngrok.router, prefix=settings.api_prefix)`

### 3.3 Remove ngrok Frontend Files

**DELETE:** `frontend/src/shared/api/ngrok.ts` (71 lines)

Remove any ngrok references in the IT page (already being deleted) or admin page if present.

### 3.4 Clean Up ngrok connected_accounts

```sql
DELETE FROM connected_accounts WHERE platform = 'ngrok';
```

---

## Phase 4: Remove Unused Backend Platform Configs

### 4.1 Clean Up oauth_service.py

**File:** `app/core/services/oauth_service.py`

The `nextdoor` config (lines 201-209) was already removed from the frontend. Remove it from the backend `PLATFORM_CONFIGS` dict as well.

Also consider removing these if not planning to ship them:
- `snapchat` (lines 171-182) — requires Snap Kit approval, niche
- `reddit` (lines 183-197) — not relevant for service businesses
- `microsoft_outlook` (lines 144-157) — edge case
- `bing` (lines 158-170) — edge case

Keep the frontend-exposed 11 platforms:
- facebook, twitter, linkedin, tiktok, youtube, pinterest (Social)
- google_analytics, google_search_console (Analytics)
- google_business_profile (Listings)
- gmail (Email)
- yelp (API key — Listings)

---

## Phase 5: Dockerfile + Azure Container Apps

### 5.1 Create Dockerfile

**CREATE:** `Dockerfile` in project root

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app/ app/
COPY migrations/ migrations/

# Run
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Key difference from current setup: NO Node.js, NO Claude Code CLI. Just Python + FastAPI + Anthropic SDK.

### 5.2 Create docker-compose.yml (for local dev)

**CREATE:** `docker-compose.yml` in project root

```yaml
version: "3.8"
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL}
```

### 5.3 Azure Container Apps Config

**CREATE:** `infra/main.bicep` (Azure Bicep template for marketplace deployment)

This template should provision:
- Container App Environment
- Container App (backend)
- Environment variables (API keys, DB URL, Twilio creds)

The specific Bicep template depends on Azure Marketplace packaging requirements — research needed.

---

## Phase 6: Azure Static Web Apps (Frontend)

### 6.1 Frontend Build Config

The frontend already builds to static files via `npm run build` → `dist/` folder.

**CREATE:** `frontend/staticwebapp.config.json`

```json
{
  "navigationFallback": {
    "rewrite": "/index.html",
    "exclude": ["/assets/*", "/api/*"]
  },
  "routes": [
    {
      "route": "/api/*",
      "rewrite": "https://<BACKEND_CONTAINER_APP_URL>/api/*"
    }
  ]
}
```

### 6.2 Update Frontend API Base URL

**File:** `frontend/src/shared/api/` — wherever the base URL is configured

Change from `http://localhost:8000` to use an environment variable:
```typescript
const API_BASE = import.meta.env.VITE_API_URL || "/api";
```

In production, the Static Web App proxies `/api/*` to the Container App backend.

---

## Phase 7: Database Migration (Supabase → Neon)

### 7.1 Export from Supabase

```bash
pg_dump --no-owner --no-acl \
  "postgresql://postgres:<password>@<supabase-host>:5432/postgres" \
  > workforce_dump.sql
```

### 7.2 Create Neon Database

- Create Neon project in Azure region (East US or your preference)
- Create database `workforce`
- Note connection string

### 7.3 Import to Neon

```bash
psql "<neon-connection-string>" < workforce_dump.sql
```

### 7.4 Update Connection String

**File:** `.env` (or Azure Container App environment variables)

```
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<neon-host>/<database>?sslmode=require
```

### 7.5 Cleanup Migration

Run after SDK is deployed:

```sql
-- Remove CLI tokens (no longer used)
DELETE FROM connected_accounts WHERE platform = 'claude_cli';

-- Remove ngrok connections (no longer used)
DELETE FROM connected_accounts WHERE platform = 'ngrok';
```

---

## Phase 8: Twilio Webhook Update

### 8.1 Update webhook_base_url

Once the Azure Container App is deployed and has a stable URL:

```sql
UPDATE phone_settings
SET webhook_base_url = 'https://<your-app>.azurecontainerapps.io'
WHERE business_id = '<business_id>';
```

### 8.2 Reconfigure Phone Numbers

The existing Twilio sync job (runs every 15 min via APScheduler) will pick up the new webhook URL and reconfigure all phone numbers. Or trigger manually via the admin page.

---

## Phase 9: Startup Simplification

### 9.1 Simplify main.py lifespan

After removing ngrok and CLI, the `lifespan()` function in `app/main.py` becomes much simpler:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Ensure DB columns
    async with engine.begin() as conn:
        await conn.execute(sa_text(
            "ALTER TABLE departments ADD COLUMN IF NOT EXISTS forward_number VARCHAR(20)"
        ))
        await conn.execute(sa_text(
            "ALTER TABLE departments ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true"
        ))

    # 2. Check Anthropic SDK readiness
    from app.core.services.anthropic_service import anthropic_service
    status = await anthropic_service.startup_check()
    if not status["ready"]:
        _logger.warning(f"⚠️  Anthropic SDK not ready: {status['message']}")

    # 3. Start scheduler + Twilio sync
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    app.state.scheduler = _scheduler
    from app.admin.services.twilio_sync import start_twilio_sync
    await start_twilio_sync(_scheduler)

    yield

    # Shutdown
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)
    await engine.dispose()
```

---

## Execution Order

Recommended order to minimize breakage:

1. **Phase 1** — SDK rewrite (biggest change, most files touched)
2. **Phase 2** — Remove IT tab + relocate internal_tools
3. **Phase 3** — Remove ngrok
4. **Phase 4** — Clean up unused platform configs
5. **Phase 9** — Simplify startup
6. **Phase 5** — Dockerfile + Container Apps
7. **Phase 6** — Static Web Apps for frontend
8. **Phase 7** — Database migration
9. **Phase 8** — Twilio webhook update

Phases 1-5 can be done locally and tested before any infrastructure changes. Phases 6-8 are deployment/infrastructure only.

---

## Files Summary

### Files to CREATE:
- `app/core/services/anthropic_service.py` (~300 lines)
- `Dockerfile`
- `docker-compose.yml`
- `frontend/staticwebapp.config.json`
- `infra/main.bicep` (Azure deployment template)

### Files to DELETE:
- `app/core/services/claude_cli_service.py` (1302 lines)
- `app/core/routers/cli.py` (161 lines)
- `app/it/routers/terminal.py` (408 lines)
- `app/it/` directory (after relocating internal_tools.py)
- `app/admin/routers/ngrok.py`
- `app/admin/services/ngrok_service.py`
- `frontend/src/it/` directory (746 lines)
- `frontend/src/shared/api/ngrok.ts` (71 lines)
- `frontend/src/connections/pages/connections.tsx` (unused — not routed)

### Files to MODIFY:
- `requirements.txt` — add anthropic, optionally remove pyngrok
- `app/config.py` — swap CLI settings for SDK settings
- `app/main.py` — remove CLI/ngrok/terminal imports, simplify lifespan
- `app/core/routers/chat.py` — update imports
- `app/core/routers/businesses.py` — update imports
- `app/core/routers/organization.py` — update imports, remove write_employee_file calls
- `app/admin/routers/twilio.py` — update imports
- `app/admin/services/twilio_service.py` — update imports
- `app/marketing/services/call_analysis_service.py` — update imports
- `app/marketing/services/email_service.py` — update imports
- `app/core/services/oauth_service.py` — remove nextdoor + other unused configs
- `frontend/src/App.tsx` — remove IT route
- `frontend/src/shared/components/layout/main-tabs.tsx` — remove IT tab

### Files to MOVE:
- `app/it/routers/internal_tools.py` → `app/core/routers/internal_tools.py`
