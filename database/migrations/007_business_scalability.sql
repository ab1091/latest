-- 007: Per-business Twilio routing and dynamic AI prompts

ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS twilio_number  TEXT,
    ADD COLUMN IF NOT EXISTS system_prompt  TEXT,
    ADD COLUMN IF NOT EXISTS google_client_id     TEXT,
    ADD COLUMN IF NOT EXISTS google_client_secret TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_businesses_twilio_number
    ON businesses(twilio_number) WHERE twilio_number IS NOT NULL;
