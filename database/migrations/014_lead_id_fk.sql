-- ============================================================
-- Migration 014: lead_id FK on appointments & voice_calls
--
-- Both tables previously linked to leads only via phone-number
-- matching (a legacy of the system's prior patient/dental-voicebot
-- design). Adds a real FK so status-automation (appointment booking
-- -> Closed, journey timeline) doesn't depend on fragile phone joins.
-- Phone-matching is kept for legacy backfill only; new writes should
-- populate lead_id directly (see application code changes).
-- ============================================================
BEGIN;

ALTER TABLE appointments ADD COLUMN IF NOT EXISTS lead_id TEXT REFERENCES leads(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_appointments_lead ON appointments(lead_id);

ALTER TABLE voice_calls ADD COLUMN IF NOT EXISTS lead_id TEXT REFERENCES leads(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_voice_calls_lead ON voice_calls(lead_id);

-- Best-effort legacy backfill. appointments.business_id lets us scope that
-- join properly; voice_calls has NO business_id column at all (consistent
-- with existing code, which already matches voice_calls by phone alone
-- everywhere — e.g. crm-service/routers/leads.py's /activity endpoint),
-- so its backfill can't be business-scoped and carries the same
-- cross-tenant phone-collision risk that already exists in this codebase.
UPDATE appointments a SET lead_id = l.id
FROM voice_calls vc, leads l
WHERE vc.appointment_id = a.id
  AND vc.patient_phone = l.phone
  AND a.business_id = l.business_id
  AND a.lead_id IS NULL;

UPDATE voice_calls vc SET lead_id = l.id
FROM leads l
WHERE vc.patient_phone = l.phone
  AND vc.lead_id IS NULL;

COMMIT;
