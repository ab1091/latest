import logging
import httpx
from datetime import datetime

from core import claw_messenger
from core.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWIML_BASE_URL

logger = logging.getLogger(__name__)


async def send_confirmation(to_phone: str, parsed: dict):
    try:
        def _clean(val):
            return None if (not val or str(val).lower() in ("null", "none", "")) else val

        patient_name = _clean(parsed.get("name")) or "Patient"
        service      = _clean(parsed.get("service")) or "Appointment"
        doctor       = _clean(parsed.get("doctor")) or ""
        date_str     = parsed.get("date") or ""
        time_str     = parsed.get("time") or ""

        if date_str and time_str:
            dt       = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            date_fmt = dt.strftime("%A, %B %-d")
            time_fmt = dt.strftime("%-I:%M %p")
        else:
            date_fmt = date_str
            time_fmt = time_str

        doctor_part = f" with {doctor}" if doctor else ""
        body = (
            f"Hi {patient_name}! Your {service}{doctor_part} is confirmed "
            f"for {date_fmt} at {time_fmt}. See you then! - AllZone Scheduler"
        )

        result = await claw_messenger.send_message(to_phone, body)
        logger.info(f"[sms] Sent to {to_phone} — handle: {result.get('sid')}")
    except Exception as e:
        logger.error(f"[sms] Failed: {e}")


async def send_recording(to_phone: str, caller_name: str, call_id: str):
    """Send call recording link to the lead via their preferred channel (SMS or WhatsApp).

    Always links to our own /api/calls/{call_id}/recording proxy — never the raw
    Azure blob URL. The Azure storage account has public access disabled
    (PublicAccessNotPermitted), so a raw blob link 404s/errors for anyone who
    isn't holding a signed SAS URL; confirmed live when exactly that link was
    texted out and clicked. Our proxy endpoint serves the locally-cached file
    (or signs+fetches it on demand) instead.
    """
    if not call_id:
        return
    if not TWIML_BASE_URL:
        logger.error("[sms:recording] TWILIO_TWIML_BASE_URL not configured — cannot build a public recording link")
        return
    recording_url = f"{TWIML_BASE_URL.rstrip('/')}/api/calls/{call_id}/recording"
    try:
        from core.config import TWILIO_WHATSAPP_FROM
        from core.db import get_conn, get_dict_cursor

        # Look up lead name and preferred channel from DB
        name    = caller_name or "there"
        channel = "sms"
        try:
            conn = get_conn(); cur = get_dict_cursor(conn)
            cur.execute(
                "SELECT first_name, preferred_channel FROM leads WHERE phone = %s LIMIT 1",
                (to_phone,)
            )
            row = cur.fetchone()
            if row:
                name    = row.get("first_name") or name
                channel = row.get("preferred_channel") or "sms"
            cur.close(); conn.close()
        except Exception:
            pass

        body = (
            f"Hi {name}! Thanks for your time on the call. "
            f"Here's your call recording: {recording_url}"
        )

        if channel == "whatsapp":
            from_num = TWILIO_WHATSAPP_FROM or "whatsapp:+14155238886"
            to_num   = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                    auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                    data={"To": to_num, "From": from_num, "Body": body},
                )
            logger.info(f"[sms:recording] Sent to {to_phone} via {channel} — SID: {res.json().get('sid')}")
        else:
            result = await claw_messenger.send_message(to_phone, body)
            logger.info(f"[sms:recording] Sent to {to_phone} via {channel} — handle: {result.get('sid')}")
    except Exception as e:
        logger.error(f"[sms:recording] Failed: {e}")
