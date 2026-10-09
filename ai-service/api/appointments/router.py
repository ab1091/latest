"""Appointments routes — Python/FastAPI port of appointments.ts"""
import os
import uuid
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, List

import httpx
from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
from core.config import (DEFAULT_BUSINESS_ID, TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    AGENCY_CALENDAR_EMAIL,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL,
    OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID)
from pydantic import BaseModel

from core.lead_transitions import transition_via_crm_api
from core.auth_scope import get_scope
from core.timezone import now_local, BUSINESS_TIMEZONE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/appointments")


# ── Google Calendar helpers ───────────────────────────────────────────────────

async def _get_google_access_token(refresh_token: str) -> Optional[str]:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not refresh_token:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
    if r.is_success:
        return r.json().get("access_token")
    return None


async def _calendar_create(refresh_token: str, summary: str, description: str, start_iso: str, end_iso: str,
                            attendee_email: Optional[str] = None) -> Optional[str]:
    access_token = await _get_google_access_token(refresh_token)
    if not access_token:
        return None
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": BUSINESS_TIMEZONE},
        "end": {"dateTime": end_iso, "timeZone": BUSINESS_TIMEZONE},
    }
    attendees = []
    agency_email = (AGENCY_CALENDAR_EMAIL or "shieldsquadagency@gmail.com").strip()
    if agency_email:
        attendees.append({"email": agency_email})
    if attendee_email and attendee_email.strip().lower() != agency_email.lower():
        attendees.append({"email": attendee_email.strip()})
    if attendees:
        body["attendees"] = attendees

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events?sendUpdates=all",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
    if r.is_success:
        return r.json().get("id")
    return None


async def _calendar_update(refresh_token: str, event_id: str, summary: str, description: str, start_iso: str, end_iso: str) -> bool:
    access_token = await _get_google_access_token(refresh_token)
    if not access_token:
        return False
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": BUSINESS_TIMEZONE},
        "end": {"dateTime": end_iso, "timeZone": BUSINESS_TIMEZONE},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.put(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
    return r.is_success


async def _calendar_delete(refresh_token: str, event_id: str) -> bool:
    access_token = await _get_google_access_token(refresh_token)
    if not access_token:
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.delete(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return r.status_code in (200, 204, 410)


# ── Outlook Calendar helpers ──────────────────────────────────────────────────

async def _get_outlook_access_token(refresh_token: str) -> Optional[str]:
    if not OUTLOOK_CLIENT_ID or not OUTLOOK_CLIENT_SECRET or not OUTLOOK_TENANT_ID or not refresh_token:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id":     OUTLOOK_CLIENT_ID,
                "client_secret": OUTLOOK_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type":    "refresh_token",
                "scope":         "Calendars.ReadWrite offline_access",
            },
        )
    if r.is_success:
        return r.json().get("access_token")
    logger.warning(f"[outlook] Token refresh failed: {r.status_code} {r.text[:200]}")
    return None


async def _outlook_create(refresh_token: str, summary: str, description: str, start_iso: str, end_iso: str) -> Optional[str]:
    access_token = await _get_outlook_access_token(refresh_token)
    if not access_token:
        return None
    body = {
        "subject": summary,
        "body": {"contentType": "Text", "content": description},
        "start": {"dateTime": start_iso, "timeZone": BUSINESS_TIMEZONE},
        "end":   {"dateTime": end_iso,   "timeZone": BUSINESS_TIMEZONE},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://graph.microsoft.com/v1.0/me/events",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=body,
        )
    if r.is_success:
        return r.json().get("id")
    logger.warning(f"[outlook] Create event failed: {r.status_code} {r.text[:200]}")
    return None


