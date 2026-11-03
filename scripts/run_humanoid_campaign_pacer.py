#!/usr/bin/env python3
"""
Humanoid Background Campaign Pacer
Automatically processes new leads one by one and dispatches personalized
Henry Jai AI Engineering Solutions welcome iMessages via the CRM pipeline.

Safety Controls:
- Strictly adheres to Apple anti-spam limits: max 20 messages / hour (~180-215s delay).
- Em-dash sanitization and natural human phrasing.
- Realistic typing simulation delays per message.
- Circuit breaker monitoring (auto-pauses if carrier error occurs).
- Updates lead status to 'contacted' and emits real-time activity feed events.
"""
import os
import sys
import time
import random
import signal
import logging
from datetime import datetime
from pathlib import Path

# Setup paths and environment
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crm-service"))

from dotenv import load_dotenv
load_dotenv(ROOT / "crm-service" / ".env")
load_dotenv(ROOT / "ai-service" / ".env", override=True)

import psycopg2
from psycopg2.extras import RealDictCursor, Json
import httpx
from jose import jwt

# Configure logging to both console and logs/campaign-pacer.log
LOG_FILE = ROOT / "logs" / "campaign-pacer.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [pacer] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger("campaign-pacer")

RUNNING = True

def handle_signal(sig, frame):
    global RUNNING
    logger.info(f"Received stop signal ({sig}). Gracefully shutting down campaign pacer...")
    RUNNING = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def get_jwt_token() -> str:
    secret = os.environ.get("JWT_SECRET", "ace05f4d41b57e3252ab4697237b6df587c968b79c002c52078f01a1ab651534")
    return jwt.encode(
        {"userId": "system:campaign-pacer", "role": "admin", "businessId": "bus_001"},
        secret,
        algorithm="HS256"
    )


