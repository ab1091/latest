"""
Notes & Tasks — genuinely new features (previously "notes" was only a
free-text column on leads/appointments). Powers the unified Lead Command
Center workspace's center timeline and quick-action affordances.
"""
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from core.auth import get_business_id, get_scope
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── Notes ─────────────────────────────────────────────────────────────────────

class NoteIn(BaseModel):
    lead_id: str
    body: str


@router.get("/notes")
def list_notes(request: Request, lead_id: str):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            """
            SELECT n.*, u.first_name, u.last_name FROM notes n
            LEFT JOIN users u ON u.id = n.author_id
            WHERE n.lead_id = %s AND n.business_id = %s ORDER BY n.created_at DESC
            """,
            (lead_id, business_id),
        )
        return {"success": True, "data": {"notes": [dict(r) for r in cur.fetchall()]}}
    finally:
        cur.close(); conn.close()


@router.post("/notes", status_code=201)
def create_note(body: NoteIn, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        cur.execute(
            "INSERT INTO notes (id, lead_id, business_id, author_id, body) VALUES (%s, %s, %s, %s, %s)",
            (note_id, body.lead_id, scope["business_id"], scope["user_id"], body.body),
        )
        conn.commit()
        cur.execute("SELECT * FROM notes WHERE id = %s", (note_id,))
        return {"success": True, "data": {"note": dict(cur.fetchone())}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("DELETE FROM notes WHERE id = %s AND business_id = %s", (note_id, business_id))
        conn.commit()
        return {"success": True}
    finally:
        cur.close(); conn.close()


# ── Tasks ─────────────────────────────────────────────────────────────────────

class TaskIn(BaseModel):
    lead_id: str
    title: str
    due_at: Optional[str] = None
    assigned_to: Optional[str] = None


class TaskPatchIn(BaseModel):
    title: Optional[str] = None
    due_at: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None


@router.get("/tasks")
def list_tasks(request: Request, lead_id: Optional[str] = None):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        if lead_id:
            cur.execute(
                """
                SELECT t.*, u.first_name, u.last_name FROM tasks t
                LEFT JOIN users u ON u.id = t.assigned_to
                WHERE t.lead_id = %s AND t.business_id = %s ORDER BY t.created_at DESC
                """,
                (lead_id, business_id),
            )
        else:
            cur.execute(
                """
                SELECT t.*, u.first_name, u.last_name, l.first_name AS lead_first_name, l.last_name AS lead_last_name
                FROM tasks t
                LEFT JOIN users u ON u.id = t.assigned_to
                JOIN leads l ON l.id = t.lead_id
                WHERE t.business_id = %s AND t.status = 'open' ORDER BY t.due_at ASC NULLS LAST
                """,
                (business_id,),
            )
        return {"success": True, "data": {"tasks": [dict(r) for r in cur.fetchall()]}}
    finally:
        cur.close(); conn.close()


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, request: Request):
    scope = get_scope(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        cur.execute(
            "INSERT INTO tasks (id, lead_id, business_id, assigned_to, created_by, title, due_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (task_id, body.lead_id, scope["business_id"], body.assigned_to, scope["user_id"], body.title, body.due_at),
        )
        conn.commit()
        cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        return {"success": True, "data": {"task": dict(cur.fetchone())}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskPatchIn, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM tasks WHERE id = %s AND business_id = %s", (task_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Task not found")

        fields, params = [], []
        for field in ("title", "due_at", "assigned_to", "status"):
            value = getattr(body, field)
            if value is not None:
                fields.append(f"{field} = %s")
                params.append(value)
        if body.status == "done":
            fields.append("completed_at = NOW()")
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        params.append(task_id)
        cur.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s", params)
        conn.commit()
        cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        return {"success": True, "data": {"task": dict(cur.fetchone())}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("DELETE FROM tasks WHERE id = %s AND business_id = %s", (task_id, business_id))
        conn.commit()
        return {"success": True}
    finally:
        cur.close(); conn.close()
