"""
Migration: drop stale columns from phone_settings.

Removes Twilio-era and legacy columns that are no longer used:
  - messaging_service_sid  (A2P 10DLC Twilio SID — ACS replaced Twilio)
  - brand_registration_sid (TCR brand SID — same)
  - sms_enabled            (legacy toggle — sms_enabled lives on departments table)
  - whatsapp_enabled       (legacy — moved to departments table)
  - whatsapp_from_number   (legacy — never used after WhatsApp was deprioritized)

Run once:
    python infra/migrations/drop_phone_settings_stale_cols.py
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
            ALTER TABLE phone_settings
                DROP COLUMN IF EXISTS messaging_service_sid,
                DROP COLUMN IF EXISTS brand_registration_sid,
                DROP COLUMN IF EXISTS sms_enabled,
                DROP COLUMN IF EXISTS whatsapp_enabled,
                DROP COLUMN IF EXISTS whatsapp_from_number;
        """)
        print("✓ Dropped stale columns from phone_settings")

        # Confirm
        cols = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'phone_settings'
            ORDER BY ordinal_position;
        """)
        print("Remaining columns:", [r["column_name"] for r in cols])
    finally:
        await conn.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
