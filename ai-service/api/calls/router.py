"""
Calls router — POST /api/calls/update, POST /api/calls/outbound
"""
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

import httpx

from core.db import get_conn, get_dict_cursor
from core.config import VAPI_API_KEY, VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID
from core.local_recordings import find_local_path, save_locally

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calls")


# ── GET /api/calls/{call_id}/recording ──────────────────────────────────────
# Served exclusively from local disk (core/local_recordings.py) — the browser
# is never hand a remote (Azure or otherwise) URL for this. Vapi is
# configured, in its own dashboard, to upload recordings into our Azure
# container; that's only ever fetched server-side, once, to populate the
# local cache. Calls from before the Azure migration (bare, unsigned R2 URLs
# on Vapi's own old bucket) have no reliable fetch path left and simply
# won't have a local copy.


@router.get("/{call_id}/recording")
async def get_call_recording(call_id: str, type: str = "mono"):
    # Local disk only — the browser is NEVER handed an Azure (or any other
    # remote) URL for this. If it's not on disk yet, this fetches it once,
    # server-side, and writes it to disk before responding; if that fetch
    # fails, the caller gets a plain error, never a redirect into Azure.
    if type != "mono":
        raise HTTPException(status_code=400, detail="Only the mono recording is available.")

    existing = find_local_path(call_id)
    if existing:
        return FileResponse(existing, media_type="audio/wav")

    conn = get_conn(); cur = get_dict_cursor(conn)
    try:
        cur.execute("""
            SELECT vc.recording_url, vc.caller_name, l.first_name, l.last_name
            FROM voice_calls vc
            LEFT JOIN leads l ON l.id = vc.lead_id
            WHERE vc.call_id = %s LIMIT 1
        """, (call_id,))
        row = cur.fetchone()
    finally:
        cur.close(); conn.close()

    if not row or not row["recording_url"]:
        raise HTTPException(status_code=404, detail="No recording available for this call.")

    lead_name = " ".join(filter(None, [row.get("first_name"), row.get("last_name")])).strip() or row.get("caller_name")
    await save_locally(call_id, row["recording_url"], lead_name=lead_name)
    fresh = find_local_path(call_id)
    if fresh:
        return FileResponse(fresh, media_type="audio/wav")

    raise HTTPException(status_code=503, detail="Recording exists but couldn't be fetched to local storage yet — try again in a moment.")


class CallUpdateIn(BaseModel):
    call_id:          str
    outcome:          Optional[str] = None   # confirmed | cancelled | reschedule_requested | no_answer | voicemail | failed | info
    transcript:       Optional[str] = None
    summary:          Optional[str] = None
    duration_seconds: Optional[int] = None
    appointment_id:   Optional[str] = None
    patient_name:     Optional[str] = None
    patient_phone:    Optional[str] = None
    raw_payload:      Optional[str] = None


