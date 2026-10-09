-- Per-agent voice selection for Vapi calls. Previously voice was chosen
-- purely by language (LANGUAGE_CONFIG in ai-service/vapi/router.py), so
-- every English-speaking agent sounded identical ("Elliot"). Nullable +
-- no default: an agent with no voice set keeps falling back to the
-- language default exactly as before (Riley is unaffected).
BEGIN;

ALTER TABLE ai_agents ADD COLUMN IF NOT EXISTS voice_provider TEXT;
ALTER TABLE ai_agents ADD COLUMN IF NOT EXISTS voice_id       TEXT;

COMMIT;
