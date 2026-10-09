"""
Vapi Voice Bot — webhook handler.
Vapi handles STT + LLM + TTS internally.
This server only receives call events and saves appointments.
"""

import json
import logging
import asyncio
import re
import uuid
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Request, Response

from core.db       import get_conn, get_dict_cursor, DEFAULT_BUSINESS_ID
from core.sms      import send_confirmation
from core.calendar import sync_appointment, update_event, delete_event
from core.hubspot   import sync_contact_and_meeting
from core.gmail     import send_appointment_confirmation
from core.config    import OPENAI_API_KEY, CRM_SERVICE_URL, VAPI_API_KEY, VAPI_ASSISTANT_ID
from core.lead_transitions import transition_via_crm_api
from core.llm_retry import post_with_retry
from core.timezone import local_to_utc
from voice.prompt   import build_date_lookup

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vapi")

_SCHEDULE_CALLBACK_TOOL = {
    "type": "function",
    "function": {
        "name": "schedule_callback",
        "description": (
            "Schedule a callback call for this lead. "
            "Use ONLY when the lead explicitly says they are busy and asks to be called back in X minutes or X hours. "
            "Do NOT use for appointment booking."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "Minutes from now to call back (e.g. 2 for 'call me in 2 minutes').",
                },
                "hours": {
                    "type": "integer",
                    "description": "Hours from now to call back (e.g. 1 for 'call me in an hour').",
                },
            },
        },
    },
}

_BOOK_APPOINTMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "book_appointment",
        "description": (
            "Book a real appointment for this caller RIGHT NOW, during the call. "
            "Call this ONLY after ALL THREE of: (1) the caller confirmed a specific day, "
            "(2) the caller confirmed a specific clock time, (3) you asked for their email, "
            "read it back to them letter-by-letter, and they confirmed it's correct. "
            "Never say the appointment is booked before calling this function — speak "
            "whatever this function returns back to the caller, since that is the real "
            "outcome (it may report the time is taken and offer an alternative instead of "
            "confirming)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "The confirmed appointment date in YYYY-MM-DD format, resolved using the date lookup table in your instructions.",
                },
                "time": {
                    "type": "string",
                    "description": "The confirmed appointment time in 24-hour HH:MM format (e.g. '14:15' for 2:15 PM). Use the caller's EXACT stated time — never round it.",
                },
                "email": {
                    "type": "string",
                    "description": "The caller's email address, spelled out and confirmed with them (e.g. 'john at gmail dot com' -> 'john@gmail.com').",
                },
            },
            "required": ["date", "time", "email"],
        },
    },
}


async def _get_sms_context(phone: str) -> str:
    """Fetch last 20 SMS/WhatsApp messages for this phone and summarize."""
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        cur.execute("""
            SELECT m.role, m.content
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            JOIN leads l ON l.id = c.lead_id
            WHERE l.phone = %s AND c.channel IN ('sms', 'whatsapp')
            ORDER BY m.created_at DESC
            LIMIT 20
        """, (phone,))
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            return ""

        rows = list(reversed(rows))
        chat = "\n".join(
            f"{'Agent' if r['role'] in ('agent','assistant') else 'Customer'}: {r['content']}"
            for r in rows
        )

        if not OPENAI_API_KEY:
            return f"\n\nPrevious SMS/WhatsApp chat:\n{chat}"

        # Must be a non-blocking call — this runs inline in the assistant-request
        # webhook, on the same event loop that also has to answer Vapi's
        # tool-calls webhook for calls already in progress. The old code used
        # the synchronous OpenAI SDK client here, which froze the whole process
        # (every in-progress call's tool-calls, every SMS) for as long as this
        # one summarization took — exactly the kind of stall that shows up as
        # live in-call lag or the assistant going silent.
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await post_with_retry(
                client, "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "Summarize this SMS conversation in 2-3 sentences. Focus on: what the customer needs, key info they shared (name, product, details). Be concise."},
                        {"role": "user", "content": chat},
                    ],
                    "max_tokens": 120,
                    "temperature": 0.3,
                },
                label="vapi:sms_context",
            )
        summary = resp.json()["choices"][0]["message"]["content"].strip()
        logger.info(f"[vapi] SMS context for {phone}: {summary[:80]}")
        return f"\n\nPREVIOUS SMS CONTEXT: {summary}"
    except Exception as e:
        logger.warning(f"[vapi] SMS context fetch failed: {e}")
        return ""


# ── Slot availability tool ────────────────────────────────────────────────────

ALLOWED_HOURS  = [10, 14, 16]
SLOT_LABELS    = {10: "10 AM", 14: "2 PM", 16: "4 PM"}


def _check_slot(date: str, time_str: str, service: str) -> str:
    try:
        dt           = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
        closest_hour = min(ALLOWED_HOURS, key=lambda h: abs(h - dt.hour))
        start        = dt.replace(hour=closest_hour, minute=0, second=0)
    except Exception:
        return "Invalid date or time provided."

    # Weekend check — clinic is open Monday to Friday only
    if start.weekday() >= 5:  # 5=Saturday, 6=Sunday
        day_name = start.strftime("%A")
        return f"We are closed on {day_name}. Our clinic is open Monday to Friday only. Please choose a weekday."

    date_label = start.strftime("%A, %B %-d")
    day_start  = start.replace(hour=0, minute=0, second=0)
    day_end    = day_start + timedelta(days=1)
    end_time   = start + timedelta(hours=1)

    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)

        # Check emergency blocks first
        cur.execute("""
            SELECT reason, provider_id FROM emergency_blocks
            WHERE business_id = %s AND status = 'active'
              AND start_time <= %s AND end_time >= %s
            LIMIT 1
        """, (DEFAULT_BUSINESS_ID, start, end_time))
        block = cur.fetchone()
        if block:
            if block["provider_id"] is None:
                cur.close(); conn.close()
                return (f"We are unable to accept appointments on {date_label} due to a clinic closure. "
                        f"Please choose a different date.")
            elif block["provider_id"]:
                # Provider-specific block — only block if same provider
                prov_check_id = block["provider_id"]
                if service:
                    cur.execute("""
                        SELECT ps.provider_id FROM services s
                        JOIN provider_services ps ON ps.service_id = s.id AND ps.business_id = s.business_id
                        WHERE s.business_id = %s AND LOWER(s.name) LIKE LOWER(%s) LIMIT 1
                    """, (DEFAULT_BUSINESS_ID, f"%{service}%"))
                    row = cur.fetchone()
                    if row and row["provider_id"] == prov_check_id:
                        cur.close(); conn.close()
                        return (f"The provider is unavailable on {date_label}. "
                                f"Please choose a different date or provider.")

        # Find provider for the service
        provider_id = None
        if service:
            cur.execute("""
                SELECT ps.provider_id FROM services s
                JOIN provider_services ps ON ps.service_id = s.id AND ps.business_id = s.business_id
                WHERE s.business_id = %s AND LOWER(s.name) LIKE LOWER(%s) LIMIT 1
            """, (DEFAULT_BUSINESS_ID, f"%{service}%"))
            row         = cur.fetchone()
            provider_id = row["provider_id"] if row else None

        # Check if the requested slot is taken
        if provider_id:
            cur.execute("""
                SELECT id FROM appointments
                WHERE provider_id = %s AND start_time = %s AND status IN ('pending','confirmed')
            """, (provider_id, start))
        else:
            cur.execute("""
                SELECT id FROM appointments
                WHERE business_id = %s AND start_time = %s AND status IN ('pending','confirmed')
            """, (DEFAULT_BUSINESS_ID, start))
        taken = cur.fetchone()

        if not taken:
            cur.close(); conn.close()
            return f"The {SLOT_LABELS[closest_hour]} slot on {date_label} is available."

        # Slot taken — find what's free that day
        if provider_id:
            cur.execute("""
                SELECT start_time FROM appointments
                WHERE provider_id = %s AND start_time >= %s AND start_time < %s
                  AND status IN ('pending','confirmed')
            """, (provider_id, day_start, day_end))
        else:
            cur.execute("""
                SELECT start_time FROM appointments
                WHERE business_id = %s AND start_time >= %s AND start_time < %s
                  AND status IN ('pending','confirmed')
            """, (DEFAULT_BUSINESS_ID, day_start, day_end))

        booked_hours = {r["start_time"].hour for r in cur.fetchall()}
        available    = [SLOT_LABELS[h] for h in ALLOWED_HOURS if h not in booked_hours]
        cur.close(); conn.close()

        if available:
            return (f"The {SLOT_LABELS[closest_hour]} slot on {date_label} is not available. "
                    f"Available slots on that day: {', '.join(available)}.")
        return f"All slots on {date_label} are fully booked. Please ask the caller to choose a different day."

    except Exception as e:
        logger.error(f"[vapi:tool] DB error: {e}")
        return "Unable to check availability right now. Please proceed with booking."


@router.post("/tools/availability")
async def availability_tool(request: Request):
    """Vapi calls this when bot needs to check slot availability."""
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)

    tool_calls = data.get("message", {}).get("toolCallList", [])
    results    = []

    for call in tool_calls:
        call_id = call.get("id", "")
        args    = call.get("function", {}).get("arguments", {})
        date    = args.get("date", "")
        time    = args.get("time", "")
        service = args.get("service", "")
        logger.info(f"[vapi:tool] check_availability date={date} time={time} service={service}")
        result  = _check_slot(date, time, service)
        results.append({"toolCallId": call_id, "result": result})

    return {"results": results}


# ── Dynamic assistant per caller ─────────────────────────────────────────────

