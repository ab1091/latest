-- Drops the legacy lead-engagement-sequence engine (migration 013),
-- superseded by the workflow graph engine (migration 017,
-- crm-service/core/workflow_engine.py). Confirmed zero live callers:
-- core/lead_sequencer.py's two functions were never imported by
-- lead_lifecycle.py (which calls workflow_engine.on_stage_change instead),
-- and no frontend page references /api/lead-sequences. Both
-- core/lead_sequencer.py and routers/lead_sequences.py have been deleted.
--
-- CASCADE drops the FK constraints this creates on scheduled_callbacks
-- (sequence_enrollment_id, sequence_step_id) — same as migration 029's
-- handling of patient_id — but leaves those two columns in place on
-- scheduled_callbacks as plain nullable TEXT columns; no code reads them
-- going forward.
DROP TABLE IF EXISTS lead_sequence_enrollments CASCADE;
DROP TABLE IF EXISTS lead_sequence_steps CASCADE;
DROP TABLE IF EXISTS lead_sequences CASCADE;
