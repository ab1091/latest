"""
Background scheduler — fires pending scheduled_callbacks via Vapi outbound call.
Runs every 30 seconds, picks up any callbacks whose scheduled_at <= NOW().
"""
import json
import logging
import uuid
from datetime import datetime, timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import VAPI_API_KEY, VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID
from core.db import get_conn, get_dict_cursor

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _fire_sms_callback(cb: dict, conn, cur, lead: dict, node_goal: str | None = None, static_text: str | None = None) -> str:
    """
    Send a follow-up SMS/WhatsApp for an SMS-type callback.
    Returns "sent", "deferred" (quiet hours / opted-out, will retry later),
    or "failed" — callers must branch on this rather than re-reading
    scheduled_callbacks.status, since a deferred retry is left 'pending'
    and must NOT be treated as a terminal outcome by the workflow engine.

    node_goal: the firing workflow node's `config.goal` instruction (e.g.
    "Day 2: they haven't replied yet, send a gentle nudge..."), when this
    callback was scheduled by the workflow engine. When set, the generated
    text is built around that specific goal instead of the generic
    first-contact/follow-up fallback below — see _fire_workflow_action.

    static_text: the firing node's `config.static_text`, when set. Sends
    this exact text verbatim — no LLM call at all — for messages that must
    be word-for-word consistent (e.g. carrier opt-out/compliance copy).
    Takes priority over node_goal.
    """
    channel = cb.get("sms_channel") or "sms"
    phone   = cb["phone"]
    name    = lead.get("first_name") or "there"

    # TCPA — this is a business-initiated, scheduled outbound send (not a
    # real-time reply), so it must respect quiet hours the same as the
    # /send and /send-bulk endpoints in api/sms/router.py.
    from api.sms.router import _is_within_quiet_hours, _is_opted_out
    allowed, reason = _is_within_quiet_hours(lead["business_id"])
    if not allowed:
        cur.execute(
            "UPDATE scheduled_callbacks SET status='pending', scheduled_at=NOW() + INTERVAL '1 hour', updated_at=NOW() WHERE id=%s",
            (cb["id"],),
        )
        conn.commit()
        logger.info(f"[callback:sms] deferred 1h — {reason} (callback_id={cb['id']})")
        return "deferred"

    if await _is_opted_out(phone):
        cur.execute("UPDATE scheduled_callbacks SET status='failed', updated_at=NOW() WHERE id=%s", (cb["id"],))
        conn.commit()
        logger.info(f"[callback:sms] skipped — {phone} has opted out (callback_id={cb['id']})")
        return "failed"

    # This is a proactive/scheduled send with no idea what's happening on the
    # phone number right now — if the lead is actively mid-conversation (sent
    # something in the last 15 min), firing it anyway lands as a jarring,
    # context-free interruption ("hope you're doing well, good time to catch
    # up on that quote?" landing mid-sentence while they're answering a live
    # question). Defer it the same way a quiet-hours block does, rather than
    # firing blind. Scoped by PHONE, not lead_id/conversation_id — a
    # duplicate lead record for the same number would otherwise still miss
    # an active conversation happening under the other record.
    cur.execute("""
        SELECT 1 FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        JOIN leads l ON l.id = c.lead_id
        WHERE l.phone = %s AND c.business_id = %s AND m.role = 'user'
          AND m.created_at > NOW() - INTERVAL '15 minutes'
        LIMIT 1
    """, (phone, lead["business_id"]))
    if cur.fetchone():
        cur.execute(
            "UPDATE scheduled_callbacks SET status='pending', scheduled_at=NOW() + INTERVAL '30 minutes', updated_at=NOW() WHERE id=%s",
            (cb["id"],),
        )
        conn.commit()
        logger.info(f"[callback:sms] deferred 30min — lead is mid-conversation right now (callback_id={cb['id']})")
        return "deferred"

    # Build a short follow-up message using the agent's SMS prompt — matched
    # by this lead's actual tags/stage via lead_configs, same resolver the
    # live conversation uses. This used to be a stage-blind "LIMIT 1" query
    # that always returned whichever ai_agents row sorted first, regardless
    # of whether the lead was new/quoted/closed — silently using the wrong
    # persona (e.g. the new-lead intro agent) for stage-specific workflow
    # steps like a Closed-stage thank-you message.
    try:
        from api.sms.router import _get_agent_prompt
        agent = _get_agent_prompt(lead["business_id"], lead.get("tags") or [], lead.get("stage"))
        if agent:
            system_prompt = agent["prompt"]
            agent_name    = agent.get("name") or "Michael"
        else:
            cur.execute(
                "SELECT sms_prompt, call_prompt, name FROM ai_agents WHERE business_id = %s LIMIT 1",
                (lead["business_id"],)
            )
            agent_row = cur.fetchone()
            system_prompt = (agent_row.get("sms_prompt") or agent_row.get("call_prompt") or "") if agent_row else ""
            agent_name    = agent_row.get("name") or "Michael" if agent_row else "Michael"
    except Exception:
        system_prompt = ""
        agent_name    = "Michael"

    # Always fetch-or-create the conversation (same helper the real inbound/
    # outbound SMS path uses) so this message never gets silently dropped —
    # previously, a callback with no prior conversation (e.g. a brand-new
    # lead's very first workflow-triggered SMS) found no conv_row and skipped
    # saving entirely, even though the text was actually sent via Claw Messenger.
    from api.sms.router import _get_or_create_sms_conv, _save_message
    conv_id = _get_or_create_sms_conv(lead["id"], lead["business_id"], channel)
    history = []
    try:
        cur.execute("""
            SELECT role, content FROM messages
            WHERE conversation_id = %s ORDER BY created_at ASC LIMIT 20
        """, (conv_id,))
        history = [dict(m) for m in cur.fetchall()]
    except Exception as e:
        logger.warning(f"[callback:sms] could not fetch history: {e}")

    # No prior messages in THIS conversation record means this LOOKS like a
    # lead's genuine first contact — but a duplicate/re-enrolled lead record
    # for the same phone number would have its own empty conversation while
    # the real person has already been talking to this business for a while
    # under a different lead_id (exactly what re-sent the "Hi, I'm Riley..."
    # intro to an already-engaged lead in practice). Cross-check by PHONE
    # across the whole business, not just this conv_id — and if real history
    # exists elsewhere, pull IT in as the actual context instead of just
    # flipping a flag, otherwise the model still has nothing to continue
    # from and may reintroduce itself anyway despite being told not to.
    is_first_contact = len(history) == 0
    if is_first_contact:
        cur.execute("""
            SELECT m.role, m.content FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            JOIN leads l ON l.id = c.lead_id
            WHERE l.phone = %s AND c.business_id = %s
            ORDER BY m.created_at ASC LIMIT 20
        """, (phone, lead["business_id"]))
        other_history = [dict(m) for m in cur.fetchall()]
        if other_history:
            is_first_contact = False
            history = other_history
            logger.info(f"[callback:sms] phone={phone} has {len(other_history)} prior message(s) under another lead/conversation record — using that as context instead of treating this as first contact (callback_id={cb['id']})")

    if static_text:
        # Verbatim, no LLM involved — for messages that must be word-for-word
        # consistent (e.g. carrier opt-out/compliance copy). {name} and
        # {agent_name} are the only supported tokens (agent_name is the same
        # value used everywhere else — the VAPI/ai_agents name, e.g. "Riley");
        # falls back to the raw text if it isn't valid for .format (e.g.
        # contains other literal braces).
        try:
            message = static_text.format(name=name, agent_name=agent_name)
        except Exception:
            message = static_text
    else:
        # Generate the text via OpenAI
        try:
            from core.llm_openai import openai_generate
            contents = []
            for m in history:
                contents.append({
                    "role": "model" if m["role"] in ("agent", "assistant") else "user",
                    "parts": [{"text": m["content"]}],
                })
            # Ground truth for any goal that references an appointment (e.g.
            # the Appointment Scheduled workflow's "an appointment was just
            # booked/confirmed" step) — without this, the model has only the
            # conversation TEXT to go on, and will happily repeat back an
            # earlier time that was actually declined/never booked if that's
            # what the transcript shows. Confirmed live: a lead whose text
            # negotiation failed (every offered slot conflicted) but who
            # then booked a real, different time over a phone call got a
            # workflow SMS congratulating them on the failed text time,
            # because nothing here ever checked the real appointments row.
            real_appt_line = ""
            try:
                cur.execute("""
                    SELECT a.start_time, s.name AS service_name
                    FROM appointments a
                    LEFT JOIN services s ON s.id = a.service_id
                    WHERE a.lead_id = %s AND a.status IN ('confirmed', 'pending')
                    ORDER BY ABS(EXTRACT(EPOCH FROM (a.start_time - NOW()))) ASC
                    LIMIT 1
                """, (lead["id"],))
                appt_row = cur.fetchone()
                if appt_row:
                    real_appt_line = (
                        "REAL APPOINTMENT ON FILE (source of truth — if you reference an appointment "
                        "time/date, it MUST match this exactly; ignore any different time mentioned "
                        "earlier in the conversation text below, that may have been declined/never "
                        f"actually booked): {appt_row.get('service_name') or 'Appointment'} at "
                        f"{appt_row['start_time'].strftime('%A, %b %d at %I:%M %p')}.\n\n"
                    )
            except Exception as e:
                logger.warning(f"[callback:sms] could not fetch real appointment for lead={lead['id']}: {e}")

            if node_goal:
                # A step's own goal text can be written assuming it's the very
                # first message (e.g. "Day 1 — introduce yourself warmly") — but
                # if real history got pulled in above (this phone has talked to
                # this business before, just under a different lead/conversation
                # record), that assumption is now wrong. A soft "don't repeat a
                # greeting" aside wasn't enough to override an explicit "introduce
                # yourself" instruction in the goal in testing — the model followed
                # the goal literally. State the override forcefully, above the
                # goal, so it actually wins instead of competing with it.
                if is_first_contact:
                    # This really is the lead's very first message — the intro
                    # line and closing note below used to unconditionally say
                    # "continuing an ongoing conversation" / "don't reintroduce
                    # yourself", even here, directly contradicting a goal like
                    # sms_day1's "introduce yourself warmly" and reliably making
                    # the model skip the intro. Found live: a real Day-1 send
                    # came out as "Hey Bee! What type of coverage..." with no
                    # greeting or self-intro at all.
                    override = ""
                    intro = f"Write a short SMS to {name} — this is the very first message they will ever receive from you."
                    closing = "This is a genuine first contact, so follow the goal's intro/greeting instructions if it has any. Stay focused on the goal above. No emoji. Under 160 characters. No quotes."
                else:
                    override = (
                        "IMPORTANT CORRECTION: the step goal below was written assuming this is the lead's very "
                        "first message ever — the conversation history above proves that's wrong, this lead has "
                        "already talked to you before. IGNORE any part of the goal that says to introduce "
                        "yourself, state your name, or state your company name — skip straight to the substance "
                        "of the goal instead, as a natural continuation. The example below is illustrative ONLY — "
                        f"always address the lead by their real name, {name}, never by the name used in the example. "
                        "Wrong shape: 'Hi, I'm Riley with Shield Insurance Agency, what coverage are you looking "
                        f"for?' Right shape (using {name}'s actual name, not a placeholder): '{name}, wanted to "
                        "check back in — still looking to get that coverage sorted?'\n\n"
                    )
                    intro = f"Write a short SMS to {name}, continuing an ongoing insurance sales conversation."
                    closing = "Use the conversation history above for tone/continuity — do not reintroduce yourself or repeat a greeting. Stay focused on the goal above only. No emoji. Under 160 characters. No quotes."
                contents.append({
                    "role": "user",
                    "parts": [{"text": (
                        f"{intro}\n\n"
                        f"{real_appt_line}"
                        f"{override}"
                        f"THIS STEP'S GOAL: {node_goal}\n\n"
                        f"{closing}"
                    )}],
                })
            elif is_first_contact:
                contents.append({
                    "role": "user",
                    "parts": [{"text": (
                        f"Write a short, warm opening SMS introducing yourself to a new lead named {name}. "
                        "Greet them, say who you are and who you're with, and ask one friendly open "
                        "question to get the conversation going (e.g. what kind of coverage they're "
                        "looking for). No emoji. Under 160 characters. No quotes."
                    )}],
                })
            else:
                contents.append({
                    "role": "user",
                    "parts": [{"text": (
                        f"{name} asked earlier to be messaged later because they were busy — this callback is "
                        "that follow-up, firing now. But check the conversation history above first: has "
                        f"{name} already sent more messages since then and kept the conversation going (e.g. "
                        "answered a question, given a detail, asked something new)? If so, the 'busy, message "
                        "me later' moment has clearly passed — do NOT ask a generic 'is now a good time' "
                        "question, that would ignore what they just said. Instead, respond naturally to their "
                        "MOST RECENT message like a normal continuation of the conversation. "
                        "Only if the history shows they genuinely went quiet with no further replies since "
                        "asking to be messaged later, write a short, warm check-in: greet them by name, "
                        "mention you're following up as promised, and ask if now's a good time — without "
                        "diving into insurance questions yet. "
                        "No emoji. Under 160 characters. No quotes."
                    )}],
                })
            text = await openai_generate(contents, system_instruction=system_prompt, max_tokens=150)
            message = text.strip('"').strip("'")
        except Exception as e:
            logger.warning(f"[callback:sms] OpenAI failed, using fallback: {e}")
            message = (
                f"Hi {name}, good day! This is {agent_name} with Shield Insurance Agency, what kind of coverage are you looking for?"
                if is_first_contact else
                f"Hey {name}, just following up! Is now a good time to chat about your insurance options?"
            )


    # Send via the shared, compliance-aware sender (opted-out re-check is
    # redundant with the check above but harmless — keeps this in sync with
    # every other send path if that function's rules ever change).
    from api.sms.router import _send_sms
    try:
        await _send_sms(phone, message, channel)
        cur.execute("UPDATE scheduled_callbacks SET status='completed', updated_at=NOW() WHERE id=%s", (cb["id"],))
        kind = "static" if static_text else ("goal-driven" if node_goal else ("opening" if is_first_contact else "generic follow-up"))
        logger.info(f"[callback:sms] {kind} sent → phone={phone} channel={channel} callback_id={cb['id']}")
        result = "sent"
        from core.activity_events import emit_activity_event
        await emit_activity_event(
            lead["business_id"], "sms_sent", f"{name}: automated SMS sent ({kind})",
            lead_id=lead["id"], metadata={"channel": channel, "callback_id": cb["id"]},
        )
    except Exception as e:
        # Bounded auto-retry: confirmed live (client testing phase) that Claw
        # Messenger can time out waiting for its own delivery ack even when the
        # underlying connection is healthy — a transient external hiccup,
        # different from the stuck-connection failure mode already fixed via
        # keepalives in claw_messenger.py. Retrying a couple of times, a bit
        # later, means a live/demo lead doesn't silently sit on a failed send
        # until a human happens to notice the fallback task below and manually
        # resends it. Return early here — skip the message-save/task-creation/
        # lifecycle-progression side effects below, since nothing has actually
        # been confirmed sent OR permanently failed yet.
        #
        # channel == "sms" is BlueBubbles now, not Claw Messenger (Claw
        # Messenger is fully retired — see api/sms/router.py::_send_sms) —
        # confirmed live via BlueBubbles' own server log that its failure
        # mode is NOT a safe-to-retry timeout: Messages.app genuinely
        # composed and attempted the real send on the original attempt AND
        # both retries (BlueBubbles logged "Message match found" / "New
        # Message from You" each time), each just separately racing a false
        # [500] on BlueBubbles' own internal send-confirmation step. Retrying
        # here doesn't retry a failed send — it very likely re-sends a
        # message that already went out, so a real lead got the same
        # automated text 2-3 times from one "failure." Only WhatsApp
        # (Twilio) keeps the retry; no equivalent evidence of this race
        # exists for that path.
        retry_count = cb.get("retry_count", 0) or 0
        if retry_count < 2 and channel != "sms":
            cur.execute("""
                UPDATE scheduled_callbacks
                SET status='pending', scheduled_at=NOW() + INTERVAL '90 seconds',
                    retry_count=%s, updated_at=NOW()
                WHERE id=%s
            """, (retry_count + 1, cb["id"]))
            conn.commit()
            logger.warning(f"[callback:sms] send failed, auto-retry {retry_count + 1}/2 in 90s: {e}")
            return "retry_scheduled"

        # A carrier-side failure (Claw Messenger outage, rate limit, unverified
        # number) must not also erase the fact that this was generated and
        # meant to be sent — the message still gets saved and the lead still
        # progresses below, same as a real send. Without this, a transient
        # provider failure would silently lose the message with zero record
        # anywhere, and the lead would sit stuck at sub_status='new' forever.
        cur.execute("UPDATE scheduled_callbacks SET status='failed', updated_at=NOW() WHERE id=%s", (cb["id"],))
        logger.error(f"[callback:sms] send failed after {retry_count} retries, giving up: {e}")
        result = "failed"

        # The lead still progresses below (comment above explains why), but
        # that means a genuine delivery failure was otherwise completely
        # invisible — the CRM shows "contacted" with a logged message
        # indistinguishable from a real send, and nothing ever surfaces that
        # this specific text never reached the lead's phone. Confirmed live:
        # a lead uploaded during a Claw Messenger outage got silently marked
        # contacted with zero trace anywhere staff would actually look.
        try:
            task_id = f"task_{uuid.uuid4().hex[:12]}"
            cur.execute("""
                INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
            """, (task_id, lead["id"], lead["business_id"],
                  f"SMS delivery failed for {name or phone}: message was generated but never sent. Verify and resend."))
        except Exception as task_err:
            logger.warning(f"[callback:sms] failed to create failure task: {task_err}")

        from core.activity_events import emit_activity_event
        await emit_activity_event(
            lead["business_id"], "sms_failed", f"{name}: automated SMS FAILED to send",
            lead_id=lead["id"], metadata={"channel": channel, "callback_id": cb["id"], "error": str(e)},
        )

    try:
        _save_message(
            conv_id, "agent", message,
            status="failed" if result == "failed" else "delivered",
            error_reason=str(e) if result == "failed" else None,
            channel=channel
        )
    except Exception:
        pass

    # Mirrors the manual /send endpoint — without this, a lead nurtured
    # purely through the workflow engine never leaves sub_status='new',
    # which means check_stale_leads()'s 24h sweep (WHERE sub_status =
    # 'contacted') can never catch them going dark, so they'd sit in the
    # "New Lead" pipeline column forever regardless of how many texts
    # were actually sent. Idempotent — a no-op once already 'contacted'.
    try:
        from core.lead_transitions import transition_via_crm_api
        await transition_via_crm_api(lead["id"], lead["business_id"], "welcome_sms_sent")
    except Exception as e:
        logger.warning(f"[callback:sms] welcome_sms_sent transition failed for lead={lead['id']}: {e}")

    conn.commit()
    return result


