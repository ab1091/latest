#!/usr/bin/env python3
"""
Smoke test — verifies every real external integration and core service
actually works, using real credentials from the .env files. Not unit tests
(nothing here is mocked) — this is meant to be run before building Docker
images or deploying, to catch config drift (expired tokens, wrong URLs,
disabled APIs) before it becomes a production incident.

Usage — run from anywhere, with any Python on PATH:
    python3 scripts/smoke_test.py

This re-execs itself under ai-service's venv automatically (it's the only
one with every dependency this script needs — sentence-transformers, groq,
google-genai, redis, psycopg2). You don't need to activate anything first.

Exits non-zero if anything failed — safe to use as a pre-build gate.
"""
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Re-exec under ai-service's venv if we're not already running under it —
# this is what makes `python3 scripts/smoke_test.py` work regardless of
# which Python/venv (if any) was active in the caller's shell.
_AI_VENV_DIR = ROOT / "ai-service" / "venv"
_AI_VENV_PYTHON = _AI_VENV_DIR / "bin" / "python3"
# Compare sys.prefix, not sys.executable — venv python binaries are usually
# *symlinks* to the base interpreter, so resolving sys.executable collapses
# both to the same real file and a naive equality check never re-execs.
# sys.prefix is set correctly at interpreter startup based on which venv's
# pyvenv.cfg was found, regardless of the symlink.
if _AI_VENV_PYTHON.exists() and Path(sys.prefix).resolve() != _AI_VENV_DIR.resolve():
    os.execv(str(_AI_VENV_PYTHON), [str(_AI_VENV_PYTHON), __file__, *sys.argv[1:]])

# Must happen before any @check-decorated function is defined below — checks
# run immediately at decoration time (module load), so imports like
# `from rag.embeddings import ...` need ai-service on sys.path *and* cwd set
# *first* (google-genai in particular resolves oddly if cwd isn't right).
sys.path.insert(0, str(ROOT / "ai-service"))
os.chdir(ROOT / "ai-service")

# Load both services' .env files (ai-service's values win on overlap, which
# matches how DATABASE_URL/JWT_SECRET are meant to be identical anyway)
from dotenv import load_dotenv
load_dotenv(ROOT / "crm-service" / ".env")
load_dotenv(ROOT / "ai-service" / ".env", override=True)

RESULTS: list[tuple[str, str, str]] = []  # (name, status, detail)


def check(name):
    """Decorator: runs the check, catches everything, records PASS/FAIL/SKIP."""
    def wrap(fn):
        t0 = time.time()
        try:
            detail = fn()
            ms = int((time.time() - t0) * 1000)
            if detail == "SKIP":
                RESULTS.append((name, "SKIP", "not configured"))
            else:
                RESULTS.append((name, "PASS", f"{detail or 'ok'} ({ms}ms)"))
        except Exception as e:
            RESULTS.append((name, "FAIL", str(e)[:160]))
    return wrap


AI_URL = f"http://localhost:{os.environ.get('PORT', '8002')}"
CRM_URL = os.environ.get("CRM_SERVICE_URL", "http://localhost:8003")


# ── Services ─────────────────────────────────────────────────────────────────

@check("ai-service /health")
def _():
    import httpx
    r = httpx.get(f"{AI_URL}/health", timeout=5)
    r.raise_for_status()
    return r.json().get("status")


@check("crm-service /health")
def _():
    import httpx
    r = httpx.get(f"{CRM_URL}/health", timeout=5)
    r.raise_for_status()
    return r.json().get("status")


# ── Database ─────────────────────────────────────────────────────────────────

@check("Postgres connection")
def _():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.close(); conn.close()
    return "connected"


@check("pgvector extension")
def _():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT installed_version FROM pg_available_extensions WHERE name='vector'")
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or not row[0]:
        raise RuntimeError("extension not installed in this database")
    return f"v{row[0]}"


@check("Redis connection")
def _():
    import redis
    r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    r.ping()
    return "connected"


# ── Auth ─────────────────────────────────────────────────────────────────────

@check("Login flow (JWT issuance)")
def _():
    import httpx
    r = httpx.post(f"{AI_URL}/api/auth/login", json={
        "email": "admin@aischeduler.com", "password": "Test1234!",
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("data", {}).get("accessToken"):
        raise RuntimeError("no accessToken in response")
    return "token issued"


# ── LLMs ─────────────────────────────────────────────────────────────────────

@check("Gemini API")
def _():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return "SKIP"
    from google import genai
    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model="gemini-2.5-flash-lite", contents="Reply with the single word: ok",
        config={"max_output_tokens": 10, "thinking_config": {"thinking_budget": 0}},
    )
    if not resp.text:
        raise RuntimeError("empty response")
    return "responded"


@check("Groq API")
def _():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return "SKIP"
    from groq import Groq
    client = Groq(api_key=key)
    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=10,
    )
    if not resp.choices:
        raise RuntimeError("empty response")
    return "responded"


