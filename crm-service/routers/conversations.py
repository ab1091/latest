"""
Conversations router — chat/SMS thread per lead
"""
import uuid
import logging
import re
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from core.auth import get_business_id, get_scope
from core.db import get_conn, dict_cursor
from core.lead_lifecycle import transition_lead_status, InvalidTransition
from core.sms_client import send_sms

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations")


def sanitize_text(text: str) -> str:
    if not text:
        return text
    cleaned = re.sub(r"\s*—\s*", ", ", text)
    cleaned = cleaned.replace("—", "-").replace("–", "-")
    cleaned = re.sub(r"--+", "-", cleaned)
    cleaned = re.sub(r",\s*,+", ",", cleaned)
    cleaned = re.sub(r",\s*\.", ".", cleaned)
    return cleaned.strip()


class MessageIn(BaseModel):
    content:  str
    role:     str = "user"   # "user" | "agent" | "human"


class CallUpdateIn(BaseModel):
    call_id:          str
    outcome:          Optional[str] = None
    transcript:       Optional[str] = None
    summary:          Optional[str] = None
    duration_seconds: Optional[int] = None
    appointment_id:   Optional[str] = None
    patient_name:     Optional[str] = None
    patient_phone:    Optional[str] = None
    already_progressed: bool = False


# GET /api/conversations?lead_id=...
@router.get("")
def list_conversations(request: Request, lead_id: Optional[str] = None):
    scope = get_scope(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        base = """
            SELECT c.id, c.lead_id, c.agent_id, c.channel,
                   c.ai_active, c.created_at, c.created_by,
                   l.first_name, l.last_name, l.phone, l.tags,
                   a.name AS agent_name,
                   (SELECT content FROM messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.created_at DESC LIMIT 1) AS last_message,
                   (SELECT created_at FROM messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.created_at DESC LIMIT 1) AS last_message_at,
                   EXISTS (SELECT 1 FROM messages m
                           WHERE m.conversation_id = c.id AND m.role = 'user') AS has_reply
            FROM conversations c
            JOIN leads l ON l.id = c.lead_id
            LEFT JOIN ai_agents a ON a.id = c.agent_id
            WHERE c.business_id = %s
        """
        params = [scope["business_id"]]

        # Admin sees all conversations, staff/agent sees only their own
        if not scope["is_admin"]:
            base += " AND l.created_by = %s"
            params.append(scope["user_id"])
        if lead_id:
            base += " AND c.lead_id = %s"
            params.append(lead_id)

        # No LIMIT — the dashboard uses this endpoint's full result to compute
        # aggregate stats (total conversations, replied-to-text). A LIMIT 100
        # here silently undercounted once real volume passed 100 (confirmed:
        # 101 real conversations, this returned exactly 100).
        base += " ORDER BY c.created_at DESC"
        cur.execute(base, params)
        rows = cur.fetchall()
        return {"success": True, "data": {"conversations": [dict(r) for r in rows]}}
    finally:
        cur.close(); conn.close()


# GET /api/conversations/:id/messages
@router.get("/{conv_id}/messages")
def get_messages(conv_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT id FROM conversations WHERE id = %s AND business_id = %s",
            (conv_id, business_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

        cur.execute("""
            SELECT id, role, content, status, error_reason, channel, retry_count, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC
        """, (conv_id,))
        rows = cur.fetchall()
        return {"success": True, "data": {"messages": [dict(r) for r in rows]}}
    finally:
        cur.close(); conn.close()


# POST /api/conversations  - start or get conversation for a lead
@router.post("")
def create_conversation(request: Request, body: dict):
    scope       = get_scope(request)
    business_id = scope["business_id"]
    user_id     = scope["user_id"]
    lead_id     = body.get("lead_id")
    agent_id    = body.get("agent_id")
    channel     = body.get("channel", "chat")

    if not lead_id:
        raise HTTPException(status_code=400, detail="lead_id required")

    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        # Reuse any existing non-voice conversation for this lead (whatsapp preferred)
        cur.execute(
            "SELECT * FROM conversations WHERE lead_id = %s AND business_id = %s AND channel != 'voice' ORDER BY CASE channel WHEN 'whatsapp' THEN 0 WHEN 'sms' THEN 1 ELSE 2 END LIMIT 1",
            (lead_id, business_id)
        )
        existing = cur.fetchone()
        if existing:
            return {"success": True, "data": {"conversation": dict(existing)}}

        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        cur.execute("""
            INSERT INTO conversations (id, business_id, lead_id, agent_id, channel, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (conv_id, business_id, lead_id, agent_id, channel, user_id))
        conn.commit()
        row = cur.fetchone()
        return {"success": True, "data": {"conversation": dict(row)}}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# POST /api/conversations/:id/messages
@router.post("/{conv_id}/messages")
async def send_message(conv_id: str, body: MessageIn, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT c.id, c.ai_active, c.agent_id, c.channel, c.lead_id,
                   l.phone, l.preferred_channel
            FROM conversations c
            LEFT JOIN leads l ON l.id = c.lead_id
            WHERE c.id = %s AND c.business_id = %s
        """, (conv_id, business_id))
        conv = cur.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        initial_status = "delivered" if body.role in ("user", "lead") else "pending"
        msg_channel = conv.get("channel") or "imessage"
        clean_content = sanitize_text(body.content)

        cur.execute("""
            INSERT INTO messages (id, conversation_id, role, content, status, channel)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (msg_id, conv_id, body.role, clean_content, initial_status, msg_channel))
        conn.commit()
        row = dict(cur.fetchone())

        raw_channel = conv.get("channel") or "imessage"
        channel = raw_channel if raw_channel in ("imessage", "sms") else "imessage"
        phone   = conv.get("phone")
        send_err = None

        if phone and channel in ("imessage", "sms") and body.role in ("human", "agent"):
            try:
                await send_sms(phone, clean_content, channel)
                cur.execute("UPDATE messages SET status = 'delivered', updated_at = NOW() WHERE id = %s", (msg_id,))
                conn.commit()
                row["status"] = "delivered"
            except Exception as e:
                send_err = str(e)
                logger.warning(f"[conversations] send failed: {send_err}")
                cur.execute("UPDATE messages SET status = 'failed', error_reason = %s, updated_at = NOW() WHERE id = %s", (send_err, msg_id))
                conn.commit()
                row["status"] = "failed"
                row["error_reason"] = send_err

        return {"success": True, "data": {"message": row, "send_error": send_err}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# POST /api/conversations/:conv_id/messages/:msg_id/retry
class RetryMessageIn(BaseModel):
    channel: Optional[str] = None

@router.post("/{conv_id}/messages/{msg_id}/retry")
async def retry_message(conv_id: str, msg_id: str, request: Request, body: Optional[RetryMessageIn] = None):
    """Retries sending a previously failed message with optional channel override."""
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT c.id, c.channel, l.phone, l.id AS lead_id
            FROM conversations c
            JOIN leads l ON l.id = c.lead_id
            WHERE c.id = %s AND c.business_id = %s
        """, (conv_id, business_id))
        conv = cur.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        cur.execute(
            "SELECT id, content, role, status FROM messages WHERE id = %s AND conversation_id = %s",
            (msg_id, conv_id)
        )
        msg = cur.fetchone()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        phone = conv.get("phone")
        if not phone:
            raise HTTPException(status_code=400, detail="Lead has no phone number")

        target_channel = (body.channel if body and body.channel else None) or conv.get("channel") or "imessage"

        # Update status to pending
        cur.execute(
            "UPDATE messages SET status = 'pending', retry_count = retry_count + 1, updated_at = NOW() WHERE id = %s",
            (msg_id,)
        )
        conn.commit()

        try:
            res = await send_sms(phone, msg["content"], target_channel, force=True)
            cur.execute(
                "UPDATE messages SET status = 'delivered', error_reason = NULL, channel = %s, updated_at = NOW() WHERE id = %s RETURNING *",
                (target_channel, msg_id)
            )
            conn.commit()
            updated = cur.fetchone()
            return {"success": True, "data": {"message": dict(updated), "send_result": res}}
        except Exception as e:
            err = str(e)
            cur.execute(
                "UPDATE messages SET status = 'failed', error_reason = %s, updated_at = NOW() WHERE id = %s RETURNING *",
                (err, msg_id)
            )
            conn.commit()
            updated = cur.fetchone()
            return {"success": False, "detail": err, "data": {"message": dict(updated)}}
    finally:
        cur.close(); conn.close()



# POST /api/conversations/calls/update — called by ai-service (vapi/router.py)
# after a Vapi call ends. No auth required — internal service-to-service call.
@router.post("/calls/update")
def update_call_from_n8n(body: CallUpdateIn):
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        lead = None
        if body.patient_phone:
            cur.execute(
                "SELECT id, business_id FROM leads WHERE phone = %s LIMIT 1",
                (body.patient_phone,)
            )
            lead = cur.fetchone()

        if not lead:
            logger.info(f"[calls/update] no lead found for phone={body.patient_phone}, skipping CRM log")
            return {"success": True, "logged": False, "reason": "lead_not_found"}

        lead_id     = lead["id"]
        business_id = lead["business_id"]

        # Find or create a voice conversation for this lead
        cur.execute(
            "SELECT id FROM conversations WHERE lead_id = %s AND channel = 'voice' LIMIT 1",
            (lead_id,)
        )
        conv = cur.fetchone()
        if conv:
            conv_id = conv["id"]
        else:
            conv_id = f"conv_{uuid.uuid4().hex[:12]}"
            cur.execute("""
                INSERT INTO conversations (id, business_id, lead_id, channel, ai_active)
                VALUES (%s, %s, %s, 'voice', FALSE)
            """, (conv_id, business_id, lead_id))

        # Log call summary as a message (transcript saved in voice_calls table, not here)
        content_parts = [f"📞 Voice call — outcome: {body.outcome or 'unknown'}"]
        if body.duration_seconds:
            mins = body.duration_seconds // 60
            secs = body.duration_seconds % 60
            content_parts.append(f"Duration: {mins}m {secs}s")
        if body.summary:
            content_parts.append(f"Summary: {body.summary}")

        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        cur.execute("""
            INSERT INTO messages (id, conversation_id, role, content)
            VALUES (%s, %s, 'agent', %s)
        """, (msg_id, conv_id, "\n\n".join(content_parts)))

        # Update lead status based on call outcome. A blank/unrecognized
        # outcome with a real transcript means the lead genuinely engaged
        # (answered, talked) but no booking/cancel/reschedule intent was
        # captured — that's a "responded" (Connected) case, NOT a cancellation.
        # Previously this fell through to call_outcome_cancelled, silently
        # mislabeling real engagement as a cancel.
        outcome_event_map = {
            "confirmed":            "call_outcome_confirmed",
            "cancelled":            "call_outcome_cancelled",
            "reschedule_requested": "call_outcome_reschedule_requested",
            "no_answer":            "call_outcome_no_answer",
            "voicemail":            "call_outcome_voicemail",
        }
        # already_progressed means ai-service's transcript-content check
        # (declined/quoted/qualified) already transitioned this lead from
        # the SAME call, moments before this request arrived. The
        # transcript-length fallback below has no idea what was actually
        # SAID — confirmed live: a lead who declined 3 times got correctly
        # marked dead by that check, then immediately flipped back to
        # connected/responded here because the transcript was >100 chars
        # regardless of content. Skip the fallback entirely when a more
        # informed decision has already been made.
        if body.outcome in outcome_event_map:
            event = outcome_event_map[body.outcome]
        elif body.already_progressed:
            event = None
        elif body.transcript and len(body.transcript) > 100:
            event = "call_outcome_engaged"
        else:
            event = "call_outcome_no_answer"
        if event:
            try:
                transition_lead_status(lead_id, event=event, conn=conn, cur=cur,
                                        metadata={"call_id": body.call_id, "outcome": body.outcome})
            except InvalidTransition:
                pass

        conn.commit()
        logger.info(f"[calls/update] logged call {body.call_id} to conv {conv_id} for lead {lead_id}")
        return {"success": True, "logged": True, "conversation_id": conv_id, "lead_id": lead_id}

    except Exception as e:
        conn.rollback()
        logger.error(f"[calls/update] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# PATCH /api/conversations/:id/toggle-ai
@router.patch("/{conv_id}/toggle-ai")
def toggle_ai(conv_id: str, request: Request):
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            UPDATE conversations
            SET ai_active = NOT ai_active, updated_at = NOW()
            WHERE id = %s AND business_id = %s
            RETURNING ai_active
        """, (conv_id, business_id))
        conn.commit()
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"success": True, "data": {"ai_active": row["ai_active"]}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# POST /api/conversations/:conv_id/messages/:msg_id/approve
@router.post("/{conv_id}/messages/{msg_id}/approve")
async def approve_draft(conv_id: str, msg_id: str, request: Request):
    """Approve a draft message — send via WhatsApp then mark as agent."""
    business_id = get_business_id(request)
    conn = get_conn()
    cur  = dict_cursor(conn)
    try:
        cur.execute("""
            SELECT c.id, l.id AS lead_id, l.phone, l.preferred_channel
            FROM conversations c
            JOIN leads l ON l.id = c.lead_id
            WHERE c.id = %s AND c.business_id = %s
        """, (conv_id, business_id))
        conv = cur.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        cur.execute(
            "SELECT id, content FROM messages WHERE id = %s AND conversation_id = %s AND role = 'draft'",
            (msg_id, conv_id)
        )
        msg = cur.fetchone()
        if not msg:
            raise HTTPException(status_code=404, detail="Draft message not found")

        phone = conv.get("phone") or ""
        content = msg["content"]

        # Send via WhatsApp
        if phone:
            try:
                await send_sms(phone, content, "whatsapp")
                logger.info(f"[conversations/approve] sent WhatsApp to {phone} for msg {msg_id}")
            except Exception as e:
                logger.warning(f"[conversations/approve] send failed: {e}")

        # Promote draft → agent
        cur.execute(
            "UPDATE messages SET role = 'agent', updated_at = NOW() WHERE id = %s RETURNING *",
            (msg_id,)
        )
        conn.commit()
        updated = cur.fetchone()

        # Mark lead as contacted
        try:
            transition_lead_status(conv["lead_id"], event="welcome_sms_sent", conn=conn, cur=cur)
        except InvalidTransition:
            pass
        conn.commit()

        return {"success": True, "data": {"message": dict(updated)}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"[conversations/approve] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
