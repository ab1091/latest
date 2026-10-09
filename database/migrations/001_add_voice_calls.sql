-- Migration 001: Add voice_calls table for Vapi AI reminder calls
-- Run this if your DB already exists and you don't want to re-init from scratch.

CREATE TABLE IF NOT EXISTS voice_calls (
    id TEXT PRIMARY KEY,
    appointment_id TEXT NOT NULL,
    call_id TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'vapi',
    status TEXT DEFAULT 'initiated' CHECK(status IN ('initiated', 'queued', 'ringing', 'in-progress', 'ended', 'failed')),
    outcome TEXT CHECK(outcome IN ('confirmed', 'cancelled', 'reschedule_requested', 'no_answer', 'voicemail', 'failed')),
    transcript TEXT,
    summary TEXT,
    duration_seconds INTEGER,
    raw_payload TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_voice_calls_appointment ON voice_calls(appointment_id);
CREATE INDEX IF NOT EXISTS idx_voice_calls_call_id ON voice_calls(call_id);
CREATE INDEX IF NOT EXISTS idx_voice_calls_status ON voice_calls(status);
CREATE INDEX IF NOT EXISTS idx_voice_calls_outcome ON voice_calls(outcome);
