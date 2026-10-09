-- New "Old Lead" stage (sub_status "stale") — sits between New Lead and
-- Connected. A lead moves here automatically 24h after first contact if
-- they never replied. If they reply later (from any state), they still
-- move to Connected as normal.
BEGIN;

ALTER TABLE leads DROP CONSTRAINT leads_stage_check;
ALTER TABLE leads ADD CONSTRAINT leads_stage_check
    CHECK (stage = ANY (ARRAY['new_lead','old_lead','connected','quoted','appointment_scheduled','closed','dead']));

ALTER TABLE leads DROP CONSTRAINT leads_sub_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_sub_status_check
    CHECK (sub_status = ANY (ARRAY['new','contacted','stale','responded','follow_up_sent','qualified','quoted','appointment_scheduled','converted','dead']));

COMMIT;
