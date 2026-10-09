"""
CRM Service — FastAPI
Separate from voice bot. Manages leads, AI agents, conversations, routing rules.
"""
from dotenv import load_dotenv
load_dotenv()

import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import httpx
import uvicorn

from routers.leads         import router as leads_router
from routers.agents        import router as agents_router
from routers.lead_configs  import router as lead_configs_router
from routers.conversations import router as conversations_router
from routers.activity_feed import router as activity_feed_router
from routers.workflows    import router as workflows_router
from routers.crm_settings import router as crm_settings_router
from routers.automation_settings import router as automation_settings_router
from routers.notes_tasks  import router as notes_tasks_router
from routers.billing      import router as billing_router
from routers.platform     import router as platform_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AllZone CRM Service",
    description="Lead management, AI agents, conversations, routing rules",
    version="1.0.0",
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads_router)
app.include_router(agents_router)
app.include_router(lead_configs_router)
app.include_router(conversations_router)
app.include_router(activity_feed_router)
app.include_router(workflows_router)
app.include_router(crm_settings_router)
app.include_router(automation_settings_router)
app.include_router(notes_tasks_router)
app.include_router(billing_router)
app.include_router(platform_router)


from core.config import VOICE_BOT_URL


@app.api_route("/api/vapi/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_vapi(path: str, request: Request):
    """Proxy Vapi webhooks to ai-service."""
    body = await request.body()
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.request(
            method=request.method,
            url=f"{VOICE_BOT_URL}/api/vapi/{path}",
            content=body,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            params=dict(request.query_params),
        )
    return Response(content=res.content, status_code=res.status_code,
                    media_type=res.headers.get("content-type", "application/json"))


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "crm-service",
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import os as _os
    debug = _os.environ.get("DEBUG", "false").lower() == "true"
    port = int(_os.environ.get("PORT", "8003"))
    # Matches the same fix in ai-service/main.py: each worker opens its own
    # DB connection pool (up to 20 connections), so cpu_count() workers here
    # meant up to N*20 connections from this service alone against the same
    # shared Postgres instance ai-service also pools against. crm-service
    # itself runs no background scheduler (confirmed — only ai-service does),
    # so this was pure unnecessary connection pressure, not a duplicate-send
    # risk. Single-agency demo/test scale has no need for multi-process HTTP
    # throughput.
    workers = 1
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=debug, workers=workers)
