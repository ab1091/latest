"""Admin routes — Python/FastAPI port of admin.ts"""
import os
import uuid
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
from core.config import (DEFAULT_BUSINESS_ID, TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL)
from pydantic import BaseModel
from core.auth_scope import get_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")


# ── Models ────────────────────────────────────────────────────────────────────

class ServiceBody(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: Optional[float] = 0


class ServiceUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None


class ProviderBody(BaseModel):
    name: str
    specialty: Optional[str] = ""
    bio: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ProviderUpdateBody(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


class SettingsBody(BaseModel):
    name: str
    receptionistName: Optional[str] = ""


# ── Services ──────────────────────────────────────────────────────────────────

@router.get("/services")
def get_services(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT * FROM services WHERE business_id = %s ORDER BY name ASC", (scope["businessId"],))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"success": True, "data": {"services": [dict(r) for r in rows]}}


@router.post("/services", status_code=201)
def create_service(body: ServiceBody, request: Request):
    scope = get_scope(request)
    svc_id = str(uuid.uuid4())
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute(
        "INSERT INTO services (id, business_id, name, description, duration_minutes, price, is_active, created_at) VALUES (%s, %s, %s, %s, %s, %s, 1, NOW())",
        (svc_id, scope["businessId"], body.name.strip(), body.description, body.duration_minutes, body.price or 0),
    )
    conn.commit()
    cur.execute("SELECT * FROM services WHERE id = %s", (svc_id,))
    created = cur.fetchone()
    cur.close(); conn.close()
    return {"success": True, "data": {"service": dict(created)}}


@router.put("/services/{svc_id}")
def update_service(svc_id: str, body: ServiceUpdateBody, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute(
        "UPDATE services SET name=%s, description=%s, duration_minutes=%s, price=%s, is_active=%s WHERE id=%s AND business_id=%s",
        (body.name, body.description, body.duration_minutes, body.price or 0,
         1 if body.is_active else 0, svc_id, scope["businessId"]),
    )
    conn.commit()
    cur.execute("SELECT * FROM services WHERE id = %s", (svc_id,))
    updated = cur.fetchone()
    cur.close(); conn.close()
    return {"success": True, "data": {"service": dict(updated)}}


@router.delete("/services/{svc_id}")
def delete_service(svc_id: str, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE services SET is_active = 0 WHERE id = %s AND business_id = %s", (svc_id, scope["businessId"]))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}


# ── Providers ─────────────────────────────────────────────────────────────────

@router.get("/providers")
def get_providers(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT * FROM providers WHERE business_id = %s ORDER BY name ASC", (scope["businessId"],))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"success": True, "data": {"providers": [dict(r) for r in rows]}}


@router.post("/providers", status_code=201)
def create_provider(body: ProviderBody, request: Request):
    scope = get_scope(request)
    prov_id = str(uuid.uuid4())
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute(
        "INSERT INTO providers (id, business_id, name, specialty, bio, phone, email, is_active, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW())",
        (prov_id, scope["businessId"], body.name.strip(), body.specialty or "", body.bio, body.phone, body.email),
    )
    conn.commit()
    cur.execute("SELECT * FROM providers WHERE id = %s", (prov_id,))
    created = cur.fetchone()
    cur.close(); conn.close()
    return {"success": True, "data": {"provider": dict(created)}}


@router.put("/providers/{prov_id}")
def update_provider(prov_id: str, body: ProviderUpdateBody, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute(
        "UPDATE providers SET name=%s, specialty=%s, bio=%s, phone=%s, email=%s, is_active=%s WHERE id=%s AND business_id=%s",
        (body.name, body.specialty or "", body.bio, body.phone, body.email,
         1 if body.is_active else 0, prov_id, scope["businessId"]),
    )
    conn.commit()
    cur.execute("SELECT * FROM providers WHERE id = %s", (prov_id,))
    updated = cur.fetchone()
    cur.close(); conn.close()
    return {"success": True, "data": {"provider": dict(updated)}}


@router.delete("/providers/{prov_id}")
def delete_provider(prov_id: str, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE providers SET is_active = 0 WHERE id = %s AND business_id = %s", (prov_id, scope["businessId"]))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}


# ── Business Settings ─────────────────────────────────────────────────────────

@router.get("/settings")
def get_settings(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT name, settings FROM businesses WHERE id = %s", (scope["businessId"],))
    biz = cur.fetchone()
    cur.close(); conn.close()
    try:
        settings = json.loads(biz["settings"] or "{}") if biz else {}
    except Exception:
        settings = {}
    return {"success": True, "data": {"name": biz["name"] if biz else "", "receptionistName": settings.get("receptionistName", "")}}


@router.put("/settings")
def update_settings(body: SettingsBody, request: Request):
    scope = get_scope(request)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Clinic name required")
    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT settings FROM businesses WHERE id = %s", (scope["businessId"],))
    biz = cur.fetchone()
    try:
        settings = json.loads(biz["settings"] or "{}") if biz else {}
    except Exception:
        settings = {}
    settings["receptionistName"] = body.receptionistName.strip() if body.receptionistName else settings.get("receptionistName", "")
    cur.execute("UPDATE businesses SET name = %s, settings = %s WHERE id = %s", (body.name.strip(), json.dumps(settings), scope["businessId"]))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}


# GET /api/admin/users — admin only
@router.get("/users")
def list_users(request: Request):
    scope = get_scope(request)
    caller_role = scope.get("role")
    if caller_role not in ("admin", "staff", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        # staff can only see customer accounts
        role_filter = "AND u.role = 'customer'" if caller_role == "staff" else ""
        cur.execute(f"""
            SELECT u.id, u.email, u.first_name, u.last_name, u.role,
                   u.agent_id, u.agent_ids, u.permissions, u.created_at
            FROM users u
            WHERE u.business_id = %s {role_filter}
            ORDER BY u.created_at DESC
        """, (scope["businessId"],))
        rows = cur.fetchall()

        # Fetch all agents for name lookup
        cur.execute("SELECT id, name FROM ai_agents WHERE business_id = %s", (scope["businessId"],))
        agent_map = {a["id"]: a["name"] for a in cur.fetchall()}

        def _fmt(r):
            d = dict(r)
            if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
                d["created_at"] = d["created_at"].isoformat() + "Z"
            # Build agent_ids list (merge agent_id + agent_ids, deduplicate)
            ids = list(d.get("agent_ids") or [])
            if d.get("agent_id") and d["agent_id"] not in ids:
                ids.insert(0, d["agent_id"])
            d["agent_ids"] = ids
            d["agent_names"] = [agent_map.get(i, i) for i in ids]
            # Keep legacy agent_name for compatibility
            d["agent_name"] = agent_map.get(d.get("agent_id"), "") if d.get("agent_id") else ""
            return d
        return {"success": True, "data": {"users": [_fmt(r) for r in rows]}}
    finally:
        cur.close(); conn.close()


# PATCH /api/admin/users/:user_id — update role / agents
@router.patch("/users/{user_id}")
def update_user(user_id: str, body: dict, request: Request):
    scope = get_scope(request)
    caller_role = scope.get("role")
    if caller_role not in ("admin", "staff", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    conn = get_conn()
    cur  = get_dict_cursor(conn)
    try:
        # staff: verify target is a customer, and block role changes
        if caller_role == "staff":
            cur.execute("SELECT role FROM users WHERE id = %s AND business_id = %s", (user_id, scope["businessId"]))
            target = cur.fetchone()
            if not target or target["role"] != "customer":
                raise HTTPException(status_code=403, detail="Staff can only edit customer accounts")
            if "role" in body and body["role"] != "customer":
                raise HTTPException(status_code=403, detail="Staff cannot change user role")
            if "password" in body:
                raise HTTPException(status_code=403, detail="Staff cannot reset passwords")
            if "permissions" in body:
                raise HTTPException(status_code=403, detail="Staff cannot grant module permissions")

        set_parts, values = [], []

        if "role" in body:
            set_parts.append("role = %s"); values.append(body["role"])
        if "first_name" in body:
            set_parts.append("first_name = %s"); values.append(body["first_name"])
        if "last_name" in body:
            set_parts.append("last_name = %s"); values.append(body["last_name"])
        if body.get("password"):
            # Only admin/super_admin ever reach here with "password" in body —
            # staff is rejected above before this point.
            from api.auth.router import _hash_password
            set_parts.append("password_hash = %s"); values.append(_hash_password(body["password"]))
        if "permissions" in body:
            perms = body["permissions"] or []
            if not isinstance(perms, list):
                perms = [perms] if perms else []
            set_parts.append("permissions = %s"); values.append(perms)

        # Handle agent_ids (multi-select list)
        if "agent_ids" in body:
            ids = body["agent_ids"] or []
            if not isinstance(ids, list):
                ids = [ids] if ids else []
            set_parts.append("agent_ids = %s"); values.append(ids)
            # Also update legacy agent_id to first in list (or null)
            set_parts.append("agent_id = %s"); values.append(ids[0] if ids else None)
        elif "agent_id" in body:
            # Legacy single assign — keep working
            aid = body["agent_id"]
            set_parts.append("agent_id = %s"); values.append(aid)
            set_parts.append("agent_ids = %s"); values.append([aid] if aid else [])

        if not set_parts:
            raise HTTPException(status_code=400, detail="No valid fields")

        values.extend([user_id, scope["businessId"]])
        cur.execute(
            f"UPDATE users SET {', '.join(set_parts)} WHERE id = %s AND business_id = %s RETURNING id, email, role",
            values
        )
        conn.commit()
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "data": {"user": dict(row)}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
