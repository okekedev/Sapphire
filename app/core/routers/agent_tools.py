"""Handles tool calls made by Foundry agents during a run.

When an agent calls self_update, this endpoint:
1. Fetches the agent's current instructions from Foundry
2. Appends the new knowledge under a dated ## section
3. Pushes the updated instructions back to Foundry

The agent's knowledge grows over time without any human intervention.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from app.database import get_db
from app.core.services.auth_service import get_current_user_id
from app.config import settings

router = APIRouter(prefix="/agent-tools", tags=["Agent Tools"])
logger = logging.getLogger(__name__)


class SelfUpdateRequest(BaseModel):
    business_id: UUID
    agent_name: str       # e.g. "luna", "riley"
    section: str          # short label for what changed
    knowledge: str        # what the agent learned


def _get_foundry_client() -> AIProjectClient:
    return AIProjectClient(
        endpoint=settings.foundry_endpoint,
        credential=DefaultAzureCredential(),
    )


@router.post("/self-update")
async def self_update(
    payload: SelfUpdateRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Agent calls this when it learns something worth persisting."""
    from sqlalchemy import text

    # Get the Foundry agent ID for this business + agent name
    result = await db.execute(
        text("SELECT foundry_agent_ids FROM businesses WHERE id = :id"),
        {"id": str(payload.business_id)},
    )
    row = result.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No Foundry agents found for this business")

    import json
    agent_ids = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    agent_id = agent_ids.get(payload.agent_name)
    if not agent_id:
        raise HTTPException(status_code=404, detail=f"Agent '{payload.agent_name}' not found")

    try:
        client = _get_foundry_client()
        agent = client.agents.get_agent(agent_id)

        # Append new knowledge as a dated section
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_section = f"\n\n## Learned: {payload.section} ({timestamp})\n{payload.knowledge}"
        updated_instructions = (agent.instructions or "") + new_section

        client.agents.update_agent(agent_id, instructions=updated_instructions)

        logger.info(f"[self_update] {payload.agent_name} updated: {payload.section}")
        return {"status": "updated", "agent": payload.agent_name, "section": payload.section}

    except Exception as e:
        logger.error(f"[self_update] Failed for {payload.agent_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
