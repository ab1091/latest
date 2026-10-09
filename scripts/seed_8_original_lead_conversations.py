#!/usr/bin/env python3
"""
Seed 8 Realistic Conversations on Original Leads from the Imported List
Demonstrating real-world outcomes:
1. Wrong Number Objection (Kristen Pelz)
2. Not Interested / Renewed elsewhere (Margaret Tuttle)
3. Aggressive Profanity / Hostile Opt-Out (Craig Watz)
4. Too Expensive / Historical Price Objection (Joe Woodyard)
5. Standard Carrier "STOP" Opt-Out (Sharon Owen)
6. Interested in Auto Only (Bonnie Hubler)
7. Call Timing Objection - "Call me tomorrow 10am" (Chase Wilson)
8. Channel Preference - "Email me the options" (Carrie Scott)
"""
import os
import uuid
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv

load_dotenv('crm-service/.env')
load_dotenv('ai-service/.env', override=True)


def seed():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    now = datetime.now()

    def t(minutes_ago):
        return now - timedelta(minutes=minutes_ago)

    conversations_data = [
        # ── 1. WRONG NUMBER ──────────────────────────────────────────────────
        {
            "lead_id": "lead_00089a99cf21",
            "name": "Kristen Pelz",
            "phone": "+12104266651",
            "stage": "dead",
            "sub_status": "dead",
            "opted_out": True,
            "notes": "Recipient reported wrong number: does not know Kristen.",
            "preferred_channel": "sms",
            "t_start": 45,
            "t_reply": 38,
            "t_close": 35,
            "messages": [
                ("agent", "Hey Kristen, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "You have the wrong number. I don't know any Kristen and I live in Chicago."),
                ("agent", "My apologies for the confusion! I've removed this number from our system right away. Have a great day!")
            ],
            "activity_title": "Kristen Pelz: marked as wrong number / dead",
            "history_event": "wrong_number"
        },
        # ── 2. NOT INTERESTED ────────────────────────────────────────────────
        {
            "lead_id": "lead_0127ba123457",
            "name": "Margaret Tuttle",
            "phone": "+19139570464",
            "stage": "dead",
            "sub_status": "dead",
            "opted_out": False,
            "notes": "Not interested - recently renewed existing policy with State Farm.",
            "preferred_channel": "sms",
            "t_start": 40,
            "t_reply": 32,
            "t_close": 30,
            "messages": [
                ("agent", "Hey Margaret, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "Not interested at this time, we just renewed our policy with State Farm last month."),
                ("agent", "Completely understand Margaret! Thank you for letting me know. Feel free to keep our number handy if you ever want a rate comparison down the road. Take care!")
            ],
            "activity_title": "Margaret Tuttle: declined - not interested",
            "history_event": "not_interested"
        },
        # ── 3. HOSTILE / PROFANITY ("fuck") ──────────────────────────────────
        {
            "lead_id": "lead_01d8c840c4c5",
            "name": "Craig Watz",
            "phone": "+18168055539",
            "stage": "dead",
            "sub_status": "dead",
            "opted_out": True,
            "notes": "Immediate compliance opt-out: hostile inbound profanity.",
            "preferred_channel": "sms",
            "t_start": 35,
            "t_reply": 29,
            "t_close": 28,
            "messages": [
                ("agent", "Hey Craig, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "Fuck off and stop texting my fucking phone. Who the hell gave you this number?!"),
                ("agent", "No problem at all, completely understand! So sorry to have bothered you. I've taken you off my list right away so you won't receive any more messages. Wishing you all the best and take care!")
            ],
            "activity_title": "Craig Watz: opted out (hostile reply)",
            "history_event": "compliance_opt_out"
        },
        # ── 4. TOO EXPENSIVE OBJECTION ───────────────────────────────────────
        {
            "lead_id": "lead_01fca7f0d762",
            "name": "Joe Woodyard",
            "phone": "+14044055598",
            "stage": "connected",
            "sub_status": "responded",
            "opted_out": False,
            "notes": "Historical pricing objection. Handled with tier discount explanation.",
            "preferred_channel": "sms",
            "t_start": 30,
            "t_reply": 22,
            "t_close": 20,
            "messages": [
                ("agent", "Hey Joe, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "Farmers was way too expensive when I checked last year. Not really looking to switch."),
                ("agent", "I hear you, Joe. Rates and tier discounts have adjusted quite a bit this quarter (especially bundle savings), but no pressure at all. Let me know if you ever want a quick no-obligation look. Have a great week!")
            ],
            "activity_title": "Joe Woodyard: connected - pricing objection handled",
            "history_event": "inbound_reply"
        },
        # ── 5. CARRIER "STOP" KEYWORD ────────────────────────────────────────
        {
            "lead_id": "lead_02213ac3fbdd",
            "name": "Sharon Owen",
            "phone": "+18165004274",
            "stage": "dead",
            "sub_status": "dead",
            "opted_out": True,
            "notes": "Automated carrier compliance opt-out via keyword STOP.",
            "preferred_channel": "sms",
            "t_start": 25,
            "t_reply": 21,
            "t_close": 20,
            "messages": [
                ("agent", "Hey Sharon, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "STOP"),
                ("agent", "No problem at all, completely understand! So sorry to have bothered you. I've taken you off my list right away so you won't receive any more messages. Wishing you all the best and take care!")
            ],
            "activity_title": "Sharon Owen: unsubscribed via STOP",
            "history_event": "compliance_stop"
        },
        # ── 6. INTERESTED IN AUTO ONLY ───────────────────────────────────────
        {
            "lead_id": "lead_03808042cedc",
            "name": "Bonnie Hubler",
            "phone": "+18168980191",
            "stage": "connected",
            "sub_status": "responded",
            "opted_out": False,
            "notes": "Requested standalone auto quote for two drivers (current policy jumped $40/mo).",
            "preferred_channel": "sms",
            "t_start": 20,
            "t_reply": 15,
            "t_close": 13,
            "messages": [
                ("agent", "Hey Bonnie, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "Hi Troy, our home is already covered, but my auto rates jumped $40 last month. Can you quote just auto for two drivers?"),
                ("agent", "Happy to help with that Bonnie! We can definitely run a standalone auto comparison. What make/model and approximate year are the vehicles you drive?")
            ],
            "activity_title": "Bonnie Hubler: requested Auto quote comparison",
            "history_event": "inbound_reply"
        },
        # ── 7. TIMING OBJECTION / CALL TOMORROW (APPOINTMENT BOOKED) ─────────
        {
            "lead_id": "lead_04b5e9e25879",
            "name": "Chase Wilson",
            "phone": "+19134982418",
            "stage": "appointment_scheduled",
            "sub_status": "appointment_scheduled",
            "opted_out": False,
            "notes": "Phone appointment booked for tomorrow at 10:00 AM CT.",
            "preferred_channel": "sms",
            "t_start": 18,
            "t_reply": 12,
            "t_close": 10,
            "messages": [
                ("agent", "Hey Chase, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "In a meeting all afternoon. Can someone call me tomorrow morning around 10am CT?"),
                ("agent", "Got it, Chase! I have noted tomorrow at 10:00 AM CT on our calendar for a quick phone call. Talk to you then!")
            ],
            "activity_title": "Chase Wilson: phone appointment booked for tomorrow 10:00 AM CT",
            "history_event": "appointment_booked"
        },
        # ── 8. EMAIL PREFERRED ───────────────────────────────────────────────
        {
            "lead_id": "lead_0568e728e38b",
            "name": "Carrie Scott",
            "phone": "+19136602614",
            "stage": "connected",
            "sub_status": "responded",
            "opted_out": False,
            "notes": "Prefers email in writing. Preparing Auto & Home quote for carrie.scott@me.com.",
            "preferred_channel": "email",
            "t_start": 15,
            "t_reply": 8,
            "t_close": 6,
            "messages": [
                ("agent", "Hey Carrie, it's Troy with Farmers Insurance. I see you're looking into Auto, Home, Renters or Life Insurance coverage. Would you like me to put together a quote breakdown for you? Feel free to reply here or call anytime. Reply NO THANKS to opt out."),
                ("user", "Yes please, but I prefer reviewing everything in writing. Can you email the bundle options to carrie.scott@me.com?"),
                ("agent", "Absolutely, Carrie! I will put together the Auto and Home bundle breakdown and send it directly to carrie.scott@me.com shortly.")
            ],
            "activity_title": "Carrie Scott: requested quote options via email",
            "history_event": "inbound_reply"
        }
    ]

    for item in conversations_data:
        lead_id = item["lead_id"]
        print(f"Seeding conversation for {item['name']} ({item['phone']}, id={lead_id})...")

        # 1. Update Lead Status
        cur.execute("""
            UPDATE leads
            SET stage = %s,
                sub_status = %s,
                opted_out = %s,
                notes = %s,
                preferred_channel = %s,
                updated_at = NOW()
            WHERE id = %s;
        """, (
            item["stage"],
            item["sub_status"],
            item["opted_out"],
            item["notes"],
            item["preferred_channel"],
            lead_id
        ))

        # 2. Get or create conversation
        cur.execute("SELECT id FROM conversations WHERE lead_id = %s AND channel = 'sms';", (lead_id,))
        conv_row = cur.fetchone()
        if conv_row:
            conv_id = conv_row["id"]
        else:
            conv_id = f"conv_{uuid.uuid4().hex[:12]}"
            cur.execute("""
                INSERT INTO conversations (id, business_id, lead_id, channel, ai_active, created_at, updated_at)
                VALUES (%s, 'bus_001', %s, 'sms', true, %s, %s);
            """, (conv_id, lead_id, t(item["t_start"]), now))

        # Clear existing messages in this test conv if any
        cur.execute("DELETE FROM messages WHERE conversation_id = %s;", (conv_id,))

        # 3. Insert Messages
        times = [t(item["t_start"]), t(item["t_reply"]), t(item["t_close"])]
        for idx, (role, content) in enumerate(item["messages"]):
            msg_time = times[idx]
            cur.execute("""
                INSERT INTO messages (id, conversation_id, role, content, status, channel, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'delivered', 'sms', %s, %s);
            """, (
                f"msg_{uuid.uuid4().hex[:12]}",
                conv_id,
                role,
                content,
                msg_time,
                msg_time
            ))

        # Update conversation timestamp to latest message
        cur.execute("UPDATE conversations SET updated_at = %s WHERE id = %s;", (times[-1], conv_id))

        # 4. Activity Feed Event
        cur.execute("""
            INSERT INTO activity_feed_events (id, business_id, lead_id, event_type, title, metadata, created_at)
            VALUES (%s, 'bus_001', %s, 'stage_change', %s, %s, %s);
        """, (
            f"afe_{uuid.uuid4().hex[:12]}",
            lead_id,
            item["activity_title"],
            Json({"channel": "imessage", "outcome": item["history_event"]}),
            times[1]
        ))

        # 5. Lead Status History
        cur.execute("""
            INSERT INTO lead_status_history (id, lead_id, event, from_stage, to_stage, from_sub_status, to_sub_status, metadata, created_at)
            VALUES (%s, %s, %s, 'new_lead', %s, 'new', %s, %s, %s);
        """, (
            f"lsh_{uuid.uuid4().hex[:12]}",
            lead_id,
            item["history_event"],
            item["stage"],
            item["sub_status"],
            Json({"last_reply": item["messages"][1][1][:50]}),
            times[1]
        ))

        # 6. Appointments table insertion (for appointment_scheduled leads)
        if item["stage"] == "appointment_scheduled":
            cur.execute("DELETE FROM appointments WHERE lead_id = %s;", (lead_id,))
            cur.execute("SELECT id FROM users WHERE phone = %s LIMIT 1;", (item["phone"],))
            u_row = cur.fetchone()
            if u_row:
                cust_user_id = u_row["id"]
            else:
                cust_user_id = f"usr_sms_{uuid.uuid4().hex[:8]}"
                cur.execute("""
                    INSERT INTO users (id, phone, first_name, last_name, email, password_hash, business_id, role, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 'sms-lead-no-login', 'bus_001', 'customer', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING;
                """, (cust_user_id, item["phone"], item["name"].split()[0], item["name"].split()[-1], f"{item['phone'].replace('+','')}@sms.lead"))

            tomorrow_10am_ct = now + timedelta(days=1)
            tomorrow_10am_ct = tomorrow_10am_ct.replace(hour=15, minute=0, second=0, microsecond=0)
            cur.execute("""
                INSERT INTO appointments (id, lead_id, user_id, business_id, start_time, end_time, status, notes, created_via, created_at, updated_at)
                VALUES (%s, %s, %s, 'bus_001', %s, %s, 'confirmed', %s, 'sms', %s, %s);
            """, (
                f"appt_{uuid.uuid4().hex[:12]}",
                lead_id,
                cust_user_id,
                tomorrow_10am_ct,
                tomorrow_10am_ct + timedelta(minutes=30),
                f"Phone appointment booked via SMS: {item['notes']}",
                times[1],
                times[1]
            ))

    conn.commit()
    cur.close()
    conn.close()
    print("Successfully seeded all 8 conversations with original leads!")


if __name__ == "__main__":
    seed()
