"""Integrations routes — Python/FastAPI port of integrations.ts"""
import os
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
import base64, json as _json
from urllib.parse import urlencode
from core.config import (JWT_SECRET, DEFAULT_BUSINESS_ID, TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL,
    OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID, OUTLOOK_REDIRECT_URI)
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations")





# ── Models ────────────────────────────────────────────────────────────────────

class VapiBody(BaseModel):
    businessId: str
    apiKey: str
    assistantId: Optional[str] = None


class TwilioBody(BaseModel):
    businessId: str
    sid: str
    authToken: str
    phoneNumber: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status")
def integration_status(request: Request):
    user_id = request.headers.get("x-user-id", "")
    business_id = request.headers.get("x-business-id", "")

    if not user_id or not business_id:
        raise HTTPException(status_code=400, detail="Missing headers")

    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT google_refresh_token, outlook_refresh_token FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.execute("SELECT hubspot_connected, vapi_api_key, twilio_sid FROM businesses WHERE id = %s", (business_id,))
    biz = cur.fetchone()
    cur.close(); conn.close()

    return {
        "success": True,
        "data": {
            "google":  {"connected": bool(user.get("google_refresh_token")  if user else False)},
            "outlook": {"connected": bool(user.get("outlook_refresh_token") if user else False)},
            "hubspot": {"connected": bool(biz.get("hubspot_connected") if biz else False)},
            "vapi":    {"connected": bool(biz.get("vapi_api_key") if biz else False)},
            "twilio":  {"connected": bool(biz.get("twilio_sid") if biz else False)},
        },
    }


@router.get("/hubspot/authorize")
def hubspot_authorize(request: Request, businessId: str = ""):
    if not businessId:
        raise HTTPException(status_code=400, detail="Missing businessId")
    scopes = "crm.objects.contacts.read crm.objects.contacts.write crm.objects.appointments.read crm.objects.appointments.write"
    auth_url = (
        f"https://app.hubspot.com/oauth/authorize"
        f"?client_id={HUBSPOT_CLIENT_ID}"
        f"&redirect_uri={HUBSPOT_REDIRECT_URI}"
        f"&scope={scopes.replace(' ', '%20')}"
        f"&state={businessId}"
    )
    return RedirectResponse(url=auth_url)


@router.get("/hubspot/callback")
async def hubspot_callback(request: Request, code: str = "", state: str = ""):
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    business_id = state
    async with httpx.AsyncClient(timeout=10) as client:
        token_res = await client.post(
            "https://api.hubapi.com/oauth/v1/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=f"grant_type=authorization_code&client_id={HUBSPOT_CLIENT_ID}&client_secret={HUBSPOT_CLIENT_SECRET}&redirect_uri={HUBSPOT_REDIRECT_URI}&code={code}".encode(),
        )

    if not token_res.is_success:
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&hubspot=error")

    refresh_token = token_res.json().get("refresh_token")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE businesses SET hubspot_refresh_token = %s, hubspot_connected = TRUE, updated_at = NOW() WHERE id = %s", (refresh_token, business_id))
    conn.commit(); cur.close(); conn.close()

    return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&hubspot=success")


@router.get("/outlook/connect")
def outlook_connect(request: Request, token: str = ""):
    """Redirects user to Microsoft login. Token passed as query param since this is a page redirect."""
    if not token:
        # Also accept Authorization header
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("userId")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Encode user_id in state so callback can identify the user
    state = base64.urlsafe_b64encode(_json.dumps({"user_id": user_id}).encode()).decode()

    scopes = "Calendars.ReadWrite offline_access User.Read"
    params = urlencode({
        "client_id":     OUTLOOK_CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  OUTLOOK_REDIRECT_URI,
        "scope":         scopes,
        "response_mode": "query",
        "state":         state,
    })
    auth_url = f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/authorize?{params}"
    return RedirectResponse(url=auth_url)


@router.get("/outlook/callback")
async def outlook_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&outlook=error&msg={error}")
    if not code or not state:
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&outlook=error")

    try:
        state_data = _json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        user_id = state_data["user_id"]
    except Exception:
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&outlook=error")

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(
            f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id":     OUTLOOK_CLIENT_ID,
                "client_secret": OUTLOOK_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  OUTLOOK_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )

    if not token_res.is_success:
        logger.error(f"[outlook] Token exchange failed: {token_res.text[:300]}")
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&outlook=error")

    tokens = token_res.json()
    refresh_token = tokens.get("refresh_token")
    access_token  = tokens.get("access_token")

    if not refresh_token:
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&outlook=error&msg=no_refresh_token")

    # Get user email from Microsoft Graph
    outlook_email = None
    if access_token:
        async with httpx.AsyncClient(timeout=10) as client:
            me_res = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if me_res.is_success:
            outlook_email = me_res.json().get("mail") or me_res.json().get("userPrincipalName")

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE users SET outlook_refresh_token = %s, outlook_email = %s, updated_at = NOW() WHERE id = %s",
        (refresh_token, outlook_email, user_id),
    )
    conn.commit(); cur.close(); conn.close()

    logger.info(f"[outlook] Connected for user {user_id} — {outlook_email}")
    return RedirectResponse(url=f"{FRONTEND_URL}/settings?tab=integrations&outlook=success")


@router.post("/outlook/disconnect")
def outlook_disconnect(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("userId")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("UPDATE users SET outlook_refresh_token = NULL, outlook_email = NULL WHERE id = %s", (user_id,))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}


@router.post("/vapi")
def update_vapi(body: VapiBody):
    if not body.businessId or not body.apiKey:
        raise HTTPException(status_code=400, detail="Missing required fields")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE businesses SET vapi_api_key = %s, vapi_assistant_id = %s, updated_at = NOW() WHERE id = %s", (body.apiKey, body.assistantId, body.businessId))
    conn.commit(); cur.close(); conn.close()
    return {"success": True, "message": "Vapi settings updated"}


@router.post("/twilio")
def update_twilio(body: TwilioBody):
    if not body.businessId or not body.sid or not body.authToken:
        raise HTTPException(status_code=400, detail="Missing required fields")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE businesses SET twilio_sid = %s, twilio_auth_token = %s, twilio_phone_number = %s, updated_at = NOW() WHERE id = %s", (body.sid, body.authToken, body.phoneNumber, body.businessId))
    conn.commit(); cur.close(); conn.close()
    return {"success": True, "message": "Twilio settings updated"}
