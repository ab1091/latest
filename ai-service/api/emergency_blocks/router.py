"""Emergency Blocks routes — Python/FastAPI port of emergencyBlocks.ts"""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
from core.calendar import delete_event
from core.config import (DEFAULT_BUSINESS_ID, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    VAPI_API_KEY, VAPI_PHONE_NUMBER_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL)
from pydantic import BaseModel
from core.auth_scope import get_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emergency-blocks")


class CreateBlockBody(BaseModel):
    providerId: Optional[str] = None
    startTime: str
    endTime: str
    reason: str
    aiExplanation: Optional[str] = None


@router.get("/impact")
def impact_check(request: Request, providerId: str = "", startTime: str = "", endTime: str = ""):
    scope = get_scope(request)
    if not startTime or not endTime:
        raise HTTPException(status_code=400, detail="Missing parameters")

    conn = get_conn()
    cur = get_dict_cursor(conn)
    if providerId:
        cur.execute("""
            SELECT COUNT(*) AS count FROM appointments
            WHERE provider_id = %s AND business_id = %s AND status = 'confirmed'
              AND start_time < %s AND end_time > %s
        """, (providerId, scope["businessId"], endTime, startTime))
    else:
        cur.execute("""
            SELECT COUNT(*) AS count FROM appointments
            WHERE business_id = %s AND status = 'confirmed'
              AND start_time < %s AND end_time > %s
        """, (scope["businessId"], endTime, startTime))
    row = cur.fetchone()
    cur.close(); conn.close()
    return {"success": True, "data": {"count": int(row["count"])}}


@router.get("")
def list_blocks(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("""
        SELECT eb.*, p.name AS provider_name
        FROM emergency_blocks eb
        LEFT JOIN providers p ON p.id = eb.provider_id
        WHERE eb.business_id = %s
        ORDER BY eb.start_time DESC
    """, (scope["businessId"],))
    blocks = cur.fetchall()
    cur.close(); conn.close()
    return {"success": True, "data": {"blocks": [dict(b) for b in blocks]}}


@router.post("", status_code=201)
async def create_block(body: CreateBlockBody, request: Request):
    scope = get_scope(request)
    if not body.startTime or not body.endTime or not body.reason:
        raise HTTPException(status_code=400, detail="Missing required fields: startTime, endTime, reason")

    conn = get_conn()
    cur = get_dict_cursor(conn)

    block_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    cur.execute("""
        INSERT INTO emergency_blocks (id, business_id, provider_id, start_time, end_time, reason, ai_explanation, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
    """, (block_id, scope["businessId"], body.providerId or None, body.startTime, body.endTime, body.reason, body.aiExplanation, now, now))

    # Find all confirmed appointments in the blocked window
    if body.providerId:
        cur.execute("""
            SELECT a.id, a.user_id, a.start_time, a.google_event_id,
                   u.phone, u.first_name, u.last_name,
                   s.name AS service_name, p.name AS provider_name
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN providers p ON a.provider_id = p.id
            WHERE a.provider_id = %s AND a.business_id = %s AND a.status = 'confirmed'
              AND a.start_time < %s AND a.end_time > %s
        """, (body.providerId, scope["businessId"], body.endTime, body.startTime))
    else:
        cur.execute("""
            SELECT a.id, a.user_id, a.start_time, a.google_event_id,
                   u.phone, u.first_name, u.last_name,
                   s.name AS service_name, p.name AS provider_name
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN providers p ON a.provider_id = p.id
            WHERE a.business_id = %s AND a.status = 'confirmed'
              AND a.start_time < %s AND a.end_time > %s
        """, (scope["businessId"], body.endTime, body.startTime))
    affected = cur.fetchall()

    if affected:
        ids = [a["id"] for a in affected]
        cur.execute("""
            UPDATE appointments
            SET status = 'cancelled', cancellation_reason = %s, cancelled_at = NOW(), updated_at = NOW()
            WHERE id = ANY(%s)
        """, (f"Emergency Block: {body.reason}", ids))

        # Delete Google Calendar events for cancelled appointments
        for apt in affected:
            if apt.get("google_event_id"):
                import asyncio
                asyncio.create_task(delete_event(apt["google_event_id"]))

        # Place outbound Vapi calls to each affected patient
        if VAPI_API_KEY and VAPI_PHONE_NUMBER_ID and VAPI_ASSISTANT_ID:
            for apt in affected:
                if not apt.get("phone"):
                    continue
                start_dt = apt["start_time"]
                if hasattr(start_dt, "strftime"):
                    apt_date = start_dt.strftime("%A, %B %-d")
                    apt_time = start_dt.strftime("%-I:%M %p")
                else:
                    dt = datetime.fromisoformat(str(start_dt))
                    apt_date = dt.strftime("%A, %B %-d")
                    apt_time = dt.strftime("%-I:%M %p")

                msg = (
                    f"Hello {apt['first_name']}, this is James from AllZone Scheduler. "
                    f"We are sorry to inform you that your {apt.get('service_name') or 'appointment'} scheduled for {apt_date} at {apt_time} "
                    f"has been cancelled due to an emergency. {body.aiExplanation or body.reason}. "
                    f"Our team will contact you shortly to reschedule. We apologize for the inconvenience."
                )
                call_id = f"emergency_{block_id}_{apt['id'][-6:]}"
                payload = {
                    "phoneNumberId": VAPI_PHONE_NUMBER_ID,
                    "customer":      {"number": apt["phone"]},
                    "assistantId":   VAPI_ASSISTANT_ID,
                    "assistantOverrides": {
                        "server": {"url": f"{TWIML_BASE_URL}/api/vapi/webhook"},
                        "firstMessage": msg,
                        "endCallMessage": "",
                    },
                }
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        r = await client.post(
                            "https://api.vapi.ai/call/phone",
                            headers={"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"},
                            json=payload,
                        )
                    if r.is_success:
                        sid = r.json().get("id", call_id)
                        cur.execute("""
                            INSERT INTO voice_calls (id, call_id, appointment_id, provider, status, direction, patient_phone, summary, created_at, updated_at)
                            VALUES (%s, %s, %s, 'vapi', 'in-progress', 'outbound', %s, %s, NOW(), NOW())
                            ON CONFLICT (call_id) DO NOTHING
                        """, (call_id, sid, apt["id"], apt["phone"], f"Emergency: {body.reason}"))
                        logger.info(f"[emergency] Outbound call to {apt['phone']} SID={sid}")
                    else:
                        logger.error(f"[emergency] Vapi call failed for {apt.get('phone')}: {r.text}")
                except Exception as e:
                    logger.error(f"[emergency] Failed to call {apt.get('phone')}: {e}")

    conn.commit(); cur.close(); conn.close()
    return {"success": True, "data": {"blockId": block_id, "affectedCount": len(affected)}}


@router.patch("/{block_id}/resolve")
def resolve_block(block_id: str, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE emergency_blocks SET status = 'resolved', updated_at = NOW() WHERE id = %s AND business_id = %s", (block_id, scope["businessId"]))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}