async def _fire_email_callback(cb: dict, conn, cur, lead: dict) -> str:
    """
    Send a workflow-triggered email. Returns "sent", "skipped" (no real
    email on file), or "failed".
    """
    from core.gmail import send_email

    email = lead.get("email") or ""
    if not email or email.endswith(("@sms.lead", "@vapi.call")):
        cur.execute("UPDATE scheduled_callbacks SET status='failed', updated_at=NOW() WHERE id=%s", (cb["id"],))
        conn.commit()
        logger.info(f"[callback:email] skipped — no real email on file for lead={lead['id']}")
        return "skipped"

    name = lead.get("first_name") or "there"

    cur.execute(
        """
        SELECT wn.config FROM workflow_nodes wn
        JOIN lead_workflow_enrollments lwe ON lwe.workflow_id = wn.workflow_id
        WHERE lwe.id = %s AND wn.node_key = %s
        """,
        (cb["workflow_enrollment_id"], cb["workflow_node_key"]),
    )
    node_row = cur.fetchone()
    subject = (node_row["config"].get("subject") if node_row and node_row.get("config") else "") or "A message from us"

    from api.sms.router import _get_agent_prompt
    agent = _get_agent_prompt(lead["business_id"], lead.get("tags") or [], lead.get("stage"))
    if agent:
        system_prompt = agent["prompt"]
        agent_name    = agent.get("name") or "the team"
    else:
        cur.execute("SELECT sms_prompt, call_prompt, name FROM ai_agents WHERE business_id = %s LIMIT 1", (lead["business_id"],))
        agent_row = cur.fetchone()
        system_prompt = (agent_row.get("sms_prompt") or agent_row.get("call_prompt") or "") if agent_row else ""
        agent_name = (agent_row.get("name") if agent_row else None) or "the team"

    try:
        from core.llm_openai import openai_generate
        body = await openai_generate(
            f"Write a short, warm follow-up email to {name}, signed off from {agent_name}. "
            f"Subject line is already set to: '{subject}'. Write only the email body, "
            "2-4 sentences, plain text, no markdown, no placeholder brackets.",
            system_instruction=system_prompt, max_tokens=200,
        )
    except Exception as e:
        logger.warning(f"[callback:email] OpenAI failed, using fallback: {e}")
        body = f"Hi {name},\n\nJust checking in — let us know if you have any questions.\n\n{agent_name}"

    sent = await send_email(email, subject, body)
    cur.execute(
        "UPDATE scheduled_callbacks SET status=%s, updated_at=NOW() WHERE id=%s",
        ("completed" if sent else "failed", cb["id"]),
    )
    conn.commit()
    logger.info(f"[callback:email] {'sent' if sent else 'failed'} → {email} callback_id={cb['id']}")
    return "sent" if sent else "failed"