async def _get_assistant_for_caller(from_phone: str) -> dict:
    """
    Look up caller's phone → find lead name + tags → match Lead Config → return agent prompt.
    Greets caller by name using firstMessage.
    """
    from vapi.prompt import _build_prompt
    default_prompt, default_name, default_voice = _build_prompt()

    if not from_phone:
        return _base_assistant(default_prompt, default_name, voice=default_voice)

    sms_context = await _get_sms_context(from_phone)

    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)

        # Find all leads for this phone — most recent first
        cur.execute(
            "SELECT id, business_id, first_name, last_name, tags, stage FROM leads WHERE phone = %s ORDER BY created_at DESC",
            (from_phone,)
        )
        leads = cur.fetchall()

        if not leads:
            cur.close(); conn.close()
            return _base_assistant(default_prompt, default_name, voice=default_voice)

        business_id  = leads[0]["business_id"] or DEFAULT_BUSINESS_ID
        caller_fname = leads[0]["first_name"] or ""
        caller_lname = leads[0]["last_name"] or ""
        caller_name  = caller_fname or None

        # Load all active Lead Configs for this business
        cur.execute("""
            SELECT lc.condition_logic, lc.conditions,
                   a.name AS agent_name, a.role, a.persona,
                   a.call_prompt, a.system_prompt,
                   a.tone, a.language, a.voice_provider, a.voice_id, a.voice_extra
            FROM lead_configs lc
            JOIN ai_agents a ON a.id = lc.agent_id
            WHERE lc.business_id = %s AND lc.status = 'active'
            ORDER BY lc.created_at ASC
        """, (business_id,))
        configs = cur.fetchall()
        cur.close(); conn.close()

        def _resolve_call_prompt(cfg: dict) -> str:
            agent = cfg["agent_name"]
            if cfg.get("call_prompt"):
                logger.info(f"[vapi:prompt] agent='{agent}' → using call_prompt")
                return cfg["call_prompt"]
            if cfg.get("system_prompt"):
                logger.info(f"[vapi:prompt] agent='{agent}' → call_prompt empty, using system_prompt")
                return cfg["system_prompt"]
            logger.warning(f"[vapi:prompt] agent='{agent}' → ALL prompts empty, using default")
            return ""

        MEDICAL_KEYWORDS = {"medical", "dental", "clinic", "health", "patient", "doctor",
                            "new-patient", "appointment", "urgent", "emergency"}
        SALES_KEYWORDS   = {"sales", "product", "purchase", "buy", "order", "quote", "deal", "vip",
                            "insurance", "coverage", "policy", "inquiry", "lead", "premium"}
        LOAN_KEYWORDS    = {"loan", "finance", "credit", "garden", "gardening", "landscaping"}

        _SEMANTIC = [
            {"insurance", "sales", "inquiry", "coverage", "policy", "premium", "life", "lead", "quote"},
            {"medical", "health", "patient", "new-patient", "clinic", "doctor", "checkup", "dental", "appointment"},
            {"lawn", "garden", "gardening", "landscaping", "loan", "finance", "credit"},
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

        # Build caller context to inject into every prompt
        all_tags_list = [t for lead in leads for t in (lead["tags"] or [])]
        caller_context = ""
        if caller_fname:
            full_name = f"{caller_fname} {caller_lname}".strip()
            caller_context += f"\n\nCALLER CONTEXT: The caller's name is {full_name}."
            if all_tags_list:
                caller_context += f" They are interested in: {', '.join(all_tags_list)}."
            caller_context += " Use their name naturally in conversation. Do NOT ask for their name again."

        # Step 1: smart tag match across all leads
        # Pre-resolve prompt for each config with clear logging
        for cfg in configs:
            resolved = _resolve_call_prompt(cfg)
            cfg["system_prompt"] = resolved  # inject resolved so _vapi_prompt uses it

        for lead in leads:
            lead_tags  = lead["tags"] or []
            lead_stage = lead.get("stage")
            for cfg in configs:
                conditions = cfg["conditions"] or []
                logic      = cfg["condition_logic"] or "any"
                # Status-only rules (e.g. the quoted/closed Lead Config, which
                # has no tag conditions at all) used to be silently dropped
                # here — this list comprehension only ever evaluated "tag"
                # conditions, so a quoted lead calling in always fell through
                # to the same fuzzy tag match as a brand-new lead. Evaluate
                # "status" conditions too, matching how the SMS/outbound-call
                # matchers already do it.
                matches = []
                for c in conditions:
                    field = c.get("field")
                    if field == "tag":
                        matches.append(_tag_hit(c.get("value", ""), lead_tags))
                    elif field == "status":
                        matches.append(lead_stage == c.get("value"))
                hit = any(matches) if logic == "any" else (all(matches) if matches else False)
                if hit and cfg["system_prompt"]:
                    prompt = _vapi_prompt(cfg, lead_tags) + sms_context + caller_context
                    logger.info(f"[vapi] exact match agent '{cfg['agent_name']}' for tags {lead_tags} caller={caller_name}")
                    return _base_assistant(prompt, cfg["agent_name"], cfg.get("language", "English"), cfg.get("role", ""), caller_name, voice=_agent_voice(cfg))

        # Step 2: fuzzy keyword match
        all_tags = {t.lower() for lead in leads for t in (lead["tags"] or [])}
        for cfg in configs:
            if not cfg["system_prompt"]:
                continue
            agent_lower = cfg["agent_name"].lower()
            cond_values = {c.get("value","").lower() for c in (cfg["conditions"] or []) if c.get("field") == "tag"}
            if (all_tags & MEDICAL_KEYWORDS) and any(k in agent_lower or k in cond_values for k in MEDICAL_KEYWORDS):
                prompt = _vapi_prompt(cfg, list(all_tags)) + sms_context + caller_context
                logger.info(f"[vapi] fuzzy match agent '{cfg['agent_name']}' for tags {all_tags}")
                return _base_assistant(prompt, cfg["agent_name"], cfg.get("language", "English"), cfg.get("role", ""), caller_name, voice=_agent_voice(cfg))
            if (all_tags & SALES_KEYWORDS) and any(k in agent_lower or k in cond_values for k in SALES_KEYWORDS):
                prompt = _vapi_prompt(cfg, list(all_tags)) + sms_context + caller_context
                return _base_assistant(prompt, cfg["agent_name"], cfg.get("language", "English"), cfg.get("role", ""), caller_name, voice=_agent_voice(cfg))
            if (all_tags & LOAN_KEYWORDS) and any(k in agent_lower or k in cond_values for k in LOAN_KEYWORDS):
                prompt = _vapi_prompt(cfg, list(all_tags)) + sms_context + caller_context
                return _base_assistant(prompt, cfg["agent_name"], cfg.get("language", "English"), cfg.get("role", ""), caller_name, voice=_agent_voice(cfg))

        # Step 3: fallback — first config + inject tags
        if configs and configs[0]["system_prompt"]:
            prompt = _vapi_prompt(configs[0], list(all_tags)) + sms_context + caller_context
            logger.info(f"[vapi] fallback agent '{configs[0]['agent_name']}' tags={all_tags}")
            return _base_assistant(prompt, configs[0]["agent_name"], configs[0].get("language", "English"), configs[0].get("role", ""), caller_name, voice=_agent_voice(configs[0]))

    except Exception as e:
        logger.error(f"[vapi] assistant lookup error: {e}")

    return _base_assistant(default_prompt, default_name, voice=default_voice)


LANGUAGE_CONFIG = {
    "Urdu": {
        "transcriber":    {"provider": "deepgram", "model": "nova-2", "language": "multi"},
        "voice":          {"provider": "azure", "voiceId": "ur-PK-UzmaNeural"},
        "prompt_note":    "Respond ONLY in Urdu (اردو). Use natural conversational Urdu. Keep responses short and clear.",
        "first_message":  "السلام علیکم! میں آپ کی کیا مدد کر سکتا ہوں؟",
    },
    "Hindi": {
        "transcriber":    {"provider": "deepgram", "model": "nova-2", "language": "hi"},
        "voice":          {"provider": "azure", "voiceId": "hi-IN-SwaraNeural"},
        "prompt_note":    "Respond ONLY in Hindi. Use natural conversational Hindi.",
        "first_message":  "नमस्ते! मैं आपकी कैसे मदद कर सकता हूं?",
    },
    "English": {
        "transcriber":    {"provider": "deepgram", "model": "nova-2", "language": "en"},
        # "voice":        {"provider": "azure", "voiceId": "en-US-JennyNeural"},  # Groq era — Azure Jenny
        "voice":          {"provider": "vapi", "voiceId": "Elliot"},
        "prompt_note":    "",
        "first_message":  "",
    },
}


def _booking_on_call_instruction() -> str:
    """Shared booking instruction for both inbound (this file) and outbound
    (api/calls/router.py) call prompts — keeps the two paths behaviorally
    identical instead of drifting apart."""
    return (
        "\n\nBOOKING ON A CALL: If the caller wants to book an appointment, collect it "
        "live, right here on the call — do not end the call without doing this. Ask for "
        "a specific day AND a specific clock time. Once you have both, ask for their "
        "email, then read it back to them letter-by-letter to confirm it's correct "
        "before using it. Only once you have all three (day, time, confirmed email), "
        "call the book_appointment function. Never tell the caller they're booked before "
        "calling it — speak exactly what the function's result tells you to say, since "
        "it may report the time is taken and offer an alternative instead of confirming. "
        "If the function asks you to try again (invalid email, taken slot, etc.), get the "
        "corrected info from the caller and call it again — do not give up and do not "
        "claim success anyway. Use the caller's EXACT stated time, never round it (e.g. "
        "2:15 PM stays 2:15 PM, not 2:00 PM). Use this date lookup table to convert "
        "relative days to YYYY-MM-DD for the function call:\n"
        f"{build_date_lookup()}"
    )


def _vapi_prompt(cfg: dict, lead_tags: list) -> str:
    prompt = cfg["system_prompt"]
    if cfg["persona"]:
        prompt = f"You are {cfg['agent_name']}. {cfg['persona']}\n\n{prompt}"
    if lead_tags:
        prompt += f"\n\nLead context: Tagged as {', '.join(lead_tags)}. Address their specific need."
    lang_note = LANGUAGE_CONFIG.get(cfg.get("language", "English"), {}).get("prompt_note", "")
    if lang_note:
        prompt += f"\n\nLANGUAGE INSTRUCTION: {lang_note}"
    prompt += "\n\nIMPORTANT: You are on a phone call. Keep responses concise and conversational."
    prompt += (
        "\n\nPRICING GUARDRAIL: You may discuss general ranges or what affects cost, but never "
        "state or confirm a specific premium or coverage amount as final — always say a licensed "
        "agent will confirm exact numbers."
    )
    prompt += _booking_on_call_instruction()
    return prompt


def _make_first_message(agent_name: str, role: str = "") -> str:
    role_lower = (role or agent_name).lower()
    if "insurance" in role_lower:
        return (
            "Hi, thank you for calling! "
            "I am here to help you today. "
            "What can I assist you with?"
        )
    if "medical" in role_lower or "receptionist" in role_lower:
        return (
            "Hello, thank you for calling! "
            "How can I assist you today?"
        )
    return f"Hello! Thank you for calling. How can I help you today?"


def _agent_voice(cfg: dict) -> dict | None:
    """Per-agent voice override (ai_agents.voice_provider/voice_id). None
    means "no override" — _base_assistant then falls back to the
    language-default voice exactly as it did before this field existed."""
    provider = cfg.get("voice_provider")
    voice_id = cfg.get("voice_id")
    if provider and voice_id:
        return {"provider": provider, "voiceId": voice_id, **(cfg.get("voice_extra") or {})}
    return None


def _base_assistant(system_prompt: str, agent_name: str, language: str = "English", role: str = "", caller_name: str = None, voice: dict | None = None) -> dict:
    """Full inline assistant config — no assistantId so Vapi uses exactly this config."""
    lang_cfg  = LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["English"])
    if caller_name:
        first_msg = f"Hi {caller_name}! This is {agent_name}. How can I help you today?"
    else:
        first_msg = lang_cfg.get("first_message") or _make_first_message(agent_name, role)
    return {
        "name":         agent_name,
        "firstMessage": first_msg,
        # The webhook caller wraps this with a fixed assistantId + these
        # overrides — that dashboard assistant may have its own leftover
        # endCallMessage from a prior unrelated business, read verbatim at
        # call end otherwise (confirmed live on the outbound path — see
        # api/calls/router.py).
        "endCallMessage": "",
        "transcriber":  lang_cfg["transcriber"],
        "voice":        voice or lang_cfg["voice"],
        # "model": {                          # Groq era — llama-3.3-70b-versatile
        #     "provider":  "groq",
        #     "model":     "llama-3.3-70b-versatile",
        #     "messages":  [{"role": "system", "content": system_prompt}],
        #     "maxTokens": 100,
        # },
        # "model": {                          # Groq era — llama-3.1-8b-instant,
        #     "provider":  "groq",             # chosen for near-instant per-turn
        #     "model":     "llama-3.1-8b-instant",  # latency on live calls.
        #     "messages":  [{"role": "system", "content": system_prompt}],
        #     "maxTokens": 150,
        #     "tools": [_SCHEDULE_CALLBACK_TOOL],
        # },
        "model": {
            # Migrated off Groq. gpt-4o-mini is typically slower per turn than
            # Groq's llama-3.1-8b-instant was — watch real call latency after
            # this switch (see silenceTimeoutSeconds/timing notes in
            # api/calls/router.py and voice/router.py, tuned against Groq speed).
            "provider":  "openai",
            "model":     "gpt-4o-mini",
            "messages":  [{"role": "system", "content": system_prompt}],
            "maxTokens": 150,
            "tools": [_SCHEDULE_CALLBACK_TOOL, _BOOK_APPOINTMENT_TOOL],
        },
        # "model": {                          # Google era — gemini-2.5-flash-lite (needs Google key in Vapi)
        #     "provider":  "google",
        #     "model":     "gemini-2.5-flash-lite",
        #     "messages":  [{"role": "system", "content": system_prompt}],
        #     "maxTokens": 150,
        # },
        "endCallFunctionEnabled": False,
        "recordingEnabled":       True,
        # Vapi injects ambient "office" background sound unless told not to.
        "backgroundSound": "off",
        # 25s: lower than the 45s that fixed the mid-sentence hangup, but
        # safe now that the model above is much faster per turn.
        "silenceTimeoutSeconds": 25,
        "startSpeakingPlan": {
            "waitSeconds": 0.25,
            "smartEndpointingPlan": {"provider": "vapi"},
        },
        # numWords=2/voiceSeconds=0.2 was firing on background noise, breath
        # sounds, and stray filler ("uh") — confirmed live, it cut the
        # assistant off mid-sentence and made it restart the same words
        # (transcript showed "the the coverage amount", "Sorry. I didn't
        # sorry. I didn't catch that."). Raised so genuine barge-in still
        # works but a stray syllable doesn't trigger a false interruption.
        "stopSpeakingPlan": {
            "numWords": 4,
            "voiceSeconds": 0.5,
            "backoffSeconds": 1,
        },
        "endCallPhrases": [
            "see you then",
            "have a great day",
            "talk to you soon",
            "goodbye",
            "take care",
            "i'll call you back",
            "we'll call you back",
        ],
    }


