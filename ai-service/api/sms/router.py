"""
Two-way SMS router — Twilio (WhatsApp) / BlueBubbles (SMS/iMessage) + OpenAI AI replies
Inbound:  webhook → find lead → AI reply → send back
Outbound: CRM triggers first SMS to a lead
"""
import os
import re
import uuid
import json
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import httpx

from core.config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER, TWILIO_WHATSAPP_FROM, OPENAI_API_KEY, GROQ_API_KEY, DEFAULT_BUSINESS_ID,
)
from core import bluebubbles, textbee
from core.lead_transitions import transition_via_crm_api, trigger_summary_generation, create_lead_from_inbound
from api.common import get_user
from core.auth_scope import get_business_id
from core.db import get_conn, get_dict_cursor as dict_cursor
from core.llm_retry import post_with_retry
from core.timezone import now_local, BUSINESS_TIMEZONE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sms")


def _llm_messages(contents, system_instruction: str = "") -> list:
    """Normalize a plain string or Gemini-style turns into OpenAI-style chat messages."""
    messages = [{"role": "system", "content": system_instruction}] if system_instruction else []
    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    else:
        for turn in contents:
            role = "assistant" if turn["role"] == "model" else "user"
            messages.append({"role": role, "content": turn["parts"][0]["text"]})
    return messages


async def _llm_generate_async(contents, system_instruction: str = "", model: str = None,
                                max_tokens: int = 200, temperature: float = 0.7, json_mode: bool = False) -> str:
    # Prefer OpenAI (and whatever model an agent was configured with) when a
    # real OPENAI_API_KEY is set; otherwise fall back to Groq's
    # OpenAI-compatible endpoint. Per-agent llm_model values are OpenAI model
    # names (e.g. "gpt-4o-mini") and aren't valid on Groq, so the Groq path
    # always uses its own known-good model rather than passing those through.
    # core.config._get() returns a "{KEY}_not_found" placeholder string (not
    # None/"") for unset env vars, so a plain truthiness check on these is
    # always True — compare against the exact placeholder instead.
    if OPENAI_API_KEY and OPENAI_API_KEY != "OPENAI_API_KEY_not_found":
        base_url = "https://api.openai.com/v1/chat/completions"
        api_key = OPENAI_API_KEY
        use_model = model or DEFAULT_LLM_MODEL
    else:
        base_url = "https://api.groq.com/openai/v1/chat/completions"
        api_key = GROQ_API_KEY
        use_model = "openai/gpt-oss-120b"
    payload = {
        "model": use_model,
        "messages": _llm_messages(contents, system_instruction),
        "max_tokens": max_tokens, "temperature": temperature,
        # Without these, the model defaults to the same safe stock openers
        # ("Got it!", "Perfect!", the same emoji) turn after turn — that
        # repetition is one of the clearest "this is a bot" tells in a text
        # thread. presence_penalty pushes it to avoid reusing tokens/phrases
        # it already used earlier in this same reply/conversation at all;
        # frequency_penalty scales that down the more a token has already
        # repeated. Values are mild on purpose — too high makes replies
        # avoid even necessary words (its own name, "insurance", etc.).
        "presence_penalty": 0.4, "frequency_penalty": 0.3,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if base_url.startswith("https://api.groq.com"):
        # gpt-oss models spend part of max_tokens on hidden chain-of-thought
        # before writing the visible reply — with a long system prompt (like
        # Riley's) that reasoning alone can exhaust the whole budget and
        # leave content empty. Capping it low leaves the budget for the
        # actual reply.
        payload["reasoning_effort"] = "low"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await post_with_retry(
            client, base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, label="sms",
        )
    return resp.json()["choices"][0]["message"]["content"].strip()

DEFAULT_AGENT_PROMPT = (
    "You are a friendly AI assistant for a business. "
    "Your job is to qualify leads, answer questions about services, "
    "and help schedule appointments. Keep replies short (under 160 chars for SMS). "
    "Be warm, professional, and helpful."
)

# CTIA/TCPA standard opt-out and resubscribe keywords (same set Twilio's own
# Advanced Opt-Out uses). Case-insensitive, exact-match on the whole body —
# a lead saying "please stop calling" mid-sentence is handled by the AI
# reply, not treated as a formal opt-out.
STOP_KEYWORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "optout", "opt-out", "opt out"}
RESUBSCRIBE_KEYWORDS = {"start", "unstop", "subscribe"}

# These conversational declines are opt-outs only when the immediately
# preceding agent message explicitly advertised "Reply NO THANKS to opt out".
# A bare "no" elsewhere in qualification (smoker, family members, etc.) must
# remain an ordinary answer and must never unsubscribe the lead.
_CONTEXTUAL_OPT_OUT_REPLIES = {
    "n", "no", "nope", "nah", "no thanks", "no thank you", "no thx", "no thanx",
    "sorry", "sorry no", "no sorry", "sorry not interested", "not interested",
    "not interested thanks", "not interested thank you", "sorry i am not interested",
    "sorry im not interested", "no i am good", "no im good", "i am good thanks",
    "im good thanks", "not at this time", "not right now", "no sorry thanks",
    "sorry no thanks", "sorry we are good", "sorry we are set",
    "please stop", "dont contact me", "do not contact me", "dont text me", "do not text me",
}

POLITE_DECLINE_REPLY = "No problem at all, completely understand! Thanks so much for letting me know. I've taken you off my list so you won't hear from me again. Wishing you all the best and take care!"
OPT_OUT_CONFIRMATION = "No problem at all, completely understand! So sorry to have bothered you. I've taken you off my list right away so you won't receive any more messages. Wishing you all the best and take care!"
RESUBSCRIBE_CONFIRMATION = "Glad to connect again! I've added you back to my list. Feel free to let me know anytime if there's anything I can help with!"


def _is_contextual_opt_out_reply(message: str, last_agent_message: str) -> bool:
    """Interpret conversational declines only in an explicit opt-out context."""
    context = (last_agent_message or "").lower()
    if "opt out" not in context or "no thanks" not in context:
        return False
    normalized = __import__("re").sub(r"[^a-z0-9\s]", "", (message or "").lower())
    normalized = " ".join(normalized.split())
    return normalized in _CONTEXTUAL_OPT_OUT_REPLIES


# ── Twilio sender ────────────────────────────────────────────────────────────

def _typing_delay_seconds(reply_text: str) -> float:
    """
    A length-scaled pause before sending a live reply, so it doesn't land
    the instant the lead's message arrives and doesn't read as typed out
    instantly either — ~30s for a short reply, up to ~110s for a long one.
    Deliberately just a number, not an awaitable — the actual sleep happens
    at each call site, inside the same try/except-protected flow as the
    send itself.

    This range is intentionally kept under check_orphaned_replies()'s
    threshold in callback_scheduler.py (bumped to 3 minutes specifically to
    leave headroom above this) — that watchdog treats a user message with no
    agent reply ROW SAVED YET (the save happens after this sleep, not
    before) past its threshold as a possible crash and auto-replays it. A
    delay reaching the watchdog's own window would make a normal, still-in-
    progress human-feel pause look identical to a crash and could double-
    send a reply. Keep both numbers in sync if either changes.
    """
    return min(110.0, max(30.0, 30.0 + len(reply_text or "") * 0.35))


async def _is_opted_out(phone: str) -> bool:
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT opted_out FROM leads WHERE phone = %s LIMIT 1", (phone,))
        row = cur.fetchone()
        return bool(row and row["opted_out"])
    finally:
        cur.close(); conn.close()


_bluebubbles_lock = asyncio.Lock()
from core.humanoid_sender import humanoid_sender, sanitize_text
from core.circuit_breaker import circuit_breaker


async def _send_sms(to: str, body: str, channel: str = "sms", force: bool = False) -> dict:
    """Sends plain SMS via BlueBubbles (iMessage/SMS) or Twilio (WhatsApp/Fallback).
    
    Humanoid-based approach:
    - Simulates human reading and typing delays based on character length.
    - Uses randomized human intervals (20-45s) between sends to prevent Apple spam bans.
    - Limits outbound sends to 20/hour to comply with Apple anti-abuse heuristics.
    - Intercepts delivery rejections with a Circuit Breaker to protect the Apple ID from ban.
    - Sanitizes text to strictly eliminate em dashes ('—') and robotic patterns.
    """
    raw_phone = to.replace("whatsapp:", "").strip()
    if not force and await _is_opted_out(raw_phone):
        logger.warning(f"[sms:compliance] blocked send to opted-out number {raw_phone}")
        raise HTTPException(status_code=403, detail="Recipient has opted out of SMS communications")

    # Sanitize content to ensure natural human phrasing without em dashes
    body = sanitize_text(body)

    if channel == "whatsapp":
        logger.warning(f"[sms:blocked] Outbound WhatsApp/Twilio blocked: strictly iMessage only per system configuration")
        raise HTTPException(status_code=400, detail="Twilio is disabled. Outbound messaging is strictly iMessage only.")

    # ── SMS / iMessage via BlueBubbles (Native SMS text relay primary) ──
    if not force:
        # Check circuit breaker safety state
        allowed, cb_reason = circuit_breaker.is_available()
        if not allowed:
            logger.warning(f"[sms:circuit_breaker] send blocked: {cb_reason}")
            raise HTTPException(status_code=503, detail=cb_reason)

        # Check velocity limit
        vel_ok, vel_reason = humanoid_sender.check_velocity_limit()
        if not vel_ok:
            logger.warning(f"[sms:velocity] {vel_reason}")
            raise HTTPException(status_code=429, detail=vel_reason)

    async with _bluebubbles_lock:
        # Enforce randomized human cadence interval between outbound messages
        await humanoid_sender.wait_inter_message_gap()

        # Simulate human typing and reading time
        await humanoid_sender.simulate_typing(body)

        try:
            sms_provider = os.getenv("SMS_GATEWAY_PROVIDER", "textbee").lower()
            if sms_provider == "textbee":
                res = await textbee.send_message(raw_phone, body)
            else:
                res = await bluebubbles.send_message(raw_phone, body)
            humanoid_sender.record_outbound_send()
            await circuit_breaker.record_success()
            return res
        except RuntimeError as e:
            err_str = str(e)
            await circuit_breaker.record_failure(err_str)
            logger.warning(f"[sms:send] SMS delivery failed for {raw_phone}: {err_str}")
            raise HTTPException(status_code=502, detail=f"SMS delivery failed: {err_str}")




def _is_within_quiet_hours(business_id: str) -> tuple[bool, str]:
    """
    Calls/texts only go out 9am-6pm US Central — approximated here using the
    business's configured Communication Rules (quiet_hours_start/end +
    timezone), which defaults to 9am-6pm America/Chicago if never set.
    Returns (allowed, reason_if_blocked).
    """
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        return True, ""
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT quiet_hours_start, quiet_hours_end, timezone FROM communication_rules WHERE business_id = %s",
            (business_id,),
        )
        row = cur.fetchone()
        start_s = row["quiet_hours_start"] if row else "09:00"
        end_s = row["quiet_hours_end"] if row else "18:00"
        tz_name = row["timezone"] if row else "America/Chicago"
    finally:
        cur.close(); conn.close()

    try:
        now = _dt.now(ZoneInfo(tz_name))
        start_h, start_m = (int(x) for x in start_s.split(":"))
        end_h, end_m = (int(x) for x in end_s.split(":"))
        now_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        if start_minutes <= now_minutes < end_minutes:
            return True, ""
        return False, f"outside allowed sending hours ({start_s}-{end_s} {tz_name})"
    except Exception as e:
        logger.warning(f"[sms:compliance] quiet-hours check failed, allowing send: {e}")
        return True, ""


# ── AI reply ─────────────────────────────────────────────────────────────────

DEFAULT_LLM_MODEL = "gpt-4o-mini"


