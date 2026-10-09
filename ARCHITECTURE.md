# Architecture & Production Readiness

Technical reference for engineering. Covers what `README.md`/`RUNNING.md` don't:
data flow, deployment reality, and what's missing before a real production launch.
For local dev setup, tech stack table, and API endpoint list, see `README.md`.

`README.md` has been reconciled to match current state (Sendblue for SMS,
Gemini for SMS/RAG, Groq voice-call-only, the RAG knowledge base, and the
7-stage pipeline including Old Lead). This document goes deeper on the parts
`README.md` intentionally doesn't cover.

---

## 1. System Diagram

```
                         ┌─────────────────────┐
                         │   Browser / Client    │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  Frontend (Next.js)   │   Vercel (deployed)
                         │  app/api/[...proxy]/   │
                         └──────────┬───────────┘
                                    │ all /api/* forwarded
                                    ▼
                         ┌───────────────────────┐
                         │   ai-service (:8000)   │   ← local + ngrok tunnel today
                         │  SMS · Calls · RAG ·   │      (NOT deployed to cloud)
                         │  Auth · Scheduler      │
                         └──────────┬────────────┘
                     internal proxy │ (_CRM_PREFIXES whitelist)
                                    ▼
                         ┌───────────────────────┐
                         │  crm-service (:8001)   │   ← local only, never exposed
                         │  Leads · Workflows ·   │      directly, not even via ngrok
                         │  Agents · CRM data     │
                         └──────────┬────────────┘
                                    │
                         ┌──────────▼────────────┐
                         │  Postgres (aicrm) +    │   ← local Postgres today
                         │  Redis (pub/sub)       │
                         └────────────────────────┘

  External integrations (called from ai-service unless noted):
  ┌─────────┬──────────────────────────────────────────────┐
  │ Vapi     │ AI voice pipeline (STT+LLM+TTS orchestration) │
  │ Twilio   │ WhatsApp + underlying carrier for Vapi calls  │
  │ Sendblue │ SMS/iMessage sending + receiving              │
  │ Gemini   │ SMS replies, RAG-grounded answers, summaries  │
  │ Groq     │ In-call conversation LLM (voice only)         │
  │ Deepgram │ Speech-to-text for voice calls                │
  │ Google   │ OAuth login + Calendar sync                   │
  │ HubSpot  │ Optional CRM sync (webhooks)                  │
  │ Outlook  │ Optional calendar OAuth                       │
  └─────────┴──────────────────────────────────────────────┘
```

---

## 2. Service Responsibilities

**`ai-service`** (FastAPI, :8000) — owns every AI/telephony concern: SMS send/receive
(Sendblue + Twilio WhatsApp), voice calls (Vapi + legacy Twilio-native inbound),
the RAG knowledge base (`rag/`), the 30s callback scheduler that fires scheduled
SMS/call actions, and auth token issuance. It's also the sole internet-facing
backend — `crm-service` is reached only through its internal proxy.

**`crm-service`** (FastAPI, :8001) — owns lead/business data: leads CRUD, the
workflow automation engine (`core/workflow_engine.py`), AI agent configs,
lead-config tag-routing rules, conversations/messages storage, CRM settings,
billing, and the multi-tenant `business_id` scoping choke point
(`core/auth.py`). Never exposed directly — every request reaches it through
`ai-service`'s proxy.

**`frontend`** (Next.js 14, App Router) — single catch-all proxy
(`app/api/[...proxy]/route.ts`) forwards every `/api/*` call to
`NEXT_PUBLIC_BACKEND_URL` (ai-service). No direct calls to crm-service from
the browser, ever.

---

## 3. Data Flow Walkthroughs

**Lead lifecycle** — a single state machine (`core/lead_lifecycle.py`,
`transition_lead_status()`) is the only code path allowed to write
`leads.sub_status`/`stage`. Every trigger (SMS reply, AI qualification, call
outcome, appointment booking) fires a named event through this one function,
which validates the transition against an adjacency map, writes an audit row
to `lead_status_history`, and cascades into workflow/sequence pause logic.

