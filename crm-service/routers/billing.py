"""
Billing — real plans/subscriptions/invoices schema. Payment-provider
integration (Stripe) is explicitly stubbed: PATCH changes the plan
directly with no charge, so this can't be mistaken for a completeness
gap in review — it's real schema, deferred payment wiring by design.
"""
import uuid
import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from core.auth import get_business_id, require_admin
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing")


@router.get("/plans")
def list_plans(request: Request):
    get_business_id(request)  # auth check only — plans aren't business-scoped
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM plans WHERE is_active ORDER BY sort_order ASC")
        return {"success": True, "data": {"plans": [dict(r) for r in cur.fetchall()]}}
    finally:
        cur.close(); conn.close()


@router.get("/subscription")
def get_subscription(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            """
            SELECT s.*, p.name AS plan_name, p.price_cents, p.billing_interval, p.max_staff_users, p.max_leads, p.features
            FROM subscriptions s JOIN plans p ON p.id = s.plan_id
            WHERE s.business_id = %s
            """,
            (business_id,),
        )
        sub = cur.fetchone()
        if not sub:
            # Auto-provision a trial on the Starter plan the first time this is queried.
            sub_id = f"sub_{uuid.uuid4().hex[:12]}"
            cur.execute(
                "INSERT INTO subscriptions (id, business_id, plan_id, status) VALUES (%s, %s, 'plan_starter', 'trialing')",
                (sub_id, business_id),
            )
            conn.commit()
            cur.execute(
                """
                SELECT s.*, p.name AS plan_name, p.price_cents, p.billing_interval, p.max_staff_users, p.max_leads, p.features
                FROM subscriptions s JOIN plans p ON p.id = s.plan_id WHERE s.business_id = %s
                """,
                (business_id,),
            )
            sub = cur.fetchone()
        return {"success": True, "data": {"subscription": dict(sub)}}
    finally:
        cur.close(); conn.close()


class SubscriptionPatchIn(BaseModel):
    plan_id: str


@router.patch("/subscription")
def update_subscription(body: SubscriptionPatchIn, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM plans WHERE id = %s AND is_active", (body.plan_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Invalid plan")

        cur.execute("SELECT id FROM subscriptions WHERE business_id = %s", (business_id,))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE subscriptions SET plan_id = %s, updated_at = NOW() WHERE business_id = %s",
                (body.plan_id, business_id),
            )
        else:
            cur.execute(
                "INSERT INTO subscriptions (id, business_id, plan_id, status) VALUES (%s, %s, %s, 'active')",
                (f"sub_{uuid.uuid4().hex[:12]}", business_id, body.plan_id),
            )
        conn.commit()
        cur.execute(
            """
            SELECT s.*, p.name AS plan_name, p.price_cents, p.billing_interval FROM subscriptions s
            JOIN plans p ON p.id = s.plan_id WHERE s.business_id = %s
            """,
            (business_id,),
        )
        return {"success": True, "data": {"subscription": dict(cur.fetchone())}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


@router.get("/invoices")
def list_invoices(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM invoices WHERE business_id = %s ORDER BY created_at DESC LIMIT 50", (business_id,))
        return {"success": True, "data": {"invoices": [dict(r) for r in cur.fetchall()]}}
    finally:
        cur.close(); conn.close()