def _get_agent_prompt(business_id: str, lead_tags: list, lead_stage: str = None) -> dict | None:
    """
    Returns {"prompt": str, "model": str} for the matched agent, or None if no
    active Lead Config rule matches this lead's tags/stage. Callers MUST treat
    None as "do not send" — no automated SMS without an explicitly assigned agent.
    """
    if not (OPENAI_API_KEY or GROQ_API_KEY):
        return None
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT lc.condition_logic, lc.conditions, a.sms_prompt, a.system_prompt, a.name, a.persona, a.llm_model
            FROM lead_configs lc
            JOIN ai_agents a ON a.id = lc.agent_id
            WHERE lc.business_id = %s AND lc.status = 'active'
            ORDER BY lc.created_at ASC
        """, (business_id,))
        for cfg in cur.fetchall():
            conditions = cfg["conditions"] or []
            logic = cfg["condition_logic"] or "any"
            matches = []
            for c in conditions:
                field = c.get("field")
                val   = c.get("value")
                if field == "tag":
                    matches.append(val in lead_tags)
                elif field == "status":
                    matches.append(lead_stage == val)
                else:
                    matches.append(False)
            hit = any(matches) if logic == "any" else (all(matches) if matches else False)
            # sms_prompt is a channel-specific override of system_prompt (see
            # crm-service/routers/sms.py's identical fallback, and how
            # call_prompt/sms_prompt are stored — this handler used to read
            # system_prompt unconditionally, silently ignoring any sms_prompt
            # ever set on an agent).
            resolved_prompt = cfg["sms_prompt"] or cfg["system_prompt"]
            if hit and resolved_prompt:
                prompt = resolved_prompt
                if cfg["persona"]:
                    prompt = f"You are {cfg['name']}. {cfg['persona']}\n\n{prompt}"
                prompt += "\n\nCRITICAL FORMATTING RULE: NEVER use em dashes ('—'), en dashes ('–'), or double hyphens ('--') anywhere in your replies. Real humans texting on an iPhone never use em dashes. Use natural punctuation like commas, periods, or single hyphens instead."
                prompt += "\n\nIMPORTANT: Keep replies concise for SMS/iMessage, 1-3 short sentences, or a brief list of up to 4 options when presenting choices. No long paragraphs."
                prompt += (
                    "\n\nTONE: This is a strict, non-negotiable requirement for EVERY single "
                    "reply in this conversation, from the first message to the last, not just "
                    "the greeting: write like a warm, genuine, sweet person texting a friend, "
                    "never a customer-service script. Avoid stiff, formal openers (\"Hello, good "
                    "day! I received your request...\"): greet the way a friendly human "
                    "actually would. Use contractions (I'll, that's, you're). Vary sentence "
                    "length: a short sentence for a quick reaction, a slightly longer one when "
                    "explaining something, never several same-length sentences in a row. Match "
                    "your energy to theirs: softer and reassuring if they sound unsure or "
                    "frustrated, warmer and more upbeat if they're excited, calm and confident "
                    "when confirming details. Sprinkle in genuine warmth throughout, not just "
                    "the opener: little human touches like \"totally get it\", \"no worries at "
                    "all\", \"sounds great!\", \"happy to help with that\" woven naturally into "
                    "replies, not just once at the start and then dropped. Never sound scripted, "
                    "salesy, or robotic, at any point in the conversation, even deep into a long "
                    "back-and-forth. When you need to ask which option applies (coverage type, "
                    "appointment time, etc.), don't just dump a bare comma-separated list like a "
                    "form field (\"auto, home, life, health, or business?\"): frame it as a real "
                    "question a person would ask, e.g. \"What kind of coverage are you after, "
                    "car, home, that kind of thing?\" or \"Are we talking auto, home, or "
                    "something else?\". Keep it brief, just make it sound asked, not listed. "
                    "Use a light emoji naturally in most replies (😊 🙂 👍 🎉 ✅): one is usually "
                    "enough, placed where a person would actually put it (end of a warm line, "
                    "after good news), never more than one per message and never forced into a "
                    "sentence where it doesn't fit. Skip it entirely for serious moments (a "
                    "claim, a complaint, bad news, cancellations): an emoji there would read as "
                    "tone-deaf, not friendly."
                )
                prompt += (
                    "\n\nEMOTIONAL INTELLIGENCE: Before writing your reply, silently read the "
                    "emotional undertone in the lead's latest message — never name the emotion or "
                    "say you noticed it, just let it shape your wording, the way a perceptive "
                    "person naturally would. This is about genuine, in-the-moment word choice, not "
                    "a script — never build your reaction from a fixed phrase you've used before in "
                    "this conversation. If you notice yourself about to write the same acknowledgment "
                    "you already used a few messages ago, stop and find a different, fresher way to "
                    "say it instead — a real person never sounds like they're reading from a card:\n"
                    "- Relief / gratitude (\"finally\", \"so relieved\", \"thank god\") → let a little "
                    "genuine warmth land before moving on, don't just answer the next question and "
                    "skip past it.\n"
                    "- Excitement (\"can't wait\", exclamation points, all-caps enthusiasm) → match "
                    "the energy, a bit more upbeat and brisk.\n"
                    "- Nervousness / uncertainty (\"not sure\", \"never done this before\", \"is this "
                    "going to be expensive\") → slow down, extra reassuring, plain language, no "
                    "jargon, no pressure.\n"
                    "- Frustration / impatience (curt replies, \"still waiting\", \"I already told "
                    "you that\") → one brief, genuine acknowledgment without over-apologizing, then "
                    "get straight to resolving it — don't grovel.\n"
                    "- Sad or serious context (a claim, an accident, a loss, a cancellation) → gentle, "
                    "no emoji, no forced positivity.\n"
                    "- Dry humor / sarcasm → a light, knowing reaction — don't take it literally, "
                    "don't get defensive, don't over-explain.\n"
                    "- Casual / joking tone from them (lowercase, \"haha\", their own emojis) → mirror "
                    "it a little, stay relaxed and informal.\n"
                    "- Confident / decisive (\"let's do it\", \"sounds good\") → a brief, confident "
                    "confirmation, no unnecessary hedging or re-explaining.\n"
                    "If nothing stands out, default to warm-neutral.\n"
                    "WORD CHOICE: this is where most of the humanity actually lives — a real texter "
                    "reacts out loud before answering, with small, imperfect, in-the-moment words: "
                    "\"hmm\", \"oh\", \"ahh\", \"aw\", \"wait\", \"okay so\", \"honestly\", \"oof\", "
                    "\"yeah\", \"nice\", trailing off with \"...\" when thinking. These are inspiration "
                    "for the FEELING, not a list to draw from verbatim — invent your own phrasing "
                    "every time, vary it constantly, and use it sparingly (most replies need none of "
                    "this at all, just natural sentence rhythm) — sprinkled into 1 in maybe 3-4 "
                    "replies is plenty. The instant it starts to feel like a pattern or a template "
                    "being filled in, it has failed at the one thing it's for.\n"
                    "Also avoid formally restating what they just told you before moving on (e.g. "
                    "\"So, just to confirm, you're looking for coverage for a 2021 Toyota Camry in San "
                    "Diego\") — that reads like a form summarizing its own fields back at someone. A "
                    "person doesn't recap; they just react to the new thing and move forward "
                    "(\"A Camry, nice — got it\") or skip straight to the next question."
                )
                stored_model = (cfg.get("llm_model") or "").strip()
                # Stale rows from before a provider migration (Gemini→Groq, then
                # Groq→OpenAI) may still have an old gemini-*/llama-* model name
                # saved that the current provider can't serve — fall back.
                model = stored_model if stored_model and not (
                    stored_model.startswith("gemini") or stored_model.startswith("llama")
                ) else DEFAULT_LLM_MODEL
                return {"prompt": prompt, "model": model, "name": cfg["name"]}

        # Fallback to the business's active agent (e.g. Alex / AllZone)
        cur.execute("""
            SELECT a.sms_prompt, a.system_prompt, a.name, a.persona, a.llm_model
            FROM ai_agents a
            WHERE a.business_id = %s
            ORDER BY (a.name IN ('Alex', 'AllZone', 'Troy')) DESC, (a.status = 'active') DESC, a.created_at ASC
            LIMIT 1
        """, (business_id,))
        fallback = cur.fetchone()
        if fallback:
            resolved_prompt = fallback["sms_prompt"] or fallback["system_prompt"]
            if resolved_prompt:
                prompt = resolved_prompt
                if fallback["persona"]:
                    prompt = f"You are {fallback['name']}. {fallback['persona']}\n\n{prompt}"
                prompt += "\n\nIMPORTANT: Keep replies concise for SMS/iMessage, 1-3 short sentences. No long paragraphs."
                prompt += (
                    "\n\nTONE: Write like a warm, genuine, sweet person texting a friend, "
                    "never a customer-service script. Avoid stiff, formal openers. Use contractions."
                )
                stored_model = (fallback.get("llm_model") or "").strip()
                model = stored_model if stored_model and not (
                    stored_model.startswith("gemini") or stored_model.startswith("llama")
                ) else DEFAULT_LLM_MODEL
                return {"prompt": prompt, "model": model, "name": fallback["name"]}
    finally:
        cur.close(); conn.close()
    return None


async def _build_ai_reply(system_prompt: str, history: list, new_message: str, model: str = DEFAULT_LLM_MODEL) -> str:
    if not (OPENAI_API_KEY or GROQ_API_KEY):
        return "Thanks for your message! Our team will get back to you shortly."
    contents = []
    for msg in history[-20:]:
        role = "model" if msg["role"] in ("agent", "assistant") else "user"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": new_message}]})
    try:
        # Must be the async client — this runs inline in the request-handling
        # coroutine, and a blocking httpx.post() here freezes the whole
        # single-threaded event loop (every other lead's message, the 30s
        # callback poller, everything) for as long as OpenAI takes to respond,
        # which is exactly what was causing reply lag that compounded under
        # any concurrent load.
        return await _llm_generate_async(contents, system_instruction=system_prompt, model=model,
                                           max_tokens=220, temperature=0.4)
    except Exception as e:
        logger.error(f"[sms] OpenAI error: {e}")
        return "Thanks for your message! We'll be in touch soon."


# ── SMS Appointment Extraction ────────────────────────────────────────────────

BOOKING_KEYWORDS = {"monday","tuesday","wednesday","thursday","friday","saturday","sunday",
                    "book","appointment","schedule","confirm","10am","2pm","4pm","10 am",
                    "tomorrow","today","next week","morning","afternoon","evening"}

# Once a lead's SMS history passes this many messages, the live reply switches
# from resending the full raw history to a condensed ai_summary + just the
# last _LONG_CONVO_TAIL messages — see the elif branch in _handle_inbound_message.
_LONG_CONVO_THRESHOLD = 20
_LONG_CONVO_TAIL = 10

# Deterministic backstop for _check_sms_appointment — booked=true must never
# be trusted from the model alone unless a real time-like token actually
# appears in the conversation. See the "IMPORTANT: found via live demo" note
# at that call site for the transcript this caught.
_TIME_REFERENCE_RE = __import__("re").compile(
    r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
    r'today|tomorrow|tonight|next week|'
    r'morning|afternoon|evening|noon|midnight|first thing|end of day|'
    r'\d{1,2}(:\d{2})?\s*(am|pm)|\d{1,2}\s*(o\'?clock)|\d{1,2}:\d{2})\b',
    __import__("re").IGNORECASE,
)

# Creating a calendar event is deliberately stricter than merely recognizing
# that the lead mentioned a time.  The message immediately before the lead's
# approval must show one exact proposed slot AND the invite email, and must ask
# the lead to confirm them.  This keeps replies such as "Morning" in the
# proposal phase instead of silently turning them into a 9 AM booking.
_EXACT_CLOCK_TIME_RE = __import__("re").compile(
    r"\b(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
    __import__("re").IGNORECASE,
)
_EMAIL_ADDRESS_RE = __import__("re").compile(
    r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", __import__("re").IGNORECASE
)
# The prompt explicitly, repeatedly instructs the model to always spell out
# the literal email address rather than say "on file" — and it still drifts
# into vague phrasing anyway (confirmed live, two different ways in one
# session: "your email at the address we have on file", then separately
# "your email at this number"). Enumerating each new vague phrase as it's
# found is a losing game — trying to pattern-match WHICH email the agent
# means is the wrong layer to fix this at. The actual email used to book
# always comes from the lead's DB record downstream in _book_appointment
# regardless of what this sentence says (an extracted literal address only
# ever overrides that when one is actually present) — so this gate only
# needs to confirm an email was referenced AT ALL, not parse which one.
_EMAIL_MENTION_RE = __import__("re").compile(r"\bemail\b", __import__("re").IGNORECASE)
_CONFIRMATION_REQUEST_RE = __import__("re").compile(
    r"(?:please\s+confirm|confirm\s+(?:that|this|both|your)|does\s+(?:that|this)|"
    r"is\s+(?:that|this|the\s+email)|do\s+(?:that|these)|okay\s+to\s+book|"
    r"shall\s+i\s+book|should\s+i\s+book|reply\s+yes|"
    # Loosened so a warmer, less form-like way of asking still counts — this
    # is ANDed with an exact clock time AND an email reference already
    # having to be present, so the false-positive risk of a plain "sound"/
    # "work for you" showing up here for an unrelated reason is low.
    # "confirm your ___" and a bare "correct?"/"right?" tag question cover
    # natural phrasings the model reaches for once it's not being pushed
    # toward one template — confirmed live: "Can you confirm your email is
    # x@y.com for the invite?" fell through every branch above and let the
    # bot tell the lead "you're all set" while nothing was ever booked.
    r"works?\s+for\s+you|good\s+for\s+you|\bsound\b|\bcorrect\??\b|\bright\?)",
    __import__("re").IGNORECASE,
)


async def _message_asks_for_confirmation(text: str) -> bool:
    """
    Whether `text` asks the customer to confirm/approve something (as opposed
    to just stating information). A fixed phrase whitelist for this kept
    breaking live as the reply wording got more natural/varied — "Can I use
    this email: x@y.com for the invite?" is a real example that slipped
    through every pattern in _CONFIRMATION_REQUEST_RE below. Regex stays for
    the parts that are genuinely fixed-format (a clock time, an email
    address) since those can't be phrased infinite ways; this one part is
    open-ended natural language, so it gets the part of the system built to
    understand that, not pattern-match it — same reasoning already applied
    to judging the lead's own reply, just extended to the agent's message.
    Cheap and fast on purpose: single word answer, tiny token budget.
    """
    try:
        answer = await _llm_generate_async(
            f'Message: "{text}"\n\nDoes this message ask the reader to confirm, '
            f"approve, or verify something (a time, an email, a detail) is "
            f"correct — as opposed to just stating information with no ask? "
            f'Answer with exactly one word: "yes" or "no".',
            model="gpt-4o-mini", max_tokens=5, temperature=0,
        )
        return answer.strip().lower().startswith("y")
    except Exception as e:
        logger.warning(f"[sms:appt] confirmation-intent check failed, defaulting to no: {e}")
        return False


async def _has_explicit_slot_and_email_approval(history: list) -> bool:
    """
    Return True whenever the bot's own last message actually proposed one
    exact slot + the literal invite email and asked for confirmation.

    This deliberately does NOT try to guess whether the lead's reply "means
    yes" via a keyword list — that approach broke 3 separate times live
    ("Yup this is mine" wasn't recognized because only "yep"/"yeah"/"yes"
    were listed; missing-day and "email on file" wording were two earlier,
    related failures), because real conversation always has one more casual
    phrasing than any fixed word list anticipates, and the bot's own next
    reply would confidently claim "booked!" regardless of whether the gate
    below actually let the booking happen. Whether the lead's reply is really
    an approval, a correction, or something else entirely is judged by the
    LLM extraction call in _check_sms_appointment right after this — that's
    the part of the system built to understand language, not pattern-match
    it, and it already has its own safeguard (an actual time-like token must
    exist somewhere in the transcript) against inventing a booking that was
    never really confirmed. This function's only job is the objective,
    checkable-without-guessing part: did OUR message actually lay out a real
    slot + email and ask for confirmation, at all.
    """
    latest_lead_index = next(
        (i for i in range(len(history) - 1, -1, -1)
         if history[i].get("role") not in ("agent", "assistant")),
        None,
    )
    if latest_lead_index is None:
        return False

    latest_lead = (history[latest_lead_index].get("content") or "").strip()
    previous_agent = next(
        ((history[i].get("content") or "").strip()
         for i in range(latest_lead_index - 1, -1, -1)
         if history[i].get("role") in ("agent", "assistant")),
        "",
    )

    if not latest_lead or not previous_agent:
        return False

    has_slot_and_email = bool(
        _EXACT_CLOCK_TIME_RE.search(previous_agent)
        and (_EMAIL_ADDRESS_RE.search(previous_agent) or _EMAIL_MENTION_RE.search(previous_agent))
    )
    if not has_slot_and_email:
        return False

    # Fast path: the regex already covers most real phrasings, so only fall
    # back to the LLM call (extra latency + cost) when it doesn't match —
    # most turns never need it.
    if _CONFIRMATION_REQUEST_RE.search(previous_agent):
        return True
    return await _message_asks_for_confirmation(previous_agent)


def _next_five_minute_start(requested: datetime, occupied_starts: list[datetime]) -> datetime:
    """Return requested, or the first unoccupied start in five-minute steps."""
    occupied = {
        (value.year, value.month, value.day, value.hour, value.minute)
        for value in occupied_starts
    }
    candidate = requested
    # A full day contains 288 five-minute positions. The bound prevents bad
    # database data from ever creating an unbounded loop.
    for _ in range(288):
        key = (candidate.year, candidate.month, candidate.day, candidate.hour, candidate.minute)
        if key not in occupied:
            return candidate
        candidate += timedelta(minutes=5)
    return candidate

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}


def _resolve_day_reference(ref: str | None, anchor: datetime) -> str | None:
    """
    Deterministically resolves a customer's own words for a day ("thursday",
    "tomorrow", "today", or an explicit date) into YYYY-MM-DD, anchored to
    `anchor` (the moment the conversation is being processed). Weekday names
    resolve to the next occurrence from anchor, 0-6 days out — if today IS
    that weekday, it means today, matching how people actually use the word.
    """
    if not ref:
        return None
    ref = ref.strip().lower().removeprefix("next ").strip()

    # Strip a leading "weekday," prefix (e.g. "thursday, aug 20") — the
    # extraction model can copy this compound format straight from the
    # agent's own message when a requested slot was taken and it proposed
    # the next opening (_book_appointment's conflict path formats that as
    # "%A, %b %d", e.g. "Thursday, Aug 20"). Confirmed live: that exact
    # phrase came back as day_reference and matched nothing below, silently
    # returning None — the bot told the customer "Awesome! I've got you
    # scheduled" while no appointment was ever created. The trailing
    # month/day is the authoritative, unambiguous part; the weekday name is
    # redundant and safe to drop before the checks below run.
    ref = re.sub(
        r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,\s*", "", ref
    )

    try:
        return datetime.strptime(ref, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass

    if ref == "today":
        return anchor.strftime("%Y-%m-%d")
    if ref == "tomorrow":
        return (anchor + timedelta(days=1)).strftime("%Y-%m-%d")
    # "day after tomorrow" (and "the day after tomorrow") is an extremely
    # common way to refer to +2 days — confirmed live: it silently fell
    # through every case here to the unparseable-date fallback below and
    # returned None, so the bot dodged naming an actual date at all
    # ("how about 9:00 AM on that day?") rather than risk stating a wrong
    # one — better than a wrong date, but the booking gate then has no real
    # date to work with either, so nothing actually gets booked.
    if ref in ("day after tomorrow", "the day after tomorrow"):
        return (anchor + timedelta(days=2)).strftime("%Y-%m-%d")
    # Casual texting spells small numbers out ("in two days") about as often
    # as digits ("in 2 days") — the day_reference extraction copies whatever
    # the customer actually typed, so both forms need to resolve here.
    _WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
    n_pattern = r"(\d+|" + "|".join(_WORD_NUMBERS) + r")"
    in_n_days = (
        re.match(rf"^in\s+{n_pattern}\s+days?$", ref)
        or re.match(rf"^{n_pattern}\s+days?\s+from\s+now$", ref)
    )
    if in_n_days:
        raw = in_n_days.group(1)
        n = int(raw) if raw.isdigit() else _WORD_NUMBERS[raw]
        return (anchor + timedelta(days=n)).strftime("%Y-%m-%d")
    if ref in _WEEKDAYS:
        days_ahead = (_WEEKDAYS[ref] - anchor.weekday()) % 7
        return (anchor + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # A spoken calendar date without a year ("15 august", "august 15th",
    # "aug 15") — not covered by any case above. Confirmed live: a customer
    # said "15 august ... 3pm", the extraction model correctly copied that
    # as day_reference (per this function's own docstring, it isn't allowed
    # to convert it itself), but this function had no format for it and
    # silently returned None — which then fell into the bare-time fallback
    # below (meant only for "just a time, no day mentioned at all") and
    # wrongly defaulted to TODAY. The AI told the customer they were booked
    # on the date they asked for while the app recorded a different one
    # entirely, and the customer caught the mismatch after the fact.
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", ref)
    for fmt in ("%d %B", "%B %d", "%d %b", "%b %d"):
        try:
            parsed_md = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        try:
            candidate = anchor.replace(month=parsed_md.month, day=parsed_md.day,
                                        hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue
        if candidate.date() < anchor.date():
            candidate = candidate.replace(year=anchor.year + 1)
        return candidate.strftime("%Y-%m-%d")

    return None


async def _check_sms_appointment(conv_id: str, lead_id: str, business_id: str,
                                  from_phone: str, history: list) -> bool:
    """
    After each SMS, check if conversation has a confirmed appointment and save
    it. Returns True whenever a booking was actually engaged this turn (booked,
    or declined for a slot conflict) — callers use this to skip other
    "someone needs to follow up" triggers (see _check_call_confirmation) that
    would otherwise redundantly fire on top of an appointment that already
    covers the same need.
    """
    try:
        # Only run if booking keywords found in last few messages
        recent_text = " ".join(m["content"].lower() for m in history[-6:])
        if not any(kw in recent_text for kw in BOOKING_KEYWORDS):
            return False

        # Hard safety gate: the bot's newly generated response is appended
        # after the latest lead turn, so inspect the agent message immediately
        # BEFORE that lead turn.  A broad preference such as "Morning" cannot
        # pass; neither can an exact time supplied for the first time by the
        # lead.  The system must first echo one exact day/time and the literal
        # invite email, ask for approval, then wait for the next lead reply.
        if not await _has_explicit_slot_and_email_approval(history):
            logger.info(
                f"[sms:appt] waiting for explicit slot + email approval before booking lead={lead_id}"
            )
            return False

        # Check if appointment already saved for this conversation
        conn = get_conn()
        cur  = dict_cursor(conn)
        cur.execute(
            "SELECT id FROM appointments WHERE notes LIKE %s LIMIT 1",
            (f"%sms_conv:{conv_id}%",)
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return False

        # Build conversation text for extraction
        chat = "\n".join(
            f"{'Agent' if m['role'] in ('agent','assistant') else 'Customer'}: {m['content']}"
            for m in history
        )

        # LLMs are unreliable at day-of-week arithmetic even when told the
        # current date — asking one for a final YYYY-MM-DD when the customer
        # said "Thursday" has produced wrong dates in practice. So the model
        # only extracts the RAW reference (e.g. "thursday", "tomorrow",
        # "2026-07-09") and Python resolves it deterministically below.
        # Anchored on the business's local time (Central), not server UTC —
        # a customer texting "tomorrow" at 8pm Central (2am UTC) means the
        # calendar day that starts in a few hours their time, not UTC's.
        today = now_local()
        extract_prompt = f"""Extract appointment details from this SMS conversation. Return ONLY valid JSON.