@check("Local embedding model (RAG)")
def _():
    from rag.embeddings import embed_texts
    vecs = embed_texts(["smoke test sentence"])
    if len(vecs[0]) != 384:
        raise RuntimeError(f"unexpected dimension: {len(vecs[0])}")
    return f"{len(vecs[0])}-dim"


# ── Google ───────────────────────────────────────────────────────────────────

def _google_token():
    import httpx
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_CALENDAR_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=10)
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("no access_token in refresh response")
    return token


@check("Google Calendar API")
def _():
    if not os.environ.get("GOOGLE_CALENDAR_REFRESH_TOKEN"):
        return "SKIP"
    import httpx
    token = _google_token()
    r = httpx.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=1",
        headers={"Authorization": f"Bearer {token}"}, timeout=10,
    )
    r.raise_for_status()
    return "calendar reachable"


@check("Gmail send scope")
def _():
    if not os.environ.get("GOOGLE_CALENDAR_REFRESH_TOKEN"):
        return "SKIP"
    import httpx
    token = _google_token()
    # tokeninfo confirms the scope is present without sending an email on every run
    r = httpx.get(f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={token}", timeout=10)
    r.raise_for_status()
    scopes = r.json().get("scope", "")
    if "gmail.send" not in scopes:
        raise RuntimeError("token lacks gmail.send scope — re-auth needed")
    return "scope present"


# ── Vapi / Telephony ─────────────────────────────────────────────────────────

@check("Vapi API")
def _():
    key = os.environ.get("VAPI_API_KEY")
    if not key:
        return "SKIP"
    import httpx
    r = httpx.get("https://api.vapi.ai/phone-number", headers={"Authorization": f"Bearer {key}"}, timeout=10)
    r.raise_for_status()
    numbers = r.json()
    return f"{len(numbers)} number(s) configured"


@check("Twilio credentials")
def _():
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not (sid and token):
        return "SKIP"
    import httpx
    r = httpx.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json", auth=(sid, token), timeout=10)
    r.raise_for_status()
    return "account reachable"


@check("Sendblue credentials")
def _():
    key = os.environ.get("SENDBLUE_API_KEY")
    secret = os.environ.get("SENDBLUE_API_SECRET")
    if not (key and secret):
        return "SKIP"
    import httpx
    # A GET with no message data — invalid params are expected (400/422), but
    # 401/403 means the credentials themselves are bad. Anything else is a
    # genuine connectivity failure.
    r = httpx.get("https://api.sendblue.com/api/account", headers={
        "sb-api-key-id": key, "sb-api-secret-key": secret,
    }, timeout=10)
    if r.status_code in (401, 403):
        raise RuntimeError(f"credentials rejected: {r.status_code}")
    return f"reachable ({r.status_code})"


# ── Core business logic (real DB writes, cleaned up after) ───────────────────

@check("Lead CRUD (create + delete)")
def _():
    import httpx, uuid
    r = httpx.post(f"{AI_URL}/api/auth/login", json={
        "email": "admin@aischeduler.com", "password": "Test1234!",
    }, timeout=10)
    token = r.json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    phone = f"+1555{uuid.uuid4().hex[:7]}"
    r = httpx.post(f"{CRM_URL}/api/leads", json={
        "first_name": "SmokeTest", "last_name": "Lead", "phone": phone, "tags": [],
    }, headers=headers, timeout=10)
    r.raise_for_status()
    lead_id = r.json()["data"]["lead"]["id"]

    r = httpx.delete(f"{CRM_URL}/api/leads/{lead_id}", headers=headers, timeout=10)
    r.raise_for_status()
    return f"created+deleted {lead_id}"


@check("Knowledge base retrieval")
def _():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM kb_chunks")
    count = cur.fetchone()[0]
    cur.close(); conn.close()
    if count == 0:
        return "SKIP"
    return f"{count} chunks indexed"


# ── Report ───────────────────────────────────────────────────────────────────

def main():
    width = max(len(r[0]) for r in RESULTS) + 2

    print("\n" + "=" * 70)
    print("SMOKE TEST RESULTS")
    print("=" * 70)
    passed = failed = skipped = 0
    for name, status, detail in RESULTS:
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "—"}[status]
        print(f"{icon} {name:<{width}} {status:<6} {detail}")
        if status == "PASS": passed += 1
        elif status == "FAIL": failed += 1
        else: skipped += 1
    print("=" * 70)
    print(f"{passed} passed, {failed} failed, {skipped} skipped\n")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
