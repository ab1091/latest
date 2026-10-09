-- ============================================================
-- Migration 019: AI Lead Scoring
-- ============================================================
BEGIN;

ALTER TABLE leads ADD COLUMN IF NOT EXISTS score INTEGER NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_band TEXT NOT NULL DEFAULT 'new'
    CHECK (score_band IN ('hot', 'warm', 'cold', 'new'));
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(business_id, score DESC);

CREATE TABLE IF NOT EXISTS lead_score_history (
    id         TEXT PRIMARY KEY,
    lead_id    TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    score      INTEGER NOT NULL,
    band       TEXT NOT NULL,
    factors    JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lead_score_history_lead ON lead_score_history(lead_id, created_at DESC);

ALTER TABLE voice_calls ADD COLUMN IF NOT EXISTS sentiment TEXT CHECK (sentiment IN ('positive', 'neutral', 'negative'));

COMMIT;