async def _outlook_update(refresh_token: str, event_id: str, summary: str, description: str, start_iso: str, end_iso: str) -> bool:
    access_token = await _get_outlook_access_token(refresh_token)
    if not access_token:
        return False
    body = {
        "subject": summary,
        "body": {"contentType": "Text", "content": description},
        "start": {"dateTime": start_iso, "timeZone": BUSINESS_TIMEZONE},
        "end":   {"dateTime": end_iso,   "timeZone": BUSINESS_TIMEZONE},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.patch(
            f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=body,
        )
    return r.is_success


async def _outlook_delete(refresh_token: str, event_id: str) -> bool:
    access_token = await _get_outlook_access_token(refresh_token)
    if not access_token:
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.delete(
            f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return r.status_code in (200, 204, 410)


# ── HubSpot helpers ───────────────────────────────────────────────────────────

async def _hubspot_sync_meeting(appointment_id: str, start_iso: str, end_iso: str, status: str, email: str, notes: str = ""):
    if not HUBSPOT_ACCESS_TOKEN:
        return
    try:
        # Convert ISO → Unix milliseconds (HubSpot requirement)
        start_dt = datetime.fromisoformat(start_iso.replace("Z", ""))
        end_dt   = datetime.fromisoformat(end_iso.replace("Z", ""))
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms   = int(end_dt.timestamp() * 1000)

        # Map internal status to valid HubSpot outcome values
        outcome_map = {
            "confirmed": "SCHEDULED",
            "pending":   "SCHEDULED",
            "completed": "COMPLETED",
            "cancelled": "CANCELLED",
            "no_show":   "NO_SHOW",
        }
        hs_outcome = outcome_map.get(status.lower(), "SCHEDULED")

        hs_headers = {"Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            # Search for existing contact
            search_res = await client.post(
                "https://api.hubapi.com/crm/v3/objects/contacts/search",
                headers=hs_headers,
                json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}], "limit": 1},
            )
            contact_id = None
            if search_res.is_success:
                results = search_res.json().get("results", [])
                if results:
                    contact_id = results[0]["id"]

            # Create contact if not found
            if not contact_id:
                create_res = await client.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts",
                    headers=hs_headers,
                    json={"properties": {"email": email}},
                )
                if create_res.is_success:
                    contact_id = create_res.json().get("id")
                    logger.info(f"[hubspot] Contact created — id {contact_id}")

            # Create appointment with only valid properties
            appt_res = await client.post(
                "https://api.hubapi.com/crm/v3/objects/appointments",
                headers=hs_headers,
                json={"properties": {
                    "hs_appointment_name":  "Appointment",
                    "hs_appointment_start": start_ms,
                    "hs_appointment_end":   end_ms,
                }},
            )
            if appt_res.is_success:
                appt_hs_id = appt_res.json().get("id")
                logger.info(f"[hubspot] Appointment synced — id {appt_hs_id}")
                if appt_hs_id and contact_id:
                    await client.put(
                        f"https://api.hubapi.com/crm/v4/objects/appointments/{appt_hs_id}/associations/contacts/{contact_id}",
                        headers=hs_headers,
                        json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 1}],
                    )
            else:
                logger.warning(f"[hubspot] Appointment create failed: {appt_res.status_code} {appt_res.text}")
    except Exception as e:
        logger.error(f"HubSpot sync error: {e}")


# ── iMessage helper ──────────────────────────────────────────────────────────

async def _send_sms(to: str, body: str):
    from core import bluebubbles
    try:
        await bluebubbles.send_message(to, body)
    except Exception as e:
        logger.warning(f"[appointments:imessage] failed to send confirmation to {to}: {e}")


# ── Conflict check ────────────────────────────────────────────────────────────

def check_conflict(cur, business_id: str, start_iso: str, end_iso: str, provider_id: Optional[str], exclude_id: Optional[str] = None) -> Optional[dict]:
    params = [business_id]
    sql = "SELECT id FROM appointments WHERE business_id = %s AND status != 'cancelled'"
    if provider_id:
        sql += " AND provider_id = %s"
        params.append(provider_id)
    else:
        sql += " AND provider_id IS NULL"
    if exclude_id:
        sql += " AND id != %s"
        params.append(exclude_id)
    sql += " AND start_time < %s AND end_time > %s LIMIT 1"
    params.extend([end_iso, start_iso])
    cur.execute(sql, params)
    return cur.fetchone()


# ── Models ────────────────────────────────────────────────────────────────────

class CreateAppointmentBody(BaseModel):
    serviceId: Optional[str] = None
    startTime: str
    notes: Optional[str] = None
    providerId: Optional[str] = None
    googleEventId: Optional[str] = None
    # Staff/admin repair and manual-booking flows can associate the booking
    # with the actual lead instead of accidentally resolving by the logged-in
    # staff member's phone number.
    leadId: Optional[str] = None


class UpdateAppointmentBody(BaseModel):
    startTime: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class CancelBody(BaseModel):
    reason: Optional[str] = None


class SaveWebCallBody(BaseModel):
    callId: str
    outcome: str
    transcript: Optional[str] = None
    durationSeconds: Optional[float] = None


class ScheduleReminderBody(BaseModel):
    delayMinutes: Optional[int] = 1


# ── Routes — specific paths BEFORE /{id} ─────────────────────────────────────

