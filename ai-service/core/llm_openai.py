"""
Shared OpenAI chat-completion helper — used anywhere a call needs to be made
outside of api/sms/router.py (which keeps its own copy since it has both
sync and async call sites already).
"""
import httpx

from core.config import OPENAI_API_KEY
from core.llm_retry import post_with_retry

DEFAULT_MODEL = "gpt-4o-mini"


def _openai_messages(contents, system_instruction: str = "") -> list:
    messages = [{"role": "system", "content": system_instruction}] if system_instruction else []
    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    else:
        for turn in contents:
            role = "assistant" if turn["role"] == "model" else "user"
            messages.append({"role": role, "content": turn["parts"][0]["text"]})
    return messages


async def openai_generate(contents, system_instruction: str = "", model: str = None,
                           max_tokens: int = 200, temperature: float = 0.7, json_mode: bool = False) -> str:
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": _openai_messages(contents, system_instruction),
        "max_tokens": max_tokens, "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await post_with_retry(
            client, "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload, label="core.llm_openai",
        )
    return resp.json()["choices"][0]["message"]["content"].strip()
