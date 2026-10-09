"""
Twilio Voice Bot — routes only.
Business logic lives in core/ and voice/prompt.py + voice/session.py.
"""

import json
import asyncio
import logging
from typing import List, Dict, Tuple
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Request, Response

from core.db       import get_conn, get_dict_cursor, DEFAULT_BUSINESS_ID
from core.sms      import send_confirmation
from core.calendar import sync_appointment
from core.hubspot  import sync_contact_and_meeting
from core.gmail    import send_appointment_confirmation
from core.config   import OPENAI_API_KEY, TWIML_BASE_URL
from core.llm_retry import post_with_retry
from voice.prompt         import build_date_lookup
from voice.medical_prompt import build_medical_prompt, DEFAULT_MEDICAL_PROMPT
from voice                import session as sess

logger   = logging.getLogger(__name__)
router   = APIRouter(prefix="/api/twilio")
BASE_URL = TWIML_BASE_URL


# ── Helpers ───────────────────────────────────────────────────────────────────

def escape_xml(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


async def _get_business_services(business_id: str) -> list:
    """Return list of {name, provider, specialty} for a business from DB."""
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        cur.execute("""
            SELECT s.name, p.name AS provider, p.specialty
            FROM provider_services ps
            JOIN services  s ON ps.service_id  = s.id
            JOIN providers p ON ps.provider_id = p.id
            WHERE s.business_id = %s AND s.is_active = 1
            ORDER BY s.name
        """, (business_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{"name": r["name"], "provider": r["provider"], "specialty": r["specialty"]} for r in rows]
    except Exception as e:
        logger.warning(f"[services] fetch failed: {e}")
        return []


async def _get_business(to_phone: str) -> Tuple[str, str]:
    """Return (business_id, system_prompt) for the dialled number."""
    try:
        biz_id = DEFAULT_BUSINESS_ID
        biz_name = "AllZone Scheduler"
        custom_prompt = None

        if to_phone:
            conn = get_conn()
            cur  = get_dict_cursor(conn)
            cur.execute(
                "SELECT id, name, system_prompt FROM businesses WHERE twilio_number = %s LIMIT 1",
                (to_phone,),
            )
            biz = cur.fetchone()
            cur.close(); conn.close()
            if biz:
                biz_id        = biz["id"]
                biz_name      = biz["name"] or biz_name
                custom_prompt = biz["system_prompt"]

        # If business has a manually set custom prompt, use it as-is
        if custom_prompt:
            return biz_id, custom_prompt

        # Build medical prompt from DB services
        services = await _get_business_services(biz_id)
        system_prompt = build_medical_prompt(services, business_name=biz_name) if services else DEFAULT_MEDICAL_PROMPT
        return biz_id, system_prompt

    except Exception as e:
        logger.warning(f"[business] lookup failed: {e}")
    return DEFAULT_BUSINESS_ID, DEFAULT_MEDICAL_PROMPT


async def _get_lead_context(phone: str, business_id: str) -> tuple[str, str]:
    """Return (first_name, sms_history_text) for the calling phone number."""
    if not phone:
        return "", ""
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        # Get lead name
        cur.execute(
            "SELECT id, first_name FROM leads WHERE phone = %s AND business_id = %s LIMIT 1",
            (phone, business_id)
        )
        lead = cur.fetchone()
        if not lead:
            cur.close(); conn.close()
            return "", ""
        first_name = lead["first_name"] or ""
        # Get recent SMS/WhatsApp conversation
        cur.execute("""
            SELECT id, channel FROM conversations
            WHERE lead_id = %s AND channel IN ('sms','whatsapp')
            ORDER BY updated_at DESC LIMIT 1
        """, (lead["id"],))
        conv = cur.fetchone()
        history_text = ""
        if conv:
            cur.execute("""
                SELECT role, content FROM messages
                WHERE conversation_id = %s ORDER BY created_at ASC LIMIT 20
            """, (conv["id"],))
            msgs = cur.fetchall()
            if msgs:
                channel_label = "WhatsApp" if conv["channel"] == "whatsapp" else "SMS"
                history_text = f"\n\nPREVIOUS {channel_label.upper()} CONVERSATION WITH THIS LEAD:\n"
                for m in msgs:
                    label = "Agent" if m["role"] in ("agent", "assistant") else lead["first_name"] or "Lead"
                    history_text += f"{label}: {m['content']}\n"
                history_text += "\nThis lead is calling in. Resume naturally — do NOT repeat questions already answered above."
        cur.close(); conn.close()
        return first_name, history_text
    except Exception as e:
        logger.warning(f"[lead_context] DB error: {e}")
        return "", ""


async def _get_appointment_context(phone: str, business_id: str) -> str:
    if not phone:
        return ""
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        cur.execute("""
            SELECT s.name as service, p.name as provider, a.start_time, a.status
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            LEFT JOIN services  s ON a.service_id  = s.id
            LEFT JOIN providers p ON a.provider_id = p.id
            WHERE u.phone = %s AND a.business_id = %s
              AND a.status NOT IN ('cancelled','completed')
            ORDER BY a.start_time ASC LIMIT 3
        """, (phone, business_id))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if not rows:
            return ""
        lines = []
        for r in rows:
            dt       = r["start_time"]
            date_str = dt.strftime("%A, %B %-d") if dt else "Unknown"
            time_str = dt.strftime("%-I:%M %p")  if dt else ""
            lines.append(f"- {r['service'] or 'Appointment'} with {r['provider'] or 'our team'} on {date_str} at {time_str} ({r['status']})")
        return "\n\nExisting appointments for this caller:\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"[context] DB error: {e}")
        return ""


async def _get_booked_slots(business_id: str) -> str:
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        cur.execute("""
            SELECT start_time FROM appointments
            WHERE business_id = %s
              AND status NOT IN ('cancelled','canceled','no_show')
              AND start_time >= NOW()
              AND start_time <= NOW() + INTERVAL '14 days'
            ORDER BY start_time ASC
        """, (business_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if not rows:
            return ""
        slots = [r["start_time"].strftime("%Y-%m-%d at %-I:%M %p") for r in rows]
        return "\n\nAlready booked slots (do NOT offer these):\n" + "\n".join(f"- {s}" for s in slots)
    except Exception as e:
        logger.warning(f"[booked_slots] DB error: {e}")
        return ""


async def conversation_twiml(text: str) -> str:
    action  = f"{BASE_URL}/api/twilio/conversation"
    escaped = escape_xml(text)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" action="{action}" method="POST" timeout="10" speechTimeout="auto">
    <Say voice="alice">{escaped}</Say>
  </Gather>
  <Redirect method="POST">{action}</Redirect>
</Response>"""


async def get_ai_response(call_sid: str, user_input: str,
                          from_phone: str = "", to_phone: str = "") -> str:
    sess.cleanup()

    if not await sess.get(call_sid):
        business_id, system_prompt = await _get_business(to_phone)
        appt_context = await _get_appointment_context(from_phone, business_id)
        booked_slots = await _get_booked_slots(business_id)
        await sess.create(
            call_sid,
            system_prompt + appt_context + booked_slots,
            business_id,
        )

    await sess.append(call_sid, "user", user_input)

    session = await sess.get(call_sid)
    try:
        # Per-turn latency-critical — this is the live spoken reply on an
        # active call. Previously served by Groq specifically for speed;
        # gpt-4o-mini is typically slower per call. Watch [timing] logs after
        # this migration for turns that feel laggy. Retry budget kept tight
        # (2 attempts, short backoff) here specifically because this is live —
        # unlike background/post-call calls, a caller is waiting in real time.
        async with httpx.AsyncClient(timeout=15) as client:
            res = await post_with_retry(
                client, "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model":       "gpt-4o-mini",
                    "messages":    session["history"],
                    "max_tokens":  100,
                    "temperature": 0.5,
                },
                max_attempts=2, base_delay=0.5, label="voice:live_turn",
            )
        text = res.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[openai] Error: {e}")
        text = "I am sorry, I could not process that. Please try again."

    text = text or "I am sorry, I could not process that. Please try again."
    await sess.append(call_sid, "assistant", text)
    return text


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/inbound")
async def inbound(request: Request):
    form       = await request.form()
    call_sid   = str(form.get("CallSid", "")).strip()
    from_phone = str(form.get("From", "")).strip()
    to_phone   = str(form.get("To", "")).strip()

    if call_sid:
        business_id, _ = await _get_business(to_phone)
        try:
            conn = get_conn()
            cur  = get_dict_cursor(conn)
            cur.execute("SELECT id FROM leads WHERE phone = %s AND business_id = %s LIMIT 1", (from_phone, business_id))
            lead_row = cur.fetchone()
            cur.execute("""
                INSERT INTO voice_calls (id, call_id, appointment_id, provider, status, direction, patient_phone, lead_id, created_at, updated_at)
                VALUES (%s, %s, NULL, 'twilio', 'in-progress', 'inbound', %s, %s, NOW(), NOW())
                ON CONFLICT (call_id) DO NOTHING
            """, (f"inbound_{call_sid}", call_sid, from_phone, lead_row["id"] if lead_row else None))
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            logger.error(f"[inbound] DB insert failed: {e}")

    business_id, system_prompt = await _get_business(to_phone)
    first_name, sms_history   = await _get_lead_context(from_phone, business_id)
    appt_context              = await _get_appointment_context(from_phone, business_id)

    if first_name:
        greeting = f"Hey {first_name}! This is Michael. Great to hear from you — how can I help?"
    else:
        greeting = "Hey! This is Michael. How can I help you today?"

    # Pre-seed session with lead name + SMS history so AI is informed from first response
    if call_sid:
        full_prompt = system_prompt + sms_history + appt_context
        await sess.create(call_sid, full_prompt, business_id)

    twiml = await conversation_twiml(greeting)
    return Response(content=twiml, media_type="text/xml")


@router.post("/start")
async def start(request: Request):
    greeting = "Hello, this is James from AllZone Scheduler. How can I help you today?"
    action   = f"{BASE_URL}/api/twilio/conversation"
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="alice">{escape_xml(greeting)}</Say>
  <Gather input="speech" action="{action}" method="POST" timeout="6" speechTimeout="auto"></Gather>
  <Say voice="alice">I did not catch that. Thank you for your time. Goodbye!</Say>
</Response>"""
    return Response(content=twiml, media_type="text/xml")


@router.post("/conversation")
async def conversation(request: Request):
    form       = await request.form()
    call_sid   = str(form.get("CallSid", "")).strip()
    speech     = str(form.get("SpeechResult", "")).strip()
    from_phone = str(form.get("From", "")).strip()
    to_phone   = str(form.get("To", "")).strip()

    if not speech:
        twiml = await conversation_twiml("I did not quite catch that. Could you please repeat?")
        return Response(content=twiml, media_type="text/xml")

    import time as _time
    logger.info(f"[conversation] CallSid={call_sid} from={from_phone} user={speech!r}")
    t0 = _time.perf_counter()
    try:
        t1 = _time.perf_counter()
        ai_text = await get_ai_response(call_sid, speech, from_phone, to_phone)
        t2 = _time.perf_counter()
        logger.info(f"[conversation] CallSid={call_sid} aria={ai_text!r}")
        twiml   = await conversation_twiml(ai_text)
        t3 = _time.perf_counter()
        logger.info(
            f"[timing] llm={t2-t1:.2f}s  tts={t3-t2:.2f}s  total={t3-t0:.2f}s"
        )
    except Exception as e:
        logger.error(f"[conversation] Error: {e}")
        twiml = await conversation_twiml("I am having a little trouble right now. Please try again.")

    return Response(content=twiml, media_type="text/xml")


@router.post("/status")
async def status_callback(request: Request):
    form        = await request.form()
    call_sid    = str(form.get("CallSid", "")).strip()
    call_status = str(form.get("CallStatus", "")).lower()
    direction   = str(form.get("Direction", "")).lower()
    from_phone  = str(form.get("From", "")).strip()
    to_phone    = str(form.get("To", "")).strip()
    duration    = int(form.get("CallDuration", 0) or 0)

    patient_phone = to_phone if direction.startswith("outbound") else from_phone

    status_map = {
        "completed": ("ended",  "confirmed"),
        "no-answer": ("ended",  "no_answer"),
        "busy":      ("failed", "failed"),
        "failed":    ("failed", "failed"),
        "canceled":  ("failed", "failed"),
    }
    if call_status not in status_map:
        return Response(status_code=204)

    normalized_status, normalized_outcome = status_map[call_status]

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE voice_calls SET status=%s, outcome=%s, duration_seconds=%s, updated_at=NOW() WHERE call_id=%s",
            (normalized_status, normalized_outcome, duration, call_sid),
        )
        conn.commit(); cur.close(); conn.close()
        logger.info(f"[status] {call_sid} → {call_status}")
    except Exception as e:
        logger.error(f"[status] DB update failed: {e}")

    session = await sess.pop(call_sid)

    if call_status == "completed" and session and patient_phone:
        business_id = session.get("business_id", DEFAULT_BUSINESS_ID)
        asyncio.create_task(
            _extract_and_save(call_sid, patient_phone, session["history"], business_id)
        )

    return Response(status_code=204)


# ── Appointment extraction ────────────────────────────────────────────────────

async def _extract_and_save(call_sid: str, from_phone: str,
                            history: List[Dict], business_id: str):
    if not OPENAI_API_KEY:
        return

    transcript = "\n".join(
        f"{'Patient' if m['role'] == 'user' else 'James'}: {m['content']}"
        for m in history if m["role"] != "system"
    )

    extract_prompt = f"""Extract appointment details from this call transcript. Return ONLY valid JSON, nothing else.
Format: {{"name": "patient full name or null", "service": "service name or null", "doctor": "doctor name or null", "date": "YYYY-MM-DD or null", "time": "HH:MM (24hr) or null", "email": "valid email or null", "booked": true/false}}
Email rules:
- Convert spoken email to proper format: "ali at gmail dot com" → "ali@gmail.com"
- "underscore" → "_", "dot" → ".", "dash" or "hyphen" → "-"
- If no email mentioned, return null

IMPORTANT — use ONLY these exact date mappings:
{build_date_lookup()}

Rules:
- If patient said "morning" with no exact time, use "09:00"
- If patient said "afternoon" with no exact time, use "14:00"
- If patient said "evening" with no exact time, use "17:00"
- If no appointment was confirmed, return {{"booked": false}}

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
                    "max_tokens":  150,
                    "temperature": 0,
                },
                label="voice:extract",
            )
        raw    = res.json()["choices"][0]["message"]["content"].strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
    except Exception as e:
        logger.error(f"[extract] Failed to parse: {e}")
        return

    if not parsed.get("booked") or not parsed.get("date") or not parsed.get("time"):
        logger.info("[extract] No appointment found in conversation")
        return

    ALLOWED_HOURS = [10, 14, 16]
    try:
        raw_start = datetime.strptime(f"{parsed['date']} {parsed['time']}", "%Y-%m-%d %H:%M")
    except Exception:
        logger.error(f"[extract] Invalid date/time: {parsed['date']} {parsed['time']}")
        return

    closest_hour = min(ALLOWED_HOURS, key=lambda h: abs(h - raw_start.hour))
    start_time   = raw_start.replace(hour=closest_hour, minute=0, second=0)
    end_time     = start_time + timedelta(hours=1)

    name_parts = (parsed.get("name") or "Inbound Caller").split()
    first_name = name_parts[0] if name_parts else "Inbound"
    last_name  = " ".join(name_parts[1:]) if len(name_parts) > 1 else "Caller"

    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        cur.execute("SELECT id, role FROM users WHERE phone = %s LIMIT 1", (from_phone,))
        existing       = cur.fetchone()
        is_admin_staff = existing and existing["role"] in ("admin", "staff", "super_admin")

        if existing and not is_admin_staff:
            user_id = existing["id"]
            if parsed.get("email"):
                cur.execute(
                    "UPDATE users SET first_name=%s, last_name=%s, email=%s, updated_at=NOW() WHERE id=%s",
                    (first_name, last_name, parsed["email"], user_id),
                )
            else:
                cur.execute(
                    "UPDATE users SET first_name=%s, last_name=%s, updated_at=NOW() WHERE id=%s",
                    (first_name, last_name, user_id),
                )
        else:
            user_id      = f"usr_inbound_{call_sid[-8:]}"
            caller_email = parsed.get("email") or f"{from_phone.replace('+','')}@inbound.call"
            cur.execute("""
                INSERT INTO users (id, phone, first_name, last_name, email, password_hash, business_id, role, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 'inbound-caller-no-login', %s, 'customer', NOW(), NOW())
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

        if provider_id:
            cur.execute("""
                SELECT id FROM appointments
                WHERE provider_id=%s AND start_time=%s
                  AND status NOT IN ('cancelled','canceled','no_show')
                LIMIT 1
            """, (provider_id, start_time))
            if cur.fetchone():
                logger.warning(f"[extract] Conflict at {start_time} — aborting")
                return

        cur.execute("SELECT id, email FROM leads WHERE phone = %s LIMIT 1", (from_phone,))
        lead_row = cur.fetchone()
        lead_id    = lead_row["id"] if lead_row else None
        lead_email = lead_row["email"] if lead_row else None

        appt_id = f"appt_inbound_{call_sid[-8:]}"
        cur.execute("""
            INSERT INTO appointments (id, business_id, user_id, service_id, provider_id, start_time, end_time, status, created_via, notes, lead_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', 'voice_inbound', %s, %s, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """, (appt_id, business_id, user_id, service_id, provider_id,
              start_time, end_time, f"Booked via inbound call {call_sid}", lead_id))

        cur.execute("UPDATE voice_calls SET appointment_id=%s WHERE call_id=%s", (appt_id, call_sid))
        conn.commit()
        logger.info(f"[extract] Saved {appt_id} for {from_phone}")

    except Exception as e:
        conn.rollback()
        logger.error(f"[extract] DB error: {e}")
        return
    finally:
        cur.close()
        conn.close()

    # Phone callers essentially never spell out their email out loud, so
    # parsed["email"] (extracted from the live transcript) is almost always
    # empty — fall back to the lead's on-file email (from SMS/signup) so the
    # calendar invite + confirmation email still go out, same as the SMS and
    # manual-booking paths.
    calendar_parsed = dict(parsed)
    if not calendar_parsed.get("email") and lead_email:
        calendar_parsed["email"] = lead_email

    await asyncio.gather(
        sync_appointment(appt_id, calendar_parsed, from_phone, call_sid, start_time, end_time, get_conn),
        send_confirmation(from_phone, parsed),
        sync_contact_and_meeting(appt_id, from_phone, calendar_parsed, start_time, end_time),
        send_appointment_confirmation(
            calendar_parsed.get("email"), calendar_parsed.get("name") or "there",
            calendar_parsed.get("service") or "your appointment", start_time,
        ),
        return_exceptions=True,
    )