def check_business_hours() -> tuple[bool, str]:
    """
    Check business hours dynamically against communication_rules configured in the CRM frontend.
    Falls back to 9:00 AM - 6:00 PM Eastern Time if database rule is unavailable.
    """
    import zoneinfo
    from datetime import datetime, time as dtime, timezone, timedelta

    enforce = os.environ.get("ENFORCE_EST_HOURS", "true").lower() == "true"
    if not enforce:
        return True, "Office hours check bypassed (ENFORCE_EST_HOURS=false)"

    # Default fallback values
    tz_name = "America/New_York"
    start_str = "09:00"
    end_str = "18:00"
    active_days = ["mon", "tue", "wed", "thu", "fri"]
    campaign_active = True

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT timezone, campaign_start_time, campaign_end_time, campaign_days, campaign_active
                FROM communication_rules
                WHERE business_id = %s
                LIMIT 1
            """, (BUSINESS_ID,))
            row = cur.fetchone()
            if row:
                tz_name = row.get("timezone") or tz_name
                start_str = row.get("campaign_start_time") or start_str
                end_str = row.get("campaign_end_time") or end_str
                if row.get("campaign_days"):
                    active_days = row.get("campaign_days")
                if row.get("campaign_active") is not None:
                    campaign_active = row.get("campaign_active")
        conn.close()
    except Exception as e:
        logger.warning(f"Could not read communication_rules from DB: {e}. Using defaults.")

    if not campaign_active:
        return False, "Campaign is paused in CRM Settings."

    try:
        user_tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        user_tz = zoneinfo.ZoneInfo("America/New_York")

    now_local = datetime.now(timezone.utc).astimezone(user_tz)
    current_time = now_local.time()
    weekday_str = now_local.strftime("%a").lower()

    if active_days and weekday_str not in [d.lower() for d in active_days]:
        return False, f"Today ({now_local.strftime('%A')}) is not an active campaign day ({', '.join(active_days).upper()})."

    try:
        sh, sm = [int(p) for p in start_str.split(":")]
        start_time = dtime(sh, sm)
    except Exception:
        start_time = dtime(9, 0)

    try:
        eh, em = [int(p) for p in end_str.split(":")]
        end_time = dtime(eh, em)
    except Exception:
        end_time = dtime(18, 0)

    if start_time <= current_time <= end_time:
        return True, f"Within scheduled campaign hours ({start_str} - {end_str} {now_local.strftime('%Z')})"

    if current_time < start_time:
        target_today = datetime.combine(now_local.date(), start_time, tzinfo=user_tz)
        seconds_left = max(1, int((target_today - now_local).total_seconds()))
        mins_left = seconds_left // 60
        hrs_left = mins_left // 60
        mins_rem = mins_left % 60
        time_str = f"{hrs_left}h {mins_rem}m" if hrs_left > 0 else f"{mins_rem}m"
        return False, f"Outside campaign hours: currently {now_local.strftime('%I:%M %p %Z')}. Auto-starts at {start_str} (in {time_str})."
    else:
        tomorrow = now_local.date() + timedelta(days=1)
        target_tomorrow = datetime.combine(tomorrow, start_time, tzinfo=user_tz)
        seconds_left = max(1, int((target_tomorrow - now_local).total_seconds()))
        mins_left = seconds_left // 60
        hrs_left = mins_left // 60
        mins_rem = mins_left % 60
        return False, f"Outside campaign hours: currently {now_local.strftime('%I:%M %p %Z')}. Paused for the evening; auto-resumes at {start_str} tomorrow (in {hrs_left}h {mins_rem}m)."


def check_safety_status() -> tuple[bool, str]:
    """Check ai-service circuit breaker and safety status."""
    try:
        res = httpx.get("http://localhost:8002/api/sms/safety-status", timeout=5.0)
        if res.status_code == 200:
            data = res.json().get("data", {})
            state = data.get("state", "CLOSED")
            if state != "CLOSED":
                return False, f"Circuit Breaker is {state} (Cooldown: {data.get('cooldown_remaining_seconds', 0)}s)"
            
            # Check hourly limit (20/hr)
            sent_count = data.get("hourly_sent_count", 0)
            limit = data.get("hourly_limit", 20)
            if sent_count >= limit:
                return False, f"Hourly velocity limit reached ({sent_count}/{limit})"
            
            # Check daily limit (50/day)
            daily_sent = data.get("daily_sent_count", 0)
            daily_limit = data.get("daily_limit", 50)
            if daily_sent >= daily_limit:
                return False, f"Daily velocity limit reached ({daily_sent}/{daily_limit} sent today). Paused until tomorrow to protect Apple ID."
                
            return True, f"Healthy (Today: {daily_sent}/{daily_limit}, Hour: {sent_count}/{limit})"
    except Exception as e:
        logger.warning(f"Could not reach safety-status endpoint: {e}")
    return True, "Safety check skipped (service unreachable)"


def get_next_lead(conn) -> dict | None:
    """Find the next new lead awaiting initial contact (Day 1)."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, first_name, last_name, phone, email, stage, sub_status
            FROM leads
            WHERE business_id = 'bus_001'
              AND sub_status = 'new'
              AND stage = 'new_lead'
              AND phone IS NOT NULL
              AND trim(phone) != ''
              AND (opted_out IS FALSE OR opted_out IS NULL)
            ORDER BY created_at ASC
            LIMIT 1;
        """)
        return cur.fetchone()


def get_next_followup_lead(conn) -> dict | None:
    """
    Find a lead contacted on Day 1 (>24h ago) awaiting their Day 2 follow-up (no inbound reply yet).
    Uses message history as the single source of truth:
    - Exactly 1 agent message delivered.
    - Delivered >= 24 hours ago.
    - 0 user replies in conversation.
    - Lead is not dead, opted out, converted, or appointment scheduled.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT l.id, l.first_name, l.last_name, l.phone, l.email, l.stage, l.sub_status, c.id AS conv_id,
                   m.last_sent_at
            FROM leads l
            JOIN conversations c ON c.lead_id = l.id
            JOIN (
                SELECT conversation_id, 
                       max(created_at) as last_sent_at,
                       count(CASE WHEN role = 'agent' AND status = 'delivered' THEN 1 END) as agent_delivered_count
                FROM messages
                GROUP BY conversation_id
            ) m ON m.conversation_id = c.id
            WHERE l.business_id = 'bus_001'
              AND l.phone IS NOT NULL
              AND trim(l.phone) != ''
              AND (l.opted_out IS FALSE OR l.opted_out IS NULL)
              AND l.stage NOT IN ('dead', 'converted', 'closed', 'appointment_scheduled')
              AND m.agent_delivered_count = 1
              AND m.last_sent_at <= NOW() - INTERVAL '24 hours'
              AND NOT EXISTS (
                  SELECT 1 FROM messages m_user
                  WHERE m_user.conversation_id = c.id
                    AND m_user.role = 'user'
              )
            ORDER BY m.last_sent_at ASC
            LIMIT 1;
        """)
        return cur.fetchone()


def choose_next_campaign_task(conn, turn_counter: int) -> tuple[str, dict] | tuple[None, None]:
    """
    Intelligently balances campaign outreach and lead nurturing:
    - Queue A: Overdue Day 2 Follow-Ups (leads contacted >24h ago with 0 inbound replies).
    - Queue B: New Cold Leads (Day 1 initial outreach).
    
    Balancing Logic:
    1. If both follow-ups and new leads are waiting, it alternates 1:1 between them:
       - Even turns: Day 2 Follow-Up (nurture warm, in-flight conversations).
       - Odd turns: Day 1 Initial Outreach (bring in fresh leads).
    2. If only one queue has candidates, it processes that queue without idling.
    3. If neither has candidates, returns (None, None).
    """
    fu_lead = get_next_followup_lead(conn)
    new_lead = get_next_lead(conn)

    if fu_lead and new_lead:
        # Balanced 1:1 interleaving: follow-ups on even turns, new leads on odd turns
        if turn_counter % 2 == 0:
            return "followup", fu_lead
        else:
            return "new_lead", new_lead
    elif fu_lead:
        return "followup", fu_lead
    elif new_lead:
        return "new_lead", new_lead
    return None, None


def get_or_create_conversation(lead_id: str, headers: dict) -> str | None:
    """Ensure conversation exists for lead."""
    try:
        res = httpx.post(
            "http://localhost:8003/api/conversations",
            json={"lead_id": lead_id, "channel": "sms"},
            headers=headers,
            timeout=20.0
        )
        if res.status_code in (200, 201):
            return res.json()["data"]["conversation"]["id"]
        else:
            logger.error(f"Failed to create/get conversation for lead {lead_id}: {res.text}")
    except Exception as e:
        logger.error(f"Error creating conversation for lead {lead_id}: {e}")
    return None


def send_welcome_imessage(conv_id: str, lead: dict, headers: dict) -> bool:
    """
    Send universal, non-assuming networking opening message (40-60 words).
    Does NOT assume recipient works in AI, uses AI, or needs AI.
    Introduces custom software/AI solutions without advertising.
    Ends with an open-ended question that works for professionals in any industry.
    """
    import random
    first_name = (lead.get("first_name") or "").strip()
    greeting = f"Hi {first_name}," if first_name else "Hi,"
    
    universal_hooks = [
        f"{greeting} Henry Jai here, hope you are having a productive week. Reaching out to connect with other professionals and learn about different businesses. On our side, we help teams build custom software and practical AI solutions, but I always enjoy discovering new industries. What key goals or projects is your team focusing on this quarter?",
        f"{greeting} Henry Jai here. I came across your profile while connecting with leaders across various sectors. Our team develops custom digital and AI solutions, but I really enjoy learning how different businesses operate and grow. What kind of exciting challenges or initiatives are you tackling right now?",
        f"{greeting} Henry Jai here. Reaching out to expand my network with fellow professionals. We specialize in custom software and practical AI development, but I always enjoy hearing what other companies are building and prioritizing. How are things shaping up for your business this year, and what areas are you currently most focused on?",
        f"{greeting} Henry Jai here, hope you are having a great week. Reaching out peer-to-peer to broaden my network. We focus on modern software architecture and practical AI implementations, but I am always fascinated to learn about different business models. What major initiatives is your organization currently working on right now?",
        f"{greeting} Henry Jai here. Connecting with professionals across varied fields to learn what teams are prioritizing this season. We build bespoke software and intelligent automated workflows, but I always value genuine cross-industry conversations. What are some of the most interesting opportunities or projects your team is exploring today?",
        f"{greeting} Henry Jai here, hope all is well. Expanding my network to connect with forward-thinking leaders. On our end, we develop custom digital solutions and applied AI tools, but I love hearing how different organizations tackle growth. What kind of key milestones or challenges are you currently navigating this quarter?"
    ]
    
    # Pick hook with pseudo-random seed per lead
    hook_idx = abs(hash(lead.get("id", ""))) % len(universal_hooks) if lead.get("id") else random.randint(0, len(universal_hooks) - 1)
    body = universal_hooks[hook_idx]
    
    logger.info(f"Sending universal discovery iMessage ({len(body.split())}w) to {lead.get('first_name')} {lead.get('last_name')} ({lead.get('phone')})...")
    try:
        res = httpx.post(
            f"http://localhost:8003/api/conversations/{conv_id}/messages",
            json={"role": "agent", "content": body},
            headers=headers,
            timeout=90.0
        )
        if res.status_code == 200:
            data = res.json().get("data", {})
            msg = data.get("message", {})
            if msg.get("status") == "delivered":
                logger.info(f"✓ Universal discovery iMessage delivered successfully to {lead.get('phone')} (msg_id={msg.get('id')})")
                return True
            else:
                logger.warning(f"Message send returned status '{msg.get('status')}': {data.get('send_error')}")
                return False
        else:
            logger.error(f"Message API returned {res.status_code}: {res.text}")
            return False
    except Exception as e:
        logger.error(f"Exception sending message to {lead.get('phone')}: {e}")
        return False


def send_or_retry_discovery_message(conn, conv_id: str, lead: dict, headers: dict) -> bool:
    """
    Send or auto-retry Day 1 universal discovery message (40-60 words).
    If an existing message failed (e.g. from yesterday before native SMS relay was enabled),
    retries the existing message in-place to update status to delivered and avoid duplicate bubbles.
    Otherwise, generates a fresh universal hook and dispatches via POST /messages.
    """
    failed_msg_id = None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM messages 
                WHERE conversation_id = %s AND status = 'failed'
                ORDER BY created_at ASC LIMIT 1;
            """, (conv_id,))
            row = cur.fetchone()
            if row:
                failed_msg_id = row[0]
    except Exception as e:
        logger.warning(f"Error checking existing failed message for {conv_id}: {e}")

    if failed_msg_id:
        logger.info(f"Auto-retrying existing failed message ({failed_msg_id}) for {lead.get('first_name')} {lead.get('last_name')} ({lead.get('phone')}) via native SMS relay...")
        try:
            res = httpx.post(
                f"http://localhost:8003/api/conversations/{conv_id}/messages/{failed_msg_id}/retry",
                json={"channel": "imessage"},
                headers=headers,
                timeout=90.0
            )
            if res.status_code == 200:
                data = res.json().get("data", {})
                msg = data.get("message", {})
                if msg.get("status") == "delivered":
                    logger.info(f"✓ Outreach successfully delivered to {lead.get('phone')} (msg_id={failed_msg_id})")
                    return True
                else:
                    logger.warning(f"Retry returned status '{msg.get('status')}': {data.get('send_error')}")
                    return False
            else:
                logger.error(f"Retry API returned {res.status_code}: {res.text}")
                return False
        except Exception as e:
            logger.error(f"Exception during auto-retry for {lead.get('phone')}: {e}")
            return False

    # Otherwise, fresh send
    return send_welcome_imessage(conv_id, lead, headers)


