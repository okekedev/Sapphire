"""
Claude CLI Service — Invokes employees as Claude CLI agents.

Authentication is per-business: each business stores its own
CLAUDE_CODE_OAUTH_TOKEN (encrypted) in the connected_accounts table.
When making CLI calls, the token is loaded from the DB and injected
into the subprocess environment.

Each employee is a Claude CLI call with:
  1. Their system prompt from the DB (required)
  2. The business profile from the DB (who they're working for)
  3. The task description as the message (what to do now)

Usage:
    from app.core.services.claude_cli_service import claude_cli

    # Workflow call (full context + execution rules):
    result = await claude_cli.call_employee(
        employee_id="marcus_director_of_seo",
        business_id=uuid,
        task="Analyze the current SEO baseline for this business",
        db=session,
    )

    # Quick assistant call (onboarding, main chat):
    result = await claude_cli.call_assistant(
        business_id=uuid,
        message="Hello, help me with my business",
        db=session,
    )
"""

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.models.connected_account import ConnectedAccount
from app.core.services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)

# Map employee model names → Claude CLI model strings
MODEL_MAP: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}

# Default model if none specified in the employee file
DEFAULT_MODEL = "haiku"


def build_profile_context(business) -> str:
    """Build a profile context string from a Business object's dedicated columns."""
    parts = []
    if business.description:
        parts.append(f"## About\n{business.description}")
    if business.services:
        parts.append(f"## Services & Products\n{business.services}")
    if business.target_audience:
        parts.append(f"## Target Audience\n{business.target_audience}")
    if business.online_presence:
        parts.append(f"## Online Presence\n{business.online_presence}")
    if business.brand_voice:
        parts.append(f"## Brand Voice & Tone\n{business.brand_voice}")
    if business.goals:
        parts.append(f"## Goals & Priorities\n{business.goals}")
    if business.competitive_landscape:
        parts.append(f"## Competitive Landscape\n{business.competitive_landscape}")
    return "\n\n".join(parts)


class ClaudeCliError(Exception):
    """Raised when a Claude CLI call fails."""
    pass


class ClaudeCliNotReady(ClaudeCliError):
    """Raised when Claude CLI is not installed or not authenticated."""
    pass


class ClaudeCliTokenExpired(ClaudeCliError):
    """Raised when the stored OAuth token is invalid or expired (401)."""
    pass


