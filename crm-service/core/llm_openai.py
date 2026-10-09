"""
Shared OpenAI chat-completion client.

core/lead_summary.py's AI deal-summary generation and routers/leads.py's
config check both depend on it.
"""
import os
import time
import logging

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def openai_generate(contents, system_instruction: str = "", max_tokens: int = 200,
                     temperature: float = 0.7, json_mode: bool = False) -> str:
    """
    contents: a plain string, or a list of Gemini-style turns
    ({"role": "user"|"model", "parts": [{"text": ...}]}) — normalized to
    OpenAI-style chat messages.
    """
    messages = [{"role": "system", "content": system_instruction}] if system_instruction else []
    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    else:
        for turn in contents:
            role = "assistant" if turn["role"] == "model" else "user"
            messages.append({"role": role, "content": turn["parts"][0]["text"]})

    payload = {"model": OPENAI_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # The only caller (lead_summary.generate_and_save_summary) runs inside an
    # already-open DB transaction holding a lock on the leads row — keep the
    # retry budget short (2 attempts, short backoff) so a transient OpenAI
    # error doesn't hold that lock open for long.
    delay = 0.5
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json=payload, timeout=20,
            )
        except httpx.TimeoutException:
            if attempt == max_attempts:
                raise
            logger.warning(f"[llm_openai] timeout — retry {attempt}/{max_attempts} in {delay:.1f}s")
            time.sleep(delay)
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
            logger.warning(f"[llm_openai] HTTP {resp.status_code} — retry {attempt}/{max_attempts} in {wait:.1f}s")
            time.sleep(wait)
            delay *= 2
            continue

        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
