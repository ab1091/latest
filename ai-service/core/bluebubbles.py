"""
BlueBubbles client — REST API to a local Mac running Messages.app + the
BlueBubbles Server app, replacing Claw Messenger as the outbound/inbound
transport for what the rest of the app still calls the "sms" channel.

Unlike Claw Messenger (a persistent websocket needing owner-election across
multiple workers — see core/claw_messenger.py), BlueBubbles is a stateless
local REST API + webhook: no connection lifecycle, no start/stop, nothing to
elect. send_message() just makes an HTTP call each time.
"""
import logging
import uuid

import httpx

from core.config import BB_SERVER_URL, BB_PASSWORD, BB_SEND_METHOD

logger = logging.getLogger(__name__)


def normalize_phone(ph: str) -> str:
    """Same algorithm as crm-service/routers/leads.py:normalize_phone —
    duplicated, not imported, since ai-service and crm-service are separate
    deployables with no shared package today."""
    if not ph:
        return ph
    if ph.startswith("+"):
        digits = "".join(c for c in ph[1:] if c.isdigit())
        return f"+{digits}"
    digits = "".join(c for c in ph if c.isdigit())
    if not digits:
        return ph
    return f"+{digits}" if len(digits) > 10 else f"+1{digits}"


_RESPONSE_TIMEOUT = 15  # seconds — see the ReadTimeout handling below for why


async def send_message(to: str, body: str) -> dict:
    """Returns a dict with a 'sid' key, matching claw_messenger.send_message's
    contract, so _send_sms's existing `except RuntimeError` → HTTPException
    handling works unchanged.

    chatGuid uses BlueBubbles' internal 1:1-chat format, 'iMessage;-;<phone>'.

    Confirmed live (repeatedly, both cold-send and warm-send, both a fake
    test number and a real phone that replied back): BlueBubbles' primary
    AppleScript send always fails instantly with "Can't get chat id ..."
    regardless of whether the chat already exists, but its automatic
    fallback script then actually delivers the message within ~1-3 seconds
    every time. The message is genuinely sent and received well before that.
    Separately, though, the /api/v1/message/text HTTP response itself hangs
    for a full 120s and then comes back as a spurious 500 "Message Send
    Error" — this server has enable_private_api=1 in its own config but
    helper_connected=false in /api/v1/server/info, so it's almost certainly
    stuck waiting on a delivery-confirmation signal from a Private API
    helper that isn't actually connected, not a real send failure.

    Before this was accounted for, a caller's own timeout (this used to be
    30s, shorter than BlueBubbles' 120s hang) looked like a failure and
    triggered _send_sms's caller's one-retry-on-failure logic — which
    actually just sent the same message to the same real person a second
    time, confirmed live via BlueBubbles' own log showing two identical
    sends ~34s apart for one inbound message. So: a genuine timeout here is
    now treated as "sent, unconfirmed" (warn and return success-shaped),
    not a hard failure — the empirical delivery time is consistently under
    3 seconds, so 15s is already generous slack, and treating a timeout as
    failure given BlueBubbles' current broken confirmation channel produces
    a guaranteed duplicate send on every single message, every time. An
    explicit HTTP error response (as opposed to a timeout) is still treated
    as a real failure below, since that's a different, more specific signal
    than "the confirmation channel never replied."
    """
    if not BB_PASSWORD:
        raise RuntimeError("BlueBubbles not configured (BB_PASSWORD missing)")

    from core.humanoid_sender import sanitize_text
    body = sanitize_text(body)

    phone = normalize_phone(to)

    async def _send_to_bb(guid: str, t_guid: str):
        async with httpx.AsyncClient(timeout=_RESPONSE_TIMEOUT) as client:
            return await client.post(
                f"{BB_SERVER_URL}/api/v1/message/text",
                params={"password": BB_PASSWORD},
                headers={"ngrok-skip-browser-warning": "true"},
                json={
                    "chatGuid": guid,
                    "message": body,
                    "method": BB_SEND_METHOD,
                    "tempGuid": t_guid,
                },
            )

    # 1. Primary: Native cellular SMS text message via paired iPhone SIM
    # Guarantees delivery as a standard text message to all devices:
    # Android, flip phones, and iPhone users who do not use or have disabled iMessage.
    sms_guid = f"SMS;-;{phone}"
    sms_temp_guid = uuid.uuid4().hex
    try:
        sms_res = await _send_to_bb(sms_guid, sms_temp_guid)
        if sms_res.is_success:
            s_data = sms_res.json()
            if not s_data.get("status") or s_data["status"] < 400:
                s_id = ((s_data.get("data") or {}).get("guid")) if isinstance(s_data.get("data"), dict) else None
                logger.info(f"[bluebubbles] ✓ Native SMS text message sent to {phone} chatGuid={sms_guid} id={s_id}")
                return {"sid": s_id, "ok": True, "service": "SMS"}
            else:
                logger.warning(f"[bluebubbles] Native SMS returned error: {s_data.get('message')}")
    except httpx.TimeoutException:
        logger.warning(
            f"[bluebubbles] SMS send timed out after {_RESPONSE_TIMEOUT}s for chatGuid={sms_guid} - treating as sent"
        )
        return {"sid": None, "ok": True, "service": "SMS", "unconfirmed": True}
    except Exception as e:
        logger.warning(f"[bluebubbles] Native SMS attempt failed for {phone}: {e}")

    # 2. Secondary fallback: iMessage
    chat_guid = f"iMessage;-;{phone}"
    temp_guid = uuid.uuid4().hex
    logger.info(f"[bluebubbles] Falling back to iMessage for {phone} ({chat_guid})...")
    try:
        res = await _send_to_bb(chat_guid, temp_guid)
        if res.is_success:
            data = res.json()
            if not data.get("status") or data["status"] < 400:
                message_id = ((data.get("data") or {}).get("guid")) if isinstance(data.get("data"), dict) else None
                logger.info(f"[bluebubbles] iMessage sent to {phone} chatGuid={chat_guid} id={message_id}")
                return {"sid": message_id, "ok": True, "service": "iMessage"}
    except httpx.TimeoutException:
        logger.warning(
            f"[bluebubbles] iMessage response timed out after {_RESPONSE_TIMEOUT}s for {chat_guid} - treating as sent"
        )
        return {"sid": None, "ok": True, "service": "iMessage", "unconfirmed": True}
    except Exception as e:
        logger.warning(f"[bluebubbles] iMessage fallback error for {phone}: {e}")

    raise RuntimeError(f"BlueBubbles send failed for {phone}: both native SMS text and iMessage attempts failed")

