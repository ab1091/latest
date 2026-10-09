-- ============================================================
-- Migration 016: Live Activity Feed
--
-- Durable event log backing the platform-wide live activity feed.
-- Every event is written here AND published to Redis (channel
-- activity_feed:{business_id}) in the same call by
-- core/activity_feed.py's emit() — this table backs the initial
-- page-load / history fetch, Redis pub/sub backs the live SSE push.
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS activity_feed_events (
    id          TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    lead_id     TEXT REFERENCES leads(id) ON DELETE SET NULL,
    event_type  TEXT NOT NULL,
    title       TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_feed_business_created
    ON activity_feed_events(business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_feed_lead
    ON activity_feed_events(lead_id);

COMMIT;
