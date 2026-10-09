-- AI Chatbot Appointment Booking System - Database Schema
-- Designed for PostgreSQL

-- ============================================
-- DROP EXISTING TABLES (dev only — ensures clean re-init)
-- Order matters: drop dependents first to avoid FK violations
-- ============================================
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS chat_sessions CASCADE;
DROP TABLE IF EXISTS refresh_tokens CASCADE;
DROP TABLE IF EXISTS voice_calls CASCADE;
DROP TABLE IF EXISTS appointments CASCADE;
DROP TABLE IF EXISTS availability CASCADE;
DROP TABLE IF EXISTS provider_services CASCADE;
DROP TABLE IF EXISTS providers CASCADE;
DROP TABLE IF EXISTS services CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS businesses CASCADE;

-- ============================================
-- BUSINESSES TABLE (Multi-tenancy support)
-- ============================================
CREATE TABLE IF NOT EXISTS businesses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    address TEXT,
    city TEXT,
    timezone TEXT DEFAULT 'America/New_York',
    settings TEXT DEFAULT '{}',  -- JSON for flexible configuration
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_businesses_email ON businesses(email);

-- ============================================
-- USERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    business_id TEXT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    city TEXT,
    role TEXT DEFAULT 'customer' CHECK(role IN ('admin', 'staff', 'customer')),
    is_active INTEGER DEFAULT 1, -- Using 0/1 for compatibility with existing code
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP,
    google_refresh_token TEXT,
    google_email VARCHAR(255),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_business ON users(business_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
-- Required by inbound flow: SELECT id FROM users WHERE phone = $1
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

-- ============================================
-- SERVICES TABLE (Types of appointments)
-- ============================================
CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    duration_minutes INTEGER DEFAULT 30,
    price REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_services_business ON services(business_id);

-- ============================================
-- PROVIDERS TABLE (Doctors, therapists, etc.)
-- ============================================
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    bio TEXT,
    city TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_providers_business ON providers(business_id);
CREATE INDEX IF NOT EXISTS idx_providers_specialty ON providers(specialty);

-- ============================================
-- PROVIDER-SERVICES TABLE (Many-to-many mapping)
-- ============================================
CREATE TABLE IF NOT EXISTS provider_services (
    provider_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider_id, service_id),
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_provider_services_provider ON provider_services(provider_id);
CREATE INDEX IF NOT EXISTS idx_provider_services_service ON provider_services(service_id);
CREATE INDEX IF NOT EXISTS idx_provider_services_business ON provider_services(business_id);

-- ============================================
-- AVAILABILITY TABLE (Business hours/slots)
-- ============================================
CREATE TABLE IF NOT EXISTS availability (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),  -- 0=Sunday
    start_time TEXT NOT NULL,  -- HH:MM format
    end_time TEXT NOT NULL,    -- HH:MM format
    is_available INTEGER DEFAULT 1,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_availability_business ON availability(business_id);
CREATE INDEX IF NOT EXISTS idx_availability_day ON availability(day_of_week);

-- ============================================
-- APPOINTMENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    service_id TEXT,
    provider_id TEXT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'cancelled', 'completed', 'no_show')),
    notes TEXT,
    -- Supported values: chatbot, web, phone, walk_in, voice_inbound, voice_outbound
    -- (No CHECK constraint — validated at application layer to allow forward-compat.)
    created_via TEXT DEFAULT 'chatbot',
    google_event_id TEXT,                -- Google Calendar Event ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancellation_reason TEXT,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL,
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_appointments_business ON appointments(business_id);
CREATE INDEX IF NOT EXISTS idx_appointments_user ON appointments(user_id);
CREATE INDEX IF NOT EXISTS idx_appointments_provider ON appointments(provider_id);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_start_time ON appointments(start_time);
-- Time-range scans (slot conflict / availability checks)
CREATE INDEX IF NOT EXISTS idx_appointments_start_end ON appointments(start_time, end_time);
-- Provider-on-date lookups (availability tool, calendar grid)
CREATE INDEX IF NOT EXISTS idx_appointments_provider_start ON appointments(provider_id, start_time);
-- Prevent two concurrent bookings for the same provider at the same start_time.
-- Cancelled / completed / no_show slots are excluded so the time can be reused.
CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_no_double_book
    ON appointments(provider_id, start_time)
    WHERE status IN ('pending', 'confirmed') AND provider_id IS NOT NULL;
