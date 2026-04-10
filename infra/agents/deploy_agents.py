"""Deploy all Sapphire agents as Azure OpenAI Assistants.

Usage:
    # Deploy all agents
    python infra/agents/deploy_agents.py

    # Deploy a single agent
    python infra/agents/deploy_agents.py --agent james

Auth: DefaultAzureCredential (az login locally, managed identity in production)
"""

import json
import argparse
import logging
from pathlib import Path
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

logger = logging.getLogger(__name__)
AGENTS_DIR = Path(__file__).parent

FOUNDRY_ENDPOINT = "https://ai-sapphire-prod.cognitiveservices.azure.com"


def load_agent_def(name: str) -> dict:
    path = AGENTS_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


def deploy_agent(client, agent_def: dict) -> str:
    # Map tool names to OpenAI Assistants tool definitions
    tools = []
    for tool in agent_def.get("tools", []):
        if tool == "web_search":
            tools.append({"type": "function", "function": {
                "name": "web_search",
                "description": "Search the web for current information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"]
                }
            }})
        elif tool in ("web_fetch", "proxy"):
            tools.append({"type": "function", "function": {
                "name": tool,
                "description": (
                    "Fetch content from a URL" if tool == "web_fetch"
                    else "Call any connected platform API with injected credentials"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url" if tool == "web_fetch" else "platform": {
                            "type": "string",
                            "description": "URL to fetch" if tool == "web_fetch" else "Platform name (e.g. facebook, google)"
                        },
                        **({"method": {"type": "string"}, "endpoint": {"type": "string"}, "payload": {"type": "object"}} if tool == "proxy" else {})
                    },
                    "required": ["url"] if tool == "web_fetch" else ["platform", "method", "endpoint"]
                }
            }})
        elif tool == "sapphire_api":
            tools.append({"type": "function", "function": {
                "name": "sapphire_api",
                "description": "Read or write Sapphire platform data (profile, contacts, jobs, customers).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource": {
                            "type": "string",
                            "description": "Data type: profile, contacts, jobs, customers"
                        },
                        "action": {
                            "type": "string",
                            "description": "Operation: list, get, create, update, delete"
                        },
                        "id": {
                            "type": "string",
                            "description": "Record ID for get/update/delete operations"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data payload for create/update operations"
                        }
                    },
                    "required": ["resource", "action"]
                }
            }})

    # All agents get self_update
    tools.append({"type": "function", "function": {
        "name": "self_update",
        "description": (
            "Update your own knowledge when you discover something new — an API change, "
            "a new platform feature, a pattern in customer behavior, or anything that would "
            "make you more effective next time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {"type": "string", "description": "Short label for what you're updating"},
                "knowledge": {"type": "string", "description": "What you learned, in plain language"}
            },
            "required": ["section", "knowledge"]
        }
    }})

    # OpenAI metadata values must be strings
    raw_meta = agent_def.get("metadata", {})
    metadata = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in raw_meta.items()}

    # Check if agent already exists (update vs create)
    existing = None
    try:
        for asst in client.beta.assistants.list(limit=100):
            if asst.name and asst.name.lower() == agent_def["name"].lower():
                existing = asst
                break
    except Exception:
        pass

    if existing:
        assistant = client.beta.assistants.update(
            existing.id,
            model=agent_def["model"],
            name=agent_def["name"],
            instructions=agent_def["instructions"],
            tools=tools,
            metadata=metadata,
        )
        logger.info(f"Updated {agent_def['name']} → assistant ID: {assistant.id}")
    else:
        assistant = client.beta.assistants.create(
            model=agent_def["model"],
            name=agent_def["name"],
            instructions=agent_def["instructions"],
            tools=tools,
            metadata=metadata,
        )
        logger.info(f"Created {agent_def['name']} → assistant ID: {assistant.id}")

    return assistant.id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=FOUNDRY_ENDPOINT)
    parser.add_argument("--agent", default="all", help="Agent name or 'all'")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    from openai import AzureOpenAI
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=args.endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2025-01-01-preview",
    )

    agent_names = ["grace", "james", "admin", "billing", "marketing", "operations", "sales"]
    if args.agent != "all":
        agent_names = [args.agent]

    print("\nDeploying agents:")
    for name in agent_names:
        agent_def = load_agent_def(name)
        agent_id = deploy_agent(client, agent_def)
        print(f"  {name}: {agent_id}")

    print("\nDone. Agent IDs resolved by name at runtime — no Key Vault storage needed.")


if __name__ == "__main__":
    main()