async def _fire_workflow_action(cb: dict, conn, cur, lead: dict):
    """
    Handle a workflow-engine-driven scheduled_callbacks row (see
    crm-service/core/workflow_engine.py). Two cases resolve entirely here:
      - action_type is None: a branch_condition 'reply_check' — evaluate
        whether the lead has replied since this check was scheduled, don't
        send anything.
      - action_type == 'sms': send the follow-up text (reusing the same
        Twilio/OpenAI send path as the legacy sequencer's SMS callbacks).
    action_type == 'call' is NOT handled here — it falls through to the
    existing outbound-call logic below, unchanged; its outcome is only
    known later, reported back via the Vapi webhook (vapi/router.py).
    """
    from core.workflow_client import advance_workflow
    enrollment_id = cb["workflow_enrollment_id"]
    node_key = cb["workflow_node_key"]
    action_type = cb.get("action_type")

    if action_type is None:
        cur.execute(
            "SELECT created_at FROM workflow_node_runs WHERE enrollment_id=%s AND node_key=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (enrollment_id, node_key),
        )
        run = cur.fetchone()
        since = run["created_at"] if run else cb["scheduled_at"]
        cur.execute("""
            SELECT m.id FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.lead_id = %s AND c.channel IN ('sms', 'whatsapp') AND m.role = 'user' AND m.created_at > %s
            LIMIT 1
        """, (cb["lead_id"], since))
        result = {"replied": cur.fetchone() is not None}
        cur.execute("UPDATE scheduled_callbacks SET status='completed', updated_at=NOW() WHERE id=%s", (cb["id"],))
        conn.commit()
        await advance_workflow(enrollment_id, lead["business_id"], node_key, result)
        return

    if action_type == "sms":
        node_goal = None
        static_text = None
        try:
            cur.execute(
                """
                SELECT wn.config FROM workflow_nodes wn
                JOIN lead_workflow_enrollments lwe ON lwe.workflow_id = wn.workflow_id
                WHERE lwe.id = %s AND wn.node_key = %s
                """,
                (enrollment_id, node_key),
            )
            node_row = cur.fetchone()
            if node_row and node_row.get("config"):
                node_goal = node_row["config"].get("goal") or None
                static_text = node_row["config"].get("static_text") or None
        except Exception as e:
            logger.warning(f"[workflow_callback] could not fetch node config for goal: {e}")

        outcome = await _fire_sms_callback(cb, conn, cur, lead, node_goal=node_goal, static_text=static_text)
        if outcome == "deferred":
            # Quiet hours — callback row is back to 'pending' with a later
            # scheduled_at; the enrollment stays 'waiting' as-is and the
            # poller will retry it. Advancing now would be a false failure.
            return
        await advance_workflow(enrollment_id, lead["business_id"], node_key,
                                {"sent": outcome == "sent", "failed": outcome != "sent"})
        return

    if action_type == "email":
        outcome = await _fire_email_callback(cb, conn, cur, lead)
        await advance_workflow(enrollment_id, lead["business_id"], node_key,
                                {"sent": outcome == "sent", "failed": outcome != "sent"})
        return

    logger.warning(f"[workflow_callback] unexpected action_type={action_type} for callback {cb['id']} — leaving for the call path")


