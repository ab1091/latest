-- Cached, on-demand AI summary combining a lead's full SMS + call history into
-- one narrative, so staff don't have to read the whole conversation/journey
-- to know where things stand.
BEGIN;

ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_summary TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_summary_updated_at TIMESTAMP;

COMMIT;
