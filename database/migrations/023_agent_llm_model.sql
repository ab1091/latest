-- Per-agent Groq model selection, so a lead_config rule can route different
-- pipeline stages to agents running different models (e.g. a cheaper/faster
-- model for early qualification, a stronger one for closing).
BEGIN;

ALTER TABLE ai_agents ADD COLUMN IF NOT EXISTS llm_model TEXT NOT NULL DEFAULT 'llama-3.3-70b-versatile';

COMMIT;
