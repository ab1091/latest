import json
import logging
from typing import Optional, Dict

import redis.asyncio as aioredis

from core.config import REDIS_URL

logger  = logging.getLogger(__name__)
_TTL    = 1800  # 30 minutes
_PREFIX = "sess:"

_redis: aioredis.Redis = None


def _r() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def get(call_sid: str) -> Optional[Dict]:
    data = await _r().get(f"{_PREFIX}{call_sid}")
    return json.loads(data) if data else None


async def create(call_sid: str, system_prompt: str, business_id: str = "") -> Dict:
    session = {
        "history":     [{"role": "system", "content": system_prompt}],
        "business_id": business_id,
    }
    await _r().setex(f"{_PREFIX}{call_sid}", _TTL, json.dumps(session))
    return session


async def append(call_sid: str, role: str, content: str):
    key  = f"{_PREFIX}{call_sid}"
    data = await _r().get(key)
    if not data:
        return
    session = json.loads(data)
    session["history"].append({"role": role, "content": content})
    await _r().setex(key, _TTL, json.dumps(session))


async def pop(call_sid: str) -> Optional[Dict]:
    key  = f"{_PREFIX}{call_sid}"
    data = await _r().get(key)
    if not data:
        return None
    await _r().delete(key)
    return json.loads(data)


def cleanup():
    pass  # Redis TTL handles expiry automatically
