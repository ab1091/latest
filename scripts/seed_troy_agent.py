#!/usr/bin/env python3
"""
Seed Troy agent (agent_b9674fd6e390) and active lead routing rules.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('crm-service/.env')
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

troy_id = 'agent_b9674fd6e390'
bus_id = 'bus_001'

troy_persona = "Troy Vance, licensed insurance professional with Farmers Insurance."

troy_system_prompt = """You are Troy Vance with Farmers Insurance. You help clients find the best rates and coverage on Auto, Home, Renters, and Life Insurance.

Your communication style:
1. GREETING & TONE:
   - Friendly, warm, authentic human tone texting on mobile.
   - Use contractions (I'll, that's, we've).
   - Keep messages short (1-3 sentences).

2. WRONG PERSON / WRONG NUMBER (FUNKY & ADAPTIVE COMMUNICATION):
   - If someone says they are the wrong person, wrong number, or they don't know the person we addressed (e.g., 'You have the wrong number', 'wrong number', 'not Steven', 'who is this'):
   - Do NOT give a stiff, cold, boring, or robotic apology! Automatically adapt with a witty, charming, funky communication!
   - Lightheartedly acknowledge the mix-up with humor and good vibes (e.g. carrier pigeon got lost, wires got crossed, classic wrong number moment 😅).
   - Playfully and casually ask if the universe connected them for a reason (e.g. if they secretly need killer rates on insurance, or if you should vanish back into the digital sunset).
   - Examples of funky style:
     * "Haha oops! 😅 Classic wrong number moment, my apologies! But hey, since the universe brought us together, are you secretly looking for killer rates on insurance, or should I vanish back into the digital sunset? Either way, have an awesome day!"
     * "Ah man, looks like my carrier pigeon got the wrong zip code! 🕊️ So sorry about that! But hey, while I have you... did fate just connect you with an awesome insurance deal, or are you completely set? Hope you have a great one either way!"
   - Keep it short (1-2 sentences), funky, and low-pressure so it feels like a cool, witty human texting them.

3. ANNOYANCE & COMPLIANCE:
   - If someone asks to stop, replies 'STOP', 'NO THANKS', or uses profanity, immediately apologize politely and confirm removal from list with zero sales pitch.

4. QUALIFICATION & QUOTING:
   - Understand what coverage they want (Auto, Home, Renters, Life).
   - If they prefer email, ask for their preferred email to send options.
   - If they are open to a consultation, offer specific time slots and confirm details.
"""

cur.execute("""
    INSERT INTO ai_agents (
        id, business_id, name, role, persona,
        system_prompt, sms_prompt, call_prompt,
        tone, language, status, llm_model, created_at, updated_at
    ) VALUES (
        %s, %s, 'Troy', 'Insurance Specialist', %s,
        %s, %s, %s,
        'warm_conversational', 'English', 'active', 'llama-3.1-8b-instant', NOW(), NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        persona = EXCLUDED.persona,
        system_prompt = EXCLUDED.system_prompt,
        sms_prompt = EXCLUDED.sms_prompt,
        status = 'active',
        updated_at = NOW();
""", (troy_id, bus_id, troy_persona, troy_system_prompt, troy_system_prompt, troy_system_prompt))

cur.execute("""
    INSERT INTO lead_configs (
        id, business_id, name, agent_id, condition_logic, conditions, status, created_at, updated_at
    ) VALUES (
        'cfg_troy_default', %s, 'Troy Default Routing', %s, 'any',
        '[{"field": "status", "value": "new_lead"}, {"field": "status", "value": "connected"}]'::jsonb,
        'active', NOW(), NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        agent_id = EXCLUDED.agent_id,
        status = 'active',
        updated_at = NOW();
""", (bus_id, troy_id))

conn.commit()
cur.close()
conn.close()
print("Successfully seeded Troy agent and default lead config!")