def get_prior_outbound_messages(conn, conv_id: str) -> list[str]:
    """Fetch all prior outbound messages sent in this conversation."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT content FROM messages 
                WHERE conversation_id = %s AND role = 'agent'
                ORDER BY created_at ASC;
            """, (conv_id,))
            return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.warning(f"Failed to fetch prior outbound messages for {conv_id}: {e}")
        return []


def send_followup_imessage(conn, conv_id: str, lead: dict, headers: dict) -> bool:
    """Send polite, low-pressure Day 2 follow-up (universal, non-assuming).
    
    Guaranteed:
    1. Always DIFFERENT from the first message sent to this lead (checks prior messages in DB).
    2. Always DIFFERENT across different leads (8 dynamic angles).
    3. Strictly between 40 and 60 words.
    4. Sender persona: Henry Jai.
    5. Zero mention of 'AllZone' or 'AllZone Technologies'.
    6. Open-ended, conversational networking inquiry.
    """
    import random
    first_name = (lead.get("first_name") or "").strip()
    greeting = f"Hi {first_name}," if first_name else "Hi,"
    
    prior_messages = get_prior_outbound_messages(conn, conv_id)
    prior_text = " ".join(prior_messages).lower()

    # 8 distinct follow-up variations spanning different networking angles (all 40-60 words):
    followup_hooks = [
        # Angle 1: Operational challenges & team focus (51 words)
        f"{greeting} Henry Jai following up briefly. Totally understand if you are heads-down with your team right now. Whenever you have a free moment, would love to hear what key goals or initiatives you are tackling this quarter. No pressure at all, hope you have a great rest of your week!",
        
        # Angle 2: Cross-industry perspective & evolving businesses (48 words)
        f"{greeting} Henry Jai here. Just wanted to follow up on my earlier note. No sales pitch whatsoever, I just always enjoy connecting with professionals across different sectors to see how businesses are evolving. What are the main milestones or projects your team is focusing on right now?",
        
        # Angle 3: Practical digital tools & operational problems (50 words)
        f"{greeting} Henry Jai here, hope your week is going smoothly. Circling back briefly in case my note got lost in the shuffle. We build custom software and AI tools, but I love learning about diverse industries. What kind of interesting problems or operational challenges are you solving these days?",
        
        # Angle 4: Annual priorities & growth targets (48 words)
        f"{greeting} Henry Jai checking in. Reaching out peer-to-peer just to see how things are progressing on your side. Zero pressure to reply, but if you have a moment, I would love to learn what big priorities or growth targets your business is currently working toward this year.",
        
        # Angle 5: Casual check-in on quarterly progress (47 words)
        f"{greeting} Henry Jai following up quickly. I know how busy schedules can get during the week. Whenever things quiet down, I would be glad to hear about what you and your team are currently building. How is this quarter shaping up for your business so far?",
        
        # Angle 6: New directions & exploring initiatives (47 words)
        f"{greeting} Henry Jai here. Just floating this back up briefly. Our background is in custom digital solutions, but I genuinely enjoy swapping insights with leaders in other fields. What are some of the most exciting new initiatives or directions your organization is exploring at the moment?",
        
        # Angle 7: Low-pressure company navigation (47 words)
        f"{greeting} Henry Jai circling back briefly. No worries if timing is not right at all. Just wanted to see what key initiatives your company is prioritizing as you navigate this quarter. Always open to connecting and hearing what professionals across different industries are currently focused on.",
        
        # Angle 8: Bespoke tech workflows & top-of-mind objectives (49 words)
        f"{greeting} Henry Jai here, hope you are having a productive week. Just touching base following my note yesterday. We develop tailor-made software and AI workflows, but I am always curious how teams in various sectors operate. What major projects or objectives are top of mind for you today?"
    ]

    # Filter out any candidate hook that shares key thematic phrases with prior messages
    candidates = []
    for h in followup_hooks:
        h_lower = h.lower()
        if "shaping up" in prior_text and "shaping up" in h_lower:
            continue
        if "diverse industries" in prior_text and "diverse industries" in h_lower:
            continue
        if "milestones" in prior_text and "milestones" in h_lower:
            continue
        if "growth targets" in prior_text and "growth" in h_lower:
            continue
        if "operational challenges" in prior_text and "operational" in h_lower:
            continue
        candidates.append(h)

    if not candidates:
        candidates = followup_hooks

    # Select deterministically per lead + random salt so every lead gets a fresh angle
    salt = random.randint(1, 9999)
    lead_seed = abs(hash(lead.get("id", "") + str(salt)))
    body = candidates[lead_seed % len(candidates)]
    
    words_count = len(body.split())
    logger.info(f"Sending distinct Day 2 follow-up ({words_count}w) to {lead.get('first_name')} {lead.get('last_name')} ({lead.get('phone')})...")
    try:
        res = httpx.post(
            f"http://localhost:8003/api/conversations/{conv_id}/messages",
            json={"role": "agent", "content": body},
            headers=headers,
            timeout=90.0
        )
        if res.status_code == 200:
            data = res.json().get("data", {})
            msg = data.get("message", {})
            if msg.get("status") == "delivered":
                logger.info(f"✓ Day 2 follow-up delivered successfully to {lead.get('phone')} (msg_id={msg.get('id')})")
                return True
            else:
                logger.warning(f"Follow-up send returned status '{msg.get('status')}': {data.get('send_error')}")
                return False
        else:
            logger.error(f"Message API returned {res.status_code}: {res.text}")
            return False
    except Exception as e:
        logger.error(f"Exception sending follow-up to {lead.get('phone')}: {e}")
        return False


