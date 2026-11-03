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
    target_phone = normalize_phone(to)
    url = f"{TEXTBEE_BASE_URL}/gateway/devices/{TEXTBEE_DEVICE_ID}/send-sms"
    headers = {
        "x-api-key": TEXTBEE_API_KEY,
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
