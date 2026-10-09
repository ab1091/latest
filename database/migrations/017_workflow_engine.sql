-- ============================================================
-- Migration 017: Workflow graph engine
--
-- Replaces lead_sequences / lead_sequence_steps / lead_sequence_enrollments
-- (013) with a real branching multi-workflow engine: multiple named
-- workflows per business/trigger, a node/edge graph per workflow, and
-- per-lead enrollment state that tracks a single "current node" pointer.
--
-- Execution is event-driven and just-in-time (crm-service/core/
-- workflow_engine.py): only ONE scheduled_callbacks row is ever pending
-- per active enrollment at a time, inserted right before it's needed —
-- never a whole path enqueued upfront — which is what makes branching
-- possible. The 013 tables are left in place (deprecated, not dropped)
-- as a one-release audit fallback.
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS workflows (
    id           TEXT PRIMARY KEY,
    business_id  TEXT REFERENCES businesses(id) ON DELETE CASCADE,  -- NULL only for is_template rows
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    trigger_type TEXT NOT NULL CHECK (trigger_type IN
                     ('stage_enter', 'sub_status_enter', 'manual', 'tag_added', 'scheduled')),
    trigger_stage      TEXT,      -- 'new_lead' | 'connected' | 'quoted' | 'appointment_scheduled' | 'closed' | 'dead'
    trigger_sub_status TEXT,
    trigger_config     JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    is_default_for_trigger BOOLEAN NOT NULL DEFAULT FALSE,   -- auto-enrolled when its trigger fires
    is_template  BOOLEAN NOT NULL DEFAULT FALSE,
    template_key TEXT,
    version      INTEGER NOT NULL DEFAULT 1,
    created_by   TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    CHECK ((is_template AND business_id IS NULL) OR (NOT is_template AND business_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workflows_template_key ON workflows(template_key) WHERE is_template;
CREATE INDEX IF NOT EXISTS idx_workflows_business_trigger
    ON workflows(business_id, trigger_type, trigger_stage) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS workflow_nodes (
    id          TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    node_key    TEXT NOT NULL,     -- stable, client-assigned, unique per-workflow (maps 1:1 to a canvas node id)
    node_type   TEXT NOT NULL CHECK (node_type IN
                     ('trigger', 'send_sms', 'send_email', 'ai_call', 'wait',
                      'branch_condition', 'move_stage', 'add_tag', 'notify_staff', 'end')),
    config      JSONB NOT NULL DEFAULT '{}',
    position_x  REAL NOT NULL DEFAULT 0,
    position_y  REAL NOT NULL DEFAULT 0,
    UNIQUE(workflow_id, node_key)
);

CREATE TABLE IF NOT EXISTS workflow_edges (
    id            TEXT PRIMARY KEY,
    workflow_id   TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    from_node_key TEXT NOT NULL,
    to_node_key   TEXT NOT NULL,
    branch_label  TEXT     -- NULL for linear edges; 'replied'/'no_reply', 'yes'/'no' for branch_condition outputs
);
CREATE INDEX IF NOT EXISTS idx_workflow_edges_from ON workflow_edges(workflow_id, from_node_key);

CREATE TABLE IF NOT EXISTS lead_workflow_enrollments (
    id               TEXT PRIMARY KEY,
    lead_id          TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    workflow_id      TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    workflow_version INTEGER NOT NULL,   -- pinned at enrollment time so live graph edits don't alter in-flight leads
    current_node_key TEXT,
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN
                          ('active', 'waiting', 'paused', 'completed', 'cancelled', 'failed')),
    enrolled_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lwe_lead ON lead_workflow_enrollments(lead_id);
-- at most one *live* run of a given workflow per lead; re-enrollment after
-- completion/cancellation is allowed (re-engagement campaigns firing again later)
CREATE UNIQUE INDEX IF NOT EXISTS idx_lwe_one_active
    ON lead_workflow_enrollments(lead_id, workflow_id) WHERE status IN ('active', 'waiting');

CREATE TABLE IF NOT EXISTS workflow_node_runs (
    id            TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES lead_workflow_enrollments(id) ON DELETE CASCADE,
    node_key      TEXT NOT NULL,
    node_type     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
                       ('pending', 'scheduled', 'running', 'completed', 'failed', 'skipped')),
    scheduled_callback_id TEXT REFERENCES scheduled_callbacks(id) ON DELETE SET NULL,
    result        JSONB NOT NULL DEFAULT '{}',
    started_at    TIMESTAMP,
    completed_at  TIMESTAMP,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workflow_node_runs_enrollment ON workflow_node_runs(enrollment_id, created_at);

ALTER TABLE scheduled_callbacks ADD COLUMN IF NOT EXISTS workflow_enrollment_id TEXT
    REFERENCES lead_workflow_enrollments(id) ON DELETE CASCADE;
ALTER TABLE scheduled_callbacks ADD COLUMN IF NOT EXISTS workflow_node_key TEXT;
ALTER TABLE scheduled_callbacks ADD COLUMN IF NOT EXISTS action_type TEXT
    CHECK (action_type IN ('sms', 'call', 'email'));

COMMIT;
