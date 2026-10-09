"""
Workflow graph engine API — CRUD for multi-workflow, branching automation
(crm-service/core/workflow_engine.py is the execution engine this manages).
"""
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from psycopg2.extras import Json

from core.auth import get_business_id, require_admin
from core.db import get_conn, dict_cursor
from core.workflow_engine import advance_after_action, WorkflowEngineError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflows")

ACTIONABLE_NODE_TYPES = {"send_sms", "send_email", "ai_call"}


class NodeIn(BaseModel):
    node_key: str
    node_type: str
    config: dict = {}
    position_x: float = 0
    position_y: float = 0


class EdgeIn(BaseModel):
    from_node_key: str
    to_node_key: str
    branch_label: Optional[str] = None


class GraphBody(BaseModel):
    nodes: list[NodeIn]
    edges: list[EdgeIn]


class WorkflowCreateBody(BaseModel):
    name: str
    description: str = ""
    trigger_type: str = "stage_enter"
    trigger_stage: Optional[str] = None
    trigger_sub_status: Optional[str] = None
    trigger_config: dict = {}


class WorkflowPatchBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    is_default_for_trigger: Optional[bool] = None
    trigger_type: Optional[str] = None
    trigger_stage: Optional[str] = None
    trigger_config: Optional[dict] = None


class ReorderBody(BaseModel):
    order: list[str]  # workflow ids, in the desired display order (within one group)


def _validate_graph(nodes: list[NodeIn], edges: list[EdgeIn]):
    node_by_key = {n.node_key: n for n in nodes}
    if not node_by_key:
        raise HTTPException(status_code=400, detail="A workflow needs at least one node")

    triggers = [n for n in nodes if n.node_type == "trigger"]
    if len(triggers) != 1:
        raise HTTPException(status_code=400, detail="A workflow must have exactly one trigger node")

    for e in edges:
        if e.from_node_key not in node_by_key or e.to_node_key not in node_by_key:
            raise HTTPException(status_code=400, detail=f"Edge references an unknown node: {e.from_node_key} -> {e.to_node_key}")

    for n in nodes:
        if n.node_type == "wait":
            outgoing = [e for e in edges if e.from_node_key == n.node_key]
            if len(outgoing) != 1:
                raise HTTPException(status_code=400, detail=f"wait node '{n.node_key}' must have exactly one outgoing edge")
            target = node_by_key.get(outgoing[0].to_node_key)
            if not target or target.node_type not in ACTIONABLE_NODE_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail=f"wait node '{n.node_key}' must lead directly to send_sms/send_email/ai_call, got "
                           f"'{target.node_type if target else None}'",
                )
        elif n.node_type == "branch_condition":
            outgoing = [e for e in edges if e.from_node_key == n.node_key]
            labels = {e.branch_label for e in outgoing}
            if len(outgoing) < 2 or None in labels:
                raise HTTPException(
                    status_code=400,
                    detail=f"branch_condition node '{n.node_key}' needs >=2 labeled outgoing edges",
                )
        elif n.node_type != "end":
            outgoing = [e for e in edges if e.from_node_key == n.node_key]
            if len(outgoing) > 1:
                raise HTTPException(status_code=400, detail=f"node '{n.node_key}' ({n.node_type}) cannot branch — use branch_condition")


def _serialize_workflow(cur, workflow: dict) -> dict:
    cur.execute("SELECT node_key, node_type, config, position_x, position_y FROM workflow_nodes WHERE workflow_id = %s", (workflow["id"],))
    nodes = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT from_node_key, to_node_key, branch_label FROM workflow_edges WHERE workflow_id = %s", (workflow["id"],))
    edges = [dict(r) for r in cur.fetchall()]
    result = dict(workflow)
    result["nodes"] = nodes
    result["edges"] = edges
    return result


# GET /api/workflows — list (optionally filter by trigger_stage)
@router.get("")
def list_workflows(request: Request, trigger_stage: Optional[str] = None):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        if trigger_stage:
            cur.execute(
                "SELECT * FROM workflows WHERE business_id = %s AND trigger_stage = %s ORDER BY sort_order ASC, created_at DESC",
                (business_id, trigger_stage),
            )
        else:
            cur.execute("SELECT * FROM workflows WHERE business_id = %s ORDER BY sort_order ASC, created_at DESC", (business_id,))
        workflows = [dict(r) for r in cur.fetchall()]
        return {"success": True, "data": {"workflows": workflows}}
    finally:
        cur.close(); conn.close()


