"""
Foundry Service — Azure AI Foundry Assistants API integration.

Manages persistent agents (Assistants) with threaded conversations.
Agents are looked up by name directly from the Foundry API — no Key Vault IDs needed.

Authentication uses DefaultAzureCredential (managed identity in production,
az login locally).

Usage:
    from app.core.services.foundry_service import foundry_service

    content, thread_id = await foundry_service.chat(
        agent_name="admin",
        message="What phone numbers do we have?",
        business_context="Business: Acme Plumbing",
        thread_id=None,  # Pass existing thread_id to continue
    )
"""

import asyncio
import json
import logging
import secrets
import time
from typing import Optional

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Ephemeral agent secret — generated once per server start
# Used to authenticate internal sapphire_api tool calls
AGENT_API_SECRET = secrets.token_hex(32)

FOUNDRY_ENDPOINT = settings.foundry_endpoint
OPENAI_API_VERSION = "2025-01-01-preview"

# Module-level agent cache: name (lowercase) → assistant_id
_agent_cache: dict[str, str] = {}

# Cache for agent instructions: name (lowercase) → system_prompt string
_instructions_cache: dict[str, str] = {}


# ── Exceptions ────────────────────────────────────────────────────────────────


class FoundryServiceError(Exception):
    """Raised when an Azure AI Foundry Assistants API call fails."""
    pass


class FoundryAgentNotFound(FoundryServiceError):
    """Raised when the requested agent is not found in Foundry."""
    pass


# ── Service ───────────────────────────────────────────────────────────────────


