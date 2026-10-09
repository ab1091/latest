"""
Leads router — CRUD + CSV import
"""
import csv
import io
import json
import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, BackgroundTasks, Form
import openpyxl
from pydantic import BaseModel

from core.auth import get_business_id, get_scope, require_admin
from core.db import get_conn, dict_cursor
from core.lead_lifecycle import transition_lead_status, STAGE_OF, InvalidTransition
from core.workflow_engine import enroll_default_workflows_for_stage
from core.lead_assignment import assign_lead
from core.lead_scoring import recompute_score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leads")


def normalize_phone(ph: str) -> str:
    """Strip formatting to bare digits + prefix, matching the raw From= number
    inbound SMS/call webhooks send us — leads stored with parens/dashes/spaces
    (e.g. the manual Add Lead form) never match on inbound lookup otherwise."""
    if not ph:
        return ph
    if ph.startswith("+"):
        digits = "".join(c for c in ph[1:] if c.isdigit())
        return f"+{digits}"
    digits = "".join(c for c in ph if c.isdigit())
    if not digits:
        return ph
    return f"+{digits}" if len(digits) > 10 else f"+1{digits}"


class LeadIn(BaseModel):
    first_name:        str
    last_name:         str = ""
    email:             str = ""
    phone:             str = ""
    tags:              list[str] = []
    status:            str = "new"
    strategy:          str = ""
    source:            str = "manual"
    notes:             str = ""
    auto_sms:          bool = True
    preferred_channel: str = "sms"
    policy_type:       str = ""


class LeadUpdate(BaseModel):
    first_name:        Optional[str] = None
    last_name:         Optional[str] = None
    email:             Optional[str] = None
    phone:             Optional[str] = None
    tags:              Optional[list[str]] = None
    status:            Optional[str] = None
    strategy:          Optional[str] = None
    notes:             Optional[str] = None
    preferred_channel: Optional[str] = None
    policy_type:       Optional[str] = None


