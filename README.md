# AllZone AI — Lead Automation Platform

An AI-powered lead automation platform for insurance agents. Automates WhatsApp/SMS outreach, AI voice calls, lead pipeline management, and follow-ups — all from one dashboard.

---

## What This Product Does

- **AI WhatsApp/SMS Messaging** — Lead added → AI sends personalized message instantly (Sendblue for SMS, Twilio for WhatsApp)
- **AI Voice Calls** — Outbound via Vapi (AI pipeline); a separate legacy Twilio-native path also exists for inbound
- **Lead CRM** — Pipeline tracking across 7 stages: new → old lead → connected → quoted → appointment scheduled → closed → dead
- **Visual Automation Builder** — Branching, multi-node workflows per pipeline stage (`/automation`), not a single fixed sequence
- **Multi-Agent Routing** — Multiple AI agents matched to leads by tags, each with its own System/Call/SMS prompts
- **RAG Knowledge Base** — Upload category-tagged company documents (PDF/DOCX/TXT); SMS and call agents automatically retrieve and cite the relevant content instead of guessing (`ai-service/rag/`)
- **Lead Scoring** — Computed on-write from SMS/call engagement, appointment activity, and quote status
- **Multi-tenant Platform** — `super_admin` manages multiple agencies from `/platform`; each agency is an isolated `admin`/`staff`/`customer` tenant
- **Call Transcripts** — Every voice call logged with outcome, duration, transcript

---

## Architecture

```
Browser (Next.js on Vercel)
        |
        | All /api/* calls
        v
Next.js Proxy (/app/api/[...proxy]/route.ts)
        |
        | HTTP
        v
AI Service (FastAPI — port 8000) ← ngrok tunnel (public URL)
        |
        | Internal HTTP proxy
        v
CRM Service (FastAPI — port 8001) ← localhost only, never exposed
        |
        v
PostgreSQL (port 5432) + Redis (port 6379)
```

**Key design decision:** Frontend only needs ONE public URL (`NEXT_PUBLIC_BACKEND_URL`).
All CRM calls are proxied through ai-service — only one ngrok tunnel needed.

```
External Services
  • Sendblue    — SMS sending + receiving
  • Twilio      — WhatsApp + underlying carrier for Vapi voice calls (Pakistan + US supported)
  • Vapi        — AI voice pipeline (STT + LLM + TTS), backed by a Twilio or Vapi-native number
  • Gemini      — LLM for SMS replies, RAG-grounded answers, summaries
  • Groq        — LLM for in-call conversation only (voice)
  • Google      — OAuth login + Calendar integration
  • ngrok       — Local webhook tunnel for ai-service
  • Vercel      — Frontend deployment
```

> **Not currently used:** ElevenLabs and HubSpot integrations exist in code
> (behind `VOICE_ENGINE=custom` and the optional CRM-sync webhook,
> respectively) but neither is wired into the active product today.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript |
| AI Service | FastAPI (Python), Uvicorn — port 8000 |
| CRM Service | FastAPI (Python), Uvicorn — port 8001 |
| Database | PostgreSQL 15 — database: `aicrm`, dedicated `aicrm_app` role, `pgvector` extension |
| Cache | Redis — activity feed pub/sub + voice sessions |
| LLM | Gemini (SMS, RAG) · Groq (in-call voice only) |
| RAG / Embeddings | Local `sentence-transformers` (`all-MiniLM-L6-v2`) + pgvector cosine search — no external embedding API |
| Voice AI | Vapi (outbound calls, dynamic prompts) — Twilio or Vapi-native number |
| Messaging | Sendblue (SMS) + Twilio (WhatsApp) |
| Auth | JWT (access 24h, refresh 30d) + bcrypt |
| Deployment | Vercel (frontend), ngrok + local (backend) |

---

## Project Structure

