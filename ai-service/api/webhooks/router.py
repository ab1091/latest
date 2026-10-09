"""Webhooks routes — Python/FastAPI port of webhooks.ts"""
import os
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
from core.config import (JWT_SECRET, DEFAULT_BUSINESS_ID, TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL)
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks")





def verify_vapi_signature(raw_body: str, signature: str) -> bool:
    if not VAPI_WEBHOOK_SECRET:
        logger.error("[webhook] VAPI_WEBHOOK_SECRET not set")
        return False
    sig = signature.strip()
    if sig.startswith("sha256="):
        sig = sig[len("sha256="):]
    if not sig:
        return False
    expected = hmac.new(VAPI_WEBHOOK_SECRET.encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def resolve_outcome(payload: dict) -> str:
    reason = (payload.get("call", {}).get("endedReason") or "").lower()
    if "voicemail" in reason:
        return "voicemail"
    if "no-answer" in reason or "did-not-answer" in reason:
        return "no_answer"
    if "busy" in reason or "failed" in reason:
        return "failed"
    return "confirmed"


async def _hubspot_update_meeting(business_id: str, appointment_id: str, status: str):
    if not HUBSPOT_ACCESS_TOKEN:
        return
    try:
        hs_headers = {"Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            # Search meetings by external ID
            search_res = await client.post(
                "https://api.hubapi.com/crm/v3/objects/meetings/search",
                headers=hs_headers,
                json={"filterGroups": [{"filters": [{"propertyName": "meeting_external_id", "operator": "EQ", "value": appointment_id}]}], "limit": 1},
            )
            if search_res.is_success:
                results = search_res.json().get("results", [])
                if results:
                    meeting_id = results[0]["id"]
                    await client.patch(
                        f"https://api.hubapi.com/crm/v3/objects/meetings/{meeting_id}",
                        headers=hs_headers,
                        json={"properties": {"hs_meeting_outcome": status.upper()}},
                    )
    except Exception as e:
        logger.error(f"HubSpot update meeting error: {e}")


# ── POST /api/webhooks/vapi ───────────────────────────────────────────────────

@router.post("/vapi")
async def vapi_webhook(request: Request):
    signature = request.headers.get("x-vapi-signature", "")
    raw_body = await request.body()
    raw_body_str = raw_body.decode("utf-8")

    if not verify_vapi_signature(raw_body_str, signature):
        logger.warning("[webhook] Invalid Vapi signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    event_type = payload.get("type", "")
    if event_type not in ("call.ended", "end-of-call-report"):
        return {"received": True}

    call_id = payload.get("call", {}).get("id")
    if not call_id:
        raise HTTPException(status_code=400, detail="Missing call.id in payload")

    logger.info(f"[webhook] Vapi call.ended: {call_id} reason={payload.get('call', {}).get('endedReason')}")

    conn = get_conn()
    cur = get_dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM voice_calls WHERE call_id = %s AND outcome IS NOT NULL", (call_id,))
        if cur.fetchone():
            logger.info(f"[webhook] Duplicate event for call {call_id} — skipped")
            return {"received": True}

        outcome = resolve_outcome(payload)
        summary = payload.get("analysis", {}).get("summary") or payload.get("summary")
        transcript = payload.get("transcript")
        duration = payload.get("call", {}).get("durationSeconds")

        cur.execute("""
            UPDATE voice_calls
            SET outcome = %s, status = 'ended', transcript = %s, summary = %s,
                duration_seconds = %s, raw_payload = %s, updated_at = NOW()
            WHERE call_id = %s
        """, (outcome, transcript, summary, duration, raw_body_str, call_id))

        # The lead is left thinking a call is coming and it never will unless
        # someone/something tells them — and staff have zero visibility into
        # the miss otherwise. Fires on no_answer too: confirmed live that
        # Vapi's own endedReason classification is inconsistent for the exact
        # same real-world event (a full voicemail box intercepting the call)
        # — sometimes resolves here as "voicemail", sometimes "no_answer".
        # Both mean the lead was not actually reached.
        voicemail_lead = None
        if outcome in ("voicemail", "no_answer"):
            cur.execute("SELECT lead_id FROM voice_calls WHERE call_id = %s", (call_id,))
            vc_row = cur.fetchone()
            lead_id = vc_row["lead_id"] if vc_row else None
            if lead_id:
                # Skip entirely if a workflow currently owns this lead's
                # follow-up cadence — same duplicated-code bug as
                # vapi/router.py's identical block: this copy had no gate at
                # all and would double-text/double-task any workflow-enrolled
                # lead on a missed call.
                cur.execute(
                    "SELECT 1 FROM lead_workflow_enrollments WHERE lead_id = %s AND status IN ('active','waiting') LIMIT 1",
                    (lead_id,),
                )
                is_workflow_call = cur.fetchone() is not None
            else:
                is_workflow_call = False
            if lead_id and not is_workflow_call:
                cur.execute("SELECT business_id, first_name, phone FROM leads WHERE id = %s", (lead_id,))
                lead_row = cur.fetchone()
                if lead_row:
                    import uuid as _uuid
                    task_id = f"task_{_uuid.uuid4().hex[:12]}"
                    cur.execute("""
                        INSERT INTO tasks (id, lead_id, business_id, title, status, due_at, created_at)
                        VALUES (%s, %s, %s, %s, 'open', NOW(), NOW())
                    """, (task_id, lead_id, lead_row["business_id"],
                          f"Call to {lead_row.get('first_name') or lead_row.get('phone')} hit voicemail — "
                          f"they haven't actually been reached yet. Follow up manually."))
                    voicemail_lead = {"id": lead_id, **lead_row}

        if outcome == "confirmed":
            cur.execute("""
                UPDATE appointments a
                SET status = 'confirmed', updated_at = NOW()
                FROM voice_calls v
                WHERE a.id = v.appointment_id AND v.call_id = %s
            """, (call_id,))

            cur.execute("""
                SELECT a.id, u.email, a.business_id
                FROM appointments a
                JOIN users u ON a.user_id = u.id
                JOIN voice_calls v ON a.id = v.appointment_id
                WHERE v.call_id = %s
            """, (call_id,))
            apt_row = cur.fetchone()
            if apt_row:
                import asyncio
                asyncio.create_task(_hubspot_update_meeting(apt_row["business_id"], apt_row["id"], "confirmed"))

        conn.commit()
        logger.info(f"[webhook] Processed call {call_id} → outcome: {outcome}")
    except Exception as e:
        logger.error(f"[webhook] Failed to process Vapi event: {e}")
        conn.rollback()
        voicemail_lead = None
    finally:
        cur.close(); conn.close()

    # Texting the lead too, not just notifying staff — they're sitting there
    # thinking a call is coming and it never will unless someone tells them.
    # Sent after commit/connection close so a Claw hiccup here can't affect
    # the outcome/task writes above.
    if voicemail_lead and voicemail_lead.get("phone"):
        try:
            from api.sms.router import _send_sms, _save_message, _get_or_create_sms_conv
            msg = (
                f"Hi {voicemail_lead['first_name']}, we just tried giving you a call but couldn't "
                f"reach you. Feel free to reply here anytime, or let us know a good time to call back!"
                if voicemail_lead.get("first_name") else
                "Hi, we just tried giving you a call but couldn't reach you. Feel free to reply here "
                "anytime, or let us know a good time to call back!"
            )
            await _send_sms(voicemail_lead["phone"], msg)
            conv_id = _get_or_create_sms_conv(voicemail_lead["id"], voicemail_lead["business_id"], "sms")
            _save_message(conv_id, "agent", msg)
        except Exception as sms_err:
            logger.warning(f"[webhook] voicemail follow-up SMS failed for {call_id}: {sms_err}")

    return {"received": True}


# ── POST /api/webhooks/hubspot ────────────────────────────────────────────────

@router.post("/hubspot")
async def hubspot_webhook(request: Request):
    try:
        events = await request.json()
        if not isinstance(events, list):
            raise HTTPException(status_code=400, detail="Invalid payload")

        logger.info(f"HubSpot: Received {len(events)} webhook events")
        conn = get_conn()
        cur = get_dict_cursor(conn)

        for event in events:
            sub_type = event.get("subscriptionType", "")
            prop_name = event.get("propertyName", "")
            prop_value = event.get("propertyValue", "")
            object_id = str(event.get("objectId", ""))

            if sub_type == "engagement.propertyChange" and prop_name == "hs_engagement_status":
                new_status = "completed" if prop_value == "COMPLETED" else "cancelled" if prop_value == "CANCELED" else None
                if new_status:
                    cur.execute("SELECT id FROM businesses WHERE hubspot_portal_id = %s", (str(event.get("portalId", "")),))
                    biz = cur.fetchone()
                    if biz:
                        cur.execute("SELECT id FROM appointments WHERE hubspot_meeting_id = %s", (object_id,))
                        apt = cur.fetchone()
                        if apt:
                            cur.execute("UPDATE appointments SET status = %s WHERE id = %s", (new_status, apt["id"]))
                            conn.commit()
                            logger.info(f"HubSpot Sync: Updated appointment {apt['id']} to {new_status}")

        cur.close(); conn.close()
        return "OK"
    except Exception as e:
        logger.error(f"HubSpot Webhook Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── POST /api/webhooks/vapi/tool ──────────────────────────────────────────────

@router.post("/vapi/tool")
async def vapi_tool_webhook(request: Request):
    signature = request.headers.get("x-vapi-signature", "")
    raw_body = await request.body()
    raw_body_str = raw_body.decode("utf-8")

    if not verify_vapi_signature(raw_body_str, signature):
        logger.warning("[webhook/tool] Invalid Vapi signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    tool_name = data.get("toolName", "")
    parameters = data.get("parameters", {})
    appointment_id = parameters.get("appointmentId")

    if not appointment_id:
        raise HTTPException(status_code=400, detail="Missing appointmentId")

    logger.info(f"[webhook/tool] {tool_name} for appointment {appointment_id}")

    conn = get_conn()
    cur = get_dict_cursor(conn)

    try:
        if tool_name == "confirm_appointment":
            cur.execute("UPDATE appointments SET status = 'confirmed', updated_at = NOW() WHERE id = %s", (appointment_id,))
            conn.commit()
            cur.close(); conn.close()
            return {"result": "Appointment confirmed successfully."}

        elif tool_name == "cancel_appointment":
            cur.execute("""
                UPDATE appointments
                SET status = 'cancelled', cancelled_at = NOW(),
                    cancellation_reason = 'Cancelled by patient via AI call', updated_at = NOW()
                WHERE id = %s
            """, (appointment_id,))
            conn.commit()
            cur.execute("SELECT business_id FROM appointments WHERE id = %s", (appointment_id,))
            apt_biz = cur.fetchone()
            if apt_biz:
                import asyncio
                asyncio.create_task(_hubspot_update_meeting(apt_biz["business_id"], appointment_id, "cancelled"))
            cur.close(); conn.close()
            return {"result": "Appointment cancelled. We will follow up if needed."}

        elif tool_name == "reschedule_appointment":
            new_date = parameters.get("newDate", "")
            import re
            if not new_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", new_date):
                cur.close(); conn.close()
                return {"result": "Please provide a valid date (e.g. tomorrow or a specific day)."}

            cur.execute("""
                SELECT a.start_time, a.end_time, a.business_id, a.provider_id,
                       EXTRACT(EPOCH FROM (a.end_time::timestamptz - a.start_time::timestamptz))/60 AS duration_minutes
                FROM appointments a WHERE a.id = %s
            """, (appointment_id,))
            apt = cur.fetchone()
            if not apt:
                cur.close(); conn.close()
                return {"result": "Appointment not found."}

            target_day = datetime.strptime(new_date + "T12:00:00", "%Y-%m-%dT%H:%M:%S").weekday()
            day_of_week = (target_day + 1) % 7  # convert to Sun=0

            cur.execute("SELECT start_time FROM availability WHERE business_id = %s AND day_of_week = %s AND is_available = 1 LIMIT 1", (apt["business_id"], day_of_week))
            avail = cur.fetchone()
            open_time = str(avail["start_time"]) if avail else "09:00"
            duration = round(float(apt["duration_minutes"] or 30))

            new_start = datetime.strptime(f"{new_date}T{open_time[:5]}:00", "%Y-%m-%dT%H:%M:%S")
            new_end = new_start + timedelta(minutes=duration)

            cur.execute("""
                UPDATE appointments
                SET start_time = %s, end_time = %s, status = 'confirmed', updated_at = NOW()
                WHERE id = %s
            """, (new_start.isoformat(), new_end.isoformat(), appointment_id))
            conn.commit()

            cur.execute("SELECT u.email FROM users u JOIN appointments a ON a.user_id = u.id WHERE a.id = %s", (appointment_id,))
            user_row = cur.fetchone()
            if user_row and user_row.get("email"):
                import asyncio
                asyncio.create_task(_hubspot_update_meeting(apt["business_id"], appointment_id, "confirmed"))

            cur.close(); conn.close()
            formatted = new_start.strftime("%A, %B %-d at %-I:%M %p")
            return {"result": f"Appointment rescheduled to {formatted}. All confirmed!"}

        else:
            cur.close(); conn.close()
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")

    except Exception as e:
        logger.error(f"[webhook/tool] DB error: {e}")
        conn.rollback(); cur.close(); conn.close()
        raise HTTPException(status_code=500, detail="Internal error — please try again.")
