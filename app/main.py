"""
FastAPI application entry point.

Run with:  func start --port 8000   (Azure Functions host)

Architecture:
  - 21 tables: users, businesses, business_members, roles, business_member_roles,
    connected_accounts, conversations, conversation_messages, notifications,
    departments, employees, contacts, interactions,
    payments, phone_settings, jobs, staff, job_templates,
    media_files, content_posts (+org_templates legacy)
  - 5 departments: Marketing, Sales, Operations, Billing, Administration
  - 12 AI employees — system prompts stored in DB (employees.system_prompt)
  - Integrations: Azure Communication Services, Stripe, OAuth platforms
  - Phone number ownership: phone_lines table (phone_number, line_type, label) — ACS is source of truth
  - RBAC: roles table (system + custom) + business_member_roles junction
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# ── Core routers ──
from app.core.routers import (
    auth, businesses, chat, health,
    notifications, organization, platforms, agent_tools, dashboard, maps,
)
# ── Department routers ──
from app.marketing.routers import contacts, tracking_routing, email, content, organizations, forms
from app.sales import routers as sales
from app.finance.routers import payments, billing, reports, stripe_router
from app.admin.routers import acs
from app.operations.routers import staff as ops_staff, job_templates as ops_templates
from app.core.routers import team as team_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    import logging
    _logger = logging.getLogger(__name__)

    # ── Startup ──
    # 0. Create all tables (idempotent — safe on every restart, bootstraps fresh DBs)
    from app.database import Base, engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _logger.info("✅ Database schema: all tables ensured")

    from sqlalchemy import text as sa_text
    async with engine.begin() as conn:
        await conn.execute(sa_text(
            "ALTER TABLE departments ADD COLUMN IF NOT EXISTS forward_number VARCHAR(20)"
        ))
        await conn.execute(sa_text(
            "ALTER TABLE departments ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true"
        ))
        _logger.info("✅ departments table: forward_number + enabled columns ensured")
        # organizations FK on contacts (existing table — create_all won't add new columns)
        await conn.execute(sa_text(
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS organization_id UUID "
            "REFERENCES organizations(id) ON DELETE SET NULL"
        ))
        await conn.execute(sa_text(
            "CREATE INDEX IF NOT EXISTS contacts_organization_id_idx ON contacts(organization_id)"
        ))
        _logger.info("✅ contacts.organization_id FK ensured")
        # New jobs columns for staff dispatch + templates (create_all won't ALTER existing table)
        await conn.execute(sa_text(
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS template_id UUID "
            "REFERENCES job_templates(id) ON DELETE SET NULL"
        ))
        await conn.execute(sa_text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS template_data JSONB"))
        await conn.execute(sa_text(
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS assigned_to UUID "
            "REFERENCES staff(id) ON DELETE SET NULL"
        ))
        await conn.execute(sa_text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS service_address TEXT"))
        await conn.execute(sa_text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ"))
        await conn.execute(sa_text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ"))
        _logger.info("✅ jobs: template/dispatch columns ensured")
        # contacts: assigned_to (sales rep assignment)
        await conn.execute(sa_text(
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS assigned_to UUID "
            "REFERENCES users(id) ON DELETE SET NULL"
        ))
        await conn.execute(sa_text(
            "CREATE INDEX IF NOT EXISTS contacts_assigned_to_idx ON contacts(assigned_to)"
        ))
        _logger.info("✅ contacts.assigned_to ensured")
        await conn.execute(sa_text(
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS contact_role VARCHAR(100)"
        ))
        _logger.info("✅ contacts.contact_role ensured")
        # organizations: address columns
        await conn.execute(sa_text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(255)"))
        await conn.execute(sa_text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS city VARCHAR(100)"))
        await conn.execute(sa_text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS state VARCHAR(100)"))
        await conn.execute(sa_text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS zip_code VARCHAR(20)"))
        await conn.execute(sa_text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS country VARCHAR(100)"))
        _logger.info("✅ organizations: address columns ensured")
        # staff: home address + geocoded coordinates for route planning
        await conn.execute(sa_text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS home_address TEXT"))
        await conn.execute(sa_text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS home_lat FLOAT"))
        await conn.execute(sa_text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS home_lng FLOAT"))
        _logger.info("✅ staff: home_address/lat/lng ensured")

    # 2. Seed system roles (idempotent — raw SQL; CTE avoids asyncpg ambiguous-param errors)
    import json as _json
    from app.core.models.role import SYSTEM_ROLES
    async with engine.begin() as conn:
        for role_name, description, permissions in SYSTEM_ROLES:
            await conn.execute(sa_text("""
                WITH p AS (SELECT
                    CAST(:rname AS varchar)  AS rname,
                    CAST(:desc  AS text)     AS desc,
                    CAST(:perms AS jsonb)    AS perms
                )
                INSERT INTO roles (name, description, permissions, is_system, business_id)
                SELECT p.rname, p.desc, p.perms, true, NULL
                FROM p
                WHERE NOT EXISTS (
                    SELECT 1 FROM roles WHERE name = p.rname AND business_id IS NULL
                )
            """), {
                "rname": role_name,
                "desc": description,
                "perms": _json.dumps(permissions),
            })
    _logger.info("✅ System roles seeded")

    # 3. Check Foundry client readiness (non-blocking — logs warnings if not ready)
    from app.core.services.openai_service import openai_service
    foundry_status = await openai_service.startup_check()
    if not foundry_status["ready"]:
        _logger.warning(
            "⚠️  Azure AI Foundry not ready — chat will fail until configured. "
            f"{foundry_status['message']}"
        )

    yield
    # ── Shutdown ──
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
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(maps.router, prefix=settings.api_prefix)
# ── Marketing / CRM ──
app.include_router(contacts.router, prefix=settings.api_prefix)
app.include_router(organizations.router, prefix=settings.api_prefix)
app.include_router(forms.router, prefix=settings.api_prefix)
app.include_router(ops_staff.router, prefix=settings.api_prefix)
app.include_router(ops_templates.router, prefix=settings.api_prefix)
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
app.include_router(acs.router, prefix=settings.api_prefix)
app.include_router(team_router.router, prefix=settings.api_prefix)

