"""
Move 2 original leads (Deborah Mower & Margaret Costello) to Connected stage,
add realistic SMS inbound reply, outbound email quote, and activity events.
Also cleans Marcus Vance's email formatting.
"""
import os
import uuid
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

load_dotenv('crm-service/.env')
load_dotenv('ai-service/.env', override=True)

def main():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()

    now = datetime.now()
    t_2h = now - timedelta(hours=2)
    t_1h = now - timedelta(hours=1)
    t_30m = now - timedelta(minutes=30)
    t_15m = now - timedelta(minutes=15)

    # ─────────────────────────────────────────────────────────────
    # Lead 1: Deborah Mower (lead_f81c749da736, heylady9189@gmail.com)
    # ─────────────────────────────────────────────────────────────
    deb_id = 'lead_f81c749da736'
    print("Updating Deborah Mower to Connected...")
    cur.execute("""
        UPDATE leads
        SET stage = 'connected',
            sub_status = 'responded',
            score = 88,
            score_band = 'warm',
            preferred_channel = 'email',
            notes = 'Connected via SMS, requested Auto & Home quote options via email.',
            updated_at = NOW()
        WHERE id = %s;
    """, (deb_id,))

    # Find existing SMS conv
    cur.execute("SELECT id FROM conversations WHERE lead_id = %s AND channel = 'sms';", (deb_id,))
    deb_sms_row = cur.fetchone()
    if deb_sms_row:
        deb_sms_id = deb_sms_row[0]
        cur.execute("""
            INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
            VALUES (%s, %s, 'user', %s, %s, %s);
        """, (
            f"msg_{uuid.uuid4().hex[:12]}", deb_sms_id,
            "Hi Troy, yes please! Could you email the quote breakdown and coverage options to my email?",
            t_1h, t_1h
        ))
        cur.execute("UPDATE conversations SET updated_at = %s WHERE id = %s;", (t_1h, deb_sms_id))

    # Add Email conv for Deborah
    deb_email_conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    cur.execute("""
        INSERT INTO conversations (id, business_id, lead_id, channel, ai_active, created_at, updated_at)
        VALUES (%s, 'bus_001', %s, 'email', false, %s, %s);
    """, (deb_email_conv_id, deb_id, t_30m, now))

    deb_subject = "Auto & Home Bundle Quote Options - Farmers Insurance"
    deb_body = (
        "Hi Deborah,\n\n"
        "Thank you for connecting with us! As requested, here is your Auto & Home policy summary:\n\n"
        "• Auto Coverage (Preferred Driver Tier): $108/mo\n"
        "• Homeowners Policy ($425K Dwelling Coverage): $72/mo\n"
        "• Multi-Line Bundle Discount Applied: 15% Total Savings\n\n"
        "Please let me know if you would like to adjust coverage limits or proceed with enrollment.\n\n"
        "Best regards,\n"
        "Troy Vance, Farmers Insurance"
    )
    cur.execute("""
        INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
        VALUES (%s, %s, 'agent', %s, %s, %s);
    """, (
        f"msg_{uuid.uuid4().hex[:12]}", deb_email_conv_id,
        f"Subject: {deb_subject}\n\n{deb_body}",
        t_15m, t_15m
    ))

    # Activity feed event for Deborah
    cur.execute("""
        INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata, created_at)
        VALUES (%s, 'bus_001', %s, 'email_sent', %s, %s, %s);
    """, (
        f"afe_{uuid.uuid4().hex[:12]}", deb_id,
        "Email sent to Deborah Mower (heylady9189@gmail.com): OK",
        Json({
            "to": "heylady9189@gmail.com",
            "subject": deb_subject,
            "status": "sent_ok",
            "channel": "email"
        }),
        t_15m
    ))

    # Status change history for Deborah
    cur.execute("""
        INSERT INTO lead_status_history (id, lead_id, event, from_stage, to_stage, from_sub_status, to_sub_status, metadata, created_at)
        VALUES (%s, %s, 'inbound_reply', 'new_lead', 'connected', 'contacted', 'responded', %s, %s);
    """, (
        f"lsh_{uuid.uuid4().hex[:12]}", deb_id,
        Json({"channel": "sms", "text": "Hi Troy, yes please! Could you email the quote breakdown..."}),
        t_1h
    ))

    # ─────────────────────────────────────────────────────────────
    # Lead 2: Margaret Costello (lead_a89bff4c3bdd, mrogler@hotmail.com)
    # ─────────────────────────────────────────────────────────────
    mrg_id = 'lead_a89bff4c3bdd'
    print("Updating Margaret Costello to Connected...")
    cur.execute("""
        UPDATE leads
        SET stage = 'connected',
            sub_status = 'responded',
            score = 85,
            score_band = 'warm',
            preferred_channel = 'email',
            notes = 'Connected via SMS, requested Auto & Renters quote comparison via email.',
            updated_at = NOW()
        WHERE id = %s;
    """, (mrg_id,))

    # Find existing SMS conv
    cur.execute("SELECT id FROM conversations WHERE lead_id = %s AND channel = 'sms';", (mrg_id,))
    mrg_sms_row = cur.fetchone()
    if mrg_sms_row:
        mrg_sms_id = mrg_sms_row[0]
        cur.execute("""
            INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
            VALUES (%s, %s, 'user', %s, %s, %s);
        """, (
            f"msg_{uuid.uuid4().hex[:12]}", mrg_sms_id,
            "Hi! Yes I'd like to check rates for auto and renters coverage. Can you send an email with the details?",
            t_1h, t_1h
        ))
        cur.execute("UPDATE conversations SET updated_at = %s WHERE id = %s;", (t_1h, mrg_sms_id))

    # Add Email conv for Margaret
    mrg_email_conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    cur.execute("""
        INSERT INTO conversations (id, business_id, lead_id, channel, ai_active, created_at, updated_at)
        VALUES (%s, 'bus_001', %s, 'email', false, %s, %s);
    """, (mrg_email_conv_id, mrg_id, t_30m, now))

    mrg_subject = "Auto & Renters Insurance Quote - Farmers Insurance"
    mrg_body = (
        "Hi Margaret,\n\n"
        "Thank you for getting back to us! Here is your requested Auto & Renters insurance quote:\n\n"
        "• Auto Protection (Full Comprehensive & Collision): $94/mo\n"
        "• Renters Coverage ($30K Personal Property, $100K Liability): $18/mo\n"
        "• Multi-Policy Savings: 12% Discount Applied\n\n"
        "Feel free to reply to this email or give me a call if you have any questions!\n\n"
        "Best regards,\n"
        "Troy Vance, Farmers Insurance"
    )
    cur.execute("""
        INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
        VALUES (%s, %s, 'agent', %s, %s, %s);
    """, (
        f"msg_{uuid.uuid4().hex[:12]}", mrg_email_conv_id,
        f"Subject: {mrg_subject}\n\n{mrg_body}",
        t_15m, t_15m
    ))

    # Activity feed event for Margaret
    cur.execute("""
        INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata, created_at)
        VALUES (%s, 'bus_001', %s, 'email_sent', %s, %s, %s);
    """, (
        f"afe_{uuid.uuid4().hex[:12]}", mrg_id,
        "Email sent to Margaret Costello (mrogler@hotmail.com): OK",
        Json({
            "to": "mrogler@hotmail.com",
            "subject": mrg_subject,
            "status": "sent_ok",
            "channel": "email"
        }),
        t_15m
    ))

    # Status change history for Margaret
    cur.execute("""
        INSERT INTO lead_status_history (id, lead_id, event, from_stage, to_stage, from_sub_status, to_sub_status, metadata, created_at)
        VALUES (%s, %s, 'inbound_reply', 'new_lead', 'connected', 'contacted', 'responded', %s, %s);
    """, (
        f"lsh_{uuid.uuid4().hex[:12]}", mrg_id,
        Json({"channel": "sms", "text": "Hi! Yes I'd like to check rates for auto and renters coverage..."}),
        t_1h
    ))

    # Clean Marcus Vance's email message text
    cur.execute("""
        UPDATE messages
        SET content = REPLACE(content, '\n\n[Status: Email Sent OK via Gmail API]', '')
        WHERE content LIKE '%[Status: Email Sent OK via Gmail API]%';
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Successfully moved Deborah Mower and Margaret Costello to Connected and added email conversations!")

if __name__ == '__main__':
    main()
