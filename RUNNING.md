# Running AI-CRM locally

Three services: **crm-service** (FastAPI, :8001), **ai-service** (FastAPI, :8000),
**frontend** (Next.js, :3000). All talk to one shared Postgres database; Redis
is provisioned but not required for core functionality to run.

## Prerequisites

- Postgres 15
- Redis (optional today; reserved for the live activity feed)
- Python 3.11 (each service's `venv/` in this repo was built for 3.11 — a
  different major version, e.g. 3.14, will not run the committed venv as-is
  and you'll need to rebuild it, see below)
- Node 20+

## 1. Database

The app runs under its own dedicated Postgres role and database — not a
personal/superuser OS account. Create both, then apply the schema + every
migration in order:

```bash
createuser --pwprompt aicrm_app          # set a real password when prompted
createdb aicrm --owner=aicrm_app
psql -d aicrm -f database/schema.pg.sql
for f in database/migrations/*.sql; do psql -d aicrm -f "$f"; done
```

Put the resulting connection string in both `ai-service/.env` and
`crm-service/.env`'s `DATABASE_URL`:

```
DATABASE_URL=postgresql://aicrm_app:<the-password-you-set>@localhost:5432/aicrm
```

`aicrm_app` only needs ownership of the `aicrm` database — it does not need
`SUPERUSER`, `CREATEDB`, or `CREATEROLE`. Earlier local setups used a
personal macOS user account directly as the Postgres role; if you're
migrating one of those, dump/restore the data across rather than re-running
the app against the old role:

```bash
pg_dump -Fc -d <old_db> -f old.dump
pg_restore -d aicrm --no-owner --role=aicrm_app old.dump
```

## 2. Environment files

Copy each example file and fill in real values (Twilio, Vapi, OpenAI/Gemini,
Google/Outlook OAuth as needed — not all integrations are required to run
the core CRM):

```bash
cp ai-service/.env.example ai-service/.env
cp crm-service/.env.example crm-service/.env
cp frontend/.env.example frontend/.env.local
```

Both `ai-service/.env` and `crm-service/.env` must point `DATABASE_URL` at
the **same** database — they share it. `JWT_SECRET` must also match between
the two, since crm-service verifies JWTs issued by ai-service's `/api/auth`.

If you want real inbound SMS/calls to reach your machine in dev, `ai-service`
also needs `TWILIO_TWIML_BASE_URL` set to a public HTTPS URL (e.g. an ngrok
tunnel pointed at port 8000), and that same URL registered as the webhook on
your Twilio number / Vapi phone number.

## 3. Install dependencies

```bash
# crm-service
cd crm-service
python3 -m venv venv        # only if the committed venv doesn't match your Python version
source venv/bin/activate
pip install -r requirements.txt
deactivate

# ai-service
cd ../ai-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

# frontend
cd ../frontend
npm install
```

## 4. Run

Each service in its own terminal:

```bash
# crm-service — http://localhost:8001
cd crm-service && ./venv/bin/python3 main.py

# ai-service — http://localhost:8000
cd ai-service && ./venv/bin/python3 main.py

# frontend — http://localhost:3000
cd frontend && npm run dev
```

`main.py` in both backend services runs multiple worker processes unless
`DEBUG=true` is set in the environment, in which case it runs single-process
with auto-reload — useful while developing.

Health checks:

```bash
curl localhost:8001/health
curl localhost:8000/health
```

The frontend proxies all `/api/*` calls to ai-service (`NEXT_PUBLIC_BACKEND_URL`),
which in turn proxies a whitelisted set of prefixes through to crm-service —
see `_CRM_PREFIXES` in `ai-service/main.py` if a new crm-service route isn't
reachable from the browser.

## Login

There's no self-serve signup for `admin`/`staff`/`super_admin` roles — the
first users of each role must be inserted/promoted directly in the database.
`customer` accounts can self-register via the frontend signup flow.

### Test accounts

Three seeded logins cover the three gated role tiers for local QA. They're
created/reset by a script rather than a one-off DB edit, so anyone can
reproduce or rotate them:

```bash
cd crm-service && ./venv/bin/python3 scripts/seed_test_accounts.py
```

| Role | Email | Password | Notes |
|---|---|---|---|
| `super_admin` | `superadmin.test@allzonetech.local` | `SuperAdmin!2026Test` | No `business_id` — sees `/platform`; must click **Manage** on an agency to scope into business-level pages (Conversations, Leads, etc.) |
| `staff` | `staff.test@allzonetech.local` | `StaffUser!2026Test` | Scoped to `bus_001` ("Test Business") |
| `customer` | `customer.test@allzonetech.local` | `Customer!2026Test` | Scoped to `bus_001`; self-service/portal role |

These are dev-only accounts (`@allzonetech.local`) and are separate from real
accounts such as `admin@allzonetech.com` — the seed script never touches
those. Passwords are hashed with bcrypt in the `users.password_hash` column,
same as any real signup; nothing is stored in plaintext.

If you rotate these passwords, update the table above **and** the
`TEST_ACCOUNTS` list in `crm-service/scripts/seed_test_accounts.py` — they
must stay in sync or the documented logins will stop working silently.

## Database structure

One shared Postgres database (`aicrm`, owned by the dedicated `aicrm_app` role), applied via `database/schema.pg.sql`
plus every file in `database/migrations/` in order (see [§1](#1-database)).
As of migration `022_sms_compliance.sql` there are 45 tables, grouped by
domain:

| Domain | Tables |
|---|---|
| Tenancy & auth | `businesses`, `users`, `refresh_tokens` |
| Leads & lifecycle | `leads`, `lead_status_history`, `lead_configs`, `lead_stages` |
| Assignment & scoring | `assignment_rules`, `assignment_rr_state`, `lead_scoring_rules`, `lead_score_history` |
| Automation engine | `workflows`, `workflow_nodes`, `workflow_edges`, `lead_workflow_enrollments`, `workflow_node_runs`, `scheduled_callbacks` |
| Messaging | `conversations`, `messages`, `communication_rules`, `emergency_blocks` |
| Voice & appointments | `voice_calls`, `appointments`, `appointment_reminder_jobs`, `appointment_reminder_events`, `availability`, `providers`, `provider_services`, `services`, `patients`, `phone_accounts` |
| AI agents | `ai_agents` |
| Notes & tasks | `notes`, `tasks` |
| Billing | `plans`, `subscriptions`, `invoices` |
| Activity feed | `activity_feed_events` |
| External CRM sync | `crm_sync_jobs`, `crm_sync_events` |
| Legacy chat widget | `chat_sessions`, `chat_messages` |

Notes:

- `leads`, `voice_calls`, `conversations`, and most operational tables carry
  `business_id` for tenant scoping; `crm-service/core/auth.py`'s
  `get_business_id()`/`get_scope()` is the single choke point almost every
  crm-service query reads that scoping from.
- `users.role` is `customer` < `staff` < `admin` < `super_admin`.
  `super_admin` rows have `business_id = NULL` and pass an
  `X-Business-Id` header (set via the Platform → Manage flow) to drill into
  one agency.
- `scheduled_callbacks` is the shared just-in-time executor queue for both
  workflow actions and legacy sequence steps — see
  `ai-service/core/callback_scheduler.py`'s 30s poller.
- Full column-level detail lives in `database/schema.pg.sql` (base tables)
  and `database/migrations/*.sql` (everything added since); this table is a
  map, not a substitute for reading those files when touching a given table.
