"""Shared utilities — JWT auth helpers."""
from fastapi import Request, HTTPException
from jose import jwt, JWTError

from core.config import JWT_SECRET


def get_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_admin(request: Request) -> dict:
    user = get_user(request)
    if user.get("role") not in ("admin", "staff", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_super_admin(request: Request) -> dict:
    user = get_user(request)
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user
