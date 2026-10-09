"""
FastAPI server — Voice Bot + API Routes
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import httpx
import uvicorn

from config import get_settings
from voice.router import router as twilio_router
from vapi.router  import router as vapi_router
from crm.router import router as crm_router
from api.auth.router import router as auth_router
from api.appointments.router import router as appointments_router
from api.dialer.router import router as dialer_router
from api.emergency_blocks.router import router as emergency_blocks_router
from api.admin.router import router as admin_router
from api.integrations.router import router as integrations_router
from api.webhooks.router import router as webhooks_router
from api.reminders.router import router as reminders_router
from api.holidays.router import router as holidays_router
from api.calls.router import router as calls_router
from api.sms.router import router as sms_router
from api.imessage.router import router as imessage_router
from api.activity_feed.router import router as activity_feed_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting Voice Bot Service...")
    logger.info(f"[startup] backend_api_url={settings.backend_api_url}")

    from core.audio import warmup
    await warmup([
        "Hello! This is James from AllZone Scheduler. How can I help you today?",
        "I did not quite catch that. Could you please repeat?",
        "I am sorry, I could not process that. Please try again.",
        "Thank you for calling. Have a great day. Goodbye!",
    ])

    # check_and_fire_callbacks polls/competes over the SAME database this
    # process is pointed at — safe when that's a dedicated local DB, but a
    # real hazard when a local instance is pointed at the production
    # database for testing against real data (confirmed live: it has no
    # locking and could race production to double-fire a real lead's
    # pending SMS/call). DISABLE_BACKGROUND_JOBS lets a local run opt out
    # while still using simulate-inbound/direct endpoints against real data
    # — unset in every deployed environment, so production is unaffected.
    import os
    if os.environ.get("DISABLE_BACKGROUND_JOBS", "").lower() in ("1", "true"):
        logger.warning("[startup] DISABLE_BACKGROUND_JOBS set — skipping callback scheduler (local testing mode)")
    else:
        from core.callback_scheduler import start_scheduler
        start_scheduler()

    # Claw Messenger's persistent websocket connection is intentionally NOT
    # started — it's being replaced by BlueBubbles (core/bluebubbles.py),
    # which is a stateless REST API with no connection lifecycle to manage,
    # so there's nothing to start here for it. Left as a two-line revert
    # (start_claw_messenger()/stop_claw_messenger(), same DISABLE_BACKGROUND_
    # JOBS-gated shape as the scheduler above) rather than deleted, in case
    # BlueBubbles needs to be rolled back.
    # from core.claw_messenger import start_claw_messenger
    # start_claw_messenger()

    yield

    if os.environ.get("DISABLE_BACKGROUND_JOBS", "").lower() not in ("1", "true"):
        from core.callback_scheduler import stop_scheduler
        stop_scheduler()
    # from core.claw_messenger import stop_claw_messenger
    # await stop_claw_messenger()
    logger.info("Shutting down Voice Bot Service...")


app = FastAPI(
    title="AllZone Voice Bot Service",
    description="Twilio voice bot + API routes",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting (100 req/min per IP) ───────────────────────────────────────
from collections import defaultdict
import time as _time

_rate_store: dict = defaultdict(list)
_rate_last_cleanup = _time.time()

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    global _rate_last_cleanup
    ip = request.client.host if request.client else "unknown"
    now = _time.time()
    window = 60
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < window]
    if len(_rate_store[ip]) >= 100:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    _rate_store[ip].append(now)
    # Purge stale IPs every 5 minutes to prevent unbounded growth
    if now - _rate_last_cleanup > 300:
        stale = [k for k, v in _rate_store.items() if not v]
        for k in stale:
            del _rate_store[k]
        _rate_last_cleanup = now
    return await call_next(request)

# Voice bot — Twilio (current)
app.include_router(twilio_router)

# Voice bot — Vapi (alternative)
app.include_router(vapi_router)

# CRM routes
app.include_router(crm_router)

# API routes (ported from TypeScript)
app.include_router(auth_router)
app.include_router(appointments_router)
app.include_router(dialer_router)
app.include_router(emergency_blocks_router)
app.include_router(admin_router)
app.include_router(integrations_router)
app.include_router(webhooks_router)
app.include_router(reminders_router)
app.include_router(holidays_router)
app.include_router(calls_router)
app.include_router(sms_router)
app.include_router(imessage_router)
app.include_router(activity_feed_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "service": "voice-bot",
    }


# ── CRM Service Proxy ─────────────────────────────────────────────────────────
# Routes all CRM-service calls through ai-service so Vercel only needs one
# public backend URL (NEXT_PUBLIC_BACKEND_URL). Must be registered LAST.
_CRM_PREFIXES = {"leads", "agents", "conversations", "lead-configs", "users", "activity-feed", "workflows", "crm-settings", "automation-settings", "notes", "tasks", "billing", "platform"}

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def _crm_proxy(path: str, request: Request):
    from core.config import CRM_SERVICE_URL
    first = path.split("/")[0]
    if first not in _CRM_PREFIXES:
        raise HTTPException(status_code=404, detail="Not found")
    url = f"{CRM_SERVICE_URL}/api/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    params = dict(request.query_params)
    last_exc = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.request(method=request.method, url=url,
                                           content=body, headers=headers, params=params)
            return Response(content=res.content, status_code=res.status_code,
                            media_type=res.headers.get("content-type", "application/json"))
        except httpx.RequestError as e:
            last_exc = e
            await asyncio.sleep(0.5 * (attempt + 1))
    raise HTTPException(status_code=503, detail=f"CRM service unavailable: {last_exc}")


if __name__ == "__main__":
    settings = get_settings()
    print(f"""
+------------------------------------------------------------+
|     AllZone Voice Bot Service                              |
+------------------------------------------------------------+
|  Running on http://{settings.host}:{settings.port:<32}|
+------------------------------------------------------------+
    """)
    # Every worker process runs its own independent copy of the startup
    # event, including the APScheduler background jobs (check_and_fire_
    # callbacks, orphan-call/reply checks) and its own separate DB
    # connection pool — with workers=cpu_count() that meant every scheduled
    # job ran N times concurrently every interval, and the DB could see up
    # to N * 20 connections from this service alone. There's proper atomic
    # claim locking so this never caused duplicate sends, but the redundant
    # load and connection pressure was real — confirmed live as message
    # delivery got slower the longer a test session ran. Single-agency
    # demo/test scale has no need for multi-process HTTP throughput; one
    # worker removes the duplication at the source.
    workers = 1
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=workers,
    )