@router.post("/update")
async def update_call(body: CallUpdateIn):
    conn = get_conn()
    cur  = get_dict_cursor(conn)
    voicemail_lead = None  # set below if outcome=voicemail and the lead resolves; used after commit
    try:
        # Check if voice_call row exists
        cur.execute("SELECT id FROM voice_calls WHERE call_id = %s", (body.call_id,))
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE voice_calls
                SET outcome          = COALESCE(%s, outcome),
                    transcript       = COALESCE(%s, transcript),
                    summary          = COALESCE(%s, summary),
                    duration_seconds = COALESCE(%s, duration_seconds),
                    status           = 'ended',
                    raw_payload      = COALESCE(%s, raw_payload),
                    updated_at       = NOW()
                WHERE call_id = %s
            """, (
                body.outcome, body.transcript, body.summary,
                body.duration_seconds, body.raw_payload, body.call_id,
            ))
        else:
            row_id = f"vc_{uuid.uuid4().hex[:12]}"
            cur.execute("""
                INSERT INTO voice_calls
                    (id, call_id, appointment_id, provider, status,
                     outcome, transcript, summary, duration_seconds, raw_payload)
                VALUES (%s, %s, %s, 'vapi', 'ended', %s, %s, %s, %s, %s)
            """, (
                row_id, body.call_id,
                body.appointment_id or "unknown",
                body.outcome, body.transcript, body.summary,
                body.duration_seconds, body.raw_payload,
            ))

        # Sync appointment status when outcome is actionable
        if body.outcome in ("confirmed", "cancelled", "reschedule_requested") and body.appointment_id:
            status_map = {
                "confirmed":            "confirmed",
                "cancelled":            "cancelled",
                "reschedule_requested": "reschedule_requested",
            }
            cur.execute("""
                UPDATE appointments
                SET status = %s, updated_at = NOW()
                WHERE id = %s
            """, (status_map[body.outcome], body.appointment_id))

        # Voicemail leaves staff with zero visibility otherwise — the lead is
        # still waiting on a call that will never come unless someone notices
        # and follows up manually. Same task-on-silent-failure pattern as the
        # SMS send-failure task in api/sms/router.py.
        #
        # Also fires on no_answer: confirmed live that Vapi's own outcome
        # classifier is inconsistent for the exact same real-world event (a
        # full voicemail box intercepting the call) — sometimes "voicemail",
        # sometimes "no_answer". Both mean the lead was not actually reached,
        # which is the only thing that actually matters here.
        if body.outcome in ("voicemail", "no_answer"):
            cur.execute("SELECT lead_id FROM voice_calls WHERE call_id = %s", (body.call_id,))
            vc_row = cur.fetchone()
            lead_id = vc_row["lead_id"] if vc_row else None
            if lead_id:
                # Skip entirely if a workflow (e.g. Call-First 5-Day Follow-Up)
                # currently owns this lead's follow-up cadence — same
                # duplicated-code bug as vapi/router.py's identical block: this
                # one had no gate at all and would double-text/double-task
                # any lead a workflow already has a missed-call step for.
                cur.execute(
                    "SELECT 1 FROM lead_workflow_enrollments WHERE lead_id = %s AND status IN ('active','waiting') LIMIT 1",
                    (lead_id,),
                )
                is_workflow_call = cur.fetchone() is not None
            else:
                is_workflow_call = False
            if lead_id and not is_workflow_call:
                cur.execute("SELECT business_id, first_name, phone FROM leads WHERE id = %s", (lead_id,))
                lead_row = cur.fetchone()
                if lead_row:
                    task_id = f"task_{uuid.uuid4().hex[:12]}"
                    cur.execute("""
                        INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                        VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                    """, (task_id, lead_id, lead_row["business_id"],
                          f"Call to {lead_row.get('first_name') or lead_row.get('phone')} hit voicemail — "
                          f"they haven't actually been reached yet. Follow up manually."))
                    voicemail_lead = {"id": lead_id, **lead_row}

        conn.commit()
        logger.info(f"[calls/update] call_id={body.call_id} outcome={body.outcome}")

        # Texting the lead too, not just notifying staff — they're sitting
        # there thinking a call is coming and it never will unless someone
        # tells them. Sent after commit so a Claw hiccup here can't roll back
        # the outcome/task writes above.
        if voicemail_lead and voicemail_lead.get("phone"):
            try:
                from api.sms.router import _send_sms, _save_message, _get_or_create_sms_conv
                msg = (
                    f"Hi {voicemail_lead['first_name']}, we just tried giving you a call but couldn't "
                    f"reach you. Feel free to reply here anytime, or let us know a good time to call back!"
                    if voicemail_lead.get("first_name") else
                    "Hi, we just tried giving you a call but couldn't reach you. Feel free to reply here "
                    "anytime, or let us know a good time to call back!"
                )
                await _send_sms(voicemail_lead["phone"], msg)
                conv_id = _get_or_create_sms_conv(voicemail_lead["id"], voicemail_lead["business_id"], "sms")
                _save_message(conv_id, "agent", msg)
            except Exception as sms_err:
                logger.warning(f"[calls/update] voicemail follow-up SMS failed for {body.call_id}: {sms_err}")

        return {"success": True, "call_id": body.call_id, "outcome": body.outcome}

    except Exception as e:
        conn.rollback()
        logger.error(f"[calls/update] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── POST /api/calls/outbound ─────────────────────────────────────────────────

class OutboundCallBody(BaseModel):
    lead_id: str
    conv_id: Optional[str] = None


def _get_agent_config_for_lead(business_id: str, lead_tags: list, lead_stage: str = None) -> tuple[str, str, dict | None] | None:
    """
    Returns (system_prompt, agent_name, voice) for the given lead tags/stage,
    or None if no active Lead Config rule matches — callers MUST treat None
    as "do not place this call," not fall back to a generic assistant (see
    lead_configs requirement: no automated call/SMS without an explicitly
    assigned agent). voice is {"provider", "voiceId"} or None (agent has no
    override → caller should use its own default voice).

    Match priority:
    1. Exact tag match against Lead Config conditions
    2. Stage ("status" field) match against Lead Config conditions
    """
    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        cur.execute("""
            SELECT lc.condition_logic, lc.conditions,
                   a.name AS agent_name, a.persona,
                   a.call_prompt, a.system_prompt,
                   a.voice_provider, a.voice_id, a.voice_extra
            FROM lead_configs lc
            JOIN ai_agents a ON a.id = lc.agent_id
            WHERE lc.business_id = %s AND lc.status = 'active'
            ORDER BY lc.created_at ASC
        """, (business_id,))
        raw_configs = cur.fetchall()

        # Resolve prompt with logging so we can see exactly which level was used
        def _resolve_outbound_prompt(cfg: dict) -> str:
            agent = cfg["agent_name"]
            if cfg.get("call_prompt"):
                logger.info(f"[calls:outbound] agent='{agent}' → using call_prompt")
                return cfg["call_prompt"]
            if cfg.get("system_prompt"):
                logger.info(f"[calls:outbound] agent='{agent}' → call_prompt empty, using system_prompt")
                return cfg["system_prompt"]
            logger.warning(f"[calls:outbound] agent='{agent}' → ALL prompts empty, using default")
            return ""

        configs = []
        for cfg in raw_configs:
            c = dict(cfg)
            c["system_prompt"] = _resolve_outbound_prompt(c)
            configs.append(c)

        _SEMANTIC = [
            {"insurance", "sales", "inquiry", "coverage", "policy", "premium", "life", "lead", "quote"},
            {"medical", "health", "patient", "new-patient", "clinic", "doctor", "checkup", "dental", "appointment"},
            {"lawn", "garden", "gardening", "landscaping"},
        ]

        def _tag_hit(condition_value: str, tags: list) -> bool:
            cv = condition_value.lower().replace("-", " ").replace("_", " ")
            cv_words = set(cv.split())
            for tag in tags:
                t = tag.lower().replace("-", " ").replace("_", " ")
                t_words = set(t.split())
                if cv == t or (cv_words & t_words):
                    return True
                for grp in _SEMANTIC:
                    if (any(w in grp for w in cv_words) or cv in grp) and \
                       (any(w in grp for w in t_words) or t in grp):
                        return True
            return False

        def _rule_hit(cfg: dict) -> bool:
            conditions = cfg["conditions"] or []
            logic      = cfg["condition_logic"] or "any"
            matches    = []
            for c in conditions:
                field = c.get("field")
                val   = c.get("value", "")
                if field == "tag":
                    matches.append(_tag_hit(val, lead_tags))
                elif field == "status":
                    matches.append(lead_stage == val)
                else:
                    matches.append(False)
            return any(matches) if logic == "any" else (all(matches) if matches else False)

        # Tag matches take priority over stage matches — per this function's
        # own documented contract above. This used to just be one loop
        # returning the first hit in created_at order regardless of whether
        # it matched by tag or by stage, which silently contradicted the
        # docstring: two active rules for the same business could both match
        # the same lead (one by tag, one by stage), and whichever happened to
        # be created first won — by accident, not by the documented priority.
        # Two passes, both still created_at order among themselves.
        tag_configs   = [c for c in configs if any((cond.get("field") == "tag") for cond in (c["conditions"] or []))]
        stage_configs = [c for c in configs if c not in tag_configs]

        def _cfg_voice(cfg: dict) -> dict | None:
            provider, voice_id = cfg.get("voice_provider"), cfg.get("voice_id")
            if not (provider and voice_id):
                return None
            return {"provider": provider, "voiceId": voice_id, **(cfg.get("voice_extra") or {})}

        for cfg in tag_configs:
            if _rule_hit(cfg) and cfg["system_prompt"]:
                return _build_prompt(cfg), cfg["agent_name"], _cfg_voice(cfg)
        for cfg in stage_configs:
            if _rule_hit(cfg) and cfg["system_prompt"]:
                return _build_prompt(cfg), cfg["agent_name"], _cfg_voice(cfg)

    finally:
        cur.close(); conn.close()
    return None


def _build_prompt(cfg: dict) -> str:
    prompt = cfg["system_prompt"]
    if cfg["persona"]:
        prompt = f"You are {cfg['agent_name']}. {cfg['persona']}\n\n{prompt}"
    prompt += (
        "\n\nPRICING GUARDRAIL: You may discuss general ranges or what affects cost, but never "
        "state or confirm a specific premium or coverage amount as final — always say a licensed "
        "agent will confirm exact numbers."
    )
    return prompt




@router.post("/outbound")
async def outbound_call(body: OutboundCallBody, request: Request):
    """
    Initiate an outbound Vapi call to a lead.
    Injects the lead's SMS/chat conversation history into the AI system prompt as context.
    """
    if not VAPI_API_KEY or not VAPI_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="Vapi not configured")

    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        # 1. Fetch lead details
        cur.execute(
            "SELECT id, business_id, first_name, last_name, phone, tags, notes, stage FROM leads WHERE id = %s",
            (body.lead_id,)
        )
        lead = cur.fetchone()
        if not lead:
            logger.warning(f"[calls:outbound] lead NOT FOUND id={body.lead_id}")
            raise HTTPException(status_code=404, detail="Lead not found")
        call_number = lead.get("phone")
        if not call_number:
            logger.warning(f"[calls:outbound] lead has NO phone id={body.lead_id}")
            raise HTTPException(status_code=400, detail="Lead has no phone number")

        lead_tags   = lead["tags"] or []
        business_id = lead["business_id"] or "bus_001"
        logger.info(f"[calls:outbound] lead found → id={lead['id']} name={lead['first_name']} phone={call_number} tags={lead_tags}")

        # 9am-6pm US Central only, same policy as the automated dialer
        # (core/callback_scheduler.py) — applies here too even though this
        # is staff-triggered, not automated, since the calling-hours rule is
        # about when the LEAD gets contacted, not who clicked the button.
        from api.sms.router import _is_within_quiet_hours
        allowed, reason = _is_within_quiet_hours(business_id)
        if not allowed:
            raise HTTPException(status_code=422, detail=f"Blocked by calling hours — {reason}")

        # 2. Fetch conversation history
        conv_id = body.conv_id
        if not conv_id:
            cur.execute(
                "SELECT id FROM conversations WHERE lead_id = %s AND business_id = %s ORDER BY created_at DESC LIMIT 1",
                (lead["id"], business_id)
            )
            conv_row = cur.fetchone()
            if conv_row:
                conv_id = conv_row["id"]

        history_text = ""
        # Separate from history_text being non-empty: unanswered outreach SMS
        # are OUR OWN messages, saved to history even if the lead never
        # replied. lead_has_replied is the only thing that can tell "we
        # texted, they answered" from "we texted into silence" — see the
        # matching fix in callback_scheduler.py for the live bug this covers.
        lead_has_replied = False
        # Quoted/closed leads get the condensed deal summary instead of the
        # raw SMS history — same reasoning as callback_scheduler._fire_callback.
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
                logger.info(f"[calls:outbound] injecting deal summary as context for lead={lead['id']}")

        if not history_text and conv_id:
            cur.execute(
                "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY created_at ASC LIMIT 20",
                (conv_id,)
            )
            msgs = cur.fetchall()
            if msgs:
                lead_has_replied = any(m["role"] not in ("agent", "assistant") for m in msgs)
                logger.info(f"[calls:outbound] injecting {len(msgs)} SMS messages as context conv={conv_id} lead_has_replied={lead_has_replied}")
                if lead_has_replied:
                    history_text = "\n\nPrevious conversation with this lead via SMS:\n"
                else:
                    history_text = (
                        "\n\nPrior SMS messages sent to this lead (they have NOT replied to any of "
                        "these — this is not a conversation, just our own outreach):\n"
                    )
                for m in msgs:
                    label = "Agent" if m["role"] in ("agent", "assistant") else "Lead"
                    history_text += f"{label}: {m['content']}\n"
                if lead_has_replied:
                    history_text += "\nUse this context to continue the conversation naturally on the call."
                else:
                    history_text += (
                        "\nThe lead never responded to any of the above — do NOT say 'continuing our "
                        "conversation' or imply they replied. Acknowledge you've reached out before "
                        "without a response, then start the conversation fresh."
                    )
            else:
                logger.info(f"[calls:outbound] no SMS history found for conv={conv_id}")
        elif not history_text:
            logger.info(f"[calls:outbound] no conversation found for lead={lead['id']} — no context injected")

        # 3. Get agent prompt from Lead Config — no rule matched means no
        # agent has been assigned to this lead's tags/stage yet, so we refuse
        # to place the call with a generic/unbranded assistant.
        matched = _get_agent_config_for_lead(business_id, lead_tags, lead.get("stage"))
        if matched is None:
            logger.warning(f"[calls:outbound] no agent configured for lead={lead['id']} tags={lead_tags} stage={lead.get('stage')} — refusing to place call")
            raise HTTPException(status_code=422, detail="No AI agent is configured for this lead's tags/stage yet. Add a Lead Config rule first.")
        base_prompt, agent_name, agent_voice = matched
        logger.info(f"[calls:outbound] agent='{agent_name}' prompt_len={len(base_prompt)}")

        from vapi.router import _booking_on_call_instruction, _BOOK_APPOINTMENT_TOOL
        full_prompt = (
            base_prompt
            + history_text
            + "\n\nIMPORTANT: You are now on a phone call. Keep responses concise and conversational. "
            "Greet the lead by their first name."
            + _booking_on_call_instruction()
        )

        lead_name = lead["first_name"] or "there"

        # The opening line must match what actually happened — see the same
        # three-way split (and why "any history" alone isn't enough) in
        # callback_scheduler.py's identical fix.
        if lead_has_replied:
            topic = (lead.get("notes") or "").strip() or (lead_tags[0] if lead_tags else "your inquiry")
            first_message = (
                f"Hi {lead_name}! This is {agent_name}, following up on the text conversation we had "
                f"about {topic}. Is now a good time to continue?"
            )
        elif history_text:
            first_message = (
                f"Hi {lead_name}! This is {agent_name} with Shield Insurance Agency. We've been trying "
                "to reach you by text about insurance coverage but haven't heard back — is now a good "
                "time to chat?"
            )
        else:
            first_message = f"Hi {lead_name}! This is {agent_name}. Hope you're doing well — is now a good time to chat?"

        # 4. Call Vapi API
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
                # Empty voicemailMessage — per Vapi, this makes the call end
                # silently the moment voicemailDetection fires instead of
                # playing a message (requested: cut the call on voicemail,
                # don't leave one).
                "voicemailMessage":  "",
                "voicemailDetection": {
                    "provider": "vapi",
                    "backoffPlan": {"startAtSeconds": 2, "frequencySeconds": 2.5, "maxRetries": 5},
                    "beepMaxAwaitSeconds": 12,
                },
                "transcriber":       {"provider": "deepgram", "model": "nova-2", "language": "en"},
                "voice":             agent_voice or {"provider": "vapi", "voiceId": "Elliot"},
                "recordingEnabled":  True,
                "endCallFunctionEnabled": True,
                "maxDurationSeconds": 1800,
                # Vapi injects ambient "office" background sound unless told
                # not to — off by explicit request.
                "backgroundSound": "off",
                # 25s: lower than the 45s that fixed the mid-sentence hangup,
                # but safe now that the model below is much faster per turn —
                # real turns finish well under this, so it only cuts genuine
                # dead air short instead of killing an in-flight reply.
                "silenceTimeoutSeconds": 25,
                # Smart endpointing reduces false "user has stopped talking"
                # reads.
                "startSpeakingPlan": {
                    "waitSeconds": 0.25,
                    "smartEndpointingPlan": {"provider": "vapi"},
                },
                # numWords=2/voiceSeconds=0.2 was firing on background noise,
                # breath sounds, and stray filler ("uh") — confirmed live, it
                # cut the assistant off mid-sentence and made it restart the
                # same words (transcript showed "the the coverage amount",
                # "Sorry. I didn't sorry. I didn't catch that."). Raised so
                # genuine barge-in still works but a stray syllable doesn't
                # trigger a false interruption.
                "stopSpeakingPlan": {
                    "numWords": 4,
                    "voiceSeconds": 0.5,
                    "backoffSeconds": 1,
                },
                "endCallPhrases": [
                    "goodbye", "bye bye", "take care", "talk soon",
                    "have a great day", "see you then", "talk to you soon",
                ],
                "model": {
                    "provider":  "openai",
                    # Migrated off Groq. Groq's llama-3.1-8b-instant was
                    # chosen specifically for near-instant per-turn latency on
                    # calls (see silenceTimeoutSeconds note above, tuned
                    # against that speed) — gpt-4o-mini is typically slower
                    # per turn. Watch real call latency after this switch; if
                    # turns start feeling laggy or silenceTimeoutSeconds cuts
                    # off in-flight replies, that timeout may need raising.
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

        if not res.is_success:
            logger.error(f"[calls/outbound] Vapi error {res.status_code}: {res.text}")
            raise HTTPException(status_code=502, detail=f"Vapi error: {res.text}")

        vapi_data = res.json()
        call_id   = vapi_data.get("id", "")
        logger.info(f"[calls:outbound] Vapi call initiated → call_id={call_id} phone={call_number} agent={agent_name}")

        # 5. Log to voice_calls
        vc_id = f"vc_{uuid.uuid4().hex[:12]}"
        cur.execute("""
            INSERT INTO voice_calls (id, call_id, provider, status, direction, patient_phone, caller_name, lead_id, created_at, updated_at)
            VALUES (%s, %s, 'vapi', 'initiated', 'outbound', %s, %s, %s, NOW(), NOW())
            ON CONFLICT (call_id) DO NOTHING
        """, (vc_id, call_id, lead["phone"], f"{lead['first_name']} {lead['last_name']}".strip(), lead["id"]))
        conn.commit()
        logger.info(f"[calls:outbound] saved to voice_calls vc_id={vc_id} call_id={call_id}")

        return {
            "success": True,
            "data": {
                "call_id":    call_id,
                "phone":      lead["phone"],
                "agent_name": agent_name,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"[calls:outbound] FAILED lead_id={body.lead_id} error={e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# ── DELETE /api/calls/end/{call_id} ─────────────────────────────────────────

@router.delete("/end/{call_id}")
async def end_call(call_id: str):
    """End an active Vapi call by call_id."""
    if not VAPI_API_KEY:
        raise HTTPException(status_code=503, detail="Vapi not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.delete(
            f"https://api.vapi.ai/call/{call_id}",
            headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
        )
    if not res.is_success:
        raise HTTPException(status_code=502, detail=f"Vapi error: {res.text}")
    logger.info(f"[calls/end] ended call {call_id}")
    return {"success": True, "call_id": call_id}
