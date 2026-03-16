"""
FastAPI application entry point.

Run with:  uvicorn app.main:app --reload

Architecture:
  - 18 tables: users, businesses, business_members, connected_accounts,
    conversations, conversation_messages, notifications,
    departments, employees, contacts, interactions,
    business_phone_lines, payments, phone_settings, jobs,
    media_files, content_posts (+org_templates legacy)
  - 5 departments: Marketing, Sales, Operations, Billing, Administration
  - 12 AI employees — system prompts stored in DB (employees.system_prompt)
  - Integrations: Twilio, Stripe, OAuth platforms
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# ── Core routers ──
from app.core.routers import (
    auth, businesses, chat, cli, health,
    notifications, organization, platforms,
)
# ── Department routers ──
from app.marketing.routers import contacts, tracking_routing, email, content
from app.sales import routers as sales
from app.finance.routers import payments, billing, reports, stripe_router
from app.admin.routers import twilio, ngrok, whatsapp
from app.it.routers import internal_tools, terminal


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    import logging
    _logger = logging.getLogger(__name__)

    # ── Startup ──
    # 0. Ensure departments table has phone routing columns
    from sqlalchemy import text as sa_text
    from app.database import engine
    async with engine.begin() as conn:
        await conn.execute(sa_text(
            "ALTER TABLE departments ADD COLUMN IF NOT EXISTS forward_number VARCHAR(20)"
        ))
        await conn.execute(sa_text(
            "ALTER TABLE departments ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true"
        ))
        _logger.info("✅ departments table: forward_number + enabled columns ensured")

    # 1. Check Claude CLI readiness (non-blocking — logs warnings if not ready)
    from app.core.services.claude_cli_service import claude_cli
    cli_status = await claude_cli.startup_check()
    if not cli_status["installed"]:
        _logger.warning(
            "⚠️  Claude CLI not installed — chat will fail until installed. "
            f"{cli_status['message']}"
        )

    # 2. Start APScheduler + Twilio ↔ DB sync (every 15 min)
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    app.state.scheduler = _scheduler

    from app.admin.services.twilio_sync import start_twilio_sync
    await start_twilio_sync(_scheduler)

    # 4. Auto-reconnect ngrok tunnel if previously connected
    try:
        from app.admin.services.ngrok_service import ngrok_service
        from app.database import async_session_factory
        from sqlalchemy import select
        from app.core.models.connected_account import ConnectedAccount

        async with async_session_factory() as db:
            result = await db.execute(
                select(ConnectedAccount).where(
                    ConnectedAccount.platform == "ngrok",
                    ConnectedAccount.status == "active",
                    ConnectedAccount.department_id == None,  # ngrok is shared, not department-scoped
                )
            )
            ngrok_account = result.scalar_one_or_none()
            if ngrok_account:
                _logger.info("🔗 Found active ngrok connection — auto-starting tunnel...")
                try:
                    tunnel_result = await ngrok_service.start_tunnel(
                        db, ngrok_account.business_id, port=8000
                    )
                    tunnel_url = tunnel_result["tunnel_url"]
                    _logger.info(f"🔗 ngrok tunnel auto-started: {tunnel_url}")

                    # Persist webhook URL to phone_settings (DB is source of truth)
                    from app.admin.models import PhoneSettings
                    ps_result = await db.execute(
                        select(PhoneSettings).where(
                            PhoneSettings.business_id == ngrok_account.business_id
                        )
                    )
                    ps = ps_result.scalar_one_or_none()
                    if ps:
                        ps.webhook_base_url = tunnel_url
                    else:
                        db.add(PhoneSettings(
                            business_id=ngrok_account.business_id,
                            webhook_base_url=tunnel_url,
                        ))

                    # Auto-configure webhooks for all active phone lines (mainline + tracking)
                    from app.marketing.models import BusinessPhoneLine
                    from app.admin.services.twilio_service import twilio_service

                    biz_id = ngrok_account.business_id
                    voice_url = f"{tunnel_url}{settings.api_prefix}/twilio/voice?business_id={biz_id}"
                    status_url = f"{tunnel_url}{settings.api_prefix}/twilio/call-status?business_id={biz_id}"

                    tn_result = await db.execute(
                        select(BusinessPhoneLine).where(
                            BusinessPhoneLine.business_id == biz_id,
                            BusinessPhoneLine.active == True,
                        )
                    )
                    tracking_numbers = tn_result.scalars().all()

                    # Auto-resolve any null SIDs by matching phone numbers from Twilio API
                    null_sid_numbers = [tn for tn in tracking_numbers if not tn.twilio_number_sid]
                    if null_sid_numbers:
                        try:
                            twilio_numbers = await twilio_service.list_phone_numbers(db, biz_id)
                            sid_lookup = {n["phone_number"]: n["sid"] for n in twilio_numbers}
                            for tn in null_sid_numbers:
                                if tn.twilio_number in sid_lookup:
                                    tn.twilio_number_sid = sid_lookup[tn.twilio_number]
                                    _logger.info(f"Auto-resolved SID for {tn.twilio_number}: {tn.twilio_number_sid}")
                        except Exception as e:
                            _logger.warning(f"Failed to resolve null SIDs from Twilio API: {e}")

                    for tn in tracking_numbers:
                        if tn.twilio_number_sid:
                            try:
                                await twilio_service.configure_webhook(
                                    db=db, business_id=biz_id,
                                    number_sid=tn.twilio_number_sid,
                                    voice_url=voice_url,
                                    status_callback_url=status_url,
                                )
                                _logger.info(f"Configured webhook for {tn.twilio_number}")
                            except Exception as e:
                                _logger.warning(f"Failed to configure webhook for {tn.twilio_number}: {e}")

                    await db.commit()
                except Exception as e:
                    _logger.warning(f"⚠️  ngrok auto-start failed (non-fatal): {e}")
    except Exception as e:
        _logger.warning(f"⚠️  ngrok startup check failed (non-fatal): {e}")

    yield
    # ── Shutdown ──
    try:
        from app.admin.services.ngrok_service import ngrok_service as _ngrok
        await _ngrok.stop_tunnel()
    except Exception:
        pass
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)
    from app.database import engine
    await engine.dispose()


app = FastAPI(
    title="Workforce API",
    description="Department-centric AI workforce automation platform",
    version="3.0.0",
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core / Platform ──
app.include_router(health.router, prefix=settings.api_prefix, tags=["Health"])
app.include_router(auth.router, prefix=settings.api_prefix, tags=["Auth"])
app.include_router(businesses.router, prefix=settings.api_prefix, tags=["Businesses"])
app.include_router(platforms.router, prefix=settings.api_prefix, tags=["Platforms"])
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(cli.router, prefix=settings.api_prefix)
app.include_router(organization.router, prefix=settings.api_prefix)
# ── Platform Tools (terminal, internal API proxy) ──
app.include_router(terminal.router, prefix=settings.api_prefix)
app.include_router(internal_tools.router, prefix=settings.api_prefix)

# ── Marketing ──
app.include_router(contacts.router, prefix=settings.api_prefix)
app.include_router(contacts.phone_lines_router, prefix=settings.api_prefix)
app.include_router(tracking_routing.router, prefix=settings.api_prefix)
app.include_router(email.router, prefix=settings.api_prefix)
app.include_router(content.router, prefix=settings.api_prefix)

# ── Sales ──
app.include_router(sales.router, prefix=settings.api_prefix)

# ── Billing ──
app.include_router(payments.router, prefix=settings.api_prefix)
app.include_router(billing.router, prefix=settings.api_prefix)
app.include_router(stripe_router.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)

# ── Administration ──
app.include_router(twilio.router, prefix=settings.api_prefix)
app.include_router(whatsapp.router, prefix=settings.api_prefix)
app.include_router(ngrok.router, prefix=settings.api_prefix)

