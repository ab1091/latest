"""
Seed a realistic connected lead with an email & SMS conversation,
send a confirmation email via Gmail API, and log the event.
"""
import os
import uuid
import asyncio
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

# Load environments
load_dotenv('crm-service/.env')
load_dotenv('ai-service/.env', override=True)

import sys
sys.path.insert(0, os.path.abspath('ai-service'))
from core.gmail import send_email

def main():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()

    business_id = 'bus_001'
    lead_id = f"lead_{uuid.uuid4().hex[:12]}"
    conv_sms_id = f"conv_{uuid.uuid4().hex[:12]}"
    conv_email_id = f"conv_{uuid.uuid4().hex[:12]}"

    first_name = "Marcus"
    last_name = "Vance"
    email = "shieldsquadagency+dummytest@gmail.com"
    phone = "+18582325999"

    print(f"Creating connected lead: {first_name} {last_name} ({email}, {phone})...")

    now = datetime.now()
    t_minus_2h = now - timedelta(hours=2)
    t_minus_1h = now - timedelta(hours=1)
    t_minus_30m = now - timedelta(minutes=30)
    t_minus_10m = now - timedelta(minutes=10)

    # 1. Create Lead in 'connected' stage, 'responded' sub_status
    cur.execute("""
        INSERT INTO leads (
            id, business_id, first_name, last_name, email, phone,
            tags, sub_status, stage, strategy, source, preferred_channel,
            score, score_band, notes, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """, (
        lead_id, business_id, first_name, last_name, email, phone,
        ['auto', 'home', 'quote_requested'], 'responded', 'connected',
        'sms_first', 'web_form', 'email',
        85, 'warm', 'Requested quote breakdown for Auto & Home bundle via email.',
        t_minus_2h, now
    ))

    # 2. Add SMS Conversation where user replied with interest and email
    cur.execute("""
        INSERT INTO conversations (id, business_id, lead_id, channel, ai_active, created_at, updated_at)
        VALUES (%s, %s, %s, 'sms', true, %s, %s)
    """, (conv_sms_id, business_id, lead_id, t_minus_2h, t_minus_1h))

    cur.execute("""
        INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
        VALUES 
        (%s, %s, 'agent', %s, %s, %s),
        (%s, %s, 'user', %s, %s, %s)
    """, (
        f"msg_{uuid.uuid4().hex[:12]}", conv_sms_id,
        "Hey Marcus, it's Troy with Farmers Insurance. I see you're looking for auto & home bundle options. Would you like me to send over the coverage breakdown?",
        t_minus_2h, t_minus_2h,
        f"msg_{uuid.uuid4().hex[:12]}", conv_sms_id,
        "Yes definitely! Could you please email the quote summary and policy details to my email?",
        t_minus_1h, t_minus_1h
    ))

    # 3. Add Email Conversation showing sent quote & email delivered OK
    cur.execute("""
        INSERT INTO conversations (id, business_id, lead_id, channel, ai_active, created_at, updated_at)
        VALUES (%s, %s, %s, 'email', true, %s, %s)
    """, (conv_email_id, business_id, lead_id, t_minus_30m, now))

    email_subject = "Quote Breakdown & Policy Options - Farmers Insurance"
    email_body = (
        f"Hi {first_name},\n\n"
        "Thank you for connecting with Farmers Insurance! As requested, here is your auto & home bundle quote summary:\n\n"
        "• Auto Policy (Comprehensive & Collision): $115/mo\n"
        "• Homeowners Coverage ($450K Dwelling): $78/mo\n"
        "• Multi-Policy Bundle Discount Applied: 15% Savings\n\n"
        "Please let me know if you would like to proceed or adjust coverage limits.\n\n"
        "Best regards,\n"
        "Troy Vance, Farmers Insurance"
    )

    cur.execute("""
        INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)
        VALUES 
        (%s, %s, 'agent', %s, %s, %s)
    """, (
        f"msg_{uuid.uuid4().hex[:12]}", conv_email_id,
        f"Subject: {email_subject}\n\n{email_body}\n\n[Status: Email Sent OK via Gmail API]",
        t_minus_10m, t_minus_10m
    ))

    # 4. Add Activity Feed Event
    cur.execute("""
        INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        f"afe_{uuid.uuid4().hex[:12]}", business_id, lead_id,
        'email_sent',
        f"Email sent to {first_name} {last_name} ({email}): OK",
        Json({
            "to": email,
            "subject": email_subject,
            "status": "sent_ok",
            "channel": "email"
        }),
        t_minus_10m
    ))

    # 5. Add Lead status history event
    cur.execute("""
        INSERT INTO lead_status_history (
            id, lead_id, event, from_stage, to_stage, from_sub_status, to_sub_status, metadata, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """, (
        f"lsh_{uuid.uuid4().hex[:12]}", lead_id,
        'inbound_reply', 'new_lead', 'connected', 'contacted', 'responded',
        Json({"channel": "sms", "text": "Yes definitely! Could you please email the quote summary..."}),
        t_minus_1h
    ))

    conn.commit()
    cur.close()
    conn.close()
    print("Database records committed successfully!")

    # 6. Send live email via Gmail API
    print(f"Sending live email via Gmail API to {email}...")
    try:
        sent = asyncio.run(send_email(to=email, subject=email_subject, body=email_body))
        print(f"Gmail send result: {sent}")
    except Exception as e:
        print(f"Gmail send exception: {e}")

if __name__ == '__main__':
    main()
