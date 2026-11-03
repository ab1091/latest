-- Adds retry_count to scheduled_callbacks and delivery tracking columns to messages

ALTER TABLE scheduled_callbacks
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'delivered',
    ADD COLUMN IF NOT EXISTS error_reason TEXT,
    ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'sms',
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
