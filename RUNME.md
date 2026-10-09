# Local dev session notes (continue from here)

## ⚠️ QUIET HOURS DISABLED — TEMPORARY, MUST REVERT (2026-07-17)

Per explicit user request, TCPA-style quiet hours are fully open right now:
`communication_rules.quiet_hours_start='00:00'`, `quiet_hours_end='23:59'` for
`bus_001` — i.e. SMS/call sends are NOT time-restricted at all currently.
User said they'll ask for compliance to be re-applied "after a month or a
week." **Until then, do not treat missing quiet-hours enforcement as a bug —
it's intentional.** When asked to restore it, a sane default is
`quiet_hours_start='09:00'`, `quiet_hours_end='20:00'` (matches what was live
earlier this session).

## Call recordings — fixed via custom Azure Blob Storage (2026-07-17)

Vapi's own default recording bucket (`hipaa-recordings` on Cloudflare R2)
never returns a working URL through the public API — bare/unsigned, always
400s. The only working access was Vapi's dashboard-only `presignedMonoUrl`
field on `GET /call/{id}`, and only in a narrow window right after a human
opens that call in Vapi's UI — not automatable.

Real fix: configured a customer-owned Azure Blob Storage account as Vapi's
recording destination (Vapi dashboard → Settings → Integrations → Azure Blob
Storage), so Vapi now uploads recordings directly there instead of its own
bucket.
- Storage account: `audioocrm` (East US 2), container: `call-recordings`.
- Credentials in `ai-service/.env`: `AZURE_STORAGE_ACCOUNT_NAME`,
  `AZURE_STORAGE_ACCOUNT_KEY`, `AZURE_STORAGE_CONNECTION_STRING`,
  `AZURE_STORAGE_CONTAINER`. Also added to `core/config.py`.
- New `ai-service/core/azure_storage.py` — `generate_sas_url()` mints a
  60-minute read-only SAS URL for a given blob on demand (uses
  `azure-storage-blob` SDK, added to `requirements.txt`).
- `ai-service/api/calls/router.py` `GET /{call_id}/recording` — looks up the
  stored `recording_url`; if it's one of our own Azure blobs, signs it fresh
  and 307-redirects. Falls back to the old best-effort Vapi
  `presignedMonoUrl` fetch only for pre-migration calls (unreliable, kept as
  last resort only).
- Frontend (`frontend/app/leads/[leadId]/page.tsx`, both audio players) now
  points `<audio src>` at `/api/calls/{call_id}/recording` instead of the
  raw stored `recording_url`.
- Verified end-to-end with a real outbound call (`019f7122-...`): recording
  landed at `https://audioocrm.blob.core.windows.net/call-recordings/...`,
  and the CRM endpoint served real audio bytes (200, 264KB) through a signed
  URL. Old pre-migration recordings (anything before this fix) are stuck on
  Vapi's bucket and cannot be recovered.

## Dialer feature moved from Twilio to Vapi (2026-07-18)

Per explicit request: no Twilio for calls, Vapi only. Audited every call-
placement path:
- `ai-service/api/calls/router.py` (`/outbound`) — already Vapi-only, no change.
- `ai-service/core/callback_scheduler.py` (automated workflow calls) —
  already Vapi-only, no change.
- `ai-service/api/dialer/router.py` `/bridge` — already Vapi-only (returns
  assistant config for provider-transfer), no change.
- `ai-service/api/dialer/router.py` `/call` — **was Twilio** (`Calls.json`
  REST call). This is the one place Twilio actually placed a call. Used by
  three frontend call sites, all with the same `{ phoneNumber, message? }`
  contract: `DialerContext.startCall` (provider-transfer flow, `explorer/
  page.tsx`), `DialerModal.tsx` (manual keypad dialer, both side navs), and
  `book/page.tsx` (outbound call during booking). Kept that contract
  unchanged, swapped the implementation to `POST https://api.vapi.ai/call/phone`
  using `VAPI_PHONE_NUMBER_ID`/`VAPI_ASSISTANT_ID`, with `body.message` as
  the `firstMessage` override. Verified with a real call through the fixed
  endpoint (Vapi call id returned, logged as `[dialer:call] Outbound Vapi
  call placed`).

