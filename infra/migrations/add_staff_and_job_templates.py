"""
Migration: add staff table, job_templates table, and new columns on jobs.

Run once:
    python infra/migrations/add_staff_and_job_templates.py
"""

import asyncio
import asyncpg
from azure.identity.aio import DefaultAzureCredential


async def main() -> None:
    credential = DefaultAzureCredential()
    token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

    conn = await asyncpg.connect(
        host="pg-sapphire-prod.postgres.database.azure.com",
        port=5432,
        database="workforce",
        user="christian@okeke.us",
        password=token.token,
        ssl="require",
    )

    try:
        # 1. Create staff table (human employees of the business — distinct from AI employees)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                business_id  UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                first_name   VARCHAR(100) NOT NULL,
                last_name    VARCHAR(100),
                phone        VARCHAR(30),
                email        VARCHAR(255),
                role         VARCHAR(30) NOT NULL DEFAULT 'technician',
                color        VARCHAR(7) DEFAULT '#6366f1',
                is_active    BOOLEAN NOT NULL DEFAULT true,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS ix_staff_business_id ON staff(business_id);
        """)
        print("✓ staff table created")

        # 2. Create job_templates table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS job_templates (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                business_id          UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                name                 VARCHAR(255) NOT NULL,
                description          TEXT,
                requires_scheduling  BOOLEAN NOT NULL DEFAULT false,
                requires_assignment  BOOLEAN NOT NULL DEFAULT false,
                requires_dispatch    BOOLEAN NOT NULL DEFAULT false,
                schema               JSONB NOT NULL DEFAULT '{"sections":[]}',
                is_active            BOOLEAN NOT NULL DEFAULT true,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS ix_job_templates_business_id ON job_templates(business_id);
        """)
        print("✓ job_templates table created")

        # 3. Add new columns to jobs
        await conn.execute("""
            ALTER TABLE jobs
                ADD COLUMN IF NOT EXISTS template_id      UUID REFERENCES job_templates(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS template_data    JSONB,
                ADD COLUMN IF NOT EXISTS assigned_to      UUID REFERENCES staff(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS service_address  TEXT,
                ADD COLUMN IF NOT EXISTS scheduled_at     TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS dispatched_at    TIMESTAMPTZ;
        """)
        print("✓ jobs columns added (template_id, template_data, assigned_to, service_address, scheduled_at, dispatched_at)")

        # Verify
        staff_cols = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'staff' ORDER BY ordinal_position
        """)
        template_cols = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'job_templates' ORDER BY ordinal_position
        """)
        jobs_new_cols = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'jobs' AND column_name IN
              ('template_id','template_data','assigned_to','service_address','scheduled_at','dispatched_at')
            ORDER BY ordinal_position
        """)
        print("staff columns:", [r["column_name"] for r in staff_cols])
        print("job_templates columns:", [r["column_name"] for r in template_cols])
        print("jobs new columns:", [r["column_name"] for r in jobs_new_cols])

    finally:
        await conn.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
