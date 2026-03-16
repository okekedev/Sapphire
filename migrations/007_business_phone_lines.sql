-- Migration 007: Rename tracking_numbers → business_phone_lines
-- Replace is_mainline boolean with line_type enum column
--
-- Safe migration: single transaction, no data loss
-- Rollback: rename table back + re-add is_mainline from line_type

BEGIN;

-- 1. Rename table
ALTER TABLE tracking_numbers RENAME TO business_phone_lines;

-- 2. Add line_type column with default 'tracking'
ALTER TABLE business_phone_lines
    ADD COLUMN line_type VARCHAR(20) NOT NULL DEFAULT 'tracking';

-- 3. Backfill: migrate is_mainline boolean → line_type enum
UPDATE business_phone_lines SET line_type = 'mainline' WHERE is_mainline = true;

-- 4. Drop is_mainline column
ALTER TABLE business_phone_lines DROP COLUMN is_mainline;

-- 5. Make campaign_name nullable (mainline doesn't need a campaign)
ALTER TABLE business_phone_lines ALTER COLUMN campaign_name DROP NOT NULL;

-- 6. Add index on line_type for efficient filtering
CREATE INDEX idx_business_phone_lines_line_type ON business_phone_lines (line_type);

COMMIT;
