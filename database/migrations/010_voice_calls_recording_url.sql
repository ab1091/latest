-- ============================================================
-- Migration 010: voice_calls.recording_url
-- Referenced by ai-service/vapi/router.py call-end upsert and
-- crm-service/routers/leads.py lead-activity endpoint, but never
-- added by a prior migration.
-- ============================================================
BEGIN;

ALTER TABLE voice_calls ADD COLUMN IF NOT EXISTS recording_url TEXT;

COMMIT;
