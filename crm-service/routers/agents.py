"""
AI Agents router — CRUD
"""
import json
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from core.auth import get_business_id, get_scope, require_admin
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents")


class AgentIn(BaseModel):
    name:            str
    role:            str = "Lead Qualifier"
    persona:         str = ""
    system_prompt:   str = ""
    call_prompt:     str = ""
    sms_prompt:      str = ""
    ghl_tag:         str = ""
    tone:            str = "professional"
    language:        str = "English"
    status:          str = "active"
    llm_model:       str = "llama-3.1-8b-instant"
    voice_provider:  Optional[str] = None
    voice_id:        Optional[str] = None
    voice_extra:     Optional[dict] = None


class AgentUpdate(BaseModel):
    name:            Optional[str] = None
    role:            Optional[str] = None
    persona:         Optional[str] = None
    system_prompt:   Optional[str] = None
    call_prompt:     Optional[str] = None
    sms_prompt:      Optional[str] = None
    ghl_tag:         Optional[str] = None
    tone:            Optional[str] = None
    language:        Optional[str] = None
    status:          Optional[str] = None
    llm_model:       Optional[str] = None
    voice_provider:  Optional[str] = None
    voice_id:        Optional[str] = None
    voice_extra:     Optional[dict] = None


# GET /api/agents
@router.get("")
def list_agents(request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        query  = """
            SELECT id, name, role, persona, system_prompt,
                   call_prompt, sms_prompt, llm_model,
                   ghl_tag, tone, language, status, created_by, created_at,
                   voice_provider, voice_id, voice_extra
            FROM ai_agents
            WHERE business_id = %s
        """
        params = [scope["business_id"]]

        if scope["role"] in ("admin", "super_admin"):
            # Agency admin / platform super admin sees all agents
            pass
        elif scope["role"] == "staff":
            # Staff sees only their assigned agents (multi)
            cur.execute("SELECT agent_id, agent_ids FROM users WHERE id = %s", (scope["user_id"],))
            user_row = cur.fetchone()
            ids = list(user_row["agent_ids"] or []) if user_row else []
            if user_row and user_row["agent_id"] and user_row["agent_id"] not in ids:
                ids.insert(0, user_row["agent_id"])
            if ids:
                query += " AND id = ANY(%s)"
                params.append(ids)
            else:
                return {"success": True, "data": {"agents": []}}
        else:
            # Customer — only their assigned agents
            cur.execute("SELECT agent_id, agent_ids FROM users WHERE id = %s", (scope["user_id"],))
            user_row = cur.fetchone()
            ids = list(user_row["agent_ids"] or []) if user_row else []
            if user_row and user_row["agent_id"] and user_row["agent_id"] not in ids:
                ids.insert(0, user_row["agent_id"])
            if ids:
                query += " AND id = ANY(%s)"
                params.append(ids)
            else:
                return {"success": True, "data": {"agents": []}}

        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        logger.info(f"[agents:list] role={scope['role']} user={scope['user_id']} → {len(rows)} agents returned")
        return {"success": True, "data": {"agents": [dict(r) for r in rows]}}
    finally:
        cur.close(); conn.close()


# GET /api/agents/:id
@router.get("/{agent_id}")
def get_agent(agent_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT * FROM ai_agents WHERE id = %s AND business_id = %s",
            (agent_id, business_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"success": True, "data": {"agent": dict(row)}}
    finally:
        cur.close(); conn.close()


# POST /api/agents
@router.post("")
def create_agent(body: AgentIn, request: Request):
    scope = get_scope(request)
    if scope["role"] == "staff":
        raise HTTPException(status_code=403, detail="Staff cannot create agents")
    business_id = scope["business_id"]
    agent_id = f"agent_{uuid.uuid4().hex[:12]}"
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            INSERT INTO ai_agents
                (id, business_id, name, role, persona, system_prompt,
                 call_prompt, sms_prompt, llm_model,
                 ghl_tag, tone, language, status, voice_provider, voice_id, voice_extra)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
        """, (
            agent_id, business_id,
            body.name, body.role, body.persona, body.system_prompt,
            body.call_prompt or body.system_prompt,
            body.sms_prompt  or body.system_prompt,
            body.llm_model,
            body.ghl_tag, body.tone, body.language, body.status,
            body.voice_provider, body.voice_id,
            json.dumps(body.voice_extra) if body.voice_extra is not None else None
        ))
        conn.commit()
        row = cur.fetchone()
        logger.info(
            f"[agents:create] id={agent_id} name='{body.name}' role='{body.role}' "
            f"call_prompt={'set' if body.call_prompt else 'empty→fallback'} "
            f"sms_prompt={'set' if body.sms_prompt else 'empty→fallback'} "
            f"status={body.status} by={scope['user_id']}"
        )
        return {"success": True, "data": {"agent": dict(row)}}
    except Exception as e:
        conn.rollback()
        logger.error(f"[agents:create] FAILED name='{body.name}' error={e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# PATCH /api/agents/:id
@router.patch("/{agent_id}")
def update_agent(agent_id: str, body: AgentUpdate, request: Request):
    scope = get_scope(request)
    business_id = scope["business_id"]
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Staff can only update tone, language, ghl_tag, call_prompt, sms_prompt
    if scope["role"] == "staff":
        staff_allowed = {"tone", "language", "ghl_tag", "call_prompt", "sms_prompt"}
        blocked = set(fields.keys()) - staff_allowed
        if blocked:
            raise HTTPException(status_code=403, detail=f"Staff cannot update: {', '.join(blocked)}")
        fields = {k: v for k, v in fields.items() if k in staff_allowed}
        if not fields:
            raise HTTPException(status_code=400, detail="No allowed fields to update")

    sets   = ", ".join(f"{k} = %s::jsonb" if k == "voice_extra" else f"{k} = %s" for k in fields)
    values = [json.dumps(v) if k == "voice_extra" else v for k, v in fields.items()] + [agent_id, business_id]

    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute(
            f"UPDATE ai_agents SET {sets}, updated_at = NOW() WHERE id = %s AND business_id = %s RETURNING *",
            values
        )
        conn.commit()
        row = cur.fetchone()
        if not row:
            logger.warning(f"[agents:update] NOT FOUND id={agent_id} by={scope['user_id']}")
            raise HTTPException(status_code=404, detail="Agent not found")
        logger.info(f"[agents:update] id={agent_id} fields_changed={list(fields.keys())} by={scope['user_id']} role={scope['role']}")
        return {"success": True, "data": {"agent": dict(row)}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"[agents:update] FAILED id={agent_id} error={e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# DELETE /api/agents/:id — super admin only
@router.delete("/{agent_id}")
def delete_agent(agent_id: str, request: Request):
    scope = get_scope(request)
    if not scope["is_admin"]:
        raise HTTPException(status_code=403, detail="Only super admin can delete agents")
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM ai_agents WHERE id = %s AND business_id = %s",
            (agent_id, business_id)
        )
        conn.commit()
        logger.info(f"[agents:delete] id={agent_id} by={scope['user_id']}")
        return {"success": True}
    finally:
        cur.close(); conn.close()
