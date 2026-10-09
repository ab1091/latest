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
    # Strictly iMessage ONLY per explicit instruction ("no twwillio jut i meesge pleae onlyy")
    chat_guid = f"iMessage;-;{phone}"
    temp_guid = uuid.uuid4().hex

    try:
        async with httpx.AsyncClient(timeout=_RESPONSE_TIMEOUT) as client:
            res = await client.post(
                f"{BB_SERVER_URL}/api/v1/message/text",
                params={"password": BB_PASSWORD},
                json={
                    "chatGuid": chat_guid,
                    "message": body,
                    "method": BB_SEND_METHOD,
                    "tempGuid": temp_guid,
                },
            )
    except httpx.TimeoutException:
        logger.warning(
            f"[bluebubbles] response timed out after {_RESPONSE_TIMEOUT}s for chatGuid={chat_guid} "
            f"tempGuid={temp_guid} - treating as sent (BlueBubbles fallback AppleScript delivers "
            f"in ~1-3s regardless; confirmation channel hung)"
        )
        return {"sid": None, "ok": True, "unconfirmed": True}
    except httpx.RequestError as e:
        raise RuntimeError(f"BlueBubbles unreachable: {e}")

    if res.is_success:
        data = res.json()
        if not data.get("status") or data["status"] < 400:
            message_id = ((data.get("data") or {}).get("guid")) if isinstance(data.get("data"), dict) else None
            logger.info(f"[bluebubbles] iMessage sent to {phone} chatGuid={chat_guid} id={message_id}")
            return {"sid": message_id, "ok": True}
        err_msg = data.get("message") or data.get("error", {}).get("message") or str(data)
        raise RuntimeError(f"BlueBubbles iMessage rejected send: {err_msg}")
    else:
        raise RuntimeError(f"BlueBubbles iMessage error: {res.status_code} {res.text}")

