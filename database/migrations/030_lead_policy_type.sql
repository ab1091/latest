-- Policy/insurance type on leads (e.g. Auto, Home, Life, Health), populated
-- via CSV import or manual entry. Free text, defaults to empty.
BEGIN;

ALTER TABLE leads ADD COLUMN IF NOT EXISTS policy_type TEXT NOT NULL DEFAULT '';

COMMIT;