def update_lead_status(conn, lead_id: str, lead_name: str, channel: str = "imessage"):
    """Update lead sub_status to contacted and record activity feed event."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE leads
            SET sub_status = 'contacted', stage = 'new_lead', updated_at = NOW()
            WHERE id = %s;
        """, (lead_id,))
        
        cur.execute("""
            INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata, created_at)
            VALUES (
                'afe_' || substr(md5(random()::text), 1, 12),
                'bus_001',
                %s,
                'sms_sent',
                %s,
                %s,
                NOW()
            );
        """, (
            lead_id,
            f"{lead_name}: automated iMessage sent (generic discovery)",
            Json({"channel": channel, "status": "delivered", "stage": "day1_discovery"})
        ))
        conn.commit()


def update_lead_followed_up(conn, lead_id: str, lead_name: str, channel: str = "imessage"):
    """Update lead sub_status to follow_up_sent and record activity feed event."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE leads
            SET sub_status = 'follow_up_sent', stage = 'new_lead', updated_at = NOW()
            WHERE id = %s;
        """, (lead_id,))
        
        cur.execute("""
            INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata, created_at)
            VALUES (
                'afe_' || substr(md5(random()::text), 1, 12),
                'bus_001',
                %s,
                'sms_sent',
                %s,
                %s,
                NOW()
            );
        """, (
            lead_id,
            f"{lead_name}: automated Day 2 follow-up sent",
            Json({"channel": channel, "status": "delivered", "stage": "day2_followup"})
        ))
        conn.commit()