class ClaudeCliService:
    """Executes Claude CLI to invoke employee agents with business context."""

    def __init__(self):
        self.company_path = Path(settings.base_dir) / "company"
        self.businesses_path = Path(settings.base_dir) / "businesses"
        self.timeout = settings.claude_cli_timeout
        self.encryption = EncryptionService()
        # CLI readiness state (set by startup check)
        self._cli_installed: bool = False
        self._cli_version: str = ""
        self._startup_checked: bool = False

    # ── Environment Helpers ──

    @staticmethod
    def _clean_env(oauth_token: Optional[str] = None) -> dict:
        """
        Return a copy of os.environ without CLAUDECODE, optionally
        injecting a per-business CLAUDE_CODE_OAUTH_TOKEN.

        Claude CLI refuses to run inside a Claude Code session
        (CLAUDECODE=1). Unsetting it lets our subprocess calls work
        even if the server was launched from within Claude Code.
        """
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        if oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        return env

    # ── Per-Business Token Management ──

    async def get_business_token(
        self, db: AsyncSession, business_id: UUID
    ) -> Optional[str]:
        """
        Load and decrypt the Claude CLI OAuth token for a business.
        Returns the plaintext token string, or None if not connected.

        Claude CLI is a shared service (department_id=NULL).
        """
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == "claude_cli",
            ConnectedAccount.status == "active",
            ConnectedAccount.department_id == None,  # Shared service
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return None
        try:
            creds = json.loads(self.encryption.decrypt(account.encrypted_credentials))
            return creds.get("oauth_token")
        except Exception as e:
            logger.error(f"Failed to decrypt Claude token for business {business_id}: {e}")
            return None

    async def store_business_token(
        self, db: AsyncSession, business_id: UUID, token: str
    ) -> ConnectedAccount:
        """
        Encrypt and store (upsert) a Claude CLI OAuth token for a business.

        Claude CLI is a shared service (department_id=NULL).
        """
        logger.info(f"[ClaudeCLI] Storing token for business {business_id} (token length: {len(token)})")

        cred_json = json.dumps({"oauth_token": token})
        encrypted = self.encryption.encrypt(cred_json)
        logger.debug(f"[ClaudeCLI] Token encrypted (encrypted length: {len(encrypted)})")

        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == "claude_cli",
            ConnectedAccount.department_id == None,  # Shared service
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            logger.info(f"[ClaudeCLI] Updating existing ConnectedAccount (id={account.id}) for business {business_id}")
            account.encrypted_credentials = encrypted
            account.status = "active"
            account.token_expires_at = None  # Long-lived token
        else:
            logger.info(f"[ClaudeCLI] Creating new ConnectedAccount for business {business_id}")
            account = ConnectedAccount(
                business_id=business_id,
                platform="claude_cli",
                department_id=None,  # Shared service
                auth_method="oauth_token",
                encrypted_credentials=encrypted,
                status="active",
            )
            db.add(account)

        await db.flush()
        logger.info(f"[ClaudeCLI] ✓ Token stored successfully (account id={account.id}, status={account.status})")
        return account

    async def mark_token_expired(
        self, db: AsyncSession, business_id: UUID
    ) -> None:
        """
        Mark the stored CLI token as expired in the DB.
        Called when a 401 is detected during a CLI call so the
        provider status reflects the real state.

        Claude CLI is a shared service (department_id=NULL).
        """
        stmt = (
            update(ConnectedAccount)
            .where(
                ConnectedAccount.business_id == business_id,
                ConnectedAccount.platform == "claude_cli",
                ConnectedAccount.status == "active",
                ConnectedAccount.department_id == None,  # Shared service
            )
            .values(status="expired")
        )
        await db.execute(stmt)
        await db.flush()
        logger.info(f"Marked CLI token as expired for business {business_id}")

    async def verify_token(self, token: str) -> bool:
        """
        Verify a Claude CLI token works by making a test call.
        Returns True if authenticated, False otherwise.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", "respond with OK",
                "--max-budget-usd", "0.01",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._clean_env(oauth_token=token),
            )
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            return proc.returncode == 0
        except Exception:
            return False

    # ── Startup Validation ──

    async def startup_check(self) -> dict:
        """
        Run at server startup to verify Claude CLI is installed.
        Authentication is now per-business (stored in DB), so we only
        check that the CLI binary is available.
        """
        status = {
            "installed": False,
            "version": "",
            "message": "",
        }

        # 1. Check if claude is on PATH
        claude_path = shutil.which("claude")
        if not claude_path:
            status["message"] = (
                "Claude CLI not found on PATH. "
                "Install with: npm install -g @anthropic-ai/claude-code"
            )
            logger.warning(f"[CLI Startup] {status['message']}")
            self._startup_checked = True
            return status

        status["installed"] = True
        self._cli_installed = True

        # 2. Get version
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._clean_env(),
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode == 0:
                status["version"] = stdout.decode().strip()
                self._cli_version = status["version"]
        except Exception as e:
            logger.warning(f"[CLI Startup] Could not get version: {e}")

        status["message"] = "Claude CLI is installed (auth is per-business)"
        logger.info(
            f"[CLI Startup] CLI installed "
            f"(version: {status['version']}). "
            f"Auth is per-business via connected_accounts."
        )

        self._startup_checked = True
        return status

    # ── Login Flow (called from /api/v1/cli/login) ──

    async def start_login(
        self, db: AsyncSession, business_id: UUID
    ) -> dict:
        """
        Check auth status for a business and return instructions.

        If the business already has a valid token, returns immediately.
        Otherwise, returns instructions for the user to paste a token.
        """
        if not self._cli_installed:
            return {
                "status": "error",
                "message": "Claude CLI is not installed on the server. "
                           "Install with: npm install -g @anthropic-ai/claude-code",
            }

        # Check if this business already has a token
        token = await self.get_business_token(db, business_id)
        if token:
            # Verify it still works
            if await self.verify_token(token):
                return {"status": "already_authenticated"}
            else:
                # Token expired or invalid — prompt for a new one
                return {
                    "status": "token_required",
                    "message": "Your saved Claude token has expired.",
                    "instructions": (
                        "Your previous token is no longer valid. "
                        "Generate a new one by running 'claude setup-token' on any machine "
                        "with Claude Code installed, then paste it here."
                    ),
                }

        # No token stored — prompt for one
        return {
            "status": "token_required",
            "message": "Claude CLI needs authentication.",
            "instructions": (
                "Generate a token by running 'claude setup-token' on any machine "
                "with Claude Code installed, then paste it here. "
                "This token works with your Claude Max subscription."
            ),
        }

    async def set_oauth_token(
        self, db: AsyncSession, business_id: UUID, token: str
    ) -> dict:
        """
        Verify a Claude OAuth token and store it encrypted in the DB
        for the given business.

        The user generates a long-lived token via `claude setup-token`
        on any machine, pastes it into the UI, and we verify + store it.
        """
        if not token or not token.strip():
            return {"status": "error", "message": "Token cannot be empty."}

        token = token.strip()

        # Verify it works with a test call
        if await self.verify_token(token):
            # Store encrypted in DB
            await self.store_business_token(db, business_id, token)
            logger.info(f"[CLI Token] Token verified and stored for business {business_id}")
            return {
                "status": "authenticated",
                "message": "Claude CLI is now connected!",
            }
        else:
            logger.warning(f"[CLI Token] Token verification failed for business {business_id}")
            return {
                "status": "error",
                "message": "Token verification failed. Please check the token and try again.",
            }

    async def get_provider_status(
        self, db: Optional[AsyncSession] = None, business_id: Optional[UUID] = None
    ) -> dict:
        """
        Return current CLI readiness state for a business.
        If db and business_id are provided, checks if the business has
        a stored token. Otherwise returns just CLI installation status.
        """
        if not self._startup_checked:
            return {
                "ready": False,
                "installed": False,
                "authenticated": False,
                "version": "",
                "message": "Startup check has not run yet",
            }

        has_token = False
        if db and business_id:
            token = await self.get_business_token(db, business_id)
            has_token = token is not None

        return {
            "ready": self._cli_installed and has_token,
            "installed": self._cli_installed,
            "authenticated": has_token,
            "version": self._cli_version,
            "message": (
                "Claude CLI is ready"
                if self._cli_installed and has_token
                else (
                    "Claude CLI not installed — run: npm install -g @anthropic-ai/claude-code"
                    if not self._cli_installed
                    else "Connect your Claude account to get started"
                )
            ),
        }

    def parse_employee_model_from_tier(self, model_tier: str) -> str:
        """
        Convert model_tier string ('opus', 'sonnet', 'haiku') to Claude CLI
        model string. Used when loading from DB where model_tier is a column.
        """
        return MODEL_MAP.get(model_tier.lower(), MODEL_MAP[DEFAULT_MODEL])

    async def load_employee_from_db(
        self,
        file_stem: str,
        business_id: UUID,
        db: AsyncSession,
    ) -> tuple:
        """
        Load employee system_prompt from DB (primary runtime path).

        Tries business-scoped employee first, falls back to global template
        (business_id=NULL). Returns (Employee, system_prompt_text).

        Raises ClaudeCliError if employee not found in either scope.
        """
        from app.core.models.organization import Employee

        # Business-scoped first, then global (NULL sorts after UUIDs in DESC)
        stmt = (
            select(Employee)
            .where(
                Employee.file_stem == file_stem,
                Employee.status == "active",
            )
            .where(
                (Employee.business_id == business_id)
                | (Employee.business_id.is_(None))
            )
            .order_by(Employee.business_id.desc())  # non-null (business) first
        )
        result = await db.execute(stmt)
        employee = result.scalars().first()

        if not employee:
            raise ClaudeCliError(
                f"Employee '{file_stem}' not found in DB for business {business_id}"
            )

        logger.info(
            f"Loaded {file_stem} from DB "
            f"(scope={'business' if employee.business_id else 'global'}, "
            f"model_tier={employee.model_tier})"
        )

        return employee, employee.system_prompt

    def get_business_profile_path(self, business_id: UUID) -> Path:
        """Get the path to a business's profile.md."""
        return self.businesses_path / str(business_id) / "profile.md"

    # ── Internal: Run Claude CLI ──

    async def _run_claude(
        self,
        system_prompt: str,
        message: str,
        label: str = "Claude CLI",
        model: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        business_id: Optional[UUID] = None,
        allowed_tools: Optional[list[str]] = None,
    ) -> str:
        """
        Run `claude --print` with the given system prompt and message.

        Auth: If db + business_id are provided, loads the business's
        encrypted CLAUDE_CODE_OAUTH_TOKEN from the DB and injects it
        into the subprocess environment. Falls back to whatever auth
        the local CLI session has if no business token is available.

        Args:
            model: Claude model string (e.g. "claude-sonnet-4-6").
            db: Async DB session (needed for per-business token lookup).
            business_id: Business UUID (needed for per-business token lookup).
            allowed_tools: List of tools to enable (e.g. ["WebSearch", "WebFetch"]).
        """
        if self._startup_checked and not self._cli_installed:
            raise ClaudeCliNotReady(
                "Claude CLI is not installed. "
                "Run: npm install -g @anthropic-ai/claude-code"
            )

        # Load per-business token from DB
        oauth_token: Optional[str] = None
        if db and business_id:
            logger.debug(f"[ClaudeCLI] Looking up token for business {business_id}")
            oauth_token = await self.get_business_token(db, business_id)
            if not oauth_token:
                logger.warning(f"[ClaudeCLI] No token found for business {business_id}")
                raise ClaudeCliNotReady(
                    "No Claude token configured for this business. "
                    "Please connect Claude in the setup banner."
                )
            logger.info(f"[ClaudeCLI] Using business token for {business_id} (length: {len(oauth_token)})")

        # Combine system prompt and message
        full_prompt = f"{system_prompt}\n\n---\n\n{message}"

        cmd = [
            "claude",
            "-p",
            full_prompt,  # Prompt must come right after -p
        ]

        if model:
            cmd.extend(["--model", model])

        if allowed_tools:
            cmd.extend(["--tools", ",".join(allowed_tools)])
            # Skip permission prompts since we're pre-approving tools
            cmd.extend(["--dangerously-skip-permissions"])

        # No budget limits - using Claude Max subscription
        cmd.extend(["--max-budget-usd", "999999"])

        logger.info(f"{label}: sending ({len(message)} chars)")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._clean_env(oauth_token=oauth_token),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise ClaudeCliError(f"{label} timed out after {self.timeout}s")

            if process.returncode != 0:
                stderr_text = stderr.decode().strip() if stderr else ""
                stdout_text = stdout.decode().strip() if stdout else ""
                error_text = stderr_text or stdout_text or "Unknown error"

                # Log both for debugging
                logger.error(f"{label} failed with exit code {process.returncode}")
                logger.error(f"  stdout: {stdout_text[:500]}")
                logger.error(f"  stderr: {stderr_text[:500]}")

                # Detect expired/invalid token (401 errors)
                if any(kw in error_text.lower() for kw in [
                    "401", "invalid bearer token", "invalid.*token",
                    "token expired", "expired token",
                ]):
                    logger.warning(
                        f"[ClaudeCLI] ✗ Token expired/invalid for business {business_id}. "
                        f"Error: {error_text[:200]}"
                    )
                    # Mark the token as expired in DB so provider status reflects reality
                    if db and business_id:
                        try:
                            await self.mark_token_expired(db, business_id)
                            logger.info(f"[ClaudeCLI] Marked token as expired in DB for business {business_id}")
                        except Exception as mark_err:
                            logger.error(f"[ClaudeCLI] Failed to mark token expired: {mark_err}")
                    raise ClaudeCliTokenExpired(
                        f"Claude CLI token is expired or invalid. "
                        f"Please reconnect Claude in Connections.\n"
                        f"Detail: {error_text}"
                    )

                # Detect other auth issues (not installed, not logged in)
                if any(kw in error_text.lower() for kw in [
                    "not authenticated", "login", "unauthorized", "auth",
                    "credentials", "please run /login",
                ]):
                    raise ClaudeCliNotReady(
                        f"Claude CLI authentication failed. "
                        f"Please reconnect Claude in Connections.\n"
                        f"Detail: {error_text}"
                    )

                raise ClaudeCliError(
                    f"{label} failed (exit {process.returncode}): {error_text}"
                )

            response = stdout.decode().strip()
            if not response:
                raise ClaudeCliError(f"{label} returned empty response")

            logger.info(f"{label}: completed ({len(response)} chars)")
            return response

        except (ClaudeCliError, ClaudeCliNotReady, ClaudeCliTokenExpired):
            raise
        except Exception as e:
            raise ClaudeCliError(f"{label} call failed: {str(e)}")

    # ── Core Execution ──

    # Default tools granted to all employees (read-only research tools)
    DEFAULT_EMPLOYEE_TOOLS = ["WebSearch", "WebFetch"]

    # Tools for employees that need platform API access (includes Bash for curl)
    PLATFORM_EMPLOYEE_TOOLS = ["Bash", "WebSearch", "WebFetch"]

    # Internal API base URL (employees call our backend via curl)
    INTERNAL_API_BASE = "http://localhost:8000/api/v1/tools"

    @staticmethod
    def build_tool_instructions(business_id: UUID) -> str:
        """
        Build tool usage instructions injected into employee prompts.

        Employees use a generic credential proxy to call any platform API.
        They discover connected platforms, research current API docs via
        WebSearch, and route requests through the proxy which injects auth.

        Dedicated endpoints exist only for operations with DB side effects:
        - Twilio provision/release (creates/updates BusinessPhoneLine records)
        - GitHub push-site (multi-step git commit)
        """
        from app.config import settings as app_settings
        base = ClaudeCliService.INTERNAL_API_BASE
        bid = str(business_id)

        # Build psql connection string from DATABASE_URL (strip asyncpg driver prefix)
        db_url = app_settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

        return f"""## Platform API Access

You have Bash tool access to call external platform APIs through our credential proxy.
Authentication is handled automatically — you never need API keys or tokens.
These are REAL operations — they create real resources, post real content, and spend real money.

### Step 1: Discover Connected Platforms

```bash
curl -s "{base}/available?business_id={bid}"
```

Returns which platforms this business has connected, with base URLs and documentation hints.

### Step 2: Research the API

Use **WebSearch** to find the current API documentation for the platform you need.
For example, search "Stripe REST API create customer" or "Facebook Graph API post to page".
This ensures you always use the latest endpoints and parameters.

### Step 3: Execute via Proxy

```bash
curl -s -X POST {base}/proxy \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","platform":"stripe","method":"POST","url":"https://api.stripe.com/v1/customers","headers":{{"Content-Type":"application/x-www-form-urlencoded"}},"body":"name=John+Doe&email=john@example.com"}}'
```

The proxy injects the stored credentials and forwards your request. You get back the raw API response.

**Parameters:**
- `platform` — platform name from discovery (e.g. "stripe", "facebook", "twilio", "google_analytics")
- `method` — HTTP method (GET, POST, PUT, PATCH, DELETE)
- `url` — full API URL from the platform's documentation
- `headers` — any extra headers (Content-Type, etc.)
- `body` — request body as a string (JSON or form-encoded, depending on the API)

### Dedicated Endpoints (DB Side Effects)

These operations modify our internal database, so they use dedicated endpoints instead of the proxy:

**Twilio — Provision a tracking number:**
```bash
curl -s -X POST {base}/twilio/provision \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","phone_number":"+19401234567","campaign_name":"Main Line","channel":"direct"}}'
```

**Twilio — Release a tracking number:**
```bash
curl -s -X POST {base}/twilio/release \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","number_sid":"PNXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"}}'
```

**Twilio — Set mainline number (registers in DB + updates Twilio credentials):**
```bash
curl -s -X POST {base}/twilio/set-mainline \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","phone_number":"+19401234567","friendly_name":"Mainline"}}'
```

**Phone Lines — Create (registers a number in the DB, auto-configures webhooks):**
```bash
curl -s -X POST "http://localhost:8000/api/v1/phone-lines?business_id={bid}" \\
  -H "Content-Type: application/json" \\
  -d '{{"twilio_number":"+19401234567","campaign_name":"Mainline","friendly_name":"Mainline","line_type":"mainline"}}'
```

**Phone Lines — List all:**
```bash
curl -s "http://localhost:8000/api/v1/phone-lines?business_id={bid}"
```

**Phone Settings — Read current settings (greeting, voice, hold, recording, departments):**
```bash
curl -s "http://localhost:8000/api/v1/tracking-routing/settings?business_id={bid}"
```

**Phone Settings — Update settings (partial update, only include fields to change):**
```bash
curl -s -X PUT "http://localhost:8000/api/v1/tracking-routing/settings?business_id={bid}" \\
  -H "Content-Type: application/json" \\
  -d '{{"greeting_text":"Hi, you'\''ve reached ...","voice_name":"Polly.Joanna-Neural","hold_message":"Please hold...","recording_enabled":true,"transcription_enabled":true,"forward_all_calls":false,"default_forward_number":"+1234567890","ring_timeout_s":30,"business_hours_start":"09:00","business_hours_end":"17:00","business_timezone":"America/Chicago","after_hours_enabled":true,"after_hours_message":"We are currently closed...","departments_config":[{{"name":"Sales","department_id":"UUID","forward_number":"+1234567890","enabled":true}}]}}'
```
Available voice options: Polly.Joanna-Neural, Polly.Matthew-Neural, Google.en-US-Chirp3-HD-Aoede, Google.en-US-Chirp3-HD-Leda, Google.en-US-Chirp3-HD-Charon, Google.en-US-Chirp3-HD-Puck

**Phone Settings fields:**
- `forward_all_calls` — When true, all inbound calls skip IVR and forward directly to default_forward_number. When false, calls go through IVR greeting → AI routing → department forwarding.
- `default_forward_number` — Fallback number. Required when forward_all_calls is true.
- `business_hours_start/end` — "HH:MM" format (e.g. "09:00", "17:00"). Required to enable after_hours.
- `business_timezone` — IANA timezone (e.g. "America/Chicago", "America/New_York").
- `after_hours_enabled` — Requires business hours AND after_hours_message to be set.
- `departments_config` — Array of department routing rules. Each needs name, department_id, forward_number, enabled.

**GitHub — Push site files (Azure SWA auto-deploys):**
```bash
curl -s -X POST {base}/github/push-site \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","project_name":"joes-lawn-care","files":{{"index.html":"<html>...</html>"}}}}'
```

### Self-Documentation

If you learn something genuinely new during this task (API quirks, better approaches,
business-specific patterns), check your "Learned Notes" section first — only add
what you don't already know:

```bash
curl -s -X POST {base}/self-document \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","employee_id":"YOUR_FILE_STEM","note":"What you learned (1-2 sentences)"}}'
```

Don't document every run — only genuinely new insights that would help next time.

### Direct Database Access

You have direct read/write access to the PostgreSQL database. Use psql if available, otherwise use python3:

```bash
psql "{db_url}" -c "SELECT id, twilio_number, line_type FROM business_phone_lines WHERE business_id='{bid}';"
```

If psql is not installed, use python3:
```bash
python3 -c "
import psycopg2
conn = psycopg2.connect('{db_url}')
cur = conn.cursor()
cur.execute(\"SELECT id, twilio_number, line_type FROM business_phone_lines WHERE business_id='{bid}'\")
for row in cur.fetchall(): print(row)
conn.close()
"
```

**Key tables:**
- `businesses` — business profiles (description, services, target_audience, etc.)
- `business_phone_lines` — phone numbers (twilio_number, line_type, campaign_name, friendly_name, active)
- `phone_settings` — IVR config (greeting_text, voice_name, hold_message, default_forward_number)
- `departments` — department routing (name, forward_number, enabled, twilio_number)
- `employees` — AI employees (name, system_prompt, department_id, model_tier)
- `interactions` — call/email/chat records (type, contact_id, metadata_)
- `contacts` — CRM contacts (full_name, phone, email, status)
- `connected_accounts` — platform credentials (platform, status, encrypted_credentials)

**Common operations:**
- Insert a mainline phone line: `INSERT INTO business_phone_lines (business_id, twilio_number, friendly_name, campaign_name, line_type, active) VALUES ('{bid}', '+19401234567', 'Mainline', 'Mainline', 'mainline', true);`
- Update phone settings: `UPDATE phone_settings SET default_forward_number='+19401234567' WHERE business_id='{bid}';`
- Read departments: `SELECT id, name, forward_number, enabled FROM departments WHERE business_id IS NULL ORDER BY display_order;`

Prefer the REST API endpoints when they exist (they handle webhooks and side effects).
Fall back to direct SQL for reads or when no endpoint covers your need.

### Rules
- Always discover connected platforms first before making API calls
- Use WebSearch to find current API docs — don't guess endpoints or parameters
- Use EXACT IDs and values from API results — never invent them
- Check the `"success"` field in every proxy response
- If an operation fails, report the error — don't retry automatically
"""

    async def call_employee(
        self,
        employee_id: str,
        business_id: UUID,
        task: str,
        previous_output: Optional[str] = None,
        platform_credentials: Optional[dict] = None,
        db: Optional[AsyncSession] = None,
        allowed_tools: Optional[list[str]] = None,
        platform_tools: bool = False,
        **kwargs,
    ) -> str:
        """
        Call an employee via Claude CLI with full context.

        Args:
            employee_id: Employee file stem (e.g. "marcus_director_of_seo")
            business_id: UUID of the business this employee is working for
            task: Description of what the employee should do
            previous_output: Output from the previous step (if any)
            platform_credentials: Dict of platform credentials if needed
            allowed_tools: Extra tools for this step (merged with defaults).
                If None, only default tools (WebSearch, WebFetch) are granted.
            platform_tools: If True, grant Bash tool access + inject API tool instructions

        Returns:
            The employee's response text

        Raises:
            ClaudeCliError: If the call fails
        """
        # Load employee system prompt from DB (required)
        if not db:
            raise ClaudeCliError(
                f"Cannot load employee {employee_id}: DB session required"
            )

        try:
            employee, system_prompt = await self.load_employee_from_db(
                file_stem=employee_id, business_id=business_id, db=db,
            )
        except ClaudeCliError as e:
            raise ClaudeCliError(f"Employee {employee_id} not found in DB: {str(e)}")

        if system_prompt is None:
            raise ClaudeCliError(
                f"Employee {employee_id} has no system_prompt in DB"
            )

        model = self.parse_employee_model_from_tier(employee.model_tier)
        logger.info(f"Employee {employee_id} using model: {model}")

        # Build context
        context_parts = []

        # 1. Business profile (from database)
        from app.core.models.business import Business
        business_result = await db.execute(
            select(Business).where(Business.id == business_id)
        )
        business = business_result.scalar_one_or_none()
        if business:
            profile_text = build_profile_context(business)
            if profile_text:
                context_parts.append(f"## Business Profile\n\n{profile_text}")

        # 2. Previous step output
        if previous_output:
            context_parts.append(
                f"## Previous Step Output\n\n{previous_output}"
            )

        # 3. Platform credentials (if needed)
        if platform_credentials:
            context_parts.append(
                f"## Available Platform Connections\n\n"
                f"{json.dumps(platform_credentials, indent=2)}"
            )

        # Assemble the full message with execution rules
        full_context = "\n\n---\n\n".join(context_parts)

        # Build tool instructions if platform tools are enabled
        tool_instructions = ""
        if platform_tools:
            tool_instructions = f"\n\n---\n\n{self.build_tool_instructions(business_id)}"

        execution_rules = (
            "## EXECUTION RULES (apply to every employee)\n\n"
            "You get ONE chance to produce your output — there is no back-and-forth.\n\n"
            "**NEVER ask questions, request clarification, or wait for approval.** "
            "Execute your task immediately with whatever information you have. "
            "If data is missing, work with what you've got — use reasonable defaults, "
            "placeholders, or your best judgment.\n\n"
            "**DO NOT:**\n"
            "- Ask \"should I proceed?\"\n"
            "- Ask for files, URLs, or credentials\n"
            "- List what you need before you can start\n"
            "- Suggest the user contact someone\n"
            "- Describe what you WOULD do — just DO it\n\n"
            "**DO:**\n"
            "- Read any previous context carefully and use it\n"
            "- Produce your complete deliverable in this single response\n"
            "- Use the Bash tool with curl to call platform APIs via the credential proxy (POST /tools/proxy)\n"
            "- Execute operations step-by-step: search first, review results, then act on real data\n"
            "- Make decisions autonomously — you're the expert in your role\n"
        )
        full_message = f"{full_context}{tool_instructions}\n\n---\n\n{execution_rules}\n\n---\n\n## Your Task\n\n{task}"

        # Use platform tools (Bash + web) or merge default tools with step-specific tools
        if platform_tools:
            tools = list(self.PLATFORM_EMPLOYEE_TOOLS)
            if allowed_tools:
                for t in allowed_tools:
                    if t not in tools:
                        tools.append(t)
        else:
            tools = list(self.DEFAULT_EMPLOYEE_TOOLS)
            if allowed_tools:
                for t in allowed_tools:
                    if t not in tools:
                        tools.append(t)

        return await self._run_claude(
            system_prompt=system_prompt,
            message=full_message,
            label=f"Employee {employee_id}",
            model=model,
            db=db,
            business_id=business_id,
            allowed_tools=tools,
        )

    # ── Inline Delegation (Assistant → Employee) ──

    async def call_employee_inline(
        self,
        employee_id: str,
        business_id: UUID,
        task: str,
        previous_context: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        platform_tools: bool = False,
    ) -> str:
        """
        Call an employee inline from the assistant's chat.

        A lighter version of call_employee() used when the assistant delegates
        a quick task (like searching Twilio numbers) directly in conversation.
        Just employee prompt + business profile + task.

        Args:
            employee_id: Employee file stem (e.g. "riley_lead_qualifier")
            business_id: UUID of the business
            task: What the employee should do
            previous_context: Optional context from the assistant's conversation
            db: Async DB session for token lookup
            platform_tools: If True, grant Bash tool access + inject API tool instructions

        Returns:
            The employee's response text
        """
        # Load employee system prompt from DB (required)
        if not db:
            raise ClaudeCliError(
                f"Cannot delegate to {employee_id}: DB session required"
            )

        try:
            employee, system_prompt = await self.load_employee_from_db(
                file_stem=employee_id, business_id=business_id, db=db,
            )
        except ClaudeCliError as e:
            raise ClaudeCliError(f"Employee {employee_id} not found in DB: {str(e)}")

        if system_prompt is None:
            raise ClaudeCliError(
                f"Employee {employee_id} has no system_prompt in DB"
            )

        model = self.parse_employee_model_from_tier(employee.model_tier)
        logger.info(f"Inline delegation to {employee_id} using model: {model}")

        # Build context
        context_parts = []

        # 1. Business profile (from database)
        from app.core.models.business import Business
        business_result = await db.execute(
            select(Business).where(Business.id == business_id)
        )
        business = business_result.scalar_one_or_none()
        if business:
            profile_text = build_profile_context(business)
            if profile_text:
                context_parts.append(f"## Business Profile\n\n{profile_text}")

        # 2. Previous context from the assistant's conversation (if any)
        if previous_context:
            context_parts.append(
                f"## Context from Assistant\n\n{previous_context}"
            )

        # Assemble message with execution rules (employees must execute autonomously)
        full_context = "\n\n---\n\n".join(context_parts) if context_parts else ""

        # Build tool instructions if platform tools are enabled
        tool_instructions = ""
        if platform_tools:
            tool_instructions = f"\n\n---\n\n{self.build_tool_instructions(business_id)}"

        delegation_rules = (
            "## INLINE DELEGATION RULES\n\n"
            "You have been delegated a task directly by the business assistant during a chat conversation.\n\n"
            "**NEVER ask questions, request clarification, or wait for approval.** "
            "Execute your task immediately with whatever information you have. "
            "If data is missing, work with what you've got — use reasonable defaults "
            "or your best judgment.\n\n"
            "**DO NOT:**\n"
            "- Ask \"should I proceed?\"\n"
            "- Ask for files, URLs, or credentials\n"
            "- List what you need before you can start\n"
            "- Suggest the user contact someone\n"
            "- Describe what you WOULD do — just DO it\n\n"
            "**DO:**\n"
            "- Produce your complete deliverable in this single response\n"
            "- Use the Bash tool with curl to call platform APIs via the credential proxy (POST /tools/proxy)\n"
            "- Execute operations step-by-step: search first, review results, then act on real data\n"
            "- Make decisions autonomously — you're the expert in your role\n"
        )
        full_message = f"{full_context}{tool_instructions}\n\n---\n\n{delegation_rules}\n\n---\n\n## Your Task\n\n{task}"

        # Use platform tools (Bash + web) or default (web only)
        if platform_tools:
            tools = list(self.PLATFORM_EMPLOYEE_TOOLS)
        else:
            tools = list(self.DEFAULT_EMPLOYEE_TOOLS)

        return await self._run_claude(
            system_prompt=system_prompt,
            message=full_message,
            label=f"Inline: {employee_id}",
            model=model,
            db=db,
            business_id=business_id,
            allowed_tools=tools,
        )

    # ── Convenience Methods ──

    async def call_assistant(
        self,
        business_id: UUID,
        message: str,
        file_stem: str = "james_coo",
        extra_context: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        allowed_tools: Optional[list[str]] = None,
    ) -> str:
        """
        Quick call to a named employee — used for onboarding, main assistant chat, etc.

        Args:
            file_stem: Employee file_stem to look up (default: james_coo for backwards compat).
            allowed_tools: Optional list of tools to enable (e.g. ["WebSearch", "WebFetch"]).
        """
        # Load employee system prompt from DB (required)
        if not db:
            raise ClaudeCliError("Cannot call employee: DB session required")

        try:
            employee, system_prompt = await self.load_employee_from_db(
                file_stem=file_stem, business_id=business_id, db=db,
            )
        except ClaudeCliError as e:
            raise ClaudeCliError(f"Employee ({file_stem}) not found in DB: {str(e)}")

        if system_prompt is None:
            raise ClaudeCliError(f"Employee ({file_stem}) has no system_prompt in DB")

        model = self.parse_employee_model_from_tier(employee.model_tier)

        # Build context with business profile if it exists
        context_parts = []
        from app.core.models.business import Business
        business_result = await db.execute(
            select(Business).where(Business.id == business_id)
        )
        business = business_result.scalar_one_or_none()
        if business:
            profile_text = build_profile_context(business)
            if profile_text:
                context_parts.append(f"## Business Profile\n\n{profile_text}")

        if extra_context:
            context_parts.append(extra_context)

        context = ""
        if context_parts:
            context = "\n\n---\n\n".join(context_parts) + "\n\n---\n\n"

        full_message = f"{context}{message}"

        return await self._run_claude(
            system_prompt=system_prompt,
            message=full_message,
            label="Business Assistant",
            model=model,
            db=db,
            business_id=business_id,
            allowed_tools=allowed_tools,
        )

    async def chat(
        self,
        system_prompt: str,
        message: str,
        db: Optional[AsyncSession] = None,
        business_id: Optional[UUID] = None,
        platform_tools: bool = False,
    ) -> str:
        """
        Generic chat call — used by department chat and report builder UIs.

        Args:
            platform_tools: If True, grant Bash tool access + inject API tool instructions
                so the employee can provision numbers, update settings, etc.
        """
        if platform_tools and business_id:
            tool_instructions = self.build_tool_instructions(business_id)
            message = f"{message}\n\n---\n\n{tool_instructions}"

        return await self._run_claude(
            system_prompt=system_prompt,
            message=message,
            label="Chat",
            db=db,
            business_id=business_id,
            allowed_tools=list(self.PLATFORM_EMPLOYEE_TOOLS) if platform_tools else None,
        )

    # ── CLI Auth Status ──

    async def check_cli_auth(self) -> dict[str, dict]:
        """
        Check which CLIs are authenticated on this system.

        Returns a dict like:
            {
                "claude": {"installed": True, "authenticated": True, "user": "..."},
                "gh": {"installed": True, "authenticated": True, "user": "octocat"},
                "az": {"installed": False, "authenticated": False},
            }
        """
        checks = {
            "claude": {
                "check_cmd": ["claude", "--version"],
                "auth_cmd": ["claude", "--version"],  # No auth subcommand; per-business tokens in DB
                "login_cmd": "claude setup-token",
            },
            "gh": {
                "check_cmd": ["gh", "--version"],
                "auth_cmd": ["gh", "auth", "status"],
                "login_cmd": "gh auth login",
            },
            "az": {
                "check_cmd": ["az", "version"],
                "auth_cmd": ["az", "account", "show"],
                "login_cmd": "az login",
            },
        }

        results = {}
        for cli_name, cmds in checks.items():
            result = {
                "installed": False,
                "authenticated": False,
                "user": None,
                "login_cmd": cmds["login_cmd"],
            }

            # Check if installed
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmds["check_cmd"],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=5)
                result["installed"] = proc.returncode == 0
            except Exception:
                results[cli_name] = result
                continue

            if not result["installed"]:
                results[cli_name] = result
                continue

            # Check if authenticated
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmds["auth_cmd"],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=10,
                )
                result["authenticated"] = proc.returncode == 0

                output = (stdout or stderr or b"").decode().strip()
                if result["authenticated"] and output:
                    result["details"] = output[:200]
            except Exception:
                pass

            results[cli_name] = result

        return results

    def list_employees(self) -> list[dict]:
        """List all available employees with their metadata."""
        employees = []
        for md_file in self.company_path.rglob("*.md"):
            # Skip non-employee files
            if md_file.name in ("COMPANY.md", "ARCHITECTURE.md", "EMPLOYEE_TEMPLATE.md"):
                continue

            content = md_file.read_text()
            lines = content.split("\n")

            name = ""
            title = ""
            department = ""
            model_tier = DEFAULT_MODEL
            for line in lines[:20]:
                if line.startswith("- **Name**:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("- **Title**:"):
                    title = line.split(":", 1)[1].strip()
                elif line.startswith("- **Department**:"):
                    department = line.split(":", 1)[1].strip()
                elif line.startswith("- **Model**:"):
                    model_tier = line.split(":", 1)[1].strip().lower()

            employees.append({
                "id": md_file.stem,
                "name": name,
                "title": title,
                "department": department,
                "model": model_tier,
                "model_string": MODEL_MAP.get(model_tier, MODEL_MAP[DEFAULT_MODEL]),
                "file": str(md_file.relative_to(self.company_path)),
            })

        return employees

    # ── Employee File Management (for Org CRUD) ──

    def write_employee_file(
        self,
        department: str,
        file_stem: str,
        content: str,
        business_id: Optional[UUID] = None,
    ) -> Path:
        """
        Write an employee .md system prompt file.
        Creates the department directory if it doesn't exist.

        If business_id is provided, writes to businesses/{business_id}/company/{dept}/
        Otherwise writes to the global company/ directory.

        Returns the path to the written file.
        """
        if business_id:
            base = self.businesses_path / str(business_id) / "company"
        else:
            base = self.company_path
        dept_dir = base / department.lower().replace(" ", "_")
        dept_dir.mkdir(parents=True, exist_ok=True)
        file_path = dept_dir / f"{file_stem}.md"
        file_path.write_text(content)
        logger.info(f"Wrote employee file: {file_path}")
        return file_path

    def delete_employee_file(self, file_stem: str) -> bool:
        """
        Delete an employee .md file. Returns True if found and deleted.
        """
        for md_file in self.company_path.rglob("*.md"):
            if md_file.stem.lower() == file_stem.lower():
                md_file.unlink()
                logger.info(f"Deleted employee file: {md_file}")
                return True
        return False


# Singleton
claude_cli = ClaudeCliService()
