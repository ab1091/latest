"""
CRM Settings — Lead Statuses, Assignment Rules, Lead Scoring Rules,
Pipeline Management (reuses Lead Statuses), Communication Rules.
"""
import uuid
import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from psycopg2.extras import Json

from core.auth import get_business_id, require_admin
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm-settings")

DEFAULT_STAGES = [
    {"key": "new_lead", "label": "New Lead", "color": "#818cf8", "sort_order": 0},
    {"key": "old_lead", "label": "Old Lead", "color": "#fb923c", "sort_order": 1},
    {"key": "connected", "label": "Connected", "color": "#38bdf8", "sort_order": 2},
    {"key": "quoted", "label": "Quoted", "color": "#34d399", "sort_order": 3},
    {"key": "appointment_scheduled", "label": "Appointment Scheduled", "color": "#60a5fa", "sort_order": 4},
    {"key": "closed", "label": "Closed Won", "color": "#4cc7a9", "sort_order": 5, "is_closed_won": True},
    {"key": "dead", "label": "Closed Lost / Trip", "color": "#f87171", "sort_order": 6, "is_closed_lost": True},
]

DEFAULT_SCORING_WEIGHTS = {
    "sms_engagement": 25, "call_engagement": 25, "appointment_activity": 20,
    "quote_requests": 15, "ai_sentiment": 15,
}


# ── Lead Statuses / Pipeline Management ──────────────────────────────────────

@router.get("/stages")
def get_stages(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM lead_stages WHERE business_id = %s ORDER BY sort_order ASC", (business_id,))
        stages = [dict(r) for r in cur.fetchall()]
        if not stages:
            for s in DEFAULT_STAGES:
                cur.execute(
                    "INSERT INTO lead_stages (id, business_id, key, label, color, sort_order, is_closed_won, is_closed_lost) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (f"stg_{uuid.uuid4().hex[:12]}", business_id, s["key"], s["label"], s["color"], s["sort_order"],
                     s.get("is_closed_won", False), s.get("is_closed_lost", False)),
                )
            conn.commit()
            cur.execute("SELECT * FROM lead_stages WHERE business_id = %s ORDER BY sort_order ASC", (business_id,))
            stages = [dict(r) for r in cur.fetchall()]
        return {"success": True, "data": {"stages": stages}}
    finally:
        cur.close(); conn.close()


class StageIn(BaseModel):
    key: str
    label: str
    color: str
    sort_order: int = 0
    is_closed_won: bool = False
    is_closed_lost: bool = False