```
AI-CRM/
├── ai-service/                    ← FastAPI — port 8000, the only public-facing backend
│   ├── main.py                    ← App entry, rate limiting, _CRM_PREFIXES proxy whitelist
│   ├── core/
│   │   ├── config.py              ← All env variable loading
│   │   ├── db.py                  ← PostgreSQL connection pool (min=2, max=20)
│   │   ├── callback_scheduler.py  ← 30s poller: fires scheduled_callbacks (SMS/call actions)
│   │   ├── audio.py               ← ElevenLabs TTS + Redis phrase cache (unused voice engine path)
│   │   ├── calendar.py            ← Google Calendar integration
│   │   └── hubspot.py             ← HubSpot CRM sync (unused)
│   ├── rag/                       ← Knowledge base: upload, chunk, embed, retrieve
│   │   ├── document_extract.py    ← PDF/DOCX/TXT extraction + cleaning + chunking
│   │   ├── embeddings.py          ← Local embedding model + retrieve_kb_context()
│   │   └── router.py              ← Upload/list/delete endpoints
│   ├── api/
│   │   ├── auth/router.py         ← Login, signup, /me, Google OAuth
│   │   ├── admin/router.py        ← Business settings, user management
│   │   ├── appointments/router.py ← Appointment CRUD
│   │   ├── calls/router.py        ← Outbound call trigger + call history
│   │   ├── dialer/router.py       ← Outbound call initiation
│   │   ├── sms/router.py          ← Inbound/outbound SMS (Sendblue) + RAG-grounded AI replies
│   │   ├── emergency_blocks/      ← Provider availability blocks
│   │   ├── holidays/              ← Business holiday calendar
│   │   ├── integrations/          ← Google/Outlook OAuth connections
│   │   └── reminders/             ← Appointment reminder jobs
│   ├── vapi/router.py             ← Vapi assistant-request + call-outcome webhooks
│   ├── voice/router.py            ← Legacy Twilio-native TwiML voice bot (inbound only)
│   └── crm/router.py              ← CRM stats + calls proxy
│
├── crm-service/                   ← FastAPI — port 8001, localhost only, never exposed directly
│   ├── main.py                    ← App entry + follow-up scheduler
│   ├── core/
│   │   ├── auth.py                ← JWT validation, bcrypt, get_business_id()/get_scope() tenancy choke point
│   │   ├── workflow_engine.py     ← Branching automation engine (enroll/advance/wait-collapsing)
│   │   ├── lead_lifecycle.py      ← Stage transitions, auto-enrollment hook
│   │   └── config.py / db.py
│   ├── routers/
│   │   ├── leads.py               ← Lead CRUD + CSV/Excel import (bulk SMS lives in ai-service's sms/router.py)
│   │   ├── agents.py              ← AI agent CRUD (name, persona, system/call/sms prompts, tone, language)
│   │   ├── conversations.py       ← Conversations + messages
│   │   ├── sms.py                 ← Kept for import compatibility only — its endpoints aren't in ai-service's `_CRM_PREFIXES` whitelist, so they're unreachable; real SMS traffic goes through `ai-service/api/sms/router.py`
│   │   ├── lead_configs.py        ← Tag-based routing rules
│   │   ├── lead_sequences.py      ← Legacy fixed-sequence engine (superseded by workflows.py)
│   │   ├── workflows.py           ← Branching automation CRUD + templates + graph save
│   │   ├── crm_settings.py        ← Stages/assignment/scoring/communication rules
│   │   ├── notes_tasks.py         ← Lead notes + tasks
│   │   ├── activity_feed.py       ← Live activity feed (SSE via ai-service)
│   │   ├── platform.py            ← super_admin cross-agency views
│   │   └── billing.py             ← Plans/subscriptions/invoices
│   └── scripts/
│       ├── seed_workflow_templates.py  ← 7 starter automation templates
│       ├── migrate_sequences_to_workflows.py
│       └── seed_test_accounts.py       ← Creates/resets the 3 test logins (see RUNNING.md)
│
├── frontend/                      ← Next.js 14 (App Router), TypeScript
│   ├── app/
│   │   ├── api/[...proxy]/        ← Catch-all proxy to ai-service (SSE-safe, unbuffered)
│   │   ├── dashboard/, leads/[leadId]/  ← Unified lead workspace (single page, not a drawer)
│   │   ├── automation/[workflowId]/    ← Drag-and-drop workflow builder (React Flow)
│   │   ├── agents/, conversations/, calls/, calendar/
│   │   ├── crm-settings/          ← Stages/assignment/scoring/communication config
│   │   ├── billing/, reports/, analytics/, users/
│   │   ├── platform/              ← super_admin agency list + cross-agency analytics
│   │   └── user/                  ← Customer views (role: customer)
│   ├── components/
│   │   ├── SideNav/                ← Role-gated nav (minRole per item)
│   │   └── WorkflowBuilder/        ← Canvas + per-node-type components (Kanban is a viewMode toggle inside leads/page.tsx, not yet its own component)
│   └── contexts/
│       ├── AuthContext.tsx         ← JWT session, user role, login/logout
│       └── ThemeContext.tsx        ← Dark/light mode
│
└── database/
    ├── schema.pg.sql              ← Base PostgreSQL schema
    └── migrations/                ← 001–029, applied in order — see RUNNING.md § Database structure
```

