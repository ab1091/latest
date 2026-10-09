"""
Workflow graph engine — branching, multi-workflow-per-stage automation.

Replaces the old single fixed sequence (core/lead_sequencer.py, kept
in place for one release as an audit fallback, no longer wired up).

Execution model: event-driven, just-in-time. Only ONE scheduled_callbacks
row is ever pending per active enrollment at a time, inserted right before
it's needed — never a whole path enqueued upfront — which is what makes
branching possible. scheduled_callbacks / ai-service's existing 30s poller
(core/callback_scheduler.py) is reused as-is as the executor; this module
only ever inserts exactly one row per "next step."

Graph walk (_advance): instantaneous nodes (move_stage/add_tag/notify_staff/
trigger) are processed synchronously in a loop within one transaction.
'wait' nodes are collapsed — never materialized as their own resting state —
their single outgoing edge MUST point to an actionable node (send_sms/
send_email/ai_call), which gets scheduled at NOW()+wait duration directly.
Actionable nodes stop the loop (status='waiting') until an external caller
reports the outcome via advance_after_action():
  - send_sms / send_email: outcome known immediately after the send attempt.
  - ai_call: outcome only known later, from the Vapi webhook.
branch_condition nodes support two evaluation modes (see config docs on
_evaluate_branch below): 'last_result' resolves synchronously against the
immediately-preceding node's recorded outcome (e.g. call answered/no-answer);
'reply_check' needs a real time window to elapse (has the lead replied by
X hours from now?) and is scheduled as a check-type row (action_type IS NULL)
that the poller fires like any other due callback, without sending anything.
"""
import random
import uuid
import logging

from psycopg2.extras import Json

logger = logging.getLogger(__name__)

MAX_ADVANCE_STEPS = 50  # guards against a misconfigured cyclic graph


class WorkflowEngineError(Exception):
    pass


# ── Graph helpers ────────────────────────────────────────────────────────────

def _get_node(cur, workflow_id: str, node_key: str) -> dict:
    cur.execute(
        "SELECT * FROM workflow_nodes WHERE workflow_id = %s AND node_key = %s",
        (workflow_id, node_key),
    )
    node = cur.fetchone()
    if not node:
        raise WorkflowEngineError(f"Node {node_key} not found in workflow {workflow_id}")
    return dict(node)


def _get_outgoing_edges(cur, workflow_id: str, node_key: str) -> list:
    cur.execute(
        "SELECT to_node_key, branch_label FROM workflow_edges WHERE workflow_id = %s AND from_node_key = %s",
        (workflow_id, node_key),
    )
    return [dict(r) for r in cur.fetchall()]


def _single_next(cur, workflow_id: str, node_key: str) -> str | None:
    edges = _get_outgoing_edges(cur, workflow_id, node_key)
    return edges[0]["to_node_key"] if edges else None


def _wait_seconds(config: dict) -> int:
    amount = config.get("amount", 0)
    unit = config.get("unit", "minutes")
    if unit == "seconds":
        return int(amount)
    if unit == "hours":
        return int(amount * 3600)
    if unit == "days":
        return int(amount * 86400)
    return int(amount * 60)  # minutes default


def _last_run_result(cur, enrollment_id: str) -> dict:
    cur.execute(
        "SELECT result FROM workflow_node_runs WHERE enrollment_id = %s ORDER BY created_at DESC LIMIT 1",
        (enrollment_id,),
    )
    row = cur.fetchone()
    return row["result"] if row and row["result"] else {}


