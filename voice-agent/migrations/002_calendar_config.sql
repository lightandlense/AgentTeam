-- Migration 002: Per-client calendar configuration columns
--
-- Adds 5 columns to the clients table that drive all calendar operations:
--   working_days          — ISO weekday numbers the business is open (1=Mon … 7=Sun)
--   business_hours        — daily open/close window as 24-hour HH:MM strings
--   slot_duration_minutes — length of each bookable appointment slot
--   buffer_minutes        — gap required between consecutive appointments
--   lead_time_minutes     — minimum notice required before the earliest bookable slot
--
-- All statements use ADD COLUMN IF NOT EXISTS so the migration is safe to re-run.

ALTER TABLE clients ADD COLUMN IF NOT EXISTS working_days INTEGER[] NOT NULL DEFAULT '{1,2,3,4,5}';

ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_hours JSONB NOT NULL DEFAULT '{"start": "09:00", "end": "17:00"}';

ALTER TABLE clients ADD COLUMN IF NOT EXISTS slot_duration_minutes INTEGER NOT NULL DEFAULT 60;

ALTER TABLE clients ADD COLUMN IF NOT EXISTS buffer_minutes INTEGER NOT NULL DEFAULT 0;

ALTER TABLE clients ADD COLUMN IF NOT EXISTS lead_time_minutes INTEGER NOT NULL DEFAULT 60;