# PATCH /api/workflows/reorder — persist manual drag-and-drop card order.
# Must be declared before PATCH /{workflow_id} so "reorder" isn't swallowed
# as a workflow_id path param.
@router.patch("/reorder")
def reorder_workflows(body: ReorderBody, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        for idx, workflow_id in enumerate(body.order):
            cur.execute(
                "UPDATE workflows SET sort_order = %s WHERE id = %s AND business_id = %s",
                (idx, workflow_id, business_id),
            )
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# GET /api/workflows/templates — template library
@router.get("/templates")
def list_templates(request: Request):
    get_business_id(request)  # auth check only
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT w.id, w.template_key, w.name, w.description, w.trigger_stage,
                   (SELECT count(*) FROM workflow_nodes n WHERE n.workflow_id = w.id) AS node_count
            FROM workflows w WHERE w.is_template ORDER BY w.name
        """)
        templates = [dict(r) for r in cur.fetchall()]
        return {"success": True, "data": {"templates": templates}}
    finally:
        cur.close(); conn.close()


# GET /api/workflows/{id}
@router.get("/{workflow_id}")
def get_workflow(workflow_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM workflows WHERE id = %s AND (business_id = %s OR is_template)", (workflow_id, business_id))
        workflow = cur.fetchone()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"success": True, "data": {"workflow": _serialize_workflow(cur, dict(workflow))}}
    finally:
        cur.close(); conn.close()


# POST /api/workflows — create a new draft workflow (trigger node only)
@router.post("", status_code=201)
def create_workflow(body: WorkflowCreateBody, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO workflows (id, business_id, name, description, trigger_type, trigger_stage, trigger_sub_status, trigger_config)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (workflow_id, business_id, body.name, body.description, body.trigger_type,
             body.trigger_stage, body.trigger_sub_status, Json(body.trigger_config)),
        )
        trigger_node_id = f"wn_{uuid.uuid4().hex[:12]}"
        cur.execute(
            "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config, position_x, position_y) "
            "VALUES (%s, %s, 'trigger', 'trigger', '{}', 0, 0)",
            (trigger_node_id, workflow_id),
        )
        conn.commit()
        cur.execute("SELECT * FROM workflows WHERE id = %s", (workflow_id,))
        workflow = dict(cur.fetchone())
        return {"success": True, "data": {"workflow": _serialize_workflow(cur, workflow)}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# PATCH /api/workflows/{id} — update metadata (not the graph)
@router.patch("/{workflow_id}")
def patch_workflow(workflow_id: str, body: WorkflowPatchBody, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM workflows WHERE id = %s AND business_id = %s", (workflow_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workflow not found")

        if body.trigger_type is not None and body.trigger_type not in (
            "stage_enter", "sub_status_enter", "manual", "tag_added", "scheduled"
        ):
            raise HTTPException(status_code=400, detail=f"Invalid trigger_type: {body.trigger_type}")

        fields, params = [], []
        for field in ("name", "description", "status", "is_default_for_trigger", "trigger_type", "trigger_stage"):
            value = getattr(body, field)
            if value is not None:
                fields.append(f"{field} = %s")
                params.append(value)
        if body.trigger_config is not None:
            fields.append("trigger_config = %s")
            params.append(Json(body.trigger_config))
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        fields.append("updated_at = NOW()")
        params.append(workflow_id)
        cur.execute(f"UPDATE workflows SET {', '.join(fields)} WHERE id = %s", params)
        conn.commit()
        cur.execute("SELECT * FROM workflows WHERE id = %s", (workflow_id,))
        return {"success": True, "data": {"workflow": _serialize_workflow(cur, dict(cur.fetchone()))}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# PUT /api/workflows/{id}/graph — full replace of nodes + edges
@router.put("/{workflow_id}/graph")
def replace_graph(workflow_id: str, body: GraphBody, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    _validate_graph(body.nodes, body.edges)

    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM workflows WHERE id = %s AND business_id = %s", (workflow_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workflow not found")

        cur.execute("DELETE FROM workflow_edges WHERE workflow_id = %s", (workflow_id,))
        cur.execute("DELETE FROM workflow_nodes WHERE workflow_id = %s", (workflow_id,))

        for n in body.nodes:
            node_id = f"wn_{uuid.uuid4().hex[:12]}"
            cur.execute(
                "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config, position_x, position_y) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (node_id, workflow_id, n.node_key, n.node_type, Json(n.config), n.position_x, n.position_y),
            )
        for e in body.edges:
            edge_id = f"we_{uuid.uuid4().hex[:12]}"
            cur.execute(
                "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key, branch_label) "
                "VALUES (%s, %s, %s, %s, %s)",
                (edge_id, workflow_id, e.from_node_key, e.to_node_key, e.branch_label),
            )

        cur.execute("UPDATE workflows SET version = version + 1, updated_at = NOW() WHERE id = %s", (workflow_id,))
        conn.commit()
        cur.execute("SELECT * FROM workflows WHERE id = %s", (workflow_id,))
        return {"success": True, "data": {"workflow": _serialize_workflow(cur, dict(cur.fetchone()))}}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# DELETE /api/workflows/{id}
@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: str, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("DELETE FROM workflows WHERE id = %s AND business_id = %s", (workflow_id, business_id))
        conn.commit()
        return {"success": True}
    finally:
        cur.close(); conn.close()


# POST /api/workflows/{template_id}/duplicate
@router.post("/{template_id}/duplicate", status_code=201)
def duplicate_workflow(template_id: str, body: dict, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM workflows WHERE id = %s AND (is_template OR business_id = %s)", (template_id, business_id))
        source = cur.fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="Source workflow not found")
        source = dict(source)

        new_id = f"wf_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO workflows (id, business_id, name, description, trigger_type, trigger_stage,
                                    trigger_sub_status, trigger_config, status, template_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s)
            """,
            (new_id, business_id, body.get("name") or f"{source['name']} (copy)", source["description"],
             source["trigger_type"], source["trigger_stage"], source["trigger_sub_status"],
             Json(source["trigger_config"]), source["template_key"]),
        )
        cur.execute("SELECT node_key, node_type, config, position_x, position_y FROM workflow_nodes WHERE workflow_id = %s", (template_id,))
        for n in cur.fetchall():
            node_id = f"wn_{uuid.uuid4().hex[:12]}"
            cur.execute(
                "INSERT INTO workflow_nodes (id, workflow_id, node_key, node_type, config, position_x, position_y) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (node_id, new_id, n["node_key"], n["node_type"], Json(n["config"]), n["position_x"], n["position_y"]),
            )
        cur.execute("SELECT from_node_key, to_node_key, branch_label FROM workflow_edges WHERE workflow_id = %s", (template_id,))
        for e in cur.fetchall():
            edge_id = f"we_{uuid.uuid4().hex[:12]}"
            cur.execute(
                "INSERT INTO workflow_edges (id, workflow_id, from_node_key, to_node_key, branch_label) VALUES (%s, %s, %s, %s, %s)",
                (edge_id, new_id, e["from_node_key"], e["to_node_key"], e["branch_label"]),
            )
        conn.commit()
        cur.execute("SELECT * FROM workflows WHERE id = %s", (new_id,))
        return {"success": True, "data": {"workflow": _serialize_workflow(cur, dict(cur.fetchone()))}}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# GET /api/workflows/{id}/enrollments
@router.get("/{workflow_id}/enrollments")
def get_enrollments(workflow_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM workflows WHERE id = %s AND business_id = %s", (workflow_id, business_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workflow not found")
        cur.execute(
            """
            SELECT e.*, l.first_name, l.last_name, l.phone
            FROM lead_workflow_enrollments e JOIN leads l ON l.id = e.lead_id
            WHERE e.workflow_id = %s ORDER BY e.enrolled_at DESC LIMIT 200
            """,
            (workflow_id,),
        )
        enrollments = [dict(r) for r in cur.fetchall()]
        return {"success": True, "data": {"enrollments": enrollments}}
    finally:
        cur.close(); conn.close()


# POST /api/workflows/enrollments/{id}/advance — internal, server-to-server (ai-service)
@router.post("/enrollments/{enrollment_id}/advance")
def advance_enrollment(enrollment_id: str, body: dict, request: Request):
    require_admin(request)  # ai-service authenticates with a system JWT, role=admin
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        advance_after_action(enrollment_id, body["node_key"], body.get("result", {}), conn, cur)
        conn.commit()
        return {"success": True}
    except WorkflowEngineError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        conn.rollback()
        logger.error(f"[workflows] advance_enrollment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
