-- Extra per-provider voice tuning (e.g. ElevenLabs "style"/"stability"
-- exaggeration knobs) that don't fit the simple provider/voiceId pair added
-- in 039. Nullable JSONB — merged into the voice object at call time only
-- when present, so existing agents (Riley, and Jenny's Azure fallback) are
-- unaffected.
BEGIN;

ALTER TABLE ai_agents ADD COLUMN IF NOT EXISTS voice_extra JSONB;

COMMIT;
