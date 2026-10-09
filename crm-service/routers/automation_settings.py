"""
Automation Settings — the simple on/off "Quick Setup" control surface over
the workflow engine, for businesses who don't want to touch the full
Workflow Builder graph editor. Backed by the exact same engine/templates
that already run (Insurance Lead Nurture, dynamic call-confirmation on the
ai-service side) — this just exposes a handful of plain toggles/numbers over
it instead of a node graph.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from core.auth import get_business_id, require_admin
from core.db import get_conn, dict_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/automation-settings")

DEFAULTS = {
    "sms_auto_enabled": True,
    "sms_followup_wait_hours": 23,
    "call_on_confirm_enabled": True,
    "call_on_confirm_wait_minutes": 45,
    "call_on_silence_enabled": True,
}


class SettingsUpdate(BaseModel):
    sms_auto_enabled: Optional[bool] = None
    sms_followup_wait_hours: Optional[int] = None
    call_on_confirm_enabled: Optional[bool] = None
    call_on_confirm_wait_minutes: Optional[int] = None
    call_on_silence_enabled: Optional[bool] = None


def _get_or_default(business_id: str, cur) -> dict:
    cur.execute("SELECT * FROM business_automation_settings WHERE business_id = %s", (business_id,))
    row = cur.fetchone()
    if row:
        d = dict(row)
        d.pop("updated_at", None)
        return d
    return {"business_id": business_id, **DEFAULTS}


@router.get("")
def get_settings(request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        settings = _get_or_default(business_id, cur)
        return {"success": True, "data": {"settings": settings}}
    finally:
        cur.close(); conn.close()


@router.patch("")
def update_settings(body: SettingsUpdate, request: Request):
    require_admin(request)
    business_id = get_business_id(request)
    conn = get_conn()
    cur = dict_cursor(conn)
    try:
        current = _get_or_default(business_id, cur)
        updates = body.dict(exclude_unset=True)
        merged = {**current, **updates}
        merged.pop("business_id", None)

        cur.execute("""
            INSERT INTO business_automation_settings
                (business_id, sms_auto_enabled, sms_followup_wait_hours,
                 call_on_confirm_enabled, call_on_confirm_wait_minutes, call_on_silence_enabled, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (business_id) DO UPDATE SET
                sms_auto_enabled = EXCLUDED.sms_auto_enabled,
                sms_followup_wait_hours = EXCLUDED.sms_followup_wait_hours,
                call_on_confirm_enabled = EXCLUDED.call_on_confirm_enabled,
                call_on_confirm_wait_minutes = EXCLUDED.call_on_confirm_wait_minutes,
                call_on_silence_enabled = EXCLUDED.call_on_silence_enabled,
                updated_at = NOW()
        """, (business_id, merged["sms_auto_enabled"], merged["sms_followup_wait_hours"],
              merged["call_on_confirm_enabled"], merged["call_on_confirm_wait_minutes"],
              merged["call_on_silence_enabled"]))

        # ── Side effects: keep the underlying workflow engine in sync so the
        # toggle actually does something, not just persist a flag nobody reads.

        # sms_auto_enabled — pause/activate every workflow that auto-enrolls
        # new leads for this business (Fast-Response + Insurance Nurture).
        # A paused workflow is skipped by enroll_default_workflows_for_stage's
        # `WHERE status = 'active'` filter, so this is a real switch, not
        # cosmetic — matches exactly what "Your Workflows" already lets an
        # admin do by hand in the advanced Workflow Builder.
        if "sms_auto_enabled" in updates:
            new_status = "active" if merged["sms_auto_enabled"] else "paused"
            cur.execute("""
                UPDATE workflows SET status = %s, updated_at = NOW()
                WHERE business_id = %s AND is_default_for_trigger = TRUE
                  AND trigger_type = 'stage_enter' AND trigger_stage = 'new_lead'
                  AND status IN ('active', 'paused')
            """, (new_status, business_id))
            logger.info(f"[automation-settings] business={business_id} sms_auto_enabled={merged['sms_auto_enabled']} -> {cur.rowcount} workflow(s) set to {new_status}")

        # sms_followup_wait_hours — how long to wait after Day 1 before
        # sending Day 2 (and after Day 2 before the silent-lead check-in call)
        # if the lead hasn't replied. Updates the live business copy of the
        # Insurance Lead Nurture workflow's reply_check nodes directly.
        if "sms_followup_wait_hours" in updates:
            cur.execute("""
                UPDATE workflow_nodes wn
                SET config = jsonb_set(config, '{timeout_hours}', to_jsonb(%s::int))
                FROM workflows w
                WHERE wn.workflow_id = w.id AND w.business_id = %s AND w.is_default_for_trigger = TRUE
                  AND w.template_key = 'insurance_lead_nurture'
                  AND wn.node_type = 'branch_condition' AND wn.config->>'mode' = 'reply_check'
            """, (merged["sms_followup_wait_hours"], business_id))
            logger.info(f"[automation-settings] business={business_id} sms_followup_wait_hours={merged['sms_followup_wait_hours']} -> {cur.rowcount} node(s) updated")

        conn.commit()
        settings = _get_or_default(business_id, cur)
        return {"success": True, "data": {"settings": settings}}
    finally:
        cur.close(); conn.close()
