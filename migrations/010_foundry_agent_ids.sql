-- Add Foundry agent IDs to businesses table.
-- Stores a JSON map of { agent_name: foundry_agent_id } populated at deployment time.
-- Example: { "grace": "asst_xxx", "riley": "asst_yyy", ... }

ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS foundry_agent_ids JSONB;
