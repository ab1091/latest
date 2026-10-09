"""
Thin client for ai-service's single real message send implementation
(BlueBubbles iMessage only per system configuration).

Extracted from the old routers/sms.py.
Kept here because routers/conversations.py's manual "send a message from the
CRM" feature genuinely depends on it.
"""
from fastapi import HTTPException
import httpx
from jose import jwt as _jwt

from core.config import JWT_SECRET, VOICE_BOT_URL


def _system_jwt() -> str:
    return _jwt.encode(
        {"userId": "system:crm-service", "role": "admin"},
        JWT_SECRET, algorithm="HS256",
    )


async def send_sms(to: str, body: str, channel: str = "imessage", force: bool = False) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{VOICE_BOT_URL}/api/sms/send-raw",
            json={"to": to, "body": body, "channel": channel, "force": force},
            headers={"Authorization": f"Bearer {_system_jwt()}"},
        )
    if not res.is_success:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json().get("data", {})
