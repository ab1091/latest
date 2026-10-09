-- Optional gender field on leads, populated via CSV import (or manual entry
-- later if a form field gets added). Constrained to male/female per request;
-- left NULL if not provided.
BEGIN;

ALTER TABLE leads ADD COLUMN IF NOT EXISTS gender TEXT CHECK (gender IN ('male', 'female'));

COMMIT;
