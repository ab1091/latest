-- ============================================================
-- Migration 013: lead engagement sequence engine
--
-- One master configurable sequence per business (an ordered list
-- of day-offset SMS/call steps). All new leads are enrolled
-- automatically; execution reuses the existing scheduled_callbacks
-- table + ai-service APScheduler poller (no new execution engine) —
-- every step is inserted upfront as a scheduled_callbacks row at
-- enrollment time, not chained step-by-step.
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS lead_sequences (
    id          TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name        TEXT NOT NULL DEFAULT 'Default Engagement Sequence',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
-- v1: exactly one active sequence per business ("one master sequence")
CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_sequences_one_active_per_biz
    ON lead_sequences(business_id) WHERE is_active;

CREATE TABLE IF NOT EXISTS lead_sequence_steps (
    id             TEXT PRIMARY KEY,
    sequence_id    TEXT NOT NULL REFERENCES lead_sequences(id) ON DELETE CASCADE,
    step_order     INTEGER NOT NULL,
    day_offset     INTEGER NOT NULL DEFAULT 0,
    delay_seconds_within_day INTEGER NOT NULL DEFAULT 0,
    action_type    TEXT NOT NULL CHECK (action_type IN ('sms','call')),
    template_ref   TEXT,
    channel        TEXT DEFAULT 'sms' CHECK (channel IN ('sms','whatsapp')),
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(sequence_id, step_order)
);

CREATE TABLE IF NOT EXISTS lead_sequence_enrollments (
    id                  TEXT PRIMARY KEY,
    lead_id             TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    sequence_id         TEXT NOT NULL REFERENCES lead_sequences(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','completed','cancelled')),
    current_step_order  INTEGER NOT NULL DEFAULT 0,
    enrolled_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(lead_id, sequence_id)
);

ALTER TABLE scheduled_callbacks ADD COLUMN IF NOT EXISTS sequence_enrollment_id TEXT
    REFERENCES lead_sequence_enrollments(id) ON DELETE CASCADE;
ALTER TABLE scheduled_callbacks ADD COLUMN IF NOT EXISTS sequence_step_id TEXT
    REFERENCES lead_sequence_steps(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_scheduled_callbacks_enrollment ON scheduled_callbacks(sequence_enrollment_id);

COMMIT;
