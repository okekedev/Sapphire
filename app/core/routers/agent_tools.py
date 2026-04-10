"""Handles tool calls made by Foundry agents during a run.

Self-update strategy:
- Same section label → replace existing entry (no duplicates)
- New section label → append
- Learned section count hits MAX_LEARNED_SECTIONS → trigger re-consolidation
- Re-consolidation: ask the model to rewrite instructions cleanly, folding all
  learnings back into the relevant sections. Result replaces the full instructions.

Agent IDs are resolved by name directly via the Foundry API (no Key Vault needed).
"""

import re
import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/agent-tools", tags=["Agent Tools"])
logger = logging.getLogger(__name__)

MAX_LEARNED_SECTIONS = 20
ALLOWED_AGENTS = {"admin", "billing", "marketing", "operations", "sales", "james", "grace"}


class SelfUpdateRequest(BaseModel):
    agent_name: str
    section: str
    knowledge: str


def _get_openai_client() -> AzureOpenAI:
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=settings.foundry_endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2025-01-01-preview",
    )


async def _get_agent_id(agent_name: str) -> str:
    """Look up Foundry agent ID by name via the Foundry API."""
    from app.core.services.foundry_service import foundry_service, FoundryAgentNotFound
    try:
        return await foundry_service.get_agent_by_name(agent_name)
    except FoundryAgentNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. Run deploy_agents.py first.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


def _consolidate(client: AzureOpenAI, instructions: str) -> str:
    """Ask the model to rewrite instructions cleanly, folding in all learnings."""
    consolidation_prompt = (
        "You are reviewing your own instructions. Below are your current instructions "
        "including a list of things you've learned over time.\n\n"
        "Rewrite these as a single clean, concise document. Fold each learned entry into "
        "the relevant section of the instructions. Remove the '## Learned:' entries — "
        "their content should be absorbed naturally into the appropriate sections.\n"
        "Do not lose any knowledge. Do not add anything new. Just consolidate.\n\n"
        f"CURRENT INSTRUCTIONS:\n{instructions}"
    )
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": consolidation_prompt}],
    )
    return response.choices[0].message.content or instructions


@router.post("/self-update")
async def self_update(payload: SelfUpdateRequest):
    """Agent calls this when it learns something worth persisting."""
    if payload.agent_name.lower() not in ALLOWED_AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent '{payload.agent_name}'")

    agent_id = await _get_agent_id(payload.agent_name)

    try:
        client = _get_openai_client()
        agent = client.beta.assistants.retrieve(agent_id)
        current = agent.instructions or ""

        updated = _upsert_learned_section(current, payload.section, payload.knowledge)

        consolidated = False
        if _count_learned_sections(updated) >= MAX_LEARNED_SECTIONS:
            logger.info(f"[self_update] {payload.agent_name} hitting {MAX_LEARNED_SECTIONS} sections — consolidating")
            updated = _consolidate(client, updated)
            consolidated = True

        client.beta.assistants.update(agent_id, instructions=updated)

        # Invalidate instructions cache so next complete() call gets fresh instructions
        from app.core.services.foundry_service import foundry_service
        foundry_service.invalidate_instructions_cache(payload.agent_name)

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


# ── Agent Data API ─────────────────────────────────────────────────────────────


class AgentDataRequest(BaseModel):
    agent_secret: str
    business_id: str
    resource: str   # profile | contacts | jobs | customers
    action: str     # list | get | create | update | delete
    id: Optional[str] = None
    data: Optional[dict] = None


PROFILE_FIELDS = {"narrative"}


@router.post("/data")
async def agent_data(payload: AgentDataRequest, db: AsyncSession = Depends(get_db)):
    """Internal endpoint for Foundry agents to read/write platform data."""
    from app.core.services.foundry_service import AGENT_API_SECRET

    if payload.agent_secret != AGENT_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid agent secret")

    try:
        biz_id = UUID(payload.business_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid business_id")

    from sqlalchemy import select, update as sa_update
    from app.core.models.business import Business
    from app.marketing.models import Contact
    from app.operations.models import Job

    # ── Profile ──
    if payload.resource == "profile":
        result = await db.execute(select(Business).where(Business.id == biz_id))
        biz = result.scalar_one_or_none()
        if not biz:
            return {"error": "Business not found"}

        if payload.action == "get":
            return {"narrative": biz.narrative}
        elif payload.action == "update" and payload.data:
            for field, value in payload.data.items():
                if field in PROFILE_FIELDS:
                    setattr(biz, field, value)
            await db.commit()
            return {"updated": list(payload.data.keys())}

    # ── Contacts ──
    elif payload.resource == "contacts":
        if payload.action == "list":
            rows = await db.execute(
                select(Contact)
                .where(Contact.business_id == biz_id)
                .order_by(Contact.created_at.desc())
                .limit(50)
            )
            contacts = rows.scalars().all()
            return [
                {
                    "id": str(c.id),
                    "name": c.full_name,
                    "phone": c.phone,
                    "email": c.email,
                    "status": c.status,
                    "notes": c.notes,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in contacts
            ]

        elif payload.action == "get" and payload.id:
            row = await db.execute(select(Contact).where(Contact.id == UUID(payload.id)))
            c = row.scalar_one_or_none()
            if not c:
                return {"error": "Contact not found"}
            return {
                "id": str(c.id),
                "name": c.full_name,
                "phone": c.phone,
                "email": c.email,
                "status": c.status,
                "notes": c.notes,
                "city": c.city,
                "company_name": c.company_name,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }

        elif payload.action == "create" and payload.data:
            c = Contact(
                business_id=biz_id,
                full_name=payload.data.get("name"),
                phone=payload.data.get("phone"),
                email=payload.data.get("email"),
                notes=payload.data.get("notes"),
                status="new",
            )
            db.add(c)
            await db.commit()
            await db.refresh(c)
            return {"id": str(c.id), "name": c.full_name, "status": c.status}

        elif payload.action == "update" and payload.id and payload.data:
            row = await db.execute(select(Contact).where(Contact.id == UUID(payload.id)))
            c = row.scalar_one_or_none()
            if not c:
                return {"error": "Contact not found"}
            for field, value in payload.data.items():
                if hasattr(c, field):
                    setattr(c, field, value)
            await db.commit()
            return {"updated": str(c.id)}

    # ── Jobs ──
    elif payload.resource == "jobs":
        if payload.action == "list":
            rows = await db.execute(
                select(Job)
                .where(Job.business_id == biz_id)
                .order_by(Job.created_at.desc())
                .limit(50)
            )
            jobs = rows.scalars().all()
            return [
                {
                    "id": str(j.id),
                    "title": j.title,
                    "status": j.status,
                    "amount_quoted": float(j.amount_quoted) if j.amount_quoted else None,
                    "amount_billed": float(j.amount_billed) if j.amount_billed else None,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in jobs
            ]

    # ── Customers ──
    elif payload.resource == "customers":
        if payload.action == "list":
            rows = await db.execute(
                select(Contact)
                .where(Contact.business_id == biz_id, Contact.status == "active_customer")
                .order_by(Contact.created_at.desc())
                .limit(50)
            )
            customers = rows.scalars().all()
            return [
                {
                    "id": str(c.id),
                    "name": c.full_name,
                    "phone": c.phone,
                    "email": c.email,
                    "company_name": c.company_name,
                    "revenue_since_contact": c.revenue_since_contact,
                }
                for c in customers
            ]

    return {"error": f"Unknown resource or action: {payload.resource}/{payload.action}"}