---

## Role-Based Access

Four tiers, ranked `customer` < `staff` < `admin` < `super_admin`:

| Role | Dashboard | Scope |
|------|-----------|-------|
| `super_admin` | `/platform` | Cross-agency — no `business_id`; must select an agency ("Manage" on `/platform`) to drill into any business-scoped page |
| `admin` | `/dashboard` | Full access within their own agency (`business_id`) |
| `staff` | `/dashboard` | Same pages as `admin` within their own agency |
| `customer` | `/user/dashboard` | Only `/user/*` pages, own records only |

Nav gating lives in `frontend/components/SideNav/SideNav.tsx` — every admin page has a role guard, customers are redirected to their `/user/*` equivalent, and a `super_admin` with no agency selected gets business-scoped nav items silently pointed back at `/platform` (by design — pick "Manage" on an agency first).

---

## Database Schema

41 tables across tenancy/auth, leads/lifecycle, the workflow automation engine,
messaging, voice/appointments, the RAG knowledge base, billing, and activity
feed — see **[RUNNING.md § Database structure](RUNNING.md#database-structure)**
for the full, currently-accurate table-by-domain map. Highlights:

| Table | Purpose |
|---|---|
| `businesses` | Multi-tenant agency records |
| `users` | Accounts — roles: `customer` < `staff` < `admin` < `super_admin` |
| `leads` | CRM contacts with 7-stage pipeline, tags, preferred channel, score |
| `kb_documents` / `kb_chunks` | RAG knowledge base — uploaded documents + their embedded, category-tagged chunks |
| `ai_agents` | Agent configs (name, persona, system/call/sms prompts, tone, language) |
| `workflows` / `workflow_nodes` / `workflow_edges` | Branching automation graphs (current engine) |
| `lead_workflow_enrollments` / `workflow_node_runs` | Per-lead automation state + audit trail |
| `scheduled_callbacks` | Shared just-in-time executor queue for SMS/call actions |
| `conversations` / `messages` | One conversation per lead per channel; all messages |
| `voice_calls` | Call logs — transcript, outcome, duration |

---

## API Endpoints

### Auth — ai-service
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Email + password → JWT |
| POST | `/api/auth/signup` | Register new user |
| GET | `/api/auth/me` | Current user profile |
| GET | `/api/auth/google` | Google OAuth start |

### Leads — crm-service
| Method | Path | Description |
|---|---|---|
| GET | `/api/leads` | List leads |
| POST | `/api/leads` | Create lead — auto-enrolls into matching workflows, no message sent outside a workflow's own steps |
| PATCH | `/api/leads/:id` | Update lead |
| DELETE | `/api/leads/:id` | Delete lead |
| POST | `/api/leads/import` | Bulk CSV/Excel import |

### Agents — crm-service
| Method | Path | Description |
|---|---|---|
| GET | `/api/agents` | List AI agents |
| POST | `/api/agents` | Create agent |
| PATCH | `/api/agents/:id` | Update agent |
| DELETE | `/api/agents/:id` | Delete agent |

### Conversations — crm-service
| Method | Path | Description |
|---|---|---|
| GET | `/api/conversations` | List conversations |
| POST | `/api/conversations` | Start/reuse conversation |
| GET | `/api/conversations/:id/messages` | Get messages |
| POST | `/api/conversations/:id/messages` | Send message |
| PATCH | `/api/conversations/:id/toggle-ai` | Toggle AI auto-reply |

### Voice & Calls — ai-service
| Method | Path | Description |
|---|---|---|
| POST | `/api/dialer/call` | Trigger outbound call |
| GET | `/api/calls` | Call history |
| POST | `/api/vapi/webhook` | Vapi call event webhook (assistant-request + call-outcome) |

### Automation — crm-service
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/workflows` | List/create branching automation workflows |
| GET | `/api/workflows/templates` | Starter template library |
| POST | `/api/workflows/{id}/duplicate` | Clone a template into a business-owned draft |
| PUT | `/api/workflows/{id}/graph` | Save the full node/edge graph |
| POST | `/api/workflows/enrollments/{id}/advance` | Advance an enrollment (called by the callback poller/webhooks) |

### CRM Settings / Notes & Tasks / Platform / Billing — crm-service
| Method | Path | Description |
|---|---|---|
| GET/PATCH | `/api/crm-settings/*` | Stages, assignment rules, scoring weights, communication rules |
| GET/POST | `/api/notes`, `/api/tasks` | Lead notes and tasks |
| GET | `/api/activity-feed` | Paginated activity feed (SSE stream lives at ai-service) |
| GET | `/api/platform/agencies` | `super_admin`-only cross-agency rollup |
| GET/PATCH | `/api/billing/plans`, `/api/billing/subscription` | Plans + current subscription |

Every crm-service router prefix above must be present in `ai-service/main.py`'s
`_CRM_PREFIXES` whitelist or the frontend proxy can't reach it — see
`RUNNING.md` for the current set.

---

## Environment Variables

Every service has a maintained, credential-free template — copy and fill in
real values locally, never commit the result (`.gitignore` blocks
`.env`/`.env.*` everywhere except the `*.example` files themselves):

```bash
cp ai-service/.env.example ai-service/.env
cp crm-service/.env.example crm-service/.env
cp frontend/.env.example frontend/.env.local
```

`DATABASE_URL` must point both backend services at the same database, and
`JWT_SECRET` must match between them (crm-service verifies JWTs issued by
ai-service). See each `.env.example` file for the full variable list
(Twilio, Vapi, Groq/Gemini, Google/Outlook OAuth) — that's the source of
truth; this README doesn't duplicate it so the two can't drift apart again.

**For Vercel deployment:** set `NEXT_PUBLIC_BACKEND_URL` to your public
ai-service URL (ngrok tunnel or deployed backend).

---

## How to Run Locally

Full setup (migrations, `.env` files, dependency install) is documented in
**[RUNNING.md](RUNNING.md)**. Once set up, one command starts all three
services:

```bash
./run.sh
```

This runs crm-service (:8001), ai-service (:8000), and the frontend (:3000)
in the foreground, health-checks each on startup, and cleans up all three
(plus any stray uvicorn workers) on Ctrl+C. Logs land in `./logs/*.log`.

To run services individually instead, or for the manual dependency-install
steps, see `RUNNING.md`.

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

If you need real inbound SMS/calls reaching your machine, you'll also need
an ngrok tunnel pointed at ai-service (:8000) — see `RUNNING.md` for the
webhook registration details.

---

## Test Accounts

There are no default/seeded production credentials in this repo. For local
QA there are three dev-only test logins (`@allzonetech.local`), created and
reset via a script rather than committed anywhere in plaintext — see
**[RUNNING.md § Test accounts](RUNNING.md#test-accounts)** for the current
emails/passwords and how to regenerate them:

```bash
cd crm-service && ./venv/bin/python3 scripts/seed_test_accounts.py
```

Real production accounts (e.g. `admin@allzonetech.com`) are provisioned
directly against the database and their credentials are never written to
this repo, any doc, or any script.

---

## Deployment

| Service | Where | Notes |
|---------|-------|-------|
| Frontend | Vercel | Auto-deploy on push to `development` branch |
| AI Service | ngrok + local | Run `python main.py` + ngrok tunnel |
| CRM Service | Local only | Run `python main.py`, never exposed directly |
| Database | Local PostgreSQL | Must be running locally |

**Production path:** Move ai-service + crm-service to a VPS (Railway, Render, EC2) when ready for full cloud deployment.

---

## Key Technical Decisions

| Decision | Why |
|----------|-----|
| Single ngrok URL | One public backend URL — ai-service proxies CRM calls internally |
| Two FastAPI services | ai-service owns voice + auth, crm-service owns lead data |
| Multi-worker uvicorn | Handles concurrency without full async migration |
| Redis pub/sub | Powers the live activity feed (SSE) + voice sessions |
| Rate limiting middleware | 100 req/min per IP, stale IPs purged every 5 min |
| Pakistan calling enabled | Twilio geo-permissions: High-Risk + Low-Risk Pakistan checked |
| Role-based routing | super_admin → /platform, admin/staff → /dashboard, customer → /user/dashboard |

---

## Third-Party Services

| Service | Used For |
|---------|----------|
| Sendblue | SMS sending + receiving |
| Twilio | WhatsApp (sandbox: `whatsapp:+14155238886`) + underlying carrier for Vapi voice calls |
| Vapi | AI voice pipeline (STT + LLM + TTS) |
| Gemini | LLM for SMS replies, RAG-grounded answers, summaries |
| Groq | LLM for in-call voice conversation only |
| Google | OAuth login + Calendar API |

Not currently used: **ElevenLabs**, **HubSpot** (see note under Architecture).
