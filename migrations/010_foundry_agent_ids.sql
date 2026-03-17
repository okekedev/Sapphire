-- Add Foundry agent IDs to businesses table (one column per agent).
-- Populated by deploy_agents.py at business signup.

ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS foundry_agent_grace  VARCHAR,
    ADD COLUMN IF NOT EXISTS foundry_agent_ivy    VARCHAR,
    ADD COLUMN IF NOT EXISTS foundry_agent_quinn  VARCHAR,
    ADD COLUMN IF NOT EXISTS foundry_agent_luna   VARCHAR,
    ADD COLUMN IF NOT EXISTS foundry_agent_morgan VARCHAR,
    ADD COLUMN IF NOT EXISTS foundry_agent_riley  VARCHAR;
