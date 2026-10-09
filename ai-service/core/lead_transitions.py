"""
Client for crm-service's lead state machine (crm-service/core/lead_lifecycle.py).

ai-service never writes leads.sub_status/stage directly — it calls crm-service's
POST /api/leads/{id}/transition endpoint, authenticated with a short-lived
system JWT signed with the same shared JWT_SECRET both services read from .env.
"""
import logging
import httpx
from jose import jwt as _jwt

from core.config import JWT_SECRET, CRM_SERVICE_URL, DEFAULT_BUSINESS_ID

logger = logging.getLogger(__name__)


def _system_jwt(business_id: str) -> str:
    return _jwt.encode(
        {"userId": "system:ai-service", "businessId": business_id, "role": "admin"},
        JWT_SECRET, algorithm="HS256",
    )


async def transition_via_crm_api(lead_id: str, business_id: str, event: str, metadata: dict = None):
    """
    Best-effort — a stage transition is a side effect of handling an inbound
    message, not a precondition for it. Confirmed live: this used to have no
    try/except and only a 5s timeout, so a slow crm-service response on this
    ONE call (observed repeatedly on a lead's very first "inbound_reply"
    transition, which does more work than a same-stage no-op later) raised
    an uncaught httpx.ReadTimeout that propagated all the way up and aborted
    the entire message-handling pipeline — the customer's actual AI reply
    never got generated at all, and they got the generic "technical hiccup"
    fallback instead. A slow/failed transition should never cost the
    customer a real answer.
    """
    token = _system_jwt(business_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{CRM_SERVICE_URL}/api/leads/{lead_id}/transition",
                json={"event": event, "metadata": metadata or {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            if res.status_code not in (200, 409):  # 409 = not a valid transition, expected/benign
                logger.warning(f"[lead_transitions] {event} for lead {lead_id} failed: {res.status_code} {res.text}")
    except Exception as e:
        logger.warning(f"[lead_transitions] {event} for lead {lead_id} errored: {e}")


async def create_lead_from_inbound(phone: str, channel: str) -> dict | None:
    """
    Auto-creates a lead for an inbound message from a number with no existing
    match — previously _handle_inbound_message just logged and dropped these,
    silently losing any cold inbound text. status='responded' (not the
    default 'new') skips crm-service's "new_lead" nurture-workflow
    enrollment — sending that generic intro text would double-message
    someone who just texted us first, on top of the direct contextual AI
    reply _handle_inbound_message sends right after this returns.
    """
    token = _system_jwt(DEFAULT_BUSINESS_ID)
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            f"{CRM_SERVICE_URL}/api/leads",
            json={
                "first_name": "", "phone": phone, "tags": ["inbound"],
                "status": "responded", "source": "inbound",
                "preferred_channel": "whatsapp" if channel == "whatsapp" else "sms",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code != 200:
            logger.warning(f"[lead_transitions] auto-create lead for inbound {phone} failed: {res.status_code} {res.text}")
            return None
        return res.json()["data"]["lead"]


async def trigger_summary_generation(lead_id: str, business_id: str):
    """
    Regenerates leads.ai_summary via crm-service's existing generate-summary
    endpoint (same one the "Generate Summary" button and the quoted/closed
    auto-trigger use) — reused here so a long-running pre-quoted conversation
    can also fall back to a condensed summary instead of resending its entire
    raw message history on every single reply.
    """
    token = _system_jwt(business_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{CRM_SERVICE_URL}/api/leads/{lead_id}/generate-summary",
                headers={"Authorization": f"Bearer {token}"},
            )
            if res.status_code != 200:
                logger.warning(f"[lead_transitions] summary generation for lead {lead_id} failed: {res.status_code} {res.text}")
    except Exception as e:
        logger.warning(f"[lead_transitions] summary generation for lead {lead_id} errored: {e}")
