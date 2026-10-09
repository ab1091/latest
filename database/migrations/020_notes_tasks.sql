-- ============================================================
-- Migration 020: Notes & Tasks
--
-- Genuinely new — previously "notes" was only a free-text column on
-- leads/appointments, with no structured multi-note or task concept.
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    lead_id     TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    author_id   TEXT REFERENCES users(id) ON DELETE SET NULL,
    body        TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notes_lead ON notes(lead_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    lead_id      TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    business_id  TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    assigned_to  TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_by   TEXT REFERENCES users(id) ON DELETE SET NULL,
    title        TEXT NOT NULL,
    due_at       TIMESTAMP,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'cancelled')),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tasks_lead ON tasks(lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to, status);

COMMIT;