# GET /api/leads
@router.get("")
def list_leads(
    request: Request, status: Optional[str] = None, stage: Optional[str] = None, tag: Optional[str] = None,
    score_band: Optional[str] = None,
    engagement: Optional[str] = None,     # 'replied' | 'no_reply'
    follow_up: Optional[str] = None,      # '1' -> has an open task
    appointment: Optional[str] = None,    # 'upcoming' | 'no_show' | 'completed' | 'none'
    opted_out: Optional[str] = None,      # 'true' | 'false'
):
    scope = get_scope(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        inner_query = """
            SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
                   l.tags, l.sub_status, l.stage, l.strategy, l.source, l.notes,
                   l.agent_id, l.created_by, l.created_at, l.updated_at,
                   l.preferred_channel, l.policy_type,
                   l.score, l.score_band, l.opted_out,
                   EXISTS (
                       SELECT 1 FROM messages m
                       JOIN conversations c ON c.id = m.conversation_id
                       WHERE c.lead_id = l.id AND m.role = 'user'
                   ) AS has_replied,
                   (SELECT count(*) FROM tasks t WHERE t.lead_id = l.id AND t.status = 'open') AS open_tasks_count,
                   (SELECT start_time FROM appointments a
                    WHERE a.lead_id = l.id AND a.status IN ('pending', 'confirmed') AND a.start_time > now()
                    ORDER BY a.start_time ASC LIMIT 1) AS next_appointment_at,
                   (SELECT status FROM appointments a
                    WHERE a.lead_id = l.id ORDER BY a.start_time DESC LIMIT 1) AS last_appointment_status
            FROM leads l
            WHERE l.business_id = %s
        """
        params = [scope["business_id"]]
        # Admin sees ALL business leads, staff/agent sees only their own
        if not scope["is_admin"]:
            inner_query += " AND l.created_by = %s"
            params.append(scope["user_id"])
        if status:
            inner_query += " AND l.sub_status = %s"
            params.append(status)
        if stage:
            inner_query += " AND l.stage = %s"
            params.append(stage)
        if tag:
            inner_query += " AND %s = ANY(l.tags)"
            params.append(tag)

        query = f"SELECT * FROM ({inner_query}) x WHERE 1=1"
        if score_band:
            query += " AND x.score_band = %s"
            params.append(score_band)
        if engagement == "replied":
            query += " AND x.has_replied = true"
        elif engagement == "no_reply":
            query += " AND x.has_replied = false"
        if follow_up == "1":
            query += " AND x.open_tasks_count > 0"
        if appointment == "upcoming":
            query += " AND x.next_appointment_at IS NOT NULL"
        elif appointment == "no_show":
            query += " AND x.last_appointment_status = 'no_show'"
        elif appointment == "completed":
            query += " AND x.last_appointment_status = 'completed'"
        elif appointment == "none":
            query += " AND x.last_appointment_status IS NULL"
        if opted_out == "true":
            query += " AND x.opted_out = true"
        elif opted_out == "false":
            query += " AND x.opted_out = false"
        query += " ORDER BY x.created_at DESC"

        cur.execute(query, params)
        rows = cur.fetchall()
        return {"success": True, "data": {"leads": [dict(r) for r in rows]}}
    finally:
        cur.close(); conn.close()


# GET /api/leads/pipeline — Kanban board data, leads grouped by stage
@router.get("/pipeline")
def get_pipeline(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        query = """
            SELECT id, first_name, last_name, phone, tags, sub_status, stage, updated_at
            FROM leads
            WHERE business_id = %s
        """
        params = [scope["business_id"]]
        if not scope["is_admin"]:
            query += " AND created_by = %s"
            params.append(scope["user_id"])
        query += " ORDER BY updated_at DESC"
        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]

        stages = {"new_lead": [], "connected": [], "quoted": [], "closed": [], "dead": []}
        for r in rows:
            stages.setdefault(r["stage"], []).append(r)

        return {"success": True, "data": {"stages": stages}}
    finally:
        cur.close(); conn.close()


# DELETE /api/leads/clear-all
@router.delete("/clear-all")
def clear_all_leads(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE business_id = %s)", (business_id,))
        cur.execute("DELETE FROM conversations WHERE business_id = %s", (business_id,))
        cur.execute("DELETE FROM leads WHERE business_id = %s", (business_id,))
        conn.commit()
        return {"success": True, "data": {"message": "All leads and conversations deleted"}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# GET /api/leads/:id/activity  — conversations + all voice calls by phone
@router.get("/{lead_id}/activity")
def get_lead_activity(lead_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        # Get lead phone
        cur.execute("SELECT phone FROM leads WHERE id = %s AND business_id = %s", (lead_id, business_id))
        lead = cur.fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Conversations (SMS, WhatsApp, Chat, Voice)
        cur.execute("""
            SELECT c.id, c.channel, c.ai_active, c.created_at,
                   (SELECT content FROM messages m WHERE m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 1) AS last_message,
                   (SELECT created_at FROM messages m WHERE m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 1) AS last_message_at
            FROM conversations c
            WHERE c.lead_id = %s AND c.business_id = %s
            ORDER BY c.created_at DESC
        """, (lead_id, business_id))
        conversations = [dict(r) for r in cur.fetchall()]

        # Voice calls from voice_calls table — matched by phone
        voice_calls = []
        if lead["phone"]:
            cur.execute("""
                SELECT call_id, caller_name, status, outcome,
                       duration_seconds, recording_url, created_at, updated_at
                FROM voice_calls
                WHERE patient_phone = %s
                ORDER BY created_at DESC
                LIMIT 50
            """, (lead["phone"],))
            voice_calls = [dict(r) for r in cur.fetchall()]

        # Appointments — primarily linked directly via lead_id (covers SMS and
        # any other booking path); also picks up older/voice-call bookings
        # that only got linked via voice_calls.appointment_id.
        cur.execute("""
            SELECT DISTINCT ON (a.id)
                   a.id, a.start_time, a.end_time, a.status,
                   a.notes, a.created_via, a.created_at,
                   a.cancellation_reason
            FROM appointments a
            LEFT JOIN voice_calls vc ON vc.appointment_id = a.id
            WHERE a.lead_id = %s OR vc.patient_phone = %s
            ORDER BY a.id, a.start_time DESC
        """, (lead_id, lead["phone"]))
        appointments = [dict(r) for r in cur.fetchall()]

        return {"success": True, "data": {"conversations": conversations, "voice_calls": voice_calls, "appointments": appointments}}
    finally:
        cur.close(); conn.close()


# GET /api/leads/:id/journey — full merged lead lifecycle timeline:
# messages, calls, appointments, status changes, sequence progress.
# Supersedes /activity for the frontend (kept for backward compat).
@router.get("/{lead_id}/journey")
def get_lead_journey(lead_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("SELECT id, phone FROM leads WHERE id = %s AND business_id = %s", (lead_id, business_id))
        lead = cur.fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        events = []

        cur.execute("""
            SELECT c.id, c.channel, m.role, m.content, m.created_at
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE c.lead_id = %s
            ORDER BY m.created_at ASC
        """, (lead_id,))
        for r in cur.fetchall():
            events.append({"type": "message", "timestamp": r["created_at"], "data": dict(r)})

        cur.execute("""
            SELECT call_id, caller_name, status, outcome, duration_seconds, recording_url, summary, transcript, created_at
            FROM voice_calls WHERE lead_id = %s ORDER BY created_at ASC
        """, (lead_id,))
        for r in cur.fetchall():
            events.append({"type": "call", "timestamp": r["created_at"], "data": dict(r)})

        cur.execute("""
            SELECT id, start_time, end_time, status, notes, created_via, created_at, cancellation_reason
            FROM appointments WHERE lead_id = %s ORDER BY created_at ASC
        """, (lead_id,))
        for r in cur.fetchall():
            events.append({"type": "appointment", "timestamp": r["created_at"], "data": dict(r)})

        cur.execute("""
            SELECT event, from_stage, to_stage, from_sub_status, to_sub_status, metadata, created_at
            FROM lead_status_history WHERE lead_id = %s ORDER BY created_at ASC
        """, (lead_id,))
        for r in cur.fetchall():
            events.append({"type": "status_change", "timestamp": r["created_at"], "data": dict(r)})

        cur.execute("""
            SELECT wnr.node_key, wnr.node_type, wnr.status, wnr.result, wnr.created_at, wnr.completed_at,
                   w.name AS workflow_name
            FROM workflow_node_runs wnr
            JOIN lead_workflow_enrollments lwe ON lwe.id = wnr.enrollment_id
            JOIN workflows w ON w.id = lwe.workflow_id
            WHERE lwe.lead_id = %s
            ORDER BY wnr.created_at ASC
        """, (lead_id,))
        for r in cur.fetchall():
            events.append({"type": "workflow_node_run", "timestamp": r["created_at"], "data": dict(r)})

        cur.execute("SELECT id, body, created_at, author_id FROM notes WHERE lead_id = %s ORDER BY created_at ASC", (lead_id,))
        for r in cur.fetchall():
            events.append({"type": "note", "timestamp": r["created_at"], "data": dict(r)})

        cur.execute("SELECT id, title, due_at, status, created_at, completed_at FROM tasks WHERE lead_id = %s ORDER BY created_at ASC", (lead_id,))
        for r in cur.fetchall():
            events.append({"type": "task", "timestamp": r["created_at"], "data": dict(r)})

        events.sort(key=lambda e: e["timestamp"])

        return {"success": True, "data": {"events": events}}
    finally:
        cur.close(); conn.close()


# GET /api/leads/:id
@router.get("/{lead_id}")
def get_lead(lead_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute(
            """
            SELECT l.*, u.first_name AS assigned_first_name, u.last_name AS assigned_last_name
            FROM leads l
            LEFT JOIN users u ON u.id = l.assigned_user_id
            WHERE l.id = %s AND l.business_id = %s
            """,
            (lead_id, business_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead = dict(row)

        cur.execute(
            """
            SELECT e.id, e.status, e.current_node_key, e.workflow_id, w.name AS workflow_name,
                   (SELECT count(*) FROM workflow_nodes n WHERE n.workflow_id = w.id) AS total_nodes,
                   wnr.started_at AS node_started_at,
                   sc.scheduled_at AS next_action_at
            FROM lead_workflow_enrollments e
            JOIN workflows w ON w.id = e.workflow_id
            LEFT JOIN workflow_node_runs wnr
                   ON wnr.enrollment_id = e.id AND wnr.node_key = e.current_node_key AND wnr.status = 'scheduled'
            LEFT JOIN scheduled_callbacks sc
                   ON sc.id = wnr.scheduled_callback_id AND sc.status = 'pending'
            WHERE e.lead_id = %s
            ORDER BY e.enrolled_at DESC LIMIT 1
            """,
            (lead_id,),
        )
        enrollment = cur.fetchone()
        lead["active_enrollment"] = dict(enrollment) if enrollment else None

        cur.execute("SELECT count(*) AS n FROM tasks WHERE lead_id = %s AND status = 'open'", (lead_id,))
        lead["open_tasks_count"] = cur.fetchone()["n"]

        return {"success": True, "data": {"lead": lead}}
    finally:
        cur.close(); conn.close()


class TransitionBody(BaseModel):
    event:         str
    to_sub_status: Optional[str] = None
    metadata:      Optional[dict] = None
    force:         bool = False


# POST /api/leads/:id/transition — the ONLY sanctioned way to change lead
# status/stage. Used by ai-service (AI qualified/quoted detection, appointment
# booking) and the frontend (manual admin overrides via force=true).
@router.post("/{lead_id}/transition")
def transition_lead(lead_id: str, body: TransitionBody, request: Request):
    business_id = get_business_id(request)
    if body.force:
        require_admin(request)

    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM leads WHERE id = %s AND business_id = %s", (lead_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Lead not found")

        try:
            result = transition_lead_status(
                lead_id, event=body.event, to_sub_status=body.to_sub_status,
                conn=conn, cur=cur, metadata=body.metadata, force=body.force,
            )
        except InvalidTransition as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        conn.commit()
        return {"success": True, "data": result or {"lead_id": lead_id, "unchanged": True}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# POST /api/leads/{lead_id}/recompute-score — explicit recompute for events that
# don't necessarily change stage (e.g. a call outcome/sentiment landing without
# a stage move). transition_lead_status already recomputes on every stage/
# sub_status write, so this is only needed for the gap cases.
@router.post("/{lead_id}/recompute-score")
def recompute_lead_score(lead_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM leads WHERE id = %s AND business_id = %s", (lead_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Lead not found")
        result = recompute_score(lead_id, cur)
        conn.commit()
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# POST /api/leads/:id/generate-summary — one AI summary combining SMS + calls
@router.post("/{lead_id}/generate-summary")
def generate_lead_summary(lead_id: str, request: Request):
    from core.lead_summary import generate_and_save_summary
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM leads WHERE id = %s AND business_id = %s", (lead_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Lead not found")

        summary = generate_and_save_summary(lead_id, cur)
        if summary is None:
            from core.llm_openai import OPENAI_API_KEY
            if not OPENAI_API_KEY:
                raise HTTPException(status_code=503, detail="OpenAI is not configured — cannot generate summary.")
            raise HTTPException(status_code=422, detail="No SMS or call history yet for this lead — nothing to summarize.")

        conn.commit()
        return {"success": True, "data": {"summary": summary}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"[leads:summary] FAILED lead={lead_id} error={e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# POST /api/leads
@router.post("")
def create_lead(body: LeadIn, request: Request, background_tasks: BackgroundTasks):
    scope   = get_scope(request)
    lead_id = f"lead_{uuid.uuid4().hex[:12]}"
    phone   = normalize_phone(body.phone)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        assigned_user_id = assign_lead(
            {"tags": body.tags, "source": body.source, "preferred_channel": body.preferred_channel},
            scope["business_id"], cur,
        )
        cur.execute("""
            INSERT INTO leads
                (id, business_id, first_name, last_name, email, phone,
                 tags, sub_status, stage, strategy, source, notes, created_by, preferred_channel, assigned_user_id, policy_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (
            lead_id, scope["business_id"],
            body.first_name, body.last_name, body.email, phone,
            body.tags, body.status, STAGE_OF.get(body.status, "new_lead"), body.strategy, body.source, body.notes,
            scope["user_id"], body.preferred_channel, assigned_user_id, body.policy_type
        ))
        row = cur.fetchone()

        if body.status == "new":
            enroll_default_workflows_for_stage(lead_id, scope["business_id"], "new_lead", conn, cur)

        conn.commit()

        return {"success": True, "data": {"lead": dict(row)}}
    except Exception as e:
        conn.rollback()
        # Unique constraint violation — phone already exists for this business
        if hasattr(e, "pgcode") and e.pgcode == "23505":
            raise HTTPException(status_code=409, detail="A lead with this phone number already exists.")
        logger.error(f"[leads] create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# PATCH /api/leads/:id
@router.patch("/{lead_id}")
def update_lead(lead_id: str, body: LeadUpdate, request: Request):
    business_id = get_business_id(request)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    if fields.get("phone"):
        fields["phone"] = normalize_phone(fields["phone"])

    # status changes go through the state machine (as a forced manual override),
    # not the generic column UPDATE below — sub_status/stage stay consistent
    # and get an audit trail entry either way.
    new_status = fields.pop("status", None)

    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM leads WHERE id = %s AND business_id = %s", (lead_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Lead not found")

        if fields:
            sets   = ", ".join(f"{k} = %s" for k in fields)
            values = list(fields.values()) + [lead_id, business_id]
            cur.execute(
                f"UPDATE leads SET {sets}, updated_at = NOW() WHERE id = %s AND business_id = %s",
                values
            )

        if new_status:
            transition_lead_status(lead_id, event="manual_override", to_sub_status=new_status,
                                    conn=conn, cur=cur, force=True)

        conn.commit()
        cur.execute("SELECT * FROM leads WHERE id = %s AND business_id = %s", (lead_id, business_id))
        row = cur.fetchone()
        return {"success": True, "data": {"lead": dict(row)}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# DELETE /api/leads/:id
@router.delete("/{lead_id}")
def delete_lead(lead_id: str, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM leads WHERE id = %s AND business_id = %s",
            (lead_id, business_id)
        )
        conn.commit()
        return {"success": True}
    finally:
        cur.close(); conn.close()


# POST /api/leads/import  — CSV or Excel upload
def _col(row: dict, *keys) -> str:
    row_lower = {k.lower().replace("_", "").replace(" ", ""): str(v).strip() if v is not None else "" for k, v in row.items()}
    for key in keys:
        val = row_lower.get(key.lower().replace("_", "").replace(" ", ""), "")
        if val:
            return val
    return ""


def _guess_header(headers: list[str], *keys) -> str:
    """Best-guess which of the sheet's actual header strings matches a target
    field, using the same loose (case/space/underscore-insensitive) matching
    as _col — used to pre-fill the import column-mapping UI so most sheets
    need zero manual mapping, only the ones with unrecognized header names."""
    normalized = {h.lower().replace("_", "").replace(" ", ""): h for h in headers}
    for key in keys:
        hit = normalized.get(key.lower().replace("_", "").replace(" ", ""))
        if hit:
            return hit
    return ""


def _parse_upload(filename: str, content: bytes) -> list[dict]:
    """Parse an uploaded CSV/Excel file into a list of row-dicts keyed by the
    sheet's own header strings. Wrapped — a corrupt/wrong-format file or a
    non-UTF-8 CSV (e.g. Windows Excel's default CSV export is Windows-1252,
    not UTF-8) used to raise here completely uncaught, producing a raw
    "Internal Server Error" with nothing actionable in it."""
    filename = (filename or "").lower()
    rows: list[dict] = []
    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws = wb.active
            first_row = next(ws.iter_rows(min_row=1, max_row=1), None)
            if first_row is None:
                raise HTTPException(status_code=400, detail="This file has no rows — nothing to import.")
            headers = [str(c.value).strip() if c.value else "" for c in first_row]
            for ws_row in ws.iter_rows(min_row=2, values_only=True):
                rows.append({headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(ws_row)})
        else:
            # Excel's own CSV export defaults to Windows-1252 on Windows, not
            # UTF-8 — try the common encodings in order rather than failing
            # outright on the first mismatch. latin-1 never raises (every
            # byte value is valid in it), so it's a safe last resort.
            text = None
            for encoding in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            rows = list(csv.DictReader(io.StringIO(text)))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read this file — make sure it's a valid CSV or Excel file. ({e})")
    return rows


MAPPING_FIELDS = {
    "first_name":  ("firstName", "first_name", "FirstName", "firstname", "name"),
    "last_name":   ("lastName",  "last_name",  "LastName",  "lastname"),
    "email":       ("email",     "Email",      "EMAIL"),
    "phone":       ("phone",     "Phone",      "PHONE", "phoneNumber", "phone_number", "mobile", "cell", "cellphone", "contactnumber"),
    "tags":        ("tags",      "Tags",       "TAGS",  "tag"),
    "status":      ("status",    "Status",     "STATUS"),
    "notes":       ("notes",     "Notes",      "NOTES"),
    "policy_type": ("policyType", "policy_type", "PolicyType", "Policy Type", "insuranceType", "insurance_type", "Insurance Type"),
}


@router.post("/import/preview")
async def import_leads_preview(file: UploadFile = File(...)):
    """Parses the file and returns its headers + a small sample, with a
    best-guess column mapping — lets the frontend show a mapping step (so the
    user can correct a misdetected phone/name column, e.g. a sheet with
    "Mobile Number" or "Cell" instead of "phone") before any leads are
    actually created. Does not touch the database."""
    content  = await file.read()
    filename = file.filename or ""
    rows = _parse_upload(filename, content)
    if not rows:
        raise HTTPException(status_code=400, detail="This file has no rows — nothing to import.")

    headers = list(rows[0].keys())
    guesses = {field: _guess_header(headers, *keys) for field, keys in MAPPING_FIELDS.items()}
    sample = [{h: row.get(h, "") for h in headers} for row in rows[:5]]

    return {"success": True, "data": {
        "headers": headers, "guesses": guesses, "sample_rows": sample, "total_rows": len(rows),
    }}


@router.post("/import")
async def import_leads(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    mapping: Optional[str] = Form(None),
):
    scope       = get_scope(request)
    business_id = scope["business_id"]
    is_admin    = scope["role"] in ("admin", "super_admin")
    content     = await file.read()

    can_update = update_existing
    call_index = 0

    # Explicit column mapping from the import wizard, e.g.
    # {"phone": "Mobile Number", "first_name": "Full Name"} — takes priority
    # over the fixed-alias guessing in _col below for whichever fields it
    # covers, since the user has confirmed those directly. Any field the
    # mapping omits (or maps to "") still falls back to _col's guess, so a
    # partial mapping (e.g. only correcting "phone") doesn't break the rest.
    col_map: dict = {}
    if mapping:
        try:
            col_map = json.loads(mapping) or {}
        except Exception:
            col_map = {}

    def _mapped(row: dict, field: str, *fallback_keys) -> str:
        header = col_map.get(field)
        if header:
            val = row.get(header, "")
            return str(val).strip() if val is not None else ""
        return _col(row, *fallback_keys)

    rows = _parse_upload(file.filename, content)

    conn    = get_conn()
    cur     = dict_cursor(conn)
    created = 0
    updated = 0
    skipped = 0
    errors  = []

    try:
        for i, row in enumerate(rows):
            # A fully blank row (every column empty) is just incidental noise —
            # trailing blank lines are common in CSV/Excel exports. Not worth
            # counting as "skipped" or reporting a reason for; only rows that
            # have SOME data but are missing what's required should surface.
            if not any(str(v).strip() for v in row.values() if v is not None):
                continue

            fn = _mapped(row, "first_name", *MAPPING_FIELDS["first_name"])
            ln = _mapped(row, "last_name",  *MAPPING_FIELDS["last_name"])
            em = _mapped(row, "email",      *MAPPING_FIELDS["email"]).lower()
            ph = _mapped(row, "phone",      *MAPPING_FIELDS["phone"])
            ph_raw = ph
            # Fix Excel scientific notation e.g. 9.23097E+11 → 923096604743
            if ph and ('e' in ph.lower() or 'E' in ph) and not ph.startswith("+"):
                try:
                    ph = str(int(float(ph)))
                except Exception:
                    pass
            # Normalize phone: strip non-digits then add + prefix
            ph_digits = "".join(c for c in ph if c.isdigit())
            if ph_digits and not ph.startswith("+"):
                ph = f"+{ph_digits}" if len(ph_digits) > 10 else f"+1{ph_digits}"
            # A non-empty phone column that doesn't actually contain a real
            # phone number ("notaphone", "555") used to sail straight through
            # as a "valid" non-empty value and get saved as-is (confirmed
            # live: leads created with phone='notaphone' and phone='+1555').
            # Require at least 10 digits, matching the NANP length the
            # normalization above already assumes.
            phone_invalid = bool(ph_raw) and len("".join(c for c in ph if c.isdigit())) < 10
            if phone_invalid:
                ph = ""
            tg_raw = _mapped(row, "tags", *MAPPING_FIELDS["tags"])
            tg = [t.strip() for t in tg_raw.split(",") if t.strip()]
            st = _mapped(row, "status", *MAPPING_FIELDS["status"]) or None
            notes = _mapped(row, "notes", *MAPPING_FIELDS["notes"]) or None
            gd_raw = _col(row, "gender", "Gender", "GENDER", "sex").strip().lower()
            gd = gd_raw if gd_raw in ("male", "female") else None
            pt = _mapped(row, "policy_type", *MAPPING_FIELDS["policy_type"])

            if not fn and not ph:
                skipped += 1
                if phone_invalid:
                    errors.append(f"Row {i+2}: skipped — '{ph_raw}' isn't a valid phone number, and no first name was given either")
                else:
                    errors.append(f"Row {i+2}: skipped — missing both first name and phone")
                continue

            if phone_invalid:
                errors.append(f"Row {i+2}: '{ph_raw}' isn't a valid phone number — imported without a phone number")

            try:
                # Check if lead with this phone already exists
                existing = None
                if ph:
                    cur.execute(
                        "SELECT id, opted_out FROM leads WHERE business_id = %s AND phone = %s",
                        (business_id, ph)
                    )
                    existing = cur.fetchone()

                if existing:
                    if can_update:
                        # Build update fields from CSV — only override non-empty values
                        update_fields: dict = {}
                        if fn: update_fields["first_name"] = fn
                        if ln: update_fields["last_name"]  = ln
                        if em: update_fields["email"]      = em
                        if tg: update_fields["tags"]       = tg
                        if gd: update_fields["gender"]     = gd
                        if pt: update_fields["policy_type"] = pt
                        # Never let a CSV re-upload resurrect an opted-out lead's
                        # stage/sub_status — this is a raw UPDATE, not
                        # lead_lifecycle.transition_lead_status(), so it bypasses
                        # the TRANSITIONS state machine entirely. Setting status
                        # from the CSV (e.g. "new") would flip stage back from
                        # 'dead' to 'new_lead' while opted_out stayed TRUE,
                        # leaving an inconsistent state where the lead no longer
                        # trips the dead-stage guard every call/workflow path
                        # checks, even though they explicitly opted out.
                        if st and not existing.get("opted_out"):
                            update_fields["sub_status"] = st
                            update_fields["stage"]      = STAGE_OF.get(st, "new_lead")
                        if notes: update_fields["notes"]   = notes
                        if update_fields:
                            sets   = ", ".join(f"{k} = %s" for k in update_fields)
                            values = list(update_fields.values()) + [existing["id"]]
                            cur.execute(
                                f"UPDATE leads SET {sets}, updated_at = NOW() WHERE id = %s",
                                values
                            )
                            updated += 1
                            logger.info(f"[leads:import] updated existing lead id={existing['id']} phone={ph} fields={list(update_fields.keys())}")
                        else:
                            skipped += 1
                            errors.append(f"Row {i+2}: skipped — lead with phone {ph} already exists, but every column in this row was blank so there was nothing to update")
                    else:
                        skipped += 1
                        errors.append(f"Row {i+2}: skipped — a lead with phone {ph} already exists (turn on \"Update existing leads\" to update it instead)")
                else:
                    lead_id = f"lead_{uuid.uuid4().hex[:12]}"
                    resolved_status = st or "new"
                    cur.execute("""
                        INSERT INTO leads
                            (id, business_id, first_name, last_name, email, phone, tags, sub_status, stage, notes, gender, policy_type, source, created_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'import', %s)
                    """, (lead_id, business_id, fn, ln, em, ph, tg, resolved_status,
                          STAGE_OF.get(resolved_status, "new_lead"), notes or "", gd, pt or "", scope["user_id"]))
                    created += 1
                    logger.info(f"[leads:import] created lead id={lead_id} phone={ph}")
                    if resolved_status == "new" and ph:
                        enroll_default_workflows_for_stage(lead_id, business_id, "new_lead", conn, cur)

                conn.commit()
            except Exception as e:
                errors.append(f"Row {i+2}: {e}")
                conn.rollback()

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()

    logger.info(f"[leads:import] done — created={created} updated={updated} skipped={skipped} errors={len(errors)}")
    return {"success": True, "data": {"created": created, "updated": updated, "skipped": skipped, "errors": errors}}
