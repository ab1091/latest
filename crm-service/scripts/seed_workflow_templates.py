"""
Seeds the 9 starter workflow templates into the workflows table
(is_template=TRUE, business_id=NULL). Idempotent — re-running is safe
(ON CONFLICT on the partial unique index over template_key WHERE is_template).

Businesses "duplicate" a template via POST /api/workflows/{template_id}/duplicate
(crm-service/routers/workflows.py), which deep-copies these nodes/edges into
a new business-owned draft workflow — no separate template schema.

Run once: crm-service/venv/bin/python scripts/seed_workflow_templates.py
"""
import sys
import os
import uuid
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from core.db import get_conn, dict_cursor  # noqa: E402


def _linear_graph(cur, workflow_id: str, steps: list[tuple]):
    """
    steps: ordered list of (wait_seconds_before, node_type, config_dict).
    Builds trigger -> [wait, node]* -> end, wiring every edge in between.
    wait_seconds_before == 0 skips the wait node entirely (action fires
    on enrollment with no delay).
    """
    prev_key = "trigger"
    cur.execute(
        "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'trigger', 'trigger', '{}')",
        (f"wn_{uuid.uuid4().hex[:12]}", workflow_id),
    )

    for i, (wait_seconds, node_type, config) in enumerate(steps, start=1):
        if wait_seconds > 0:
            wait_key = f"wait_{i}"
            cur.execute(
                "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, 'wait', %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", workflow_id, wait_key, json.dumps({"amount": wait_seconds, "unit": "seconds"})),
            )
            cur.execute(
                "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, %s, %s)",
                (f"we_{uuid.uuid4().hex[:12]}", workflow_id, prev_key, wait_key),
            )
            prev_key = wait_key

        step_key = f"step_{i}"
        cur.execute(
            "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, %s, %s)",
            (f"wn_{uuid.uuid4().hex[:12]}", workflow_id, step_key, node_type, json.dumps(config)),
        )
        cur.execute(
            "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, %s, %s)",
            (f"we_{uuid.uuid4().hex[:12]}", workflow_id, prev_key, step_key),
        )
        prev_key = step_key

    cur.execute(
        "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'end', 'end', '{}')",
        (f"wn_{uuid.uuid4().hex[:12]}", workflow_id),
    )
    cur.execute(
        "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, %s, 'end')",
        (f"we_{uuid.uuid4().hex[:12]}", workflow_id, prev_key),
    )