def _handle_schedule_callback_tool(args: dict, from_phone: str) -> str:
    """Handle schedule_callback tool-call from Vapi AI during a live call."""
    try:
        import uuid as _uuid
        minutes = int(args.get("minutes") or 0)
        hours   = int(args.get("hours")   or 0)
        seconds = minutes * 60 + hours * 3600
        if seconds <= 0:
            seconds = 60 * 60  # default 1 hour

        label = (f"{hours} hour{'s' if hours != 1 else ''}" if hours >= 1 else
                 f"{minutes} minute{'s' if minutes != 1 else ''}")

        conn = get_conn(); cur = get_dict_cursor(conn)
        try:
            cur.execute("SELECT id, business_id FROM leads WHERE phone=%s LIMIT 1",
                        (from_phone,))
            lead_row = cur.fetchone()
            if lead_row:
                # Replace any earlier pending call-callback for this lead
                # instead of stacking a new row on every repeated request —
                # otherwise a lead who asks twice gets called twice.
                cur.execute("""
                    UPDATE scheduled_callbacks SET status='cancelled', updated_at=NOW()
                    WHERE lead_id=%s AND callback_type='call' AND status='pending'
                """, (lead_row["id"],))

                cb_id = f"cb_{_uuid.uuid4().hex[:12]}"
                cur.execute("""
                    INSERT INTO scheduled_callbacks
                        (id, lead_id, business_id, phone, scheduled_at, call_reason,
                         callback_type, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW() + make_interval(secs => %s), %s, 'call', NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """, (cb_id, lead_row["id"], lead_row["business_id"], from_phone,
                      seconds, f"Lead requested callback in {label} during call"))
                conn.commit()
                logger.info(f"[vapi:tool] schedule_callback → {cb_id} in {label} for {from_phone}")
                return f"Callback scheduled in {label}. I'll call you back then. Have a great day!"
            else:
                logger.warning(f"[vapi:tool] schedule_callback — lead not found for {from_phone}")
                return f"Got it! I'll call you back in {label}."
        finally:
            cur.close(); conn.close()
    except Exception as e:
        logger.error(f"[vapi:tool] schedule_callback error: {e}")
        return "Got it, I'll call you back soon!"


