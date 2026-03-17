"""Deploy all Sapphire agents to Azure AI Foundry.

Usage:
    # Deploy all agents (new business signup)
    python infra/agents/deploy_agents.py --endpoint https://ai-sapphire-prod.services.ai.azure.com

    # Deploy with business context injected
    python infra/agents/deploy_agents.py --endpoint https://... --business-id <uuid>

    # Deploy a single agent
    python infra/agents/deploy_agents.py --endpoint https://... --agent grace

Auth: DefaultAzureCredential (az login locally, managed identity in production)
"""

import json
import argparse
import logging
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

logger = logging.getLogger(__name__)
AGENTS_DIR = Path(__file__).parent


def load_agent_def(name: str) -> dict:
    path = AGENTS_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


def inject_business_context(instructions: str, context: dict) -> str:
    """Replace {{field}} placeholders with actual business values."""
    for key, value in context.items():
        instructions = instructions.replace(f"{{{{{key}}}}}", value or "")
    return instructions


def deploy_agent(client, agent_def: dict, context: dict | None = None) -> str:
    instructions = agent_def["instructions"]
    if context:
        instructions = inject_business_context(instructions, context)

    # Map tool names to Foundry tool definitions
    tools = []
    for tool in agent_def.get("tools", []):
        if tool == "web_search":
            tools.append({"type": "bing_grounding"})
        elif tool == "proxy":
            tools.append({
                "type": "function",
                "function": {
                    "name": "proxy",
                    "description": "Call any connected platform API with injected credentials",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "platform": {"type": "string", "description": "Platform name (e.g. facebook, twilio)"},
                            "method": {"type": "string", "description": "HTTP method"},
                            "endpoint": {"type": "string", "description": "API endpoint path"},
                            "payload": {"type": "object", "description": "Request body"}
                        },
                        "required": ["platform", "method", "endpoint"]
                    }
                }
            })

    # All agents get self_update — lets them update their own instructions when they learn something
    tools.append({
        "type": "function",
        "function": {
            "name": "self_update",
            "description": (
                "Update your own knowledge when you discover something new — an API change, "
                "a new platform feature, a pattern in customer behavior, or anything that would "
                "make you more effective next time. Call this proactively when you notice something "
                "worth remembering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Short label for what you're updating (e.g. 'Facebook API - post endpoint', 'Lead qualification - pricing objection')"
                    },
                    "knowledge": {
                        "type": "string",
                        "description": "What you learned, in plain language. Be specific and actionable."
                    }
                },
                "required": ["section", "knowledge"]
            }
        }
    })

    agent = client.agents.create_agent(
        model=agent_def["model"],
        name=agent_def["name"],
        instructions=instructions,
        tools=tools,
        metadata=agent_def.get("metadata", {}),
    )
    logger.info(f"Deployed {agent_def['name']} → agent ID: {agent.id}")
    return agent.id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True, help="Azure AI Foundry endpoint URL")
    parser.add_argument("--agent", default="all", help="Agent name or 'all'")
    parser.add_argument("--business-id", help="Business ID to inject context from DB")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    credential = DefaultAzureCredential()
    client = AIProjectClient(endpoint=args.endpoint, credential=credential)

    # Load business context from DB if provided
    context = None
    if args.business_id:
        context = load_business_context(args.business_id)

    agent_names = ["grace", "ivy", "quinn", "luna", "morgan", "riley"]
    if args.agent != "all":
        agent_names = [args.agent]

    deployed = {}
    for name in agent_names:
        agent_def = load_agent_def(name)
        agent_id = deploy_agent(client, agent_def, context)
        deployed[name] = agent_id

    print("\nDeployed agents:")
    for name, agent_id in deployed.items():
        print(f"  {name}: {agent_id}")

    if args.business_id:
        save_agent_ids(args.business_id, deployed)


def load_business_context(business_id: str) -> dict:
    """Load business profile from DB for context injection."""
    import asyncio
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async def _load():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT * FROM businesses WHERE id = :id"),
                {"id": business_id}
            )
            row = result.mappings().fetchone()
            if not row:
                raise ValueError(f"Business {business_id} not found")
            return dict(row)

    return asyncio.run(_load())


def save_agent_ids(business_id: str, agent_ids: dict):
    """Persist Foundry agent IDs back to the business record (one column per agent)."""
    import asyncio
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async def _save():
        async with AsyncSessionLocal() as db:
            set_clauses = ", ".join(f"foundry_agent_{name} = :{name}" for name in agent_ids)
            params = {name: agent_id for name, agent_id in agent_ids.items()}
            params["id"] = business_id
            await db.execute(
                text(f"UPDATE businesses SET {set_clauses} WHERE id = :id"),
                params,
            )
            await db.commit()

    asyncio.run(_save())


if __name__ == "__main__":
    main()
