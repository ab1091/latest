"""
BlueBubbles inbound webhook — replaces Claw Messenger's websocket listener
as the inbound transport for the "sms" channel. Deliberately still tagged
"sms" everywhere downstream (leads.preferred_channel, conversations.channel,
the workflow/callback-scheduler channel allow-lists, crm_settings'
channels_enabled) — this is a transport swap behind the existing channel,
not a new channel type, so none of that plumbing needs touching.
"""
import logging

from fastapi import APIRouter, Request

from core.bluebubbles import normalize_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imessage")

# Numbers reachable on THIS Mac's own signed-in iMessage account (System
# Settings → Apple ID → iMessage → "You can be reached at"). Messaging one
# of these from BlueBubbles for internal testing triggers Apple's
# self-echo behavior — see the comment in imessage_webhook() below. Update
# this list if the account's reachable numbers change.
SELF_NUMBERS = {normalize_phone("+17373283529"), normalize_phone("+17373283423")}


@router.post("/webhook")
async def imessage_webhook(request: Request):
    payload = await request.json()
    if payload.get("type") != "new-message":
        return {"status": "ignored"}

    data = payload.get("data") or {}
    if data.get("isFromMe"):
        return {"status": "ignored-self"}

    # Self-messaging edge case: texting a number on the SAME Apple ID as this
    # Mac (e.g. internal testing) makes Apple's iMessage servers echo the
    # sent message back as a second, separate "received" row that genuinely
    # has isFromMe=false at the Messages.app database level — the isFromMe
    # check above can't catch this because, from Messages.app's own data,
    # it really is marked as received. A real customer's phone is never on
    # this account, so this only fires for self/internal-number testing.
    from_addr = ((data.get("handle") or {}).get("address") or "").strip()
    from_service = ((data.get("handle") or {}).get("service") or "").strip()
    if from_service.lower() == "imessage" and normalize_phone(from_addr) in SELF_NUMBERS:
        logger.info(f"[imessage] dropped self-account echo from {from_addr!r}")
        return {"status": "ignored-self-echo"}

    text = (data.get("text") or "").strip()
    address = ((data.get("handle") or {}).get("address") or "").strip()
    if not text or not address:
        return {"status": "empty"}

    if "@" in address:
        # Apple-ID/email sender — the lead model is entirely phone-keyed
        # (leads.phone), no email-keyed lookup path exists. Not worth
        # shoehorning in for v1; drop it rather than silently mis-file it
        # under a garbage "phone" value.
        logger.info(f"[imessage] dropped email-address sender: {address!r}")
        return {"status": "unsupported-sender"}

    from_phone = normalize_phone(address)
    logger.info(f"[imessage] inbound from {from_phone}: {text[:80]!r}")

    from api.sms.router import _handle_inbound_message
    await _handle_inbound_message(from_phone, text, "sms")
    return {"status": "ok"}
