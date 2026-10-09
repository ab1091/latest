"""
Lead assignment engine — Round Robin / Team Based / Territory Based / Manual.

Called from lead creation (crm-service/routers/leads.py) right after a new
lead is inserted. No-ops (leaves leads.assigned_user_id NULL) if the
business has no assignment_rules row or mode='manual' — staff assign leads
by hand in that case.
"""
import logging

logger = logging.getLogger(__name__)


def _match_conditions(lead: dict, conditions: list, logic: str) -> bool:
    """Same {field, operator, value} shape already proven in lead_configs.py's match_config."""
    results = []
    for cond in conditions:
        field = cond.get("field")
        op = cond.get("operator", "equals")
        val = cond.get("value", "")
        if field == "tag":
            lead_tags = lead.get("tags") or []
            results.append(val in lead_tags if op == "equals" else any(val in t for t in lead_tags))
        elif field == "source":
            results.append(lead.get("source") == val)
        elif field == "preferred_channel":
            results.append(lead.get("preferred_channel") == val)
        else:
            results.append(False)
    if not results:
        return False
    return any(results) if logic == "any" else all(results)


def _assign_round_robin(business_id: str, config: dict, cur) -> str | None:
    user_ids = config.get("user_ids") or []
    if not user_ids:
        return None
    cur.execute("SELECT last_assigned_user_id FROM assignment_rr_state WHERE business_id = %s FOR UPDATE", (business_id,))
    row = cur.fetchone()
    last_id = row["last_assigned_user_id"] if row else None

    next_id = user_ids[0]
    if last_id in user_ids:
        idx = user_ids.index(last_id)
        next_id = user_ids[(idx + 1) % len(user_ids)]

    cur.execute(
        """
        INSERT INTO assignment_rr_state (business_id, last_assigned_user_id, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (business_id) DO UPDATE SET last_assigned_user_id = EXCLUDED.last_assigned_user_id, updated_at = NOW()
        """,
        (business_id, next_id),
    )
    return next_id


def _assign_team_based(business_id: str, config: dict, cur) -> str | None:
    """Load-balanced: assign to whichever team member currently has the fewest open leads."""
    user_ids = config.get("user_ids") or []
    if not user_ids:
        return None
    cur.execute(
        """
        SELECT assigned_user_id, count(*) AS n FROM leads
        WHERE business_id = %s AND assigned_user_id = ANY(%s) AND stage NOT IN ('closed', 'dead')
        GROUP BY assigned_user_id
        """,
        (business_id, user_ids),
    )
    load = {row["assigned_user_id"]: row["n"] for row in cur.fetchall()}
    return min(user_ids, key=lambda uid: load.get(uid, 0))


def _assign_territory_based(lead: dict, config: dict, cur) -> str | None:
    for rule in config.get("rules", []):
        if _match_conditions(lead, rule.get("conditions", []), rule.get("condition_logic", "any")):
            return rule.get("user_id")
    return config.get("default_user_id")


def assign_lead(lead: dict, business_id: str, cur) -> str | None:
    """
    lead must contain at least: tags, source, preferred_channel (used by
    territory matching). Returns the assigned user_id, or None (manual/no rule).
    """
    cur.execute("SELECT mode, config FROM assignment_rules WHERE business_id = %s", (business_id,))
    rule = cur.fetchone()
    if not rule or rule["mode"] == "manual":
        return None

    mode = rule["mode"]
    config = rule["config"] or {}
    try:
        if mode == "round_robin":
            return _assign_round_robin(business_id, config, cur)
        if mode == "team_based":
            return _assign_team_based(business_id, config, cur)
        if mode == "territory_based":
            return _assign_territory_based(lead, config, cur)
    except Exception as e:
        logger.error(f"[lead_assignment] mode={mode} failed for business={business_id}: {e}")
    return None
