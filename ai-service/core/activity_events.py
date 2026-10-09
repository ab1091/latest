"""
Client for crm-service's activity feed (crm-service/core/activity_feed.py).

ai-service never writes activity_feed_events directly — it calls crm-service's
POST /api/activity-feed/emit endpoint, authenticated with the same short-lived
system JWT pattern already used for lead-lifecycle transitions
(core/lead_transitions.py).
"""
import logging
import httpx
from jose import jwt as _jwt

from core.config import JWT_SECRET, CRM_SERVICE_URL

logger = logging.getLogger(__name__)


def _system_jwt(business_id: str) -> str:
    return _jwt.encode(
        {"userId": "system:ai-service", "businessId": business_id, "role": "admin"},
        JWT_SECRET, algorithm="HS256",
    )


async def emit_activity_event(business_id: str, event_type: str, title: str,
                               lead_id: str = None, metadata: dict = None):
    token = _system_jwt(business_id)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.post(
                f"{CRM_SERVICE_URL}/api/activity-feed/emit",
                json={"event_type": event_type, "title": title, "lead_id": lead_id, "metadata": metadata or {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            if res.status_code != 200:
                logger.warning(f"[activity_events] emit {event_type} failed: {res.status_code} {res.text}")
    except Exception as e:
        logger.warning(f"[activity_events] emit {event_type} errored: {e}")
