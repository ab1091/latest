-- Removes 6 tables confirmed to have zero references anywhere in either
-- service's codebase (audited 2026-07-14):
--   patients, phone_accounts  — leftover from a pre-pivot "household model"
--                                (migration 005), superseded by `leads`
--   refresh_tokens            — designed for server-side token revocation,
--                                never wired up; auth uses stateless JWTs
--   crm_sync_events,
--   crm_sync_jobs             — HubSpot sync infra; HubSpot itself is not
--                                used in the live product
--   appointment_reminder_events — the "jobs" side of reminders is used,
--                                  this sub-table (provider callbacks) never
--                                  is
-- No foreign keys from any other table reference these (verified before
-- writing this migration).

-- CASCADE on these two only drops the (always-NULL, verified before this
-- migration was written) patient_id foreign key constraints on
-- `appointments`/`voice_calls` — it does not touch those tables' data or
-- any other column.
DROP TABLE IF EXISTS patients CASCADE;
DROP TABLE IF EXISTS phone_accounts CASCADE;
DROP TABLE IF EXISTS refresh_tokens;
DROP TABLE IF EXISTS crm_sync_events;
DROP TABLE IF EXISTS crm_sync_jobs;
DROP TABLE IF EXISTS appointment_reminder_events;