def _node_run_for(cur, enrollment_id: str, node_key: str) -> dict | None:
    cur.execute(
        "SELECT status, result FROM workflow_node_runs WHERE enrollment_id = %s AND node_key = %s "
        "ORDER BY created_at DESC LIMIT 1",
        (enrollment_id, node_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _record_run(cur, enrollment_id: str, node_key: str, node_type: str, status: str,
                 scheduled_callback_id: str = None, result: dict = None) -> str:
    run_id = f"wnr_{uuid.uuid4().hex[:12]}"
    cur.execute(
        """
        INSERT INTO workflow_node_runs
            (id, enrollment_id, node_key, node_type, status, scheduled_callback_id, result,
             started_at, completed_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s IN ('running','scheduled') THEN NOW() ELSE NULL END,
                CASE WHEN %s IN ('completed','failed','skipped') THEN NOW() ELSE NULL END,
                clock_timestamp())
        """,
        (run_id, enrollment_id, node_key, node_type, status, scheduled_callback_id,
         Json(result or {}), status, status),
    )
    return run_id


def _set_enrollment(cur, enrollment_id: str, current_node_key: str, status: str):
    cur.execute(
        "UPDATE lead_workflow_enrollments SET current_node_key = %s, status = %s, updated_at = NOW() WHERE id = %s",
        (current_node_key, status, enrollment_id),
    )


# ── Action scheduling ────────────────────────────────────────────────────────

def _schedule_action(cur, enrollment: dict, node: dict, delay_seconds: int, lead: dict) -> str:
    """
    Insert exactly one scheduled_callbacks row for a send_sms/ai_call action node.

    call_reason doubles as the per-call goal/context for ai_call nodes — see
    ai-service/core/callback_scheduler.py::_fire_callback(), which appends it
    verbatim into the call's system prompt as "CONTEXT: {call_reason}". A
    node's config.goal (same field send_sms nodes use) lets each ai_call step
    carry its own purpose (e.g. a Day-2 "check in, are they still interested"
    call vs an interested-lead "work toward booking an appointment" call)
    instead of every workflow call sounding identical.
    """
    cb_id = f"cb_{uuid.uuid4().hex[:12]}"
    node_type = node["node_type"]
    action_type = "sms" if node_type == "send_sms" else ("call" if node_type == "ai_call" else "email")

    # Real calls get a small random jitter on top of the node's own delay —
    # a bulk CSV import enrolls every row in the same tight loop, so with no
    # jitter every lead's Call 1 lands in the exact same 30s poller tick and
    # dials out back-to-back within a couple seconds of each other. Spreads
    # a batch out over a few minutes instead of firing as one concurrent
    # burst, without meaningfully delaying any single lead's "first" call.
    if action_type == "call":
        delay_seconds += random.randint(15, 240)
    call_reason = (node.get("config", {}).get("goal") or "Workflow automation step") if node_type == "ai_call" else "Workflow automation step"
    cur.execute(
        """
        INSERT INTO scheduled_callbacks
            (id, lead_id, business_id, phone, scheduled_at, status,
             call_reason, callback_type, sms_channel, workflow_enrollment_id, workflow_node_key, action_type)
        VALUES (%s, %s, %s, %s, NOW() + (%s || ' seconds')::interval,
                'pending', %s, %s, %s, %s, %s, %s)
        """,
        (cb_id, lead["id"], lead["business_id"], lead["phone"], delay_seconds,
         call_reason, action_type, node.get("config", {}).get("channel", "sms"),
         enrollment["id"], node["node_key"], action_type),
    )
    return cb_id


def _schedule_branch_check(cur, enrollment: dict, node: dict, delay_seconds: int, lead: dict) -> str:
    """Insert a check-type row (no action_type) — the poller evaluates, doesn't send anything."""
    cb_id = f"cb_{uuid.uuid4().hex[:12]}"
    cur.execute(
        """
        INSERT INTO scheduled_callbacks
            (id, lead_id, business_id, phone, scheduled_at, status,
             call_reason, workflow_enrollment_id, workflow_node_key)
        VALUES (%s, %s, %s, %s, NOW() + (%s || ' seconds')::interval,
                'pending', 'Workflow branch check', %s, %s)
        """,
        (cb_id, lead["id"], lead["business_id"], lead["phone"], delay_seconds,
         enrollment["id"], node["node_key"]),
    )
    return cb_id


def _evaluate_branch(cur, enrollment: dict, node: dict) -> str:
    """
    branch_condition config shapes:
      last_result mode (resolves immediately, e.g. call outcome):
        {"mode": "last_result", "field": "outcome", "equals": "confirmed",
         "true_branch": "yes", "false_branch": "no"}
        "equals" matches a single value. For "did the lead actually answer",
        an ai_call's outcome can be several distinct not-answered values
        ("no_answer", "voicemail", "failed") — use "in"/"not_in" (a list)
        instead of "equals" for that case:
        {"mode": "last_result", "field": "outcome",
         "not_in": ["no_answer", "voicemail", "failed"],
         "true_branch": "answered", "false_branch": "no_answer"}
      reply_check mode (needs a real time window — handled by the caller
        scheduling a check row BEFORE calling this; this function is only
        invoked once the check fires, with the reply outcome already in
        the last run's result):
        {"mode": "reply_check", "timeout_hours": 4,
         "true_branch": "replied", "false_branch": "no_reply"}
    Returns the branch_label to follow.
    """
    config = node.get("config", {})
    mode = config.get("mode", "last_result")
    last_result = _last_run_result(cur, enrollment["id"])

    if mode == "reply_check":
        matched = bool(last_result.get("replied"))
    else:
        field = config.get("field", "outcome")
        value = last_result.get(field)
        if "in" in config:
            matched = value in config["in"]
        elif "not_in" in config:
            matched = value not in config["not_in"]
        else:
            matched = value == config.get("equals")

    return config.get("true_branch", "yes") if matched else config.get("false_branch", "no")


# ── Core graph walk ──────────────────────────────────────────────────────────

def _advance(enrollment_id: str, conn, cur, lead: dict = None):
    cur.execute("SELECT * FROM lead_workflow_enrollments WHERE id = %s FOR UPDATE", (enrollment_id,))
    enrollment = dict(cur.fetchone())
    if enrollment["status"] not in ("active", "waiting"):
        return  # already completed/cancelled/paused/failed — nothing to do

    if lead is None:
        cur.execute("SELECT id, business_id, phone, first_name, last_name, tags FROM leads WHERE id = %s",
                    (enrollment["lead_id"],))
        lead = dict(cur.fetchone())

    workflow_id = enrollment["workflow_id"]
    node_key = enrollment["current_node_key"]
    status = "active"

    for _ in range(MAX_ADVANCE_STEPS):
        if node_key is None:
            status = "completed"
            break

        node = _get_node(cur, workflow_id, node_key)
        node_type = node["node_type"]

        if node_type == "trigger":
            node_key = _single_next(cur, workflow_id, node_key)
            continue

        if node_type == "move_stage":
            from core.lead_lifecycle import transition_lead_status, InvalidTransition
            event = node.get("config", {}).get("event")
            if event:
                try:
                    transition_lead_status(lead["id"], event=event, conn=conn, cur=cur, force=True)
                except InvalidTransition as e:
                    logger.warning(f"[workflow_engine] move_stage node {node_key} skipped: {e}")
            _record_run(cur, enrollment_id, node_key, node_type, "completed")
            node_key = _single_next(cur, workflow_id, node_key)
            continue

        if node_type == "add_tag":
            tag = node.get("config", {}).get("tag")
            if tag:
                cur.execute(
                    "UPDATE leads SET tags = array_append(tags, %s) WHERE id = %s AND NOT (%s = ANY(tags))",
                    (tag, lead["id"], tag),
                )
            _record_run(cur, enrollment_id, node_key, node_type, "completed")
            node_key = _single_next(cur, workflow_id, node_key)
            continue

        if node_type == "notify_staff":
            from core.activity_feed import emit
            message = node.get("config", {}).get("message", "Workflow notification")
            emit(business_id=lead["business_id"], event_type="workflow_notify_staff",
                 title=message, lead_id=lead["id"], conn=conn, cur=cur)
            _record_run(cur, enrollment_id, node_key, node_type, "completed")
            node_key = _single_next(cur, workflow_id, node_key)
            continue

        if node_type == "branch_condition":
            config = node.get("config", {})
            existing_run = _node_run_for(cur, enrollment_id, node_key)
            if config.get("mode") == "reply_check" and existing_run is None:
                # First time reaching this node: schedule the check, stop and wait for it to fire.
                delay = int(config.get("timeout_hours", 4) * 3600)
                cb_id = _schedule_branch_check(cur, enrollment, node, delay, lead)
                _record_run(cur, enrollment_id, node_key, node_type, "scheduled", scheduled_callback_id=cb_id)
                _set_enrollment(cur, enrollment_id, node_key, "waiting")
                return
            if config.get("mode") == "reply_check" and existing_run["status"] != "completed":
                # Check row scheduled but hasn't fired yet — nothing to do.
                return
            branch_label = _evaluate_branch(cur, enrollment, node)
            _record_run(cur, enrollment_id, node_key, node_type, "completed", result={"branch": branch_label})
            edges = _get_outgoing_edges(cur, workflow_id, node_key)
            match = next((e for e in edges if e["branch_label"] == branch_label), None)
            node_key = match["to_node_key"] if match else None
            continue

        if node_type == "wait":
            delay = _wait_seconds(node.get("config", {}))
            target_key = _single_next(cur, workflow_id, node_key)
            if not target_key:
                node_key = None
                continue
            target_node = _get_node(cur, workflow_id, target_key)
            if target_node["node_type"] not in ("send_sms", "send_email", "ai_call"):
                raise WorkflowEngineError(
                    f"wait node {node_key} must be followed by an action node "
                    f"(send_sms/send_email/ai_call), got {target_node['node_type']}"
                )
            _record_run(cur, enrollment_id, node_key, node_type, "completed")
            cb_id = _schedule_action(cur, enrollment, target_node, delay, lead)
            _record_run(cur, enrollment_id, target_key, target_node["node_type"], "scheduled", scheduled_callback_id=cb_id)
            _set_enrollment(cur, enrollment_id, target_key, "waiting")
            return

        if node_type in ("send_sms", "ai_call", "send_email"):
            cb_id = _schedule_action(cur, enrollment, node, 0, lead)
            _record_run(cur, enrollment_id, node_key, node_type, "scheduled", scheduled_callback_id=cb_id)
            _set_enrollment(cur, enrollment_id, node_key, "waiting")
            return

        if node_type == "end":
            node_key = None
            status = "completed"
            continue

        raise WorkflowEngineError(f"Unknown node_type '{node_type}' at {node_key}")
    else:
        logger.error(f"[workflow_engine] enrollment {enrollment_id} exceeded {MAX_ADVANCE_STEPS} steps — a cyclic graph? marking failed")
        _set_enrollment(cur, enrollment_id, node_key, "failed")
        return

    _set_enrollment(cur, enrollment_id, None, status)


def advance_after_action(enrollment_id: str, node_key: str, result: dict, conn, cur):
    """
    Called once an externally-dispatched action's outcome is known:
      - send_sms/send_email: right after the send attempt (success/failure).
      - ai_call: from the Vapi call-ended webhook.
      - branch_condition (reply_check mode): from the poller firing the
        scheduled check row.
    Marks that node's run completed/failed, advances to its next node, and
    resumes the graph walk.
    """
    cur.execute("SELECT * FROM lead_workflow_enrollments WHERE id = %s FOR UPDATE", (enrollment_id,))
    enrollment = cur.fetchone()
    if not enrollment:
        raise WorkflowEngineError(f"Enrollment {enrollment_id} not found")
    enrollment = dict(enrollment)
    if enrollment["current_node_key"] != node_key:
        logger.warning(f"[workflow_engine] advance_after_action for {node_key} but enrollment is at "
                        f"{enrollment['current_node_key']} — ignoring stale callback")
        return

    node = _get_node(cur, enrollment["workflow_id"], node_key)
    run_status = "failed" if result.get("failed") else "completed"
    cur.execute(
        """
        UPDATE workflow_node_runs SET status = %s, result = %s, completed_at = NOW()
        WHERE enrollment_id = %s AND node_key = %s AND status IN ('scheduled', 'running')
        """,
        (run_status, Json(result), enrollment_id, node_key),
    )

    if node["node_type"] == "branch_condition":
        # The check-row fired; leave current_node_key pointing here so
        # _advance's branch_condition branch re-evaluates using this result.
        _set_enrollment(cur, enrollment_id, node_key, "active")
    else:
        next_key = _single_next(cur, enrollment["workflow_id"], node_key)
        _set_enrollment(cur, enrollment_id, next_key, "active")

    _advance(enrollment_id, conn, cur)


# ── Enrollment lifecycle ─────────────────────────────────────────────────────

def enroll_lead(lead_id: str, business_id: str, workflow_id: str, conn, cur) -> str | None:
    cur.execute(
        "SELECT node_key FROM workflow_nodes WHERE workflow_id = %s AND node_type = 'trigger' LIMIT 1",
        (workflow_id,),
    )
    trigger = cur.fetchone()
    if not trigger:
        logger.warning(f"[workflow_engine] workflow {workflow_id} has no trigger node — skipping enrollment")
        return None

    cur.execute("SELECT version FROM workflows WHERE id = %s", (workflow_id,))
    version = cur.fetchone()["version"]

    enrollment_id = f"lwe_{uuid.uuid4().hex[:12]}"
    cur.execute(
        """
        INSERT INTO lead_workflow_enrollments (id, lead_id, workflow_id, workflow_version, current_node_key, status)
        VALUES (%s, %s, %s, %s, %s, 'active')
        ON CONFLICT (lead_id, workflow_id) WHERE status IN ('active','waiting') DO NOTHING
        """,
        (enrollment_id, lead_id, workflow_id, version, trigger["node_key"]),
    )
    if cur.rowcount == 0:
        logger.info(f"[workflow_engine] lead {lead_id} already actively enrolled in workflow {workflow_id}")
        return None

    _advance(enrollment_id, conn, cur)
    logger.info(f"[workflow_engine] lead={lead_id} enrolled in workflow={workflow_id} enrollment={enrollment_id}")

    try:
        cur.execute("SELECT name FROM workflows WHERE id = %s", (workflow_id,))
        wf_row = cur.fetchone()
        cur.execute("SELECT first_name, last_name, phone FROM leads WHERE id = %s", (lead_id,))
        lead_row = cur.fetchone()
        lead_name = " ".join(filter(None, [lead_row.get("first_name"), lead_row.get("last_name")])).strip() if lead_row else lead_id
        from core.activity_feed import emit
        emit(
            business_id=business_id, event_type="workflow_enrolled",
            title=f"{lead_name or lead_id} enrolled in “{wf_row['name'] if wf_row else workflow_id}”",
            lead_id=lead_id, conn=conn, cur=cur,
            metadata={"workflow_id": workflow_id, "enrollment_id": enrollment_id},
        )
    except Exception as e:
        logger.warning(f"[workflow_engine] activity feed emit failed for enrollment {enrollment_id}: {e}")

    return enrollment_id


def enroll_default_workflows_for_stage(lead_id: str, business_id: str, stage: str, conn, cur):
    """Enroll a lead into every active, default-for-trigger workflow matching this stage."""
    cur.execute(
        """
        SELECT id FROM workflows
        WHERE business_id = %s AND status = 'active' AND is_default_for_trigger
          AND trigger_type = 'stage_enter' AND trigger_stage = %s
        """,
        (business_id, stage),
    )
    for row in cur.fetchall():
        enroll_lead(lead_id, business_id, row["id"], conn, cur)


def on_stage_change(lead_id: str, from_stage: str, new_stage: str, business_id: str, conn, cur):
    """
    Called from lead_lifecycle.transition_lead_status whenever a lead's
    stage changes. Cancels other active enrollments for the lead (unless
    their workflow opts out via trigger_config.persist_across_stages) and
    enrolls into whichever workflows are configured as default for the
    new stage.
    """
    cur.execute(
        """
        SELECT e.id, w.trigger_config
        FROM lead_workflow_enrollments e
        JOIN workflows w ON w.id = e.workflow_id
        WHERE e.lead_id = %s AND e.status IN ('active', 'waiting')
        """,
        (lead_id,),
    )
    for row in cur.fetchall():
        if (row["trigger_config"] or {}).get("persist_across_stages"):
            continue
        cur.execute(
            "UPDATE scheduled_callbacks SET status = 'cancelled', updated_at = NOW() "
            "WHERE workflow_enrollment_id = %s AND status = 'pending'",
            (row["id"],),
        )
        cancel_status = "cancelled" if new_stage in ("closed", "dead") else "paused"
        cur.execute(
            "UPDATE lead_workflow_enrollments SET status = %s, updated_at = NOW() WHERE id = %s",
            (cancel_status, row["id"]),
        )

    # A lead going dead (declined) means NO further automated contact of any
    # kind, from any source — not just the workflow-linked callbacks handled
    # above. This also catches standalone callbacks (a "call me back in X"
    # request via SMS or during a live call, the qualified-lead 24h follow-up
    # call) that aren't tied to a workflow_enrollment_id.
    if new_stage == "dead":
        cur.execute(
            "UPDATE scheduled_callbacks SET status = 'cancelled', updated_at = NOW() "
            "WHERE lead_id = %s AND status = 'pending'",
            (lead_id,),
        )

    # The quoted/closed agent (a distinct lead_configs rule) is meant to work
    # off a condensed deal summary instead of replaying the full raw
    # qualification history — regenerate it right as the lead crosses into
    # either stage so that summary is fresh the moment the agent needs it.
    # Best-effort: an OpenAI hiccup here must never break the stage transition
    # itself, same reasoning as recompute_score below.
    if new_stage in ("quoted", "closed"):
        from core.lead_summary import generate_and_save_summary
        try:
            generate_and_save_summary(lead_id, cur)
        except Exception as e:
            logger.warning(f"[workflow_engine] summary regen failed for lead={lead_id}: {e}")

    enroll_default_workflows_for_stage(lead_id, business_id, new_stage, conn, cur)
    logger.info(f"[workflow_engine] lead={lead_id} stage {from_stage}->{new_stage}: enrollments reconciled")