async def _handle_book_appointment_tool(args: dict, from_phone: str) -> str:
    """Handle book_appointment tool-call from Vapi AI during a live call.

    Reuses api/sms/router.py's _book_appointment() — the exact function behind
    SMS bookings, which the user confirmed live as "100% perfect working" —
    instead of duplicating booking/calendar/confirmation logic here. Two prior
    attempts at getting the voice model to finish booking purely via prompt
    text failed on separate live calls (no day, no email, model just claimed
    "I have you down"); a real function-call with required JSON-schema fields
    forces the model to actually supply date/time/email before it can call
    this at all, which plain prose could not enforce.
    """
    date_str = (args.get("date") or "").strip()
    time_str = (args.get("time") or "").strip()
    email    = (args.get("email") or "").strip()

    if not _EMAIL_RE.fullmatch(email):
        return ("That email doesn't look valid. Ask the caller to repeat their email "
                "address slowly, read it back to confirm, then call this function again.")

    try:
        start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception:
        return ("The date or time was invalid. Confirm the exact day and time with the "
                "caller again, then call this function again with date as YYYY-MM-DD and "
                "time as 24-hour HH:MM.")

    # No weekday restriction here, matching api/sms/router.py's _book_appointment
    # (the shared function this calls into) — that path has never enforced
    # one, so this call-side check was inconsistent with the SMS-booked
    # outcome for the exact same business/appointment type.
    end_time = start_time + timedelta(hours=1)

    try:
        conn = get_conn(); cur = get_dict_cursor(conn)
        cur.execute("SELECT id, business_id FROM leads WHERE phone=%s LIMIT 1", (from_phone,))
        lead_row = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"[vapi:tool] book_appointment lead lookup failed: {e}")
        return "Something went wrong looking up the caller's record — let them know a team member will confirm shortly by text."

    if not lead_row:
        logger.warning(f"[vapi:tool] book_appointment — no lead found for {from_phone}")
        return "Couldn't find this caller's record — let them know a team member will follow up to confirm."

    from api.sms.router import _book_appointment, _get_or_create_sms_conv, _next_five_minute_start

    try:
        day_start = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        conn = get_conn(); cur = get_dict_cursor(conn)
        cur.execute("""
            SELECT start_time FROM appointments
            WHERE business_id = %s AND status IN ('confirmed', 'pending')
              AND start_time >= %s AND start_time < %s
            ORDER BY start_time
        """, (lead_row["business_id"], day_start, day_end))
        occupied = [r["start_time"] for r in cur.fetchall()]
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"[vapi:tool] book_appointment availability check failed: {e}")
        occupied = []

    adjusted_start = _next_five_minute_start(start_time, occupied)
    if adjusted_start != start_time:
        return (f"That exact time is taken. Offer the caller "
                f"{adjusted_start.strftime('%A, %B %-d at %-I:%M %p')} instead — if they "
                f"agree, call this function again with that new time.")

    try:
        conv_id = _get_or_create_sms_conv(lead_row["id"], lead_row["business_id"], "sms")
        await _book_appointment(lead_row["id"], lead_row["business_id"], from_phone, conv_id,
                                 start_time, end_time, extracted_email=email,
                                 created_via="voice_vapi_live")
    except Exception as e:
        logger.error(f"[vapi:tool] book_appointment failed: {e}")
        return "Something went wrong while booking — let the caller know a team member will confirm shortly by text."

    logger.info(f"[vapi:tool] book_appointment → {from_phone} at {start_time} email={email}")
    return (f"Booked for {start_time.strftime('%A, %B %-d at %-I:%M %p')}. A confirmation "
            f"text and email are on the way to {email}. Tell the caller it's all set.")


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def vapi_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)

    msg  = data.get("message", {})
    kind = msg.get("type", "")

    logger.info(f"[vapi] event={kind}")

    if kind == "assistant-request":
        from_phone = msg.get("call", {}).get("customer", {}).get("number", "")
        assistant_config = await _get_assistant_for_caller(from_phone)
        logger.info(f"[vapi] assistant-request for {from_phone} → {assistant_config.get('name','default')}")
        # assistantId is just a base so calls appear grouped in Vapi's
        # dashboard — assistantOverrides supplies the actual live prompt,
        # tools, and first message, fully replacing whatever the base
        # assistant has. This used to be a hardcoded ID ("282bb750...")
        # that had been deleted from the Vapi account entirely — confirmed
        # live via a direct GET returning 404 — so this handler's response
        # was broken (pointing at a nonexistent assistant) even on the rare
        # path that reached it at all. VAPI_ASSISTANT_ID is a real,
        # continuously-existing assistant already used elsewhere (outbound
        # calls in api/calls/router.py), so reusing it here can't silently
        # drift out of sync with the account the same way again.
        return {
            "assistantId": VAPI_ASSISTANT_ID,
            "assistantOverrides": assistant_config,
        }

    elif kind == "end-of-call-report":
        transcript   = msg.get("transcript", "")
        from_phone   = (
            msg.get("customer", {}).get("number", "")
            or msg.get("call", {}).get("customer", {}).get("number", "")
        )
        call_id      = msg.get("call", {}).get("id", "") or msg.get("id", "")
        ended_reason = msg.get("endedReason", "") or msg.get("call", {}).get("endedReason", "")
        call_type    = msg.get("call", {}).get("type", "") or msg.get("type", "")
        direction    = "inbound" if "inbound" in call_type.lower() else "outbound"
        summary      = msg.get("summary", "")
        recording_url = (
            msg.get("recordingUrl", "")
            or msg.get("call", {}).get("recordingUrl", "")
            or ""
        )
        duration_seconds = int(
            msg.get("durationSeconds")
            or msg.get("call", {}).get("durationSeconds")
            or 0
        )
        logger.info(f"[vapi] call ended — reason={ended_reason} from={from_phone} call_id={call_id} duration={duration_seconds}s recording={'yes' if recording_url else 'no'}")

        if call_id:
            asyncio.create_task(
                _extract_and_save(call_id, from_phone, transcript or "", duration_seconds, ended_reason, summary, recording_url, direction, json.dumps(data))
            )

    elif kind == "tool-calls":
        # Route tool-calls inline so serverUrl webhook handles everything
        tool_calls = msg.get("toolCallList", [])
        # from_phone available for schedule_callback
        tc_from_phone = msg.get("call", {}).get("customer", {}).get("number", "")
        results = []
        for call in tool_calls:
            call_id_t = call.get("id", "")
            fn_name   = call.get("function", {}).get("name", "")
            args      = call.get("function", {}).get("arguments", {})

            if fn_name == "check_availability":
                result = _check_slot(args.get("date",""), args.get("time",""), args.get("service",""))
                logger.info(f"[vapi:tool] check_availability date={args.get('date')} time={args.get('time')} → {result[:60]}")

            elif fn_name == "schedule_callback":
                result = _handle_schedule_callback_tool(args, tc_from_phone)

            elif fn_name == "book_appointment":
                result = await _handle_book_appointment_tool(args, tc_from_phone)

            else:
                result = f"Unknown tool: {fn_name}"

            results.append({"toolCallId": call_id_t, "result": result})
        return {"results": results}

    elif kind == "status-update":
        status  = msg.get("status", "")
        call_id = msg.get("call", {}).get("id", "")
        logger.info(f"[vapi] status update — call={call_id} status={status}")
        if status == "ended" and call_id:
            asyncio.create_task(_fallback_save_if_missing(call_id))

    return {"status": "ok"}


def _transcript_to_history(transcript: str) -> list:
    """Turn a Vapi 'AI: ...\\nUser: ...' transcript into the {role, content}
    history format _check_lead_progression (built for SMS) expects."""
    history = []
    for line in (transcript or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("ai:"):
            history.append({"role": "agent", "content": line[3:].strip()})
        elif line.lower().startswith("user:"):
            history.append({"role": "user", "content": line[5:].strip()})
        elif history:
            history[-1]["content"] += " " + line
    return history


async def _fallback_save_if_missing(call_id: str, delay: float = 45.0):
    """
    Safety net for calls where Vapi's `end-of-call-report` event — the only
    thing that normally writes a voice_calls row — never arrives, even
    though the earlier `status-update: ended` event does (observed live:
    call reaches 'ended' status but no end-of-call-report ever follows,
    so the call is silently missing from CRM call history forever). Waits
    to give the normal webhook a chance first, then reconstructs the call
    straight from Vapi's REST API if nothing was saved.
    """
    await asyncio.sleep(delay)
    if not VAPI_API_KEY:
        return

    conn = get_conn(); cur = get_dict_cursor(conn)
    try:
        cur.execute("SELECT 1 FROM voice_calls WHERE call_id = %s", (call_id,))
        already_saved = cur.fetchone() is not None
    finally:
        cur.close(); conn.close()
    if already_saved:
        return

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"https://api.vapi.ai/call/{call_id}",
                headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
            )
        if not res.is_success:
            logger.warning(f"[vapi:fallback] GET /call/{call_id} failed: {res.status_code} {res.text[:200]}")
            return
        data = res.json()
    except Exception as e:
        logger.warning(f"[vapi:fallback] fetch error for {call_id}: {e}")
        return

    from_phone   = (data.get("customer") or {}).get("number", "")
    ended_reason = data.get("endedReason", "") or ""
    direction    = "inbound" if "inbound" in (data.get("type") or "").lower() else "outbound"
    summary      = data.get("summary", "") or ""
    artifact     = data.get("artifact") or {}
    recording_url = data.get("recordingUrl", "") or artifact.get("recordingUrl", "") or ""
    transcript    = data.get("transcript", "") or artifact.get("transcript", "") or ""

    duration_seconds = 0
    started_at, ended_at = data.get("startedAt"), data.get("endedAt")
    if started_at and ended_at:
        try:
            s = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            e = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            duration_seconds = int((e - s).total_seconds())
        except Exception:
            pass

    logger.info(
        f"[vapi:fallback] end-of-call-report never arrived for {call_id} — "
        f"recovered via API (reason={ended_reason} duration={duration_seconds}s)"
    )
    await _extract_and_save(call_id, from_phone, transcript, duration_seconds, ended_reason, summary, recording_url, direction, json.dumps(data))


# ── Appointment extraction from transcript ────────────────────────────────────

# Map Vapi endedReason → our outcome values
_ENDED_REASON_OUTCOME = {
    "customer-did-not-answer": "no_answer",
    "no-answer":               "no_answer",
    "voicemail":               "voicemail",
    "assistant-error":         "failed",
    "call-error":              "failed",
    "pipeline-error":          "failed",
    "error":                   "failed",
}