@router.get("/providers")
def get_providers(request: Request, serviceId: str = "", serviceType: str = "", city: str = "", specialty: str = ""):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)

    params = [scope["businessId"]]
    sql = "SELECT p.* FROM providers p WHERE p.business_id = %s AND p.is_active = 1"

    if serviceId:
        sql += " AND EXISTS (SELECT 1 FROM provider_services ps WHERE ps.provider_id = p.id AND ps.business_id = p.business_id AND ps.is_active = 1 AND ps.service_id = %s)"
        params.append(serviceId)
    elif serviceType:
        sql += " AND EXISTS (SELECT 1 FROM provider_services ps JOIN services s ON s.id = ps.service_id AND s.business_id = ps.business_id AND s.is_active = 1 WHERE ps.provider_id = p.id AND ps.business_id = p.business_id AND ps.is_active = 1 AND LOWER(s.name) LIKE %s)"
        params.append(f"%{serviceType.lower()}%")

    if city:
        sql += " AND LOWER(COALESCE(p.city, '')) LIKE %s"
        params.append(f"%{city.lower()}%")
    if specialty:
        sql += " AND LOWER(COALESCE(p.specialty, '')) LIKE %s"
        params.append(f"%{specialty.lower()}%")

    sql += " ORDER BY p.name ASC LIMIT 200"
    cur.execute(sql, params)
    providers = cur.fetchall()
    cur.close(); conn.close()
    return {"success": True, "data": {"providers": [dict(p) for p in providers]}}