**Workflow automation** — event-driven, not a pre-scheduled batch.
`core/workflow_engine.py`'s `_advance()` walks the graph synchronously for
instant nodes (move_stage, add_tag, notify_staff) and stops at the first
action node (send_sms/ai_call), inserting exactly one row into
`scheduled_callbacks` for "what happens next." The existing 30s poller in
`ai-service` picks it up when due — same executor for workflow steps as for
legacy sequences and callback-requested calls.

**SMS pipeline** — inbound webhook → lead lookup → `_get_agent_prompt()`
(tag/stage-matched agent, refuses to reply if no Lead Config rule matches) →
`retrieve_kb_context()` (RAG, category-matched to lead tags) appended to the
system prompt → last-20-messages history + new message sent to Gemini →
reply sent via Sendblue → saved to `messages` → lead transitioned to
`responded`.

**Call pipeline** — outbound calls go through Vapi, which uses either a
Twilio-backed number (supports international) or a Vapi-native number
(US-domestic only, free tier). Vapi handles STT (Deepgram) + LLM (Groq) + TTS
internally during the call; `ai-service`'s webhook (`vapi/router.py`)
receives the end-of-call report, extracts booking/outcome via Groq, and
notifies `crm-service` to advance the lead's status.

**RAG pipeline** — see inline docs in `ai-service/rag/`. Upload: extract text
(pypdf/python-docx) → clean (dedupe headers/footers, fix line-wraps) → chunk
(~900 chars, 120 overlap, paragraph-aware) → embed (local
`sentence-transformers/all-MiniLM-L6-v2`, 384-dim) → store in `kb_chunks`
(pgvector). Query: embed the lead's message → cosine-similarity search
scoped to `business_id` + category-matched-to-lead-tag → drop results below
`MIN_SIMILARITY=0.3` → inject top 3 into the agent's system prompt.

---

## 4. Multi-Tenancy Model

`business_id` scoping is the **only** tenant isolation mechanism — there is
no Postgres Row-Level Security. Every table that holds tenant data carries a
`business_id TEXT REFERENCES businesses(id) ON DELETE CASCADE` column and a
composite index; every query in both services filters on it, enforced at the
application layer via `get_business_id(request)` (implemented separately but
identically in `crm-service/core/auth.py` and `ai-service/core/auth_scope.py`).
`super_admin` is the sole exception — `business_id IS NULL` on their user
row, and they must select an agency via `X-Business-Id` header to act within
one. A bug in any query's `WHERE business_id = %s` clause is a cross-tenant
data leak with no second line of defense — worth a deliberate audit pass
before onboarding a second real paying customer.

---

## 5. Auth Model

JWT, shared-secret (`JWT_SECRET` must be byte-identical across both backend
`.env` files — `crm-service` validates tokens `ai-service` issues, and vice
versa for internal service-to-service calls like the SMS send-raw relay).
Access tokens expire in 24h, refresh in 30 days. Role hierarchy: `customer` <
`staff` < `admin` < `super_admin`, gated both server-side (`require_admin`,
`require_super_admin` dependencies) and client-side (`minRole` per nav item
in `SideNav.tsx` — UI gating only, not a security boundary on its own).

---

## 6. Current Deployment State

| Service | Where today | Production-ready? |
|---|---|---|
| Frontend | Vercel, auto-deploy on `development` push | Yes |
| `ai-service` | Local machine + ngrok tunnel | **No** |
| `crm-service` | Local machine only | **No** |
| Postgres | Local install | **No** |
| Redis | Local install | **No** |

