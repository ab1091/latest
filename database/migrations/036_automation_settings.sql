-- Simple per-business automation settings for the "Quick Setup" automation
-- page — plain on/off toggles for SMS and Call automation, backed by the
-- same workflow engine that already exists (no new execution logic, just a
-- simpler control surface over it).
CREATE TABLE IF NOT EXISTS business_automation_settings (
    business_id                    TEXT PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
    sms_auto_enabled                BOOLEAN NOT NULL DEFAULT TRUE,
    sms_followup_wait_hours         INTEGER NOT NULL DEFAULT 23,
    call_on_confirm_enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    call_on_confirm_wait_minutes    INTEGER NOT NULL DEFAULT 45,
    call_on_silence_enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at                      TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE business_automation_settings OWNER TO aicrm_app;
GRANT ALL PRIVILEGES ON TABLE business_automation_settings TO aicrm_app;