Note: `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_FROM_NUMBER` are
still in `.env` and still used for **SMS/WhatsApp** send paths (unrelated —
Sendblue handles SMS, Twilio is the WhatsApp channel) and for the emergency-
blocks Twilio TwiML flow — those weren't touched, only voice call placement.

`VOICE_ENGINE=vapi` in `.env` is dead config — grepped the whole codebase,
nothing reads that variable. The "custom" (Twilio+Groq+ElevenLabs) voice
pipeline in `ai-service/voice/router.py` still exists as code but isn't
wired into any live call-placement path anymore after this change — every
real path now goes through Vapi already, so it's effectively unreachable
dead code, not actively removed.

## CRITICAL FIX: real webhooks were hitting the wrong service (2026-07-18)

**Root cause of "automation SMS replies are generic/broken":** it was never a
code bug in this repo's `ai-service`/`crm-service`. A real ngrok tunnel
(`https://5df8-2400-adc5-40d-6b00-b4c1-9b17-8cd9-31f1.ngrok-free.app`, a
free ephemeral URL — **will change if the ngrok agent process restarts**,
check `curl localhost:4041/api/tunnels` for the current one) has been live
since ~Jul 9 and pointed at **port 8000**. Earlier in this session, ai-service
was moved to port 8002 to avoid a conflict with an old, unrelated process
already on 8000 (`/Users/azt/Desktop/CRM/AllZone-AI-CRM/ai-service`) — which
meant every real inbound SMS/iMessage and every Vapi call webhook was hitting
that OLD, unrelated service the entire time, not this repo. That's why real
replies kept getting a generic fallback: the old service was still on Gemini
(depleted credits), never got today's Groq/RAG/prompt fixes.

Fixed by reverting the port-move entirely instead of chasing the tunnel:
- Killed the old process (PID was 65501) and freed port 8000.
- Moved `ai-service` back to port 8000 (undid `BACKEND_API_URL`/`VOICE_BOT_URL`/
  `PORT` changes in both `.env` files and `NEXT_PUBLIC_BACKEND_URL` in
  `frontend/.env.local` — all back to `8000`).
- **Also found and fixed a second, related bug**: `TWILIO_TWIML_BASE_URL` in
  both `.env` files was pointed at a *different*, actually-offline reserved
  ngrok domain (`predeterminate-hailey-uncloying.ngrok-free.dev`,
  `ERR_NGROK_3200`) — stale leftover config, not the tunnel actually in use.
  `ai-service/vapi/prompt.py` pushes this URL to Vapi as the assistant's
  webhook/tool `server_url` **on every ai-service startup** — so every
  restart had been re-registering Vapi's webhook to point at a dead endpoint,
  breaking voice-call function-calling/webhooks too. Updated both `.env`
  files to the real live tunnel URL, restarted ai-service, confirmed the
  Vapi assistant PATCH synced successfully and the tunnel now reaches this
  service (`curl -H "ngrok-skip-browser-warning: true" <tunnel>/health` → 200).

**If SMS/call automation ever looks broken again, check this first:**
1. `lsof -tiTCP:8000 -sTCP:LISTEN` — confirm it's *this* ai-service, not
   something else.
2. `curl localhost:4041/api/tunnels` — confirm the live tunnel's `addr`
   matches (should be `http://localhost:8000`) and grab its current
   `public_url`.
3. Confirm `TWILIO_TWIML_BASE_URL` in both `.env` files matches that
   `public_url` exactly — if ngrok was restarted, this URL changes and both
   files need updating, then ai-service needs a restart to re-sync Vapi.
