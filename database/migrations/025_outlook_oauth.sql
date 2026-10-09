-- Outlook Calendar OAuth storage on users — mirrors google_refresh_token/
-- google_email, which already exist in schema.pg.sql. The Outlook connect
-- flow (ai-service/api/integrations/router.py) has referenced these columns
-- since it was written, but they were never actually added — every connect
-- attempt has been crashing with UndefinedColumn.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS outlook_refresh_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS outlook_email VARCHAR(255);

COMMIT;
