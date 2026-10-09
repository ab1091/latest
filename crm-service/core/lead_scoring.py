"""
AI Lead Scoring — computed on-write (not batch), so the score visibly
moves the moment an SMS reply, call outcome, or appointment event lands.

Called from transition_lead_status() as a catch-all (guarantees a
recompute on every lifecycle event even if an individual call site
forgets), plus explicitly after events that don't always change stage
(e.g. a call outcome that doesn't move the lead but still shifts sentiment).
"""
import uuid
import logging

from psycopg2.extras import Json

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "sms_engagement": 25, "call_engagement": 25, "appointment_activity": 20,
    "quote_requests": 15, "ai_sentiment": 15,
}


def _get_weights(business_id: str, cur) -> dict:
    cur.execute("SELECT factor_key, weight, enabled FROM lead_scoring_rules WHERE business_id = %s", (business_id,))
    rows = {r["factor_key"]: r for r in cur.fetchall()}
    weights = {}
    for factor, default_weight in DEFAULT_WEIGHTS.items():
        row = rows.get(factor)
        if row is None:
            weights[factor] = default_weight
        elif not row["enabled"]:
            weights[factor] = 0
        else:
            weights[factor] = row["weight"]
    return weights


def _band_for(score: int) -> str:
    if score >= 95:
        return "hot"
    if score >= 70:
        return "warm"
    if score >= 30:
        return "cold"
    return "new"


def recompute_score(lead_id: str, cur) -> dict:
    cur.execute("SELECT business_id, sub_status FROM leads WHERE id = %s", (lead_id,))
    lead = cur.fetchone()
    if not lead:
        return {}
    business_id = lead["business_id"]
    weights = _get_weights(business_id, cur)
    factors = {}

    # SMS engagement — inbound replies across this lead's sms/whatsapp conversations
    cur.execute(
        """
        SELECT count(*) AS n FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.lead_id = %s AND c.channel IN ('sms', 'whatsapp') AND m.role = 'user'
        """,
        (lead_id,),
    )
    reply_count = cur.fetchone()["n"]
    sms_raw = min(25, reply_count * 5)
    factors["sms_engagement"] = {"raw": sms_raw, "replies": reply_count}

    # Call engagement — total answered duration + a bonus if the latest outcome confirmed
    cur.execute(
        "SELECT outcome, duration_seconds FROM voice_calls WHERE lead_id = %s ORDER BY created_at DESC",
        (lead_id,),
    )
    calls = cur.fetchall()
    answered_seconds = sum((c["duration_seconds"] or 0) for c in calls if c["outcome"] not in ("no_answer", "voicemail", None))
    call_raw = min(25, answered_seconds / 12)
    if calls and calls[0]["outcome"] == "confirmed":
        call_raw = min(25, call_raw + 10)
    factors["call_engagement"] = {"raw": round(call_raw, 1), "answered_seconds": answered_seconds}

    # Appointment activity
    cur.execute(
        "SELECT status FROM appointments WHERE lead_id = %s ORDER BY created_at DESC",
        (lead_id,),
    )
    appts = [r["status"] for r in cur.fetchall()]
    if any(s == "completed" for s in appts):
        appt_raw = 20
    elif any(s in ("confirmed", "pending") for s in appts):
        appt_raw = 10
    else:
        appt_raw = 0
    factors["appointment_activity"] = {"raw": appt_raw}

    # Quote requests — has this lead ever reached 'quoted' or beyond?
    cur.execute(
        "SELECT 1 FROM lead_status_history WHERE lead_id = %s AND to_sub_status IN ('quoted', 'appointment_scheduled', 'converted') LIMIT 1",
        (lead_id,),
    )
    ever_quoted = cur.fetchone() is not None or lead["sub_status"] in ("quoted", "appointment_scheduled", "converted")
    quote_raw = 15 if ever_quoted else 0
    factors["quote_requests"] = {"raw": quote_raw}

    # AI sentiment — latest classified call
    cur.execute("SELECT sentiment FROM voice_calls WHERE lead_id = %s AND sentiment IS NOT NULL ORDER BY created_at DESC LIMIT 1", (lead_id,))
    sentiment_row = cur.fetchone()
    sentiment = sentiment_row["sentiment"] if sentiment_row else None
    sentiment_raw = {"positive": 15, "neutral": 7}.get(sentiment, 0)
    factors["ai_sentiment"] = {"raw": sentiment_raw, "sentiment": sentiment}

    total = 0.0
    for factor, default_weight in DEFAULT_WEIGHTS.items():
        raw = factors[factor]["raw"]
        weight = weights[factor]
        total += raw * (weight / default_weight) if default_weight else 0
    score = max(0, min(100, round(total)))
    band = _band_for(score)

    cur.execute("UPDATE leads SET score = %s, score_band = %s WHERE id = %s", (score, band, lead_id))
    cur.execute(
        "INSERT INTO lead_score_history (id, lead_id, score, band, factors) VALUES (%s, %s, %s, %s, %s)",
        (f"lsh_score_{uuid.uuid4().hex[:12]}", lead_id, score, band, Json(factors)),
    )
    logger.info(f"[lead_scoring] lead={lead_id} score={score} band={band}")
    return {"score": score, "band": band, "factors": factors}