Format: {{"intent": "book|cancel|info", "day_reference": "the customer's own words for the day, e.g. 'thursday', 'tomorrow', 'today', or an explicit date, or null", "time": "HH:MM (24hr) or null", "service": "service name or null", "booked": true/false, "email": "an email address the customer typed or explicitly confirmed anywhere in this conversation, or null if none was mentioned"}}

Rules:
- day_reference must be copied from what the customer actually said (a weekday name, 'today',
  'tomorrow', or an explicit date) — do NOT calculate or convert it to a calendar date yourself.
- A vague time-of-day answer may be mapped to a representative clock time only after the agent
  has proposed that exact clock time and invite email and the customer has explicitly approved
  both on the following turn. "Morning" by itself is a preference, not a confirmed booking.
- booked=true ONLY if an actual time reference — an exact clock time ("9am", "2:30") or one of
  the vague time-of-day phrases above (morning, afternoon, evening, first thing, end of day) —
  appears SOMEWHERE in the exchange being confirmed: either the customer said it themselves, or
  the agent proposed that specific time/day and the customer agreed to THAT proposal. A plain
  "yes" agreeing to a question that itself contains no day/time ("would you like us to review
  your options?", "sound good?", "want to move forward?") is NOT a booking, no matter how
  enthusiastic — there is nothing to book yet. Never invent or guess a time nobody mentioned.
- Example — NOT booked: Agent: "Would you like us to review your options?" Customer: "Yes
  please, that sounds good" → {{"intent": "info", "day_reference": null, "time": null,
  "booked": false}} (the agent's question has no day/time in it, so "yes" confirms nothing
  bookable — do not default to a time).
- Example — booked: Agent: "I can offer tomorrow at 9:00 AM and send the invite to a@b.com.
  Please confirm that both are correct." Customer: "Yes, that works" →
  {{"intent": "book", "day_reference": "tomorrow", "time": "09:00", "booked": true}}.
- If no time was confirmed at all, set booked=false and time=null.

Conversation:
{chat}"""

        if not (OPENAI_API_KEY or GROQ_API_KEY):
            cur.close(); conn.close()
            return False

        # The fast default model previously used here (under the prior LLM
        # provider) fabricated a booking — "Sunday 9:00 AM" — out of a real
        # 5-turn insurance qualification conversation that contained no time
        # reference anywhere, despite the prompt's explicit rules and examples
        # telling it not to. Same model-capability gap already found for the
        # decline/qualified/quoted judgment in _check_lead_progression (the
        # small/fast model got it wrong repeatedly, the larger model got it
        # right) — booking a real appointment and telling the customer "Confirmed!" for
        # something they never actually booked is too consequential a
        # mistake to leave on the smaller model.
        text = await _llm_generate_async(extract_prompt, model="gpt-4o",
                                           max_tokens=200, temperature=0, json_mode=True)
        parsed = json.loads(text)

        # The model sometimes returns a list of candidate extractions (one per
        # intent it noticed across the conversation) instead of a single
        # object — pick the one that's actually a confirmed booking, if any.
        if isinstance(parsed, list):
            parsed = next((p for p in parsed if isinstance(p, dict) and p.get("booked")), {})

        # Deterministic backstop, independent of the model's own compliance —
        # booked=true requires an actual time-like token to be present
        # SOMEWHERE in the real conversation text (not just claimed by the
        # model). A hallucinated day_reference/time with nothing in the
        # transcript to back it up gets overridden to not-booked here,
        # regardless of what the model returned. Cheap insurance against
        # exactly the failure above, on the highest-stakes of these
        # classifiers (it creates a real calendar event and tells the
        # customer "Confirmed!").
        if parsed.get("booked") and not _TIME_REFERENCE_RE.search(chat):
            logger.warning(
                f"[sms:appt] model returned booked=true (day={parsed.get('day_reference')!r} "
                f"time={parsed.get('time')!r}) but no time-like reference exists anywhere in the "
                f"transcript — overriding to not-booked. lead={lead_id}"
            )
            parsed["booked"] = False

        resolved_date = _resolve_day_reference(parsed.get("day_reference"), today)

        # A customer who confirms only a TIME ("morning 9am") with no day is
        # implicitly talking about the next occurrence of that time — not
        # something to silently drop. Default to today, or tomorrow if that
        # time has already passed today. Without this, the bot's spoken
        # confirmation ("I've scheduled you for 9am") was a lie: nothing
        # actually got booked because resolved_date came back None.
        #
        # Gated on day_reference being EMPTY, not just on resolved_date being
        # None — confirmed live: a customer said "15 august ... 3pm" (a real
        # day_reference, just one _resolve_day_reference didn't yet parse),
        # and this fallback swallowed that failure by silently booking TODAY
        # instead. This fallback exists for "no day mentioned at all"; an
        # unparseable day the customer DID give is a bug to fix in
        # _resolve_day_reference, never something to guess through here.
        if parsed.get("booked") and not resolved_date and parsed.get("time") and not parsed.get("day_reference"):
            try:
                candidate = datetime.strptime(f"{today.strftime('%Y-%m-%d')} {parsed['time']}", "%Y-%m-%d %H:%M")
                if candidate <= today:
                    candidate += timedelta(days=1)
                resolved_date = candidate.strftime("%Y-%m-%d")
            except ValueError:
                pass

        if not parsed.get("booked") or not resolved_date or not parsed.get("time"):
            cur.close(); conn.close()
            return False

        cur.close(); conn.close()

        # Parse date/time
        start_time = datetime.strptime(f"{resolved_date} {parsed['time']}", "%Y-%m-%d %H:%M")
        end_time   = start_time + timedelta(hours=1)

        await _book_appointment(lead_id, business_id, from_phone, conv_id, start_time, end_time,
                                 extracted_email=parsed.get("email"), service_hint=parsed.get("service"))
        return True

    except Exception as e:
        logger.error(f"[sms:appt] Error: {e}")
        return False


async def _book_appointment(lead_id: str, business_id: str, from_phone: str, conv_id: str | None,
                             start_time: datetime, end_time: datetime,
                             extracted_email: str | None = None, service_hint: str | None = None,
                             created_via: str = "sms"):
    """
    Shared appointment-creation path: availability check, appointments row,
    Google Calendar sync (real invite if a real email is on file), stage
    transition to appointment_scheduled, confirmation email + SMS.

    Used by _check_sms_appointment (an explicit day/time confirmed in the SMS
    conversation) AND by _check_call_confirmation (the lead agreed to a call/
    appointment with a licensed agent) — that scheduled call slot IS the
    appointment from the business's side, even though the lead never named a
    specific day/time themselves. Before this was shared, the "book an
    appointment with a licensed agent" flow only ever scheduled the call
    itself: the lead stayed stuck at stage=connected, no appointments row
    existed, and no calendar invite/confirmation email ever went out —
    confirmed live, a lead who explicitly agreed to book never got any of
    that even though the bot told her "I'm setting up the appointment now."
    """
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        # If one or more appointments already start at the requested time,
        # advance in five-minute increments (9:00 -> 9:05 -> 9:10). We still
        # preserve the explicit-approval handshake: propose the adjusted slot
        # and wait for the lead's next approval rather than silently booking a
        # time different from the one they approved.
        day_start = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        cur.execute("""
            SELECT start_time FROM appointments
            WHERE business_id = %s AND status IN ('confirmed', 'pending')
              AND start_time >= %s AND start_time < %s
            ORDER BY start_time
        """, (business_id, day_start, day_end))
        occupied_starts = [row["start_time"] for row in cur.fetchall()]
        adjusted_start = _next_five_minute_start(start_time, occupied_starts)
        if adjusted_start != start_time:
            cur.execute(
                "SELECT email FROM leads WHERE id = %s OR phone = %s ORDER BY (id = %s) DESC LIMIT 1",
                (lead_id, from_phone, lead_id),
            )
            email_row = cur.fetchone()
            invite_email = (extracted_email or "").strip()
            if not _EMAIL_ADDRESS_RE.fullmatch(invite_email):
                invite_email = ((email_row or {}).get("email") or "").strip()

            cur.close(); conn.close()
            logger.info(
                f"[sms:appt] requested start {start_time} occupied for business={business_id}; "
                f"proposing next five-minute start {adjusted_start} to lead={lead_id}"
            )
            if _EMAIL_ADDRESS_RE.fullmatch(invite_email):
                adjusted_msg = (
                    f"Ah, that time just got taken! Next opening is "
                    f"{adjusted_start.strftime('%A, %b %d at %I:%M %p')} — I'll send the invite "
                    f"to {invite_email}, does that work?"
                )
            else:
                adjusted_msg = (
                    f"Ah, that time just got taken! Next opening is "
                    f"{adjusted_start.strftime('%A, %b %d at %I:%M %p')}. "
                    "What's the best email for the invite?"
                )
            await asyncio.sleep(_typing_delay_seconds(adjusted_msg))
            await _send_sms(from_phone, adjusted_msg)
            if conv_id:
                _save_message(conv_id, "agent", adjusted_msg)
            return

        # Get or create user from phone — use lead's name if available
        cur.execute("""
            SELECT u.id, l.first_name, l.last_name, l.email, l.tags
            FROM leads l
            LEFT JOIN users u ON u.phone = l.phone
            WHERE l.phone = %s
            LIMIT 1
        """, (from_phone,))
        lead_row = cur.fetchone()

        # The lead's own name/email (from the leads table) is always the real
        # data to use here — whether or not a matching `users` row exists is
        # a separate question (users is for portal-login accounts; most SMS
        # leads never get one). Gating name/email on that JOIN, as this used
        # to, silently threw away the lead's real email in favor of a fake
        # "usr_sms@sms.lead" placeholder whenever no users row existed —
        # which meant the calendar invite + confirmation email almost never
        # reached the lead's actual on-file address.
        lead_tags   = (lead_row["tags"]      if lead_row else None) or []
        first_name  = (lead_row["first_name"] if lead_row else None) or "Client"
        last_name   = (lead_row["last_name"]  if lead_row else None) or ""
        placeholder = f"{from_phone.replace('+','')}@sms.lead"
        lead_email  = (lead_row["email"] if lead_row else None) or placeholder

        # A real, human-provided/confirmed email from THIS conversation always
        # wins over whatever's already on file — it's either a correction to a
        # stale record, or the answer to the AGENT APPOINTMENT/APPOINTMENT
        # EMAIL guardrail asking for one because none was on file at all.
        # Without this, that guardrail could ask the question and get a real
        # answer, and the booking would still silently ignore it.
        extracted_email = (extracted_email or "").strip()
        email_was_corrected = False
        if extracted_email and "@" in extracted_email and extracted_email != lead_email:
            lead_email = extracted_email
            email_was_corrected = True

        # Keep the CRM record aligned with the address the lead explicitly
        # approved.  This used to sit after the no-email branch's `return`, so
        # it was unreachable: the corrected address worked for one invite but
        # the next conversation reverted to the stale email on file.
        if email_was_corrected and lead_id:
            cur.execute(
                "UPDATE leads SET email = %s, updated_at = NOW() WHERE id = %s",
                (lead_email, lead_id),
            )
            logger.info(f"[sms:appt] updated lead={lead_id} approved email → {lead_email}")

        # No real email anywhere (never on file, never given in this
        # conversation) — confirmed live: the prompt's own reply asked "is
        # this still your email" / "what's your email" while this function
        # booked immediately anyway using the {phone}@sms.lead placeholder,
        # so the lead's actual answer (if any) was never actually waited for
        # or used. Defer exactly like the slot-conflict case above instead of
        # finalizing on an address nobody can receive a real invite at — the
        # next inbound message re-runs this same extraction, and if it
        # contains a real email this time, booking completes normally.
        if lead_email == placeholder:
            cur.close(); conn.close()
            email_msg = "What's the best email for the calendar invite?"
            await asyncio.sleep(_typing_delay_seconds(email_msg))
            await _send_sms(from_phone, email_msg)
            if conv_id:
                _save_message(conv_id, "agent", email_msg)
            return

        if lead_row and lead_row["id"]:
            user_id = lead_row["id"]
        else:
            # users.email is UNIQUE, separately from the id/phone lookup above
            # — a user can already exist under this exact email from an
            # entirely different phone/lead (e.g. the same person texted in
            # before under a different number). Inserting blind then only
            # guards the (astronomically unlikely) id collision, not this
            # real one — confirmed live: booking crashed on
            # "duplicate key value violates unique constraint users_email_key"
            # after the AI reply had already told the lead "you're all set",
            # so nothing was actually booked despite the confident reply.
            existing_user_id = None
            if lead_email and "@" in lead_email:
                cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (lead_email,))
                existing = cur.fetchone()
                existing_user_id = existing["id"] if existing else None
            if existing_user_id:
                user_id = existing_user_id
            else:
                user_id = f"usr_sms_{uuid.uuid4().hex[:8]}"
                cur.execute("""
                    INSERT INTO users (id, phone, first_name, last_name, email, password_hash, business_id, role, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 'sms-lead-no-login', %s, 'customer', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                """, (user_id, from_phone, first_name, last_name, lead_email, business_id))

        # Determine service label from conversation or lead tags
        service_label = service_hint or ""
        if not service_label:
            tags_lower = [t.lower() for t in lead_tags]
            if any("insurance" in t for t in tags_lower):
                service_label = "Insurance Consultation"
            elif any("medical" in t or "health" in t or "dental" in t for t in tags_lower):
                service_label = "Medical Consultation"
            elif any("loan" in t or "finance" in t for t in tags_lower):
                service_label = "Finance Consultation"
            else:
                service_label = "Consultation"

        # Get or create service in DB
        cur.execute(
            "SELECT id FROM services WHERE business_id=%s AND LOWER(name)=LOWER(%s) LIMIT 1",
            (business_id, service_label)
        )
        svc_row = cur.fetchone()
        if svc_row:
            service_id = svc_row["id"]
        else:
            service_id = f"svc_{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO services (id, business_id, name, duration_minutes)
                VALUES (%s, %s, %s, 60)
                ON CONFLICT DO NOTHING
            """, (service_id, business_id, service_label))

        # Save appointment with service + client info
        appt_id = f"appt_{uuid.uuid4().hex[:12]}"
        booked_via_label = "Booked live on a call" if created_via == "voice_vapi_live" else "Booked via SMS"
        notes   = f"Client: {first_name} {last_name}. {booked_via_label}. sms_conv:{conv_id or 'call_confirm:' + lead_id}"

        # Try Google Calendar sync using business refresh token
        google_event_id = None
        try:
            from core.config import GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
            if GOOGLE_REFRESH_TOKEN and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
                # Token fetch stays a plain single attempt (form-encoded body,
                # not compatible with post_with_retry's json= signature) —
                # the observed live failure was specifically the calendar
                # event creation below, which is what actually gets retried.
                async with httpx.AsyncClient(timeout=10) as client:
                    token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "refresh_token": GOOGLE_REFRESH_TOKEN,
                        "grant_type": "refresh_token",
                    })
                if token_resp.is_success:
                    access_token = token_resp.json().get("access_token")
                    if access_token:
                        cal_body = {
                            "summary": f"{service_label} — {first_name} {last_name}".strip(" —"),
                            "description": notes,
                            # start_time/end_time hold the business's LOCAL
                            # wall-clock time (e.g. the "9:00 AM" the lead
                            # actually confirmed) — labeling that "UTC" used
                            # to show the invite 5-6 hours off from what was
                            # actually booked.
                            "start": {"dateTime": start_time.isoformat(), "timeZone": BUSINESS_TIMEZONE},
                            "end":   {"dateTime": end_time.isoformat(),   "timeZone": BUSINESS_TIMEZONE},
                        }
                        # Always include agency email so it appears on the agency's Google Calendar.
                        # Also invite the lead if they provided a real email.
                        from core.config import AGENCY_CALENDAR_EMAIL
                        agency_email = (AGENCY_CALENDAR_EMAIL or "shieldsquadagency@gmail.com").strip()
                        cal_attendees = []
                        if agency_email:
                            cal_attendees.append({"email": agency_email})
                        has_real_email = lead_email and not lead_email.endswith("@sms.lead") and lead_email.strip().lower() != agency_email.lower()
                        if has_real_email:
                            cal_attendees.append({"email": lead_email.strip()})
                        cal_body["attendees"] = cal_attendees

                        async with httpx.AsyncClient(timeout=15) as client:
                            cal_resp = await post_with_retry(
                                client,
                                "https://www.googleapis.com/calendar/v3/calendars/primary/events?sendUpdates=all",
                                headers={"Authorization": f"Bearer {access_token}"},
                                json=cal_body, label="calendar-create",
                            )
                        if cal_resp.is_success:
                            google_event_id = cal_resp.json().get("id")
                            logger.info(f"[sms:appt] Google Calendar event created: {google_event_id}")
                        else:
                            logger.warning(f"[sms:appt] Google Calendar create failed: {cal_resp.status_code} {cal_resp.text[:200]}")
        except Exception as cal_e:
            logger.warning(f"[sms:appt] Google Calendar sync error: {cal_e}")

        cur.execute("""
            INSERT INTO appointments
                (id, business_id, lead_id, user_id, service_id, start_time, end_time, status, notes, created_via, google_event_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed', %s, %s, %s)
        """, (appt_id, business_id, lead_id, user_id, service_id, start_time, end_time, notes, created_via, google_event_id))
        conn.commit()
        cur.close(); conn.close()

        # Move the lead out of "connected" and into its own dedicated stage —
        # without this, on_stage_change() never fires, so whatever workflow
        # got the lead here (e.g. Connected — Call First, Text Fallback) keeps
        # running completely unaware a real appointment now exists: it can
        # still place its own follow-up call/text on top of a booking that's
        # already confirmed. "appointment_booked" is the existing event for
        # exactly this (already used by the manual booking API,
        # api/appointments/router.py) — this SMS path just never called it.
        try:
            await transition_via_crm_api(lead_id, business_id, "appointment_booked",
                                          metadata={"appointment_id": appt_id})
        except Exception as e:
            logger.warning(f"[sms:appt] stage transition failed for {lead_id}: {e}")

        try:
            from core.admin_notify import notify_admins_appointment_booked
            await notify_admins_appointment_booked(business_id, first_name or from_phone, start_time, service_label)
        except Exception as e:
            logger.warning(f"[sms:appt] admin notify failed: {e}")

        # A real appointment now exists for this lead — any still-pending
        # ad-hoc "call to follow up" callback (_check_call_confirmation,
        # identified by callback_type='call' + no workflow_enrollment_id)
        # is now redundant: its whole purpose was to get a human on the
        # phone with this lead, and the text conversation already did that
        # job by landing a real time. Firing it anyway means calling someone
        # about a booking that's already confirmed — confirmed live: a lead
        # who resolved their booking by text got called ~2 minutes into a
        # conversation that had already moved on.
        try:
            cancel_conn = get_conn()
            cancel_cur = cancel_conn.cursor()
            cancel_cur.execute("""
                UPDATE scheduled_callbacks
                SET status = 'cancelled', updated_at = NOW()
                WHERE lead_id = %s AND callback_type = 'call'
                  AND workflow_enrollment_id IS NULL
                  AND status = 'pending'
            """, (lead_id,))
            cancelled = cancel_cur.rowcount
            cancel_conn.commit()
            cancel_cur.close(); cancel_conn.close()
            if cancelled:
                logger.info(f"[sms:appt] cancelled {cancelled} redundant pending call-confirmation callback(s) for lead={lead_id} — appointment already booked via SMS")
        except Exception as e:
            logger.warning(f"[sms:appt] failed to cancel redundant call callback for {lead_id}: {e}")

        # Build conversation transcript to include in the confirmation email
        convo_lines = []
        if conv_id:
            try:
                cur.execute(
                    "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY created_at ASC",
                    (conv_id,)
                )
                for r in cur.fetchall():
                    sender_label = "Alex (AllZone Technologies)" if r["role"] in ("agent", "assistant") else (first_name or "You")
                    convo_lines.append(f"• {sender_label}: \"{r['content']}\"")
            except Exception as e:
                logger.warning(f"[sms:appt] failed to fetch conversation history for email: {e}")
        convo_summary = "\n".join(convo_lines) if convo_lines else None

        from core.gmail import send_appointment_confirmation
        await send_appointment_confirmation(
            lead_email, first_name, service_label, start_time,
            conversation_text=convo_summary, phone=from_phone
        )

        logger.info(f"[sms:appt] Saved appointment {appt_id} for {from_phone} ({first_name}) — {service_label} at {start_time}")

        # Send confirmation SMS. Deliberately a plain template, not an LLM
        # call — this is the authoritative "it's really booked" message
        # (the AI's own in-the-moment reply just above can't know yet
        # whether the slot actually cleared availability/DB checks), and
        # this system's whole reliability posture (see the deterministic
        # backstops throughout this file) is to never let a probabilistic
        # model generate the one message that has to be factually exact.
        # Still worth writing like a person, not a calendar-system
        # notification — confirmed live: "Confirmed! Your Consultation is
        # booked for... We'll see you then!" reads like an automated
        # Calendly email dropped into a text thread, undoing the warmth of
        # every reply before it.
        confirm_msg = (f"You're all set! Your {service_label} is booked for "
                       f"{start_time.strftime('%A, %b %d at %I:%M %p')} 😊 "
                       f"Talk soon!")
        await asyncio.sleep(_typing_delay_seconds(confirm_msg))
        await _send_sms(from_phone, confirm_msg)
        if conv_id:
            _save_message(conv_id, "agent", confirm_msg)

    except Exception as e:
        logger.error(f"[sms:appt] Error: {e}")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _save_message(conv_id: str, role: str, content: str, status: str = "delivered", error_reason: str = None, channel: str = "sms"):
    conn = get_conn()
    cur = conn.cursor()
    clean_content = sanitize_text(content) if content else content
    try:
        cur.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, status, error_reason, channel)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (f"msg_{uuid.uuid4().hex[:12]}", conv_id, role, clean_content, status, error_reason, channel),
        )
        conn.commit()
    finally:
        cur.close(); conn.close()