async def _fire_callback(cb: dict):
    """Trigger a Vapi outbound call (or SMS follow-up) for a scheduled callback."""
    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        logger.info(f"[callback] firing id={cb['id']} lead={cb['lead_id']} phone={cb['phone']} scheduled_at={cb['scheduled_at']} type={cb.get('callback_type','call')}")

        # Lock the row
        cur.execute(
            "UPDATE scheduled_callbacks SET status='processing', updated_at=NOW() WHERE id=%s AND status='pending'",
            (cb["id"],)
        )
        if cur.rowcount == 0:
            logger.warning(f"[callback] id={cb['id']} already picked up by another worker — skipping")
            return
        conn.commit()

        # Get lead info
        cur.execute(
            "SELECT id, business_id, first_name, last_name, email, phone, tags, notes, stage FROM leads WHERE id=%s",
            (cb["lead_id"],)
        )
        lead = cur.fetchone()
        if not lead:
            logger.error(f"[callback] lead NOT FOUND id={cb['lead_id']} — marking failed")
            cur.execute("UPDATE scheduled_callbacks SET status='failed', updated_at=NOW() WHERE id=%s", (cb["id"],))
            conn.commit()
            return
        logger.info(f"[callback] lead found → name={lead['first_name']} phone={lead.get('phone')}")

        # Lead has declined / gone dead since this callback was scheduled —
        # never place the call or send the text regardless of which code
        # path queued it (workflow, live-call tool, SMS "call me back",
        # legacy sequencer). on_stage_change() only cancels callbacks tied
        # to a workflow enrollment, so this is the one place ALL callback
        # types pass through before actually contacting the lead.
        if lead.get("stage") == "dead":
            logger.info(f"[callback] lead={lead['id']} is dead/declined — cancelling callback id={cb['id']} instead of firing")
            cur.execute("UPDATE scheduled_callbacks SET status='cancelled', updated_at=NOW() WHERE id=%s", (cb["id"],))
            conn.commit()
            return

        # 9am-6pm US Central only — for BOTH calls and texts. _fire_sms_callback
        # below already checked this for sms-type callbacks, but that was the
        # only place it was ever checked: the actual call-dialing logic past
        # this point had NO time-of-day gate at all, so a workflow call could
        # fire at 3am with nothing to stop it. This is the one chokepoint every
        # callback type (call, sms, workflow-dispatched) passes through before
        # anything happens, so checking here covers all of them at once.
        from api.sms.router import _is_within_quiet_hours
        allowed, reason = _is_within_quiet_hours(lead["business_id"])
        if not allowed:
            cur.execute(
                "UPDATE scheduled_callbacks SET status='pending', scheduled_at=NOW() + INTERVAL '1 hour', updated_at=NOW() WHERE id=%s",
                (cb["id"],),
            )
            conn.commit()
            logger.info(f"[callback] deferred 1h — {reason} (callback_id={cb['id']})")
            return

        # Second layer of the same protection as _book_appointment's
        # cancel-on-book (ai-service/api/sms/router.py): an ad-hoc "get this
        # lead on the phone" call (no workflow_enrollment_id — scheduled by
        # _check_call_confirmation) is redundant if the lead already has a
        # real future appointment booked by the time this actually fires —
        # confirmed live tonight, a lead who booked by text got called
        # anyway ~2 minutes later. That fix cancels the callback eagerly the
        # moment a booking lands; this is the backstop right at the one
        # chokepoint every call passes through, in case something schedules
        # an ad-hoc call through a path that fix doesn't cover. Workflow-
        # driven calls (workflow_enrollment_id set) are exempt on purpose —
        # e.g. the Appointment Scheduled recovery workflow's own call is
        # supposed to fire even though an appointment already exists.
        if cb.get("callback_type") == "call" and not cb.get("workflow_enrollment_id"):
            cur.execute(
                "SELECT id FROM appointments WHERE lead_id=%s AND status IN ('confirmed','pending') "
                "AND start_time > NOW() LIMIT 1",
                (lead["id"],),
            )
            if cur.fetchone():
                logger.info(f"[callback] lead={lead['id']} already has a future appointment — cancelling redundant ad-hoc call id={cb['id']}")
                cur.execute("UPDATE scheduled_callbacks SET status='cancelled', updated_at=NOW() WHERE id=%s", (cb["id"],))
                conn.commit()
                return

        # A non-workflow call (the legacy voicemail-retry chain is the main
        # source — up to 3 automatic retries, ~1 hour apart) has no built-in
        # awareness of anything that happened on the lead's other channel in
        # the meantime. Workflow calls get the 3-day silence gate below (or
        # their own reply_check branch); ad-hoc/legacy calls got neither —
        # confirmed live: a lead replied "Can we chat?" to a text, the
        # WORKFLOW correctly saw that instantly and completed, but the
        # legacy retry chain (already scheduled before her reply, no
        # workflow_enrollment_id) fired anyway ~40 minutes later, then again
        # the next morning, oblivious to the fact she'd already engaged.
        # Cancel rather than fire once she's replied to anything since this
        # callback was queued — calling someone who just asked to keep
        # talking by text is exactly the wrong move.
        if cb.get("callback_type") == "call" and not cb.get("workflow_enrollment_id"):
            cur.execute("""
                SELECT 1 FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.lead_id = %s AND m.role = 'user' AND m.created_at > %s
                LIMIT 1
            """, (lead["id"], cb["created_at"]))
            if cur.fetchone():
                logger.info(f"[callback] lead={lead['id']} replied since this callback was queued — cancelling ad-hoc/legacy retry call id={cb['id']}")
                cur.execute("UPDATE scheduled_callbacks SET status='cancelled', updated_at=NOW() WHERE id=%s", (cb["id"],))
                conn.commit()
                return

        # Quick Setup toggle — "Call if lead goes silent" off means skip
        # every workflow-driven silence/no-reply call (Insurance Lead
        # Nurture's check-in, Connected's re-engagement call, Quoted's and
        # Appointment Scheduled's recovery calls, and any future workflow's
        # equivalent) — the SMS cadence and the confirmed-interest call are
        # unaffected. Previously this only matched a call node literally
        # named "call_checkin", so the toggle silently covered just 1 of the
        # 4 such calls actually in use — found by checking the setting's
        # real effect against every active workflow's nodes rather than
        # trusting the label. Any workflow-driven call ('call'
        # callback_type + a workflow_enrollment_id) is this same class of
        # call by definition — nothing else fires a call through a workflow.
        if cb.get("workflow_enrollment_id") and cb.get("callback_type") == "call":
            cur.execute(
                "SELECT call_on_silence_enabled FROM business_automation_settings WHERE business_id = %s",
                (lead["business_id"],),
            )
            settings_row = cur.fetchone()
            if settings_row and not settings_row["call_on_silence_enabled"]:
                logger.info(f"[callback] call_on_silence disabled for business={lead['business_id']} — skipping check-in call, callback_id={cb['id']}")
                cur.execute("UPDATE scheduled_callbacks SET status='cancelled', updated_at=NOW() WHERE id=%s", (cb["id"],))
                conn.commit()
                from core.workflow_client import advance_workflow
                await advance_workflow(cb["workflow_enrollment_id"], lead["business_id"],
                                        cb["workflow_node_key"], {"skipped": True, "outcome": "call_on_silence_disabled"})
                return

        # Workflow-engine-driven callback (branch check or SMS action) — ai_call
        # falls through to the existing call-placing logic below unchanged.
        if cb.get("workflow_enrollment_id") and cb.get("action_type") != "call":
            await _fire_workflow_action(cb, conn, cur, lead)
            return

        # SMS-type callback (legacy sequencer): send follow-up text, not a voice call
        if cb.get("callback_type") == "sms":
            await _fire_sms_callback(cb, conn, cur, lead)
            return

        # Policy: a workflow-driven call (every ai_call step across every
        # template — fast-response, no-reply check-ins, re-engagement,
        # appointment recovery, cold-lead, quote follow-up) is a proactive
        # call the lead never explicitly asked for, so it may only fire once
        # they've genuinely gone silent for a real stretch — not on whatever
        # short timer the individual workflow step happens to be set to.
        # "Genuinely silent" = no inbound message for 3+ full days (or, if
        # they've never replied at all, 3+ days since they were first
        # contacted). This replaces the old narrow 15-minute "mid-conversation"
        # check with the same idea at the right timescale — 15 minutes only
        # ever caught someone messaging in the same instant the call would've
        # fired; it did nothing for a lead who, say, replied yesterday and
        # would still get an unwanted automated call today.
        # Deliberately does NOT apply to the dynamic confirmed-interest call
        # (_check_call_confirmation) — that one has no workflow_enrollment_id
        # and exists *because* the lead explicitly said yes to a call, so it's
        # exempt by construction and keeps firing on its own short (~2min) delay.
        # ALSO deliberately does NOT apply to "Call-First 5-Day Follow-Up"
        # (template_key call_first_5day_followup) — that workflow's entire
        # premise, by explicit design, is calling a brand-new lead
        # immediately rather than waiting for silence; it already has its
        # own built-in pacing (immediate, then ~3.5h, ~3.5h) via wait nodes,
        # so this gate would otherwise silently stall its Call 1 by days and
        # defeat the workflow's purpose. Confirmed live: every one of a
        # 59-lead batch got deferred ~24h on first fire because of this gate
        # before the exemption was added.
        is_call_first_workflow = False
        if cb.get("workflow_enrollment_id"):
            cur.execute("""
                SELECT w.template_key FROM lead_workflow_enrollments e
                JOIN workflows w ON w.id = e.workflow_id
                WHERE e.id = %s
            """, (cb["workflow_enrollment_id"],))
            wf_row = cur.fetchone()
            is_call_first_workflow = bool(wf_row and wf_row["template_key"] == "call_first_5day_followup")

        if cb.get("workflow_enrollment_id") and not is_call_first_workflow:
            cur.execute("""
                SELECT COALESCE(
                    (SELECT MAX(m.created_at) FROM messages m
                     JOIN conversations c ON c.id = m.conversation_id
                     WHERE c.lead_id = %s AND m.role = 'user'),
                    (SELECT created_at FROM leads WHERE id = %s)
                ) AS last_activity
            """, (lead["id"], lead["id"]))
            last_activity_row = cur.fetchone()
            last_activity = last_activity_row["last_activity"] if last_activity_row else None
            silence_gate = timedelta(days=3)
            if last_activity is None or (datetime.utcnow() - last_activity) < silence_gate:
                retry_at = (last_activity + silence_gate) if last_activity else (datetime.utcnow() + silence_gate)
                # Never schedule further out than a day-at-a-time re-check —
                # keeps this responsive if the lead goes silent again after
                # this retry point, without needing a precise callback per lead.
                retry_at = min(retry_at, datetime.utcnow() + timedelta(days=1))
                cur.execute(
                    "UPDATE scheduled_callbacks SET status='pending', scheduled_at=%s, updated_at=NOW() WHERE id=%s",
                    (retry_at, cb["id"]),
                )
                conn.commit()
                logger.info(f"[callback] deferred to {retry_at} — lead not yet silent 3+ days (last_activity={last_activity}), callback_id={cb['id']}")
                return

        call_number = lead.get("phone")
        lead_name   = lead.get("first_name") or "there"

        # Get agent prompt + extract bot first name from prompt. No matching
        # Lead Config rule means no agent has been assigned to this lead's
        # tags/stage yet — refuse to place the call rather than using a
        # generic/unbranded assistant.
        import re as _re
        from api.calls.router import _get_agent_config_for_lead
        matched = _get_agent_config_for_lead(lead["business_id"] or "bus_001", lead["tags"] or [], lead.get("stage"))
        if matched is None:
            logger.warning(f"[callback] no agent configured for lead={lead['id']} tags={lead['tags']} stage={lead.get('stage')} — refusing to place call, callback_id={cb['id']}")
            cur.execute("UPDATE scheduled_callbacks SET status='failed', updated_at=NOW() WHERE id=%s", (cb["id"],))
            conn.commit()
            if cb.get("workflow_enrollment_id") and cb.get("action_type") == "call":
                from core.workflow_client import advance_workflow
                await advance_workflow(cb["workflow_enrollment_id"], lead["business_id"],
                                        cb["workflow_node_key"], {"failed": True, "outcome": "no_agent_configured"})
            return
        base_prompt, agent_name, agent_voice = matched
        _nm = _re.search(r'You are ([A-Z][a-z]+)[,\.]', base_prompt or "")
        bot_name = _nm.group(1) if _nm else "Michael"

        # Fetch recent SMS/WhatsApp conversation history so the agent knows what was discussed
        history_text = ""
        # Separate from history_text being non-empty: Day-1/Day-2 no-reply SMS
        # are OUR OWN outbound messages, saved to the conversation even though
        # the lead never answered either one. history_text alone can't tell
        # "we texted, they replied" from "we texted twice into silence" —
        # only this flag can, and the opening line said on the call must
        # differ accordingly (never claim a conversation happened if it didn't).
        lead_has_replied = False
        try:
            # Quoted/closed leads have a condensed deal summary regenerated
            # the moment they cross into that stage (workflow_engine.
            # on_stage_change -> lead_summary.generate_and_save_summary) —
            # anchor the call on that instead of replaying the full raw
            # qualification history, same approach as the SMS side.
            if lead.get("stage") in ("quoted", "closed"):
                cur.execute("SELECT ai_summary FROM leads WHERE id = %s", (lead["id"],))
                summary_row = cur.fetchone()
                if summary_row and summary_row["ai_summary"]:
                    history_text = (
                        "\n\nDEAL SUMMARY SO FAR (everything qualified/discussed before this "
                        "point — insurance type, key details, quote given, objections raised. "
                        "Treat all of it as already known, never re-ask it, and pick up exactly "
                        "where it leaves off):\n" + summary_row["ai_summary"]
                    )
                    lead_has_replied = True  # quoted/closed is impossible without real back-and-forth
                    logger.info(f"[callback] injecting deal summary as context for lead={lead['id']}")

            if not history_text:
                # Scoped by PHONE, not lead_id — a duplicate/re-enrolled lead
                # record for the same number (exactly the bug found in the
                # SMS path, see _fire_sms_callback above) would otherwise
                # find zero conversations under ITS OWN lead_id and place
                # the call with no idea the number has real history under a
                # different lead record.
                cur.execute("""
                    SELECT c.id, c.channel
                    FROM conversations c
                    JOIN leads l ON l.id = c.lead_id
                    WHERE l.phone = %s AND c.business_id = %s AND c.channel IN ('sms', 'whatsapp')
                    ORDER BY c.updated_at DESC LIMIT 1
                """, (lead.get("phone"), lead["business_id"]))
                conv_row = cur.fetchone()
                if conv_row:
                    cur.execute("""
                        SELECT role, content FROM messages
                        WHERE conversation_id = %s
                        ORDER BY created_at ASC LIMIT 20
                    """, (conv_row["id"],))
                    msgs = cur.fetchall()
                    if msgs:
                        lead_has_replied = any(m["role"] not in ("agent", "assistant") for m in msgs)
                        channel_label = "WhatsApp" if conv_row["channel"] == "whatsapp" else "SMS"
                        logger.info(f"[callback] injecting {len(msgs)} {channel_label} messages as context conv={conv_row['id']} lead_has_replied={lead_has_replied}")
                        if lead_has_replied:
                            history_text = f"\n\nPREVIOUS {channel_label.upper()} CONVERSATION WITH THIS LEAD:\n"
                        else:
                            history_text = (
                                f"\n\nPRIOR {channel_label.upper()} MESSAGES SENT TO THIS LEAD (they have NOT "
                                "replied to any of these — this is not a conversation, just our own outreach):\n"
                            )
                        for m in msgs:
                            role_label = "Agent" if m["role"] in ("agent", "assistant") else "Lead"
                            history_text += f"{role_label}: {m['content']}\n"
                        if lead_has_replied:
                            history_text += (
                                "\nThis is what was discussed before the call. "
                                "Resume naturally — do NOT repeat questions already answered above."
                            )
                        else:
                            history_text += (
                                "\nThe lead never responded to any of the above — do NOT say 'continuing our "
                                "conversation' or imply they replied. Acknowledge you've reached out before "
                                "without a response, then start the conversation fresh."
                            )
                    else:
                        logger.info(f"[callback] conv found but no messages conv={conv_row['id']} — no history injected")
                else:
                    logger.info(f"[callback] no SMS/WhatsApp conversation found for lead={lead['id']} — no history injected")
        except Exception as hist_err:
            logger.warning(f"[callback] could not fetch conversation history: {hist_err}")

        # Workflow-triggered calls (ai_call nodes) carry their own purpose in
        # call_reason (a node's config.goal — see workflow_engine._schedule_action)
        # — e.g. a Day-2 no-reply check-in call vs an interested-lead
        # appointment-booking call. Framing those as "the lead requested a
        # callback" would be factually wrong (nobody asked to be called), so
        # only use that framing for genuine lead-initiated "call me back"
        # requests; workflow calls get their goal stated directly instead.
        if cb.get("workflow_enrollment_id"):
            call_context = (
                f"\n\nCALL GOAL: {cb.get('call_reason') or 'Follow up with this lead.'} "
                "Pick up naturally from any prior conversation shown above — do not re-ask "
                "anything already covered."
            )
        else:
            call_context = (
                f"\n\nCONTEXT: This lead requested a callback. "
                f"Reason: {cb.get('call_reason') or 'callback requested'}. "
                "Pick up exactly where the conversation left off. Do NOT ask if they are busy again."
            )

        from vapi.router import _booking_on_call_instruction, _BOOK_APPOINTMENT_TOOL
        full_prompt = (
            base_prompt
            + history_text
            + call_context
            + "\n\nIMPORTANT: You are now on a phone call. Keep responses concise and conversational."
            + _booking_on_call_instruction()
        )

        # The opening line must match what actually happened. Three distinct
        # cases — collapsing the last two into one ("any history -> 'continuing
        # our conversation'") was the bug: Day-1/Day-2 no-reply texts are OUR
        # OWN messages, saved to history even though the lead never answered
        # either one, so that phrasing falsely claimed a two-way conversation
        # to a lead who never replied.
        if lead_has_replied:
            topic = (lead.get("notes") or "").strip() or (lead["tags"][0] if lead.get("tags") else "your inquiry")
            first_message = (
                f"Hi {lead_name}! This is {bot_name}, following up on the text conversation we had "
                f"about {topic}. Is now a good time to continue?"
            )
        elif history_text:
            first_message = (
                f"Hi {lead_name}! This is {bot_name} with Shield Insurance Agency. We've been trying "
                "to reach you by text about insurance coverage but haven't heard back — is now a good "
                "time to chat?"
            )
        else:
            first_message = f"Hi {lead_name}! This is {bot_name}. Hope you're doing well — is now a good time to chat?"

        from core.config import TWIML_BASE_URL
        payload = {
            "phoneNumberId": VAPI_PHONE_NUMBER_ID,
            "customer":      {"number": call_number, "name": f"{lead['first_name']} {lead['last_name']}".strip()},
            "assistantId":   VAPI_ASSISTANT_ID,
            "assistantOverrides": {
                "name":              agent_name,
                "server":            {"url": f"{TWIML_BASE_URL}/api/vapi/webhook"},
                "firstMessage":      first_message,
                # The Vapi assistant itself may be a repurposed/shared dashboard
                # assistant with its own leftover endCallMessage/voicemailMessage
                # from a prior unrelated business — confirmed live: a real call
                # ended by reading "Thank you for scheduling with Wellness
                # Partners. Your appointment is confirmed..." verbatim to a lead
                # who had just declined, because those two fields weren't
                # overridden here. Empty endCallMessage lets the model's own
                # natural close (already instructed in the system prompt) be
                # the final line instead of an injected canned one.
                "endCallMessage":    "",
                # Empty voicemailMessage — per Vapi, this makes the call hang
                # up the instant voicemail is detected instead of speaking a
                # message first. Confirmed live: with a real spoken message
                # here, every voicemail hit cost 17-20 billed seconds (time to
                # play "please give us a call back...") instead of cutting
                # immediately — 18 calls in one night at that rate is real
                # wasted call-minute cost for zero value, since nobody hears a
                # voicemail from an AI agent and calls back anyway. That exact
                # spoken line was also what got misread as the LEAD asking for
                # a callback elsewhere (see vapi/router.py) — removing it here
                # kills that risk at the source too, not just downstream.
                "voicemailMessage":  "",
                # voicemailMessage alone does nothing without this — confirmed
                # live: a call that reached a full/automated mailbox greeting
                # never got flagged as voicemail (endedReason stayed
                # customer-ended-call) and the assistant tried to hold a real
                # conversation with the carrier's automated prompt for several
                # turns instead of leaving voicemailMessage and hanging up.
                "voicemailDetection": {
                    "provider": "vapi",
                    "backoffPlan": {"startAtSeconds": 2, "frequencySeconds": 2.5, "maxRetries": 5},
                    "beepMaxAwaitSeconds": 12,
                },
                "transcriber":       {"provider": "deepgram", "model": "nova-2", "language": "en"},
                "voice":             agent_voice or {"provider": "vapi", "voiceId": "Elliot"},
                "backgroundSound":   "off",
                # No startSpeakingPlan here before meant Vapi's bare default —
                # a plain silence timeout with no semantic understanding of
                # "still thinking" vs "done talking". Confirmed live: a lead
                # answering a coverage-amount question got cut off mid-pause
                # ("It's...") and told "sorry, I didn't catch that" before she
                # could finish. smartEndpointingPlan judges the actual content
                # of the pause instead of just its length; waitSeconds raised
                # from Vapi's default as a second layer of patience on top.
                "startSpeakingPlan": {
                    "waitSeconds": 0.8,
                    "smartEndpointingPlan": {"provider": "vapi"},
                },
                "recordingEnabled":  True,
                "endCallFunctionEnabled": True,
                "maxDurationSeconds": 1800,
                "endCallPhrases": [
                    "goodbye", "bye bye", "take care", "talk soon",
                    "have a great day", "see you then", "talk to you soon",
                ],
                "model": {
                    "provider":  "openai",
                    "model":     "gpt-4o-mini",
                    "messages":  [{"role": "system", "content": full_prompt}],
                    "maxTokens": 300,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "schedule_callback",
                                "description": "Schedule a callback call for this lead. Use ONLY when the lead says they are busy and asks to be called back in X minutes or X hours.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "minutes": {"type": "integer", "description": "Minutes from now to call back."},
                                        "hours":   {"type": "integer", "description": "Hours from now to call back."},
                                    },
                                },
                            },
                        },
                        _BOOK_APPOINTMENT_TOOL,
                    ],
                },
            },
        }

        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                "https://api.vapi.ai/call/phone",
                headers={"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )

        if res.is_success:
            vapi_call_id = res.json().get("id", "")
            cur.execute(
                "UPDATE scheduled_callbacks SET status='completed', vapi_call_id=%s, updated_at=NOW() WHERE id=%s",
                (vapi_call_id, cb["id"])
            )
            logger.info(f"[callback] Vapi call initiated → call_id={vapi_call_id} phone={call_number} agent={agent_name} callback_id={cb['id']}")
            conn.commit()
            from core.activity_events import emit_activity_event
            await emit_activity_event(
                lead["business_id"], "call_placed", f"{lead.get('first_name') or call_number}: automated call placed",
                lead_id=lead["id"], metadata={"callback_id": cb["id"], "vapi_call_id": vapi_call_id},
            )
        else:
            cur.execute(
                "UPDATE scheduled_callbacks SET status='failed', updated_at=NOW() WHERE id=%s",
                (cb["id"],)
            )
            logger.error(f"[callback] Vapi error {res.status_code} for callback_id={cb['id']}: {res.text[:200]}")
            conn.commit()
            # The call never actually reached Vapi, so no webhook will ever
            # arrive to advance this enrollment — without this it stays
            # 'waiting' at this node forever. Report it as a failed outcome
            # so the graph walk continues (or a branch_condition routes it
            # down the "no"/unqualified path) instead of stranding the lead.
            if cb.get("workflow_enrollment_id") and cb.get("action_type") == "call":
                from core.workflow_client import advance_workflow
                await advance_workflow(cb["workflow_enrollment_id"], lead["business_id"],
                                        cb["workflow_node_key"], {"failed": True, "outcome": "call_failed"})

    except Exception as e:
        conn.rollback()
        logger.error(f"[callback] EXCEPTION firing callback_id={cb['id']}: {e}")
        try:
            cur.execute("UPDATE scheduled_callbacks SET status='failed', updated_at=NOW() WHERE id=%s", (cb["id"],))
            conn.commit()
            if cb.get("workflow_enrollment_id") and cb.get("action_type") == "call":
                from core.workflow_client import advance_workflow
                await advance_workflow(cb["workflow_enrollment_id"], lead["business_id"],
                                        cb["workflow_node_key"], {"failed": True, "outcome": "call_failed"})

            # Same reasoning as the SMS failure task above (_fire_sms_callback):
            # a transient failure here (network blip, Vapi outage, DNS) leaves
            # zero trace anywhere staff would look — the lead just silently
            # never gets called. Confirmed live: a lead who'd explicitly
            # confirmed she wanted a call had it die mid-outage with nothing
            # surfaced anywhere.
            task_id = f"task_{uuid.uuid4().hex[:12]}"
            cur.execute("""
                INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
            """, (task_id, lead["id"], lead["business_id"],
                  f"Call failed for {lead.get('first_name') or lead.get('phone')} — was scheduled but never placed. Verify and call back."))
            conn.commit()
        except Exception:
            pass
    finally:
        cur.close()
        conn.close()


async def check_and_fire_callbacks():
    """Poll DB for due callbacks and fire them."""
    if not VAPI_API_KEY or not VAPI_PHONE_NUMBER_ID:
        return
    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        cur.execute("""
            SELECT id, lead_id, business_id, phone, scheduled_at, call_reason,
                   callback_type, sms_channel, workflow_enrollment_id, workflow_node_key, action_type,
                   retry_count, created_at
            FROM scheduled_callbacks
            WHERE status = 'pending' AND scheduled_at <= NOW()
            ORDER BY scheduled_at ASC
            LIMIT 10
        """)
        due = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    if due:
        logger.info(f"[callback:poll] {len(due)} callback(s) due — firing now")
    for cb in due:
        await _fire_callback(cb)


async def check_stale_leads():
    """
    Move leads to 'Old Lead' (sub_status 'stale') if they were contacted
    (welcome_sms_sent fired) but never replied within 24h. If they reply
    later, transition_lead_status's normal inbound_reply handling moves
    them to Connected same as any other lead — this is a one-way nudge
    into a visible "needs follow-up" bucket, not a dead end.
    """
    from core.lead_transitions import transition_via_crm_api
    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        cur.execute("""
            SELECT id, business_id FROM leads
            WHERE sub_status = 'contacted' AND updated_at <= NOW() - INTERVAL '24 hours'
            LIMIT 200
        """)
        stale = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    if stale:
        logger.info(f"[stale_leads] {len(stale)} lead(s) crossed 24h with no reply — moving to Old Lead")
    for row in stale:
        try:
            await transition_via_crm_api(row["id"], row["business_id"], "no_reply_24h")
        except Exception as e:
            logger.warning(f"[stale_leads] failed to transition lead={row['id']}: {e}")


async def check_orphaned_replies():
    """
    Safety net for an inbound message that was received and saved, but never
    got an AI reply — for ANY reason: an unhandled exception mid-processing,
    a worker crash, or (confirmed live) a dev-server hot-reload killing the
    in-flight request right after the message was saved but before the reply
    was generated/sent. None of the existing failure handling catches this
    class of bug, because it requires the *process itself* to die partway
    through — there's no try/except left running to catch anything.
    This doesn't attempt to auto-regenerate the reply: by the time this
    fires, earlier side effects in the original request (stage transitions,
    workflow advances) may have already run, and blindly replaying the whole
    inbound-message pipeline risks double-firing those. Staff visibility
    within ~2-4 minutes is the safe fix — a human confirms nothing else broke
    before manually resuming the conversation.
    """
    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        cur.execute("""
            SELECT DISTINCT ON (c.lead_id)
                   c.lead_id, c.channel, m.content, m.created_at, l.business_id, l.first_name, l.phone,
                   EXTRACT(EPOCH FROM (NOW() - m.created_at)) / 60 AS age_minutes
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            JOIN leads l ON l.id = c.lead_id
            WHERE m.role = 'user'
              -- Kept above _typing_delay_seconds()'s max (~110s in
              -- api/sms/router.py) with headroom — that intentional
              -- human-feel pause happens before the agent reply row is
              -- saved, so a threshold at or below it would treat a normal
              -- in-progress reply as a crash and auto-replay the message.
              AND m.created_at <= NOW() - INTERVAL '3 minutes'
              AND COALESCE(l.opted_out, false) = false
              AND COALESCE(l.stage, '') != 'dead'
              AND COALESCE(c.ai_active, true) = true
              AND NOT EXISTS (
                  SELECT 1 FROM messages m2
                  WHERE m2.conversation_id = m.conversation_id
                    AND m2.role = 'agent'
                    AND m2.created_at > m.created_at
              )
              AND NOT EXISTS (
                  SELECT 1 FROM tasks t
                  WHERE t.lead_id = c.lead_id AND t.status = 'open'
                    AND t.title LIKE 'Lead reply pending%'
              )
            ORDER BY c.lead_id, m.created_at DESC
            LIMIT 50
        """)
        orphaned = cur.fetchall()

        for row in orphaned:
            name = row.get("first_name") or row.get("phone") or "lead"
            age_minutes = float(row["age_minutes"])
            recovered = False

            # Auto-recovery attempt: replay the exact message through the real
            # production handler, same as manually confirmed safe live — the
            # only side effect that can have already run before a reply was
            # generated is the inbound_reply stage transition, which is
            # 409-tolerant/idempotent, so replaying is safe. Capped to a 10min
            # window and one attempt per cycle (the NOT EXISTS task guard
            # above stops repeat attempts once a task exists) — past that,
            # something more structural is likely wrong and this should
            # escalate to a human instead of silently retrying forever.
            if row["channel"] == "sms" and age_minutes <= 10:
                try:
                    from api.sms.router import _handle_inbound_message
                    await _handle_inbound_message(row["phone"], row["content"], "sms")
                    logger.info(f"[orphan_check] lead={row['lead_id']} auto-recovered via replay (message was {age_minutes:.1f}min old)")
                    recovered = True
                except Exception as e:
                    logger.warning(f"[orphan_check] auto-recovery replay failed for lead={row['lead_id']}: {e}")

            if not recovered:
                task_id = f"task_{uuid.uuid4().hex[:12]}"
                cur.execute("""
                    INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                    VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                """, (task_id, row["lead_id"], row["business_id"],
                      f"Lead reply pending — {name} sent \"{row['content'][:80]}\" over 2 minutes ago "
                      f"with no AI reply (auto-recovery {'skipped' if row['channel'] != 'sms' or age_minutes > 10 else 'failed'}). "
                      f"Verify and follow up manually."))
                logger.warning(f"[orphan_check] lead={row['lead_id']} message unanswered since {row['created_at']} — task {task_id} created")
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _parse_vapi_ts(ts: str):
    return datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z" if "." in ts else "%Y-%m-%dT%H:%M:%S%z")


async def check_orphaned_calls():
    """
    Safety net for a call Vapi completed but whose end-of-call-report webhook
    never reached us — confirmed live: a flaky free-tier ngrok tunnel dropped
    for under a minute right as a call ended, silently losing the one event
    that saves the transcript, links lead_id, and books/declines the
    appointment. Mid-call events (assistant.started, conversation-update,
    etc.) had come through fine; only the final report was lost, so the call
    left zero trace anywhere in the CRM even though it completed successfully
    on Vapi's side — lead stuck at its pre-call stage forever, no appointment,
    no record a call even happened.

    Discovers orphans from OUR OWN scheduled_callbacks table (every call this
    app placed and got a real vapi_call_id back for), NOT Vapi's global
    `GET /call?limit=50` recent-call list. That list-based approach was the
    original design here and had a real, confirmed failure mode: a burst of
    58+ calls in ~5 minutes during a bulk lead-import test pushed several
    still-orphaned calls out of the most-recent-50 window before this job's
    3-minute cycle ever got to look at them — permanently unrecoverable
    after that, since they could never re-enter a "most recent 50" window
    again. scheduled_callbacks has no such ceiling: it only ever contains
    calls WE placed, so it can't be crowded out by unrelated account
    activity or our own volume, however bursty.
    """
    if not VAPI_API_KEY:
        return

    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        # >=3min gives the normal webhook time to land before we treat it as
        # lost. No upper bound needed — unlike the old Vapi-list approach,
        # this table only ever holds calls we ourselves placed, so it can't
        # accumulate unbounded unrelated history to keep re-scanning.
        cur.execute("""
            SELECT sc.vapi_call_id, sc.lead_id, sc.phone
            FROM scheduled_callbacks sc
            WHERE sc.callback_type = 'call' AND sc.status = 'completed'
              AND sc.vapi_call_id IS NOT NULL
              AND sc.updated_at < NOW() - INTERVAL '3 minutes'
              AND NOT EXISTS (
                  SELECT 1 FROM voice_calls vc
                  WHERE vc.call_id = sc.vapi_call_id AND vc.status = 'ended'
              )
            ORDER BY sc.updated_at ASC
            LIMIT 20
        """)
        orphans = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    if not orphans:
        return

    async with httpx.AsyncClient(timeout=15) as client:
        for orphan in orphans:
            call_id = orphan["vapi_call_id"]
            try:
                res = await client.get(
                    f"https://api.vapi.ai/call/{call_id}",
                    headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
                )
                res.raise_for_status()
                call = res.json()
            except Exception as e:
                logger.warning(f"[orphan_call_check] Vapi fetch failed for {call_id}: {e}")
                continue

            if call.get("status") != "ended":
                continue  # still in progress or Vapi hasn't finalized it yet — try again next cycle

            ended_at = call.get("endedAt")
            started_at = call.get("startedAt")
            duration = 0
            if started_at and ended_at:
                try:
                    duration = int((_parse_vapi_ts(ended_at) - _parse_vapi_ts(started_at)).total_seconds())
                except Exception:
                    pass

            from_phone = (call.get("customer") or {}).get("number", "") or orphan["phone"]
            direction  = "inbound" if "inbound" in (call.get("type") or "").lower() else "outbound"

            try:
                from vapi.router import _extract_and_save
                await _extract_and_save(
                    call_id=call_id,
                    from_phone=from_phone,
                    transcript=call.get("transcript") or "",
                    duration_seconds=duration,
                    ended_reason=call.get("endedReason") or "",
                    vapi_summary=call.get("summary") or "",
                    recording_url=call.get("recordingUrl") or "",
                    direction=direction,
                    raw_payload=json.dumps(call),
                )
                logger.warning(f"[orphan_call_check] backfilled missing/incomplete call {call_id} for {from_phone} — webhook never landed")
            except Exception as e:
                logger.warning(f"[orphan_call_check] backfill failed for call {call_id}: {e}")


async def check_stuck_processing_callbacks():
    """
    Safety net: a scheduled_callbacks row locked to status='processing' (the
    claim step at the top of _fire_callback, right before actually dialing/
    texting) that never resolves to a terminal status means whatever was
    processing it died mid-flight — an ai-service restart, an unhandled
    crash before the terminal UPDATE. check_and_fire_callbacks only ever
    queries status='pending', so a row wedged in 'processing' is invisible
    to every future poll and stays stuck forever with nothing to indicate
    why. Reset anything stuck >5min back to pending so it gets retried.
    """
    conn = get_conn(); cur = get_dict_cursor(conn)
    try:
        cur.execute("""
            UPDATE scheduled_callbacks
            SET status = 'pending', updated_at = timezone('UTC', NOW())
            WHERE status = 'processing'
              AND updated_at < timezone('UTC', NOW()) - INTERVAL '5 minutes'
            RETURNING id, lead_id
        """)
        reset = cur.fetchall()
        conn.commit()
        for row in reset:
            logger.warning(f"[stuck_processing] reset callback {row['id']} (lead={row['lead_id']}) from stuck 'processing' back to 'pending'")
    finally:
        cur.close(); conn.close()


async def check_stuck_workflow_actions():
    """
    Safety net: a lead_workflow_enrollments row sitting at status='waiting'
    with NO live (pending/processing) scheduled_callbacks row tied to it is
    silently stuck — nothing will ever advance it again on its own.

    Confirmed live: 13 real, active leads ended up exactly here in one
    incident, from three UNRELATED root causes — a lost call-outcome
    webhook, an external bulk DB operation that cancelled pending sends
    without telling the workflow, and a process-restart-orphaned
    'processing' lock. Different causes, identical signature: 'waiting'
    with nothing pending. Rather than only patch the specific causes found
    this once, this catches the SHAPE of the problem generically, so
    whatever different cause strands a lead next time doesn't silently
    leave them uncalled/untexted forever again.

    Only re-fires for ai_call/send_sms node types — the two concretely
    understood, safe-to-replay cases. Anything else (branch_condition,
    wait, etc.) gets a staff task instead of a guessed auto-action; dead/
    opted-out leads are skipped entirely, since 'waiting' with nothing
    pending is the CORRECT end state for them.
    """
    import uuid as _uuid
    conn = get_conn(); cur = get_dict_cursor(conn)
    try:
        cur.execute("""
            SELECT e.id AS enrollment_id, e.lead_id, e.workflow_id, e.current_node_key, l.business_id,
                   l.phone, l.first_name, l.stage, l.opted_out
            FROM lead_workflow_enrollments e
            JOIN leads l ON l.id = e.lead_id
            WHERE e.status = 'waiting'
              AND e.updated_at < timezone('UTC', NOW()) - INTERVAL '10 minutes'
              AND NOT EXISTS (
                  SELECT 1 FROM scheduled_callbacks sc
                  WHERE sc.workflow_enrollment_id = e.id AND sc.status IN ('pending', 'processing')
              )
        """)
        stuck = cur.fetchall()

        for e in stuck:
            if e["stage"] == "dead" or e["opted_out"]:
                continue  # correctly inert — nothing should fire for these

            cur.execute(
                "SELECT node_type FROM workflow_nodes WHERE workflow_id = %s AND node_key = %s",
                (e["workflow_id"], e["current_node_key"]),
            )
            node = cur.fetchone()
            if not node:
                continue

            if node["node_type"] in ("ai_call", "send_sms") and e["phone"]:
                callback_type = "call" if node["node_type"] == "ai_call" else "sms"
                cb_id = f"cb_{_uuid.uuid4().hex[:12]}"
                cur.execute("""
                    INSERT INTO scheduled_callbacks
                        (id, lead_id, business_id, phone, scheduled_at, call_reason,
                         callback_type, workflow_enrollment_id, workflow_node_key, action_type,
                         created_at, updated_at)
                    VALUES (%s, %s, %s, %s, timezone('UTC', NOW()), %s, %s, %s, %s, %s,
                            timezone('UTC', NOW()), timezone('UTC', NOW()))
                """, (cb_id, e["lead_id"], e["business_id"], e["phone"],
                      "Auto-recovered: enrollment was stuck waiting with no live callback",
                      callback_type, e["enrollment_id"], e["current_node_key"], callback_type))
                conn.commit()
                logger.warning(f"[stuck_workflow] re-queued {node['node_type']} for lead={e['lead_id']} enrollment={e['enrollment_id']} node={e['current_node_key']} (was stuck with nothing pending)")
            else:
                task_id = f"task_{_uuid.uuid4().hex[:12]}"
                cur.execute("""
                    INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                    VALUES (%s, %s, %s, %s, 'open', timezone('UTC', NOW()), timezone('UTC', NOW()))
                """, (task_id, e["lead_id"], e["business_id"],
                      f"{e['first_name'] or e['phone'] or 'Lead'}'s workflow is stuck at "
                      f"'{e['current_node_key']}' ({node['node_type']}) with nothing scheduled — needs manual review."))
                conn.commit()
                logger.warning(f"[stuck_workflow] lead={e['lead_id']} stuck at non-auto-recoverable node {e['current_node_key']} ({node['node_type']}) — task created")
    finally:
        cur.close(); conn.close()


def start_scheduler():
    scheduler.add_job(check_and_fire_callbacks, "interval", seconds=30, id="callback_poller", replace_existing=True)
    scheduler.add_job(check_stale_leads, "interval", minutes=30, id="stale_lead_poller", replace_existing=True)
    scheduler.add_job(check_orphaned_replies, "interval", minutes=2, id="orphan_reply_poller", replace_existing=True)
    scheduler.add_job(check_orphaned_calls, "interval", minutes=3, id="orphan_call_poller", replace_existing=True)
    scheduler.add_job(check_stuck_processing_callbacks, "interval", minutes=5, id="stuck_processing_poller", replace_existing=True)
    scheduler.add_job(check_stuck_workflow_actions, "interval", minutes=5, id="stuck_workflow_poller", replace_existing=True)
    scheduler.start()
    logger.info("[callback_scheduler] Started — callback polling every 30s, stale-lead check every 30m, orphaned-reply check every 2m, orphaned-call check every 3m, stuck-processing check every 5m, stuck-workflow check every 5m")


def stop_scheduler():
    scheduler.shutdown(wait=False)
