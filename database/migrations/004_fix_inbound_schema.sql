-- ============================================
-- Migration 004: Fix schema drift for inbound voice flow
-- ============================================
-- This migration fixes critical issues where backend code (twilio.ts inbound flow,
-- emergencyBlocks.ts, appointments.ts) references columns that did not exist in
-- the schema. Without this migration, /api/twilio/inbound throws on a fresh DB.
--
-- Changes:
--   1. voice_calls.direction         -- inbound/outbound flag
--   2. voice_calls.patient_phone     -- caller's phone for inbound calls
--   3. voice_calls.appointment_id    -- drop NOT NULL (inbound calls have no appt yet)
--   4. Indexes for common lookups (users.phone, appt time ranges)
--   5. Partial unique index to prevent provider double-booking
--
-- Idempotent: safe to run multiple times.
-- ============================================

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────
-- 1. voice_calls: add inbound-flow columns
-- ──────────────────────────────────────────────────────────────────────────

-- Add direction column with CHECK constraint
ALTER TABLE voice_calls
    ADD COLUMN IF NOT EXISTS direction TEXT
        CHECK (direction IN ('inbound', 'outbound'))
        DEFAULT 'outbound';

-- Backfill existing rows: anything created before this migration is outbound
UPDATE voice_calls
SET direction = 'outbound'
WHERE direction IS NULL;

-- Add patient_phone for inbound callers (E.164 format, e.g. +14155551234)
ALTER TABLE voice_calls
    ADD COLUMN IF NOT EXISTS patient_phone TEXT;

-- ──────────────────────────────────────────────────────────────────────────
-- 2. voice_calls.appointment_id: allow NULL
-- ──────────────────────────────────────────────────────────────────────────
-- Inbound calls create the voice_calls row BEFORE the appointment exists.
-- The appointment is only inserted after the call ends and Groq extracts details.
-- Schema currently has appointment_id NOT NULL — this blocks the inbound INSERT.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'voice_calls'
          AND column_name = 'appointment_id'
          AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE voice_calls ALTER COLUMN appointment_id DROP NOT NULL;
    END IF;
END
$$;

-- ──────────────────────────────────────────────────────────────────────────
-- 3. Indexes for the inbound flow
-- ──────────────────────────────────────────────────────────────────────────

-- Inbound code does: SELECT id FROM users WHERE phone = $1 LIMIT 1
-- Without this index, every inbound call triggers a full table scan on users.
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

-- voice_calls lookups by direction (admin dashboard, analytics)
CREATE INDEX IF NOT EXISTS idx_voice_calls_direction ON voice_calls(direction);

-- voice_calls lookup by caller phone (returning callers, call history)
CREATE INDEX IF NOT EXISTS idx_voice_calls_patient_phone ON voice_calls(patient_phone);

-- Appointment slot conflict checks scan by time range
CREATE INDEX IF NOT EXISTS idx_appointments_start_end
    ON appointments(start_time, end_time);

-- Appointment lookups by provider on a specific date (availability tool)
CREATE INDEX IF NOT EXISTS idx_appointments_provider_start
    ON appointments(provider_id, start_time);

-- ──────────────────────────────────────────────────────────────────────────
-- 4. Prevent provider double-booking
-- ──────────────────────────────────────────────────────────────────────────
-- Two concurrent inbound calls could currently book the same provider at
-- the same start_time. This partial unique index makes that impossible.
-- Cancelled and completed slots are excluded so the same time can be reused.

CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_no_double_book
    ON appointments(provider_id, start_time)
    WHERE status IN ('pending', 'confirmed') AND provider_id IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────────
-- Note on appointments.created_via
-- ──────────────────────────────────────────────────────────────────────────
-- The schema comment lists 'chatbot', 'web', 'phone', 'walk_in' but the inbound
-- code already inserts 'voice_inbound'. The column has NO CHECK constraint, so
-- inserts succeed today. We are intentionally NOT adding a CHECK here because
-- it would break older rows. Document the supported values in the master schema
-- and rely on application-layer validation.
--
-- Supported values: chatbot, web, phone, walk_in, voice_inbound, voice_outbound
-- ──────────────────────────────────────────────────────────────────────────

COMMIT;