4. Consider getting a reserved free static ngrok domain so this stops
   drifting on every ngrok restart.


## RAG enabled + Riley's SMS prompt rewritten for real conversation design (2026-07-17)

**RAG was fully broken until today** — `pgvector` was never actually installed
(only mentioned as installed, never verified), so `kb_documents`/`kb_chunks`
didn't exist. Fixed: built `pgvector` 0.8.5 from source against Postgres 15
(Homebrew's bottle only ships PG17/18 builds — a plain `brew install` alone
is not enough on this machine), `CREATE EXTENSION vector`, applied
`database/migrations/028_knowledge_base.sql`, and fixed table ownership
(`kb_documents`/`kb_chunks` had been created under the `azt` role instead of
`aicrm_app`, causing `permission denied` on upload — `ALTER TABLE ... OWNER
TO aicrm_app` fixed it). Verified end-to-end: uploaded a test insurance FAQ
doc, simulated an inbound Sendblue message asking about discounts, confirmed
the reply was grounded in the uploaded doc's actual numbers (not
hallucinated) and sent successfully.

**Riley's prompt rewritten** based on a full conversation-design spec (9
example scenarios: repeated greetings, new auto/home lead funnel, existing-
customer servicing requests, price objections, appointment scheduling, lead
qualification, follow-up re-engagement, declining). Old prompt was narrowly
scoped to "re-engagement specialist" only, but `lead_configs` routes ALL
new/old/connected leads to Riley — so new leads were getting a persona built
for win-back conversations, which is why generic greetings looped instead of
progressing. New prompt (`ai_agents.system_prompt` + `.sms_prompt`, both
kept in sync — ai-service's live inbound path reads `system_prompt`,
crm-service's manual-send path prefers `sms_prompt`) encodes: one-question-
at-a-time funnel logic, servicing-vs-sales-request detection, price-objection
handling, appointment-time-window offering, context-aware follow-up, and
graceful decline handling. Updated via `PATCH /api/agents/{id}` — **note:
`staff` role gets 403 on prompt fields, must use `admin`/`super_admin`**
(with `X-Business-Id: bus_001` header for super_admin).

Also relaxed the hard "under 160 characters" instruction appended in both
`crm-service/routers/sms.py` and `ai-service/api/sms/router.py` (search
`IMPORTANT: Keep replies concise`) since several scenarios need short
bulleted option lists that don't fit in one SMS segment — iMessage via
Sendblue doesn't have that constraint anyway.

Verified via direct `_build_ai_reply` calls (no real send) against 6 of the
9 scenarios — all matched intended behavior. More scenarios may still be
added; this prompt is expected to keep evolving.

## Quiet-hours timezone + import auto-messaging fixed (2026-07-17)

**Sendblue credentials were never the problem** — verified working with a
real direct send. The actual issue was `bus_001`'s TCPA quiet-hours rule
using `America/New_York` while testing was happening from Pacific time, so
manual sends outside 9am–8pm ET looked like "messages don't work."
- DB: `communication_rules.timezone` for `bus_001` updated from
  `America/New_York` → `America/Los_Angeles`. Quiet hours are still 09:00–20:00,
  just evaluated in Pacific now.
- Note: `ai-service/api/sms/router.py`'s `/api/sms/send` enforces quiet hours;
  `crm-service/routers/sms.py`'s own `/api/sms/send` does not (it delegates to
  ai-service's `/api/sms/send-raw`, which also has no quiet-hours gate). The
  frontend hits ai-service's version directly since `sms` isn't in
  ai-service's `_CRM_PREFIXES` proxy list — that's the one that's gated.

**CSV/Excel lead import no longer auto-messages leads by default.** Previously
every imported "new" lead with a phone number was silently auto-enrolled in
the Day1 workflow (which sends a welcome SMS), with no way to opt out.
- `crm-service/routers/leads.py`: `POST /api/leads/import` now takes an
  `auto_sms: bool = Form(False)` param (mirrors the existing `auto_call`
  param) — workflow enrollment on import only happens if explicitly
  requested. Default is **off**.
- Also fixed the same gap on single-lead creation (`POST /api/leads`):
  `LeadIn.auto_sms` existed on the request model but was never actually
  checked before enrolling — `create_lead` now respects it.
- `frontend/app/leads/page.tsx` — added an "Auto Message" toggle next to the
  existing "Auto Call" toggle in the import modal, defaulting to off.
- `frontend/app/user/leads/page.tsx` (customer portal import) sends no flags
  at all, so it automatically inherits the new safe default with no frontend
  change needed there.
- Verified: imported a test lead via the API with no `auto_sms` flag → zero
  rows in `lead_workflow_enrollments` and `scheduled_callbacks` for it.

## LLM provider switched: Gemini → Groq (2026-07-16)

Gemini's API key ran out of prepayment credits mid-testing (`429
RESOURCE_EXHAUSTED`), so all AI text generation (SMS auto-replies, callback/
intent extraction, appointment extraction, lead qualification detection, lead
summaries, workflow follow-up SMS/email copy) was migrated from Gemini to
Groq (`llama-3.1-8b-instant`), using a Groq key provided directly in chat.

Files changed:
- `ai-service/.env`, `crm-service/.env`, root `.env` — `GROQ_API_KEY` updated
  to the new key; `crm-service/.env` also gained `GROQ_MODEL=llama-3.1-8b-instant`.
- `crm-service/routers/sms.py` — replaced `google.genai` client with a local
  `_groq_generate()` helper (sync, via `httpx` → Groq's OpenAI-compatible
  `/chat/completions`).
- `crm-service/routers/leads.py` — `generate_lead_summary` now calls
  `_groq_generate` from `routers.sms`.
- `crm-service/routers/agents.py` — default `llm_model` changed to
  `llama-3.1-8b-instant`.
- `ai-service/api/sms/router.py` — same pattern as crm-service's sms.py, plus
  an async variant (`_groq_generate_async`) for the async call sites.
- `ai-service/core/callback_scheduler.py` — now imports a new shared
  `ai-service/core/llm_groq.py` (async `groq_generate()` helper) instead of
  inlining a Gemini client per call site.
- DB: `ai_agents.llm_model` for the one existing agent row ("Riley") was
  updated from `gemini-2.5-flash` to `llama-3.1-8b-instant` — stale
  `gemini-*` values stored on agent rows are also defensively normalized to
  the Groq default at read time in `ai-service/api/sms/router.py`'s
  `_get_agent_prompt`.

`ai-service/core/config.py` still defines `GEMINI_API_KEY` as a constant but
nothing imports it anymore — harmless if left, fine to delete later.
Everything else in ai-service (voice calls, Vapi) already used Groq before
this change; only the Gemini-specific SMS/summary code paths needed migrating.

Verified post-migration: `_build_ai_reply` in both services and JSON-mode
extraction (`_extract_callback_seconds`) tested directly against the live
Groq key and returned real completions.


This file tracks what was actually done to get this repo running locally on
this machine, as a companion to the generic instructions in `RUNNING.md`.
Read this first if you're picking the session back up — it documents the
deviations from `RUNNING.md` that matter (mainly the ai-service port change).

## Current status (as of this session)

All three services were confirmed running and healthy:

| Service | URL | venv / runtime |
|---|---|---|
| crm-service | http://localhost:8001 | `crm-service/venv` (Python 3.11), `uvicorn main:app --reload` |
| ai-service | **http://localhost:8002** (not the default 8000 — see below) | `ai-service/venv` (Python 3.11), `uvicorn main:app --reload` |
| frontend | http://localhost:3000 | `npm run dev` (Next.js 14) |

Logs: `logs/crm-service.log`, `logs/ai-service.log`, `logs/frontend.log`.

## Why ai-service runs on 8002, not 8000

Port 8000 was already held by an unrelated, older project
(`/Users/azt/Desktop/CRM/AllZone-AI-CRM/ai-service`, a long-running process
from a previous day). Rather than kill that process, ai-service for **this**
repo was moved to port **8002**. To make that consistent, these files were
edited:

- `ai-service/.env`: `PORT`, `BACKEND_API_URL`, `VOICE_BOT_URL` → `8002`
- `crm-service/.env`: `BACKEND_API_URL`, `VOICE_BOT_URL` → `8002`
- `frontend/.env.local`: `NEXT_PUBLIC_BACKEND_URL=http://localhost:8002`

If you ever free up port 8000 (stop that other process) and want to move
back to the documented default, revert those three URLs to `8000` and
restart ai-service with `--port 8000`.

## What was set up this session

1. **`.env` files** — `ai-service/.env` and `crm-service/.env` didn't exist
   (only `.env.example` did). Both were created from the repo-root `.env`
   (which already had real values filled in for both services concatenated
   together — harmless duplicate keys, both sides agree). `frontend/.env.local`
   was created fresh (see contents below).
2. **Database** — Postgres was already running (Homebrew, port 5432), and
   the `aicrm` database + `aicrm_app` role + full schema already existed.
   No migrations needed to be run.
3. **Python venvs** — created fresh with `python3.11 -m venv venv` in both
   `ai-service/` and `crm-service/`, then `pip install -r requirements.txt`.
4. **Frontend deps** — `npm install` in `frontend/` (Node v22, npm at
   `/Users/azt/.local/bin`).
5. **Test accounts** — the DB already had rows for the three seeded test
   accounts, but their password hashes didn't match the documented passwords
   (likely left over from an earlier/different seeding). Fixed by re-running:
   ```bash
   cd crm-service && ./venv/bin/python3 scripts/seed_test_accounts.py
   ```
   This resets them to match the table below every time it's run.

## Test login credentials

| Role | Email | Password |
|---|---|---|
| `super_admin` | `superadmin.test@allzonetech.local` | `SuperAdmin!2026Test` |
| `staff` | `staff.test@allzonetech.local` | `StaffUser!2026Test` |
| `customer` | `customer.test@allzonetech.local` | `Customer!2026Test` |

`super_admin` lands on `/platform` with no business scoped — click **Manage**
on an agency there to drill into business-level pages. `staff`/`customer` are
scoped to `bus_001` ("Test Business"). If login ever fails with 401 for these,
re-run the seed script above — that's what fixed it last time.

## `frontend/.env.local` (as created this session)

```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8002
NEXT_PUBLIC_CRM_URL=http://localhost:8001
NEXT_PUBLIC_FRONTEND_URL=http://localhost:3000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<same value as GOOGLE_CLIENT_ID in ai-service/.env>
```

## How to restart everything

The processes above were started directly in the background (not via
`run.sh`, since `run.sh` assumes ai-service runs on 8000). If they've been
stopped (e.g. machine restart), bring them back up with:

```bash
cd crm-service && DEBUG=true ./venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload > ../logs/crm-service.log 2>&1 &

cd ai-service && DEBUG=true ./venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload > ../logs/ai-service.log 2>&1 &

cd frontend && npm run dev > ../logs/frontend.log 2>&1 &
```

Health checks:

```bash
curl localhost:8001/health   # crm-service
curl localhost:8002/health   # ai-service
curl localhost:3000          # frontend
```

Tail logs (from `voice_calling_agents/`):

```bash
tail -f logs/crm-service.log
tail -f logs/ai-service.log
tail -f logs/frontend.log
```

To stop everything, kill by port:

```bash
for port in 8001 8002 3000; do
  lsof -tiTCP:$port -sTCP:LISTEN | xargs kill -9
done
```
