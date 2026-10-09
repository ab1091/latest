import dotenv, os, psycopg2, psycopg2.extras

dotenv.load_dotenv('crm-service/.env')
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

cur.execute("SELECT system_prompt, sms_prompt FROM ai_agents WHERE id = 'agent_b9674fd6e390'")
row = cur.fetchone()
old_sys = row['system_prompt']
old_sms = row['sms_prompt']

old_wrong_number_header = "2. WRONG PERSON / WRONG NUMBER (ZERO SALES PITCH):"

new_wrong_number_block = """2. WRONG PERSON / WRONG NUMBER (FUNKY & ADAPTIVE COMMUNICATION):
   - If someone says they are the wrong person, wrong number, or they don't know the person we addressed (e.g., 'You have the wrong number', 'wrong number', 'not Steven', 'who is this'):
   - Do NOT give a stiff, cold, boring, or robotic apology! Automatically adapt with a witty, charming, funky communication!
   - Lightheartedly acknowledge the mix-up with humor and good vibes (e.g. carrier pigeon got lost, wires got crossed, classic wrong number moment 😅).
   - Playfully and casually ask if the universe connected them for a reason (e.g. if they secretly need killer rates on insurance, or if you should vanish back into the digital sunset).
   - Examples of funky style:
     * "Haha oops! 😅 Classic wrong number moment, my apologies! But hey, since the universe brought us together, are you secretly looking for killer rates on insurance, or should I vanish back into the digital sunset? Either way, have an awesome day!"
     * "Ah man, looks like my carrier pigeon got the wrong zip code! 🕊️ So sorry about that! But hey, while I have you... did fate just connect you with an awesome insurance deal, or are you completely set? Hope you have a great one either way!"
   - Keep it short (1-2 sentences), funky, and low-pressure so it feels like a cool, witty human texting them."""

# Find section 2 and replace until section 3
import re
pattern = r"2\. WRONG PERSON / WRONG NUMBER \(ZERO SALES PITCH\):.*?(?=3\. ANNOYANCE)"
new_sys = re.sub(pattern, new_wrong_number_block + "\n\n", old_sys, flags=re.DOTALL)
new_sms = re.sub(pattern, new_wrong_number_block + "\n\n", old_sms, flags=re.DOTALL)

cur.execute("""
    UPDATE ai_agents 
    SET status = 'active', system_prompt = %s, sms_prompt = %s, updated_at = NOW() 
    WHERE id = 'agent_b9674fd6e390'
""", (new_sys, new_sms))

cur.execute("""
    UPDATE lead_configs 
    SET status = 'active', updated_at = NOW() 
    WHERE agent_id = 'agent_b9674fd6e390'
""")

conn.commit()
print("Successfully updated ai_agents and lead_configs to active with funky wrong number prompt!")
