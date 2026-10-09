-- ============================================================
-- Migration 009: Fix schema drift between crm-service code and DB
-- (columns referenced by routers/ that were never added in 008)
-- ============================================================
BEGIN;

-- ── leads ─────────────────────────────────────────────────────
ALTER TABLE leads ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS preferred_channel TEXT NOT NULL DEFAULT 'sms';

-- ── ai_agents ─────────────────────────────────────────────────
ALTER TABLE ai_agents ADD COLUMN IF NOT EXISTS call_prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_agents ADD COLUMN IF NOT EXISTS sms_prompt  TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_agents ADD COLUMN IF NOT EXISTS created_by  TEXT;

-- ── conversations ─────────────────────────────────────────────
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_channel_check;
ALTER TABLE conversations ADD CONSTRAINT conversations_channel_check
    CHECK (channel IN ('chat', 'sms', 'voice', 'whatsapp'));

-- ── messages ──────────────────────────────────────────────────
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_role_check;
ALTER TABLE messages ADD CONSTRAINT messages_role_check
    CHECK (role IN ('user', 'agent', 'human', 'draft'));
ALTER TABLE messages ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

-- ── users (agent assignment used by routers/agents.py) ───────
ALTER TABLE users ADD COLUMN IF NOT EXISTS agent_id  TEXT REFERENCES ai_agents(id) ON DELETE SET NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS agent_ids TEXT[] NOT NULL DEFAULT '{}';

COMMIT;
