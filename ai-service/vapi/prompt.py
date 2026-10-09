"""
Vapi assistant prompt fallback builder.

_build_prompt() is the last-resort identity vapi/router.py:_get_assistant_for_caller()
falls back to when a call has no phone-matched lead and no matching Lead
Config. This used to return a hardcoded leftover from this CRM's earlier
life as a medical-office scheduling bot — "James, a receptionist at AllZone
Medical Centre" (voice/medical_prompt.py) — which meant any caller who
didn't match an existing lead got greeted as the wrong business entirely.
Confirmed live: a real test call hit exactly this path and heard "James
with AllZone Medical Centre." Fixed to pull the business's real agent
(name, prompt, voice) from ai_agents instead, so an unmatched caller still
reaches the actual Shield Insurance Agency identity.
"""

import logging

from core.db import get_conn, get_dict_cursor, DEFAULT_BUSINESS_ID

logger = logging.getLogger(__name__)

_FALLBACK_NAME   = "Riley"
_FALLBACK_PROMPT = (
    "You are Riley, Shield Insurance Agency's assistant. Help the caller with "
    "auto insurance — understand what they need, and let them know a licensed "
    "agent will follow up. Keep responses brief and natural. You do not sell, "
    "quote, or advise."
)


def _build_prompt() -> tuple[str, str, dict | None]:
    """Returns (prompt, agent_name, voice). voice is {"provider","voiceId"}
    or None. Falls back to a minimal but correctly-branded Shield Insurance
    identity if the DB is unreachable or no active agent exists yet."""
    try:
        conn = get_conn()
        cur  = get_dict_cursor(conn)
        cur.execute("""
            SELECT name, call_prompt, system_prompt, voice_provider, voice_id
            FROM ai_agents
            WHERE business_id = %s AND status = 'active'
            ORDER BY created_at ASC LIMIT 1
        """, (DEFAULT_BUSINESS_ID,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if row:
            prompt = row["call_prompt"] or row["system_prompt"]
            if prompt:
                voice = (
                    {"provider": row["voice_provider"], "voiceId": row["voice_id"]}
                    if row["voice_provider"] and row["voice_id"] else None
                )
                return prompt, row["name"], voice
    except Exception as e:
        logger.warning(f"[vapi:prompt] DB fetch failed, using fallback: {e}")

    return _FALLBACK_PROMPT, _FALLBACK_NAME, None
