#!/usr/bin/env python3
"""
AllZone Voice Bot — One-click setup script
Run: python setup.py
"""

import os
import sys
import time
import shutil
import subprocess
import secrets

# ── Colours ──────────────────────────────────────────────────────────────────
G  = "\033[92m"   # green
Y  = "\033[93m"   # yellow
R  = "\033[91m"   # red
B  = "\033[94m"   # blue
W  = "\033[97m"   # white
NC = "\033[0m"    # reset


def ok(msg):  print(f"  {G}✓{NC}  {msg}")
def info(msg): print(f"  {B}→{NC}  {msg}")
def warn(msg): print(f"  {Y}!{NC}  {msg}")
def fail(msg): print(f"  {R}✗{NC}  {msg}"); sys.exit(1)


def run(cmd, capture=False, check=True):
    if capture:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result
    subprocess.run(cmd, shell=True, check=check)


def header(title):
    print(f"\n{W}{'─' * 55}{NC}")
    print(f"{W}  {title}{NC}")
    print(f"{W}{'─' * 55}{NC}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Check prerequisites
# ─────────────────────────────────────────────────────────────────────────────
def fix_docker_credentials():
    """Remove credsStore=desktop from Docker config if docker-credential-desktop is missing."""
    import json
    config_path = os.path.expanduser("~/.docker/config.json")
    if not os.path.exists(config_path):
        return
    with open(config_path) as f:
        config = json.load(f)
    if config.get("credsStore") == "desktop" and not shutil.which("docker-credential-desktop"):
        config.pop("credsStore", None)
        with open(config_path, "w") as f:
            json.dump(config, f, indent="\t")
        warn("Fixed Docker credential config (removed missing credsStore)")


def check_prerequisites():
    header("Step 1 — Checking Prerequisites")

    if not shutil.which("docker"):
        fail("Docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop")
    ok("Docker found")

    result = run("docker info", capture=True, check=False)
    if result.returncode != 0:
        fail("Docker daemon is not running. Please start Docker Desktop.")
    ok("Docker daemon is running")

    fix_docker_credentials()

    result = run("docker compose version", capture=True, check=False)
    if result.returncode != 0:
        fail("Docker Compose not found. Update Docker Desktop to the latest version.")
    ok("Docker Compose found")

    if not shutil.which("python3") and not shutil.which("python"):
        fail("Python 3 not found.")
    ok("Python 3 found")

    if not shutil.which("npm"):
        warn("npm not found — attempting to install Node.js automatically...")
        if shutil.which("brew"):
            result = run("brew install node", capture=False, check=False)
            if not shutil.which("npm"):
                fail("Node.js install failed. Install manually: https://nodejs.org")
            ok("Node.js installed via Homebrew")
        else:
            fail(
                "npm not found and Homebrew is not installed.\n"
                "  Install Node.js manually: https://nodejs.org\n"
                "  Or install Homebrew first: https://brew.sh"
            )
    else:
        ok("npm found")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Check / create .env file
# ─────────────────────────────────────────────────────────────────────────────
ENV_TEMPLATE = """\
# ── App ──────────────────────────────────────────────────────────
JWT_SECRET=replace-with-a-strong-random-secret
DEFAULT_BUSINESS_ID=bus_001

# ── Twilio ───────────────────────────────────────────────────────
# Get from: https://console.twilio.com
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
# ngrok URL for local dev: ngrok http 8000
TWILIO_TWIML_BASE_URL=https://your-ngrok-url.ngrok-free.app

# ── Groq (LLM for voice bot) ─────────────────────────────────────
# Get from: https://console.groq.com
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── ElevenLabs (Text-to-Speech) ──────────────────────────────────
# Get from: https://elevenlabs.io
ELEVENLABS_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
ELEVENLABS_MODEL_ID=eleven_turbo_v2

# ── Google Calendar ───────────────────────────────────────────────
# Get from: https://console.cloud.google.com
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxx
GOOGLE_CALENDAR_REFRESH_TOKEN=1//xxxxxxxxxxxxxxxxxx

# ── HubSpot CRM (optional) ────────────────────────────────────────
# Get from: https://app.hubspot.com/private-apps
HUBSPOT_ACCESS_TOKEN=pat-na2-xxxxxxxxxxxxxxxxxxxx

# ── Webhook Secrets ───────────────────────────────────────────────
VAPI_WEBHOOK_SECRET=your-webhook-secret
REMINDER_TOOL_SECRET=your-reminder-secret
"""


def check_env():
    header("Step 2 — Environment Configuration")

    env_path = os.path.join("ai-service", ".env")

    if os.path.exists(env_path):
        ok(f"Found ai-service/.env")

        # Check for unfilled placeholder values
        with open(env_path) as f:
            content = f.read()

        if "replace-with-a-strong-random-secret" in content:
            generated = secrets.token_hex(32)
            content = content.replace("replace-with-a-strong-random-secret", generated)
            with open(env_path, "w") as f:
                f.write(content)
            ok("JWT_SECRET auto-generated")

        placeholders = [
            line.split("=")[0].strip()
            for line in content.splitlines()
            if "=" in line
            and not line.startswith("#")
            and any(x in line for x in ["xxxxxxx", "replace-with", "your-", "XXXXXXXXXX"])
        ]

        if placeholders:
            warn("The following keys still have placeholder values:")
            for p in placeholders:
                print(f"       {Y}{p}{NC}")
            warn("Fill them in ai-service/.env before proceeding.")
            choice = input(f"\n  {Y}Continue anyway? (y/n): {NC}").strip().lower()
            if choice != "y":
                print("  Aborted. Fill in ai-service/.env and run setup again.")
                sys.exit(0)
        else:
            ok("All required keys appear to be filled in")
    else:
        warn("ai-service/.env not found — creating template...")
        with open(env_path, "w") as f:
            f.write(ENV_TEMPLATE)
        print(f"""
  {Y}Created ai-service/.env with placeholder values.{NC}

  Please fill in the following before continuing:
    {W}· TWILIO_ACCOUNT_SID / AUTH_TOKEN / FROM_NUMBER{NC}
    {W}· TWILIO_TWIML_BASE_URL{NC}  (run: ngrok http 8000)
    {W}· GROQ_API_KEY{NC}
    {W}· ELEVENLABS_API_KEY{NC}
    {W}· GOOGLE_CLIENT_ID / SECRET / REFRESH_TOKEN{NC}

  Then run this script again.
""")
        sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2b — Generate package-lock.json if missing
# ─────────────────────────────────────────────────────────────────────────────
def ensure_package_lock():
    lock_path = os.path.join("frontend", "package-lock.json")
    if os.path.exists(lock_path):
        ok("frontend/package-lock.json found")
        return
    if not shutil.which("npm"):
        fail("npm not found. Install Node.js to generate package-lock.json before Docker build.")
    info("Generating frontend/package-lock.json (required for npm ci in Docker)...")
    result = run("npm install --package-lock-only --prefix frontend", capture=True, check=False)
    if result.returncode != 0:
        print(result.stderr)
        fail("Failed to generate package-lock.json")
    ok("frontend/package-lock.json generated")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Build Docker images
# ─────────────────────────────────────────────────────────────────────────────
def build_images():
    header("Step 3 — Building Docker Images")
    info("This may take 3-5 minutes on first run...")
    print()
    result = subprocess.run("docker compose build", shell=True)
    if result.returncode != 0:
        fail("Docker build failed. Check the error above.")
    ok("Docker images built successfully")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Start containers
# ─────────────────────────────────────────────────────────────────────────────
def start_containers():
    header("Step 4 — Starting Containers")
    result = run("docker compose up -d --force-recreate 2>&1", capture=True, check=False)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        fail("Failed to start containers. Check the error above.")
    ok("Containers started")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Wait for database to be ready
# ─────────────────────────────────────────────────────────────────────────────
def wait_for_db():
    header("Step 5 — Waiting for Database")
    info("Waiting for PostgreSQL to be ready...")

    for attempt in range(30):
        result = run(
            'docker exec allzone-voice-bot-db-1 '
            'pg_isready -U postgres -d ai_schedular',
            capture=True, check=False
        )
        if result.returncode == 0:
            ok("PostgreSQL is ready")
            return
        time.sleep(2)
        print(f"    attempt {attempt + 1}/30...", end="\r")

    fail("PostgreSQL did not become ready in time. Check: docker logs allzone-voice-bot-db-1")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Initialize database schema + seed data
# ─────────────────────────────────────────────────────────────────────────────
def init_database():
    header("Step 6 — Database Setup")

    # Check if already initialized (tables exist)
    result = run(
        "docker exec allzone-voice-bot-db-1 "
        "psql -U postgres -d ai_schedular -c "
        "\"SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='users';\"",
        capture=True, check=False
    )

    already_init = result.returncode == 0 and "1" in result.stdout

    if already_init:
        warn("Database already initialized — skipping schema + seed")
        choice = input(f"  {Y}Re-initialize? This will DELETE all existing data (y/n): {NC}").strip().lower()
        if choice != "y":
            ok("Keeping existing database")
        else:
            info("Applying schema...")
            run(
                "docker exec -i allzone-voice-bot-db-1 "
                "psql -U postgres -d ai_schedular < database/schema.pg.sql"
            )
            ok("Schema applied")

            info("Seeding sample data...")
            run(
                "docker exec -i allzone-voice-bot-db-1 "
                "psql -U postgres -d ai_schedular < database/seed.large.pg.sql"
            )
            ok("Sample data loaded")
    else:
        info("Applying schema...")
        run(
            "docker exec -i allzone-voice-bot-db-1 "
            "psql -U postgres -d ai_schedular < database/schema.pg.sql"
        )
        ok("Schema applied")

        info("Seeding sample data...")
        run(
            "docker exec -i allzone-voice-bot-db-1 "
            "psql -U postgres -d ai_schedular < database/seed.large.pg.sql"
        )
        ok("Sample data loaded")

    info("Running migrations...")
    migration_dir = os.path.join("database", "migrations")
    if os.path.isdir(migration_dir):
        migrations = sorted(
            f for f in os.listdir(migration_dir) if f.endswith(".sql")
        )
        for migration in migrations:
            migration_path = os.path.join(migration_dir, migration)
            result = run(
                f"docker exec -i allzone-voice-bot-db-1 "
                f"psql -U postgres -d ai_schedular < {migration_path}",
                capture=True, check=False
            )
            if result.returncode != 0:
                warn(f"Migration {migration} had warnings (usually safe): {result.stderr[:200]}")
            else:
                ok(f"Migration applied: {migration}")
    else:
        warn("No migrations directory found — skipping")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Health check
# ─────────────────────────────────────────────────────────────────────────────
def health_check():
    header("Step 7 — Health Check")
    import urllib.request
    import json

    info("Waiting for ai-service to start...")
    for attempt in range(20):
        try:
            with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as r:
                data = json.loads(r.read())
                if data.get("status") == "healthy":
                    ok(f"AI Service healthy (v{data.get('version', '?')})")
                    break
        except Exception:
            time.sleep(3)
            print(f"    attempt {attempt + 1}/20...", end="\r")
    else:
        warn("AI Service health check timed out — it may still be starting")

    info("Checking frontend...")
    for attempt in range(10):
        try:
            with urllib.request.urlopen("http://localhost:3000", timeout=3) as r:
                if r.status == 200:
                    ok("Frontend is up")
                    break
        except Exception:
            time.sleep(3)
    else:
        warn("Frontend not responding yet — give it a moment")


# ─────────────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────────────
def print_summary():
    print(f"""
{G}{'═' * 55}{NC}
{G}  Setup Complete!{NC}
{G}{'═' * 55}{NC}

  {W}URLs:{NC}
    Frontend     →  {B}http://localhost:3000{NC}
    AI Service   →  {B}http://localhost:8000{NC}
    Health Check →  {B}http://localhost:8000/health{NC}

  {W}Default Login:{NC}
    Email        →  john.doe@email.com
    Password     →  password123

  {W}Useful Commands:{NC}
    View logs    →  docker compose logs -f
    Stop all     →  docker compose down
    Restart      →  docker compose up -d

  {W}For Twilio voice bot (local dev):{NC}
    1. Run ngrok:   ngrok http 8000
    2. Copy the https URL
    3. Set TWILIO_TWIML_BASE_URL in ai-service/.env
    4. Set webhook in Twilio Console:
       Voice → {B}https://your-ngrok-url/api/twilio/inbound{NC}
    5. Rebuild: docker compose build ai-service
               docker compose up -d ai-service

{G}{'═' * 55}{NC}
""")


# ─────────────────────────────────────────────────────────────────────────────
# DB EXPORT / IMPORT
# ─────────────────────────────────────────────────────────────────────────────
def export_db():
    header("Export Database")
    backup_file = f"backup_{time.strftime('%Y%m%d_%H%M%S')}.sql"
    result = run(
        f"docker exec allzone-voice-bot-db-1 "
        f"pg_dump -U postgres ai_schedular > {backup_file}",
        capture=True, check=False
    )
    if result.returncode != 0:
        fail(f"Export failed: {result.stderr}")
    ok(f"Database exported → {W}{backup_file}{NC}")
    print(f"\n  {Y}Copy this file to the new laptop along with ai-service/.env{NC}\n")


def import_db(backup_file: str):
    header("Import Database")
    if not os.path.exists(backup_file):
        fail(f"File not found: {backup_file}")
    info(f"Importing {backup_file} ...")
    result = run(
        f"docker exec -i allzone-voice-bot-db-1 "
        f"psql -U postgres ai_schedular < {backup_file}",
        capture=True, check=False
    )
    if result.returncode != 0:
        warn(f"Some warnings during import (usually safe to ignore)")
    ok("Database imported successfully")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # Must run from project root
    if not os.path.exists("docker-compose.yml"):
        fail("Run this script from the project root directory:\n   python3 setup.py")

    # ── Sub-commands ──────────────────────────────────────────────────────────
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "export":
            export_db()
            sys.exit(0)

        if cmd == "import":
            if len(sys.argv) < 3:
                fail("Usage: python3 setup.py import <backup_file.sql>")
            import_db(sys.argv[2])
            sys.exit(0)

        if cmd == "help":
            print(f"""
{W}Usage:{NC}
  python3 setup.py              → Full setup (build + start + database)
  python3 setup.py export       → Export database to .sql file
  python3 setup.py import <file>→ Import database from .sql file

{W}New Laptop Setup:{NC}
  1. Copy project folder to new laptop
  2. Copy {Y}ai-service/.env{NC} to new laptop (has API keys)
  3. Copy {Y}backup_XXXXXX.sql{NC} to new laptop (has your data)
  4. Run: {G}python3 setup.py{NC}
  5. Run: {G}python3 setup.py import backup_XXXXXX.sql{NC}
""")
            sys.exit(0)

        fail(f"Unknown command: {cmd}\nRun: python3 setup.py help")

    # ── Normal full setup ─────────────────────────────────────────────────────
    print(f"""
{B}{'═' * 55}{NC}
{B}   AllZone Voice Bot — Project Setup{NC}
{B}{'═' * 55}{NC}
""")

    check_prerequisites()
    check_env()
    ensure_package_lock()
    build_images()
    start_containers()
    wait_for_db()
    init_database()
    health_check()
    print_summary()
