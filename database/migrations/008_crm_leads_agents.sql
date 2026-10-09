-- ============================================================
-- Migration 008: CRM Leads, AI Agents, Lead Configs, Conversations
-- ============================================================
BEGIN;

-- ── 1. Leads ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id          TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    first_name  TEXT NOT NULL DEFAULT '',
    last_name   TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    tags        TEXT[]   NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'contacted', 'qualified', 'converted', 'dead')),
    strategy    TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',
    notes       TEXT NOT NULL DEFAULT '',
    agent_id    TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_business_status
    ON leads(business_id, status);
CREATE INDEX IF NOT EXISTS idx_leads_business_created
    ON leads(business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_tags
    ON leads USING GIN(tags);

-- ── 2. AI Agents ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_agents (
    id            TEXT PRIMARY KEY,
    business_id   TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'Lead Qualifier',
    persona       TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    ghl_tag       TEXT NOT NULL DEFAULT '',
    tone          TEXT NOT NULL DEFAULT 'professional',
    language      TEXT NOT NULL DEFAULT 'English',
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'inactive')),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_agents_business
    ON ai_agents(business_id, status);

-- ── 3. Lead Routing Configs ──────────────────────────────────
CREATE TABLE IF NOT EXISTS lead_configs (
    id               TEXT PRIMARY KEY,
    business_id      TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    condition_logic  TEXT NOT NULL DEFAULT 'any' CHECK (condition_logic IN ('any', 'all')),
    conditions       JSONB NOT NULL DEFAULT '[]',
    agent_id         TEXT REFERENCES ai_agents(id) ON DELETE SET NULL,
    provider_id      TEXT,
    calendar_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lead_configs_business
    ON lead_configs(business_id, status);

-- ── 4. Conversations ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    lead_id     TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    agent_id    TEXT REFERENCES ai_agents(id) ON DELETE SET NULL,
    channel     TEXT NOT NULL DEFAULT 'chat' CHECK (channel IN ('chat', 'sms', 'voice')),
    ai_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_business
    ON conversations(business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_lead
    ON conversations(lead_id);

-- ── 5. Messages ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'agent', 'human')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at ASC);

COMMIT;
