-- ============================================================
-- Migration 018: CRM Settings — Lead Statuses, Assignment Rules,
-- Lead Scoring Rules, Communication Rules. ("Pipeline Management"
-- reuses lead_stages; "stage automation" is a deep-link to the
-- workflow engine, not new schema here.)
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS lead_stages (
    id             TEXT PRIMARY KEY,
    business_id    TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    key            TEXT NOT NULL,
    label          TEXT NOT NULL,
    color          TEXT NOT NULL DEFAULT '#818cf8',
    sort_order     INTEGER NOT NULL DEFAULT 0,
    is_closed_won  BOOLEAN NOT NULL DEFAULT FALSE,
    is_closed_lost BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(business_id, key)
);

CREATE TABLE IF NOT EXISTS assignment_rules (
    id          TEXT PRIMARY KEY,
    business_id TEXT NOT NULL UNIQUE REFERENCES businesses(id) ON DELETE CASCADE,
    mode        TEXT NOT NULL DEFAULT 'manual' CHECK (mode IN ('round_robin', 'team_based', 'territory_based', 'manual')),
    config      JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assignment_rr_state (
    business_id            TEXT PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
    last_assigned_user_id  TEXT REFERENCES users(id) ON DELETE SET NULL,
    updated_at             TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_scoring_rules (
    id          TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    factor_key  TEXT NOT NULL CHECK (factor_key IN
                    ('sms_engagement', 'call_engagement', 'appointment_activity', 'quote_requests', 'ai_sentiment')),
    weight      INTEGER NOT NULL DEFAULT 0,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(business_id, factor_key)
);

CREATE TABLE IF NOT EXISTS communication_rules (
    business_id       TEXT PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
    quiet_hours_start TEXT NOT NULL DEFAULT '09:00',
    quiet_hours_end   TEXT NOT NULL DEFAULT '20:00',
    timezone          TEXT NOT NULL DEFAULT 'America/New_York',
    max_sms_per_day   INTEGER NOT NULL DEFAULT 5,
    max_calls_per_day INTEGER NOT NULL DEFAULT 3,
    channels_enabled  JSONB NOT NULL DEFAULT '{"sms": true, "whatsapp": true, "call": true, "email": false}',
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMIT;
