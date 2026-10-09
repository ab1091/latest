-- scheduled_callbacks.callback_type never got updated when send_email
-- workflow nodes were introduced (action_type already allows 'email',
-- callback_type didn't) — any workflow with a send_email step crashed
-- the moment it tried to schedule that node. Widen it to match.
ALTER TABLE scheduled_callbacks DROP CONSTRAINT IF EXISTS scheduled_callbacks_callback_type_check;
ALTER TABLE scheduled_callbacks ADD CONSTRAINT scheduled_callbacks_callback_type_check
    CHECK (callback_type = ANY (ARRAY['sms'::text, 'call'::text, 'email'::text]));
