-- ============================================================
-- Migration 011: scheduled_callbacks table
-- Referenced throughout ai-service/core/callback_scheduler.py,
-- ai-service/vapi/router.py, ai-service/api/sms/router.py, and
-- crm-service/routers/{sms,leads}.py, but never formally created
-- by any prior migration — the table does not exist in the
-- database at all. This adopts it into tracked migration history.
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS scheduled_callbacks (
    id           TEXT PRIMARY KEY,
    lead_id      TEXT REFERENCES leads(id) ON DELETE CASCADE,
    business_id  TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    phone        TEXT NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','processing','completed','failed','cancelled')),
    call_reason  TEXT,
    callback_type TEXT CHECK (callback_type IN ('sms','call')),
    sms_channel  TEXT,
    vapi_call_id TEXT,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_callbacks_status_time
    ON scheduled_callbacks(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_callbacks_lead
    ON scheduled_callbacks(lead_id);

COMMIT;
