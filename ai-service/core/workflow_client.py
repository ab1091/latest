"""
Client for crm-service's workflow engine (crm-service/core/workflow_engine.py).

ai-service fires the actual SMS/call actions (via the existing
scheduled_callbacks executor) but never mutates workflow/enrollment state
directly — it reports outcomes back to crm-service's
POST /api/workflows/enrollments/{id}/advance, mirroring the same
system-JWT HTTP pattern already used for lead-lifecycle transitions
(core/lead_transitions.py) and activity feed events (core/activity_events.py).
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


async def advance_workflow(enrollment_id: str, business_id: str, node_key: str, result: dict):
    token = _system_jwt(business_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"{CRM_SERVICE_URL}/api/workflows/enrollments/{enrollment_id}/advance",
                json={"node_key": node_key, "result": result},
                headers={"Authorization": f"Bearer {token}"},
            )
            if res.status_code != 200:
                logger.warning(f"[workflow_client] advance {enrollment_id}/{node_key} failed: {res.status_code} {res.text}")
    except Exception as e:
        logger.warning(f"[workflow_client] advance {enrollment_id}/{node_key} errored: {e}")