**The backend has never been deployed to the cloud.** Every integration
(Vapi, Sendblue, Twilio webhooks) currently points at a free-tier ngrok URL
that changes every time the tunnel restarts — this was the root cause of two
separate real outages fixed this session (Vapi assistant's stale `server.url`,
Sendblue's stale webhook registration). Both now have partial mitigation
(`ai-service` re-syncs its own Vapi webhook URL on every startup via
`vapi/prompt.py`'s `push_prompt()`), but Sendblue's webhook registration is
still manual, and the fundamental problem — no permanent public URL — isn't
solved until the backend is actually deployed.

---

## 7. Production Readiness Gaps

Ranked roughly by how much it'll hurt if skipped:

1. **No cloud deployment of `ai-service`/`crm-service`.** Everything else on
   this list is secondary to this. Dockerfiles already exist for both
   (`python:3.11-slim`, non-root user, `EXPOSE`) and are unused for anything
   but local dev.
2. **`ngrok` dependency.** Free-tier URLs rotate on every restart. Both Vapi
   and Sendblue webhooks silently break when this happens; this already
   caused real incidents. Solved by (1).
3. **Multi-worker + local embedding model = OOM risk.** `main.py` spawns
   `workers = max(2, cpu_count())` outside `DEBUG` mode. Each worker
   independently lazy-loads the `sentence-transformers` model on first RAG
   call — this caused a real out-of-memory crash on the dev machine during
   testing. In production, either cap worker count for `ai-service`, or run
   the RAG embedding path as its own single-instance service.
4. **The 30s callback scheduler runs once per worker, no leader election.**
   Row-level locking (`UPDATE ... WHERE status='pending'`) prevents duplicate
   sends, so this isn't a correctness bug — but N workers means N redundant
   poll queries every 30 seconds for zero added throughput. Same fix as (3):
   either fewer workers, or isolate the scheduler into its own process.
5. **No CI/CD.** No `.github/workflows` or equivalent anywhere in the repo.
   Nothing runs tests, lints, or validates a migration file before merge.
6. **Health checks are liveness-only.** `/health` on both backends returns a
   static `{status: "healthy"}` with no DB/Redis connectivity check — a
   dead database connection pool would still report healthy.
7. **`docker-compose.yml` is stale.** Its Postgres service defaults to DB
   name `ai_schedular`; every other config (`.env.example`, `RUNNING.md`)
   uses `aicrm`. Needs reconciling before it's trustworthy for anything.
8. **Connection pool sizing doesn't account for worker count.** Each worker
   gets its own `ThreadedConnectionPool(2, 20)` — with N workers × 2
   services, worst case exceeds a typical managed Postgres's default
   `max_connections` (100) well before the app is under real load. Needs
   either lower per-worker caps or PgBouncer in front of Postgres.
9. **API keys live in plaintext `.env` files.** Fine for local dev; a real
   secrets manager (cloud provider's built-in one is enough) should own
   these before production credentials touch a deployed server.

---

## 8. Recommended Production Architecture

No hosting provider has been chosen yet. Recommendation, consistent with
what public exposure each service actually needs:

- **`ai-service`** — needs a public domain (webhooks from Vapi/Sendblue/
  Twilio must reach it). Container platform with autoscaling
  (Azure Container Apps or equivalent) — cap `workers` low per the OOM risk
  above, or split RAG into its own single-instance container.
- **`crm-service`** — internal-only. Same platform, but no public ingress —
  reachable only from `ai-service`'s network, matching its current
  "never exposed directly" design.
- **`frontend`** — stays on Vercel, already production-grade.
- **Postgres** — managed instance (the platform's managed Postgres, or
  equivalent) with `pgvector` available — confirm this before committing to
  a provider, since the RAG feature depends on it.
- **Redis** — managed instance, replacing the local install.
- Replace `ngrok` entirely with `ai-service`'s real domain in every webhook
  registration (Vapi assistant `server.url`, Sendblue account webhook,
  Twilio TwiML URLs).

---

## 9. Security Notes

- **Secrets:** move off `.env` files onto the hosting platform's secrets
  manager before any production credential is issued.
- **Telephony deliverability:** Twilio/Vapi calls carry a STIR/SHAKEN
  attestation level (`A`/`B`/`C`) tied to caller-ID trust. A new number
  starts at partial trust (`B`) and can get silently intercepted by
  carrier-side spam filtering — discovered this session while debugging a
  call that never audibly rang despite Twilio reporting it "completed."
  Worth flagging to whoever owns telephony compliance before scaling
  outbound call volume.
- **Tenant isolation** has no defense-in-depth beyond correct `WHERE
  business_id = %s` clauses (see §4) — worth a dedicated audit pass, not
  just incidental review, before a second paying customer's data sits next
  to the first's in the same tables.