def _upsert_template(cur, template_key: str, name: str, description: str, trigger_stage: str | None,
                      trigger_type: str = "manual", trigger_config: dict | None = None):
    cur.execute("SELECT id FROM workflows WHERE template_key = %s AND is_template", (template_key,))
    existing = cur.fetchone()
    if existing:
        workflow_id = existing["id"]
        cur.execute("DELETE FROM workflow_edges WHERE workflow_id = %s", (workflow_id,))
        cur.execute("DELETE FROM workflow_nodes WHERE workflow_id = %s", (workflow_id,))
        cur.execute(
            "UPDATE workflows SET name=%s, description=%s, trigger_type=%s, trigger_stage=%s, trigger_config=%s WHERE id = %s",
            (name, description, trigger_type, trigger_stage, json.dumps(trigger_config or {}), workflow_id),
        )
        print(f"  updating existing template '{template_key}' -> {workflow_id}")
    else:
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO workflows (id, business_id, name, description, trigger_type, trigger_stage,
                                    trigger_config, status, is_template, template_key)
            VALUES (%s, NULL, %s, %s, %s, %s, %s, 'active', TRUE, %s)
            """,
            (workflow_id, name, description, trigger_type, trigger_stage,
             json.dumps(trigger_config or {}), template_key),
        )
        print(f"  creating template '{template_key}' -> {workflow_id}")
    return workflow_id


def seed():
    conn = get_conn()
    cur = dict_cursor(conn)

    # 1. New Lead Fast Response
    wf = _upsert_template(
        cur, "new_lead_fast_response", "New Lead Fast Response",
        "Instant SMS, AI call after 10 minutes, follow-up SMS after 4 hours, reminder the next day.",
        trigger_stage="new_lead", trigger_type="stage_enter",
        trigger_config={"persist_across_stages": True},
    )
    _linear_graph(cur, wf, [
        (0,     "send_sms", {"channel": "sms", "goal":
            "Instant first-touch SMS — introduce yourself, thank them for their interest, and ask one "
            "open question about what type of coverage they're looking for."}),
        (600,   "ai_call",  {}),                                              # 10 min
        (14400, "send_sms", {"channel": "sms", "goal":
            "It's been 4 hours with no reply. Send a brief, low-pressure check-in — acknowledge they're "
            "probably busy, and ask if now's a better time to chat."}),  # 4h
        (86400, "send_sms", {"channel": "sms", "goal":
            "It's been a full day with no reply. Send a friendly reminder that you're still available "
            "to help, with a soft nudge — no pressure, just keeping the door open."}),  # 1 day
    ])

    # 2. Insurance Lead Nurture — message, wait for reply, message again if
    # silent. The call is NOT scheduled by this graph on a reply anymore —
    # a reply just hands the lead to the live SMS conversation (see
    # ai-service/api/sms/router.py::_check_call_confirmation), which proposes
    # a call once real interest is shown and only schedules one (~45min out,
    # full chat context attached) once the lead explicitly confirms they
    # want it — a dynamic, conversation-driven trigger instead of a blanket
    # "any reply -> call" timer. Two unanswered texts still get a direct
    # check-in call from this graph ("we've texted you twice, still
    # interested?") since there's no live conversation to hand off to.
    # trigger_config.persist_across_stages is required because a lead's
    # first reply moves them new_lead->connected, which would otherwise
    # pause/cancel this enrollment mid-flow (see workflow_engine.on_stage_change).
    wf = _upsert_template(
        cur, "insurance_lead_nurture", "Insurance Lead Nurture",
        "SMS, wait for reply, SMS again if silent — a reply hands off to the live conversation, "
        "which proposes and schedules a call once the lead actually confirms they want one; two "
        "unanswered texts trigger a direct check-in call instead of a third text.",
        trigger_stage="new_lead", trigger_type="stage_enter",
        trigger_config={"persist_across_stages": True},
    )

    def node(key, node_type, config):
        cur.execute(
            "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, %s, %s)",
            (f"wn_{uuid.uuid4().hex[:12]}", wf, key, node_type, json.dumps(config)),
        )

    def edge(from_key, to_key, branch_label=None):
        cur.execute(
            "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key, branch_label) VALUES (%s, %s, %s, %s, %s)",
            (f"we_{uuid.uuid4().hex[:12]}", wf, from_key, to_key, branch_label),
        )

    node("trigger", "trigger", {})

    node("sms_day1", "send_sms", {"channel": "sms", "static_text":
        "Hello, good day! I received your request for an insurance quote. What's the best time "
        "today for a quick call, or would you rather text? Reply NO THANKS to opt out of future "
        "text messages."})
    edge("trigger", "sms_day1")

    node("check_day1", "branch_condition", {"mode": "reply_check", "timeout_hours": 23,
                                             "true_branch": "replied", "false_branch": "no_reply"})
    edge("sms_day1", "check_day1")

    # A reply just stops the drip cadence here — it does NOT book a call by
    # itself anymore. The live conversation (router.py::_check_call_confirmation)
    # takes it from here and schedules the call once the lead actually says yes.
    # Each "replied" branch below gets its OWN End node right next door,
    # rather than both sharing one distant node — a single shared End forced
    # a long line to snake all the way across the diagram to reach it, which
    # is what made the graph look tangled. Functionally identical either way
    # (an End node does nothing but mark the enrollment complete); this is
    # purely so every edge stays a short hop to its immediate neighbor.
    node("end_engaged_day1", "end", {})
    edge("check_day1", "end_engaged_day1", "replied")

    node("sms_day2", "send_sms", {"channel": "sms", "goal":
        "Day 2 — they haven't replied yet, which means they never answered Day 1's question and "
        "nothing has actually been discussed or prepared for them yet. Do NOT say you have coverage "
        "options, a quote, or anything else 'ready' — there's nothing to base that on since they "
        "haven't shared what they need. Open with a warm, professional greeting (e.g. hoping they're "
        "having a good day) — not a repeat of Day 1's intro. Then simply check back in and ask if "
        "now's a good time to chat about their insurance needs. Warm and low-pressure, like a "
        "genuine invitation, not a sales pitch. Do not repeat Day 1's wording, and do not imply "
        "anything has already been prepared for them."})
    edge("check_day1", "sms_day2", "no_reply")

    node("check_day2", "branch_condition", {"mode": "reply_check", "timeout_hours": 24,
                                             "true_branch": "replied", "false_branch": "no_reply"})
    edge("sms_day2", "check_day2")

    node("end_engaged_day2", "end", {})
    edge("check_day2", "end_engaged_day2", "replied")

    node("call_checkin", "ai_call", {"goal":
        "We've texted this lead twice about insurance coverage (Day 1 and Day 2) over the past "
        "couple of days and they never replied to either one — there is no conversation to "
        "continue, only unanswered texts. This is a check-in call, not a sales pitch. Do NOT say "
        "'continue our conversation' or anything implying they've responded before. Open along "
        "the lines of: 'Hi, this is Riley from Shield Insurance Agency — we've been trying to "
        "reach you by text the past couple of days about insurance coverage, is now a good time "
        "to chat?' Then start the conversation fresh from there. If yes, help them from there. "
        "If no, or they're not interested, thank them for their time and let them go — no pressure."})
    edge("check_day2", "call_checkin", "no_reply")

    node("end_no_engagement", "end", {})
    edge("call_checkin", "end_no_engagement")

    # 3. Connected — Re-engagement Check
    # A lead reaches Connected the moment they reply once — Insurance Lead
    # Nurture (above) already ends there and hands off to the live
    # conversation. This is a safety net for AFTER that: if the live
    # conversation goes quiet again before the lead reaches Quoted, nudge
    # once by text, then a check-in call. Deliberately no
    # persist_across_stages, same reasoning as Appointment Scheduled below —
    # progress to Quoted/Closed cancels this automatically, so it only ever
    # fires for a genuine stall, not a lead who's actively moving forward.
    wf = _upsert_template(
        cur, "connected_reengagement", "Connected — Re-engagement Check",
        "For leads who replied once then went quiet again before reaching a quote — one text nudge, "
        "then a check-in call. Cancels itself automatically the moment the lead progresses.",
        trigger_stage="connected", trigger_type="stage_enter",
    )
    _linear_graph(cur, wf, [
        (86400, "send_sms", {"channel": "sms", "goal":
            "This lead engaged once (replied to an earlier text) but has gone quiet again since, and "
            "hasn't reached a quote yet. Send a warm, low-pressure check-in referencing that you were "
            "mid-conversation — do not restart the conversation from scratch or reintroduce yourself. "
            "One easy question to pick things back up."}),
        (86400, "ai_call", {"goal":
            "This lead engaged once, then went quiet for two days despite a follow-up text. This is a "
            "brief, low-pressure check-in call — ask if they're still interested in exploring coverage "
            "and help them from there if so; if not, thank them for their time, no pressure."}),
    ])

    # 4. Appointment Scheduled — Confirm & Recover
    # Auto-fires the moment a lead is booked. Deliberately does NOT set
    # persist_across_stages: if the lead progresses past this stage (they
    # showed up, quoted/closed) before the recovery steps fire,
    # on_stage_change cancels this enrollment's pending steps automatically
    # — that cancellation IS the "did they actually show up" check, reusing
    # existing infra instead of a new stage-polling branch type. The 72h
    # wait below is a fixed approximation (the engine's wait node is a fixed
    # duration from enrollment, not "N hours after their specific
    # appointment time") — good enough for typical short-notice bookings,
    # not exact for an appointment booked far in the future.
    wf = _upsert_template(
        cur, "appointment_recovery", "Appointment Scheduled — Confirm & Recover",
        "Confirms the booking immediately, then — only if the lead hasn't progressed past this stage "
        "by then (cancelled automatically otherwise) — a warm no-blame recovery text and a check-in "
        "call, for a booking that was likely missed.",
        trigger_stage="appointment_scheduled", trigger_type="stage_enter",
    )
    _linear_graph(cur, wf, [
        (0,    "notify_staff", {"message": "Appointment booked — a lead just scheduled a call/meeting with a licensed agent. Review and prepare."}),
        (0,    "send_sms", {"channel": "sms", "goal":
            "An appointment was just booked/confirmed. Send a short, warm confirmation — thank them, "
            "say you're looking forward to it, and invite them to reply here if anything comes up or "
            "they need to change the time."}),
        (259200, "send_sms", {"channel": "sms", "goal":
            "It's been a few days since their scheduled appointment and there's been no further "
            "progress — send a warm, no-blame message (they may have simply missed it) offering to "
            "help find a new time or answer any questions."}),  # +72h
        (3600, "ai_call",  {"goal":
            "Their appointment window passed with no progress since. This is a check-in call, not a "
            "scripted pitch — ask if they still want to move forward and help get something "
            "rescheduled if so."}),                                          # +1h after that
    ])

    # 5. Cold Lead Re-engagement
    wf = _upsert_template(
        cur, "cold_lead_reengagement", "Cold Lead Re-engagement",
        "Reactivation SMS, AI outreach call, offer campaign, requalification call. Enroll manually against dead/cold leads.",
        trigger_stage=None, trigger_type="manual",
    )
    _linear_graph(cur, wf, [
        (0,      "send_sms", {"channel": "sms", "goal":
            "Re-engage a cold/past lead. Reference that it's been a while, mention something may have "
            "changed (rates, needs, life events), and ask if it's worth revisiting."}),
        (86400,  "ai_call",  {}),                                             # +1 day
        (172800, "send_sms", {"channel": "sms", "goal":
            "Offer a specific, low-commitment incentive to re-engage — e.g. a free quick coverage "
            "review — to give them a concrete reason to respond now."}),  # +2 days
        (259200, "ai_call",  {}),                                             # +3 days — requalification
    ])

    # 6. Quote Follow-Up
    wf = _upsert_template(
        cur, "quote_follow_up", "Quote Follow-Up",
        "Quote sent notification, 24-hour follow-up, AI objection-handling call, notify staff to close.",
        trigger_stage="quoted", trigger_type="stage_enter",
    )
    _linear_graph(cur, wf, [
        (0,     "send_sms",     {"channel": "sms", "goal":
            "A quote was just sent/discussed. Confirm it's on its way (or reference what was just "
            "discussed), and invite any questions — don't restate the exact numbers yourself, that's "
            "already been communicated."}),
        (86400, "send_sms",     {"channel": "sms", "goal":
            "It's been 24 hours since the quote. Follow up warmly, ask if they had a chance to look it "
            "over, and invite questions or concerns — create gentle urgency without being pushy."}),
        (3600,  "ai_call",      {}),                                          # +1h after previous
        (86400, "notify_staff", {"message": "Lead completed the Quote Follow-Up sequence — review for closing."}),
    ])

    # 7. Long-Term Nurture (Day 1 / 3 / 7 / 14 / 30)
    wf = _upsert_template(
        cur, "long_term_nurture", "Long-Term Nurture",
        "Day 1, 3, 7, 14, and 30 touches for leads on a long sales cycle.",
        trigger_stage=None, trigger_type="manual",
    )
    _linear_graph(cur, wf, [
        (0,       "send_sms", {"channel": "sms", "goal":
            "Day 1 of a long-cycle nurture touch. Warm, brief check-in — no pressure, just staying on "
            "their radar for when they're ready to explore coverage."}),
        (172800,  "send_sms", {"channel": "sms", "goal":
            "Day 3 touch. Share one small piece of useful, non-salesy insurance info or a common "
            "question they might be wondering about, and ask if they have questions."}),   # +2d = day 3
        (345600,  "send_sms", {"channel": "sms", "goal":
            "Day 7 touch. Check in casually — mention you're still around whenever the timing's right, "
            "keep it short and low-key."}),   # +4d = day 7
        (604800,  "send_sms", {"channel": "sms", "goal":
            "Day 14 touch. A slightly more direct nudge — ask if their situation or needs have changed "
            "recently, since that's often when people revisit coverage."}),  # +7d = day 14
        (1382400, "send_sms", {"channel": "sms", "goal":
            "Day 30 re-engagement. Final scheduled touch in this cadence — offer a fresh reason to "
            "reconnect (e.g. a quick, no-obligation review), and let them know you're easy to reach "
            "whenever they want to pick this back up."}),  # +16d = day 30
    ])

    # 8. AI Sales Agent Workflow (the one template with real branching)
    wf = _upsert_template(
        cur, "ai_sales_agent_workflow", "AI Sales Agent Workflow",
        "Instant contact, AI qualification call, then branches: qualified leads are moved to Connected "
        "and staff is notified; unqualified leads end the sequence.",
        trigger_stage="new_lead", trigger_type="stage_enter",
    )
    prev_key = "trigger"
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'trigger', 'trigger', '{}')",
                (f"wn_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'sms1', 'send_sms', %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", wf, json.dumps({"channel": "sms", "goal":
                    "Instant first contact. Warm, brief intro — say who you are and ask what type of "
                    "coverage they're interested in."})))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, 'trigger', 'sms1')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'wait1', 'wait', %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", wf, json.dumps({"amount": 300, "unit": "seconds"})))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, 'sms1', 'wait1')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'call1', 'ai_call', '{}')",
                (f"wn_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, 'wait1', 'call1')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'branch1', 'branch_condition', %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", wf, json.dumps({
                    "mode": "last_result", "field": "outcome", "equals": "confirmed",
                    "true_branch": "qualified", "false_branch": "unqualified",
                })))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, 'call1', 'branch1')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'move1', 'move_stage', %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", wf, json.dumps({"event": "ai_qualified"})))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key, branch_label) VALUES (%s, %s, 'branch1', 'move1', 'qualified')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'notify1', 'notify_staff', %s)",
                (f"wn_{uuid.uuid4().hex[:12]}", wf, json.dumps({"message": "AI-qualified lead ready for follow-up."})))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, 'move1', 'notify1')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, 'end', 'end', '{}')",
                (f"wn_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key) VALUES (%s, %s, 'notify1', 'end')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))
    cur.execute("INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key, branch_label) VALUES (%s, %s, 'branch1', 'end', 'unqualified')",
                (f"we_{uuid.uuid4().hex[:12]}", wf))

    # 9. Closed — Thank You & Referral
    # The deal is won — this is not a sales cadence anymore. A brief
    # thank-you, then one soft referral ask a month later. Never re-asks
    # what coverage they're looking for or anything qualification-shaped.
    wf = _upsert_template(
        cur, "closed_thank_you", "Closed — Thank You & Referral",
        "A short thank-you once the deal closes, then a single low-pressure check-in and referral "
        "ask a month later. No sales pitch, no qualification questions.",
        trigger_stage="closed", trigger_type="stage_enter",
    )
    _linear_graph(cur, wf, [
        (0, "send_sms", {"channel": "sms", "goal":
            "This deal just closed — the lead is now a customer. Send a short, warm thank-you: "
            "confirm they're all set, and invite them to reach out anytime with questions. Do not "
            "ask about coverage needs or anything qualification-shaped — they've already bought."}),
        (2592000, "send_sms", {"channel": "sms", "goal":
            "It's been about a month since this customer's policy closed. Send a brief, friendly "
            "check-in on how things are going, and — only if it fits naturally — mention that "
            "referrals are always appreciated if they know anyone who could use help with coverage. "
            "Low-pressure, no ask if it doesn't fit."}),  # +30 days
    ])

    # 10. Call-First 5-Day Follow-Up — up to 3 call attempts, each followed
    # by a distinct iMessage only if the call goes unanswered (no_answer/
    # voicemail/failed), spaced ~3-4h apart. A reply to any of the 3 texts
    # ends the automated cadence — the live conversation takes over from
    # there, same handoff philosophy as Insurance Lead Nurture above.
    wf = _upsert_template(
        cur, "call_first_5day_followup", "Call-First 5-Day Follow-Up",
        "Call, then (only if unanswered) a text after 3 minutes offering a callback or chat. Up to 3 "
        "call+text rounds ~3.5h apart. Any reply ends the cadence and hands off to the live conversation.",
        trigger_stage="new_lead", trigger_type="stage_enter",
        trigger_config={"persist_across_stages": True},
    )

    def node(key, node_type, config):
        cur.execute(
            "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config) VALUES (%s, %s, %s, %s, %s)",
            (f"wn_{uuid.uuid4().hex[:12]}", wf, key, node_type, json.dumps(config)),
        )

    def edge(from_key, to_key, branch_label=None):
        cur.execute(
            "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key, branch_label) VALUES (%s, %s, %s, %s, %s)",
            (f"we_{uuid.uuid4().hex[:12]}", wf, from_key, to_key, branch_label),
        )

    # "call_failed" (not just "failed") is what actually gets reported when
    # Vapi rejects the call outright before it ever starts (e.g. the daily
    # outbound limit on a Vapi-bought number) — confirmed live: missing this
    # value here silently misrouted every rate-limited call attempt down the
    # "answered" branch, skipping the follow-up text entirely for 54 of 59
    # leads in one real run.
    NOT_ANSWERED = ["no_answer", "voicemail", "failed", "call_failed"]

    def call_round(round_num: int, call_goal: str, sms_text: str, next_call_key: str | None):
        """call{N} -> branch{N} -[answered]-> end; -[no_answer]-> wait{N} -> sms{N} -> check{N} -[replied]-> end; -[no_reply]-> next_call_key or end"""
        call_key, branch_key, wait_key, sms_key, check_key = (
            f"call{round_num}", f"branch{round_num}", f"wait{round_num}", f"sms{round_num}", f"check{round_num}"
        )
        node(call_key, "ai_call", {"goal": call_goal})
        node(branch_key, "branch_condition", {"mode": "last_result", "field": "outcome",
                                               "not_in": NOT_ANSWERED,
                                               "true_branch": "answered", "false_branch": "no_answer"})
        edge(call_key, branch_key)
        node(f"end_answered{round_num}", "end", {})
        edge(branch_key, f"end_answered{round_num}", "answered")

        node(wait_key, "wait", {"amount": 180, "unit": "seconds"})  # 3 minutes
        edge(branch_key, wait_key, "no_answer")
        node(sms_key, "send_sms", {"channel": "sms", "static_text": sms_text})
        edge(wait_key, sms_key)
        node(check_key, "branch_condition", {"mode": "reply_check", "timeout_hours": 3.5,
                                              "true_branch": "replied", "false_branch": "no_reply"})
        edge(sms_key, check_key)
        node(f"end_engaged{round_num}", "end", {})
        edge(check_key, f"end_engaged{round_num}", "replied")

        if next_call_key:
            edge(check_key, next_call_key, "no_reply")
        else:
            node(f"end_final{round_num}", "end", {})
            edge(check_key, f"end_final{round_num}", "no_reply")

    node("trigger", "trigger", {})
    edge("trigger", "call1")

    call_round(
        1,
        "This is the very first outreach call to a brand-new lead. Collect their basic information, "
        "ask relevant qualifying questions, build rapport, keep the conversation engaging, and guide "
        "them toward booking an appointment with a licensed agent.",
        "Hi, we tried calling you but unfortunately couldn't reach you. Would you like us to call you "
        "again, or would you prefer to continue the conversation by chat?",
        next_call_key="call2",
    )
    call_round(
        2,
        "This is a second follow-up call — the lead didn't answer the first call and didn't reply to "
        "the first follow-up text either. Acknowledge you're following up again, stay warm and "
        "low-pressure, and guide them toward booking an appointment with a licensed agent if they're "
        "interested.",
        "Hi, we're following up to see if you're still interested in speaking with a licensed agent. "
        "We'd be happy to call you again or continue by text—whichever is more convenient for you.",
        next_call_key="call3",
    )
    call_round(
        3,
        "This is a third and final follow-up call — the lead hasn't answered or replied to two prior "
        "attempts. Let them know this is a final follow-up, stay warm and non-pushy, and guide them "
        "toward booking an appointment with a licensed agent if they're still interested.",
        "Hi, we've tried reaching you a few times and wanted to make one final follow-up. If you're "
        "still interested, reply here and we can continue by message or arrange a convenient time for "
        "a call with a licensed agent.",
        next_call_key=None,
    )

    conn.commit()
    cur.close()
    conn.close()
    print("Done — 10 templates seeded.")


if __name__ == "__main__":
    seed()
