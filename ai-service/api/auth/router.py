"""Auth routes — Python/FastAPI port of auth.ts"""
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt as _bcrypt
import httpx
from fastapi import APIRouter, Request, HTTPException
from core.db import get_conn, get_dict_cursor
from core.config import (JWT_SECRET, DEFAULT_BUSINESS_ID, TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWIML_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN,
    HUBSPOT_ACCESS_TOKEN, HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI, VAPI_WEBHOOK_SECRET, VAPI_ASSISTANT_ID,
    REMINDER_TOOL_SECRET, FRONTEND_URL)
from jose import jwt, JWTError
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth")


ACCESS_EXPIRES_MIN   = 60 * 24   # 24 hours
REFRESH_EXPIRES_DAYS = 30


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False




def generate_access_token(payload: dict) -> str:
    data = {**payload, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_EXPIRES_MIN)}
    return jwt.encode(data, JWT_SECRET, algorithm="HS256")


def generate_refresh_token(payload: dict) -> str:
    data = {**payload, "exp": datetime.utcnow() + timedelta(days=REFRESH_EXPIRES_DAYS)}
    return jwt.encode(data, JWT_SECRET, algorithm="HS256")


def get_token_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def ensure_business_id(cur, user_id: str, current_biz: Optional[str], role: Optional[str] = None) -> Optional[str]:
    if current_biz:
        return current_biz
    # super_admin is meant to have business_id = NULL (cross-agency) — never
    # auto-assign it into the default business, unlike every other role.
    if role == "super_admin":
        return None
    if not DEFAULT_BUSINESS_ID:
        raise HTTPException(status_code=500, detail="DEFAULT_BUSINESS_ID not configured")
    cur.execute(
        "UPDATE users SET business_id = %s, updated_at = NOW() WHERE id = %s AND business_id IS NULL",
        (DEFAULT_BUSINESS_ID, user_id),
    )
    return DEFAULT_BUSINESS_ID


# ── Models ────────────────────────────────────────────────────────────────────

class SignupBody(BaseModel):
    email: str
    password: str
    firstName: str = ""
    lastName: str = ""
    first_name: str = ""   # snake_case alias (users page sends this)
    last_name: str = ""
    phone: str = ""
    role: str = "customer"


class LoginBody(BaseModel):
    email: str
    password: str


class RefreshBody(BaseModel):
    refreshToken: str


class GoogleBody(BaseModel):
    code: str
    userId: Optional[str] = None