class FoundryService:
    def __init__(self) -> None:
        self._token_provider = get_bearer_token_provider(
            DefaultAzureCredential(
                managed_identity_client_id=settings.uami_client_id or None,
                exclude_managed_identity_credential=not settings.is_production,
            ),
            "https://cognitiveservices.azure.com/.default",
        )

    def _get_client(self) -> AzureOpenAI:
        """Create an AzureOpenAI client with DefaultAzureCredential token provider."""
        return AzureOpenAI(
            azure_endpoint=FOUNDRY_ENDPOINT,
            azure_ad_token_provider=self._token_provider,
            api_version=OPENAI_API_VERSION,
        )

    async def get_agent_by_name(self, name: str) -> str:
        """Look up a Foundry assistant ID by name.

        Checks module-level cache first; lists all assistants if not cached.
        Raises FoundryAgentNotFound if no assistant with that name exists.

        Returns the assistant ID string.
        """
        name_lower = name.lower()
        if name_lower in _agent_cache:
            return _agent_cache[name_lower]

        # Run the sync list call in a thread executor to avoid blocking
        client = self._get_client()
        try:
            loop = asyncio.get_event_loop()
            assistants = await loop.run_in_executor(
                None,
                lambda: list(client.beta.assistants.list(limit=100)),
            )
        except Exception as e:
            raise FoundryServiceError(f"Failed to list Foundry assistants: {e}") from e

        for assistant in assistants:
            if assistant.name and assistant.name.lower() == name_lower:
                _agent_cache[name_lower] = assistant.id
                logger.info(f"[Foundry] Resolved agent '{name}' → {assistant.id}")
                return assistant.id

        raise FoundryAgentNotFound(
            f"Agent '{name}' not found in Foundry. "
            f"Available agents: {[a.name for a in assistants]}. "
            f"Run infra/agents/deploy_agents.py first."
        )

    async def get_agent_instructions(self, name: str) -> str:
        """Fetch and cache the system prompt for a named Foundry agent."""
        name_lower = name.lower()
        if name_lower in _instructions_cache:
            return _instructions_cache[name_lower]

        agent_id = await self.get_agent_by_name(name)
        client = self._get_client()
        loop = asyncio.get_event_loop()
        try:
            assistant = await loop.run_in_executor(
                None,
                lambda: client.beta.assistants.retrieve(agent_id),
            )
            instructions = assistant.instructions or ""
            _instructions_cache[name_lower] = instructions
            logger.info(f"[Foundry] Cached instructions for '{name}' ({len(instructions)} chars)")
            return instructions
        except Exception as e:
            raise FoundryServiceError(f"Failed to fetch instructions for '{name}': {e}") from e

    async def complete(
        self,
        agent_name: str,
        message: str,
        business_context: str = "",
        model: str = "gpt-5-mini",
    ) -> str:
        """One-shot completion using the agent's Foundry-stored instructions.

        Uses the completions API directly — no thread, no run, no polling.
        Ideal for IVR, call analysis, email generation, and other fast one-shot tasks.
        Instructions are cached after the first fetch.

        Returns the response string.
        """
        system_prompt = await self.get_agent_instructions(agent_name)

        if business_context:
            system_prompt = f"{system_prompt}\n\n---\n\nContext:\n{business_context}"

        client = self._get_client()
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    max_tokens=1024,
                ),
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise FoundryServiceError(f"Completion failed for agent '{agent_name}': {e}") from e

    def invalidate_instructions_cache(self, name: str) -> None:
        """Clear cached instructions for an agent (call after self_update)."""
        _instructions_cache.pop(name.lower(), None)

    async def _handle_tool_calls(
        self,
        client: AzureOpenAI,
        thread_id: str,
        run_id: str,
        run,
        agent_name: str,
        business_id: Optional[str] = None,
    ) -> None:
        """Process tool call requests from the agent and submit outputs."""
        if not run.required_action or not run.required_action.submit_tool_outputs:
            return

        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []

        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            logger.info(f"[Foundry/{agent_name}] Tool call: {fn_name}({list(args.keys())})")

            try:
                output = await self._execute_tool(fn_name, args, agent_name, business_id=business_id)
            except Exception as e:
                output = f"Tool error: {e}"
                logger.warning(f"[Foundry/{agent_name}] Tool '{fn_name}' failed: {e}")

            tool_outputs.append({"tool_call_id": tc.id, "output": str(output)})

        # Submit all outputs at once
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run_id,
                tool_outputs=tool_outputs,
            ),
        )

    async def _execute_tool(self, fn_name: str, args: dict, agent_name: str, business_id: Optional[str] = None) -> str:
        """Execute a single tool call and return the string output."""
        if fn_name == "web_fetch":
            url = args.get("url", "")
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
                r = await http.get(url)
                r.raise_for_status()
                return r.text[:3000]

        elif fn_name == "web_search":
            query = args.get("query", "")
            logger.info(f"[Foundry] web_search placeholder: {query}")
            return "Web search not yet configured. Use your training knowledge."

        elif fn_name == "self_update":
            section = args.get("section", "")
            knowledge = args.get("knowledge", "")
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.post(
                    "http://localhost:8000/api/v1/agent-tools/self-update",
                    json={"agent_name": agent_name, "section": section, "knowledge": knowledge},
                )
                r.raise_for_status()
                return r.text

        elif fn_name == "proxy":
            platform = args.get("platform", "")
            method = args.get("method", "GET").upper()
            endpoint = args.get("endpoint", "")
            payload = args.get("payload", {})
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.request(
                    method,
                    f"http://localhost:8000/api/v1/tools/proxy/{platform}{endpoint}",
                    json=payload,
                )
                r.raise_for_status()
                return r.text

        elif fn_name == "sapphire_api":
            resource = args.get("resource", "")
            action = args.get("action", "list")
            record_id = args.get("id")
            data = args.get("data", {})
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.post(
                    "http://localhost:8000/api/v1/agent-tools/data",
                    json={
                        "agent_secret": AGENT_API_SECRET,
                        "business_id": business_id or "",
                        "resource": resource,
                        "action": action,
                        "id": record_id,
                        "data": data,
                    },
                )
                return r.text

        else:
            return f"Unknown tool: {fn_name}"

    async def chat(
        self,
        agent_name: str,
        message: str,
        business_context: str = "",
        thread_id: Optional[str] = None,
        business_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """Chat with a Foundry agent.

        Creates a new thread if thread_id is None; reuses existing thread otherwise.
        Prepends business_context to the first message of a new thread.

        Returns (response_text, thread_id).
        """
        agent_id = await self.get_agent_by_name(agent_name)
        client = self._get_client()
        loop = asyncio.get_event_loop()

        # Create or reuse thread
        is_new_thread = thread_id is None
        if is_new_thread:
            thread = await loop.run_in_executor(
                None,
                lambda: client.beta.threads.create(),
            )
            thread_id = thread.id
            logger.info(f"[Foundry/{agent_name}] Created thread {thread_id}")

        # Build the user message content
        if is_new_thread and business_context:
            full_message = f"{business_context}\n\n---\n\n{message}"
        else:
            full_message = message

        # Add user message to thread
        await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=full_message,
            ),
        )

        # Create run
        run = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=agent_id,
            ),
        )
        run_id = run.id
        logger.info(f"[Foundry/{agent_name}] Run {run_id} created (status={run.status})")

        # Poll until done (max 60s)
        max_polls = 60
        polls = 0
        while polls < max_polls:
            await asyncio.sleep(1)
            polls += 1

            run = await loop.run_in_executor(
                None,
                lambda: client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run_id,
                ),
            )
            status = run.status
            logger.debug(f"[Foundry/{agent_name}] Poll {polls}: status={status}")

            if status == "completed":
                break
            elif status == "requires_action":
                await self._handle_tool_calls(client, thread_id, run_id, run, agent_name, business_id=business_id)
                # Continue polling after submitting tool outputs
            elif status in ("failed", "cancelled", "expired"):
                error_info = getattr(run, "last_error", None)
                raise FoundryServiceError(
                    f"Run {run_id} ended with status '{status}': {error_info}"
                )
            # queued / in_progress → keep polling

        else:
            raise FoundryServiceError(
                f"Run {run_id} did not complete within {max_polls} seconds"
            )

        # Retrieve the assistant's response
        messages = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.list(
                thread_id=thread_id,
                order="desc",
                limit=1,
            ),
        )

        for msg in messages.data:
            if msg.role == "assistant":
                # Extract text content
                for block in msg.content:
                    if hasattr(block, "text") and hasattr(block.text, "value"):
                        return block.text.value, thread_id
                break

        raise FoundryServiceError(f"No assistant message found after run {run_id}")


# ── Singleton ─────────────────────────────────────────────────────────────────

foundry_service = FoundryService()