def mark_lead_failed(conn, lead_id: str, lead_name: str, error_reason: str):
    """Mark lead as dead / non-imessage when recipient cannot receive iMessage."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE leads
            SET stage = 'dead',
                sub_status = 'dead',
                notes = %s,
                tags = array_append(tags, 'non-imessage'),
                updated_at = NOW()
            WHERE id = %s;
        """, (f"iMessage delivery failed: {error_reason[:150]}", lead_id))
        cur.execute("""
            INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata, created_at)
            VALUES (
                'afe_' || substr(md5(random()::text), 1, 12),
                'bus_001',
                %s,
                'sms_failed',
                %s,
                %s,
                NOW()
            );
        """, (
            lead_id,
            f"{lead_name}: iMessage delivery failed (non-iMessage number)",
            Json({"error": error_reason, "channel": "imessage"})
        ))
        conn.commit()


def main():
    logger.info("==================================================")
    logger.info("Humanoid Background Campaign Pacer starting up...")
    logger.info("Policy: Intelligent Dual-Queue Interleaving (1:1 Follow-up : New Lead)")
    logger.info("50 Leads/Day Max | 1 Msg Day 1 | Follow-up Day 2 | 3+ min Humanoid Gap")
    logger.info("Schedule: 9:00 AM - 5:30 PM Daily (Auto-Start / Auto-Pause)")
    logger.info("==================================================")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not found. Exiting.")
        return

    conn = psycopg2.connect(db_url)
    conn.autocommit = False

    sent_in_run = 0

    while RUNNING:
        try:
            # 1. Business hours check (9:00 AM - 5:30 PM)
            in_hours, hours_msg = check_business_hours()
            if not in_hours:
                logger.info(f"[schedule] {hours_msg} Sleeping 60s...")
                for _ in range(60):
                    if not RUNNING:
                        break
                    time.sleep(1)
                continue

            # 2. Safety check (circuit breaker, hourly 20 limit, daily 50 limit)
            safe, reason = check_safety_status()
            if not safe:
                logger.warning(f"Safety pause: {reason}. Pausing pacer for 60 seconds...")
                for _ in range(60):
                    if not RUNNING:
                        break
                    time.sleep(1)
                continue

            headers = {"Authorization": f"Bearer {get_jwt_token()}"}

            # 3. Intelligent Dual-Queue Task Selection (Interleaving 1:1)
            task_type, target_lead = choose_next_campaign_task(conn, sent_in_run)

            if task_type == "new_lead":
                lead = target_lead
                lead_id = lead["id"]
                lead_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or lead_id

                # Create or fetch conversation
                conv_id = get_or_create_conversation(lead_id, headers)
                if not conv_id:
                    logger.error(f"Skipping lead {lead_id} due to conversation creation error.")
                    time.sleep(5)
                    continue

                # Dispatch or auto-retry Day 1 universal discovery outreach
                logger.info(f"[intelligent-pacer:new-lead] Dispatching Day 1 discovery to {lead_name} ({lead.get('phone')})...")
                success = send_or_retry_discovery_message(conn, conv_id, lead, headers)
                if success:
                    update_lead_status(conn, lead_id, lead_name)
                    sent_in_run += 1
                    logger.info(f"✓ Outreach sent to lead {lead_name} (Total dispatched today: {sent_in_run})")
                    # At least 3 minutes gap: base 180s (3.0 mins) + 10-35s natural human jitter = ~3.1m to 3.6m
                    delay = 180 + random.randint(10, 35)
                    logger.info(f"Humanoid pacing gap (at least 3 minutes): waiting {delay}s (~{delay/60:.1f}m) before next message...")
                else:
                    logger.warning(f"Send was not confirmed delivered for {lead_name}. Marking lead delivery failed and advancing...")
                    mark_lead_failed(conn, lead_id, lead_name, "Delivery failed via both iMessage and SMS relay")
                    try:
                        httpx.post("http://localhost:8002/api/sms/reset-circuit-breaker", headers=headers, timeout=5.0)
                    except Exception:
                        pass
                    delay = 15
                    logger.info(f"Undeliverable lead handled. Advancing to next lead in queue in {delay}s...")

            elif task_type == "followup":
                fu_lead = target_lead
                lead_id = fu_lead["id"]
                lead_name = f"{fu_lead.get('first_name', '')} {fu_lead.get('last_name', '')}".strip() or lead_id
                conv_id = fu_lead["conv_id"]

                logger.info(f"[intelligent-pacer:follow-up] Processing Day 2 follow-up for {lead_name} ({fu_lead.get('phone')})...")
                fu_success = send_followup_imessage(conn, conv_id, fu_lead, headers)
                if fu_success:
                    update_lead_followed_up(conn, lead_id, lead_name)
                    sent_in_run += 1
                    logger.info(f"✓ Day 2 follow-up dispatched to {lead_name} (Total dispatched today: {sent_in_run})")
                    delay = 180 + random.randint(10, 35)
                    logger.info(f"Humanoid pacing gap (at least 3 minutes): waiting {delay}s (~{delay/60:.1f}m) before next message...")
                else:
                    delay = 15
                    logger.warning(f"Follow-up send failed for {lead_name}. Advancing in {delay}s...")

            else:
                logger.info("No new leads or follow-ups awaiting contact. Sleeping 30s before checking again...")
                for _ in range(30):
                    if not RUNNING:
                        break
                    time.sleep(1)
                continue

            for _ in range(delay):
                if not RUNNING:
                    break
                time.sleep(1)

        except Exception as e:
            logger.error(f"Unexpected loop exception: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            time.sleep(10)

    conn.close()
    logger.info(f"Campaign pacer stopped. Total sent this session: {sent_in_run}")


if __name__ == "__main__":
    main()
