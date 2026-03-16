"""Twilio Client (WebRTC) service — browser-based outbound calling.

Handles:
  - TwiML App creation/management for outbound calls
  - Access Token generation for Twilio Voice SDK in the browser

Flow:
  1. Frontend requests a client token  →  GET /twilio/client-token
  2. Service creates/retrieves a TwiML App (cached per business)
  3. Returns a short-lived JWT Access Token with Voice Grant
  4. Browser connects via @twilio/voice-sdk → Twilio hits our outbound-voice webhook
  5. Webhook returns TwiML to dial the target number using the campaign caller ID
  6. Recording + transcription + AI summary reuse existing _process_call_pipeline
"""

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

from app.core.models.connected_account import ConnectedAccount
from app.admin.services.twilio_service import twilio_service
from app.core.services.encryption_service import encryption

logger = logging.getLogger(__name__)

PLATFORM = "twilio"

# In-memory cache: business_id → TwiML App SID
_twiml_app_cache: dict[str, str] = {}


async def _get_twilio_client_and_creds(
    db: AsyncSession, business_id: UUID
) -> tuple[Client, dict]:
    """Get an authenticated Twilio REST client + credential dict."""
    creds = await twilio_service.get_credentials(db, business_id)
    if not creds:
        raise ValueError("Twilio not connected for this business")
    client = Client(creds["account_sid"], creds["auth_token"])
    return client, creds


async def _persist_twiml_app_sid(
    db: AsyncSession, business_id: UUID, twiml_app_sid: str
) -> None:
    """Save the TwiML App SID into the encrypted credentials so it survives restarts.

    Twilio is a shared service (department_id=NULL).
    """
    stmt = select(ConnectedAccount).where(
        ConnectedAccount.business_id == business_id,
        ConnectedAccount.platform == PLATFORM,
        ConnectedAccount.status == "active",
        ConnectedAccount.department_id == None,  # Shared service
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()
    if not account:
        return

    # Decrypt existing creds, add twiml_app_sid, re-encrypt
    creds = json.loads(encryption.decrypt(account.encrypted_credentials))
    creds["twiml_app_sid"] = twiml_app_sid
    account.encrypted_credentials = encryption.encrypt(json.dumps(creds))
    await db.flush()


async def ensure_twiml_app(
    db: AsyncSession, business_id: UUID, webhook_base_url: str
) -> str:
    """Create or retrieve a TwiML App for outbound calls.

    The TwiML App tells Twilio where to POST when the browser client
    initiates a call. We set the voice URL to our outbound-voice webhook.

    Returns the TwiML App SID.
    """
    cache_key = str(business_id)

    # Check in-memory cache first
    if cache_key in _twiml_app_cache:
        return _twiml_app_cache[cache_key]

    client, creds = await _get_twilio_client_and_creds(db, business_id)

    # Check if TwiML app SID is already stored in credentials
    existing_sid = creds.get("twiml_app_sid")
    if existing_sid:
        try:
            client.applications(existing_sid).fetch()
            _twiml_app_cache[cache_key] = existing_sid
            return existing_sid
        except Exception:
            logger.warning(
                "Stored TwiML app %s not found, creating new one", existing_sid
            )

    # Create a new TwiML App
    voice_url = (
        f"{webhook_base_url}/api/v1/twilio/outbound-voice"
        f"?business_id={business_id}"
    )
    app = client.applications.create(
        friendly_name=f"Platform Outbound - {str(business_id)[:8]}",
        voice_url=voice_url,
        voice_method="POST",
    )

    twiml_app_sid = app.sid
    _twiml_app_cache[cache_key] = twiml_app_sid

    # Persist so it survives server restarts
    await _persist_twiml_app_sid(db, business_id, twiml_app_sid)

    logger.info("Created TwiML App %s for business %s", twiml_app_sid, business_id)
    return twiml_app_sid


async def generate_client_token(
    db: AsyncSession,
    business_id: UUID,
    identity: str,
    webhook_base_url: str,
) -> str:
    """Generate a short-lived Access Token for the Twilio Voice SDK.

    Args:
        db: Database session
        business_id: The business making the call
        identity: Unique caller identity (e.g. "user-{user_id}")
        webhook_base_url: Base URL for webhooks

    Returns:
        JWT token string for the browser SDK
    """
    _, creds = await _get_twilio_client_and_creds(db, business_id)
    twiml_app_sid = await ensure_twiml_app(db, business_id, webhook_base_url)

    # Create Access Token (using Account SID + Auth Token as API key)
    token = AccessToken(
        creds["account_sid"],
        creds["account_sid"],   # API Key SID (using account SID)
        creds["auth_token"],    # API Key Secret (using auth token)
        identity=identity,
        ttl=3600,  # 1 hour
    )

    # Add Voice Grant for outbound calling
    voice_grant = VoiceGrant(
        outgoing_application_sid=twiml_app_sid,
        incoming_allow=False,
    )
    token.add_grant(voice_grant)

    return token.to_jwt()
