from fastapi import Request, HTTPException
from jose import jwt, JWTError
from core.config import JWT_SECRET, DEFAULT_BUSINESS_ID


def get_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_business_id(request: Request) -> str:
    """
    Business scoping for the current request. A super_admin has no home
    business (business_id is NULL) and must select one agency to act
    within via the X-Business-Id header — every other role is scoped to
    their own business_id exactly as before.
    """
    payload = get_user(request)
    if payload.get("role") == "super_admin":
        impersonated = request.headers.get("X-Business-Id")
        if not impersonated:
            raise HTTPException(status_code=400, detail="super_admin must select an agency (X-Business-Id header)")
        return impersonated
    return payload.get("businessId") or DEFAULT_BUSINESS_ID


def get_scope(request: Request) -> dict:
    payload = get_user(request)
    role = payload.get("role", "customer")
    return {
        "user_id":     payload.get("userId"),
        "business_id": get_business_id(request),
        "role":        role,
        "is_admin":    role in ("admin", "super_admin"),
        "is_staff":    role in ("admin", "staff", "super_admin"), # admin + staff (can access admin pages)
        "is_super_admin": role == "super_admin",
    }


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
