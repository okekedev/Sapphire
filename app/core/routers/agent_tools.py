"""Handles tool calls made by Foundry agents during a run.

Self-update strategy:
- Same section label → replace existing entry (no duplicates)
- New section label → append
- Learned section count hits MAX_LEARNED_SECTIONS → trigger re-consolidation
- Re-consolidation: ask Claude to rewrite instructions cleanly, folding all
  learnings back into the relevant sections. Result replaces the full instructions.

Agent IDs are loaded from settings.foundry_agent_ids (Key Vault secret
'foundry-agent-ids') — a JSON map of { agent_name: foundry_agent_id }.
No DB access needed.
"""

import json
import re
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from app.config import settings

router = APIRouter(prefix="/agent-tools", tags=["Agent Tools"])
logger = logging.getLogger(__name__)

MAX_LEARNED_SECTIONS = 20
ALLOWED_AGENTS = {"grace", "ivy", "quinn", "luna", "morgan", "riley"}


class SelfUpdateRequest(BaseModel):
    agent_name: str
    section: str
    knowledge: str


def _get_foundry_client() -> AIProjectClient:
    return AIProjectClient(
        endpoint=settings.foundry_endpoint,
        credential=DefaultAzureCredential(),
    )


def _get_agent_id(agent_name: str) -> str:
    """Look up Foundry agent ID from config (Key Vault secret foundry-agent-ids)."""
    agent_ids = json.loads(settings.foundry_agent_ids or "{}")
    agent_id = agent_ids.get(agent_name.lower())
    if not agent_id:
        raise HTTPException(
            status_code=404,
            detail=f"No Foundry agent ID configured for '{agent_name}'. Run deploy_agents.py first.",
        )
    return agent_id


def _upsert_learned_section(instructions: str, section: str, knowledge: str) -> str:
    """Replace existing section with same label, or append if new."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_entry = f"\n\n## Learned: {section} ({timestamp})\n{knowledge}"

    pattern = rf"\n\n## Learned: {re.escape(section)} \(\d{{4}}-\d{{2}}-\d{{2}}\)\n.*?(?=\n\n##|\Z)"
    if re.search(pattern, instructions, flags=re.DOTALL):
        return re.sub(pattern, new_entry, instructions, flags=re.DOTALL)

    return instructions + new_entry


def _count_learned_sections(instructions: str) -> int:
    return len(re.findall(r"\n\n## Learned:", instructions))


async def _consolidate(client: AIProjectClient, agent_id: str, instructions: str) -> str:
    """Ask Claude to rewrite the instructions cleanly, folding in all learnings."""
    consolidation_prompt = (
        "You are reviewing your own instructions. Below are your current instructions "
        "including a list of things you've learned over time.\n\n"
        "Rewrite these as a single clean, concise document. Fold each learned entry into "
        "the relevant section of the instructions. Remove the '## Learned:' entries — "
        "their content should be absorbed naturally into the appropriate sections.\n"
        "Do not lose any knowledge. Do not add anything new. Just consolidate.\n\n"
        f"CURRENT INSTRUCTIONS:\n{instructions}"
    )

    thread = client.agents.create_thread()
    client.agents.create_message(thread_id=thread.id, role="user", content=consolidation_prompt)
    client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent_id)

    messages = client.agents.list_messages(thread_id=thread.id)
    for msg in messages:
        if msg.role == "assistant":
            return msg.content[0].text.value if msg.content else instructions

    return instructions


@router.post("/self-update")
async def self_update(payload: SelfUpdateRequest):
    """Agent calls this when it learns something worth persisting."""
    if payload.agent_name.lower() not in ALLOWED_AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent '{payload.agent_name}'")

    agent_id = _get_agent_id(payload.agent_name)

    try:
        client = _get_foundry_client()
        agent = client.agents.get_agent(agent_id)
        current = agent.instructions or ""

        updated = _upsert_learned_section(current, payload.section, payload.knowledge)

        consolidated = False
        if _count_learned_sections(updated) >= MAX_LEARNED_SECTIONS:
            logger.info(f"[self_update] {payload.agent_name} hitting {MAX_LEARNED_SECTIONS} sections — consolidating")
            updated = await _consolidate(client, agent_id, updated)
            consolidated = True

        client.agents.update_agent(agent_id, instructions=updated)

        logger.info(f"[self_update] {payload.agent_name} updated: {payload.section} (consolidated={consolidated})")
        return {
            "status": "updated",
            "agent": payload.agent_name,
            "section": payload.section,
            "consolidated": consolidated,
            "learned_sections": _count_learned_sections(updated),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[self_update] Failed for {payload.agent_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