@router.get("/filters")
def get_filters(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT city, specialty FROM providers WHERE business_id = %s AND is_active = 1", (scope["businessId"],))
    rows = cur.fetchall()
    cur.close(); conn.close()
    cities = sorted(set(r["city"] for r in rows if r.get("city") and r["city"].strip()))
    specialties = sorted(set(r["specialty"] for r in rows if r.get("specialty") and r["specialty"].strip()))
    return {"success": True, "data": {"cities": cities, "specialties": specialties}}


@router.get("/services/list")
def get_services(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT * FROM services WHERE business_id = %s AND is_active = 1 ORDER BY name ASC", (scope["businessId"],))
    services = cur.fetchall()
    cur.close(); conn.close()
    return {"success": True, "data": {"services": [dict(s) for s in services]}}


@router.get("/business-hours")
def get_business_hours(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT * FROM availability WHERE business_id = %s ORDER BY day_of_week", (scope["businessId"],))
    hours = cur.fetchall()
    cur.close(); conn.close()
    return {"success": True, "data": {"hours": [dict(h) for h in hours]}}


@router.get("/business-info")
def get_business_info(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT id, name, address, city, phone, email, settings, timezone FROM businesses WHERE id = %s", (scope["businessId"],))
    biz = cur.fetchone()
    cur.close(); conn.close()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    import json
    try:
        settings = json.loads(biz.get("settings") or "{}")
    except Exception:
        settings = {}
    return {
        "success": True,
        "data": {
            "id": biz["id"],
            "name": biz["name"],
            "address": biz.get("address") or "",
            "city": biz.get("city") or "",
            "phone": biz.get("phone") or "",
            "email": biz.get("email") or "",
            "timezone": biz.get("timezone") or "America/Chicago",
            "description": settings.get("description", ""),
        },
    }


@router.get("/calls/all")
def get_all_calls(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("""
        SELECT vc.call_id, vc.outcome, vc.summary, vc.transcript, vc.duration_seconds,
               vc.status, vc.created_at, vc.appointment_id, vc.direction, vc.patient_phone,
               s.name AS service_name, a.start_time,
               p.name AS provider_name,
               COALESCE(
                   NULLIF(vc.caller_name, ''),
                   vc.patient_phone
               ) AS patient_display_name
        FROM voice_calls vc
        LEFT JOIN appointments a ON vc.appointment_id = a.id
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN providers p ON a.provider_id = p.id
        LEFT JOIN users apt_u ON apt_u.id = a.user_id
        LEFT JOIN users phone_u ON phone_u.phone = vc.patient_phone AND phone_u.role = 'customer'
        WHERE (a.business_id = %s OR (vc.appointment_id IS NULL AND vc.direction = 'inbound'))
        ORDER BY vc.created_at DESC
    """, (scope["businessId"],))
    calls = cur.fetchall()
    cur.close(); conn.close()

    result = []
    for c in calls:
        raw_outcome = c["outcome"] or ""
        if raw_outcome == "confirmed":
            outcome = "confirmed"
        elif raw_outcome in ("cancelled", "reschedule_requested", "no_answer", "voicemail", "failed"):
            outcome = raw_outcome
        else:
            outcome = "info"

        result.append({
            "patientName": c.get("patient_display_name") or c.get("patient_phone") or "Inbound Caller",
            "callId":          c["call_id"],
            "outcome":         outcome,
            "summary":         c["summary"],
            "transcript":      c["transcript"],
            "durationSeconds": c["duration_seconds"],
            "status":          c["status"],
            "createdAt":       str(c["created_at"]) if c.get("created_at") else None,
            "appointmentId":   c["appointment_id"],
            "direction":       c.get("direction") or "outbound",
            "serviceName":     c.get("service_name"),
            "providerName":    c.get("provider_name"),
            "appointmentDate": str(c["start_time"]) if c.get("start_time") else None,
        })
    return {"success": True, "data": result}


@router.get("/availability/{date}")
def get_availability(date: str, request: Request, providerId: str = ""):
    scope = get_scope(request)
    try:
        y, m, d = date.split("-")
        day_of_week = datetime(int(y), int(m), int(d)).weekday()
        # Convert to JS convention: 0=Sun, 1=Mon...
        day_of_week = (day_of_week + 1) % 7
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    conn = get_conn()
    cur = get_dict_cursor(conn)

    if providerId:
        cur.execute("SELECT id FROM providers WHERE id = %s AND business_id = %s AND is_active = 1", (providerId, scope["businessId"]))
        if not cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=400, detail="Invalid provider for this business")

    cur.execute("SELECT * FROM availability WHERE business_id = %s AND day_of_week = %s AND is_available = 1", (scope["businessId"], day_of_week))
    hours = cur.fetchone()

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    if not hours:
        cur.close(); conn.close()
        return {"success": True, "data": {"businessHours": None, "bookedSlots": [], "isClosedDay": True, "closedReason": f"Business is closed on {day_names[day_of_week]}"}}

    params = [scope["businessId"], f"{date}T00:00:00.000", f"{date}T23:59:59.999"]
    sql = "SELECT start_time, end_time, provider_id FROM appointments WHERE business_id = %s AND status != 'cancelled' AND start_time >= %s AND start_time <= %s"
    if providerId:
        sql += " AND provider_id = %s"
        params.append(providerId)
    cur.execute(sql, params)
    booked = cur.fetchall()
    cur.close(); conn.close()

    return {
        "success": True,
        "data": {
            "businessHours": dict(hours),
            "bookedSlots": [dict(b) for b in booked],
            "isClosedDay": False,
            "closedReason": None,
        },
    }


@router.get("")
def get_appointments(request: Request, includeCancelled: str = ""):
    scope = get_scope(request)
    include = includeCancelled.lower() in ("1", "true", "yes")
    conn = get_conn()
    cur = get_dict_cursor(conn)

    # Only super admin sees all; staff and customer see only their own
    cur.execute("SELECT role FROM users WHERE id = %s", (scope["userId"],))
    user_row = cur.fetchone()
    role = user_row["role"] if user_row else "customer"
    is_super_admin = role in ("admin", "super_admin")

    sql = """
        SELECT a.id, a.start_time, a.end_time, a.status, a.notes,
               a.google_event_id, a.provider_id, a.service_id,
               s.name AS service_name, p.name AS provider_name,
               u.first_name, u.last_name, u.email AS patient_email, u.phone AS patient_phone
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN providers p ON a.provider_id = p.id
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.business_id = %s
    """
    params = [scope["businessId"]]
    if not is_super_admin:
        sql += " AND a.user_id = %s"
        params.append(scope["userId"])
    if not include:
        sql += " AND a.status != 'cancelled'"
    sql += " ORDER BY a.start_time DESC"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    def _fmt(r):
        d = dict(r)
        for k in ("start_time", "end_time", "created_at", "updated_at", "cancelled_at"):
            if d.get(k) and hasattr(d[k], "isoformat"):
                d[k] = d[k].isoformat() + "Z"
        return d
    return {"success": True, "data": {"appointments": [_fmt(r) for r in rows]}}


@router.post("", status_code=201)
async def create_appointment(body: CreateAppointmentBody, request: Request):
    scope = get_scope(request)
    try:
        start = datetime.fromisoformat(body.startTime.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid start time")

    conn = get_conn()
    cur = get_dict_cursor(conn)

    service = None
    if body.serviceId:
        cur.execute("SELECT * FROM services WHERE id = %s AND business_id = %s AND is_active = 1", (body.serviceId, scope["businessId"]))
        service = cur.fetchone()
        if not service:
            cur.close(); conn.close()
            raise HTTPException(status_code=400, detail="Selected service is not available")

    if body.providerId:
        cur.execute("SELECT id FROM providers WHERE id = %s AND business_id = %s AND is_active = 1", (body.providerId, scope["businessId"]))
        if not cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=400, detail="Selected provider is not available")

    duration = int(service["duration_minutes"]) if service and service.get("duration_minutes") else 30
    end = start + timedelta(minutes=duration)
    start_iso = start.isoformat()
    end_iso = end.isoformat()

    if check_conflict(cur, scope["businessId"], start_iso, end_iso, body.providerId):
        cur.close(); conn.close()
        raise HTTPException(status_code=409, detail="Time slot is not available")

    appointment_id = str(uuid.uuid4())
    google_event_id = body.googleEventId or None
    calendar_sync = {"status": "skipped", "attempts": 0, "error": None}

    # Get user tokens. By default this is the logged-in customer/staff user;
    # an explicit leadId below overrides the attendee/contact fields while
    # retaining the staff user as the appointment owner.
    cur.execute("SELECT email, phone, first_name, last_name, google_refresh_token, outlook_refresh_token FROM users WHERE id = %s", (scope["userId"],))
    user_row = cur.fetchone()
    google_rt  = (user_row.get("google_refresh_token")  if user_row else None) or GOOGLE_REFRESH_TOKEN
    outlook_rt = (user_row.get("outlook_refresh_token") if user_row else None)
    user_email = user_row.get("email") if user_row else None
    svc_name   = service["name"] if service else "Appointment"

    # Resolve lead_id so this booking can drive lead-lifecycle automation.
    # Staff may explicitly select a lead; customers retain the old by-phone
    # behavior. Never accept a cross-business lead ID.
    lead_id = None
    if body.leadId:
        if not scope.get("is_staff"):
            cur.close(); conn.close()
            raise HTTPException(status_code=403, detail="Only staff can book for a lead")
        cur.execute(
            "SELECT id, first_name, last_name, phone, email FROM leads WHERE id = %s AND business_id = %s",
            (body.leadId, scope["businessId"]),
        )
        selected_lead = cur.fetchone()
        if not selected_lead:
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="Lead not found")
        lead_id = selected_lead["id"]
        user_email = selected_lead.get("email") or user_email
        user_phone = selected_lead.get("phone")
        attendee_first_name = selected_lead.get("first_name")
        attendee_last_name = selected_lead.get("last_name")
    else:
        user_phone = user_row.get("phone") if user_row else None
        attendee_first_name = user_row.get("first_name") if user_row else None
        attendee_last_name = user_row.get("last_name") if user_row else None
    if not lead_id and user_phone:
        cur.execute("SELECT id FROM leads WHERE phone = %s AND business_id = %s LIMIT 1",
                    (user_phone, scope["businessId"]))
        lead_row = cur.fetchone()
        lead_id = lead_row["id"] if lead_row else None

    # Google Calendar sync
    if not google_event_id and google_rt:
        try:
            eid = await _calendar_create(google_rt, svc_name, body.notes or "", start_iso, end_iso, user_email)
            if eid:
                google_event_id = eid
                calendar_sync = {"status": "success", "attempts": 1, "error": None}
            else:
                calendar_sync = {"status": "failed", "attempts": 1, "error": "Calendar event not created"}
        except Exception as e:
            calendar_sync = {"status": "failed", "attempts": 1, "error": str(e)}
    elif not google_event_id:
        calendar_sync = {"status": "skipped", "attempts": 1, "error": "Google Calendar not connected"}

    # Outlook Calendar sync
    outlook_event_id = None
    if outlook_rt:
        try:
            outlook_event_id = await _outlook_create(outlook_rt, svc_name, body.notes or "", start_iso, end_iso)
            if outlook_event_id:
                logger.info(f"[outlook] Event created: {outlook_event_id}")
        except Exception as e:
            logger.warning(f"[outlook] Sync error on create: {e}")

    now = datetime.utcnow().isoformat()
    cur.execute(
        """INSERT INTO appointments (id, business_id, user_id, service_id, provider_id,
               start_time, end_time, notes, status, created_at, updated_at, google_event_id, outlook_event_id, lead_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'confirmed', %s, %s, %s, %s, %s)""",
        (appointment_id, scope["businessId"], scope["userId"], body.serviceId, body.providerId,
         start_iso, end_iso, body.notes, now, now, google_event_id, outlook_event_id, lead_id),
    )
    conn.commit(); cur.close(); conn.close()

    if lead_id:
        await transition_via_crm_api(lead_id, scope["businessId"], "appointment_booked",
                                       metadata={"appointment_id": appointment_id})

    try:
        from core.admin_notify import notify_admins_appointment_booked
        booker_name = " ".join(filter(None, [attendee_first_name, attendee_last_name])).strip()
        await notify_admins_appointment_booked(scope["businessId"], booker_name or user_email or "A client", start, svc_name)
    except Exception as e:
        logger.warning(f"[appointments] admin notify failed: {e}")

    if user_email:
        try:
            from core.gmail import send_appointment_confirmation
            await send_appointment_confirmation(user_email, attendee_first_name or "there", svc_name, start)
        except Exception as e:
            logger.warning(f"[appointments] confirmation email failed: {e}")

    if user_email:
        import asyncio
        asyncio.create_task(_hubspot_sync_meeting(appointment_id, start_iso, end_iso, "confirmed", user_email, body.notes or ""))

    return {
        "success": True,
        "data": {
            "appointment": {
                "id": appointment_id,
                "startTime": start_iso,
                "endTime": end_iso,
                "status": "confirmed",
                "googleEventId": google_event_id,
                "providerId": body.providerId,
                "serviceId": body.serviceId,
            },
            "calendarSync": calendar_sync,
        },
    }


@router.put("/{apt_id}")
async def update_appointment(apt_id: str, body: UpdateAppointmentBody, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)

    is_admin_or_staff = scope.get("role") in ("admin", "staff", "super_admin")

    if is_admin_or_staff:
        cur.execute("""
            SELECT a.*, COALESCE(s.duration_minutes, 30) AS duration_minutes,
                   COALESCE(s.name, 'Appointment') AS service_name
            FROM appointments a
            LEFT JOIN services s ON a.service_id = s.id
            WHERE a.id = %s AND a.business_id = %s
        """, (apt_id, scope["businessId"]))
    else:
        cur.execute("""
            SELECT a.*, COALESCE(s.duration_minutes, 30) AS duration_minutes,
                   COALESCE(s.name, 'Appointment') AS service_name
            FROM appointments a
            LEFT JOIN services s ON a.service_id = s.id
            WHERE a.id = %s AND a.user_id = %s AND a.business_id = %s
        """, (apt_id, scope["userId"], scope["businessId"]))
    existing = cur.fetchone()
    if not existing:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    set_parts = ["updated_at = CURRENT_TIMESTAMP"]
    params = []
    new_start_iso = None
    new_end_iso = None
    calendar_sync = {"status": "skipped", "attempts": 0, "error": None}

    if body.startTime:
        try:
            new_start = datetime.fromisoformat(body.startTime.replace("Z", "+00:00"))
        except Exception:
            cur.close(); conn.close()
            raise HTTPException(status_code=400, detail="Invalid start time")
        duration = int(existing["duration_minutes"]) or 30
        new_end = new_start + timedelta(minutes=duration)
        new_start_iso = new_start.isoformat()
        new_end_iso = new_end.isoformat()

        if check_conflict(cur, scope["businessId"], new_start_iso, new_end_iso, existing.get("provider_id"), apt_id):
            cur.close(); conn.close()
            raise HTTPException(status_code=409, detail="Time slot is not available")

        set_parts.extend(["start_time = %s", "end_time = %s"])
        params.extend([new_start_iso, new_end_iso])

    if body.notes is not None:
        set_parts.append("notes = %s")
        params.append(body.notes)

    if body.status:
        set_parts.append("status = %s")
        params.append(body.status)

    if is_admin_or_staff:
        params.extend([apt_id, scope["businessId"]])
        cur.execute(f"UPDATE appointments SET {', '.join(set_parts)} WHERE id = %s AND business_id = %s", params)
    else:
        params.extend([apt_id, scope["userId"], scope["businessId"]])
        cur.execute(f"UPDATE appointments SET {', '.join(set_parts)} WHERE id = %s AND user_id = %s AND business_id = %s", params)
    conn.commit()

    if new_start_iso and new_end_iso and existing.get("google_event_id"):
        cur.execute("SELECT google_refresh_token FROM users WHERE id = %s", (scope["userId"],))
        urow = cur.fetchone()
        refresh_token = (urow.get("google_refresh_token") if urow else None) or GOOGLE_REFRESH_TOKEN
        if refresh_token:
            try:
                ok = await _calendar_update(refresh_token, existing["google_event_id"], existing["service_name"], existing.get("notes", ""), new_start_iso, new_end_iso)
                calendar_sync = {"status": "success" if ok else "failed", "attempts": 1, "error": None}
            except Exception as e:
                calendar_sync = {"status": "failed", "attempts": 1, "error": str(e)}
        else:
            calendar_sync = {"status": "skipped", "attempts": 1, "error": "Google Calendar not connected"}

    cur.close(); conn.close()
    return {"success": True, "message": "Appointment updated", "data": {"calendarSync": calendar_sync}}


@router.delete("/{apt_id}")
async def cancel_appointment(apt_id: str, request: Request, body: CancelBody = CancelBody()):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT * FROM appointments WHERE id = %s AND user_id = %s AND business_id = %s", (apt_id, scope["userId"], scope["businessId"]))
    existing = cur.fetchone()
    if not existing:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    cur.execute(
        "UPDATE appointments SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP, cancellation_reason = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s AND business_id = %s",
        (body.reason, apt_id, scope["userId"], scope["businessId"]),
    )
    conn.commit()

    calendar_sync = {"status": "skipped", "attempts": 0, "error": None}
    if existing.get("google_event_id"):
        cur.execute("SELECT google_refresh_token FROM users WHERE id = %s", (scope["userId"],))
        urow = cur.fetchone()
        refresh_token = (urow.get("google_refresh_token") if urow else None) or GOOGLE_REFRESH_TOKEN
        if refresh_token:
            try:
                ok = await _calendar_delete(refresh_token, existing["google_event_id"])
                calendar_sync = {"status": "success" if ok else "failed", "attempts": 1, "error": None}
            except Exception as e:
                calendar_sync = {"status": "failed", "attempts": 1, "error": str(e)}
        else:
            calendar_sync = {"status": "skipped", "attempts": 1, "error": "Google Calendar not connected"}

    # Send cancellation SMS
    cur.execute("""
        SELECT u.phone, u.first_name, s.name AS service_name, a.start_time
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN services s ON a.service_id = s.id
        WHERE a.id = %s
    """, (apt_id,))
    appt_details = cur.fetchone()
    cur.close(); conn.close()

    if appt_details and appt_details.get("phone"):
        try:
            start_dt = appt_details["start_time"]
            if hasattr(start_dt, "strftime"):
                date_fmt = start_dt.strftime("%A, %B %-d")
                time_fmt = start_dt.strftime("%-I:%M %p")
            else:
                dt = datetime.fromisoformat(str(start_dt))
                date_fmt = dt.strftime("%A, %B %-d")
                time_fmt = dt.strftime("%-I:%M %p")
            patient = appt_details.get("first_name") or "Patient"
            svc = appt_details.get("service_name") or "Appointment"
            reason_text = f" Reason: {body.reason}." if body.reason else ""
            sms_body = f"Hi {patient}, your {svc} appointment scheduled for {date_fmt} at {time_fmt} has been cancelled.{reason_text} Please call us to reschedule. - AllZone Scheduler"
            import asyncio
            asyncio.create_task(_send_sms(appt_details["phone"], sms_body))
        except Exception as e:
            logger.error(f"SMS send error: {e}")

    return {"success": True, "message": "Appointment cancelled", "data": {"calendarSync": calendar_sync}}


@router.get("/{apt_id}/call-status")
def get_call_status(apt_id: str):
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("""
        SELECT call_id, outcome, summary, transcript, duration_seconds, status, created_at
        FROM voice_calls WHERE appointment_id = %s ORDER BY created_at DESC LIMIT 1
    """, (apt_id,))
    record = cur.fetchone()
    cur.close(); conn.close()
    if not record:
        raise HTTPException(status_code=404, detail="No call record found")
    return {
        "success": True,
        "data": {
            "callId": record["call_id"],
            "outcome": record["outcome"],
            "summary": record["summary"],
            "transcript": record["transcript"],
            "durationSeconds": record["duration_seconds"],
            "status": record["status"],
            "createdAt": str(record["created_at"]) if record.get("created_at") else None,
        },
    }


@router.get("/{apt_id}/reschedule-options")
def get_reschedule_options(apt_id: str, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT provider_id, start_time, end_time FROM appointments WHERE id = %s AND business_id = %s", (apt_id, scope["businessId"]))
    apt = cur.fetchone()
    if not apt:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    s = apt["start_time"] if hasattr(apt["start_time"], "timestamp") else datetime.fromisoformat(str(apt["start_time"]))
    e = apt["end_time"] if hasattr(apt["end_time"], "timestamp") else datetime.fromisoformat(str(apt["end_time"]))
    duration_min = max(30, round((e.timestamp() - s.timestamp()) / 60))

    results = []
    for offset in (1, 2):
        d = now_local() + timedelta(days=offset)
        date_str = d.strftime("%Y-%m-%d")
        day_of_week = (d.weekday() + 1) % 7  # 0=Sun

        cur.execute("SELECT start_time, end_time FROM availability WHERE business_id = %s AND day_of_week = %s AND is_available = 1", (scope["businessId"], day_of_week))
        hours = cur.fetchone()
        if not hours:
            results.append({"label": date_str, "date": date_str, "slots": []})
            continue

        cur.execute("""
            SELECT start_time, end_time FROM appointments
            WHERE business_id = %s AND status != 'cancelled'
              AND start_time >= %s AND start_time < %s
        """, (scope["businessId"], f"{date_str}T00:00:00", f"{date_str}T23:59:59"))
        booked = cur.fetchall()

        open_h, open_m = [int(x) for x in str(hours["start_time"]).split(":")[:2]]
        close_h, close_m = [int(x) for x in str(hours["end_time"]).split(":")[:2]]
        open_min = open_h * 60 + open_m
        close_min = close_h * 60 + close_m

        booked_ranges = []
        for b in booked:
            bs = b["start_time"] if hasattr(b["start_time"], "timestamp") else datetime.fromisoformat(str(b["start_time"]))
            be = b["end_time"] if hasattr(b["end_time"], "timestamp") else datetime.fromisoformat(str(b["end_time"]))
            booked_ranges.append((bs.timestamp(), be.timestamp()))

        free_slots = []
        m = open_min
        while m + duration_min <= close_min:
            slot_start = datetime(d.year, d.month, d.day, m // 60, m % 60)
            slot_end = slot_start + timedelta(minutes=duration_min)
            conflict = any(slot_start.timestamp() < be and slot_end.timestamp() > bs for bs, be in booked_ranges)
            if not conflict:
                free_slots.append(slot_start.strftime("%-I:%M %p"))
            if len(free_slots) >= 2:
                break
            m += duration_min

        day_label = d.strftime("%A, %B %-d")
        results.append({"label": day_label, "date": date_str, "slots": free_slots})

    cur.close(); conn.close()
    return {"success": True, "data": results}


@router.post("/{apt_id}/save-web-call")
def save_web_call(apt_id: str, body: SaveWebCallBody, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT id, lead_id FROM appointments WHERE id = %s AND user_id = %s AND business_id = %s", (apt_id, scope["userId"], scope["businessId"]))
    apt_row = cur.fetchone()
    if not apt_row:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    cur.execute("""
        INSERT INTO voice_calls (id, appointment_id, call_id, provider, status, outcome, transcript, duration_seconds, created_at, updated_at, lead_id)
        VALUES (%s, %s, %s, 'vapi', 'ended', %s, %s, %s, NOW(), NOW(), %s)
        ON CONFLICT (call_id) DO UPDATE
          SET outcome = EXCLUDED.outcome, transcript = EXCLUDED.transcript,
              duration_seconds = EXCLUDED.duration_seconds, status = 'ended', updated_at = NOW(),
              lead_id = COALESCE(EXCLUDED.lead_id, voice_calls.lead_id)
    """, (str(uuid.uuid4()), apt_id, body.callId, body.outcome, body.transcript, body.durationSeconds, apt_row["lead_id"]))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}


@router.post("/{apt_id}/schedule-reminder")
def schedule_reminder(apt_id: str, request: Request, body: ScheduleReminderBody = ScheduleReminderBody()):
    scope = get_scope(request)
    delay = max(0, min(body.delayMinutes or 1, 60))
    conn = get_conn()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT id, business_id, user_id FROM appointments WHERE id = %s AND user_id = %s", (apt_id, scope["userId"]))
    apt = cur.fetchone()
    if not apt:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    job_id = str(uuid.uuid4())
    scheduled_for = (datetime.utcnow() + timedelta(minutes=delay)).isoformat()
    cur.execute(
        "INSERT INTO appointment_reminder_jobs (id, appointment_id, business_id, user_id, channel, scheduled_for, status) VALUES (%s, %s, %s, %s, 'ai_call', %s, 'pending')",
        (job_id, apt_id, apt["business_id"], apt["user_id"], scheduled_for),
    )
    conn.commit(); cur.close(); conn.close()
    return {"success": True, "data": {"jobId": job_id, "scheduledFor": scheduled_for}}


@router.get("/{apt_id}")
def get_appointment(apt_id: str, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("""
        SELECT a.*, s.name AS service_name, s.duration_minutes, p.name AS provider_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN providers p ON a.provider_id = p.id
        WHERE a.id = %s AND a.user_id = %s AND a.business_id = %s
    """, (apt_id, scope["userId"], scope["businessId"]))
    apt = cur.fetchone()
    cur.close(); conn.close()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return {"success": True, "data": {"appointment": dict(apt)}}
