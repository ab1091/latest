"""
Centralized lead status/stage state machine.

All writes to leads.sub_status / leads.stage MUST go through
transition_lead_status() — no other code should UPDATE those columns
directly. This keeps status semantics consistent across every entry
point (SMS replies, AI qualification/quote detection, call outcomes,
appointment booking, the follow-up scheduler) and gives the journey
timeline a single audit trail (lead_status_history) to read from.
"""
import uuid
import logging
from psycopg2.extras import Json

from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)

# sub_status (internal, granular) -> stage (client-facing, 7-value pipeline)
STAGE_OF = {
    "new":                    "new_lead",
    "contacted":              "new_lead",
    "follow_up_sent":         "new_lead",
    "stale":                  "old_lead",
    "responded":              "connected",
    "qualified":              "connected",
    "quoted":                 "quoted",
    "appointment_scheduled":  "appointment_scheduled",
    "converted":              "closed",
    "dead":                   "dead",
}

# Allowed sub_status -> sub_status transitions. Anything not listed here
# is rejected unless force=True (admin manual override).
TRANSITIONS = {
    "new":                   {"contacted", "responded", "dead"},
    "contacted":             {"responded", "follow_up_sent", "stale", "dead"},
    "follow_up_sent":        {"responded", "dead"},
    "stale":                 {"responded", "dead"},
    # appointment_scheduled is reachable directly from responded (not just
    # via qualified/quoted) because a call can book an appointment on the
    # spot without the SMS-side qualified/quoted classifier ever having run
    # on this lead yet.
    "responded":             {"qualified", "quoted", "appointment_scheduled", "dead"},
    "qualified":             {"quoted", "appointment_scheduled", "converted", "dead"},
    "quoted":                {"appointment_scheduled", "converted", "dead"},
    "appointment_scheduled": {"converted", "dead"},
    "converted":             set(),
    # Not fully terminal — a lead who declined and later texts back in is a
    # real re-engagement signal (inbound_reply -> responded), not something
    # that should be silently ignored forever. Only a human/AI conversation
    # reopens it though: nothing else auto-fires from "dead".
    "dead":                  {"responded"},
}

# event -> target sub_status. Callers normally pass an event; to_sub_status
# is only for admin overrides / cases with no natural event name.
EVENT_TO_SUB_STATUS = {
    "welcome_sms_sent":       "contacted",
    "no_reply_24h":           "stale",
    "inbound_reply":          "responded",
    "ai_qualified":           "qualified",
    "ai_quoted":              "quoted",
    # NOT "converted" — "confirmed" here means the call ended with an
    # appointment booked (voice_calls.outcome='confirmed' is only ever set
    # when an appointments row was actually created), not a completed sale.
    # A booked follow-up with a licensed agent is not a closed deal — only a
    # human should ever move a lead to converted/closed (see appointment_
    # completed below, and the absence of any AI-triggered "converted" event
    # anywhere else in the codebase — that's deliberate policy, not an
    # oversight).
    "call_outcome_confirmed":            "appointment_scheduled",
    "call_outcome_cancelled":            "contacted",
    "call_outcome_reschedule_requested": "contacted",
    "call_outcome_no_answer":            "new",
    "call_outcome_voicemail":            "new",
    "call_outcome_engaged":              "responded",
    "appointment_booked":       "appointment_scheduled",
    # Currently unused — grep finds no caller anywhere. Flagging rather than
    # silently leaving it: per policy (see call_outcome_confirmed above), an
    # AI/automation trigger should never move a lead straight to converted.
    # If this ever gets wired up (e.g. an ai_call step that confirms an
    # appointment happened), it should land on a "needs human close" signal
    # (a staff task) rather than converted directly.
    "appointment_completed":   "converted",
    "sequence_follow_up_sent": "follow_up_sent",
    "mark_dead":              "dead",
}


class InvalidTransition(Exception):
    pass


def transition_lead_status(
    lead_id: str,
    event: str,
    to_sub_status: str = None,
    conn=None,
    cur=None,
    metadata: dict = None,
    force: bool = False,
) -> dict | None:
    """
    Single entrypoint for all leads.sub_status / leads.stage writes.

    - Resolves the target sub_status from `event` (via EVENT_TO_SUB_STATUS)
      unless `to_sub_status` is explicitly given.
    - Validates against TRANSITIONS unless force=True.
    - Writes sub_status + derived stage + updated_at, inserts a
      lead_status_history row.
    - If stage changed, calls workflow_engine.on_stage_change() to pause/
      cancel the lead's workflow enrollment(s) and enroll into defaults
      for the new stage.
    - Idempotent: no-ops (returns None) if the target sub_status equals
      the current one.
    - Caller may pass an existing open conn/cur (to run inside their own
      transaction); otherwise a new connection is opened and committed.
    """
    target = to_sub_status or EVENT_TO_SUB_STATUS.get(event)
    if not target:
        raise ValueError(f"Unknown event '{event}' and no to_sub_status given")
    if target not in STAGE_OF:
        raise ValueError(f"'{target}' is not a valid sub_status")

    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
        cur = dict_cursor(conn)

    try:
        cur.execute("SELECT sub_status, stage, business_id, first_name, last_name, phone FROM leads WHERE id = %s FOR UPDATE", (lead_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Lead {lead_id} not found")

        current_sub_status = row["sub_status"]
        current_stage = row["stage"]
        business_id = row["business_id"]

        if current_sub_status == target:
            return None  # idempotent no-op

        if not force and target not in TRANSITIONS.get(current_sub_status, set()):
            raise InvalidTransition(
                f"Lead {lead_id}: transition {current_sub_status} -> {target} "
                f"(event={event}) is not allowed"
            )

        new_stage = STAGE_OF[target]

        cur.execute(
            "UPDATE leads SET sub_status = %s, stage = %s, updated_at = NOW() WHERE id = %s",
            (target, new_stage, lead_id),
        )

        history_id = f"lsh_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO lead_status_history
                (id, lead_id, from_stage, to_stage, from_sub_status, to_sub_status, event, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (history_id, lead_id, current_stage, new_stage, current_sub_status, target, event,
             Json(metadata or {})),
        )

        if new_stage != current_stage:
            from core.workflow_engine import on_stage_change
            on_stage_change(lead_id, current_stage, new_stage, business_id, conn, cur)

        lead_name = " ".join(filter(None, [row.get("first_name"), row.get("last_name")])).strip() or row.get("phone") or lead_id
        from core.activity_feed import emit
        try:
            emit(
                business_id=business_id, event_type="stage_change",
                title=f"{lead_name}: {current_stage} → {new_stage} ({event})",
                lead_id=lead_id, conn=conn, cur=cur,
                metadata={"event": event, "from_sub_status": current_sub_status, "to_sub_status": target},
            )
        except Exception as e:
            logger.warning(f"[lead_lifecycle] activity feed emit failed for {lead_id}: {e}")

        from core.lead_scoring import recompute_score
        try:
            recompute_score(lead_id, cur)
        except Exception as e:
            logger.warning(f"[lead_lifecycle] score recompute failed for {lead_id}: {e}")

        if owns_conn:
            conn.commit()

        logger.info(
            f"[lead_lifecycle] lead={lead_id} event={event} "
            f"{current_sub_status}->{target} (stage {current_stage}->{new_stage})"
        )

        return {
            "lead_id": lead_id,
            "old_stage": current_stage,
            "new_stage": new_stage,
            "old_sub_status": current_sub_status,
            "new_sub_status": target,
        }
    except Exception:
        if owns_conn:
            conn.rollback()
        raise
    finally:
        if owns_conn:
            cur.close()
            conn.close()
