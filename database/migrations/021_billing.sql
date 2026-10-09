-- ============================================================
-- Migration 021: Billing — real schema, payment-provider integration
-- explicitly stubbed (no Stripe calls yet; PATCH changes the plan
-- directly and the UI labels this clearly).
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS plans (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    price_cents      INTEGER NOT NULL DEFAULT 0,
    billing_interval TEXT NOT NULL DEFAULT 'month' CHECK (billing_interval IN ('month', 'year')),
    max_staff_users  INTEGER,
    max_leads        INTEGER,
    features         JSONB NOT NULL DEFAULT '{}',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                     TEXT PRIMARY KEY,
    business_id            TEXT NOT NULL UNIQUE REFERENCES businesses(id) ON DELETE CASCADE,
    plan_id                TEXT NOT NULL REFERENCES plans(id),
    status                 TEXT NOT NULL DEFAULT 'trialing' CHECK (status IN
                               ('trialing', 'active', 'past_due', 'cancelled', 'paused')),
    current_period_start   TIMESTAMP NOT NULL DEFAULT NOW(),
    current_period_end     TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT,
    cancel_at_period_end   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at             TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoices (
    id               TEXT PRIMARY KEY,
    business_id      TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    subscription_id  TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
    amount_cents     INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'open', 'paid', 'void', 'uncollectible')),
    period_start     TIMESTAMP,
    period_end       TIMESTAMP,
    stripe_invoice_id TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    paid_at          TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invoices_business ON invoices(business_id, created_at DESC);

INSERT INTO plans (id, name, price_cents, billing_interval, max_staff_users, max_leads, features, sort_order) VALUES
    ('plan_starter',  'Starter',  0,     'month', 2,    250,  '{"ai_agents": 1, "workflows": 3, "sms_included": 200}', 0),
    ('plan_growth',   'Growth',   29900, 'month', 10,   2500, '{"ai_agents": 3, "workflows": 15, "sms_included": 2000}', 1),
    ('plan_pro',      'Pro',      79900, 'month', 50,   25000,'{"ai_agents": 10, "workflows": 50, "sms_included": 10000}', 2),
    ('plan_enterprise','Enterprise', 0,  'month', NULL, NULL, '{"ai_agents": null, "workflows": null, "sms_included": null, "custom": true}', 3)
ON CONFLICT (id) DO NOTHING;

COMMIT;
