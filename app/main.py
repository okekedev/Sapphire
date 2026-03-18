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
    auth, businesses, chat, health,
    notifications, organization, platforms, agent_tools,
)
# ── Department routers ──
from app.marketing.routers import contacts, tracking_routing, email, content
from app.sales import routers as sales
from app.finance.routers import payments, billing, reports, stripe_router
from app.admin.routers import twilio


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

    # 1. Check Foundry client readiness (non-blocking — logs warnings if not ready)
    from app.core.services.anthropic_service import anthropic_service
    foundry_status = await anthropic_service.startup_check()
    if not foundry_status["ready"]:
        _logger.warning(
            "⚠️  Azure AI Foundry not ready — chat will fail until configured. "
            f"{foundry_status['message']}"
        )

    # 2. Start APScheduler + Twilio ↔ DB sync (every 15 min)
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    app.state.scheduler = _scheduler

    from app.admin.services.twilio_sync import start_twilio_sync
    await start_twilio_sync(_scheduler)

    yield
    # ── Shutdown ──
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
app.include_router(agent_tools.router, prefix=settings.api_prefix, tags=["Agent Tools"])
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(organization.router, prefix=settings.api_prefix)
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

