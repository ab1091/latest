-- ============================================================
-- Migration 015: role/tenancy foundations + assignment + new
-- "Appointment Scheduled" pipeline stage
--
-- Part of the Lead Command Center platform rebuild. Adds a real
-- super_admin role (platform-wide, business_id NULL) on top of the
-- existing admin/staff/customer tiers, a status flag on businesses
-- for agency lifecycle management, a human-owner column on leads
-- (previously only agent_id existed, for the AI agent), and widens
-- the lead stage/sub_status taxonomy with 'appointment_scheduled'
-- so the pipeline matches New Lead -> Connected -> Quoted ->
-- Appointment Scheduled -> Closed Won -> Dead.
-- ============================================================
BEGIN;

-- ── Roles: add super_admin ──────────────────────────────────────────────────
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('super_admin', 'admin', 'staff', 'customer'));

-- ── Agency lifecycle status ─────────────────────────────────────────────────
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('trial', 'active', 'suspended', 'cancelled'));

-- ── Lead assignment (human owner) ───────────────────────────────────────────
-- leads.agent_id already exists (the AI agent handling the lead) but there
-- was no column at all for "which staff member owns this lead" — required
-- for the CRM Settings Assignment Rules feature (round robin/team/territory).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS assigned_user_id TEXT
    REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_leads_assigned_user ON leads(assigned_user_id);

-- ── New pipeline stage: Appointment Scheduled ───────────────────────────────
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_sub_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_sub_status_check
    CHECK (sub_status IN ('new', 'contacted', 'responded', 'follow_up_sent',
                          'qualified', 'quoted', 'appointment_scheduled',
                          'converted', 'dead'));

ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_stage_check;
ALTER TABLE leads ADD CONSTRAINT leads_stage_check
    CHECK (stage IN ('new_lead', 'connected', 'quoted', 'appointment_scheduled', 'closed', 'dead'));

COMMIT;
