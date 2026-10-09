"""
Live Activity Feed — durable event log + Redis pub/sub fan-out.

emit() is the single entrypoint every producer (lifecycle transitions,
SMS/call events, workflow node runs, appointment booking, etc.) calls to
record a platform activity event. It writes one durable row to
activity_feed_events (backs paginated history / initial page load) and
publishes the same event to Redis channel activity_feed:{business_id}
in the same call (backs the live SSE stream in ai-service).

Redis is used only as a fan-out bus, not as the source of truth — if a
publish fails (Redis down), the durable row still lands and the feed
just doesn't push live for that event.
"""
import json
import uuid
import logging

import redis
from psycopg2.extras import Json

from core.config import REDIS_URL
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)

_redis_client: redis.Redis = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def emit(
    business_id: str,
    event_type: str,
    title: str,
    lead_id: str = None,
    metadata: dict = None,
    conn=None,
    cur=None,
) -> dict:
    """
    Record + broadcast one activity feed event. Caller may pass an existing
    open conn/cur to write within their own transaction (recommended when
    emitting alongside a lifecycle/workflow write so the two can't drift);
    otherwise a new connection is opened and committed immediately.
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
        cur = dict_cursor(conn)

    event_id = f"afe_{uuid.uuid4().hex[:12]}"
    payload = metadata or {}

    try:
        cur.execute(
            """
            INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING created_at
            """,
            (event_id, business_id, lead_id, event_type, title, Json(payload)),
        )
        created_at = cur.fetchone()["created_at"]

        if owns_conn:
            conn.commit()
    except Exception:
        if owns_conn:
            conn.rollback()
        raise
    finally:
        if owns_conn:
            cur.close()
            conn.close()

    event = {
        "id": event_id,
        "business_id": business_id,
        "lead_id": lead_id,
        "event_type": event_type,
        "title": title,
        "metadata": payload,
        "created_at": created_at.isoformat(),
    }

    try:
        _get_redis().publish(f"activity_feed:{business_id}", json.dumps(event, default=str))
    except Exception as e:
        logger.warning(f"[activity_feed] Redis publish failed (event still durably recorded): {e}")

    return event
