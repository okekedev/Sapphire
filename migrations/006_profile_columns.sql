-- Migration 006: Replace company_profile JSONB with dedicated columns
-- Run in Supabase SQL Editor

ALTER TABLE businesses ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS services TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS target_audience TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS online_presence TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS brand_voice TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS goals TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS competitive_landscape TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS profile_source VARCHAR(50);

ALTER TABLE businesses DROP COLUMN IF EXISTS company_profile;
