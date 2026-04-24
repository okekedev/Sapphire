"""
Migration: add organizations table, contacts.organization_id FK, and contact_forms table.

Run once:
    python infra/migrations/add_organizations_and_forms.py
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
        # 1. Create organizations table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                name        VARCHAR(255) NOT NULL,
                domain      VARCHAR(255),
                industry    VARCHAR(100),
                website     VARCHAR(500),
                notes       TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS organizations_business_id_idx ON organizations(business_id);
        """)
        print("✓ organizations table created")

        # 2. Add organization_id FK to contacts
        await conn.execute("""
            ALTER TABLE contacts
                ADD COLUMN IF NOT EXISTS organization_id UUID
                    REFERENCES organizations(id) ON DELETE SET NULL;
            CREATE INDEX IF NOT EXISTS contacts_organization_id_idx ON contacts(organization_id);
        """)
        print("✓ contacts.organization_id FK added")

        # 3. Create contact_forms table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_forms (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                business_id  UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                name         VARCHAR(255) NOT NULL,
                redirect_url VARCHAR(500),
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS contact_forms_business_id_idx ON contact_forms(business_id);
        """)
        print("✓ contact_forms table created")

        # Confirm
        orgs_cols = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'organizations' ORDER BY ordinal_position
        """)
        contacts_cols = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'contacts' AND column_name = 'organization_id'
        """)
        forms_cols = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'contact_forms' ORDER BY ordinal_position
        """)
        print("organizations columns:", [r["column_name"] for r in orgs_cols])
        print("contacts.organization_id present:", bool(contacts_cols))
        print("contact_forms columns:", [r["column_name"] for r in forms_cols])

    finally:
        await conn.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
