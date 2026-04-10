"""
OpenAI Service — calls GPT-5 models via Azure AI Foundry.

Authentication uses DefaultAzureCredential (managed identity in production,
az login locally). No per-business tokens — single Foundry endpoint.

Model tiers map to Azure OpenAI deployments:
  haiku  → gpt-5-mini   (fast, cost-efficient)
  sonnet → gpt-5        (balanced)
  opus   → gpt-5-pro    (most capable)

Usage:
    from app.core.services.openai_service import openai_service

    result = await openai_service.call_employee(
        employee_id="riley_lead_qualifier",
        business_id=uuid,
        task="Qualify this new lead",
        db=session,
    )
"""

import json
import logging
from typing import Optional
from uuid import UUID

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# Map model_tier values → Azure OpenAI deployment names
MODEL_MAP: dict[str, str] = {
    "opus": "gpt-5-mini",
    "sonnet": "gpt-5-mini",
    "haiku": "gpt-5-mini",
}
DEFAULT_MODEL = "haiku"

# Map any legacy Claude model names → equivalent deployment
_LEGACY_MODEL_MAP: dict[str, str] = {
    "claude-haiku-4-5": "gpt-5-mini",
    "claude-haiku-4-5-20251001": "gpt-5-mini",
    "claude-sonnet-4-6": "gpt-5",
    "claude-sonnet-4-5": "gpt-5",
    "claude-opus-4-6": "gpt-5",
    "claude-opus-4-5": "gpt-5",
}

OPENAI_API_VERSION = "2025-01-01-preview"


# ── Exceptions ───────────────────────────────────────────────────────────────

class OpenAIServiceError(Exception):
    """Raised when an Azure OpenAI API call fails."""
    pass


class OpenAIServiceNotReady(OpenAIServiceError):
    """Raised when the service is not configured or reachable."""
    pass


# ── Helper ───────────────────────────────────────────────────────────────────

def build_profile_context(business) -> str:
    """Return the business narrative for use as AI context."""
    return getattr(business, "narrative", None) or ""


# ── Service ───────────────────────────────────────────────────────────────────

