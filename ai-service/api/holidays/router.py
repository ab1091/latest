"""Holidays routes — Python/FastAPI port of holidays.ts"""
import os
import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
from core.config import (DEFAULT_BUSINESS_ID, TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL)
from core.auth_scope import get_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/holidays")


async def _get_access_token(refresh_token: str) -> Optional[str]:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
    return r.json().get("access_token") if r.is_success else None


@router.get("")
async def get_holidays(request: Request):
    scope = get_scope(request)

    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT google_refresh_token FROM users WHERE id = %s", (scope["userId"],))
    user = cur.fetchone()
    cur.close(); conn.close()

    if not user or not user.get("google_refresh_token"):
        return {"success": True, "data": {"holidays": [], "message": "Google Calendar not connected"}}

    access_token = await _get_access_token(user["google_refresh_token"])
    if not access_token:
        return {"success": True, "data": {"holidays": [], "message": "Could not refresh Google token"}}

    year = datetime.now().year
    time_min = f"{year}-01-01T00:00:00Z"
    time_max = f"{year}-12-31T23:59:59Z"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://www.googleapis.com/calendar/v3/calendars/en.usa%23holiday%40group.v.calendar.google.com/events",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime"},
            )

        if not r.is_success:
            return {"success": True, "data": {"holidays": [], "message": "Could not fetch holidays"}}

        items = r.json().get("items", [])
        holidays = [
            {
                "id": item.get("id"),
                "summary": item.get("summary"),
                "date": item.get("start", {}).get("date") or item.get("start", {}).get("dateTime"),
            }
            for item in items
        ]
        return {"success": True, "data": {"holidays": holidays}}

    except Exception as e:
        logger.error(f"[holidays] fetch error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch holidays")
