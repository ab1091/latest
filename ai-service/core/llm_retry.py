"""
Shared retry/backoff wrapper for outbound OpenAI calls.

Paid API account — two things matter: don't silently eat a transient blip as
a low-quality canned fallback reply to a real lead (reliability), and don't
retry forever burning quota on a request that will never succeed (cost).

Only rate-limit/server errors (429, 5xx) and timeouts are retried, with
exponential backoff (honoring OpenAI's Retry-After header when present).
Any other error (400 bad request, 401 bad key, etc.) raises immediately on
the first attempt — retrying those wastes calls for no chance of success.
"""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


async def post_with_retry(client: httpx.AsyncClient, url: str, *, headers: dict, json: dict,
                           max_attempts: int = 3, base_delay: float = 1.0, label: str = "") -> httpx.Response:
    tag = f" {label}" if label else ""
    delay = base_delay
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await client.post(url, headers=headers, json=json)
        except httpx.TimeoutException:
            if attempt == max_attempts:
                raise
            logger.warning(f"[llm_retry]{tag} timeout — retry {attempt}/{max_attempts} in {delay:.0f}s")
            await asyncio.sleep(delay)
            delay *= 2
            continue

        if resp.status_code in _RETRYABLE_STATUS and attempt < max_attempts:
            wait = delay
            retry_after = resp.headers.get("retry-after")
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    pass
            logger.warning(f"[llm_retry]{tag} HTTP {resp.status_code} — retry {attempt}/{max_attempts} in {wait:.0f}s")
            await asyncio.sleep(wait)
            delay *= 2
            continue

        resp.raise_for_status()
        return resp

    resp.raise_for_status()
    return resp
