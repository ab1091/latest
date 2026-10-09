import logging
import httpx
from datetime import datetime

from core.config import GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, AGENCY_CALENDAR_EMAIL
from core.timezone import BUSINESS_TIMEZONE

logger = logging.getLogger(__name__)


async def _get_token() -> str | None:
    if not (GOOGLE_REFRESH_TOKEN and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id":     GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "refresh_token": GOOGLE_REFRESH_TOKEN,
                    "grant_type":    "refresh_token",
                },
            )
        return res.json().get("access_token")
    except Exception as e:
        logger.error(f"[calendar] Token fetch error: {e}")
        return None


async def sync_appointment(appt_id: str, parsed: dict, from_phone: str,
                           call_sid: str, start_time: datetime, end_time: datetime,
                           get_conn):
    token = await _get_token()
    if not token:
        logger.warning("[calendar] No access token — skipping sync")
        return
    try:
        patient_name = parsed.get("name") or "Inbound Caller"
        service_name = parsed.get("service") or "Appointment"
        
        attendees = []
        agency_email = (AGENCY_CALENDAR_EMAIL or "shieldsquadagency@gmail.com").strip()
        if agency_email:
            attendees.append({"email": agency_email})
        if parsed.get("email") and parsed["email"].strip().lower() != agency_email.lower():
            attendees.append({"email": parsed["email"].strip()})

        event_body = {
            "summary":     f"{service_name} — {patient_name}",
            "description": f"Booked via inbound call.\nPatient: {patient_name}\nPhone: {from_phone}\nCall ID: {call_sid}",
            # start_time/end_time are naive datetimes holding the business's
            # LOCAL wall-clock time (e.g. "9:00 AM" Central, exactly what the
            # lead agreed to) — declaring them "UTC" here used to make Google
            # display the invite 5-6 hours off from the time actually booked.
            "start":       {"dateTime": start_time.isoformat(), "timeZone": BUSINESS_TIMEZONE},
            "end":         {"dateTime": end_time.isoformat(),   "timeZone": BUSINESS_TIMEZONE},
            "attendees":   attendees,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            cal_res = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events?sendUpdates=all",
                headers={"Authorization": f"Bearer {token}"},
                json=event_body,
            )

        if cal_res.is_success:
            event_id = cal_res.json().get("id")
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute("UPDATE appointments SET google_event_id=%s WHERE id=%s", (event_id, appt_id))
            conn.commit(); cur.close(); conn.close()
            logger.info(f"[calendar] Synced — event {event_id}")
        else:
            logger.warning(f"[calendar] Failed: {cal_res.status_code} {cal_res.text}")
    except Exception as e:
        logger.error(f"[calendar] Error: {e}")


async def update_event(google_event_id: str, parsed: dict, start_time: datetime, end_time: datetime):
    if not google_event_id:
        return
    token = await _get_token()
    if not token:
        return
    try:
        patient_name = parsed.get("name") or "Patient"
        service_name = parsed.get("service") or "Appointment"
        event_body = {
            "summary": f"{service_name} — {patient_name} (Rescheduled)",
            "start":   {"dateTime": start_time.isoformat(), "timeZone": BUSINESS_TIMEZONE},
            "end":     {"dateTime": end_time.isoformat(),   "timeZone": BUSINESS_TIMEZONE},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.patch(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{google_event_id}",
                headers={"Authorization": f"Bearer {token}"},
                json=event_body,
            )
        if res.is_success:
            logger.info(f"[calendar] Updated event {google_event_id}")
        else:
            logger.warning(f"[calendar] Update failed: {res.status_code} {res.text}")
    except Exception as e:
        logger.error(f"[calendar] Update error: {e}")


async def delete_event(google_event_id: str):
    if not google_event_id:
        return
    token = await _get_token()
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{google_event_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if res.is_success or res.status_code == 410:
            logger.info(f"[calendar] Deleted event {google_event_id}")
        else:
            logger.warning(f"[calendar] Delete failed: {res.status_code} {res.text}")
    except Exception as e:
        logger.error(f"[calendar] Delete error: {e}")
