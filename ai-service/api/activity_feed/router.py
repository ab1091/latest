"""
Live Activity Feed — SSE stream.

Registered directly on ai-service (not proxied to crm-service) because it's
the only ingress the frontend's Next.js proxy can reach, and streaming
responses need to pass through untouched (verified: frontend/app/api/[...proxy]/
route.ts already forwards res.body unbuffered, so this needs zero proxy changes).

Note: the browser's native EventSource API cannot send custom Authorization
headers, so — unlike every other authenticated endpoint in this app — the
JWT is passed as a query parameter here. This is a deliberate, standard
exception for SSE, not a pattern to copy elsewhere.
"""
import json
import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError

from core.config import JWT_SECRET, REDIS_URL, DEFAULT_BUSINESS_ID

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/activity-feed")

_HEARTBEAT_SECONDS = 20


async def _event_generator(business_id: str, is_super_admin: bool):
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    try:
        if is_super_admin:
            await pubsub.psubscribe("activity_feed:*")
        else:
            await pubsub.subscribe(f"activity_feed:{business_id}")

        yield "event: connected\ndata: {}\n\n"

        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=_HEARTBEAT_SECONDS),
                    timeout=_HEARTBEAT_SECONDS + 5,
                )
            except asyncio.TimeoutError:
                message = None

            if message is None:
                yield ": heartbeat\n\n"  # SSE comment line — keeps proxies/browsers from timing out the connection
                continue

            if message.get("type") in ("message", "pmessage"):
                yield f"data: {message['data']}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.close()
        await client.close()


@router.get("/stream")
async def stream_activity_feed(token: str = Query(...)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        return StreamingResponse(iter(["event: error\ndata: invalid token\n\n"]), media_type="text/event-stream")

    role = payload.get("role", "customer")
    is_super_admin = role == "super_admin"
    business_id = payload.get("businessId") or DEFAULT_BUSINESS_ID

    return StreamingResponse(
        _event_generator(business_id, is_super_admin),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
