-- Per-user module permissions: lets an admin share access to a specific
-- section (Leads, Communication, CRM Settings, etc.) with a staff/customer
-- account beyond their role's default floor. Additive only — never removes
-- what a role already grants.
ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions TEXT[] NOT NULL DEFAULT '{}';
