import os
import logging

logger = logging.getLogger(__name__)


def _get(key: str, default: str = "") -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    placeholder = default if default else f"{key}_not_set"
    logger.warning(f"[config] {key} not set — using: '{placeholder}'")
    return placeholder


DATABASE_URL        = _get("DATABASE_URL")
JWT_SECRET          = _get("JWT_SECRET", "your-secret-key")
DEFAULT_BUSINESS_ID = _get("DEFAULT_BUSINESS_ID", "bus_001")
VOICE_BOT_URL       = _get("VOICE_BOT_URL", "http://ai-service:8000")
REDIS_URL           = _get("REDIS_URL", "redis://localhost:6379/0")

TWILIO_ACCOUNT_SID      = _get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN       = _get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER      = _get("TWILIO_FROM_NUMBER")
TWILIO_WHATSAPP_FROM    = _get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
OPENAI_API_KEY          = _get("OPENAI_API_KEY")
