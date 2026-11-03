"""
TextBee Android SMS Gateway client — REST API to an Android phone running
the TextBee APK with active SIM cards.
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

TEXTBEE_API_KEY = os.getenv("TEXTBEE_API_KEY", "")
TEXTBEE_DEVICE_ID = os.getenv("TEXTBEE_DEVICE_ID", "")
TEXTBEE_BASE_URL = os.getenv("TEXTBEE_BASE_URL", "https://api.textbee.dev/api/v1")


def normalize_phone(ph: str) -> str:
    """Normalize phone number to international E.164 format."""
    if not ph:
        return ph
    ph = ph.strip()
    if ph.startswith("+"):
        digits = "".join(c for c in ph[1:] if c.isdigit())
        return f"+{digits}"
    digits = "".join(c for c in ph if c.isdigit())
    if not digits:
        return ph
    # Handle Pakistan local format (03xx -> +923xx)
    if len(digits) == 11 and digits.startswith("03"):
        return f"+92{digits[1:]}"
    # Standard 10-digit US format
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"


async def send_message(to: str, body: str) -> dict:
    """
    Dispatches a native SMS message through the connected Android phone's cellular SIM card.
    Returns a dict matching the standard gateway contract: {"sid": ..., "status": ...}.
    """
    api_key = os.getenv("TEXTBEE_API_KEY", TEXTBEE_API_KEY)
    device_id = os.getenv("TEXTBEE_DEVICE_ID", TEXTBEE_DEVICE_ID)
    base_url = os.getenv("TEXTBEE_BASE_URL", TEXTBEE_BASE_URL)

    target_phone = normalize_phone(to)
    url = f"{base_url}/gateway/devices/{device_id}/send-sms"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "recipients": [target_phone],
        "message": body
    }
    logger.info(f"[textbee] Sending SMS via Android to {target_phone}: {body[:40]}...")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            logger.error(f"[textbee] HTTP {resp.status_code}: {resp.text}")
            raise RuntimeError(f"TextBee error {resp.status_code}: {resp.text}")
        data = resp.json()
        batch_id = data.get("data", {}).get("smsBatchId", "sent")
        logger.info(f"[textbee] SMS queued on Android device successfully: batchId={batch_id}")
        return {"sid": batch_id, "status": "queued", "gateway": "android_textbee"}


async def fetch_recent_messages(limit: int = 25) -> list[dict]:
    """Fetches recently received and sent messages from TextBee cloud API."""
    api_key = os.getenv("TEXTBEE_API_KEY", TEXTBEE_API_KEY)
    base_url = os.getenv("TEXTBEE_BASE_URL", TEXTBEE_BASE_URL)
    if not api_key:
        return []
    url = f"{base_url}/gateway/messages?limit={limit}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"x-api-key": api_key})
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
    except Exception as e:
        logger.warning(f"[textbee] Failed to fetch gateway messages: {e}")
    return []


_inbound_task = None
_inbound_running = False


async def poll_and_process_inbound(inbound_handler):
    """
    Checks for newly received SMS messages from leads on the Android device,
    records them in the processed table, and forwards them to the CRM inbound handler.
    """
    from core.db import get_conn, get_dict_cursor as dict_cursor
    raw_messages = await fetch_recent_messages(limit=30)
    if not raw_messages:
        return

    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_inbound_sms (
                sms_id TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        conn.commit()

        for m in raw_messages:
            msg_type = m.get("type", "").upper()
            direction = m.get("direction", "").lower()
            if msg_type != "RECEIVED" and direction != "received":
                continue

            sms_id = m.get("_id")
            sender = (m.get("sender") or "").strip()
            content = (m.get("message") or "").strip()

            if not sms_id or not sender or not content:
                continue

            # Ignore non-phone automated system senders (like verification code providers)
            digits = "".join(c for c in sender if c.isdigit())
            if len(digits) < 7:
                continue

            # Check if this message was already processed
            cur.execute("SELECT 1 FROM processed_inbound_sms WHERE sms_id = %s", (sms_id,))
            if cur.fetchone():
                continue

            # Mark processed
            cur.execute(
                "INSERT INTO processed_inbound_sms (sms_id, sender, message) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (sms_id, sender, content)
            )
            conn.commit()

            logger.info(f"[textbee:inbound] Detected new inbound SMS from {sender}: {content[:40]}")
            # Route to unified inbound message handler
            try:
                await inbound_handler(sender, content, "sms")
            except Exception as e:
                logger.error(f"[textbee:inbound] Handler failed for {sender}: {e}")
    except Exception as e:
        logger.warning(f"[textbee:inbound] Polling error: {e}")
    finally:
        cur.close()
        conn.close()


async def _inbound_loop(inbound_handler, interval_seconds: int = 10):
    global _inbound_running
    _inbound_running = True
    logger.info(f"[textbee] Inbound SMS listener started (polling every {interval_seconds}s)")
    while _inbound_running:
        try:
            await poll_and_process_inbound(inbound_handler)
        except Exception as e:
            logger.warning(f"[textbee] Error in inbound loop: {e}")
        await asyncio.sleep(interval_seconds)


def start_inbound_listener(inbound_handler, interval_seconds: int = 10):
    global _inbound_task
    import asyncio
    if _inbound_task is None or _inbound_task.done():
        loop = asyncio.get_event_loop()
        _inbound_task = loop.create_task(_inbound_loop(inbound_handler, interval_seconds))


def stop_inbound_listener():
    global _inbound_running, _inbound_task
    _inbound_running = False
    if _inbound_task and not _inbound_task.done():
        _inbound_task.cancel()
        _inbound_task = None

