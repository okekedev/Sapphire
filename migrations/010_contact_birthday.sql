-- Migration 010: Add birthday column to contacts table
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS birthday DATE;