class OpenAIService:
    DEFAULT_EMPLOYEE_TOOLS = ["WebSearch", "WebFetch"]
    PLATFORM_EMPLOYEE_TOOLS = ["Bash", "WebSearch", "WebFetch"]
    INTERNAL_API_BASE = "http://localhost:8000/api/v1/tools"

    def __init__(self) -> None:
        self._token_provider = get_bearer_token_provider(
            DefaultAzureCredential(managed_identity_client_id=settings.uami_client_id or None),
            "https://cognitiveservices.azure.com/.default",
        )

    def _resolve_deployment(self, model: Optional[str]) -> str:
        """Resolve any model name or tier to a valid deployment name."""
        if not model:
            return MODEL_MAP[DEFAULT_MODEL]
        # Direct deployment name match
        if model in MODEL_MAP.values():
            return model
        # Tier name (haiku/sonnet/opus)
        if model.lower() in MODEL_MAP:
            return MODEL_MAP[model.lower()]
        # Legacy Claude model name
        if model in _LEGACY_MODEL_MAP:
            return _LEGACY_MODEL_MAP[model]
        # Unknown — fall back to default
        logger.warning(f"Unknown model '{model}', falling back to {MODEL_MAP[DEFAULT_MODEL]}")
        return MODEL_MAP[DEFAULT_MODEL]

    async def _call_model(
        self,
        system_prompt: str,
        message: str,
        label: str = "GPT",
        model: Optional[str] = None,
        db=None,
        business_id=None,
        allowed_tools=None,  # kept for call-signature compat
    ) -> str:
        """Call Azure OpenAI chat completions via DefaultAzureCredential."""
        deployment = self._resolve_deployment(model)
        logger.info(f"[{label}] deployment={deployment}")
        try:
            token = self._token_provider()
            url = (
                f"{settings.foundry_endpoint}/openai/deployments/{deployment}"
                f"/chat/completions?api-version={OPENAI_API_VERSION}"
            )
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "max_completion_tokens": 8192,
            }
            async with httpx.AsyncClient(timeout=settings.foundry_timeout) as http:
                r = await http.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"[{label}] API call failed: {e}")
            raise OpenAIServiceError(str(e)) from e

    # Alias for callers that use _run_claude directly
    _run_claude = _call_model

    # ── Employee model resolution ──

    def parse_employee_model_from_tier(self, model_tier: str) -> str:
        return MODEL_MAP.get(model_tier.lower(), MODEL_MAP[DEFAULT_MODEL])

    # ── DB helpers ──

    async def load_employee_from_db(
        self,
        file_stem: str,
        business_id: UUID,
        db: AsyncSession,
    ) -> tuple:
        """Load employee + system_prompt from DB. Falls back to global template."""
        from app.core.models.organization import Employee

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
            .order_by(Employee.business_id.desc())
        )
        result = await db.execute(stmt)
        employee = result.scalars().first()

        if not employee:
            raise OpenAIServiceError(
                f"Employee '{file_stem}' not found in DB for business {business_id}"
            )
        logger.info(
            f"Loaded {file_stem} from DB "
            f"(scope={'business' if employee.business_id else 'global'}, "
            f"model_tier={employee.model_tier})"
        )
        return employee, employee.system_prompt

    # ── Tool instructions ──

    @staticmethod
    def build_tool_instructions(business_id: UUID) -> str:
        from app.config import settings as app_settings
        base = OpenAIService.INTERNAL_API_BASE
        bid = str(business_id)
        db_url = app_settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

        return f"""## Platform API Access

You have Bash tool access to call external platform APIs through our credential proxy.
Authentication is handled automatically — you never need API keys or tokens.
These are REAL operations — they create real resources, post real content, and spend real money.

### Step 1: Discover Connected Platforms

```bash
curl -s "{base}/available?business_id={bid}"
```

### Step 2: Research the API

Use **WebSearch** to find the current API documentation for the platform you need.

### Step 3: Execute via Proxy

```bash
curl -s -X POST {base}/proxy \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","platform":"stripe","method":"POST","url":"https://api.stripe.com/v1/customers","headers":{{"Content-Type":"application/x-www-form-urlencoded"}},"body":"name=John+Doe&email=john@example.com"}}'
```

### Dedicated Endpoints

**Twilio — Provision a tracking number:**
```bash
curl -s -X POST {base}/twilio/provision \\
  -H "Content-Type: application/json" \\
  -d '{{"business_id":"{bid}","phone_number":"+19401234567","campaign_name":"Main Line","channel":"direct"}}'
```

**Phone Lines — List all:**
```bash
curl -s "http://localhost:8000/api/v1/phone-lines?business_id={bid}"
```

**Phone Settings — Read current settings:**
```bash
curl -s "http://localhost:8000/api/v1/tracking-routing/settings?business_id={bid}"
```

### Direct Database Access

```bash
psql "{db_url}" -c "SELECT phone_number, line_type, label FROM phone_lines WHERE business_id='{bid}';"
```

### Rules
- Always discover connected platforms first before making API calls
- Use WebSearch to find current API docs — don't guess endpoints or parameters
- Use EXACT IDs and values from API results — never invent them
- Check the success field in every proxy response
- If an operation fails, report the error — don't retry automatically
"""

    # ── Public call methods ──

    async def call_assistant(
        self,
        business_id: UUID,
        message: str,
        file_stem: str = "ivy",
        extra_context: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        allowed_tools: Optional[list[str]] = None,
    ) -> str:
        if not db:
            raise OpenAIServiceError("Cannot call employee: DB session required")

        try:
            employee, system_prompt = await self.load_employee_from_db(
                file_stem=file_stem, business_id=business_id, db=db,
            )
        except OpenAIServiceError as e:
            raise OpenAIServiceError(f"Employee ({file_stem}) not found in DB: {e}")

        if system_prompt is None:
            raise OpenAIServiceError(f"Employee ({file_stem}) has no system_prompt in DB")

        model = self.parse_employee_model_from_tier(employee.model_tier)

        context_parts = []
        from app.core.models.business import Business
        business_result = await db.execute(select(Business).where(Business.id == business_id))
        business = business_result.scalar_one_or_none()
        if business:
            profile_text = build_profile_context(business)
            if profile_text:
                context_parts.append(f"## Business Profile\n\n{profile_text}")

        if extra_context:
            context_parts.append(extra_context)

        context = ("\n\n---\n\n".join(context_parts) + "\n\n---\n\n") if context_parts else ""
        full_message = f"{context}{message}"

        return await self._call_model(
            system_prompt=system_prompt,
            message=full_message,
            label="Business Assistant",
            model=model,
            db=db,
            business_id=business_id,
        )

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
        if not db:
            raise OpenAIServiceError(f"Cannot load employee {employee_id}: DB session required")

        try:
            employee, system_prompt = await self.load_employee_from_db(
                file_stem=employee_id, business_id=business_id, db=db,
            )
        except OpenAIServiceError as e:
            raise OpenAIServiceError(f"Employee {employee_id} not found in DB: {e}")

        if system_prompt is None:
            raise OpenAIServiceError(f"Employee {employee_id} has no system_prompt in DB")

        model = self.parse_employee_model_from_tier(employee.model_tier)
        logger.info(f"Employee {employee_id} using deployment: {model}")

        context_parts = []
        from app.core.models.business import Business
        business_result = await db.execute(select(Business).where(Business.id == business_id))
        business = business_result.scalar_one_or_none()
        if business:
            profile_text = build_profile_context(business)
            if profile_text:
                context_parts.append(f"## Business Profile\n\n{profile_text}")

        if previous_output:
            context_parts.append(f"## Previous Step Output\n\n{previous_output}")

        if platform_credentials:
            context_parts.append(
                f"## Available Platform Connections\n\n"
                f"{json.dumps(platform_credentials, indent=2)}"
            )

        full_context = "\n\n---\n\n".join(context_parts)
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
            "- Make decisions autonomously — you're the expert in your role\n"
        )
        full_message = (
            f"{full_context}{tool_instructions}\n\n---\n\n"
            f"{execution_rules}\n\n---\n\n## Your Task\n\n{task}"
        )

        return await self._call_model(
            system_prompt=system_prompt,
            message=full_message,
            label=f"Employee {employee_id}",
            model=model,
            db=db,
            business_id=business_id,
        )

    async def call_employee_inline(
        self,
        employee_id: str,
        business_id: UUID,
        task: str,
        previous_context: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        platform_tools: bool = False,
    ) -> str:
        if not db:
            raise OpenAIServiceError(f"Cannot delegate to {employee_id}: DB session required")

        try:
            employee, system_prompt = await self.load_employee_from_db(
                file_stem=employee_id, business_id=business_id, db=db,
            )
        except OpenAIServiceError as e:
            raise OpenAIServiceError(f"Employee {employee_id} not found in DB: {e}")

        if system_prompt is None:
            raise OpenAIServiceError(f"Employee {employee_id} has no system_prompt in DB")

        model = self.parse_employee_model_from_tier(employee.model_tier)

        context_parts = []
        from app.core.models.business import Business
        business_result = await db.execute(select(Business).where(Business.id == business_id))
        business = business_result.scalar_one_or_none()
        if business:
            profile_text = build_profile_context(business)
            if profile_text:
                context_parts.append(f"## Business Profile\n\n{profile_text}")

        if previous_context:
            context_parts.append(f"## Context from Assistant\n\n{previous_context}")

        full_context = "\n\n---\n\n".join(context_parts) if context_parts else ""
        tool_instructions = ""
        if platform_tools:
            tool_instructions = f"\n\n---\n\n{self.build_tool_instructions(business_id)}"

        delegation_rules = (
            "## INLINE DELEGATION RULES\n\n"
            "You have been delegated a task directly by the business assistant during a chat.\n\n"
            "**NEVER ask questions, request clarification, or wait for approval.** "
            "Execute your task immediately with whatever information you have.\n\n"
            "**DO NOT:**\n"
            "- Ask \"should I proceed?\"\n"
            "- List what you need before you can start\n"
            "- Describe what you WOULD do — just DO it\n\n"
            "**DO:**\n"
            "- Produce your complete deliverable in this single response\n"
            "- Make decisions autonomously — you're the expert in your role\n"
        )
        full_message = (
            f"{full_context}{tool_instructions}\n\n---\n\n"
            f"{delegation_rules}\n\n---\n\n## Your Task\n\n{task}"
        )

        return await self._call_model(
            system_prompt=system_prompt,
            message=full_message,
            label=f"Inline: {employee_id}",
            model=model,
            db=db,
            business_id=business_id,
        )

    async def chat(
        self,
        system_prompt: str,
        message: str,
        db=None,
        business_id=None,
        platform_tools: bool = False,
    ) -> str:
        return await self._call_model(
            system_prompt=system_prompt,
            message=message,
            db=db,
            business_id=business_id,
        )

    async def get_provider_status(self, db=None, business_id=None) -> dict:
        return {
            "status": "connected",
            "provider": "azure_openai",
            "endpoint": settings.foundry_endpoint,
            "model": settings.foundry_default_model,
        }

    async def startup_check(self) -> dict:
        try:
            self._token_provider()
            return {
                "ready": True,
                "provider": "azure_openai",
                "endpoint": settings.foundry_endpoint,
                "model": settings.foundry_default_model,
                "message": "Azure OpenAI credentials resolved",
            }
        except Exception as e:
            return {
                "ready": False,
                "provider": "azure_openai",
                "message": str(e),
            }


# ── Singleton ─────────────────────────────────────────────────────────────────

openai_service = OpenAIService()
