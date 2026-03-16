-- Migration 009: Simplify A2P — move SIDs to phone_settings, drop a2p_registrations
-- A2P 10DLC registration is done in Twilio Console. We only need the SIDs to query status.

-- Add A2P SIDs to phone_settings
ALTER TABLE phone_settings ADD COLUMN IF NOT EXISTS messaging_service_sid VARCHAR(50);
ALTER TABLE phone_settings ADD COLUMN IF NOT EXISTS brand_registration_sid VARCHAR(50);

-- Migrate the SIDs from a2p_registrations if they exist
UPDATE phone_settings ps
SET messaging_service_sid = a2p.messaging_service_sid,
    brand_registration_sid = a2p.brand_registration_sid
FROM a2p_registrations a2p
WHERE a2p.business_id = ps.business_id
  AND a2p.messaging_service_sid IS NOT NULL;

-- Drop the a2p_registrations table
DROP TABLE IF EXISTS a2p_registrations;
