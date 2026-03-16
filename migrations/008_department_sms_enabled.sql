-- Add sms_enabled column to departments table
-- Controls per-department SMS notifications (caller name + reason) after IVR routing
ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS sms_enabled BOOLEAN NOT NULL DEFAULT FALSE;
