-- Migration: Add reminder jobs and events tables (Ubaid's work)

-- Update appointments table with reminder fields
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS google_reminder_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ai_call_reminder_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reminder_offset_minutes INTEGER NOT NULL DEFAULT 60,
    ADD COLUMN IF NOT EXISTS google_reminder_status TEXT NOT NULL DEFAULT 'not_requested',
    ADD COLUMN IF NOT EXISTS ai_call_reminder_status TEXT NOT NULL DEFAULT 'not_requested';

-- Appointment Reminder Jobs
CREATE TABLE IF NOT EXISTS appointment_reminder_jobs (
    id TEXT PRIMARY KEY,
    appointment_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK(channel IN ('google_calendar', 'ai_call')),
    scheduled_for TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    provider_call_id TEXT,
    voicemail_detected BOOLEAN NOT NULL DEFAULT FALSE,
    transcript TEXT,
    summary TEXT,
    last_error TEXT,
    locked_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_appointment_reminder_jobs_status_schedule
    ON appointment_reminder_jobs(status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_appointment_reminder_jobs_appointment
    ON appointment_reminder_jobs(appointment_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_appointment_reminder_jobs_provider_call_id
    ON appointment_reminder_jobs(provider_call_id)
    WHERE provider_call_id IS NOT NULL;

-- Appointment Reminder Events
CREATE TABLE IF NOT EXISTS appointment_reminder_events (
    id TEXT PRIMARY KEY,
    appointment_id TEXT,
    job_id TEXT,
    provider TEXT NOT NULL,
    provider_call_id TEXT,
    external_event_id TEXT,
    event_type TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES appointment_reminder_jobs(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_appointment_reminder_events_event_hash
    ON appointment_reminder_events(event_hash);
CREATE INDEX IF NOT EXISTS idx_appointment_reminder_events_appointment
    ON appointment_reminder_events(appointment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_appointment_reminder_events_job
    ON appointment_reminder_events(job_id, created_at DESC);
