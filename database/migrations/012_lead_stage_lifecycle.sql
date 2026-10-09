-- ============================================================
-- Migration 012: lead stage/sub_status lifecycle taxonomy
--
-- Renames leads.status -> leads.sub_status (internal, granular)
-- and adds leads.stage (client-facing 5-stage pipeline), driven
-- exclusively by the new centralized state machine
-- (crm-service/core/lead_lifecycle.py). Also adds lead_status_history
-- as an audit trail for the journey timeline.
--
-- NOTE: some code already writes 'responded' and 'follow_up_sent'
-- into leads.status, which violates today's CHECK constraint
-- (migrations/008) — this migration widens it to match reality.
-- ============================================================
BEGIN;

ALTER TABLE leads RENAME COLUMN status TO sub_status;

ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_sub_status_check
    CHECK (sub_status IN ('new','contacted','responded','follow_up_sent','qualified','quoted','converted','dead'));

ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'new_lead'
    CHECK (stage IN ('new_lead','connected','quoted','closed','dead'));

UPDATE leads SET stage = CASE
    WHEN sub_status IN ('new','contacted','follow_up_sent') THEN 'new_lead'
    WHEN sub_status IN ('responded','qualified')            THEN 'connected'
    WHEN sub_status = 'quoted'                               THEN 'quoted'
    WHEN sub_status = 'converted'                            THEN 'closed'
    WHEN sub_status = 'dead'                                 THEN 'dead'
    ELSE 'new_lead'
END;

CREATE INDEX IF NOT EXISTS idx_leads_business_stage ON leads(business_id, stage);

CREATE TABLE IF NOT EXISTS lead_status_history (
    id              TEXT PRIMARY KEY,
    lead_id         TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    from_stage      TEXT,
    to_stage        TEXT NOT NULL,
    from_sub_status TEXT,
    to_sub_status   TEXT NOT NULL,
    event           TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lead_status_history_lead ON lead_status_history(lead_id, created_at);

COMMIT;
