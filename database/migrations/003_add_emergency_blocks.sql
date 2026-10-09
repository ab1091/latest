-- Migration: Emergency blocks table + ai_explanation for emergency reminder calls

CREATE TABLE IF NOT EXISTS emergency_blocks (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    reason TEXT NOT NULL,
    ai_explanation TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'resolved')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_emergency_blocks_business ON emergency_blocks(business_id);
CREATE INDEX IF NOT EXISTS idx_emergency_blocks_provider ON emergency_blocks(provider_id);
CREATE INDEX IF NOT EXISTS idx_emergency_blocks_times ON emergency_blocks(start_time, end_time);

-- Add ai_explanation to reminder jobs so emergency context is passed to the voice AI
ALTER TABLE appointment_reminder_jobs
    ADD COLUMN IF NOT EXISTS ai_explanation TEXT;
