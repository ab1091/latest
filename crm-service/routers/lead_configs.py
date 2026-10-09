"""
Lead Configuration router — tag-based routing rules
IF condition (tag/source) → THEN execute (agent + provider + calendar)
"""
import uuid
import logging
from typing import Optional, Any
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from core.auth import get_business_id, require_admin
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lead-configs")


class Condition(BaseModel):
    field:    str          # "tag" | "source" | "status"
    operator: str          # "equals" | "contains" | "any"
    value:    str


class LeadConfigIn(BaseModel):
    name:             str
    condition_logic:  str = "any"    # "any" | "all"
    conditions:       list[Condition] = []
    agent_id:         Optional[str] = None
    provider_id:      Optional[str] = None
    calendar_enabled: bool = False
    status:           str = "active"


class LeadConfigUpdate(BaseModel):
    name:             Optional[str] = None
    condition_logic:  Optional[str] = None
    conditions:       Optional[list[Any]] = None
    agent_id:         Optional[str] = None
    provider_id:      Optional[str] = None
    calendar_enabled: Optional[bool] = None
    status:           Optional[str] = None


# GET /api/lead-configs
@router.get("")
def list_configs(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT lc.id, lc.name, lc.condition_logic, lc.conditions,
                   lc.agent_id, lc.provider_id, lc.calendar_enabled,
                   lc.status, lc.created_at,
                   a.name AS agent_name, a.role AS agent_role
            FROM lead_configs lc
            LEFT JOIN ai_agents a ON a.id = lc.agent_id
            WHERE lc.business_id = %s
            ORDER BY lc.created_at DESC
        """, (business_id,))
        rows = cur.fetchall()
        return {"success": True, "data": {"configs": [dict(r) for r in rows]}}
    finally:
        cur.close(); conn.close()


# POST /api/lead-configs
@router.post("")
def create_config(body: LeadConfigIn, request: Request):
    business_id = get_business_id(request)
    config_id   = f"lc_{uuid.uuid4().hex[:12]}"

    import json
    conditions_json = json.dumps([c.model_dump() for c in body.conditions])

    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            INSERT INTO lead_configs
                (id, business_id, name, condition_logic, conditions,
                 agent_id, provider_id, calendar_enabled, status)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            RETURNING *
        """, (
            config_id, business_id, body.name, body.condition_logic,
            conditions_json, body.agent_id, body.provider_id,
            body.calendar_enabled, body.status
        ))
        conn.commit()
        row = cur.fetchone()
        return {"success": True, "data": {"config": dict(row)}}
    except Exception as e:
        conn.rollback()
        logger.error(f"[lead_configs] create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# PATCH /api/lead-configs/:id
@router.patch("/{config_id}")
def update_config(config_id: str, body: LeadConfigUpdate, request: Request):
    business_id = get_business_id(request)

    import json
    raw = body.model_dump(exclude_none=True)
    if "conditions" in raw:
        raw["conditions"] = json.dumps(raw["conditions"]) + "::jsonb"

    if not raw:
        raise HTTPException(status_code=400, detail="No fields to update")

    sets   = []
    values = []
    for k, v in raw.items():
        if k == "conditions":
            sets.append(f"conditions = %s::jsonb")
            values.append(json.dumps(body.conditions))
        else:
            sets.append(f"{k} = %s")
            values.append(v)

    values += [config_id, business_id]
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute(
            f"UPDATE lead_configs SET {', '.join(sets)}, updated_at = NOW() WHERE id = %s AND business_id = %s RETURNING *",
            values
        )
        conn.commit()
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Config not found")
        return {"success": True, "data": {"config": dict(row)}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# DELETE /api/lead-configs/:id
@router.delete("/{config_id}")
def delete_config(config_id: str, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM lead_configs WHERE id = %s AND business_id = %s",
            (config_id, business_id)
        )
        conn.commit()
        return {"success": True}
    finally:
        cur.close(); conn.close()


# POST /api/lead-configs/match — find matching config for a lead
@router.post("/match")
def match_config(request: Request, body: dict):
    """Given lead tags/source/stage, find the first matching rule."""
    business_id = get_business_id(request)
    lead_tags   = body.get("tags", [])
    lead_source = body.get("source", "")
    lead_stage  = body.get("stage", "")

    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT lc.*, a.name AS agent_name, a.system_prompt AS agent_prompt
            FROM lead_configs lc
            LEFT JOIN ai_agents a ON a.id = lc.agent_id
            WHERE lc.business_id = %s AND lc.status = 'active'
            ORDER BY lc.created_at ASC
        """, (business_id,))
        configs = cur.fetchall()

        for cfg in configs:
            conditions = cfg["conditions"] or []
            logic      = cfg["condition_logic"] or "any"
            matches    = []
            for cond in conditions:
                field = cond.get("field")
                val   = cond.get("value", "")
                if field == "tag":
                    matches.append(val in lead_tags)
                elif field == "source":
                    matches.append(lead_source == val)
                elif field == "status":
                    matches.append(lead_stage == val)
                else:
                    matches.append(False)

            hit = any(matches) if logic == "any" else all(matches)
            if hit:
                return {"success": True, "data": {"config": dict(cfg)}}

        return {"success": True, "data": {"config": None}}
    finally:
        cur.close(); conn.close()
