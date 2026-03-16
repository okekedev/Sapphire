"""
Ngrok Service — local tunnel management for development.

Users paste their ngrok auth token via the Connections page.
The token is encrypted and stored in connected_accounts (same as Twilio/Stripe).
When the server starts, if ngrok is connected we auto-start the tunnel.
"""

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.connected_account import ConnectedAccount
from app.core.services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)

PLATFORM = "ngrok"
encryption = EncryptionService()


class NgrokService:
    """Per-business ngrok credential management and tunnel helpers."""

    # ── Credential storage ──

    async def store_credentials(
        self,
        db: AsyncSession,
        business_id: UUID,
        auth_token: str,
    ) -> ConnectedAccount:
        """Encrypt and persist ngrok auth token for a business."""
        cred_json = json.dumps({
            "auth_token": auth_token,
            "tunnel_url": "",  # Populated when tunnel starts
        })
        encrypted = encryption.encrypt(cred_json)

        # Upsert
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            account.encrypted_credentials = encrypted
            account.status = "active"
            account.external_account_id = auth_token[:8] + "****"
        else:
            account = ConnectedAccount(
                business_id=business_id,
                platform=PLATFORM,
                auth_method="api_key",
                encrypted_credentials=encrypted,
                status="active",
                external_account_id=auth_token[:8] + "****",
            )
            db.add(account)

        await db.flush()
        return account

    async def get_credentials(
        self, db: AsyncSession, business_id: UUID
    ) -> dict | None:
        """Retrieve and decrypt ngrok credentials, or None if not connected."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
            ConnectedAccount.status == "active",
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return None
        return json.loads(encryption.decrypt(account.encrypted_credentials))

    async def update_tunnel_url(
        self, db: AsyncSession, business_id: UUID, tunnel_url: str
    ) -> None:
        """Update the stored tunnel URL after starting ngrok."""
        creds = await self.get_credentials(db, business_id)
        if not creds:
            return

        creds["tunnel_url"] = tunnel_url
        encrypted = encryption.encrypt(json.dumps(creds))

        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if account:
            account.encrypted_credentials = encrypted
            await db.flush()

    async def disconnect(self, db: AsyncSession, business_id: UUID) -> bool:
        """Revoke stored credentials for a business."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            return False
        account.status = "revoked"
        await db.flush()
        return True

    # ── Status ──

    async def get_status(self, db: AsyncSession, business_id: UUID) -> dict:
        """Return connection status for the Connections page card."""
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.platform == PLATFORM,
        )
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if not account or account.status == "revoked":
            return {
                "platform": "ngrok",
                "connected": False,
                "auth_token_preview": None,
                "tunnel_url": None,
                "connected_at": None,
            }

        creds = json.loads(encryption.decrypt(account.encrypted_credentials))
        return {
            "platform": "ngrok",
            "connected": True,
            "auth_token_preview": creds.get("auth_token", "")[:8] + "****",
            "tunnel_url": creds.get("tunnel_url") or None,
            "connected_at": account.connected_at.isoformat() if account.connected_at else None,
        }

    # ── Tunnel management ──

    def _kill_existing(self) -> None:
        """Kill ALL ngrok processes (including zombies from previous server runs)."""
        import subprocess
        import time

        # 1. Try pyngrok's built-in kill
        try:
            from pyngrok import ngrok
            ngrok.kill()
        except Exception:
            pass

        # 2. Also kill any OS-level ngrok processes pyngrok doesn't know about
        try:
            subprocess.run(["pkill", "-f", "ngrok"], capture_output=True, timeout=5)
        except Exception:
            pass
        try:
            subprocess.run(["killall", "ngrok"], capture_output=True, timeout=5)
        except Exception:
            pass

        # Give ngrok servers a moment to release the session
        time.sleep(2)
        logger.info("Killed existing ngrok processes")

    async def start_tunnel(
        self, db: AsyncSession, business_id: UUID, port: int = 8000
    ) -> dict:
        """
        Start an ngrok tunnel using the stored auth token.

        Kills any existing ngrok process first to avoid the
        "1 simultaneous session" error on free plans.

        Returns {"tunnel_url": "https://xxxx.ngrok-free.app", "status": "running"}
        """
        creds = await self.get_credentials(db, business_id)
        if not creds:
            raise ValueError("ngrok not connected — add your auth token first")

        auth_token = creds["auth_token"]

        try:
            from pyngrok import ngrok, conf

            # Kill any existing ngrok process first (avoids ERR_NGROK_108)
            self._kill_existing()

            # Configure auth token
            conf.get_default().auth_token = auth_token

            # Start tunnel
            tunnel = ngrok.connect(port, "http")
            tunnel_url = tunnel.public_url

            # Ensure https
            if tunnel_url.startswith("http://"):
                tunnel_url = tunnel_url.replace("http://", "https://")

            # Store the tunnel URL
            await self.update_tunnel_url(db, business_id, tunnel_url)

            logger.info(f"ngrok tunnel started: {tunnel_url} → localhost:{port}")
            return {"tunnel_url": tunnel_url, "status": "running"}

        except ImportError:
            raise ValueError(
                "pyngrok not installed. Run: pip install pyngrok"
            )
        except Exception as e:
            logger.error(f"Failed to start ngrok tunnel: {e}")
            raise ValueError(f"Failed to start ngrok tunnel: {str(e)}")

    async def stop_tunnel(self) -> None:
        """Stop all ngrok tunnels."""
        try:
            from pyngrok import ngrok
            for tunnel in ngrok.get_tunnels():
                ngrok.disconnect(tunnel.public_url)
            ngrok.kill()
            logger.info("ngrok tunnels stopped")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Error stopping ngrok: {e}")

    async def get_active_tunnel(self) -> str | None:
        """Check if an ngrok tunnel is currently running and return its URL."""
        try:
            from pyngrok import ngrok
            tunnels = ngrok.get_tunnels()
            for t in tunnels:
                if t.public_url and "https" in t.public_url:
                    return t.public_url
                if t.public_url:
                    return t.public_url.replace("http://", "https://")
            return None
        except (ImportError, Exception):
            return None


ngrok_service = NgrokService()