@router.put("/stages")
def update_stages(body: list[StageIn], request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        for s in body:
            cur.execute(
                """
                INSERT INTO lead_stages (id, business_id, key, label, color, sort_order, is_closed_won, is_closed_lost)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (business_id, key) DO UPDATE SET
                    label = EXCLUDED.label, color = EXCLUDED.color, sort_order = EXCLUDED.sort_order,
                    is_closed_won = EXCLUDED.is_closed_won, is_closed_lost = EXCLUDED.is_closed_lost
                """,
                (f"stg_{uuid.uuid4().hex[:12]}", business_id, s.key, s.label, s.color, s.sort_order,
                 s.is_closed_won, s.is_closed_lost),
            )
        conn.commit()
        cur.execute("SELECT * FROM lead_stages WHERE business_id = %s ORDER BY sort_order ASC", (business_id,))
        return {"success": True, "data": {"stages": [dict(r) for r in cur.fetchall()]}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# ── Assignment Rules ─────────────────────────────────────────────────────────

@router.get("/assignment-rules")
def get_assignment_rules(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM assignment_rules WHERE business_id = %s", (business_id,))
        rule = cur.fetchone()
        return {"success": True, "data": {"rule": dict(rule) if rule else {"mode": "manual", "config": {}}}}
    finally:
        cur.close(); conn.close()


class AssignmentRuleIn(BaseModel):
    mode: str
    config: dict = {}


@router.put("/assignment-rules")
def update_assignment_rules(body: AssignmentRuleIn, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    if body.mode not in ("round_robin", "team_based", "territory_based", "manual"):
        raise HTTPException(status_code=400, detail="Invalid mode")
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            """
            INSERT INTO assignment_rules (id, business_id, mode, config, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (business_id) DO UPDATE SET mode = EXCLUDED.mode, config = EXCLUDED.config, updated_at = NOW()
            """,
            (f"ar_{uuid.uuid4().hex[:12]}", business_id, body.mode, Json(body.config)),
        )
        conn.commit()
        return {"success": True, "data": {"rule": {"mode": body.mode, "config": body.config}}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# ── Lead Scoring Rules ───────────────────────────────────────────────────────

@router.get("/scoring-rules")
def get_scoring_rules(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM lead_scoring_rules WHERE business_id = %s", (business_id,))
        rules = [dict(r) for r in cur.fetchall()]
        if not rules:
            for factor, weight in DEFAULT_SCORING_WEIGHTS.items():
                cur.execute(
                    "INSERT INTO lead_scoring_rules (id, business_id, factor_key, weight, enabled) VALUES (%s, %s, %s, %s, TRUE)",
                    (f"lsr_{uuid.uuid4().hex[:12]}", business_id, factor, weight),
                )
            conn.commit()
            cur.execute("SELECT * FROM lead_scoring_rules WHERE business_id = %s", (business_id,))
            rules = [dict(r) for r in cur.fetchall()]
        return {"success": True, "data": {"rules": rules}}
    finally:
        cur.close(); conn.close()


class ScoringRuleIn(BaseModel):
    factor_key: str
    weight: int
    enabled: bool = True


@router.put("/scoring-rules")
def update_scoring_rules(body: list[ScoringRuleIn], request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        for r in body:
            cur.execute(
                """
                INSERT INTO lead_scoring_rules (id, business_id, factor_key, weight, enabled)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (business_id, factor_key) DO UPDATE SET weight = EXCLUDED.weight, enabled = EXCLUDED.enabled
                """,
                (f"lsr_{uuid.uuid4().hex[:12]}", business_id, r.factor_key, r.weight, r.enabled),
            )
        conn.commit()
        cur.execute("SELECT * FROM lead_scoring_rules WHERE business_id = %s", (business_id,))
        return {"success": True, "data": {"rules": [dict(r) for r in cur.fetchall()]}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# ── Communication Rules ──────────────────────────────────────────────────────

@router.get("/communication-rules")
def get_communication_rules(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM communication_rules WHERE business_id = %s", (business_id,))
        rule = cur.fetchone()
        if not rule:
            cur.execute("INSERT INTO communication_rules (business_id) VALUES (%s)", (business_id,))
            conn.commit()
            cur.execute("SELECT * FROM communication_rules WHERE business_id = %s", (business_id,))
            rule = cur.fetchone()
        return {"success": True, "data": {"rule": dict(rule)}}
    finally:
        cur.close(); conn.close()


class CommunicationRulesIn(BaseModel):
    quiet_hours_start: str = "09:00"
    quiet_hours_end: str = "20:00"
    timezone: str = "America/Chicago"
    max_sms_per_day: int = 5
    max_calls_per_day: int = 3
    channels_enabled: dict = {"sms": True, "whatsapp": True, "call": True, "email": False}


@router.put("/communication-rules")
def update_communication_rules(body: CommunicationRulesIn, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            """
            INSERT INTO communication_rules
                (business_id, quiet_hours_start, quiet_hours_end, timezone, max_sms_per_day, max_calls_per_day, channels_enabled, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (business_id) DO UPDATE SET
                quiet_hours_start = EXCLUDED.quiet_hours_start, quiet_hours_end = EXCLUDED.quiet_hours_end,
                timezone = EXCLUDED.timezone, max_sms_per_day = EXCLUDED.max_sms_per_day,
                max_calls_per_day = EXCLUDED.max_calls_per_day, channels_enabled = EXCLUDED.channels_enabled, updated_at = NOW()
            """,
            (business_id, body.quiet_hours_start, body.quiet_hours_end, body.timezone,
             body.max_sms_per_day, body.max_calls_per_day, Json(body.channels_enabled)),
        )
        conn.commit()
        cur.execute("SELECT * FROM communication_rules WHERE business_id = %s", (business_id,))
        return {"success": True, "data": {"rule": dict(cur.fetchone())}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
