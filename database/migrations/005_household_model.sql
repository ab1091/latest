-- ============================================
-- Migration 005: Household model (phone_accounts + patients)
-- ============================================
-- Why this exists:
--   The current inbound flow creates one fake-email "user" per phone number
--   (e.g. +19735551234@inbound.call). That breaks two real-world cases:
--
--     1. Dev/QA: one tester calls 10 times from the same RingCentral number
--        with 10 different test names → all collapse onto a single user row.
--     2. Production: a household shares one phone (mom books for kid, dad,
--        herself, grandparent) → all four patients collapse onto one user.
--
--   This migration introduces a household-aware model where:
--     - phone_accounts  represents a phone number (the household)
--     - patients        represents a real person under that phone account
--   Appointments link to a patient (a person), not a phone (a household).
--
-- Strategy:
--   Additive only. We add patient_id alongside the existing user_id and leave
--   user_id intact so legacy code paths keep working. New code (inbound flow,
--   CRM sync) starts using patient_id immediately. A future migration (007+)
--   can drop user_id once nothing references it.
--
-- Idempotent: safe to run multiple times.
-- ============================================

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────
-- 1. phone_accounts — one row per phone number per business
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS phone_accounts (
    id            TEXT PRIMARY KEY,
    business_id   TEXT NOT NULL,
    phone         TEXT NOT NULL,                    -- E.164 format (+14155551234)
    last_call_at  TIMESTAMP,
    notes         TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
    -- One phone per business. Two clinics can share a number (rare but legal).
    CONSTRAINT phone_accounts_business_phone_unique UNIQUE (business_id, phone)
);

CREATE INDEX IF NOT EXISTS idx_phone_accounts_phone
    ON phone_accounts(phone);
CREATE INDEX IF NOT EXISTS idx_phone_accounts_business
    ON phone_accounts(business_id);

-- ──────────────────────────────────────────────────────────────────────────
-- 2. patients — one row per real person under a phone account
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS patients (
    id                   TEXT PRIMARY KEY,
    phone_account_id     TEXT NOT NULL,
    business_id          TEXT NOT NULL,
    first_name           TEXT NOT NULL,
    last_name            TEXT,
    date_of_birth        DATE,                       -- For HIPAA-grade matching, optional
    email                TEXT,                       -- Real email if provided, NOT a fake @inbound.call
    consent_given        BOOLEAN DEFAULT FALSE,      -- "this call may be recorded"
    consent_given_at     TIMESTAMP,
    hubspot_contact_id   TEXT,                       -- Cached HubSpot Contact ID (avoids re-search)
    notes                TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (phone_account_id) REFERENCES phone_accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (business_id)      REFERENCES businesses(id)     ON DELETE CASCADE
);

-- Names are matched case-insensitively per phone account
-- "John Smith" and "john smith" should resolve to the same patient.
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_account_name
    ON patients(phone_account_id, lower(first_name), lower(coalesce(last_name, '')));

CREATE INDEX IF NOT EXISTS idx_patients_business
    ON patients(business_id);
CREATE INDEX IF NOT EXISTS idx_patients_hubspot_contact
    ON patients(hubspot_contact_id) WHERE hubspot_contact_id IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────────
-- 3. appointments.patient_id — additive FK, nullable
-- ──────────────────────────────────────────────────────────────────────────
-- We keep user_id NOT NULL for now so existing code paths (chatbot booking
-- by logged-in user) keep working. New inbound flow will set patient_id and
-- can leave user_id pointing at a generic "inbound system" user.

ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS patient_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'appointments_patient_id_fkey'
          AND table_name = 'appointments'
    ) THEN
        ALTER TABLE appointments
            ADD CONSTRAINT appointments_patient_id_fkey
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_appointments_patient
    ON appointments(patient_id);

-- ──────────────────────────────────────────────────────────────────────────
-- 4. voice_calls.caller_name — what Aria heard the caller say
-- ──────────────────────────────────────────────────────────────────────────
-- Independent of the patient resolution. Lets you debug "what did the model
-- transcribe" vs "which patient did we end up binding to" — useful when
-- spell-back goes wrong.

ALTER TABLE voice_calls
    ADD COLUMN IF NOT EXISTS caller_name TEXT;

ALTER TABLE voice_calls
    ADD COLUMN IF NOT EXISTS patient_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'voice_calls_patient_id_fkey'
          AND table_name = 'voice_calls'
    ) THEN
        ALTER TABLE voice_calls
            ADD CONSTRAINT voice_calls_patient_id_fkey
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_voice_calls_patient
    ON voice_calls(patient_id);

-- ──────────────────────────────────────────────────────────────────────────
-- 5. Backfill from existing inbound users
-- ──────────────────────────────────────────────────────────────────────────
-- Detect rows that were created by the old inbound flow (fake @inbound.call
-- emails) and migrate them into the new model.
--
-- For each such user:
--   a) ensure a phone_account exists for (business_id, phone)
--   b) create a patient row (using whatever first_name/last_name was captured)
--   c) update any appointments to point patient_id at the new patient
--
-- Users without a phone are skipped (nothing to anchor on).

DO $$
DECLARE
    inbound_user RECORD;
    pa_id TEXT;
    p_id TEXT;
BEGIN
    FOR inbound_user IN
        SELECT id, business_id, phone, first_name, last_name, email, created_at
        FROM users
        WHERE email LIKE '%@inbound.call'
          AND phone IS NOT NULL
          AND business_id IS NOT NULL
    LOOP
        -- Upsert phone_account
        SELECT id INTO pa_id FROM phone_accounts
            WHERE business_id = inbound_user.business_id
              AND phone = inbound_user.phone
            LIMIT 1;

        IF pa_id IS NULL THEN
            pa_id := 'pa_' || substring(md5(inbound_user.business_id || inbound_user.phone) for 24);
            INSERT INTO phone_accounts (id, business_id, phone, created_at, updated_at)
            VALUES (pa_id, inbound_user.business_id, inbound_user.phone,
                    inbound_user.created_at, inbound_user.created_at)
            ON CONFLICT DO NOTHING;
        END IF;

        -- Upsert patient (use 'Inbound Caller' if name is missing)
        SELECT id INTO p_id FROM patients
            WHERE phone_account_id = pa_id
              AND lower(first_name) = lower(coalesce(inbound_user.first_name, 'Inbound'))
              AND lower(coalesce(last_name, '')) = lower(coalesce(inbound_user.last_name, ''))
            LIMIT 1;

        IF p_id IS NULL THEN
            p_id := 'pat_' || substring(md5(pa_id || coalesce(inbound_user.first_name, 'Inbound') || coalesce(inbound_user.last_name, '')) for 24);
            INSERT INTO patients (
                id, phone_account_id, business_id, first_name, last_name, created_at, updated_at
            ) VALUES (
                p_id, pa_id, inbound_user.business_id,
                coalesce(inbound_user.first_name, 'Inbound'),
                inbound_user.last_name,
                inbound_user.created_at, inbound_user.created_at
            )
            ON CONFLICT DO NOTHING;
        END IF;

        -- Link appointments
        UPDATE appointments
            SET patient_id = p_id
            WHERE user_id = inbound_user.id
              AND patient_id IS NULL;
    END LOOP;
END
$$;

COMMIT;
