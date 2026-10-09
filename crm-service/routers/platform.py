"""
Platform / Super Admin — cross-agency views for AllZone's own team.
Every endpoint here is require_super_admin-gated; nothing here is
reachable by a regular agency admin or staff member.
"""
import uuid
import logging
import bcrypt
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from core.auth import require_super_admin
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/platform")


@router.get("/agencies")
def list_agencies(request: Request):
    require_super_admin(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT b.id, b.name, b.email, b.status, b.created_at,
                   (SELECT count(*) FROM users u WHERE u.business_id = b.id) AS staff_count,
                   (SELECT count(*) FROM leads l WHERE l.business_id = b.id) AS lead_count,
                   (SELECT count(*) FROM workflows w WHERE w.business_id = b.id AND w.status = 'active') AS active_workflows,
                   (SELECT max(created_at) FROM activity_feed_events e WHERE e.business_id = b.id) AS last_activity_at,
                   COALESCE((SELECT p.name FROM subscriptions s JOIN plans p ON p.id = s.plan_id WHERE s.business_id = b.id), 'No plan') AS plan_name
            FROM businesses b
            ORDER BY b.created_at DESC
        """)
        return {"success": True, "data": {"agencies": [dict(r) for r in cur.fetchall()]}}
    finally:
        cur.close(); conn.close()


@router.get("/agencies/{business_id}")
def get_agency(business_id: str, request: Request):
    require_super_admin(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM businesses WHERE id = %s", (business_id,))
        biz = cur.fetchone()
        if not biz:
            raise HTTPException(status_code=404, detail="Agency not found")
        cur.execute("SELECT id, email, first_name, last_name, role, created_at FROM users WHERE business_id = %s ORDER BY created_at ASC", (business_id,))
        users = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT count(*) AS n, stage FROM leads WHERE business_id = %s GROUP BY stage", (business_id,))
        stage_counts = {r["stage"]: r["n"] for r in cur.fetchall()}
        cur.execute(
            """
            SELECT s.status, p.name AS plan_name, p.price_cents, s.current_period_end
            FROM subscriptions s JOIN plans p ON p.id = s.plan_id WHERE s.business_id = %s
            """,
            (business_id,),
        )
        sub = cur.fetchone()
        return {
            "success": True,
            "data": {
                "agency": dict(biz), "users": users, "stage_counts": stage_counts,
                "subscription": dict(sub) if sub else None,
            },
        }
    finally:
        cur.close(); conn.close()


class ProvisionAgencyBody(BaseModel):
    name: str
    email: str
    admin_email: str
    admin_password: str
    admin_first_name: Optional[str] = ""
    admin_last_name: Optional[str] = ""


@router.post("/agencies", status_code=201)
def provision_agency(body: ProvisionAgencyBody, request: Request):
    require_super_admin(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM users WHERE email = %s", (body.admin_email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="An account with that admin email already exists")

        biz_id = f"bus_{uuid.uuid4().hex[:10]}"
        cur.execute(
            "INSERT INTO businesses (id, name, email, status) VALUES (%s, %s, %s, 'trial')",
            (biz_id, body.name, body.email),
        )

        user_id = str(uuid.uuid4())
        # Same bcrypt scheme ai-service's own signup uses (api/auth/router.py:_hash_password) —
        # crm-service has no login endpoint of its own, but users it creates must still be
        # verifiable by ai-service's /api/auth/login against this same hash format.
        password_hash = bcrypt.hashpw(body.admin_password.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (id, business_id, email, password_hash, first_name, last_name, role) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'admin')",
            (user_id, biz_id, body.admin_email, password_hash, body.admin_first_name, body.admin_last_name),
        )
        conn.commit()
        return {"success": True, "data": {"business_id": biz_id, "admin_user_id": user_id}}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


@router.get("/analytics")
def platform_analytics(request: Request):
    require_super_admin(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT count(*) AS n FROM businesses")
        total_agencies = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM leads")
        total_leads = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM voice_calls")
        total_calls = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM messages")
        total_messages = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM workflows WHERE status = 'active'")
        active_workflows = cur.fetchone()["n"]
        cur.execute("""
            SELECT COALESCE(sum(p.price_cents), 0) AS n FROM subscriptions s
            JOIN plans p ON p.id = s.plan_id WHERE s.status IN ('active', 'trialing')
        """)
        mrr_cents = cur.fetchone()["n"]
        cur.execute("""
            SELECT b.name, count(l.id) AS lead_count FROM businesses b
            LEFT JOIN leads l ON l.business_id = b.id
            GROUP BY b.id, b.name ORDER BY lead_count DESC LIMIT 10
        """)
        top_agencies = [dict(r) for r in cur.fetchall()]

        return {
            "success": True,
            "data": {
                "total_agencies": total_agencies, "total_leads": total_leads,
                "total_calls": total_calls, "total_messages": total_messages,
                "active_workflows": active_workflows, "mrr_cents": mrr_cents,
                "top_agencies": top_agencies,
            },
        }
    finally:
        cur.close(); conn.close()
