"""Reminders routes — Python/FastAPI port of reminders.ts"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

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
router = APIRouter(prefix="/api/reminders")





def require_tool_secret(request: Request):
    received = request.headers.get("x-reminder-tool-secret", "").strip()
    if not received or received != REMINDER_TOOL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid reminder tool secret")


# ── Models ────────────────────────────────────────────────────────────────────

class ContextBody(BaseModel):
    appointmentId: str


class ConfirmBody(BaseModel):
    appointmentId: str
    summary: Optional[str] = None


class CancelBody(BaseModel):
    appointmentId: str
    summary: Optional[str] = None


class AvailabilityBody(BaseModel):
    appointmentId: str
    date: str  # YYYY-MM-DD


class RescheduleBody(BaseModel):
    appointmentId: str
    newStartTime: str  # ISO datetime
    summary: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_reminder_context(appointment_id: str) -> dict:
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("""
        SELECT a.id, a.start_time, a.end_time, a.status, a.notes,
               u.first_name, u.last_name, u.phone, u.email,
               s.name AS service_name, s.duration_minutes,
               p.name AS provider_name
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN providers p ON a.provider_id = p.id
        WHERE a.id = %s
    """, (appointment_id,))
    apt = cur.fetchone()
    cur.close(); conn.close()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return dict(apt)


def confirm_appointment(appointment_id: str, summary: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE appointments SET status = 'confirmed', updated_at = NOW() WHERE id = %s", (appointment_id,))
    if summary:
        cur.execute("UPDATE voice_calls SET summary = %s, updated_at = NOW() WHERE appointment_id = %s", (summary, appointment_id))
    conn.commit(); cur.close(); conn.close()


def cancel_appointment_reminder(appointment_id: str, summary: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE appointments
        SET status = 'cancelled', cancelled_at = NOW(),
            cancellation_reason = 'Cancelled via AI reminder call', updated_at = NOW()
        WHERE id = %s
    """, (appointment_id,))
    if summary:
        cur.execute("UPDATE voice_calls SET summary = %s, updated_at = NOW() WHERE appointment_id = %s", (summary, appointment_id))
    conn.commit(); cur.close(); conn.close()


def get_reschedule_availability(appointment_id: str, date: str) -> dict:
    conn = get_conn()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT business_id, start_time, end_time FROM appointments WHERE id = %s", (appointment_id,))
    apt = cur.fetchone()
    if not apt:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    s = apt["start_time"] if hasattr(apt["start_time"], "timestamp") else datetime.fromisoformat(str(apt["start_time"]))
    e = apt["end_time"] if hasattr(apt["end_time"], "timestamp") else datetime.fromisoformat(str(apt["end_time"]))
    duration_min = max(30, round((e.timestamp() - s.timestamp()) / 60))

    try:
        y, m, d = date.split("-")
        dt = datetime(int(y), int(m), int(d))
        day_of_week = (dt.weekday() + 1) % 7  # 0=Sun
    except Exception:
        cur.close(); conn.close()
        raise HTTPException(status_code=400, detail="Invalid date format")

    cur.execute("SELECT start_time, end_time FROM availability WHERE business_id = %s AND day_of_week = %s AND is_available = 1", (apt["business_id"], day_of_week))
    hours = cur.fetchone()

    if not hours:
        cur.close(); conn.close()
        return {"date": date, "available": False, "slots": []}

    cur.execute("""
        SELECT start_time, end_time FROM appointments
        WHERE business_id = %s AND status != 'cancelled'
          AND start_time >= %s AND start_time < %s
    """, (apt["business_id"], f"{date}T00:00:00", f"{date}T23:59:59"))
    booked = cur.fetchall()
    cur.close(); conn.close()

    open_h, open_m = [int(x) for x in str(hours["start_time"]).split(":")[:2]]
    close_h, close_m = [int(x) for x in str(hours["end_time"]).split(":")[:2]]
    open_min = open_h * 60 + open_m
    close_min = close_h * 60 + close_m

    booked_ranges = []
    for b in booked:
        bs = b["start_time"] if hasattr(b["start_time"], "timestamp") else datetime.fromisoformat(str(b["start_time"]))
        be = b["end_time"] if hasattr(b["end_time"], "timestamp") else datetime.fromisoformat(str(b["end_time"]))
        booked_ranges.append((bs.timestamp(), be.timestamp()))

    slots = []
    for mins in range(open_min, close_min - duration_min + 1, duration_min):
        slot_start = datetime(int(y), int(m), int(d), mins // 60, mins % 60)
        slot_end = slot_start + timedelta(minutes=duration_min)
        if not any(slot_start.timestamp() < be and slot_end.timestamp() > bs for bs, be in booked_ranges):
            slots.append(slot_start.isoformat())
        if len(slots) >= 3:
            break

    return {"date": date, "available": bool(slots), "slots": slots}


def reschedule_appointment(appointment_id: str, new_start_time: str, summary: Optional[str] = None):
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT start_time, end_time FROM appointments WHERE id = %s", (appointment_id,))
    apt = cur.fetchone()
    if not apt:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    s = apt["start_time"] if hasattr(apt["start_time"], "timestamp") else datetime.fromisoformat(str(apt["start_time"]))
    e = apt["end_time"] if hasattr(apt["end_time"], "timestamp") else datetime.fromisoformat(str(apt["end_time"]))
    duration_min = max(30, round((e.timestamp() - s.timestamp()) / 60))

    new_start = datetime.fromisoformat(new_start_time.replace("Z", "+00:00"))
    new_end = new_start + timedelta(minutes=duration_min)

    cur.execute("""
        UPDATE appointments
        SET start_time = %s, end_time = %s, status = 'confirmed', updated_at = NOW()
        WHERE id = %s
    """, (new_start.isoformat(), new_end.isoformat(), appointment_id))
    if summary:
        cur.execute("UPDATE voice_calls SET summary = %s, updated_at = NOW() WHERE appointment_id = %s", (summary, appointment_id))
    conn.commit(); cur.close(); conn.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/voice/webhook")
async def voice_webhook(request: Request):
    # Simplified — just acknowledge
    return {"success": True, "data": {}}


@router.post("/tools/context")
def tools_context(body: ContextBody, request: Request):
    require_tool_secret(request)
    context = get_reminder_context(body.appointmentId)
    return {"success": True, "data": context}


@router.post("/tools/confirm")
def tools_confirm(body: ConfirmBody, request: Request):
    require_tool_secret(request)
    confirm_appointment(body.appointmentId, body.summary)
    return {"success": True, "data": {"appointmentId": body.appointmentId, "disposition": "confirmed"}}


@router.post("/tools/cancel")
def tools_cancel(body: CancelBody, request: Request):
    require_tool_secret(request)
    cancel_appointment_reminder(body.appointmentId, body.summary)
    return {"success": True, "data": {"appointmentId": body.appointmentId, "disposition": "cancelled"}}


@router.post("/tools/reschedule/availability")
def tools_reschedule_availability(body: AvailabilityBody, request: Request):
    require_tool_secret(request)
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", body.date):
        raise HTTPException(status_code=400, detail="Use YYYY-MM-DD for date")
    availability = get_reschedule_availability(body.appointmentId, body.date)
    return {"success": True, "data": availability}


@router.post("/tools/reschedule/commit")
def tools_reschedule_commit(body: RescheduleBody, request: Request):
    require_tool_secret(request)
    reschedule_appointment(body.appointmentId, body.newStartTime, body.summary)
    return {
        "success": True,
        "data": {
            "appointmentId": body.appointmentId,
            "disposition": "rescheduled",
            "newStartTime": body.newStartTime,
        },
    }
