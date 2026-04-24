"""
Migration: drop WhatsApp columns from departments.

Removes Twilio-era WhatsApp columns that are no longer used:
  - whatsapp_enabled      (Twilio WhatsApp toggle — ACS replaced Twilio)
  - whatsapp_sender_sid   (XE... Twilio Sender SID — ACS has no equivalent)
  - whatsapp_sender_status (Twilio sender verification status)

Run once:
    python infra/migrations/drop_departments_whatsapp_cols.py
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
        await conn.execute("""
            ALTER TABLE departments
                DROP COLUMN IF EXISTS whatsapp_enabled,
                DROP COLUMN IF EXISTS whatsapp_sender_sid,
                DROP COLUMN IF EXISTS whatsapp_sender_status;
        """)
        print("✓ Dropped whatsapp_enabled, whatsapp_sender_sid, whatsapp_sender_status from departments")

        cols = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'departments'
            ORDER BY ordinal_position;
        """)
        print("Remaining columns:", [r["column_name"] for r in cols])
    finally:
        await conn.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
