-- appointments.outlook_event_id — mirrors google_event_id. The Outlook sync
-- path in create_appointment() (ai-service/api/appointments/router.py) has
-- referenced this column since it was written, but it was never actually
-- added — every appointment create has been crashing with UndefinedColumn
-- (same class of bug as 025_outlook_oauth.sql, that time on users).
BEGIN;

ALTER TABLE appointments ADD COLUMN IF NOT EXISTS outlook_event_id TEXT;

COMMIT;
