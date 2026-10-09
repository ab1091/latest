"""
Gmail API client — sends email via the same Google account/token already
used for Calendar sync (GOOGLE_CALENDAR_REFRESH_TOKEN now carries both the
`calendar` and `gmail.send` scopes).
"""
import base64
import logging
from datetime import datetime
from email.mime.text import MIMEText

import httpx

from core.config import GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

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
        logger.error(f"[gmail] Token fetch error: {e}")
        return None


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email via Gmail API. Returns True on success."""
    token = await _get_token()
    if not token:
        logger.warning("[gmail] No access token — skipping send")
        return False
    try:
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": raw},
            )
        if res.is_success:
            logger.info(f"[gmail] Sent to {to} — message {res.json().get('id')}")
            return True
        logger.warning(f"[gmail] Send failed: {res.status_code} {res.text}")
        return False
    except Exception as e:
        logger.error(f"[gmail] Send error: {e}")
        return False


_FAKE_EMAIL_SUFFIXES = ("@sms.lead", "@vapi.call")


async def send_appointment_confirmation(
    email: str | None, first_name: str, service_name: str, start_time: datetime,
    conversation_text: str | None = None, phone: str | None = None
) -> bool:
    """
    Shared confirmation-email sender for every booking path (SMS, Vapi
    outbound/inbound calls, legacy Twilio voice) — skips cleanly if there's
    no real email on file (placeholder addresses like `...@sms.lead` /
    `...@vapi.call` are auto-generated for leads with no real email).
    Includes the full lead conversation details in the body.
    """
    if not email or email.endswith(_FAKE_EMAIL_SUFFIXES):
        return False
    when = start_time.strftime("%A, %B %d at %I:%M %p")
    phone_line = f"Phone: {phone}\n" if phone else ""
    convo_block = (
        f"\n--------------------------------------------------\n"
        f"Conversation Details / Messages:\n"
        f"{conversation_text}\n"
        f"--------------------------------------------------\n"
    ) if conversation_text else ""

    body = (
        f"Hi {first_name},\n\n"
        f"Your appointment for {service_name} is confirmed for {when}.\n\n"
        f"{phone_line}"
        f"Consultation with: Troy Vance | Farmers Insurance\n"
        f"{convo_block}\n"
        f"If you need to reschedule or have any questions beforehand, feel free to reply directly to this email or call/text us back.\n\n"
        f"See you then!\n\n"
        f"Warm regards,\n"
        f"Troy Vance\n"
        f"Agency Owner | Farmers Insurance\n"
    )
    return await send_email(
        email,
        f"Confirmed: Phone Consultation with Troy Vance — {when}",
        body,
    )
