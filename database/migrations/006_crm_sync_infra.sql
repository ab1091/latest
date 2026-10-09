-- ============================================
-- Migration 006: CRM sync infrastructure
-- ============================================
-- Why this exists:
--   Today HubSpotService.syncContact / syncMeeting / updateMeetingStatus
--   are called fire-and-forget from twilio.ts, appointments.ts, webhooks.ts.
--   If HubSpot is unreachable, rate-limited, or returns 5xx, the call ends,
--   the appointment is in our DB, but nothing ever shows up in CRM.
--
--   This migration adds:
--     1. crm_sync_jobs   queue table for HubSpot pushes with retry
--     2. businesses.hubspot_portal_id   so the reverse webhook
--        (HubSpot → us) can map the portalId to the right business
--     3. businesses.hubspot_account_id  display label for admin UI
--
-- Idempotent: safe to run multiple times.
-- ============================================

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────
-- 1. Add HubSpot identification columns to businesses
-- ──────────────────────────────────────────────────────────────────────────
-- Note: hubspot_refresh_token and hubspot_connected are added by the existing
-- script `scripts/migrateProductionIntegrations.ts`. We add them here too
-- with IF NOT EXISTS so a fresh PG install gets them via the migration chain.

ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS hubspot_refresh_token TEXT,
    ADD COLUMN IF NOT EXISTS hubspot_connected     BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS hubspot_portal_id     TEXT,                  -- HubSpot's portalId, used by reverse webhook
    ADD COLUMN IF NOT EXISTS hubspot_account_id    TEXT,                  -- Display label (e.g. "Allzone Demo Portal")
    ADD COLUMN IF NOT EXISTS hubspot_last_sync_at  TIMESTAMP;

-- portal_id is unique per business since one HubSpot portal pairs with one business
CREATE UNIQUE INDEX IF NOT EXISTS idx_businesses_hubspot_portal
    ON businesses(hubspot_portal_id)
    WHERE hubspot_portal_id IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────────
-- 2. crm_sync_jobs — durable queue for HubSpot writes
-- ──────────────────────────────────────────────────────────────────────────
-- Producers: anywhere we currently call HubSpotService.syncX directly.
--   Instead they INSERT a row here with op='sync_contact' / 'sync_meeting'
--   / 'sync_call' / 'update_meeting_status' and a JSON payload.
--
-- Consumer: a single worker process (scripts/crmSyncWorker.ts) that:
--   - SELECT next pending job FOR UPDATE SKIP LOCKED
--   - Calls the appropriate HubSpotService method
--   - On success: status='completed', completed_at=now()
--   - On failure: increments attempt_count, sets next_attempt_at with
--     exponential backoff, status stays 'pending' until max_attempts reached
--   - At max_attempts: status='failed' (dead-letter, alert ops)
--
-- This makes CRM sync resilient to HubSpot downtime without blocking the
-- inbound call flow.

CREATE TABLE IF NOT EXISTS crm_sync_jobs (
    id                TEXT PRIMARY KEY,
    business_id       TEXT NOT NULL,
    op                TEXT NOT NULL CHECK (op IN (
        'sync_contact',
        'sync_meeting',
        'sync_call',
        'update_meeting_status'
    )),
    -- Stable key so we can deduplicate (same patient + same appointment etc.)
    -- e.g. 'contact:pat_abc123' or 'meeting:appt_xyz789'
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

-- Worker scan path: status=pending AND next_attempt_at <= now()
CREATE INDEX IF NOT EXISTS idx_crm_sync_jobs_dispatch
    ON crm_sync_jobs(status, next_attempt_at)
    WHERE status = 'pending';

-- For dedup checks during enqueue
CREATE INDEX IF NOT EXISTS idx_crm_sync_jobs_target
    ON crm_sync_jobs(business_id, op, target_key);

-- For ops dashboards / debugging
CREATE INDEX IF NOT EXISTS idx_crm_sync_jobs_status
    ON crm_sync_jobs(status, created_at DESC);

-- Audit / debugging: every CRM event we push or receive
CREATE TABLE IF NOT EXISTS crm_sync_events (
    id            TEXT PRIMARY KEY,
    job_id        TEXT,
    business_id   TEXT NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
    event_type    TEXT NOT NULL,                  -- 'sync_attempt', 'webhook_received', etc.
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

COMMIT;
