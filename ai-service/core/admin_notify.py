"""
Notifies a business's admins by SMS when an appointment gets booked, so a
human finds out immediately instead of only via the in-app activity feed.
An admin "opts in" simply by having a phone number on their users row — no
phone means no text, silently (most seeded admin accounts have none).
"""
import logging

from core.db import get_conn, get_dict_cursor as dict_cursor

logger = logging.getLogger(__name__)


async def notify_admins_appointment_booked(business_id: str, lead_name: str, when, service_label: str = "Appointment"):
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT phone FROM users WHERE business_id = %s AND role IN ('admin', 'super_admin') "
            "AND phone IS NOT NULL AND phone != ''",
            (business_id,),
        )
        phones = [r["phone"] for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not phones:
        return

    when_str = when.strftime("%a, %b %d at %I:%M %p") if hasattr(when, "strftime") else str(when)
    message = f"New appointment booked: {lead_name} — {service_label} on {when_str}."

    from api.sms.router import _send_sms
    for phone in phones:
        try:
            # force=True: this is an internal staff notification, not a
            # lead-facing marketing/reply send, so the lead TCPA opt-out
            # check doesn't apply here.
            await _send_sms(phone, message, force=True)
        except Exception as e:
            logger.warning(f"[admin_notify] failed to notify admin {phone}: {e}")