_APPOINTMENT_WINDOW_OFFER_RE = re.compile(
    r"\b(morning|afternoon|evening)\b.*\b(morning|afternoon|evening)\b", re.IGNORECASE | re.DOTALL
)


def _regex_callback_seconds(message: str) -> int | None:
    """Fast regex check — catches ONLY unambiguous phrasing that can't
    plausibly be an answer to something else ('I'm busy, message me later').

    Deliberately narrow. This used to also match any bare NUMBER+UNIT near a
    generic word like "after" or "later" (e.g. "contact"/"call"/"message" co-
    occurring anywhere in the text) — but that fires just as easily on a
    normal answer to an unrelated question that happens to contain a time
    phrase. Confirmed live: a lead answering "When is your closing date?"
    with "After 1 week" got the ENTIRE qualifying conversation hijacked into
    a fake "I'll message you back in 168 hours" confirmation — she had no
    idea what that meant, understandably. Bare number+unit phrasing is
    ambiguous without knowing what question it's answering, so it's no
    longer judged here at all — see _extract_callback_seconds, which routes
    anything not caught by this narrow fast path through an LLM call that's
    given the actual conversation context to disambiguate."""
    msg = message.lower()
    busy_words  = ["busy", "not available", "unavailable", "occupied"]
    later_words = ["later", "after sometime", "after some time", "in a while"]
    if any(b in msg for b in busy_words) and any(l in msg for l in later_words):
        return 30 * 60
    return None


_VOICE_CALL_RE = __import__("re").compile(r'\bcall(s|ed|ing)?\b|\bphone\b|\bring\s+me\b', __import__("re").IGNORECASE)


def _wants_voice_call(message: str) -> bool:
    """
    Distinguishes 'call me back in 10 min' from generic 'contact/message/text
    me later' — a lead who explicitly asks to be CALLED should get a real
    phone call scheduled (callback_type='call'), not just another text later
    (which is what this callback path used to do unconditionally regardless
    of wording).
    """
    return bool(_VOICE_CALL_RE.search(message or ""))


async def _extract_callback_seconds(message: str, last_agent_message: str = "") -> int | None:
    """Detect callback request. Narrow regex first, then a context-aware LLM
    fallback for everything else — passing what the agent last asked is what
    lets the model tell "contact me after 1 week" (a real deferral) apart
    from "after 1 week" as a plain answer to "when is your closing date?"."""
    result = _regex_callback_seconds(message)
    if result:
        logger.info(f"[sms] callback detected via regex → {result}s")
        return result

    # Deterministic short-circuit for the highest-stakes false-positive case:
    # a reply to the agent's own appointment-window offer ("what time works
    # best -- morning, afternoon, or evening?") hijacked into a callback
    # deferral instead. The upgraded model below (gpt-4o) still got this
    # wrong live even with an explicit instruction against it and after
    # testing clean on retries — non-deterministic, and this is exactly the
    # class of case a regex can decide reliably instead of leaving it to
    # chance: the prompt's own APPOINTMENT BOOKING MECHANICS always phrases
    # the window offer as 2+ of morning/afternoon/evening together, which a
    # genuine "contact me later" message from the agent would not.
    if _APPOINTMENT_WINDOW_OFFER_RE.search(last_agent_message or ""):
        return None

    if not (OPENAI_API_KEY or GROQ_API_KEY):
        return None
    try:
        context_line = (
            f"The agent's last message was: {last_agent_message!r}\n\n" if last_agent_message else ""
        )
        text = await _llm_generate_async(
            f"{context_line}The lead's reply: {message!r}",
            system_instruction=(
                "Decide whether the lead's reply is EXPLICITLY asking to be contacted/called back "
                "later (a deferral, e.g. 'I'm busy, message me in 20 minutes', 'call me back in 2 "
                "hours') — as opposed to just answering whatever the agent's last message actually "
                "asked, even if that answer happens to contain a time period or duration (e.g. "
                "replying 'after 1 week' to 'when is your closing date?', or '3 months' to 'how long "
                "have you had insurance?'). If the agent's last message was asking about anything "
                "other than the lead's own availability, treat the reply as answering THAT question, "
                "not as a callback request — this distinction matters far more than the presence of "
                "a time phrase.\n"
                "IMPORTANT: if the agent's last message was asking what time works for an "
                "APPOINTMENT/booking with a licensed agent (e.g. 'what time works best for your "
                "appointment', 'when should we schedule you in'), that is NOT a callback deferral "
                "even though it's about the lead's own availability — the lead is choosing an "
                "appointment slot, not asking to be contacted later. Only treat it as a callback "
                "request when the agent's last message was about when/whether to reach the lead "
                "again (contacting them, calling them, checking back in), not about picking an "
                "appointment time. Return null in the appointment-slot case.\n"
                "If it IS a genuine callback/deferral request, return ONLY JSON: "
                "{\"callback_seconds\": <integer>}\n"
                "Otherwise: {\"callback_seconds\": null}\n"
                "Rules: X minutes → X*60, X hours → X*3600.\n"
                "Return ONLY the JSON. No explanation."
            ),
            # The fast default model has been caught live returning a real
            # callback_seconds for a reply that was actually picking an
            # appointment slot ("day after tomorrow, maybe morning" right
            # after being asked what time works) — despite the explicit
            # instruction above telling it not to. Non-deterministic (didn't
            # reproduce on repeat calls with identical input), which is its
            # own problem: this hijacks an in-progress booking into an
            # unrelated "I'll text you later" flow when it happens. Same
            # model-capability gap already fixed the same way for the
            # day/time extraction in _check_sms_appointment.
            model="gpt-4o",
            max_tokens=60, temperature=0, json_mode=True,
        )
        parsed = json.loads(text)
        cb     = parsed.get("callback_seconds")
        if cb and isinstance(cb, (int, float)) and cb > 0:
            logger.info(f"[sms] callback detected via LLM → {int(cb)}s")
            return int(cb)
    except Exception as e:
        logger.warning(f"[sms] LLM callback detection failed: {e}")
    return None


def _get_or_create_sms_conv(lead_id: str, business_id: str, channel: str = "sms") -> str:
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        # ORDER BY matters even with LIMIT 1: without it, which row Postgres
        # returns when more than one conversation exists for this lead is
        # undefined — confirmed during testing (multiple conversation rows
        # from repeated manual seeding) that this picked an arbitrary one,
        # not the newest, silently reading/writing the wrong thread's
        # history. Normal traffic only ever creates one via this same
        # get-or-create path, but the query itself shouldn't rely on that.
        cur.execute(
            "SELECT id FROM conversations WHERE lead_id = %s AND business_id = %s AND channel = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (lead_id, business_id, channel),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        cur.execute(
            "INSERT INTO conversations (id, business_id, lead_id, channel, ai_active) VALUES (%s, %s, %s, %s, TRUE)",
            (conv_id, business_id, lead_id, channel),
        )
        conn.commit()
        return conv_id
    finally:
        cur.close(); conn.close()