_NULL_LIKE_VALUES = {"", "null", "none", "n/a", "na", "unknown", "undefined"}
_EXTRACTED_OPTIONAL_FIELDS = (
    "name", "service", "doctor", "date", "time", "email", "callback_datetime",
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_extracted_fields(values: dict | None) -> dict:
    """Normalize unreliable optional strings returned by transcript extraction."""
    normalized = dict(values or {})
    for field in _EXTRACTED_OPTIONAL_FIELDS:
        value = normalized.get(field)
        if isinstance(value, str):
            value = value.strip()
            if value.lower() in _NULL_LIKE_VALUES:
                value = None
            normalized[field] = value

    # An LLM can return arbitrary prose in the email field. Treat it as absent
    # so the appointment sync can fall back to the verified lead email instead
    # of sending an invalid attendee/To header to Google.
    email = normalized.get("email")
    if email and not _EMAIL_RE.fullmatch(email):
        normalized["email"] = None
    return normalized


def _regex_callback_seconds_from_transcript(text: str) -> int | None:
    """
    Fast regex detection for 'call me back in X minutes/hours/seconds' in a voice call transcript.
    Runs before the LLM to catch callback requests deterministically.
    """
    import re
    t = text.lower()
    # Match explicit time amounts with callback intent
    patterns = [
        r'\bcall\s+(?:me\s+)?(?:back\s+)?(?:in|after)\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b',
        r'\bcontact\s+(?:me\s+)?(?:in|after)\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b',
        r'\bget\s+back\s+(?:to\s+me\s+)?(?:in|after)\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b',
        r'\bring\s+(?:me\s+)?(?:back\s+)?(?:in|after)\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b',
        r'\b(\d+)\s*(second|sec|minute|min|hour|hr)s?\s*(?:later|from now)\b',
    ]
    for pattern in patterns:
        m = re.search(pattern, t)
        if m:
            amount = int(m.group(1))
            unit   = m.group(2)
            if unit.startswith("sec"):               return amount
            if unit.startswith("min"):               return amount * 60
            if unit.startswith("hour") or unit.startswith("hr"): return amount * 3600
    return None


async def _extract_and_save(
    call_id: str,
    from_phone: str,
    transcript: str,
    duration_seconds: int = 0,
    ended_reason: str = "",
    vapi_summary: str = "",
    recording_url: str = "",
    direction: str = "inbound",
    raw_payload: str = "",
):
    parsed      = {}
    appt_id     = None
    start_time  = None
    end_time    = None

    # Determine initial outcome from ended_reason (before transcript extraction)
    initial_outcome = _ENDED_REASON_OUTCOME.get(ended_reason.lower(), None)

    # ── Step 0: regex-based callback detection (runs before the LLM) ────────────
    # Gated on not-voicemail: a voicemail "transcript" is 100% our own AI
    # monologue (it includes our scripted voicemailMessage line, e.g. "please
    # give us a call back when you get a chance") — there's no real lead
    # speech to detect a callback request from. Confirmed live: this line
    # being present verbatim in the transcript caused the LLM step below to
    # misread OUR OWN closing line as the lead requesting a callback, which
    # rescheduled another call exactly 1 hour later — and since every retry
    # hit the same voicemail and repeated the exact same line, it became an
    # infinite hourly call loop against one number (ran unbounded for 8+
    # hours before caught).
    search_text = transcript or vapi_summary or ""
    if search_text and initial_outcome not in ("voicemail", "no_answer"):
        regex_cb_seconds = _regex_callback_seconds_from_transcript(search_text)
        if regex_cb_seconds:
            try:
                import uuid as _uuid
                conn2 = get_conn(); cur2 = get_dict_cursor(conn2)
                try:
                    cur2.execute("SELECT id, business_id FROM leads WHERE phone=%s LIMIT 1",
                                 (from_phone,))
                    lead_row = cur2.fetchone()
                    if lead_row:
                        # Same call may already have scheduled this live via the
                        # schedule_callback tool — don't stack a second row.
                        cur2.execute("""
                            SELECT id FROM scheduled_callbacks
                            WHERE lead_id=%s AND callback_type='call' AND status='pending'
                        """, (lead_row["id"],))
                        if not cur2.fetchone():
                            cb_id = f"cb_{_uuid.uuid4().hex[:12]}"
                            mins = regex_cb_seconds // 60
                            label = f"{mins} minute{'s' if mins != 1 else ''}" if mins >= 1 else f"{regex_cb_seconds} seconds"
                            cur2.execute("""
                                INSERT INTO scheduled_callbacks
                                    (id, lead_id, business_id, phone, scheduled_at, call_reason, callback_type, created_at, updated_at)
                                VALUES (%s, %s, %s, %s, NOW() + make_interval(secs => %s), %s, 'call', NOW(), NOW())
                                ON CONFLICT DO NOTHING
                            """, (cb_id, lead_row["id"], lead_row["business_id"], from_phone,
                                  regex_cb_seconds, f"Lead requested callback in {label} during call"))
                            conn2.commit()
                            logger.info(f"[vapi:callback] REGEX scheduled callback {cb_id} in {label} for {from_phone}")
                finally:
                    cur2.close(); conn2.close()
            except Exception as e:
                logger.error(f"[vapi:callback] regex callback schedule failed: {e}")

    # ── Step 1: extract via OpenAI ──────────────────────────────────────────────
    if OPENAI_API_KEY and transcript:
        extract_prompt = f"""Extract appointment details from this call transcript. Return ONLY valid JSON, nothing else.
Format: {{"intent": "book|reschedule|cancel|info|callback", "name": "patient full name or null", "service": "service name or null", "doctor": "doctor name or null", "date": "YYYY-MM-DD or null", "time": "HH:MM (24hr) or null", "email": "valid email or null", "booked": true/false, "callback_seconds": null or integer, "callback_datetime": null or "YYYY-MM-DD HH:MM"}}

intent rules:
- "book" = new appointment confirmed
- "reschedule" = patient wants to change existing appointment to a new date/time
- "cancel" = patient wants to cancel appointment
- "callback" = lead said they are busy and requested a callback at a specific time
- "info" = caller only asked for information, no booking action

Callback rules (VERY IMPORTANT — always convert to seconds):
- If lead said "call me in X seconds" → set intent="callback", callback_seconds=X, callback_datetime=null
- If lead said "call me in X minutes" → set intent="callback", callback_seconds=(X * 60), callback_datetime=null
- If lead said "call me in X hours" → set intent="callback", callback_seconds=(X * 3600), callback_datetime=null
- If lead said "call me at 3 PM" or specific time/date → set intent="callback", callback_seconds=null, callback_datetime="YYYY-MM-DD HH:MM"
- If lead said "call me tomorrow morning" → set intent="callback", callback_seconds=null, callback_datetime="tomorrow date 09:00"
- If lead said "call me on Monday" → set intent="callback", callback_seconds=null, callback_datetime="next Monday date 10:00"
- Auto call decline after completion call or good bye

Email rules:
- Convert spoken email: "ali at gmail dot com" → "ali@gmail.com"
- "underscore" → "_", "dot" → ".", "dash" or "hyphen" → "-"
- If no email mentioned, return null

IMPORTANT — use ONLY these exact date mappings:
{build_date_lookup()}

Rules:
- If patient said "morning" with no exact time, use "09:00"
- If patient said "afternoon" with no exact time, use "14:00"
- If patient said "evening" with no exact time, use "17:00"
- If the patient clearly agreed to book and gave a time, but the assistant
  repeated a DIFFERENT time and the patient said "no" to correct that mistake,
  keep intent="book" and booked=true using the PATIENT'S requested time. The
  correction rejects the wrong repeated time, not the appointment itself.
- If no appointment was confirmed or rescheduled, set booked=false

Transcript:
{transcript}"""

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await post_with_retry(
                    client, "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model":       "gpt-4o-mini",
                        "messages":    [{"role": "user", "content": extract_prompt}],
                        "max_tokens":  200,
                        "temperature": 0,
                    },
                    label="vapi:extract",
                )
            raw    = res.json()["choices"][0]["message"]["content"].strip()
            raw    = raw.replace("```json", "").replace("```", "").strip()
            parsed = _normalize_extracted_fields(json.loads(raw))
        except Exception as e:
            logger.error(f"[vapi:extract] Failed to parse: {e}")

    caller_name = parsed.get("name")

    # ── Step 1b: handle callback scheduling ───────────────────────────────────
    # Same voicemail gate as Step 0 above — see comment there.
    if parsed.get("intent") == "callback" and initial_outcome not in ("voicemail", "no_answer"):
        try:
            import uuid as _uuid
            cb_seconds  = parsed.get("callback_seconds")
            cb_datetime = parsed.get("callback_datetime")
            now         = datetime.utcnow()

            if cb_seconds:
                scheduled_at = now + timedelta(seconds=int(cb_seconds))
            elif cb_datetime:
                # cb_datetime is an absolute wall-clock time the caller SPOKE
                # (e.g. "call me at 3pm", resolved against the Central-
                # anchored date lookup table in voice/prompt.py) — it means
                # Central time, but the scheduler poller compares
                # scheduled_at against Postgres's true-UTC NOW(). Storing it
                # naively used to mean a "3pm" request actually fired
                # whenever the server's UTC clock hit 3pm — 5-6 hours off
                # from when the caller actually meant.
                local_dt = datetime.strptime(cb_datetime, "%Y-%m-%d %H:%M")
                scheduled_at = local_to_utc(local_dt)
            else:
                scheduled_at = now + timedelta(hours=1)

            # Find lead by phone
            conn2 = get_conn(); cur2 = get_dict_cursor(conn2)
            try:
                cur2.execute("SELECT id, business_id FROM leads WHERE phone=%s LIMIT 1",
                             (from_phone,))
                lead_row = cur2.fetchone()
                if lead_row:
                    cb_id = f"cb_{_uuid.uuid4().hex[:12]}"
                    cur2.execute("""
                        INSERT INTO scheduled_callbacks
                            (id, lead_id, business_id, phone, scheduled_at, call_reason, callback_type, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'call', NOW(), NOW())
                        ON CONFLICT DO NOTHING
                    """, (cb_id, lead_row["id"], lead_row["business_id"], from_phone,
                          scheduled_at, "Lead requested callback during call"))
                    conn2.commit()
                    logger.info(f"[vapi:callback] LLM scheduled callback {cb_id} at {scheduled_at} for {from_phone}")
            finally:
                cur2.close(); conn2.close()
        except Exception as e:
            logger.error(f"[vapi:callback] Failed to schedule callback: {e}")

    # ── Step 2: handle booking or reschedule ─────────────────────────────────
    # Default "" (no intent), NOT "book" — parsed stays {} whenever there's no
    # transcript to extract from (e.g. every no_answer/voicemail call, which
    # is most calls in a cold-outreach batch). A "book" default here meant
    # EVERY unanswered call fell into the intent=="book" branch below and
    # fired a bogus "thanks for the call, let's lock in your appointment"
    # text — confirmed live: a lead with 4 straight no_answer calls got that
    # exact text after every single one. Step 3 below (line ~1467) already
    # uses the correct "" default for the same reason; this just matches it.
    intent    = parsed.get("intent", "")
    has_slot  = parsed.get("date") and parsed.get("time")

    # The lead may already have been booked live, mid-call, via the
    # book_appointment tool (_handle_book_appointment_tool, routed through
    # api/sms/router.py's _book_appointment — same path SMS uses). This
    # transcript-based extraction step runs unconditionally after every call
    # and would otherwise create a SECOND, duplicate appointment (plus a
    # second confirmation SMS/email) for a call that already finished
    # booking live. created_via='voice_vapi_live' is the marker set only by
    # that live tool path.
    already_booked_live = False
    try:
        _c = get_conn(); _cu = get_dict_cursor(_c)
        _cu.execute("""
            SELECT a.id, a.start_time, a.end_time FROM appointments a
            JOIN leads l ON l.id = a.lead_id
            WHERE l.phone = %s AND a.created_via = 'voice_vapi_live'
              AND a.created_at >= NOW() - INTERVAL '30 minutes'
            ORDER BY a.created_at DESC LIMIT 1
        """, (from_phone,))
        _row = _cu.fetchone()
        _cu.close(); _c.close()
        if _row:
            already_booked_live = True
            appt_id, start_time, end_time = _row["id"], _row["start_time"], _row["end_time"]
            logger.info(f"[vapi:extract] {from_phone} already booked live via tool ({appt_id}) — skipping duplicate post-call booking")
    except Exception as e:
        logger.warning(f"[vapi:extract] live-booking check failed: {e}")

    if has_slot and intent in ("book", "reschedule") and parsed.get("booked") and not already_booked_live:
        ALLOWED_HOURS = [10, 14, 16]
        try:
            raw_start = datetime.strptime(f"{parsed['date']} {parsed['time']}", "%Y-%m-%d %H:%M")
        except Exception:
            logger.error(f"[vapi:extract] Invalid date/time: {parsed.get('date')} {parsed.get('time')}")
        else:
            closest_hour = min(ALLOWED_HOURS, key=lambda h: abs(h - raw_start.hour))
            start_time   = raw_start.replace(hour=closest_hour, minute=0, second=0)
            if start_time.weekday() >= 5:
                logger.warning(f"[vapi:extract] Rejected weekend booking on {start_time.strftime('%A')}")
                return
            end_time = start_time + timedelta(hours=1)

            # Check emergency blocks before saving
            try:
                _conn = get_conn()
                _cur  = get_dict_cursor(_conn)
                _cur.execute("""
                    SELECT id FROM emergency_blocks
                    WHERE business_id = %s AND status = 'active'
                      AND start_time <= %s AND end_time >= %s
                    LIMIT 1
                """, (DEFAULT_BUSINESS_ID, start_time, end_time))
                _block = _cur.fetchone()
                _cur.close(); _conn.close()
                if _block:
                    logger.warning(f"[vapi:extract] Blocked by emergency block — not saving appointment")
                    return
            except Exception as e:
                logger.error(f"[vapi:extract] Emergency block check error: {e}")

            name_parts  = (parsed.get("name") or "Vapi Caller").split()
            first_name  = name_parts[0] if name_parts else "Vapi"
            last_name   = " ".join(name_parts[1:]) if len(name_parts) > 1 else "Caller"
            business_id = DEFAULT_BUSINESS_ID

            if intent == "reschedule":
                # ── Reschedule: update the most recent appointment for this caller ──
                try:
                    conn = get_conn()
                    cur  = get_dict_cursor(conn)
                    cur.execute("""
                        SELECT a.id, a.google_event_id, s.name AS service_name, p.name AS provider_name
                        FROM appointments a
                        JOIN users u ON u.id = a.user_id
                        LEFT JOIN services s ON s.id = a.service_id
                        LEFT JOIN providers p ON p.id = a.provider_id
                        WHERE u.phone = %s AND a.business_id = %s AND a.status IN ('pending', 'confirmed')
                        ORDER BY a.created_at DESC LIMIT 1
                    """, (from_phone, business_id))
                    existing_appt = cur.fetchone()

                    if existing_appt:
                        appt_id         = existing_appt["id"]
                        google_event_id = existing_appt["google_event_id"]
                        # Use DB service/doctor for SMS so it never shows "null"
                        if existing_appt.get("service_name"):
                            parsed["service"] = existing_appt["service_name"]
                        if existing_appt.get("provider_name"):
                            parsed["doctor"] = existing_appt["provider_name"]
                        cur.execute("""
                            UPDATE appointments
                            SET start_time=%s, end_time=%s, status='confirmed',
                                notes=%s, updated_at=NOW()
                            WHERE id=%s
                        """, (start_time, end_time,
                              f"Rescheduled via Vapi call {call_id}", appt_id))
                        conn.commit(); cur.close(); conn.close()
                        logger.info(f"[vapi:reschedule] Updated {appt_id} to {start_time}")
                        if google_event_id:
                            await update_event(google_event_id, parsed, start_time, end_time)
                    else:
                        conn.commit(); cur.close(); conn.close()
                        logger.warning(f"[vapi:reschedule] No existing appointment for {from_phone}")
                except Exception as e:
                    logger.error(f"[vapi:reschedule] DB error: {e}")
                    appt_id = None

            else:
                # ── New booking ───────────────────────────────────────────────────
                try:
                    conn = get_conn()
                    cur  = get_dict_cursor(conn)

                    cur.execute("SELECT id, role FROM users WHERE phone = %s LIMIT 1", (from_phone,))
                    existing       = cur.fetchone()
                    is_admin_staff = existing and existing["role"] in ("admin", "staff", "super_admin")

                    if existing and not is_admin_staff:
                        user_id = existing["id"]
                        if parsed.get("email"):
                            cur.execute(
                                "UPDATE users SET email=%s, updated_at=NOW() WHERE id=%s AND (email IS NULL OR email LIKE %s)",
                                (parsed["email"], user_id, f"%@vapi.call"),
                            )
                    else:
                        caller_email = parsed.get("email") or f"{from_phone.replace('+','')}@vapi.call"
                        # A caller's spoken email can already belong to a user
                        # under a different phone number (e.g. same person,
                        # different line) — the users.email unique constraint
                        # rejected the INSERT below in that case, which killed
                        # the whole booking silently and left the lead stuck
                        # on "quoted" instead of a real appointment. Reuse the
                        # existing record by email instead of failing.
                        email_match = None
                        if parsed.get("email"):
                            cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (caller_email,))
                            email_match = cur.fetchone()
                        if email_match:
                            user_id = email_match["id"]
                        else:
                            user_id = f"usr_vapi_{call_id[-8:]}"
                            cur.execute("""
                                INSERT INTO users (id, phone, first_name, last_name, email, password_hash, business_id, role, created_at, updated_at)
                                VALUES (%s, %s, %s, %s, %s, 'vapi-caller-no-login', %s, 'customer', NOW(), NOW())
                                ON CONFLICT (id) DO NOTHING
                            """, (user_id, from_phone, first_name, last_name, caller_email, business_id))

                    service_id  = None
                    provider_id = None

                    if parsed.get("service"):
                        cur.execute(
                            "SELECT id FROM services WHERE business_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
                            (business_id, f"%{parsed['service']}%"),
                        )
                        row        = cur.fetchone()
                        service_id = row["id"] if row else None

                    if parsed.get("doctor"):
                        cur.execute(
                            "SELECT id FROM providers WHERE business_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
                            (business_id, f"%{parsed['doctor']}%"),
                        )
                        row         = cur.fetchone()
                        provider_id = row["id"] if row else None

                    if not provider_id and service_id:
                        cur.execute(
                            "SELECT provider_id FROM provider_services WHERE service_id=%s AND business_id=%s LIMIT 1",
                            (service_id, business_id),
                        )
                        row         = cur.fetchone()
                        provider_id = row["provider_id"] if row else None

                    cur.execute("SELECT id FROM leads WHERE phone = %s LIMIT 1", (from_phone,))
                    lead_row = cur.fetchone()
                    lead_id  = lead_row["id"] if lead_row else None

                    appt_id = f"appt_vapi_{call_id[-8:]}"
                    cur.execute("""
                        INSERT INTO appointments (id, business_id, user_id, service_id, provider_id, start_time, end_time, status, created_via, notes, lead_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', 'voice_vapi', %s, %s, NOW(), NOW())
                        ON CONFLICT (id) DO NOTHING
                    """, (appt_id, business_id, user_id, service_id, provider_id,
                          start_time, end_time,
                          f"Client: {(parsed.get('name') or 'Unknown')}. Phone: {from_phone}. Booked via voice call.", lead_id))

                    conn.commit(); cur.close(); conn.close()
                    logger.info(f"[vapi:extract] Saved {appt_id} for {from_phone}")

                    # Move the lead out of "connected" and into its own stage —
                    # without this, whatever workflow got the lead here (e.g.
                    # Connected — Call First, Text Fallback) keeps running
                    # unaware a real appointment now exists, and can still fire
                    # its own follow-up call/text on top of a confirmed booking.
                    if lead_id:
                        try:
                            await transition_via_crm_api(lead_id, business_id, "appointment_booked",
                                                          metadata={"appointment_id": appt_id})
                        except Exception as e:
                            logger.warning(f"[vapi:extract] stage transition failed for {lead_id}: {e}")

                    try:
                        from core.admin_notify import notify_admins_appointment_booked
                        await notify_admins_appointment_booked(
                            business_id, parsed.get("name") or from_phone, start_time,
                            parsed.get("service") or "Appointment",
                        )
                    except Exception as e:
                        logger.warning(f"[vapi:extract] admin notify failed: {e}")

                except Exception as e:
                    logger.error(f"[vapi:extract] DB error: {e}")
                    appt_id = None
    elif intent == "cancel":
        # ── Cancel: mark most recent active appointment as cancelled ─────────
        try:
            conn = get_conn()
            cur  = get_dict_cursor(conn)
            cur.execute("""
                SELECT a.id, a.google_event_id
                FROM appointments a
                JOIN users u ON u.id = a.user_id
                WHERE u.phone = %s AND a.business_id = %s AND a.status IN ('pending', 'confirmed')
                ORDER BY a.created_at DESC LIMIT 1
            """, (from_phone, DEFAULT_BUSINESS_ID))
            cancel_appt = cur.fetchone()
            if cancel_appt:
                appt_id = cancel_appt["id"]
                cur.execute("""
                    UPDATE appointments SET status='cancelled', notes=%s, updated_at=NOW()
                    WHERE id=%s
                """, (f"Cancelled via Vapi call {call_id}", appt_id))
                conn.commit()
                logger.info(f"[vapi:cancel] Cancelled {appt_id} for {from_phone}")
                if cancel_appt.get("google_event_id"):
                    await delete_event(cancel_appt["google_event_id"])
            else:
                logger.warning(f"[vapi:cancel] No active appointment found for {from_phone}")
            cur.close(); conn.close()
        except Exception as e:
            logger.error(f"[vapi:cancel] DB error: {e}")
            appt_id = None
    elif intent == "book" and not already_booked_live:
        # Fallback safety net only: the call prompt now instructs the model
        # to book live via the book_appointment tool (see BOOKING ON A CALL
        # in _booking_on_call_instruction()), which already ran during the
        # call if it worked. This branch only fires when that DIDN'T happen —
        # the lead verbally agreed to book but the model never successfully
        # called the tool (e.g. never got a confirmed email). Pure prompt-only
        # enforcement without a real function-call was tried twice before and
        # failed live both times, so rather than leave the lead stranded,
        # hand off to the SMS flow (AGENT APPOINTMENT / APPOINTMENT EMAIL
        # rules), which is proven reliable on its own.
        logger.info(f"[vapi:extract] intent=book, not booked live — handing off to SMS for {from_phone}")
        try:
            conn = get_conn(); cur = get_dict_cursor(conn)
            cur.execute("SELECT id, business_id, first_name FROM leads WHERE phone=%s LIMIT 1", (from_phone,))
            lead_row = cur.fetchone()
            cur.close(); conn.close()
            if lead_row:
                first_name = lead_row.get("first_name") or ""
                time_phrase = None
                if parsed.get("time"):
                    try:
                        hh, mm = (int(x) for x in parsed["time"].split(":"))
                        time_phrase = datetime(2000, 1, 1, hh, mm).strftime("%-I:%M %p") + " today"
                    except Exception:
                        time_phrase = None

                greeting = f"Hi {first_name}, " if first_name else "Hi, "
                if time_phrase:
                    msg = (
                        f"{greeting}thanks for the call! To lock in your appointment around "
                        f"{time_phrase}, what's the best email to send the confirmation to?"
                    )
                else:
                    msg = (
                        f"{greeting}thanks for the call! To lock in your appointment, would morning, "
                        "afternoon, or evening work best, and what's the best email to send the "
                        "confirmation to?"
                    )

                from api.sms.router import _send_sms, _save_message, _get_or_create_sms_conv
                await _send_sms(from_phone, msg)
                conv_id = _get_or_create_sms_conv(lead_row["id"], lead_row["business_id"], "sms")
                _save_message(conv_id, "agent", msg)
        except Exception as e:
            logger.warning(f"[vapi:extract] booking SMS hand-off failed for {from_phone}: {e}")
    else:
        logger.info(f"[vapi:extract] intent={intent} — no action taken")

    # ── Step 3: determine final outcome ──────────────────────────────────────
    intent = parsed.get("intent", "")
    if intent == "reschedule" and appt_id:
        call_outcome = "reschedule_requested"
    elif intent == "cancel" and appt_id:
        call_outcome = "cancelled"
    elif appt_id:
        call_outcome = "confirmed"
    elif initial_outcome:
        call_outcome = initial_outcome
    elif intent == "info":
        call_outcome = None  # informational call — no DB outcome value
    elif transcript and len(transcript) > 100:
        call_outcome = None  # had a real conversation but no booking
    else:
        call_outcome = "no_answer"

    # ── Generate summary via OpenAI if not provided by Vapi ────────────────────
    ai_summary = vapi_summary or ""
    if not ai_summary and transcript and OPENAI_API_KEY and len(transcript) > 50:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await post_with_retry(
                    client, "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model":       "gpt-4o-mini",
                        "messages":    [{"role": "user", "content":
                            f"Summarize this call transcript in 1-2 sentences. Be factual and concise.\n\n{transcript[:3000]}"}],
                        "max_tokens":  120,
                        "temperature": 0,
                    },
                    label="vapi:summary",
                )
            ai_summary = res.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"[vapi:summary] OpenAI summary failed: {e}")

    # ── Sentiment classification (feeds lead scoring's AI Sentiment factor) ──
    call_sentiment = None
    if transcript and OPENAI_API_KEY and len(transcript) > 50:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await post_with_retry(
                    client, "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content":
                            "Classify the lead's overall sentiment in this call transcript as exactly one word: "
                            f"positive, neutral, or negative.\n\n{transcript[:3000]}"}],
                        "max_tokens": 5,
                        "temperature": 0,
                    },
                    label="vapi:sentiment",
                )
            word = res.json()["choices"][0]["message"]["content"].strip().lower()
            call_sentiment = word if word in ("positive", "neutral", "negative") else None
        except Exception as e:
            logger.warning(f"[vapi:sentiment] OpenAI sentiment classification failed: {e}")

    # ── Step 4: always log the call to voice_calls ────────────────────────────
    # already_progressed tracks whether _check_lead_progression below made a
    # real, transcript-read decision (declined/quoted/qualified) — step 5's
    # CRM notify must not let its own dumb "transcript exists" heuristic
    # override that. Confirmed live: a lead who declined 3 times on a real
    # call got correctly marked dead by this check, then ~30ms later got
    # silently flipped back to connected/responded by step 5's fallback,
    # because that fallback only checks transcript length, not content.
    already_progressed = False
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        vc_id = f"vc_vapi_{call_id[-8:]}"

        lead_id = None
        lead_business_id = None
        lead_full_name = None
        if from_phone:
            cur.execute("SELECT id, business_id, first_name, last_name FROM leads WHERE phone = %s LIMIT 1", (from_phone,))
            lead_row = cur.fetchone()
            if lead_row:
                lead_id = lead_row["id"]
                lead_business_id = lead_row["business_id"]
                lead_full_name = " ".join(filter(None, [lead_row.get("first_name"), lead_row.get("last_name")])).strip() or None

        cur.execute("""
            INSERT INTO voice_calls (id, call_id, appointment_id, provider, status, direction,
                                     patient_phone, caller_name, transcript, summary,
                                     duration_seconds, outcome, recording_url, raw_payload, created_at, updated_at, lead_id, sentiment)
            VALUES (%s, %s, %s, 'vapi', 'ended', %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s, %s)
            ON CONFLICT (call_id) DO UPDATE SET
                outcome          = EXCLUDED.outcome,
                transcript       = COALESCE(EXCLUDED.transcript, voice_calls.transcript),
                summary          = COALESCE(EXCLUDED.summary, voice_calls.summary),
                duration_seconds = COALESCE(EXCLUDED.duration_seconds, voice_calls.duration_seconds),
                recording_url    = COALESCE(EXCLUDED.recording_url, voice_calls.recording_url),
                raw_payload      = COALESCE(EXCLUDED.raw_payload, voice_calls.raw_payload),
                status           = 'ended',
                updated_at       = NOW(),
                lead_id          = COALESCE(EXCLUDED.lead_id, voice_calls.lead_id),
                sentiment        = COALESCE(EXCLUDED.sentiment, voice_calls.sentiment)
        """, (vc_id, call_id, appt_id, direction, from_phone, caller_name,
              transcript[:5000] if transcript else None,
              ai_summary or None,
              duration_seconds or None, call_outcome,
              recording_url or None, raw_payload or None, lead_id, call_sentiment))
        conn.commit(); cur.close(); conn.close()
        logger.info(f"[vapi:call] Logged {vc_id} outcome={call_outcome} sentiment={call_sentiment} for {from_phone}")

        if recording_url:
            from core.local_recordings import save_locally
            asyncio.create_task(save_locally(call_id, recording_url, lead_name=lead_full_name or caller_name))

        # The lead is left thinking a call is coming and it never will unless
        # someone/something tells them — and staff have zero visibility into
        # the miss otherwise. Fires on no_answer too: confirmed live that
        # Vapi's own endedReason classification is inconsistent for the exact
        # same real-world event (a full voicemail box intercepting the call)
        # — sometimes resolves as "voicemail", sometimes "no_answer". Both
        # mean the lead was not actually reached.
        #
        # Skip entirely if this call was placed by a workflow (e.g. Call-First
        # 5-Day Follow-Up) — that workflow already has its own complete,
        # purpose-built handling for a missed call (its own wait, its own
        # scripted text, its own next-call scheduling). This block predates
        # the workflow engine and was never made workflow-aware, so it was
        # firing in parallel with every workflow's own follow-up — confirmed
        # live: a lead got two different "we tried to call you" texts and
        # multiple calls from two uncoordinated systems for one missed call.
        # Checked at the LEAD level (any active/waiting workflow enrollment),
        # not by matching this specific call's scheduled_callbacks row — that
        # per-call check raced against callback_scheduler.py writing
        # vapi_call_id onto the row *after* placing the Vapi call. Confirmed
        # live: a lead's genuinely workflow-placed call still fell through
        # this gate (row not yet updated when this ran) and triggered a
        # rogue extra retry call + duplicate text anyway. Enrollment status
        # doesn't depend on any post-call-placement write, so it can't race.
        is_workflow_call = False
        if lead_id:
            wf_conn = get_conn(); wf_cur = get_dict_cursor(wf_conn)
            wf_cur.execute(
                "SELECT 1 FROM lead_workflow_enrollments WHERE lead_id = %s AND status IN ('active','waiting') LIMIT 1",
                (lead_id,),
            )
            is_workflow_call = wf_cur.fetchone() is not None
            wf_cur.close(); wf_conn.close()

        if lead_id and call_outcome in ("voicemail", "no_answer") and not is_workflow_call:
            try:
                notify_conn = get_conn()
                notify_cur = get_dict_cursor(notify_conn)
                notify_cur.execute("SELECT first_name, stage FROM leads WHERE id = %s", (lead_id,))
                lead_row = notify_cur.fetchone()
                first_name = lead_row["first_name"] if lead_row else None
                lead_stage = lead_row["stage"] if lead_row else None

                # Cap automatic retries at 3 total voicemail/no_answer calls per
                # lead — confirmed live this needed a hard limit: a code bug
                # elsewhere (now fixed separately) turned this into an
                # unbounded hourly loop that called the same number 18 times
                # in one night. Even with that bug gone, nothing here was ever
                # capping retries on purpose, so add the cap explicitly rather
                # than relying on no other bug ever re-introducing a loop.
                # After the cap, no further automatic calls or SMS go out —
                # the lead has to reply on their own before anything resumes,
                # which the normal inbound-reply flow already handles.
                #
                # Also never auto-retry once the lead has moved past needing
                # to be reached at all — they already have an appointment on
                # the books, already got a quote, or the deal's already
                # closed. Retrying there would just be pestering someone the
                # business already has what it needs from.
                notify_cur.execute(
                    "SELECT count(*) AS n FROM voice_calls WHERE lead_id = %s AND outcome IN ('voicemail','no_answer')",
                    (lead_id,),
                )
                voicemail_count = notify_cur.fetchone()["n"]
                past_needing_contact = lead_stage in ("appointment_scheduled", "quoted", "closed")
                will_retry = voicemail_count < 3 and not past_needing_contact

                task_id = f"task_{uuid.uuid4().hex[:12]}"
                if will_retry:
                    task_title = (
                        f"Call to {first_name or from_phone} hit voicemail (attempt {voicemail_count}/3) — "
                        f"one more automatic retry is scheduled in an hour."
                    )
                elif past_needing_contact:
                    task_title = (
                        f"Call to {first_name or from_phone} hit voicemail — no automatic retry since "
                        f"they're already at stage '{lead_stage}'; follow up manually if still needed."
                    )
                else:
                    task_title = (
                        f"Call to {first_name or from_phone} hit voicemail 3 times — "
                        f"they haven't been reached. No more automatic calls or texts; waiting on them to reply."
                    )
                notify_cur.execute("""
                    INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                    VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                """, (task_id, lead_id, lead_business_id or DEFAULT_BUSINESS_ID, task_title))

                if will_retry:
                    retry_cb_id = f"cb_{uuid.uuid4().hex[:12]}"
                    notify_cur.execute("""
                        INSERT INTO scheduled_callbacks
                            (id, lead_id, business_id, phone, scheduled_at, call_reason, callback_type, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW() + INTERVAL '1 hour', %s, 'call', NOW(), NOW())
                        ON CONFLICT DO NOTHING
                    """, (retry_cb_id, lead_id, lead_business_id or DEFAULT_BUSINESS_ID, from_phone,
                          f"Automatic retry after voicemail (attempt {voicemail_count + 1} of 3)"))

                notify_conn.commit(); notify_cur.close(); notify_conn.close()

                # Same "already past needing contact" reasoning as the retry
                # cap above — a lead who already has an appointment/quote/
                # closed deal doesn't need a "sorry we missed you, call us
                # back" text, that's just confusing at that point.
                if not past_needing_contact:
                    msg = (
                        f"Hi {first_name}, we just tried giving you a call but couldn't reach you. "
                        f"Feel free to reply here anytime, or let us know a good time to call back!"
                        if first_name else
                        "Hi, we just tried giving you a call but couldn't reach you. Feel free to reply "
                        "here anytime, or let us know a good time to call back!"
                    )
                    from api.sms.router import _send_sms, _save_message, _get_or_create_sms_conv
                    await _send_sms(from_phone, msg)
                    conv_id = _get_or_create_sms_conv(lead_id, lead_business_id or DEFAULT_BUSINESS_ID, "sms")
                    _save_message(conv_id, "agent", msg)
            except Exception as e:
                logger.warning(f"[vapi:call] voicemail follow-up (task/SMS) failed for lead {lead_id}: {e}")

        if lead_id:
            try:
                from core.lead_transitions import _system_jwt
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        f"{CRM_SERVICE_URL}/api/leads/{lead_id}/recompute-score",
                        headers={"Authorization": f"Bearer {_system_jwt(lead_business_id or DEFAULT_BUSINESS_ID)}"},
                    )
            except Exception as e:
                logger.warning(f"[vapi:score] recompute-score failed for lead {lead_id}: {e}")

            # Phone calls never advanced the pipeline stage (qualified/quoted/
            # declined) — that check only ever ran on SMS messages. A lead
            # could confirm coverage + budget over a full voice call and
            # still sit at 'connected' forever. Feed the call transcript
            # through the exact same progression check SMS uses so voice
            # calls qualify/quote/decline leads too.
            try:
                history = _transcript_to_history(transcript)
                if history:
                    from api.sms.router import _check_lead_progression
                    progression_result = await _check_lead_progression(
                        lead_id, lead_business_id or DEFAULT_BUSINESS_ID, from_phone, history
                    )
                    already_progressed = progression_result is not None
            except Exception as e:
                logger.warning(f"[vapi:progression] check failed for lead {lead_id}: {e}")
    except Exception as e:
        logger.error(f"[vapi:call] DB error: {e}")

    # ── Step 5: notify CRM service to log in conversations ────────────────────
    if from_phone:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{CRM_SERVICE_URL}/api/conversations/calls/update",
                    json={
                        "call_id":              call_id,
                        "outcome":              call_outcome,
                        "transcript":           transcript[:5000] if transcript else None,
                        "summary":              ai_summary or None,
                        "duration_seconds":     duration_seconds or None,
                        "patient_name":         caller_name,
                        "patient_phone":        from_phone,
                        "already_progressed":   already_progressed,
                    },
                )
            logger.info(f"[vapi:crm] Notified CRM for call {call_id}")
        except Exception as e:
            logger.warning(f"[vapi:crm] CRM notify failed: {e}")

    # ── Step 6: if this call was fired by a workflow ai_call node, report
    # the outcome back so branch_condition nodes gated on call outcome can
    # resolve — ai_call outcomes are only known here, not at dispatch time.
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        cur.execute(
            "SELECT workflow_enrollment_id, workflow_node_key, business_id FROM scheduled_callbacks "
            "WHERE vapi_call_id = %s AND workflow_enrollment_id IS NOT NULL LIMIT 1",
            (call_id,),
        )
        cb_row = cur.fetchone()
        cur.close(); conn.close()
        if cb_row:
            from core.workflow_client import advance_workflow
            await advance_workflow(
                cb_row["workflow_enrollment_id"], cb_row["business_id"], cb_row["workflow_node_key"],
                {"outcome": call_outcome, "failed": call_outcome is None},
            )
    except Exception as e:
        logger.warning(f"[vapi:workflow] advance-after-call failed for {call_id}: {e}")

    # ── Step 6: sync integrations if appointment was saved ────────────────────
    # Skipped when already_booked_live — that path (_book_appointment via the
    # book_appointment tool) already ran its own calendar sync + confirmation
    # SMS/email during the call; redoing it here would double-send both.
    if appt_id and start_time and end_time and not already_booked_live:
        # Phone callers essentially never spell out their email out loud, so
        # parsed["email"] (extracted from the live transcript) is almost
        # always empty — without this fallback, neither the calendar invite
        # nor the confirmation email below ever go out for a call-booked
        # appointment. Fall back to whatever email the lead already has on
        # file (from SMS/signup), matching the same "based on user provided
        # email" behavior already used for SMS-booked and manually-booked
        # appointments.
        calendar_parsed = _normalize_extracted_fields(parsed)
        try:
            conn = get_conn(); cur = get_dict_cursor(conn)
            cur.execute(
                "SELECT first_name, last_name, email FROM leads WHERE phone = %s LIMIT 1",
                (from_phone,),
            )
            lead_contact_row = cur.fetchone()
            cur.close(); conn.close()
            if lead_contact_row:
                stored_email = (lead_contact_row.get("email") or "").strip()
                if not calendar_parsed.get("email") and _EMAIL_RE.fullmatch(stored_email):
                    calendar_parsed["email"] = stored_email
                if not calendar_parsed.get("name"):
                    stored_name = " ".join(filter(None, (
                        lead_contact_row.get("first_name"), lead_contact_row.get("last_name"),
                    ))).strip()
                    calendar_parsed["name"] = stored_name or None
        except Exception as e:
            logger.warning(f"[vapi:appt] lead contact lookup failed for {from_phone}: {e}")

        await asyncio.gather(
            sync_appointment(appt_id, calendar_parsed, from_phone, call_id, start_time, end_time, get_conn),
            send_confirmation(from_phone, parsed),
            sync_contact_and_meeting(appt_id, from_phone, calendar_parsed, start_time, end_time),
            send_appointment_confirmation(
                calendar_parsed.get("email"), calendar_parsed.get("name") or "there",
                calendar_parsed.get("service") or "your appointment", start_time,
            ),
            return_exceptions=True,
        )

    # Step 7 (send recording link to customer) disabled per request — also
    # would have sent the bare unsigned blob URL, which the customer
    # couldn't have opened anyway since the container is private.
