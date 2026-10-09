import os
import logging

logger = logging.getLogger(__name__)


def _get(key: str, default: str = "") -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    placeholder = default if default else f"{key}_not_found"
    logger.warning(f"[config] ⚠️  {key} is not set — using: '{placeholder}'")
    return placeholder


# ── App ───────────────────────────────────────────────────────────────────────
JWT_SECRET          = _get("JWT_SECRET",          "your-secret-key")
DEFAULT_BUSINESS_ID = _get("DEFAULT_BUSINESS_ID", "bus_001")
FRONTEND_URL        = _get("FRONTEND_URL",        "http://localhost:3000")

# ── Twilio (voice calls + WhatsApp only — SMS moved to Claw Messenger) ────────
TWILIO_ACCOUNT_SID   = _get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN    = _get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER   = _get("TWILIO_FROM_NUMBER")
TWILIO_WHATSAPP_FROM = _get("TWILIO_WHATSAPP_FROM")
TWIML_BASE_URL     = _get("TWILIO_TWIML_BASE_URL")

# ── Claw Messenger (SMS/iMessage) ──────────────────────────────────────────────
# Being replaced by BlueBubbles below as the active transport for the "sms"
# channel — see core/bluebubbles.py and _send_sms in api/sms/router.py. Left
# wired but dormant rather than deleted, so it's a one-line revert if needed.
CLAW_MESSENGER_API_KEY = _get("CLAW_MESSENGER_API_KEY")

# ── BlueBubbles (iMessage, replacing Claw Messenger) ───────────────────────────
# A local REST API on a Mac running Messages.app + BlueBubbles Server — only
# reachable from a machine on the same network as that Mac (or a tunnel to
# it), so this only works when ai-service itself runs locally for now.
BB_SERVER_URL  = _get("BB_SERVER_URL", "http://localhost:1234")
BB_PASSWORD    = _get("BB_PASSWORD")
BB_SEND_METHOD = _get("BB_SEND_METHOD", "apple-script")

# ── Google Calendar ───────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID       = _get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET   = _get("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN   = _get("GOOGLE_CALENDAR_REFRESH_TOKEN")
AGENCY_CALENDAR_EMAIL  = _get("AGENCY_CALENDAR_EMAIL", "shieldsquadagency@gmail.com")

# ── HubSpot ───────────────────────────────────────────────────────────────────
HUBSPOT_ACCESS_TOKEN  = _get("HUBSPOT_ACCESS_TOKEN")
HUBSPOT_CLIENT_ID     = _get("HUBSPOT_CLIENT_ID")
HUBSPOT_CLIENT_SECRET = _get("HUBSPOT_CLIENT_SECRET")
HUBSPOT_REDIRECT_URI  = _get("HUBSPOT_REDIRECT_URI")


# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = _get("OPENAI_API_KEY")

# ── Groq (used as the OpenAI-compatible fallback when OPENAI_API_KEY is unset) ─
GROQ_API_KEY = _get("GROQ_API_KEY")

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL = _get("REDIS_URL", "redis://localhost:6379/0")

# ── Webhooks ──────────────────────────────────────────────────────────────────
VAPI_WEBHOOK_SECRET  = _get("VAPI_WEBHOOK_SECRET")
VAPI_ASSISTANT_ID    = _get("VAPI_ASSISTANT_ID")
VAPI_PHONE_NUMBER_ID = _get("VAPI_PHONE_NUMBER_ID")
VAPI_API_KEY         = _get("VAPI_API_KEY")
REMINDER_TOOL_SECRET = _get("REMINDER_TOOL_SECRET")

# ── Microsoft Outlook Calendar ────────────────────────────────────────────────
OUTLOOK_CLIENT_ID     = _get("OUTLOOK_CLIENT_ID")
OUTLOOK_CLIENT_SECRET = _get("OUTLOOK_CLIENT_SECRET")
OUTLOOK_TENANT_ID     = _get("OUTLOOK_TENANT_ID")
OUTLOOK_REDIRECT_URI  = _get("OUTLOOK_REDIRECT_URI", "http://localhost:8000/api/integrations/outlook/callback")

# ── CRM Service ───────────────────────────────────────────────────────────────
CRM_SERVICE_URL = _get("CRM_SERVICE_URL", "http://localhost:8001")

# ── Azure Blob Storage (call recordings) ────────────────────────────────────
AZURE_STORAGE_ACCOUNT_NAME = _get("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY  = _get("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_STORAGE_CONTAINER    = _get("AZURE_STORAGE_CONTAINER", "call-recordings")