-- Postgres date function is okay, but indexing expression needs IMMUTABLE. DATE(timestamp) is mostly fine.
-- CREATE INDEX idx_appointments_date ON appointments(DATE(start_time));
-- Commenting out simplistic expression index to avoid PG complexity for now, filter using ranges.

-- ============================================
-- CHAT SESSIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    business_id TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'abandoned')),
    context TEXT DEFAULT '{}',  -- JSON
    intent TEXT,
    outcome TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_business ON chat_sessions(business_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON chat_sessions(status);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_started ON chat_sessions(started_at);

-- ============================================
-- CHAT MESSAGES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);

-- ============================================
-- VOICE CALLS TABLE (Vapi AI reminder calls)
-- ============================================
CREATE TABLE IF NOT EXISTS voice_calls (
    id TEXT PRIMARY KEY,
    -- Nullable: inbound calls insert this row before the appointment exists.
    appointment_id TEXT,
    call_id TEXT NOT NULL UNIQUE,          -- Vapi or Twilio call ID
    provider TEXT NOT NULL DEFAULT 'vapi', -- 'vapi' or 'twilio'
    direction TEXT CHECK(direction IN ('inbound', 'outbound')) DEFAULT 'outbound',
    patient_phone TEXT,                    -- E.164 format, used for inbound caller lookup
    status TEXT DEFAULT 'initiated' CHECK(status IN ('initiated', 'queued', 'ringing', 'in-progress', 'ended', 'failed')),
    outcome TEXT CHECK(outcome IN ('confirmed', 'cancelled', 'reschedule_requested', 'no_answer', 'voicemail', 'failed')),
    transcript TEXT,
    summary TEXT,
    duration_seconds INTEGER,
    raw_payload TEXT,                      -- full Vapi webhook JSON (for audit)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_voice_calls_appointment ON voice_calls(appointment_id);
CREATE INDEX IF NOT EXISTS idx_voice_calls_call_id ON voice_calls(call_id);
CREATE INDEX IF NOT EXISTS idx_voice_calls_status ON voice_calls(status);
CREATE INDEX IF NOT EXISTS idx_voice_calls_outcome ON voice_calls(outcome);
CREATE INDEX IF NOT EXISTS idx_voice_calls_direction ON voice_calls(direction);
CREATE INDEX IF NOT EXISTS idx_voice_calls_patient_phone ON voice_calls(patient_phone);

-- ============================================
-- REFRESH TOKENS TABLE (For JWT auth)
-- ============================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- ============================================
-- INTEGRATION COLUMNS ON businesses (mirror migrations 002, 006 + scripts)
-- ============================================
ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS hubspot_refresh_token TEXT,
    ADD COLUMN IF NOT EXISTS hubspot_connected     BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS hubspot_portal_id     TEXT,        -- HubSpot portalId, used by reverse webhook
    ADD COLUMN IF NOT EXISTS hubspot_account_id    TEXT,        -- Display label for admin UI
    ADD COLUMN IF NOT EXISTS hubspot_last_sync_at  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS vapi_api_key          TEXT,
    ADD COLUMN IF NOT EXISTS vapi_assistant_id     TEXT,
    ADD COLUMN IF NOT EXISTS twilio_sid            TEXT,
    ADD COLUMN IF NOT EXISTS twilio_auth_token     TEXT,
    ADD COLUMN IF NOT EXISTS twilio_phone_number   TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_businesses_hubspot_portal
    ON businesses(hubspot_portal_id) WHERE hubspot_portal_id IS NOT NULL;

-- ============================================
-- HOUSEHOLD MODEL (migration 005)
-- ============================================
-- phone_accounts: one row per phone number per business (the "household")
-- patients: one row per real person under a phone account
-- See migrations/005_household_model.sql for the full rationale.

CREATE TABLE IF NOT EXISTS phone_accounts (
    id            TEXT PRIMARY KEY,
    business_id   TEXT NOT NULL,
    phone         TEXT NOT NULL,                    -- E.164 format (+14155551234)
    last_call_at  TIMESTAMP,
    notes         TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
    CONSTRAINT phone_accounts_business_phone_unique UNIQUE (business_id, phone)
);

CREATE INDEX IF NOT EXISTS idx_phone_accounts_phone    ON phone_accounts(phone);
CREATE INDEX IF NOT EXISTS idx_phone_accounts_business ON phone_accounts(business_id);

CREATE TABLE IF NOT EXISTS patients (
    id                   TEXT PRIMARY KEY,
    phone_account_id     TEXT NOT NULL,
    business_id          TEXT NOT NULL,
    first_name           TEXT NOT NULL,
    last_name            TEXT,
    date_of_birth        DATE,
    email                TEXT,                       -- Real email if provided (NOT a fake @inbound.call)
    consent_given        BOOLEAN DEFAULT FALSE,      -- "this call may be recorded"
    consent_given_at     TIMESTAMP,
    hubspot_contact_id   TEXT,                       -- Cached HubSpot Contact ID
    notes                TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (phone_account_id) REFERENCES phone_accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (business_id)      REFERENCES businesses(id)     ON DELETE CASCADE
);

-- Case-insensitive name uniqueness within a phone account
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_account_name
    ON patients(phone_account_id, lower(first_name), lower(coalesce(last_name, '')));

CREATE INDEX IF NOT EXISTS idx_patients_business
    ON patients(business_id);
CREATE INDEX IF NOT EXISTS idx_patients_hubspot_contact
    ON patients(hubspot_contact_id) WHERE hubspot_contact_id IS NOT NULL;

-- Wire patient_id into appointments and voice_calls (additive — keeps user_id intact)
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS patient_id TEXT;

ALTER TABLE voice_calls
    ADD COLUMN IF NOT EXISTS caller_name TEXT,
    ADD COLUMN IF NOT EXISTS patient_id  TEXT;

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

CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_voice_calls_patient  ON voice_calls(patient_id);

-- ============================================
-- CRM SYNC INFRASTRUCTURE (migration 006)
-- ============================================
-- crm_sync_jobs: durable queue for HubSpot writes with retry/backoff
-- crm_sync_events: audit log of every CRM event (push or webhook)

CREATE TABLE IF NOT EXISTS crm_sync_jobs (
    id                TEXT PRIMARY KEY,
    business_id       TEXT NOT NULL,
    op                TEXT NOT NULL CHECK (op IN (
        'sync_contact', 'sync_meeting', 'sync_call', 'update_meeting_status'
    )),
    target_key        TEXT NOT NULL,
    payload           JSONB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 8,
    next_attempt_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error        TEXT,
    locked_at         TIMESTAMP,
    locked_by         TEXT,
    completed_at      TIMESTAMP,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crm_sync_jobs_dispatch
    ON crm_sync_jobs(status, next_attempt_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_crm_sync_jobs_target
    ON crm_sync_jobs(business_id, op, target_key);
CREATE INDEX IF NOT EXISTS idx_crm_sync_jobs_status
    ON crm_sync_jobs(status, created_at DESC);

CREATE TABLE IF NOT EXISTS crm_sync_events (
    id            TEXT PRIMARY KEY,
    job_id        TEXT,
    business_id   TEXT NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
    event_type    TEXT NOT NULL,
    payload       JSONB NOT NULL,
    error         TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)      REFERENCES crm_sync_jobs(id) ON DELETE SET NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(id)    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crm_sync_events_business_created
    ON crm_sync_events(business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_crm_sync_events_job
    ON crm_sync_events(job_id, created_at DESC);
