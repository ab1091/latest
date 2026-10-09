"""
CRM Routes — Python (FastAPI)
Handles HubSpot contacts/meetings and local DB contact stats.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
import httpx

from api.common     import get_user
from core.db     import get_conn, get_dict_cursor
from core.hubspot import hs_headers, HUBSPOT_ACCESS_TOKEN, HS_BASE
from core.auth_scope import get_business_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm")


# ── Routes ────────────────────────────────────────────────────────────────────

# GET /api/crm/hubspot/contacts
@router.get("/hubspot/contacts")
async def hubspot_contacts(request: Request, after: Optional[str] = None):
    get_business_id(request)
    if not HUBSPOT_ACCESS_TOKEN:
        raise HTTPException(status_code=503, detail="HubSpot not connected")

    params = {
        "limit": 50,
        "properties": "firstname,lastname,email,phone,createdate,lastmodifieddate",
    }
    if after:
        params["after"] = after

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{HS_BASE}/crm/v3/objects/contacts", headers=hs_headers(), params=params)

    if not res.is_success:
        raise HTTPException(status_code=500, detail=res.text)

    data = res.json()
    contacts = [
        {
            "id":        c["id"],
            "firstName": c["properties"].get("firstname") or "",
            "lastName":  c["properties"].get("lastname")  or "",
            "email":     c["properties"].get("email")     or "",
            "phone":     c["properties"].get("phone")     or "",
            "createdAt": c["properties"].get("createdate"),
            "updatedAt": c["properties"].get("lastmodifieddate"),
        }
        for c in data.get("results", [])
    ]

    return {"success": True, "data": {"contacts": contacts, "paging": data.get("paging")}}


# GET /api/crm/hubspot/contacts/:hsId/meetings
@router.get("/hubspot/contacts/{hs_id}/meetings")
async def hubspot_contact_meetings(hs_id: str, request: Request):
    get_business_id(request)
    if not HUBSPOT_ACCESS_TOKEN:
        raise HTTPException(status_code=503, detail="HubSpot not connected")

    async with httpx.AsyncClient(timeout=10) as client:
        assoc_res = await client.get(
            f"{HS_BASE}/crm/v4/objects/contacts/{hs_id}/associations/meetings",
            headers=hs_headers(),
        )

    if not assoc_res.is_success:
        return {"success": True, "data": {"meetings": []}}

    meeting_ids = [r["toObjectId"] for r in assoc_res.json().get("results", [])]
    if not meeting_ids:
        return {"success": True, "data": {"meetings": []}}

    props = "hs_meeting_title,hs_meeting_start_time,hs_meeting_end_time,hs_meeting_outcome,hs_meeting_body,meeting_external_id"
    meetings = []

    async with httpx.AsyncClient(timeout=10) as client:
        for mid in meeting_ids[:20]:
            r = await client.get(
                f"{HS_BASE}/crm/v3/objects/meetings/{mid}",
                headers=hs_headers(),
                params={"properties": props},
            )
            if r.is_success:
                m = r.json()
                meetings.append({
                    "id":         m["id"],
                    "title":      m["properties"].get("hs_meeting_title") or "Meeting",
                    "startTime":  m["properties"].get("hs_meeting_start_time"),
                    "endTime":    m["properties"].get("hs_meeting_end_time"),
                    "outcome":    m["properties"].get("hs_meeting_outcome") or "SCHEDULED",
                    "notes":      m["properties"].get("hs_meeting_body") or "",
                    "externalId": m["properties"].get("meeting_external_id") or "",
                })

    return {"success": True, "data": {"meetings": meetings}}


# GET /api/crm/hubspot/stats
@router.get("/hubspot/stats")
async def hubspot_stats(request: Request):
    get_business_id(request)
    if not HUBSPOT_ACCESS_TOKEN:
        raise HTTPException(status_code=503, detail="HubSpot not connected")

    async with httpx.AsyncClient(timeout=10) as client:
        c_res = await client.get(f"{HS_BASE}/crm/v3/objects/contacts", headers=hs_headers(), params={"limit": 1})
        m_res = await client.get(f"{HS_BASE}/crm/v3/objects/meetings", headers=hs_headers(), params={"limit": 1})

    return {
        "success": True,
        "data": {
            "totalContacts": c_res.json().get("total", 0) if c_res.is_success else 0,
            "totalMeetings": m_res.json().get("total", 0) if m_res.is_success else 0,
        },
    }


# GET /api/crm/contacts  — local DB contacts with appointment stats
@router.get("/contacts")
def crm_contacts(request: Request):
    business_id = get_business_id(request)

    conn = get_conn()
    cur  = get_dict_cursor(conn)
    cur.execute("""
        SELECT u.id, u.email, u.first_name, u.last_name, u.phone, u.role, u.created_at,
               COUNT(a.id)::text                                               AS total,
               COUNT(a.id) FILTER (WHERE a.status = 'confirmed')::text         AS confirmed,
               COUNT(a.id) FILTER (WHERE a.status = 'completed')::text         AS completed,
               COUNT(a.id) FILTER (WHERE a.status = 'cancelled')::text         AS cancelled,
               MAX(a.start_time)::text                                          AS last_apt
        FROM users u
        LEFT JOIN appointments a ON a.user_id = u.id AND a.business_id = %s
        WHERE u.business_id = %s
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """, (business_id, business_id))
    contacts = cur.fetchall()
    cur.close(); conn.close()

    return {"success": True, "data": {"contacts": [dict(c) for c in contacts]}}


# GET /api/crm/stats
@router.get("/stats")
def crm_stats(request: Request):
    business_id = get_business_id(request)

    conn = get_conn()
    cur  = get_dict_cursor(conn)
    cur.execute("""
        SELECT
            (SELECT COUNT(*) FROM users        WHERE business_id = %s)::text AS total_contacts,
            (SELECT COUNT(*) FROM appointments WHERE business_id = %s)::text AS total_apts,
            (SELECT COUNT(*) FROM appointments WHERE business_id = %s AND status = 'confirmed')::text  AS confirmed,
            (SELECT COUNT(*) FROM appointments WHERE business_id = %s AND status = 'completed')::text  AS completed,
            (SELECT COUNT(*) FROM appointments WHERE business_id = %s AND status = 'cancelled')::text  AS cancelled
    """, (business_id, business_id, business_id, business_id, business_id))
    row = cur.fetchone()
    cur.close(); conn.close()

    return {"success": True, "data": dict(row)}


# GET /api/crm/contacts/:id/appointments
@router.get("/contacts/{contact_id}/appointments")
def contact_appointments(contact_id: str, request: Request):
    business_id = get_business_id(request)

    conn = get_conn()
    cur  = get_dict_cursor(conn)
    cur.execute("""
        SELECT a.id, a.start_time, a.end_time, a.status, a.notes,
               p.name AS provider_name, s.name AS service_name
        FROM appointments a
        LEFT JOIN providers p ON p.id = a.provider_id
        LEFT JOIN services  s ON s.id = a.service_id
        WHERE a.user_id = %s AND a.business_id = %s
        ORDER BY a.start_time DESC
    """, (contact_id, business_id))
    apts = cur.fetchall()
    cur.close(); conn.close()

    return {"success": True, "data": {"appointments": [dict(a) for a in apts]}}


@router.get("/calls")
def get_call_history(request: Request):
    payload     = get_user(request)
    business_id = get_business_id(request)
    user_id     = payload.get("userId")
    role        = payload.get("role", "customer")
    is_super_admin = role in ("admin", "super_admin")  # agency admin or platform super_admin see all; staff see only their own

    conn = get_conn()
    cur  = get_dict_cursor(conn)

    base_query = """
        SELECT DISTINCT ON (vc.created_at, vc.id)
            vc.id, vc.call_id, vc.direction, vc.patient_phone,
            vc.status, vc.outcome, vc.duration_seconds,
            vc.caller_name, vc.created_at,
            vc.transcript, vc.summary, vc.recording_url,
            s.name  AS service_name,
            p.name  AS provider_name,
            NULLIF(l.email, '') AS lead_email,
            COALESCE(
                NULLIF(vc.caller_name, ''),
                NULLIF(TRIM(CONCAT(l.first_name, ' ', COALESCE(l.last_name, ''))), ''),
                vc.patient_phone
            ) AS display_name
        FROM voice_calls vc
        LEFT JOIN appointments a  ON a.id  = vc.appointment_id
        LEFT JOIN services     s  ON s.id  = a.service_id
        LEFT JOIN providers    p  ON p.id  = a.provider_id
        LEFT JOIN leads        l  ON l.phone = vc.patient_phone AND l.business_id = %s
        WHERE (a.business_id = %s OR a.business_id IS NULL)
    """
    params = [business_id, business_id]

    if not is_super_admin:
        base_query += " AND l.created_by = %s"
        params.append(user_id)

    # No LIMIT here on purpose — this endpoint doubles as the data source for
    # dashboard/export aggregate stats (total calls, picked-up, voicemail,
    # etc.), which must reflect the true count. A LIMIT 100 here previously
    # made both the "Total Calls" tile and the aggregate breakdowns silently
    # wrong once real volume passed 100 (confirmed live: 199 real calls, tile
    # showed exactly 100 — the round number was the tell).
    base_query += " ORDER BY vc.created_at DESC, vc.id"

    cur.execute(base_query, params)
    rows = cur.fetchall()
    cur.close(); conn.close()

    result = []
    for r in rows:
        outcome_raw = (r["outcome"] or "").lower()
        # call_failed (Vapi API-level rejection, e.g. daily cap — before dialing
        # ever happened) must stay distinct from "info", or dashboard/export
        # logic that checks against no_answer/voicemail/failed/call_failed
        # silently miscounts these as picked-up calls.
        if outcome_raw not in ("confirmed", "cancelled", "reschedule_requested", "no_answer", "voicemail", "failed", "call_failed", "info"):
            outcome_raw = "info"

        result.append({
            "id":               r["id"],
            "callId":           r["call_id"],
            "call_type":        r["direction"] or "inbound",
            "direction":        r["direction"] or "inbound",
            "phone":            r["patient_phone"] or "—",
            "status":           r["status"] or "ended",
            "outcome":          outcome_raw,
            "duration_seconds": r["duration_seconds"] or 0,
            "durationSeconds":  r["duration_seconds"] or 0,
            "patientName":      r["display_name"] or r["patient_phone"] or "—",
            "email":            r["lead_email"],
            "serviceName":      r["service_name"] or None,
            "providerName":     r["provider_name"] or None,
            "transcript":       r["transcript"] or None,
            "summary":          r["summary"] or None,
            "recordingUrl":     r["recording_url"] or None,
            "created_at":       r["created_at"].isoformat() + "Z" if r["created_at"] else None,
            "createdAt":        r["created_at"].isoformat() + "Z" if r["created_at"] else None,
        })
    return {"success": True, "data": {"calls": result}}


# ── POST /api/crm/calls/send-recording — test endpoint ───────────────────────

from pydantic import BaseModel as _BaseModel

class SendRecordingBody(_BaseModel):
    phone: str
    name: Optional[str] = None
    recording_url: Optional[str] = None
    call_id: Optional[str] = None

@router.post("/calls/send-recording")
async def send_recording_sms(body: SendRecordingBody, request: Request):
    """Send recording link to a phone number via WhatsApp/SMS.

    Only ever sends our own /api/calls/{call_id}/recording proxy link — never
    the raw Azure blob URL (that storage account has public access disabled,
    so a raw link is dead on arrival for anyone without a signed SAS token).
    call_id is required either directly or via a matching recording_url
    lookup; a bare recording_url with no resolvable call_id is refused
    rather than falling back to sending that raw URL.
    """
    get_user(request)  # auth check

    call_id = body.call_id
    conn = get_conn(); cur = get_dict_cursor(conn)
    try:
        if not call_id and body.recording_url:
            cur.execute("SELECT call_id, caller_name FROM voice_calls WHERE recording_url = %s LIMIT 1", (body.recording_url,))
            row = cur.fetchone()
            if row:
                call_id = row["call_id"]
                if not body.name:
                    body.name = row["caller_name"]
        elif call_id and not body.name:
            cur.execute("SELECT caller_name FROM voice_calls WHERE call_id = %s LIMIT 1", (call_id,))
            row = cur.fetchone()
            if row:
                body.name = row["caller_name"]
    finally:
        cur.close(); conn.close()

    if not call_id:
        raise HTTPException(status_code=400, detail="No call_id found for this recording")

    from core.sms import send_recording
    await send_recording(body.phone, body.name or "", call_id)
    return {"success": True, "message": f"Recording sent to {body.phone}"}