class ProfileUpdateBody(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/me")
def get_me(request: Request):
    token_payload = get_token_user(request)
    user_id = token_payload.get("userId")

    conn = get_conn()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    biz = ensure_business_id(cur, user["id"], user.get("business_id"), user.get("role"))
    conn.commit(); cur.close(); conn.close()

    return {
        "success": True,
        "data": {
            "user": {
                "id": user["id"],
                "email": user["email"],
                "firstName": user["first_name"],
                "lastName": user["last_name"],
                "phone": user.get("phone"),
                "role": user["role"],
                "businessId": biz,
                "agent_id": user.get("agent_id"),
                "google_email": user.get("google_email"),
                "google_connected": bool(user.get("google_refresh_token")),
                "permissions": user.get("permissions") or [],
            }
        },
    }


@router.patch("/profile")
def update_profile(body: ProfileUpdateBody, request: Request):
    token_payload = get_token_user(request)
    user_id = token_payload.get("userId")

    updates = body.dict(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    conn = get_conn()
    cur = get_dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        if "email" in updates:
            cur.execute("SELECT id FROM users WHERE email = %s AND id != %s", (updates["email"], user_id))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Email already registered")

        column_map = {"firstName": "first_name", "lastName": "last_name", "email": "email", "phone": "phone"}
        set_clauses = [f"{column_map[k]} = %s" for k in updates if k in column_map]
        values = [v for k, v in updates.items() if k in column_map]
        cur.execute(
            f"UPDATE users SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = %s",
            (*values, user_id),
        )
        conn.commit()

        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
    finally:
        cur.close(); conn.close()

    return {
        "success": True,
        "data": {
            "user": {
                "id": user["id"],
                "email": user["email"],
                "firstName": user["first_name"],
                "lastName": user["last_name"],
                "phone": user.get("phone"),
                "role": user["role"],
                "businessId": user.get("business_id"),
            }
        },
    }


@router.post("/signup", status_code=201)
def signup(body: SignupBody, request: Request):
    # Determine role — only admin can create staff/admin accounts;
    # only an existing super_admin can grant super_admin (never via public signup).
    allowed_roles = {"customer", "staff", "admin", "super_admin"}
    requested_role = body.role if body.role in allowed_roles else "customer"
    caller_business_id = None
    if requested_role != "customer":
        try:
            caller = get_token_user(request)
            caller_role = caller.get("role")
            caller_business_id = caller.get("businessId")
            if requested_role == "super_admin":
                if caller_role != "super_admin":
                    requested_role = "customer"
            elif caller_role not in ("admin", "super_admin"):
                requested_role = "customer"
            elif caller_role == "super_admin":
                # super_admin has no business of its own — must be drilled into one
                # via the same X-Business-Id header used elsewhere for agency scoping.
                caller_business_id = request.headers.get("X-Business-Id") or caller_business_id
        except Exception:
            requested_role = "customer"

    # Support both camelCase and snake_case name fields
    first = body.firstName or body.first_name or ""
    last  = body.lastName  or body.last_name  or ""

    conn = get_conn()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT id FROM users WHERE email = %s", (body.email,))
    if cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = _hash_password(body.password)
    user_id = str(uuid.uuid4())
    if requested_role == "super_admin":
        biz = None
    elif requested_role == "customer":
        biz = DEFAULT_BUSINESS_ID
    else:
        # staff/admin created by an authenticated admin/super_admin — scope to
        # the caller's own business, not the hardcoded default (multi-tenant fix).
        biz = caller_business_id or DEFAULT_BUSINESS_ID

    cur.execute(
        "INSERT INTO users (id, business_id, email, password_hash, first_name, last_name, phone, role) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (user_id, biz, body.email, password_hash, first, last, body.phone, requested_role),
    )
    conn.commit(); cur.close(); conn.close()

    payload = {"userId": user_id, "email": body.email, "role": requested_role, "businessId": biz}
    return {
        "success": True,
        "data": {
            "user": {
                "id": user_id, "email": body.email,
                "firstName": body.firstName, "lastName": body.lastName,
                "role": "customer", "businessId": biz,
            },
            "accessToken": generate_access_token(payload),
            "refreshToken": generate_refresh_token(payload),
        },
    }


@router.post("/login")
def login(body: LoginBody):
    conn = get_conn()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT * FROM users WHERE email = %s", (body.email,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    biz = ensure_business_id(cur, user["id"], user.get("business_id"), user.get("role"))
    conn.commit()

    if not _verify_password(body.password, user.get("password_hash") or ""):
        cur.close(); conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    cur.close(); conn.close()

    payload = {"userId": user["id"], "email": user["email"], "role": user["role"], "businessId": biz}
    return {
        "success": True,
        "data": {
            "user": {
                "id": user["id"],
                "email": user["email"],
                "firstName": user["first_name"],
                "lastName": user["last_name"],
                "role": user["role"],
                "businessId": biz,
                "google_connected": bool(user.get("google_refresh_token")),
                "permissions": user.get("permissions") or [],
            },
            "accessToken": generate_access_token(payload),
            "refreshToken": generate_refresh_token(payload),
        },
    }


@router.post("/refresh-token")
def refresh_token_route(body: RefreshBody):
    try:
        payload = jwt.decode(body.refreshToken, JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    biz = payload.get("businessId")
    if not biz and payload.get("role") != "super_admin":
        conn = get_conn()
        cur = get_dict_cursor(conn)
        cur.execute("SELECT id, business_id FROM users WHERE id = %s", (payload.get("userId"),))
        row = cur.fetchone()
        if row:
            biz = ensure_business_id(cur, row["id"], row.get("business_id"), payload.get("role"))
            conn.commit()
        cur.close(); conn.close()

    if not biz and payload.get("role") != "super_admin":
        raise HTTPException(status_code=400, detail="User business scope missing")

    new_token = generate_access_token({
        "userId": payload["userId"],
        "email": payload.get("email", ""),
        "role": payload.get("role", "customer"),
        "businessId": biz,
    })
    return {"success": True, "data": {"accessToken": new_token}}


@router.post("/google")
async def google_auth(body: GoogleBody):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": body.code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": "postmessage",
                "grant_type": "authorization_code",
            },
        )

    if not token_res.is_success:
        raise HTTPException(status_code=400, detail=f"Google token exchange failed: {token_res.text}")

    tokens = token_res.json()
    id_token_str = tokens.get("id_token")
    if not id_token_str:
        raise HTTPException(status_code=400, detail="No ID token returned")

    try:
        id_payload = jwt.decode(id_token_str, options={"verify_signature": False})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID token")

    google_email = id_payload.get("email")
    if not google_email:
        raise HTTPException(status_code=400, detail="No email in Google token")

    conn = get_conn()
    cur = get_dict_cursor(conn)

    target_user_id = body.userId
    if not target_user_id:
        cur.execute("SELECT * FROM users WHERE email = %s", (google_email,))
        existing = cur.fetchone()
        if existing:
            target_user_id = existing["id"]
            ensure_business_id(cur, target_user_id, existing.get("business_id"), existing.get("role"))
        else:
            new_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO users (id, business_id, email, password_hash, first_name, last_name, role, google_email) "
                "VALUES (%s, %s, %s, 'GOOGLE_AUTH_PLACEHOLDER', %s, %s, 'customer', %s)",
                (new_id, DEFAULT_BUSINESS_ID, google_email,
                 id_payload.get("given_name", ""), id_payload.get("family_name", ""), google_email),
            )
            target_user_id = new_id

    if tokens.get("refresh_token"):
        cur.execute(
            "UPDATE users SET google_refresh_token = %s, google_email = %s, updated_at = NOW() WHERE id = %s",
            (tokens["refresh_token"], google_email, target_user_id),
        )
    conn.commit()

    cur.execute("SELECT * FROM users WHERE id = %s", (target_user_id,))
    user = cur.fetchone()
    biz = ensure_business_id(cur, user["id"], user.get("business_id"), user.get("role"))
    conn.commit(); cur.close(); conn.close()

    payload = {"userId": user["id"], "email": user["email"], "role": user["role"], "businessId": biz}
    return {
        "success": True,
        "data": {
            "user": {
                "id": user["id"],
                "email": user["email"],
                "firstName": user["first_name"],
                "businessId": biz,
                "google_connected": bool(user.get("google_refresh_token") or tokens.get("refresh_token")),
            },
            "accessToken": generate_access_token(payload),
            "refreshToken": generate_refresh_token(payload),
        },
    }
