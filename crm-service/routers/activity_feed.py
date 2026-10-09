"""
Live Activity Feed — durable history + internal emit endpoint.

The durable write path (activity_feed_events table) and Redis publish
both live in core/activity_feed.py:emit(). This router exposes:
  - GET  /api/activity-feed        paginated history (backs initial page load
                                    before the SSE stream, which lives directly
                                    in ai-service, takes over)
  - POST /api/activity-feed/emit   internal, server-to-server — lets ai-service
                                    record+broadcast events without importing
                                    crm-service's Python modules directly,
                                    mirroring the existing lead-transition
                                    HTTP pattern (core/lead_transitions.py)
"""
import logging
from typing import Optional
from fastapi import APIRouter, Request, Query

from core.auth import get_business_id, require_admin
from core.db import get_conn, dict_cursor
from core.activity_feed import emit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/activity-feed")


@router.get("")
def get_activity_feed(request: Request, limit: int = Query(50, le=200), before: Optional[str] = None):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        if before:
            cur.execute(
                """
                SELECT * FROM activity_feed_events
                WHERE business_id = %s AND created_at < %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (business_id, before, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM activity_feed_events
                WHERE business_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (business_id, limit),
            )
        events = [dict(r) for r in cur.fetchall()]
        return {"success": True, "data": {"events": events}}
    finally:
        cur.close(); conn.close()


@router.post("/emit")
def emit_activity_event(body: dict, request: Request):
    require_admin(request)  # ai-service authenticates as a system JWT with role=admin
    business_id = get_business_id(request)
    event = emit(
        business_id=business_id,
        event_type=body["event_type"],
        title=body["title"],
        lead_id=body.get("lead_id"),
        metadata=body.get("metadata"),
    )
    return {"success": True, "data": {"event": event}}