# Messages that are unambiguously a continuation of the conversation, never a
# decline — matched deterministically so they never reach the LLM at all.
# This exists because gpt-4o-mini, even given trailing conversation
# context, still occasionally misjudged a bare "Ok" mid-quote-flow as
# declined=true, repeatedly flipping an actively-engaged lead to dead and
# back (see lead journey history). A regex can't be wrong about "ok" being
# a decline, so remove the LLM's chance to be wrong for this common case.
_SAFE_CONTINUATION_RE = __import__("re").compile(
    r"^\s*(ok(ay)?|k|kk|ya|yah|yes|yeah|yep|yup|sure|alright|sounds\s*good|"
    r"great|perfect|thanks?|thank\s*you|got\s*it|cool|fine|good|no\s*problem|np)"
    r"\s*[.!]?\s*$",
    __import__("re").IGNORECASE,
)
# Bare zip codes / phone numbers / a lone number
_SAFE_NUMBER_RE = __import__("re").compile(r"^\s*\d{3,}\s*$")
# A bare email address
_SAFE_EMAIL_RE = __import__("re").compile(r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$")


# A reply with no actual letters/digits at all — just emoji, punctuation, or
# whitespace (e.g. a bare "👍") — is too ambiguous to auto-confirm a call
# from. A thumbs-up could mean "yes go ahead" or just "got it, thanks" —
# there's no way to tell apart from the symbol alone, and the LLM classifier
# guessed "yes" on this in testing, which isn't a safe default for something
# that dials the lead's phone. Require an actual worded reply instead.
_HAS_WORDS_RE = __import__("re").compile(r'[A-Za-z0-9]')


def _is_symbols_only(msg: str) -> bool:
    """True if the message has no letters or digits — just emoji/punctuation/whitespace."""
    return not bool(_HAS_WORDS_RE.search(msg or ""))


def _is_safe_continuation(msg: str) -> bool:
    msg = msg or ""
    return bool(
        _SAFE_CONTINUATION_RE.match(msg)
        or _SAFE_NUMBER_RE.match(msg)
        or _SAFE_EMAIL_RE.match(msg)
    )


async def _check_lead_progression(lead_id: str, business_id: str, phone: str, history: list):
    """
    After each SMS exchange, check if the lead has progressed to 'qualified'
    (enough qualifying info given) or 'quoted' (agent gave a specific price).
    Only runs once per milestone (skips if already quoted/converted/dead).
    """
    if not (OPENAI_API_KEY or GROQ_API_KEY):
        return
    try:
        conn = get_conn()
        cur  = dict_cursor(conn)

        # Skip once a lead is already past both milestones. appointment_scheduled
        # belongs here too — found live: booking an appointment moves sub_status
        # straight from qualified to appointment_scheduled, which isn't "quoted"
        # so this used to fall through, re-run the qualified check, and (since
        # already_qualified is a literal == "qualified" match) create a second
        # duplicate "Send quote" staff task off the exact same conversation.
        cur.execute("SELECT sub_status FROM leads WHERE id = %s", (lead_id,))
        row = cur.fetchone()
        if not row or row["sub_status"] in ("quoted", "appointment_scheduled", "converted", "dead"):
            cur.close(); conn.close()
            return
        already_qualified = row["sub_status"] == "qualified"

        # Build conversation text
        chat = "\n".join(
            f"{'Agent' if m['role'] in ('agent','assistant') else 'Lead'}: {m['content']}"
            for m in history
        )
        last_lead_msg = next(
            (m["content"] for m in reversed(history) if m["role"] not in ("agent", "assistant")),
            "",
        )

        # declined gets its own single-purpose LLM call, run in parallel with
        # the qualified/quoted call below. Bundling all three judgments into
        # one prompt was unreliable in practice — a price objection like
        # "that's way too expensive" kept getting scored as declined=true
        # (the fast default model pattern-matches "expensive" to rejection even
        # with explicit few-shot counter-examples in a multi-task prompt). A
        # dedicated, narrowly-scoped prompt fixed it. Getting this wrong is
        # costly — declined=true marks the lead permanently dead and cancels
        # all further automation (core.workflow_engine.on_stage_change) — so
        # it's worth the extra call rather than trusting a shared judgment.
        #
        # Judging the bare latest message with NO surrounding context caused a
        # second, worse failure mode in practice: short continuation replies
        # like "Ok" — genuinely ambiguous in isolation — kept getting scored
        # declined=true even mid-quote-flow (lead giving zip/email/"yes auto"
        # etc.), repeatedly flipping an actively-engaged lead to dead and back
        # to connected on their very next reply. A few trailing turns of real
        # context is enough for the model to see "Ok" is a continuation, not a
        # rejection, without reintroducing the original bundled-prompt issue.
        recent_context = "\n".join(
            f"{'Agent' if m['role'] in ('agent','assistant') else 'Lead'}: {m['content']}"
            for m in history[-6:]
        )
        if _is_safe_continuation(last_lead_msg):
            # Deterministic fast path — see _is_safe_continuation. Wrapped in a
            # coroutine so the asyncio.gather(declined_task, progress_task)
            # below doesn't need a separate code path for this case.
            async def _not_declined():
                return '{"declined": false}'
            declined_task = _not_declined()
        else:
            declined_task = _llm_generate_async(
                "Below is the tail end of an ongoing SMS conversation between an insurance agent "
                "and a lead, ending with the lead's latest message.\n\n"
                f"{recent_context}\n\n"
                f"Judge ONLY the lead's LAST message: {last_lead_msg!r}\n\n"
                "Is THAT message a DECLINE — meaning they clearly do not want this insurance at "
                "all, are flatly saying no, or are asking to stop being contacted (e.g. 'not "
                "interested', 'no thanks', 'stop', 'remove me')?\n"
                "A short reply that continues the conversation ('ok', 'yes', 'sure', 'sounds "
                "good', a zip code, an email address, a number) is NEVER a decline by itself — "
                "given the context above it means they're still engaged, not rejecting anything. "
                "A PRICE OBJECTION (pushing back on cost — 'too expensive', 'that's a lot', 'can "
                "you do better', 'that's steep') is also NOT a decline — it's a buying signal, "
                "they're negotiating because they still want it. Hesitation ('let me think about "
                "it') and re-engagement are also NOT declines. Only return true when the message "
                "itself contains explicit rejection or opt-out language.\n"
                "Return ONLY JSON: {\"declined\": bool}",
                # This decision permanently kills the lead's automation if wrong
                # (marks it dead) — worth the larger, still-fast gpt-4o model over
                # the fast default one, same reliability reasoning as progress_task
                # below. Runs after the reply is already sent, so no live-latency cost.
                model="gpt-4o",
                max_tokens=20, temperature=0, json_mode=True,
            )

        # quoted no longer requires the agent to have personally issued a
        # firm company price — a lead who has stated (and confirmed, with no
        # objection) both a coverage amount and a budget has given everything
        # needed to generate a quote, even if a human still has to price it
        # exactly. Business call: a real voice call where the lead confirmed
        # $100k coverage / $58 budget back-and-forth, with the AI only
        # reflecting the numbers back rather than issuing its own price,
        # still stalled at 'qualified' under the old stricter definition —
        # that undercounted real buying signal.
        # Both checks are monotonic — "at any point", not "as of the latest
        # message" — deliberately, after a live call transcript with a fully
        # confirmed $3000/$500-per-month quote ("Yes. Yes. Yes.") still came
        # back quoted=false because the lead's next reply ("It's for my cell
        # phone") was unrelated. The fast default classifier was anchoring on the last
        # message and treating an unrelated follow-up as undoing an already-
        # confirmed quote. Explicitly telling it that later confusion doesn't
        # retroactively erase an earlier confirmation fixed it (verified
        # against that exact transcript, plus regression-checked against a
        # no-numbers-given case and a price-objection case to make sure this
        # didn't just make it fire more eagerly).
        progress_prompt = (
            "You are reviewing an insurance conversation (call or SMS) between an agent/AI "
            "and a lead.\n"
            "Return ONLY JSON: {\"qualifying_detail_found\": \"<one of: coverage amount, budget, "
            "smoker status, family size, age, none>\", \"qualified\": bool, \"quoted\": bool}\n"
            "qualified = true ONLY if AT ANY POINT the LEAD THEMSELVES (never the agent) stated a "
            "type of insurance (health/life/auto/home/business) AND the LEAD THEMSELVES also stated "
            "at least one of these five specific details: coverage amount, budget, smoker status, "
            "family size, or age. Fill qualifying_detail_found with whichever one applies, or "
            "\"none\" if the lead has only given the insurance type so far. A bare statement of "
            "type alone (e.g. lead says only 'I need health insurance' and nothing else) is NEVER "
            "enough by itself — qualified MUST be false in that case, even after several back-and-"
            "forth messages, until one of the five details is actually given. Do not count words "
            "that only appear in the AGENT's question (e.g. the agent offering 'new policy, renewal, "
            "or switching' as options is not the lead providing a detail — only the lead's own "
            "answer counts, and note that new/renewal/switching is not one of the five qualifying "
            "details anyway). Once true it stays true for "
            "the rest of the conversation, even if a later message is confusing or off-topic.\n"
            "quoted = true if AT ANY POINT the lead clearly stated (or confirmed back when the "
            "agent repeated it) BOTH a coverage amount AND a budget/monthly premium for a "
            "specific insurance type, with no objection raised at the time — once both numbers "
            "were given and confirmed, quoted stays true for the rest of the conversation even "
            "if the lead later says something confusing, off-topic, or unrelated — that does "
            "NOT retroactively undo an earlier confirmed quote. Also true for explicit agreement "
            "to an agent-given price (e.g. 'sounds good', 'yes let's do it', 'sign me up'). "
            "quoted MUST be false only if: coverage or budget numbers were never both given at "
            "any point, the lead raised a price objection ('too expensive') or showed hesitation "
            "('let me think about it') before ever confirming, or the numbers only came up in an "
            "unrelated/ambiguous exchange that was never confirmed.\n\n"
            f"Full conversation so far:\n{chat}\n\n"
            f"LEAD'S LATEST MESSAGE (for context only — does not retroactively undo earlier "
            f"confirmed facts):\n{last_lead_msg}"
        )
        # The fast default model (used for live reply generation where speed
        # matters most) previously got this judgment wrong repeatedly on a
        # real transcript even with the monotonic prompt above — anchoring on
        # a confusing final message and ignoring an already-confirmed quote.
        # The larger gpt-4o model got it right on the same transcript.
        # This check runs after the reply is already sent (SMS) or after the
        # call has ended (voice), so the extra latency costs nothing live.
        progress_task = _llm_generate_async(
            progress_prompt, model="gpt-4o", max_tokens=60, temperature=0, json_mode=True
        )

        declined_text, progress_text = await asyncio.gather(declined_task, progress_task)
        declined_parsed = json.loads(declined_text)
        parsed = json.loads(progress_text)

        if declined_parsed.get("declined"):
            await transition_via_crm_api(lead_id, business_id, "mark_dead")
            logger.info(f"[sms:progression] lead {lead_id} DECLINED — moved to dead/Trip Lead")
            cur.close(); conn.close()
            return "declined"

        if parsed.get("quoted"):
            await transition_via_crm_api(lead_id, business_id, "ai_quoted")
            logger.info(f"[sms:progression] lead {lead_id} QUOTED")
            cur.close(); conn.close()
            return "quoted"

        result = None
        if parsed.get("qualified") and not already_qualified:
            await transition_via_crm_api(lead_id, business_id, "ai_qualified")

            # Guaranteed, immediate staff visibility — the AI tells qualified
            # leads "a quoting specialist will follow up", but nothing else
            # enforces that promise (workflow automation only fires on stage
            # changes, and qualified is a same-stage sub-status change, so no
            # workflow can ever see it). A task makes the promise real
            # regardless of what automation is or isn't configured.
            cur.execute("SELECT first_name, last_name FROM leads WHERE id = %s", (lead_id,))
            lead_row  = cur.fetchone()
            lead_name = " ".join(filter(None, [
                (lead_row or {}).get("first_name"), (lead_row or {}).get("last_name"),
            ])).strip()
            task_id = f"task_{uuid.uuid4().hex[:12]}"
            cur.execute("""
                INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                VALUES (%s, %s, %s, %s, 'open', NOW() + INTERVAL '2 hours', NOW())
            """, (task_id, lead_id, business_id,
                  f"Send quote to {lead_name or phone} — qualified, needs pricing follow-up"))
            conn.commit()
            logger.info(f"[sms:progression] lead {lead_id} QUALIFIED → task {task_id} created for staff")

            # No separate auto-call scheduling here — the "Insurance Lead
            # Nurture" workflow's reply_check branch is what schedules the
            # follow-up call, ~45min after the lead's SMS reply (see
            # _resolve_pending_reply_checks). Scheduling a second call here
            # off the qualified milestone risked landing a redundant call on
            # top of an already-handled conversation. Known trade-off: a
            # lead qualified entirely over a voice call (no SMS reply
            # involved) no longer gets an automatic follow-up call from this
            # path — that case would need its own explicit trigger if wanted.
            result = "qualified"

        cur.close(); conn.close()
        return result

    except Exception as e:
        logger.warning(f"[sms:progression] check failed: {e}")
        return None


async def _check_call_confirmation(lead_id: str, business_id: str, phone: str, history: list,
                                    conv_id: str | None = None):
    """
    Dynamic call trigger: a call gets scheduled only once the lead has
    EXPLICITLY confirmed they want one over text — not on every reply, and
    not on a blanket timer. Looks at whether the agent's most recent message
    (before the lead's latest reply) actually proposed a call, and whether
    the lead's latest reply agreed to THAT specific offer (see the CALL
    PROPOSAL guardrail in _handle_inbound_message, which is what gets the
    agent to make that offer once real interest is shown).

    Runs after the SMS reply is already sent (same pattern as
    _check_lead_progression / _check_sms_appointment below) — this is a
    background judgment, not something that should add live-reply latency.
    """
    if not (OPENAI_API_KEY or GROQ_API_KEY) or len(history) < 2:
        return
    try:
        conn = get_conn()
        cur = dict_cursor(conn)

        cur.execute("SELECT stage FROM leads WHERE id = %s", (lead_id,))
        row = cur.fetchone()
        if not row or row["stage"] == "dead":
            cur.close(); conn.close()
            return

        # Quick Setup toggle — "Call once a lead confirms interest" off means
        # skip this feature entirely for this business, regardless of what
        # the lead says.
        cur.execute(
            "SELECT call_on_confirm_enabled, call_on_confirm_wait_minutes "
            "FROM business_automation_settings WHERE business_id = %s",
            (business_id,),
        )
        settings_row = cur.fetchone()
        call_on_confirm_enabled = settings_row["call_on_confirm_enabled"] if settings_row else True
        call_wait_minutes = settings_row["call_on_confirm_wait_minutes"] if settings_row else 45
        if not call_on_confirm_enabled:
            cur.close(); conn.close()
            return

        # Don't double-book — a call already pending/placed recently for this
        # lead means there's nothing to schedule.
        cur.execute("""
            SELECT 1 FROM scheduled_callbacks
            WHERE lead_id = %s AND callback_type = 'call'
              AND status IN ('pending', 'processing', 'completed')
              AND created_at > NOW() - INTERVAL '24 hours'
            LIMIT 1
        """, (lead_id,))
        if cur.fetchone():
            cur.close(); conn.close()
            return

        # The caller passes full_history, which (in the live inbound path) has
        # the AI's own new reply appended AFTER the lead's message — so the
        # chat log does not necessarily end with the lead's turn. Pull the
        # actual last lead message out explicitly (same approach as
        # _check_lead_progression's last_lead_msg above) instead of assuming
        # it's the final line, otherwise the model gets confused about which
        # message is "latest" and misses clear confirmations.
        recent = history[-8:]
        chat = "\n".join(
            f"{'Agent' if m['role'] in ('agent','assistant') else 'Lead'}: {m['content']}"
            for m in recent
        )
        last_lead_msg = next(
            (m["content"] for m in reversed(history) if m["role"] not in ("agent", "assistant")),
            "",
        )

        # An emoji/symbols-only reply (e.g. bare "👍") is too ambiguous to
        # auto-schedule a call from — could mean "yes go ahead" or just "got
        # it, thanks". Skip the LLM call entirely and wait for a worded reply
        # instead of guessing on something that dials the lead's phone.
        if _is_symbols_only(last_lead_msg):
            cur.close(); conn.close()
            return

        text = await _llm_generate_async(
            "Below is the tail end of an SMS conversation between an insurance agent and a lead.\n\n"
            f"{chat}\n\n"
            f"Focus on the LEAD's most recent message: {last_lead_msg!r}\n\n"
            "Return call_confirmed=true if EITHER of these is true:\n"
            "1. The AGENT message right before it explicitly offered a PHONE CALL specifically "
            "(e.g. 'want a quick call to go over your options?', 'can I give you a call?'), AND the "
            "lead's message quoted above clearly agrees to that specific offer (e.g. 'yes', 'sure', "
            "'sounds good', 'ok call me') — not declining it or replying about something unrelated.\n"
            "2. The lead's message quoted above ASKS FOR a call on their own, unprompted — even if "
            "the agent never offered one (e.g. 'can someone call me', 'I'd rather just talk on the "
            "phone', 'please call me', 'can I speak to an agent').\n"
            "Return call_confirmed=FALSE for anything else, even if it sounds related — this "
            "includes agreeing to 'book an appointment with a licensed agent' and agreeing to have "
            "someone 'prepare/send a quote'. Those are handled by a separate text-based scheduling "
            "flow that will ask for a specific day/time next; they are NOT the same as agreeing to "
            "receive a phone call, and must not be treated as one.\n"
            "Example — FALSE: Agent: 'Would you like to book an appointment with a licensed agent "
            "to discuss your options?' Lead: 'Yes please' → "
            "{\"call_confirmed\": false} (this is a request to schedule a future appointment via "
            "text, not consent to receive a phone call right now).\n"
            "Example — TRUE: Agent: 'Want a quick call to go over your options?' Lead: 'Sure, call "
            "me' → {\"call_confirmed\": true}.\n"
            "Return ONLY JSON: {\"call_confirmed\": bool}",
            model="gpt-4o", max_tokens=20, temperature=0, json_mode=True,
        )
        parsed = json.loads(text)
        if not parsed.get("call_confirmed"):
            cur.close(); conn.close()
            return

        cb_id = f"cb_{uuid.uuid4().hex[:12]}"
        call_reason = (
            "This lead just confirmed by text that they'd like a call. Continue naturally from "
            "the text conversation already shown to you below — do not restart or re-ask anything "
            "already covered there; pick up exactly where it left off, like a human agent taking "
            "over the same conversation (e.g. if coverage amount or budget hasn't come up yet, "
            "that's a natural next question — don't re-introduce yourself or re-ask what type of "
            "insurance they want if that's already answered above)."
        )
        cur.execute("""
            INSERT INTO scheduled_callbacks
                (id, lead_id, business_id, phone, scheduled_at, status,
                 call_reason, callback_type, created_at, updated_at)
            VALUES (%s, %s, %s, %s, NOW() + (%s || ' minutes')::interval, 'pending',
                    %s, 'call', NOW(), NOW())
        """, (cb_id, lead_id, business_id, phone, call_wait_minutes, call_reason))
        conn.commit()
        cur.close(); conn.close()
        logger.info(f"[sms:call_confirm] lead={lead_id} confirmed a call via SMS — scheduled cb_id={cb_id} in {call_wait_minutes}min")

        # This schedules the near-term "someone will call you shortly" check-in
        # (~45min, per the confirmed design) — it does NOT book a formal
        # appointment, on purpose. Auto-picking a time the lead was never
        # asked about isn't a real booking. The actual appointment (stage
        # transition, calendar invite, the works — see _book_appointment)
        # only gets created once the lead names/picks an actual time, which
        # _check_sms_appointment already handles — the APPOINTMENT EMAIL
        # guardrail's follow-up now asks for that time before confirming.
    except Exception as e:
        logger.warning(f"[sms:call_confirm] check failed for lead={lead_id}: {e}")


async def _resolve_pending_reply_checks(lead_id: str, business_id: str):
    """
    A lead just replied — if they have a workflow enrollment currently parked
    at a branch_condition(mode="reply_check") node waiting on exactly this
    signal, resolve it now instead of waiting for its scheduled timeout to
    elapse. Without this, "call ~30-60 min after they reply" would actually
    mean "call up to `timeout_hours` after they reply, plus the buffer" —
    the reply_check node only re-evaluates when its scheduled check row
    fires, which by default is hours out (see workflow_engine.py's
    _evaluate_branch docstring).

    Idempotent/safe even if the check row's own timeout also fires later:
    marking it 'completed' here means the 30s poller (core/callback_scheduler.py)
    will no longer pick it up, and advance_after_action ignores a stale
    node_key if the enrollment has already moved on.
    """
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT lwe.id AS enrollment_id, lwe.current_node_key, cb.id AS cb_id
            FROM lead_workflow_enrollments lwe
            JOIN workflow_nodes wn ON wn.workflow_id = lwe.workflow_id AND wn.node_key = lwe.current_node_key
            LEFT JOIN scheduled_callbacks cb ON cb.workflow_enrollment_id = lwe.id
                AND cb.workflow_node_key = lwe.current_node_key AND cb.status = 'pending'
            WHERE lwe.lead_id = %s AND lwe.status = 'waiting'
              AND wn.node_type = 'branch_condition' AND wn.config->>'mode' = 'reply_check'
        """, (lead_id,))
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            if row["cb_id"]:
                cur.execute(
                    "UPDATE scheduled_callbacks SET status='completed', updated_at=NOW() WHERE id=%s",
                    (row["cb_id"],),
                )
        conn.commit()
    except Exception as e:
        logger.warning(f"[sms:workflow] could not resolve pending reply-checks for lead={lead_id}: {e}")
        rows = []
    finally:
        cur.close(); conn.close()

    if not rows:
        return

    from core.workflow_client import advance_workflow
    for row in rows:
        await advance_workflow(row["enrollment_id"], business_id, row["current_node_key"], {"replied": True})


# ── Shared inbound handler — used by both the Twilio (WhatsApp) webhook and
# Claw Messenger's WebSocket listener (core/claw_messenger.py's _listen()),
# since everything past "who sent what over which channel" is identical
# regardless of provider or transport. ──────────────────────────────────────

async def _handle_inbound_message(from_phone: str, message: str, channel: str):
    logger.info(f"[sms:inbound] From={from_phone} channel={channel} msg={message[:60]}")

    conn = get_conn()
    cur = dict_cursor(conn)
    lead_id = business_id = conv_id = None  # set once the lead/conv are found below; kept in
    # scope so the outer except can still create a staff task (and correctly
    # save its fallback SMS to history) even if the failure happened after
    # that point, not just before it.
    try:
        cur.execute(
            "SELECT id, business_id, first_name, tags, notes, opted_out, stage, email FROM leads WHERE phone = %s LIMIT 1",
            (from_phone,),
        )
        lead = cur.fetchone()
        if not lead:
            logger.info(f"[sms:inbound] Unknown number {from_phone} — auto-creating lead")
            created = await create_lead_from_inbound(from_phone, channel)
            if not created:
                logger.error(f"[sms:inbound] auto-create failed for {from_phone} — dropping message")
                return
            lead = {
                "id": created["id"], "business_id": created["business_id"],
                "first_name": created["first_name"], "tags": created["tags"],
                "notes": created["notes"], "opted_out": created["opted_out"],
                "stage": created["stage"], "email": created["email"],
            }

        lead_id = lead["id"]
        business_id = lead["business_id"] or DEFAULT_BUSINESS_ID
        lead_tags = lead["tags"] or []
        lead_notes = lead.get("notes") or ""
        conv_id = _get_or_create_sms_conv(lead_id, business_id, channel)

        # Claw Messenger (and Twilio) can redeliver the same inbound message —
        # seen live as the identical text landing twice within milliseconds,
        # which then fires two/three concurrent AI replies for what was
        # really one message from the lead. Treat an identical message saved
        # for this conversation in the last few seconds as a duplicate
        # delivery, not a new one.
        cur.execute(
            "SELECT 1 FROM messages WHERE conversation_id = %s AND role = 'user' "
            "AND content = %s AND created_at > NOW() - INTERVAL '10 seconds'",
            (conv_id, message),
        )
        if cur.fetchone():
            logger.info(f"[sms:inbound] duplicate webhook delivery for {from_phone} ({message[:40]!r}) — ignoring")
            return

        # Save the incoming user message immediately so it is recorded in the CRM
        # and visible in the chat thread regardless of any downstream AI generation or network issues.
        _save_message(conv_id, "user", message)

        # ── TCPA opt-out / resubscribe — checked before any AI/callback
        # processing, and regardless of ai_active, since these are legally
        # mandatory regardless of whether AI replies are paused for this lead.
        normalized = message.strip().lower()
        cur.execute(
            "SELECT content FROM messages WHERE conversation_id = %s "
            "AND role IN ('agent', 'assistant') ORDER BY created_at DESC LIMIT 1",
            (conv_id,),
        )
        _last_msg_row = cur.fetchone()
        last_agent_for_opt_out = (_last_msg_row["content"] if isinstance(_last_msg_row, dict) else _last_msg_row[0]) if _last_msg_row else None
        # Check conversational declines (like "no", "no thanks", "sorry", "not interested")
        cleaned_normalized = __import__("re").sub(r"[^a-z0-9\s]", "", normalized)
        cleaned_normalized = " ".join(cleaned_normalized.split())
        is_contextual_opt_out = _is_contextual_opt_out_reply(message, last_agent_for_opt_out)
        is_hard_stop = normalized in STOP_KEYWORDS
        is_conversational_decline = (
            is_contextual_opt_out
            or cleaned_normalized in _CONTEXTUAL_OPT_OUT_REPLIES
            or cleaned_normalized in ("no", "n", "nope", "nah", "sorry")
            or any(phrase in cleaned_normalized for phrase in (
                "no thanks", "not interested", "sorry", "no thank you", "dont text me", "dont contact me"
            ))
        )

        if is_hard_stop or is_conversational_decline:
            cur.execute(
                "UPDATE leads SET opted_out = TRUE, opted_out_at = NOW(), updated_at = NOW() WHERE id = %s",
                (lead_id,),
            )
            conn.commit()
            # An explicit opt-out is also a definitive decline for pipeline
            # purposes. Moving to Dead/Trip Lead cancels active workflows so
            # non-SMS actions (especially calls) cannot continue contacting
            # someone who just asked to be left alone.
            await transition_via_crm_api(
                lead_id, business_id, "mark_dead", metadata={"reason": "sms_opt_out"}
            )

            # When the recipient opts out or asks to stop (whether hard 'STOP' or polite decline),
            # ALWAYS reply warmly with sympathetic, human words instead of a cold robotic unsubscribe notice.
            if is_hard_stop:
                reply_body = OPT_OUT_CONFIRMATION
            else:
                reply_body = POLITE_DECLINE_REPLY

            try:
                await _send_sms(from_phone, reply_body, channel, force=True)
                _save_message(conv_id, "agent", reply_body)
            except Exception as tw_err:
                logger.error(f"[sms:compliance] opt-out confirmation failed for {from_phone}: {tw_err}")
            logger.info(f"[sms:compliance] lead {lead_id} ({from_phone}) opted out (reply='{reply_body[:30]}...')")
            return

        if normalized in RESUBSCRIBE_KEYWORDS and lead.get("opted_out"):
            cur.execute(
                "UPDATE leads SET opted_out = FALSE, opted_out_at = NULL, updated_at = NOW() WHERE id = %s",
                (lead_id,),
            )
            conn.commit()
            # START is explicit re-engagement. The lifecycle allows
            # dead -> responded for a genuine inbound reply, restoring the
            # lead to Connected while keeping the audit trail intact.
            await transition_via_crm_api(
                lead_id, business_id, "inbound_reply", metadata={"reason": "sms_resubscribe"}
            )
            try:
                await _send_sms(from_phone, RESUBSCRIBE_CONFIRMATION, channel, force=True)
                _save_message(conv_id, "agent", RESUBSCRIBE_CONFIRMATION)
            except Exception as tw_err:
                logger.error(f"[sms:compliance] resubscribe confirmation failed for {from_phone}: {tw_err}")
            logger.info(f"[sms:compliance] lead {lead_id} ({from_phone}) resubscribed")
            return

        # Message history for context
        cur.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = %s ORDER BY created_at ASC",
            (conv_id,),
        )
        history = [dict(r) for r in cur.fetchall()]

        # Lead engaged — mark responded regardless of whether AI is paused for
        # this conversation. No-ops if already past this stage (idempotent /
        # 409-tolerant — see transition_via_crm_api). This also revives a
        # previously-dead (Trip Lead) lead back to Connected — texting back
        # in is a real re-engagement signal, not something to leave stuck.
        await transition_via_crm_api(lead_id, business_id, "inbound_reply")
        await _resolve_pending_reply_checks(lead_id, business_id)

        # Re-read stage fresh — the transition above may have just changed it
        # (e.g. dead -> responded on revival), and the `lead` dict below is
        # used for agent-matching further down, so a stale stage would wrongly
        # keep refusing to reply to a lead who was just revived.
        cur.execute("SELECT stage FROM leads WHERE id = %s", (lead_id,))
        fresh_stage = cur.fetchone()
        if fresh_stage:
            lead["stage"] = fresh_stage["stage"]

        cur.execute("SELECT ai_active FROM conversations WHERE id = %s", (conv_id,))
        conv_row = cur.fetchone()
        ai_active = conv_row["ai_active"] if conv_row else True

        # ── Callback / busy detection (runs before AI reply) ─────────────────
        last_agent_message = next(
            (m["content"] for m in reversed(history) if m["role"] in ("agent", "assistant")), ""
        )
        cb_seconds = await _extract_callback_seconds(message, last_agent_message)
        if cb_seconds:
            cb_id = f"cb_{uuid.uuid4().hex[:12]}"
            wants_call = _wants_voice_call(message)
            if wants_call:
                cur.execute("""
                    INSERT INTO scheduled_callbacks
                        (id, lead_id, business_id, phone, scheduled_at, status,
                         call_reason, callback_type, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW() + make_interval(secs => %s), 'pending',
                            'Lead asked to be called back via SMS/WhatsApp', 'call', NOW(), NOW())
                """, (cb_id, lead_id, business_id, from_phone, cb_seconds))
            else:
                cur.execute("""
                    INSERT INTO scheduled_callbacks
                        (id, lead_id, business_id, phone, scheduled_at, status,
                         call_reason, callback_type, sms_channel, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW() + make_interval(secs => %s), 'pending',
                            'Lead requested follow-up via SMS/WhatsApp', 'sms', %s, NOW(), NOW())
                """, (cb_id, lead_id, business_id, from_phone, cb_seconds, channel))
            minutes = cb_seconds // 60
            if minutes >= 60:
                hrs = minutes // 60
                time_label = f"{hrs} hour{'s' if hrs != 1 else ''}"
            elif minutes > 0:
                time_label = f"{minutes} minute{'s' if minutes != 1 else ''}"
            else:
                time_label = f"{cb_seconds} second{'s' if cb_seconds != 1 else ''}"
            confirm = (f"No problem! I'll have someone call you in {time_label}." if wants_call
                       else f"No problem! I'll message you back in {time_label}. Talk soon!")
            _save_message(conv_id, "agent", confirm)
            conn.commit()

            if wants_call:
                try:
                    await transition_via_crm_api(lead_id, business_id, "appointment_booked")
                    cur.execute("SELECT id FROM users WHERE phone = %s LIMIT 1", (from_phone,))
                    u_row = cur.fetchone()
                    if u_row:
                        appt_user_id = u_row["id"]
                    else:
                        appt_user_id = f"usr_sms_{uuid.uuid4().hex[:8]}"
                        cur.execute("""
                            INSERT INTO users (id, phone, first_name, last_name, email, password_hash, business_id, role, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, 'sms-lead-no-login', %s, 'customer', NOW(), NOW())
                            ON CONFLICT (id) DO NOTHING
                        """, (appt_user_id, from_phone, (lead.get("first_name") or "Lead"), (lead.get("last_name") or ""), f"{from_phone.replace('+','')}@sms.lead", business_id))
                    appt_id = f"appt_{uuid.uuid4().hex[:12]}"
                    cur.execute("""
                        INSERT INTO appointments (id, lead_id, user_id, business_id, start_time, end_time, status, notes, created_via, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW() + make_interval(secs => %s), NOW() + make_interval(secs => %s) + interval '30 minutes', 'confirmed', %s, 'sms', NOW(), NOW())
                    """, (appt_id, lead_id, appt_user_id, business_id, cb_seconds, cb_seconds, f"Phone appointment scheduled via SMS: {message[:120]}"))
                    conn.commit()
                    logger.info(f"[sms:inbound] lead {lead_id} transitioned to appointment_scheduled with appointment {appt_id}")
                except Exception as appt_err:
                    logger.warning(f"[sms:inbound] failed to transition lead {lead_id} to appointment_scheduled: {appt_err}")

            try:
                await asyncio.sleep(_typing_delay_seconds(confirm))
                await _send_sms(from_phone, confirm, channel)
            except Exception as tw_err:
                logger.warning(f"[sms:inbound] Twilio confirm failed: {tw_err}")
            logger.info(f"[sms:inbound] {'Call' if wants_call else 'SMS follow-up'} scheduled cb_id={cb_id} in {cb_seconds}s for {from_phone}")
            return

        if ai_active and lead.get("opted_out"):
            # Already opted out (and this message wasn't a STOP/START keyword,
            # handled above) — do not send anything further, just log it.
            logger.info(f"[sms:compliance] inbound from opted-out lead {lead_id} ({from_phone}) — not replying")
            conn.commit()
        elif ai_active:
            agent = _get_agent_prompt(business_id, lead_tags, lead.get("stage"))
            if agent is None:
                logger.warning(f"[sms:inbound] no agent configured for lead={lead_id} tags={lead_tags} stage={lead.get('stage')} — not replying")
                conn.commit()
                return
            system_prompt = agent["prompt"]
            if history:
                # A short/generic reply after a real gap (e.g. bare "hello",
                # "hi", "you there?") was observed generating a fresh
                # introduction/generic opener ("Hi! How can I assist you
                # today?") despite the actual conversation history being
                # passed in as real turns above — the history alone wasn't
                # enough to stop the model defaulting to greeting mode on an
                # ambiguous input. Same class of issue as the workflow-SMS
                # continuity fix, just needed here too since this path never
                # had an explicit instruction for it.
                system_prompt += (
                    "\n\nCONTINUITY: the conversation history above is real and already happened — "
                    "even if the lead's latest message is short or generic (e.g. 'hello', 'hi', 'you "
                    "there?', after a long gap), do NOT treat this as a brand new conversation, "
                    "reintroduce yourself, or ask a generic opening question like 'how can I assist "
                    "you today?'. Instead pick up from the most recent unresolved point in the "
                    "conversation (e.g. an appointment time still being worked out, a question they "
                    "hadn't answered yet) — respond like a human who remembers exactly where you "
                    "left off."
                )

            # Funky & Adaptive communication for wrong number / wrong person
            msg_lower = (message or "").lower()
            if any(phrase in msg_lower for phrase in (
                "wrong number", "wrong #", "wrong person", "not steven", "not the person",
                "who is this", "who is that", "who are you", "dont know any", "don't know any"
            )):
                system_prompt += (
                    "\n\nWRONG NUMBER / WRONG PERSON (FUNKY & ADAPTIVE COMMUNICATION):\n"
                    "The recipient just indicated that this is the wrong number, wrong person, or they don't know who we are texting.\n"
                    "Do NOT give a stiff, boring, cold, or robotic apology! Automatically adapt with a charming, humorous, funky response:\n"
                    "- Playfully laugh off the mixup with witty good vibes (e.g. carrier pigeon got lost, wires got crossed, classic wrong number moment 😅).\n"
                    "- Ask a funky/playful question (e.g. since the universe brought us together, are they secretly in the market for killer insurance rates or did fate just hand them a discount, or should you vanish back into the digital sunset?).\n"
                    "- Keep it short (1-2 sentences), funky, and low-pressure so it feels like a cool human texting them.\n"
                )

            # Warm & polite re-engagement for existing customers
            if any(phrase in msg_lower for phrase in (
                "already customer", "already customers", "already a customer",
                "already with allzone", "already working with you", "already a client",
                "current client", "existing client", "current customer", "existing customer",
                "work with allzone", "we use allzone", "i use allzone", "working with allzone already"
            )):
                system_prompt += (
                    "\n\nEXISTING CLIENT (WARM & POLITE RE-ENGAGEMENT):\n"
                    "The recipient just mentioned that they are already a client or partner with AllZone Technologies!\n"
                    "Do NOT send a cold, generic confirmation like 'Got your message' or dismiss them.\n"
                    "- Warmly thank them for partnering with AllZone.\n"
                    "- Politely ask how their project or software is performing, or what new AI/engineering capability they are looking into.\n"
                    "- Keep it sweet, polite, and conversational (1-2 short sentences max). Strictly NEVER use em dashes.\n"
                    "Example phrasing:\n"
                    "\"Oh awesome, thank you so much for partnering with AllZone! How is your system running, or is there a new AI capability or engineering project you'd like to explore?\"\n"
                )
                try:
                    # Automatically elevate lead priority in CRM to Top Priority
                    cur.execute("""
                        UPDATE leads
                        SET tags = array_append(array_remove(tags, 'existing-customer'), 'existing-customer'),
                            score = GREATEST(score, 95),
                            score_band = 'hot',
                            updated_at = NOW()
                        WHERE id = %s
                    """, (lead_id,))
                    task_id = f"task_{uuid.uuid4().hex[:12]}"
                    cur.execute("""
                        INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                        VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                    """, (
                        task_id, lead_id, business_id,
                        f"Priority: Existing Farmers customer {lead.get('first_name') or from_phone} active on iMessage. Check policies for bundle discounts."
                    ))
                    conn.commit()
                    logger.info(f"[sms:inbound] elevated lead {lead_id} to existing-customer hot priority")
                except Exception as tag_err:
                    logger.warning(f"[sms:inbound] failed to elevate existing customer priority: {tag_err}")

            # Sympathetic & human guidance for any stop, decline, or opt-out requests
            system_prompt += (
                "\n\nDECLINES & STOP REQUESTS (WARM & SYMPATHETIC WORDS ONLY):\n"
                "If the recipient indicates they are not interested, want to stop, or ask not to be contacted, "
                "NEVER under any circumstances send robotic, legalistic phrases such as "
                "'You have been unsubscribed and will not receive further messages. Reply START to resubscribe.'\n"
                "Always use sympathetic, warm, human words: acknowledge their preference with empathy, apologize politely for the intrusion, "
                "confirm you will remove them from your list so they won't be bothered, and wish them well.\n"
                "Example: 'No problem at all, completely understand! So sorry to have bothered you. I've taken you off my list right away. Wishing you all the best and take care!'"
            )

            if lead_notes:
                system_prompt += (
                    f"\n\nLEAD CONTEXT: This lead's specific interest is: '{lead_notes}'. "
                    "You already know this, do NOT ask them again what they are interested in. "
                    "Skip that question and move to the next qualifying question."
                )
            lead_email = lead.get("email") or ""
            has_real_email = lead_email and not lead_email.endswith("@sms.lead")
            system_prompt += (
                "\n\nCONTACT INFO: phone and"
                + (" email are" if has_real_email else " email, the phone is")
                + " already on file (you're already texting this number"
                + (", and an email is on record" if has_real_email else "")
                + "). If a step asks you to 'collect the best phone number and email,' that's "
                "already handled by the system automatically — do NOT say a phone number or "
                "email in your reply at all, and never write a bracket placeholder like "
                "'[best phone number provided]' or '[email]'. Just say something like 'our team "
                "will reach out to confirm' without stating any contact detail yourself."
            )
            system_prompt += (
                "\n\nPRICING GUARDRAIL: You may discuss general ranges or what affects cost, but "
                "never state or confirm a specific premium, monthly cost, or coverage amount as "
                "final or binding — even if the lead asks directly or gives their own number and "
                "asks you to confirm it. Always say a licensed agent will confirm the exact numbers. "
                "Avoid reciting rating factors like a brochure (e.g. don't say 'premiums can vary "
                "based on coverage, driving history, and discounts') — that reads like a knowledge-"
                "base answer, not a person. Keep it short and reassuring instead, e.g. 'Honestly it "
                "depends on a few things, but I can't promise a number here — our licensed agent will "
                "get you the real rate.'"
            )
            system_prompt += (
                "\n\nCALL REQUEST ACKNOWLEDGMENT: Whenever the lead asks for a phone call, or agrees "
                "to one you offered, confirm in your own words (following the VOICE guidance above, "
                "not a fixed script) that someone will call them soon — within the hour, not at a "
                "specific time you'd need to pick. Don't offer time windows for this; it's already "
                "happening automatically."
            )
            system_prompt += (
                "\n\nAPPOINTMENT BOOKING MECHANICS: this covers HOW to book once you've already "
                "decided (per QUALIFYING / APPOINTMENT READINESS above) that offering the appointment "
                "is the right move — new, renewing, switching, or existing-customer-wanting-coverage "
                "leads all get the SAME licensed-agent appointment, never a vague 'servicing team' "
                "(that phrase is reserved for genuine account-service requests only, as covered above). "
                "Ask the appointment question as a clear yes/no, don't bundle it with another question "
                "in the same message. If they agree, do NOT say it's booked or that you're setting it up yet — "
                "nothing is actually scheduled until they pick a time. Ask what time works best, "
                "offering 2-3 concrete windows (e.g. morning, afternoon, evening) rather than an "
                "open-ended 'when works for you?'. The moment they answer with ANY of the windows "
                "you offered (e.g. just 'morning'), treat it only as a preference from which to "
                "PROPOSE a slot; it is not approval to book. Do not ask them to narrow the window "
                "down themselves. State the ACTUAL clock time being requested, not just the vague "
                "word — the system books a fixed representative time for each window ONLY when the "
                "lead gave the bare window word with no clock time attached (morning = 9:00 AM, "
                "afternoon = 2:00 PM, evening = 5:00 PM). If the lead's reply names a specific clock "
                "time of their own (e.g. 'afternoon, 2:15pm', 'morning around 9:30'), use THAT exact "
                "time instead — never round or replace a time the lead actually stated with the "
                "window's fixed default. Always name a day together with that time, never a bare time "
                "on its own — if the lead never named a day, that means the soonest one (today, or "
                "tomorrow if that time already passed today); if they did name a day, use that. If they "
                "used an explicit weekday name or calendar date, echo that back directly. But if they "
                "used a RELATIVE reference instead (e.g. 'day after tomorrow', 'in 3 days', 'next "
                "week') — do NOT convert it to a specific weekday name yourself (e.g. never say "
                "'Thursday' for 'day after tomorrow') — day-of-week arithmetic is exactly the kind of "
                "thing language models get wrong even when the current date is known, and a *wrong* "
                "day name is worse than none: confirmed live, 'day after tomorrow' from a Friday got "
                "stated back as 'Thursday', two days off. Use their own words back instead ('the day "
                "after tomorrow', 'in 3 days') — the system resolves the actual calendar date "
                "separately and correctly; you just need to not contradict it with a wrong guess. Avoid "
                "'locked in', 'setting it up', booked, confirmed, or 'have you down' — nothing is "
                "booked yet at this point. State the literal invite email as directed below, and ask "
                "for a real yes/no confirmation that both the slot and email are right — phrase it "
                "however fits the conversation, following the VOICE guidance above, not a template. "
                "Then STOP and wait for their next reply. Only after they answer "
                "with clear approval such as 'yes, that's correct' may the system check availability "
                "and create the appointment. If they correct the time/date or email, restate the "
                "complete corrected slot and email and ask for confirmation again; do not book on "
                "the correction message itself. Only ask about the window again if their answer doesn't match "
                "any window you offered at all. If a specific time or window was already declined "
                "as unavailable earlier in THIS conversation (look for an 'already booked' message "
                "from you), do not offer or confirm that same one again — acknowledge it's taken and "
                "ask them to pick one of the remaining windows, or a different day entirely if none "
                "are left. Do not ask for a phone number (already on file). If "
                "they'd rather keep texting, respect that and continue by text, don't ask again in "
                "the same way right after."
            )
            if has_real_email:
                system_prompt += (
                    f"\n\nAPPOINTMENT EMAIL: This is an exception to the CONTACT INFO rule above — "
                    f"once (and only once) the lead has actually agreed to book the appointment and a "
                    f"time preference, write out the literal address {lead_email} together with the "
                    f"exact proposed day/time, every time you mention the invite — never a vague "
                    f"'your email on file' instead of the actual address (a lead told that literally "
                    f"didn't know what it meant). Ask the lead to confirm both the slot and this "
                    f"email are correct, and wait for their next reply. If they correct either value, "
                    f"restate both corrected details (spelling out the literal address again) and ask "
                    f"again; a correction is not itself final approval."
                )
            else:
                system_prompt += (
                    "\n\nAPPOINTMENT EMAIL: This is an exception to the CONTACT INFO rule above — "
                    "we do NOT have a real email on file for this lead. Once (and only once) they've "
                    "agreed to book and chosen a time preference, ask for the best email for the "
                    "calendar invite. When they provide it, restate the exact proposed day/time and "
                    "literal email, ask them to confirm both, and wait for another reply. Do not book "
                    "on the same message in which they first provide or correct the email."
                )

            # Call outcomes are saved into a separate channel='voice' conversation,
            # so the SMS history query above never sees them — without this, the
            # SMS agent has no idea a call ever happened and will re-ask things
            # already covered on the phone.
            cur.execute("""
                SELECT outcome, summary, duration_seconds, created_at
                FROM voice_calls
                WHERE lead_id = %s AND (summary IS NOT NULL OR transcript IS NOT NULL)
                ORDER BY created_at DESC LIMIT 3
            """, (lead_id,))
            recent_calls = cur.fetchall()
            if recent_calls:
                call_lines = []
                for c in reversed(recent_calls):
                    dur = c["duration_seconds"] or 0
                    call_lines.append(
                        f"- {c['created_at'].strftime('%b %-d, %-I:%M%p')} "
                        f"(outcome: {c['outcome'] or 'unknown'}, {dur // 60}m {dur % 60}s): "
                        f"{c['summary'] or 'no summary available'}"
                    )
                system_prompt += (
                    "\n\nRECENT PHONE CALL HISTORY WITH THIS LEAD (you were not on this call, "
                    "but treat this as already-known information — never ask again about "
                    "anything covered below, and reference it naturally if relevant):\n"
                    + "\n".join(call_lines)
                )

            # The quoted/closed agent (a separate Lead Config rule, see
            # _get_agent_prompt) is meant to work off the deal summary rather
            # than replaying the whole qualification conversation — it's
            # regenerated automatically the moment the lead enters quoted/
            # closed (workflow_engine.on_stage_change). Anchor the reply on
            # that summary and trim the raw history down to just the most
            # recent live exchange, so the model isn't re-deriving context
            # it should already have from the summary.
            reply_history = history
            if lead.get("stage") in ("quoted", "closed"):
                cur.execute("SELECT ai_summary FROM leads WHERE id = %s", (lead_id,))
                summary_row = cur.fetchone()
                if summary_row and summary_row["ai_summary"]:
                    system_prompt += (
                        "\n\nDEAL SUMMARY SO FAR (everything qualified/discussed before this "
                        "point — insurance type, key details, quote given, objections raised. "
                        "Treat all of it as already known, never re-ask it, and pick up exactly "
                        "where it leaves off):\n" + summary_row["ai_summary"]
                    )
                    reply_history = history[-8:]
            elif len(history) > _LONG_CONVO_THRESHOLD:
                # Every reply on a long-running lead was resending the ENTIRE
                # raw history, unbounded, forever — cost and latency grew with
                # every single message, no cap anywhere pre-quoted (the
                # summary above only ever kicked in once a lead reached
                # quoted/closed). Reuses the exact same ai_summary field/
                # mechanism, just triggered by length instead of only by
                # stage. Only regenerates once ~_LONG_CONVO_TAIL new messages
                # have actually accumulated since the last summary, not on
                # every message past the threshold.
                cur.execute("SELECT ai_summary, ai_summary_updated_at FROM leads WHERE id = %s", (lead_id,))
                summary_row = cur.fetchone()
                boundary_msg = history[-(_LONG_CONVO_TAIL + 1)]
                stale = (
                    not summary_row or not summary_row["ai_summary"] or not summary_row["ai_summary_updated_at"]
                    or summary_row["ai_summary_updated_at"] < boundary_msg["created_at"]
                )
                if stale:
                    await trigger_summary_generation(lead_id, business_id)
                    cur.execute("SELECT ai_summary FROM leads WHERE id = %s", (lead_id,))
                    summary_row = cur.fetchone()
                if summary_row and summary_row["ai_summary"]:
                    system_prompt += (
                        "\n\nCONVERSATION SUMMARY SO FAR (this lead's conversation has gotten long — "
                        "everything before the most recent messages below has been condensed here. "
                        "Treat it as already known, never re-ask it):\n" + summary_row["ai_summary"]
                    )
                    reply_history = history[-_LONG_CONVO_TAIL:]

            ai_reply = await _build_ai_reply(system_prompt, reply_history, message, agent["model"])
            # A carrier-side send failure (Claw Messenger/Twilio hiccup, rate limit,
            # unverified-number rejection) must not take the whole reply with
            # it — without this try/except, an exception here used to escape
            # to the function's outer handler and skip _save_message AND every
            # downstream check below (appointment/qualification/call-confirm),
            # silently losing the AI's reply and the turn's progression checks
            # even though the reply was already generated.
            send_status = "delivered"
            send_error = None
            try:
                await asyncio.sleep(_typing_delay_seconds(ai_reply))
                await _send_sms(from_phone, ai_reply, channel)
            except Exception as send_err:
                send_status = "failed"
                send_error = str(send_err)
                logger.error(f"[sms:inbound] send failed for {from_phone}: {send_error}")
                try:
                    task_id = f"task_{uuid.uuid4().hex[:12]}"
                    cur.execute("""
                        INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                        VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                    """, (task_id, lead_id, business_id,
                          f"SMS reply failed to send to {lead.get('first_name') or from_phone}: {send_error[:80]} - Please verify and retry."))
                    conn.commit()
                except Exception as task_err:
                    logger.warning(f"[sms:inbound] failed to create send-failure task: {task_err}")

            _save_message(conv_id, "agent", ai_reply, status=send_status, error_reason=send_error, channel=channel)
            await transition_via_crm_api(lead_id, business_id, "welcome_sms_sent")
            logger.info(f"[sms:inbound] AI reply processed for {from_phone} (status={send_status}): {ai_reply[:60]}")


            # EXISTING CUSTOMER SERVICE REQUESTS (see system prompt) tells the
            # bot to say it's connecting the lead to the servicing team — but
            # nothing ever actually did that. Confirmed live: a lead got told
            # "please hold" and then genuinely nothing happened, no human ever
            # notified. Deterministic keyword check on the bot's own reply
            # (not an LLM call) since the exact phrase is dictated by the
            # prompt itself — cheap and reliable for this one.
            if "servicing team" in ai_reply.lower():
                try:
                    task_id = f"task_{uuid.uuid4().hex[:12]}"
                    cur.execute("""
                        INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                        VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                    """, (task_id, lead_id, business_id,
                          f"Servicing request from {lead.get('first_name') or from_phone} — bot told them "
                          f"someone would follow up. Review conversation and reach out."))
                    conn.commit()
                    logger.info(f"[sms:inbound] servicing handoff → task {task_id} created for staff")
                except Exception as task_err:
                    logger.warning(f"[sms:inbound] failed to create servicing task: {task_err}")

            full_history = history + [
                {"role": "user", "content": message},
                {"role": "agent", "content": ai_reply},
            ]
            appointment_engaged = await _check_sms_appointment(conv_id, lead_id, business_id, from_phone, full_history)
            await _check_lead_progression(lead_id, business_id, from_phone, full_history)
            # Booking (or declining) an appointment THIS turn already means
            # someone will follow up with the lead — skip the redundant
            # "does this also mean they want a call" check rather than let
            # two independent automations both decide they're the one
            # responsible for following up. Note this only guards the SAME
            # turn: a lead who first agrees to "book an appointment" with no
            # time yet (nothing for _check_sms_appointment to engage with)
            # and only names a time on a LATER turn was still able to get an
            # unsolicited call in between — confirmed live. That gap is now
            # closed at the source: _check_call_confirmation's own classifier
            # no longer treats "agreed to book an appointment" as call
            # consent, only an explicit request/agreement to a phone call.
            if not appointment_engaged:
                await _check_call_confirmation(lead_id, business_id, from_phone, full_history, conv_id)
        else:
            logger.info(f"[sms:inbound] AI paused for conv {conv_id}")
            conn.commit()

    except Exception as e:
        logger.error(f"[sms:inbound] Error: {e}")
        conn.rollback()
        # Guarantee the user's message is preserved in the database even if an error occurred early
        if conv_id and message:
            try:
                _chk_conn = get_conn()
                _chk_cur = _chk_conn.cursor()
                _chk_cur.execute(
                    "SELECT 1 FROM messages WHERE conversation_id = %s AND role = 'user' AND content = %s LIMIT 1",
                    (conv_id, message),
                )
                if not _chk_cur.fetchone():
                    _save_message(conv_id, "user", message)
                _chk_cur.close()
                _chk_conn.close()
            except Exception:
                pass
        # Second, immediate layer of protection alongside check_orphaned_replies
        # (which only catches this ~2min later, on a poll cycle) — a Python
        # exception ANYWHERE above (LLM call failure, a DB hiccup, a bug) used
        # to just log here and leave the lead's message unanswered with zero
        # staff visibility until the watchdog eventually noticed. This closes
        # that gap immediately instead of waiting on the poller, and also
        # tries to give the lead something rather than dead air.
        if lead_id and business_id:
            try:
                task_id = f"task_{uuid.uuid4().hex[:12]}"
                cur2 = dict_cursor(conn)
                cur2.execute("""
                    INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                    VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                """, (task_id, lead_id, business_id,
                      f"Reply generation failed for lead {from_phone} — error: {str(e)[:150]}. Verify and follow up."))
                conn.commit()
                cur2.close()
            except Exception as task_err:
                logger.warning(f"[sms:inbound] failed to create error task: {task_err}")
            fallback_msg = sanitize_text("Got your message! I will check into this and follow up with you shortly.")
            try:
                await _send_sms(from_phone, fallback_msg, channel)
                if conv_id:
                    _save_message(conv_id, "agent", fallback_msg)
            except Exception:
                pass  # best-effort — the staff task above is the real backstop
    finally:
        cur.close(); conn.close()

    return


# ── POST /api/sms/inbound — Twilio webhook (WhatsApp only now) ───────────────

@router.post("/inbound")
async def sms_inbound(
    From: str = Form(...),
    Body: str = Form(...),
    To: str = Form(default=""),
):
    from_raw = From.strip()
    message = Body.strip()
    is_whatsapp = from_raw.startswith("whatsapp:")
    from_phone = from_raw.replace("whatsapp:", "").strip()
    channel = "whatsapp" if is_whatsapp else "sms"
    await _handle_inbound_message(from_phone, message, channel)
    return PlainTextResponse("<?xml version='1.0'?><Response></Response>", media_type="text/xml")


# ── POST /api/sms/inbound-textbee — TextBee Android SMS Gateway webhook ─────────

@router.post("/inbound-textbee")
async def sms_inbound_textbee(request: Request):
    """
    Receives incoming SMS webhook from TextBee Android device (MESSAGE_RECEIVED event).
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    from_phone = (payload.get("sender") or payload.get("from") or "").strip()
    message = (payload.get("message") or payload.get("body") or "").strip()
    sms_id = payload.get("smsId") or payload.get("_id")

    if not from_phone or not message:
        return {"status": "ignored", "reason": "missing sender or message"}

    # Ignore automated verification codes
    digits = "".join(c for c in from_phone if c.isdigit())
    if len(digits) < 7:
        return {"status": "ignored", "reason": "non-phone sender"}

    # Deduplicate via processed_inbound_sms
    if sms_id:
        from core.db import get_conn, get_dict_cursor as dict_cursor
        conn = get_conn()
        cur = dict_cursor(conn)
        try:
            cur.execute("SELECT 1 FROM processed_inbound_sms WHERE sms_id = %s", (sms_id,))
            if cur.fetchone():
                return {"status": "already_processed"}
            cur.execute(
                "INSERT INTO processed_inbound_sms (sms_id, sender, message) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (sms_id, from_phone, message)
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    logger.info(f"[textbee:webhook] Received inbound text from {from_phone}: {message[:40]}")
    await _handle_inbound_message(from_phone, message, "sms")
    return {"status": "ok"}



# ── POST /api/sms/simulate-inbound — staff testing helper ────────────────────
# The Conversations compose box only ever sends AS the business (role='human',
# an outbound text) — there was no way to type what the LEAD would say and
# see the bot react for real. Staff were typing lead-side test replies into
# that box anyway, which actually sent them as a nonsense outbound message
# from the business and never triggered an AI reply at all. This runs the
# exact same inbound pipeline a real text does (AI reply, stage transitions,
# decline/qualify/quote checks) — just triggered from the CRM instead of a
# real phone.

class SimulateInboundBody(BaseModel):
    conversation_id: str
    message: str


@router.post("/simulate-inbound")
async def simulate_inbound(body: SimulateInboundBody, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT l.phone, c.channel
            FROM conversations c JOIN leads l ON l.id = c.lead_id
            WHERE c.id = %s AND c.business_id = %s
        """, (body.conversation_id, business_id))
        row = cur.fetchone()
        if not row or not row["phone"]:
            raise HTTPException(status_code=404, detail="Conversation or lead phone not found")
        phone = row["phone"]
        channel = row["channel"] if row["channel"] in ("sms", "whatsapp") else "sms"
    finally:
        cur.close(); conn.close()

    await _handle_inbound_message(phone, body.message, channel)
    return {"success": True}


# ── POST /api/sms/send-raw — internal, server-to-server (crm-service) ────────
# The single place that actually sends a raw SMS/WhatsApp message. crm-service
# calls this instead of keeping its own Twilio/Claw Messenger client, so there's
# exactly one implementation of "how we send a text" in the whole system.

class SendRawSMSBody(BaseModel):
    to: str
    body: str
    channel: str = "sms"
    force: bool = False


@router.post("/send-raw")
async def send_raw_sms(body: SendRawSMSBody, request: Request):
    get_user(request)  # any valid shared-secret JWT — just needs to be a trusted caller
    result = await _send_sms(body.to, body.body, body.channel, body.force)
    return {"success": True, "data": result}


# ── POST /api/sms/send — send first SMS to a lead ────────────────────────────

class SendSMSBody(BaseModel):
    lead_id: str
    message: Optional[str] = None


@router.post("/send")
async def send_sms(body: SendSMSBody, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT id, first_name, phone, tags, stage, notes FROM leads WHERE id = %s AND business_id = %s",
            (body.lead_id, business_id),
        )
        lead = cur.fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        if not lead["phone"]:
            raise HTTPException(status_code=400, detail="Lead has no phone number")

        # TCPA — this is a business-initiated outbound send (not a reply to
        # something the lead just texted), so it must respect quiet hours.
        allowed, reason = _is_within_quiet_hours(business_id)
        if not allowed:
            raise HTTPException(status_code=422, detail=f"Blocked by quiet hours — {reason}")

        conv_id = _get_or_create_sms_conv(lead["id"], business_id)

        if body.message:
            text = body.message
        else:
            agent = _get_agent_prompt(business_id, lead["tags"] or [], lead.get("stage"))
            if agent is None:
                raise HTTPException(status_code=422, detail="No AI agent is configured for this lead's tags/stage yet. Add a Lead Config rule first, or pass an explicit message.")
            prompt = agent["prompt"]
            text = await _build_ai_reply(
                prompt, [],
                f"Say a brief, friendly opening message to {lead['first_name']} to start a conversation.",
                agent["model"],
            )

        try:
            send_resp = await _send_sms(lead["phone"], text)
            _save_message(conv_id, "agent", text, status="delivered", channel="imessage")
            await transition_via_crm_api(lead["id"], business_id, "welcome_sms_sent")

            return {
                "success": True,
                "data": {"sid": send_resp.get("sid"), "message": text, "conversation": conv_id},
            }
        except Exception as send_err:
            _save_message(conv_id, "agent", text, status="failed", error_reason=str(send_err), channel="imessage")
            raise
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"[sms:send] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# ── POST /api/sms/send-bulk — broadcast SMS to leads ─────────────────────────

class BulkSMSBody(BaseModel):
    tag: Optional[str] = None
    status: Optional[str] = "new"
    message: Optional[str] = None


@router.post("/send-bulk")
async def send_bulk_sms(body: BulkSMSBody, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        allowed, reason = _is_within_quiet_hours(business_id)
        if not allowed:
            raise HTTPException(status_code=422, detail=f"Blocked by quiet hours — {reason}")

        query = "SELECT id, first_name, phone, tags, stage, notes FROM leads WHERE business_id = %s AND phone != '' AND opted_out IS NOT TRUE"
        params: list = [business_id]
        if body.status:
            query += " AND sub_status = %s"; params.append(body.status)
        if body.tag:
            query += " AND %s = ANY(tags)"; params.append(body.tag)
        query += " LIMIT 100"
        cur.execute(query, params)
        leads = cur.fetchall()

        sent, failed, results = 0, 0, []
        for lead in leads:
            try:
                conv_id = _get_or_create_sms_conv(lead["id"], business_id)
                if body.message:
                    text = body.message
                else:
                    agent = _get_agent_prompt(business_id, lead["tags"] or [], lead.get("stage"))
                    if agent is None:
                        raise ValueError(f"no agent configured for tags={lead['tags']} stage={lead.get('stage')}")
                    prompt = agent["prompt"]
                    text = await _build_ai_reply(
                        prompt, [],
                        f"Say a brief, friendly opening message to {lead['first_name']}.",
                        agent["model"],
                    )
                await _send_sms(lead["phone"], text)
                _save_message(conv_id, "agent", text, status="delivered", channel="imessage")
                await transition_via_crm_api(lead["id"], business_id, "welcome_sms_sent")
                sent += 1
                results.append({"lead_id": lead["id"], "phone": lead["phone"], "status": "sent"})
            except Exception as e:
                _save_message(conv_id, "agent", text, status="failed", error_reason=str(e), channel="imessage")
                failed += 1
                results.append({"lead_id": lead["id"], "phone": lead["phone"], "status": "failed", "error": str(e)})

        conn.commit()
        return {"success": True, "data": {"sent": sent, "failed": failed, "results": results}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# ── GET /api/sms/safety-status ───────────────────────────────────────────────
@router.get("/safety-status")
def get_safety_status():
    """Returns current safety and circuit breaker metrics for the outbound iMessage/SMS pipeline."""
    return {"success": True, "data": circuit_breaker.get_status()}


# ── POST /api/sms/reset-circuit-breaker ──────────────────────────────────────
@router.post("/reset-circuit-breaker")
async def reset_circuit_breaker(request: Request):
    """Allows an administrator to manually unpause sending and reset the circuit breaker."""
    get_user(request)
    result = await circuit_breaker.reset()
    return {"success": True, "data": result}

