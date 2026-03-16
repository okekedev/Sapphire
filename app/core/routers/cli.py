"""
CLI Router — Manage Claude CLI authentication per-business.

Each business stores its own CLAUDE_CODE_OAUTH_TOKEN (encrypted)
in the connected_accounts table. The flow:
  1. User clicks "Connect Claude" in the setup banner
  2. Frontend opens a terminal modal (xterm.js) connected via WebSocket
  3. Backend spawns `claude setup-token` in a real PTY
  4. User authenticates interactively in the embedded terminal
  5. Backend captures the token, verifies it, stores it encrypted in DB
  6. All future CLI calls for that business inject the token into the env
"""

from fastapi import APIRouter, Depends, Query
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.models.connected_account import ConnectedAccount
from app.core.services.auth_service import get_current_user_id
from app.core.services.claude_cli_service import claude_cli

router = APIRouter(prefix="/cli", tags=["CLI"])


@router.get("/status")
async def get_cli_status(
    current_user_id: UUID = Depends(get_current_user_id),
):
    """Check which CLI tools are installed and authenticated."""
    status = await claude_cli.check_cli_auth()
    return {"tools": status}


@router.get("/provider")
async def get_provider_status(
    business_id: UUID = Query(None, description="Business to check token for"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current AI provider status for a business.

    Returns whether the Claude CLI is installed and whether this
    business has a valid token stored.
    """
    return await claude_cli.get_provider_status(db=db, business_id=business_id)


@router.post("/login")
async def start_login(
    business_id: UUID = Query(..., description="Business to check/connect"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Check Claude auth status for a business.

    If the business already has a valid token, returns immediately.
    Otherwise, returns status indicating the terminal flow should start.
    """
    return await claude_cli.start_login(db=db, business_id=business_id)


@router.post("/token")
async def set_token(
    business_id: UUID = Query(..., description="Business to set token for"),
    token: str = Query(..., description="OAuth token to store"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually set a Claude CLI token for a business.

    Useful for testing or when the user has already authenticated
    via the CLI but the token isn't in the database.
    """
    await claude_cli.store_business_token(db, business_id, token)
    await db.commit()
    return {"status": "success", "message": "Token stored successfully"}


@router.get("/connection-status")
async def get_connection_status(
    business_id: UUID = Query(..., description="Business to check connection for"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Claude CLI connection status for the Connections page.

    Returns platform info, status (active/expired/disconnected),
    version, and connected_at timestamp.
    """
    # Get CLI installation info
    provider = await claude_cli.get_provider_status(db=db, business_id=business_id)

    # Look up the connected_accounts record for more detail
    # Claude CLI is a shared service (department_id=NULL)
    stmt = select(ConnectedAccount).where(
        ConnectedAccount.business_id == business_id,
        ConnectedAccount.platform == "claude_cli",
        ConnectedAccount.department_id == None,  # Shared service
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        return {
            "platform": "claude_cli",
            "status": "disconnected",
            "installed": provider.get("installed", False),
            "version": provider.get("version", ""),
            "connected_at": None,
            "message": "Claude CLI is not connected. Click Reconnect to set up.",
        }

    # Determine effective status
    if account.status == "revoked":
        effective_status = "disconnected"
        message = "Claude CLI was disconnected. Click Reconnect to set up again."
    elif account.status == "active" and provider.get("installed"):
        effective_status = "active"
        message = "Claude CLI is ready."
    else:
        # Token exists but may be expired (detected at runtime)
        effective_status = account.status
        message = provider.get("message", "Unknown status")

    return {
        "platform": "claude_cli",
        "status": effective_status,
        "installed": provider.get("installed", False),
        "version": provider.get("version", ""),
        "connected_at": account.connected_at.isoformat() if account.connected_at else None,
        "message": message,
    }


@router.delete("/token")
async def disconnect_claude(
    business_id: UUID = Query(..., description="Business to disconnect"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Claude CLI for a business (revoke stored token)."""
    # Claude CLI is a shared service (department_id=NULL)
    stmt = (
        update(ConnectedAccount)
        .where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == "claude_cli",
            ConnectedAccount.department_id == None,  # Shared service
        )
        .values(status="revoked")
    )
    await db.execute(stmt)
    return {"status": "disconnected", "message": "Claude CLI disconnected."}
