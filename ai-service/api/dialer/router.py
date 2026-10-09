"""Dialer routes — Python/FastAPI port of dialer.ts"""
import os
import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
from core.config import (DEFAULT_BUSINESS_ID, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    VAPI_API_KEY, VAPI_PHONE_NUMBER_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL)
from pydantic import BaseModel
from core.auth_scope import get_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dialer")


class BridgeBody(BaseModel):
    providerId: str


class CallBody(BaseModel):
    phoneNumber: str
    message: Optional[str] = None


@router.post("/bridge")
async def bridge(body: BridgeBody, request: Request):
    scope = get_scope(request)

    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT * FROM providers WHERE id = %s AND business_id = %s AND is_active = 1", (body.providerId, scope["businessId"]))
    provider = cur.fetchone()

    if not provider:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Provider not found")

    if not provider.get("phone"):
        cur.close(); conn.close()
        raise HTTPException(status_code=400, detail="Provider does not have a registered phone number")

    if not VAPI_ASSISTANT_ID:
        cur.close(); conn.close()
        raise HTTPException(status_code=500, detail="Vapi assistant is not configured for bridge calls")

    from datetime import datetime
    now_iso = datetime.utcnow().isoformat()
    cur.execute("""
        SELECT ai_explanation, reason FROM emergency_blocks
        WHERE provider_id = %s AND status = 'active'
          AND start_time <= %s AND end_time >= %s
        ORDER BY created_at DESC LIMIT 1
    """, (body.providerId, now_iso, now_iso))
    block = cur.fetchone()
    cur.close(); conn.close()

    emergency_notice = None
    if block:
        emergency_notice = block.get("ai_explanation") or block.get("reason")

    first_message = (
        f"Hello! I need to let you know: {emergency_notice} I'm sorry for the inconvenience. Would you like me to help you reschedule?"
        if emergency_notice
        else f"Connecting you to {provider['name']}. Please hold while I place the call."
    )

    return {
        "success": True,
        "data": {
            "assistantId": VAPI_ASSISTANT_ID,
            "assistantOverrides": {
                "firstMessage": first_message,
                # See api/calls/router.py for why this matters — the shared
                # Vapi assistant has its own leftover endCallMessage from a
                # prior unrelated business, read verbatim otherwise.
                "endCallMessage": "",
                "variableValues": {
                    "transferDestinationNumber": provider["phone"],
                    "transferDestinationName": provider["name"],
                    "transferDestinationSpecialty": provider.get("specialty") or "",
                    "emergencyNotice": emergency_notice or "",
                    "isEmergency": "true" if emergency_notice else "false",
                },
            },
            "destination": {"type": "number", "number": provider["phone"]},
            "provider": {"name": provider["name"], "specialty": provider.get("specialty"), "id": provider["id"]},
        },
    }


@router.post("/call")
async def outbound_call(body: CallBody, request: Request):
    scope = get_scope(request)

    raw_number = body.phoneNumber.strip()
    if not raw_number or not re.match(r"^\+?[\d\s\-(). ]{7,20}$", raw_number):
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    if not VAPI_API_KEY or not VAPI_PHONE_NUMBER_ID or not VAPI_ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Vapi is not configured on this server.")

    # 9am-6pm US Central only, same policy as the automated dialer (core/
    # callback_scheduler.py) — applies here too even though this is
    # staff-triggered, not automated, since the calling-hours rule is about
    # when the LEAD gets contacted, not who clicked the button.
    from api.sms.router import _is_within_quiet_hours
    allowed, reason = _is_within_quiet_hours(scope.get("businessId") or DEFAULT_BUSINESS_ID)
    if not allowed:
        raise HTTPException(status_code=422, detail=f"Blocked by calling hours — {reason}")

    payload = {
        "phoneNumberId": VAPI_PHONE_NUMBER_ID,
        "customer":      {"number": raw_number},
        "assistantId":   VAPI_ASSISTANT_ID,
        "assistantOverrides": {
            "server": {"url": f"{TWIML_BASE_URL}/api/vapi/webhook"},
            "firstMessage": body.message or "Hi, connecting your call now.",
            "endCallMessage": "",
            # Same voicemail policy as the automated dialer (core/
            # callback_scheduler.py, api/calls/router.py): empty
            # voicemailMessage + voicemailDetection makes the call hang up
            # the instant a machine/voicemail is detected instead of talking
            # into it. This endpoint had neither — a manual staff-initiated
            # dial would ring straight through to a mailbox with no
            # detection at all.
            "voicemailMessage":  "",
            "voicemailDetection": {
                "provider": "vapi",
                "backoffPlan": {"startAtSeconds": 2, "frequencySeconds": 2.5, "maxRetries": 5},
                "beepMaxAwaitSeconds": 12,
            },
        },
    }

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            "https://api.vapi.ai/call/phone",
            headers={"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )

    if not res.is_success:
        raise HTTPException(status_code=502, detail=f"Vapi error: {res.text}")

    data = res.json()
    logger.info(f"[dialer:call] Outbound Vapi call placed id={data.get('id')} to={raw_number} by={scope['userId']}")
    return {"success": True, "callSid": data.get("id"), "to": raw_number}
