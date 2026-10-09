BEGIN;

-- TCPA opt-out tracking. The live SMS path (ai-service/api/sms/router.py)
-- had no way to record a STOP request at all — this is the missing piece.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS opted_out BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS opted_out_at TIMESTAMP;

COMMIT;
