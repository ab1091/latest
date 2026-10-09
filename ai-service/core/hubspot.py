import logging
import httpx
from datetime import datetime

from core.config import HUBSPOT_ACCESS_TOKEN

logger = logging.getLogger(__name__)

HS_BASE = "https://api.hubapi.com"


def hs_headers() -> dict:
    return {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }


async def sync_contact_and_meeting(appt_id: str, from_phone: str,
                                   parsed: dict, start_time: datetime, end_time: datetime):
    if not HUBSPOT_ACCESS_TOKEN:
        return
    try:
        has_real_email = bool(
            parsed.get("email") and "@inbound.call" not in (parsed.get("email") or "")
        )
        contact_props = {
            "firstname": (parsed.get("name") or "Inbound").split()[0],
            "lastname":  " ".join((parsed.get("name") or "Inbound Caller").split()[1:]) or "Caller",
            "phone":     from_phone,
        }
        if has_real_email:
            contact_props["email"] = parsed["email"]

        headers = hs_headers()

        async with httpx.AsyncClient(timeout=10) as client:
            search_res = await client.post(
                f"{HS_BASE}/crm/v3/objects/contacts/search",
                headers=headers,
                json={"filterGroups": [{"filters": [{"propertyName": "phone", "operator": "EQ", "value": from_phone}]}]},
            )
            results = search_res.json().get("results", [])

            if results:
                # Contact already exists — do not overwrite any fields
                contact_id = results[0]["id"]
            else:
                c_res = await client.post(
                    f"{HS_BASE}/crm/v3/objects/contacts",
                    headers=headers,
                    json={"properties": contact_props},
                )
                contact_id = c_res.json().get("id")

        logger.info(f"[hubspot] Contact synced: {contact_id}")

        start_ms = int(start_time.timestamp() * 1000)
        end_ms   = int(end_time.timestamp() * 1000)

        async with httpx.AsyncClient(timeout=10) as client:
            m_res = await client.post(
                f"{HS_BASE}/crm/v3/objects/meetings",
                headers=headers,
                json={"properties": {
                    "hs_meeting_title":      f"Appointment: {appt_id}",
                    "hs_timestamp":          start_ms,
                    "hs_meeting_start_time": start_ms,
                    "hs_meeting_end_time":   end_ms,
                    "hs_meeting_body":       f"Inbound call — {parsed.get('service')} on {parsed.get('date')} at {parsed.get('time')}",
                    "hs_meeting_outcome":    "SCHEDULED",
                }},
            )
            if not m_res.is_success:
                logger.error(f"[hubspot] Meeting create failed: {m_res.status_code} {m_res.text}")
                return
            meeting_id = m_res.json().get("id")

        if meeting_id and contact_id:
            async with httpx.AsyncClient(timeout=10) as client:
                assoc = await client.put(
                    f"{HS_BASE}/crm/v4/objects/meetings/{meeting_id}/associations/contacts/{contact_id}",
                    headers=headers,
                    json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 200}],
                )
                if not assoc.is_success:
                    logger.error(f"[hubspot] Association failed: {assoc.status_code} {assoc.text}")
            logger.info(f"[hubspot] Meeting {meeting_id} linked to contact {contact_id}")

    except Exception as e:
        logger.error(f"[hubspot] Sync error: {e}")
