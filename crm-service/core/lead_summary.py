"""
Combined SMS + voice-call summary generation for a single lead.

Shared by the manual "Generate Summary" button (routers/leads.py) and the
automatic regeneration that fires when a lead reaches quoted/closed
(core/workflow_engine.on_stage_change) so the quoted-stage agent has a
condensed, up-to-date picture of the deal instead of replaying raw history.

Must be called with an already-open cur (and, for the auto-trigger path, an
already-open transaction) — never opens its own connection, so it can run
safely inside on_stage_change's existing transaction without a second
connection blocking on the same locked leads row.
"""
import logging

logger = logging.getLogger(__name__)


def generate_and_save_summary(lead_id: str, cur) -> str | None:
    from core.llm_openai import OPENAI_API_KEY, openai_generate

    cur.execute(
        "SELECT first_name, last_name, stage, sub_status FROM leads WHERE id = %s",
        (lead_id,),
    )
    lead = cur.fetchone()
    if not lead:
        return None

    cur.execute("""
        SELECT c.channel, m.role, m.content, m.created_at
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        WHERE c.lead_id = %s
        ORDER BY m.created_at ASC
    """, (lead_id,))
    messages = cur.fetchall()

    cur.execute("""
        SELECT outcome, transcript, summary, duration_seconds, created_at
        FROM voice_calls WHERE lead_id = %s ORDER BY created_at ASC
    """, (lead_id,))
    calls = cur.fetchall()

    if not messages and not calls:
        return None
    if not OPENAI_API_KEY:
        return None

    parts = []
    if messages:
        parts.append("SMS/WhatsApp conversation:")
        for m in messages:
            who = "Lead" if m["role"] in ("user", "human") else "Agent"
            parts.append(f"{who}: {m['content']}")
    for c in calls:
        if c["transcript"] or c["summary"]:
            parts.append(f"\nVoice call (outcome: {c['outcome'] or 'unknown'}, {c['duration_seconds'] or 0}s):")
            parts.append(c["summary"] or c["transcript"])

    combined = "\n".join(parts)[:8000]  # keep prompt bounded for very long histories

    try:
        summary = openai_generate(
            "Summarize this lead's full history (SMS texts and voice calls combined) in 3-5 "
            "sentences. Cover: what they're interested in, key details they've shared (budget, "
            "coverage amount, etc.), where things currently stand (quoted, scheduled, objections), "
            "and any next step agreed on. Be concise and factual — no filler.\n\n"
            f"Lead: {lead['first_name']} {lead['last_name'] or ''} — "
            f"currently at stage '{lead['stage']}' / status '{lead['sub_status']}'.\n\n{combined}",
            max_tokens=300, temperature=0.3,
        )
    except Exception as e:
        logger.warning(f"[lead_summary] OpenAI summary failed for lead={lead_id}: {e}")
        return None

    cur.execute(
        "UPDATE leads SET ai_summary = %s, ai_summary_updated_at = NOW() WHERE id = %s",
        (summary, lead_id),
    )
    return summary
