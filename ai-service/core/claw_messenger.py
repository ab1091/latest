"""
Claw Messenger client — persistent WebSocket SMS/iMessage transport,
replacing Sendblue's stateless REST call.

Protocol (empirically verified live, not just from docs — see the
conversation history for the actual test sends/replies that confirmed this):
  - wss://claw-messenger.onrender.com/ws?key=API_KEY
  - Send:    {"type":"send","id":<str>,"to":<phone>,
              "parts":[{"type":"text","value":<body>}],"service":"SMS"}
  - Result:  {"type":"send.result","id":<same id>,"ok":bool,"messageId":...}
             — empirically, this ONLY ever arrives for a same-turn
             rejection (e.g. bad phone format). A valid send gets no
             completion frame with our id at all — see send_message()'s
             docstring for how that's handled.
  - Status:  {"type":"status","messageId":<Claw's own id>,
              "status":"delivered"|"read",...} — async delivery/read
             confirmation for a valid send, keyed by Claw's own messageId,
             not the id we sent — not correlated back to a specific send.
  - Inbound: {"type":"message","from":<phone>,"text":<body>,...} pushed over
             the same socket — there is no webhook for inbound.
  - The server sends application-level {"type":"ping"} frames and expects an
    application-level {"type":"pong"} reply, or it closes the connection as
    "Inactive" (confirmed live — a connection that didn't pong got dropped
    within under two minutes even though the transport-level WS connection
    was healthy).

Why this file is more than a thin client: this service runs multiple uvicorn
worker processes (main.py: workers = max(2, cpu_count()) whenever DEBUG isn't
set, which is the default — confirmed 4 live processes for one `main.py`
invocation). Verified live that Claw Messenger does NOT reject a second
simultaneous connection on the same key (opened two at once, both stayed
open for the full test window) — so if every worker opened its own
connection, a single inbound text could get pulled down and replied to once
per worker, i.e. a customer getting the same bot reply N times. To avoid
that: exactly one worker becomes the "owner" via a Postgres advisory lock
and is the only one that ever opens the socket. Every worker (owner or not)
sends the same way — push a job onto a Redis list, block for the result on a
per-id key — so send_message() doesn't need to know or care which process
holds the connection, and ownership can silently fail over to another worker
(the lock releases automatically if the owner's connection dies) without any
caller-visible change.
"""
import asyncio
import json
import logging
import threading
import uuid

import psycopg2
import redis.asyncio as aioredis
import websockets

from core.config import CLAW_MESSENGER_API_KEY
from core.db import DATABASE_URL

logger = logging.getLogger(__name__)

WS_URL = f"wss://claw-messenger.onrender.com/ws?key={CLAW_MESSENGER_API_KEY}"
_ADVISORY_LOCK_ID = 847362951  # arbitrary, fixed — just needs to not collide with other lock usage

_OUTBOX_KEY = "claw:outbox"
_SEND_TIMEOUT = 20  # seconds a caller will wait for a send.result before giving up
_SEND_FRAME_TIMEOUT = 10  # seconds to wait for ws.send() itself before treating the connection as dead
_ACTIVITY_TIMEOUT = 90  # seconds with zero received frames (including server pings) before forcing a reconnect

_owner_task: asyncio.Task | None = None
_stopping = False

# Thread-local, not a single global — each inbound message now runs its own
# fresh event loop on its own worker thread (see _handle_inbound_frame), so
# a single shared aioredis.Redis client would get used from multiple event
# loops at once. redis-py's async client binds its connection/transport to
# whichever loop first touches it; reused from a second loop that's exactly
# the kind of bug that only shows up under real concurrent traffic, not a
# single-conversation test. One client per thread (and therefore per loop,
# since each worker thread here only ever runs one loop for its lifetime)
# keeps every loop's usage isolated.
_redis_local = threading.local()


def _r() -> aioredis.Redis:
    if not hasattr(_redis_local, "redis"):
        from core.config import REDIS_URL
        # socket_timeout=None is required for BLPOP — redis-py's default
        # client-side socket read timeout is shorter than the BLPOP timeout
        # we pass, so without this the client raises its own TimeoutError
        # mid-wait instead of letting BLPOP's own timeout return None
        # cleanly (found live: this was firing every ~5s and tearing down
        # the owner connection/lock on every single cycle).
        _redis_local.redis = aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=None)
    return _redis_local.redis


# ── Public API — used by every caller, owner worker or not ────────────────────

async def send_message(to: str, body: str, service: str = "SMS", _retries: int = 1) -> dict:
    """Returns a dict with a 'sid' key (normalized from Claw Messenger's
    'messageId') so callers like core/sms.py don't need any shape changes.

    Claw Messenger's ack behavior turned out to be asymmetric (confirmed
    live across many real sends): a same-turn rejection (e.g. a malformed
    phone number) gets an immediate {"type":"send.result","id":...,"ok":
    false,...} — but a VALID send never gets a completion frame with our id
    at all, only async {"type":"status",...} delivery/read frames later,
    keyed by Claw's own messageId, uncorrelated to our id. Blocking the
    full timeout waiting for an ack that structurally never arrives made
    every successful send get reported (and logged/saved) as a failure.
    So: poll in short slices, and treat "the job was actually handed to
    the live socket, and no rejection followed" as success instead of
    requiring an ack that only ever shows up for the error case.

    _retries: how many additional attempts to make if a whole attempt times
    out with no explanation in the connection-lifecycle logs (no drop, no
    ws.send() timeout — see claw:inbound investigation). Observed live
    twice in one session with nothing else in the logs pointing to a cause,
    so a bare retry (fresh id, fresh outbox job) is worth it before this
    propagates up as a hard failure — a second attempt costs one more
    _SEND_TIMEOUT window at most, and this only runs on the already-slow
    error path, not on the common case."""
    if not CLAW_MESSENGER_API_KEY:
        raise RuntimeError("Claw Messenger not configured")

    msg_id = uuid.uuid4().hex
    job = {"id": msg_id, "to": to, "body": body, "service": service}
    r = _r()
    await r.rpush(_OUTBOX_KEY, json.dumps(job))

    result_key = f"claw:result:{msg_id}"
    sent_key = f"claw:sent:{msg_id}"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + _SEND_TIMEOUT
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            if _retries > 0:
                logger.warning(f"[claw] send timed out for id={msg_id} to={to} — retrying ({_retries} left)")
                return await send_message(to, body, service, _retries=_retries - 1)
            raise RuntimeError(f"Claw Messenger send timed out waiting for a result (id={msg_id})")
        popped = await r.blpop(result_key, timeout=max(0.1, min(2, remaining)))
        if popped:
            data = json.loads(popped[1])
            if not data.get("ok"):
                raise RuntimeError(f"Claw Messenger error: {data.get('error')}")
            data["sid"] = data.get("messageId")
            return data
        if await r.get(sent_key):
            return {"sid": None, "ok": True}


# ── Owner election + connection loop ───────────────────────────────────────────

def _try_acquire_owner_lock() -> psycopg2.extensions.connection | None:
    """Blocking — call via asyncio.to_thread. Returns a dedicated, held-open
    connection if the lock was acquired (advisory locks are session-scoped —
    releasing/returning this connection anywhere releases the lock), else None.

    Confirmed live: a worker that dies abruptly (container recycle, OOM-kill —
    anything that doesn't cleanly close the socket) leaves Postgres holding
    this connection as "idle" indefinitely, since without keepalives libpq
    has no way to notice the peer is gone. Found a connection from this exact
    lock still "idle" 5 days after its worker died, silently blocking every
    other worker from ever taking over ownership — no new SMS/call outcome
    could be sent that whole time with no visible error, just growing send
    timeouts. Keepalives below bound that to under a minute instead of
    indefinite: Postgres now notices a dead peer and drops the lock quickly
    so a healthy worker can take over on its own, no manual restart needed.
    """
    conn = psycopg2.connect(
        DATABASE_URL, options="-c TimeZone=UTC",
        keepalives=1, keepalives_idle=15, keepalives_interval=5, keepalives_count=3,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (_ADVISORY_LOCK_ID,))
    got = cur.fetchone()[0]
    cur.close()
    if got:
        return conn
    conn.close()
    return None


async def _pump_outbox(ws, send_lock: asyncio.Lock):
    """Owner-only: relay jobs any worker (including this one) pushed onto the
    shared Redis outbox, over this worker's live WebSocket connection.

    ws.send() is wrapped in a timeout — confirmed live that a silently wedged
    connection (TCP-level stall, no close frame, so nothing else here ever
    notices) can make a bare ws.send() hang forever. Since this loop is
    strictly serial, one stuck send silently blocks every message queued
    after it too, with zero logging — a job popped right as this happens is
    gone: no error, no retry, no trace. On timeout we requeue the job at the
    front of the outbox (so it's the very next thing sent once reconnected)
    and raise, which propagates out through the asyncio.gather() in
    _owner_session() and lets _run()'s reconnect loop tear down and retry."""
    r = _r()
    while True:
        popped = await r.blpop(_OUTBOX_KEY, timeout=5)
        if not popped:
            continue
        job = json.loads(popped[1])
        payload = {
            "type": "send",
            "id": job["id"],
            "to": job["to"],
            "parts": [{"type": "text", "value": job["body"]}],
            "service": job.get("service", "SMS"),
        }
        try:
            async with send_lock:
                await asyncio.wait_for(ws.send(json.dumps(payload)), timeout=_SEND_FRAME_TIMEOUT)
        except asyncio.TimeoutError:
            await r.lpush(_OUTBOX_KEY, popped[1])
            logger.warning(f"[claw] ws.send() timed out for id={job['id']} — requeued, forcing reconnect")
            raise
        # Marks the frame as actually handed to the live socket — see
        # send_message()'s docstring for why this (not a completion ack)
        # is what determines success for a valid send.
        await r.set(f"claw:sent:{job['id']}", "1", ex=60)
        logger.info(f"[claw] sent id={job['id']} to={job['to']}")


def _run_inbound_in_new_loop(from_phone: str, text: str):
    """Runs on its own worker thread with its OWN fresh event loop —
    deliberately not just `await`ed as a same-loop task. Every DB call in
    this codebase goes through psycopg2, which is synchronous: a plain
    asyncio.create_task on the shared listener loop still lets one
    conversation's blocking cur.execute() calls freeze the entire event
    loop, including every OTHER concurrent conversation and the listener's
    own ability to read the next inbound frame. Confirmed directly: two
    synthetic messages from different leads sent ~50ms apart still had a
    ~4.8s gap before the second one's pipeline even started, because the
    first one's synchronous DB work held the only event loop hostage the
    whole time. A real worker thread isn't blocked by another thread's
    blocking call (psycopg2's ThreadedConnectionPool is explicitly built
    for exactly this), so this actually gets two leads' conversations
    running in parallel instead of queued behind each other.
    asyncio.to_thread() runs this on a pool thread; asyncio.run() gives
    that thread its own loop for _handle_inbound_message's own internal
    awaits (LLM calls, crm-service calls, etc.)."""
    from api.sms.router import _handle_inbound_message
    asyncio.run(_handle_inbound_message(from_phone, text, "sms"))


async def _handle_inbound_frame(from_phone: str, text: str):
    """Dispatches one inbound message's full reply pipeline onto its own
    worker thread (see _run_inbound_in_new_loop) instead of running inline
    on the listener's loop — this is what create_task in _listen schedules,
    so the listener itself returns to reading the next frame immediately
    rather than waiting for asyncio.to_thread to finish. An exception here
    would otherwise be an unretrieved Task exception, logged noisily by
    asyncio's default handler but easy to lose track of, so it's still
    caught and logged explicitly."""
    try:
        await asyncio.to_thread(_run_inbound_in_new_loop, from_phone, text)
    except Exception as e:
        logger.error(f"[claw] inbound handling failed for {from_phone}: {e}")


async def _listen(ws, send_lock: asyncio.Lock, last_activity: list):
    """Owner-only: handle every frame the server pushes — pings, send
    results (published back to whichever worker is waiting on that id), and
    genuine inbound messages (there is no webhook for these; this socket
    IS the inbound channel).

    last_activity (a shared 1-element list, mutated here) feeds _watchdog —
    a receive-side stall (nothing arriving at all, not even the server's own
    keepalive pings) is a different failure mode than a stuck ws.send(), and
    isn't caught by that timeout alone."""
    r = _r()
    async for raw in ws:
        last_activity[0] = asyncio.get_event_loop().time()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"[claw] non-JSON frame: {raw!r}")
            continue

        frame_type = data.get("type")
        if frame_type == "ping":
            async with send_lock:
                await ws.send(json.dumps({"type": "pong"}))

        elif frame_type == "send.result":
            logger.info(f"[claw] send.result for id={data.get('id')} ok={data.get('ok')} status={data.get('status')}")
            result_key = f"claw:result:{data.get('id')}"
            await r.rpush(result_key, json.dumps(data))
            await r.expire(result_key, 60)

        elif frame_type == "message":
            from_phone = (data.get("from") or "").strip()
            text = (data.get("text") or "").strip()
            if not from_phone or not text:
                # Diagnostic: log the raw frame whenever a "message" frame
                # gets dropped here (e.g. no text — a pure audio/attachment
                # message) so we can see what fields Claw Messenger actually
                # sends for non-text content instead of losing it silently.
                logger.info(f"[claw] dropped message frame (no from/text) raw={raw[:500]!r}")
                continue
            logger.info(f"[claw] inbound from {from_phone}: {text[:80]!r}")
            # Fire-and-forget, not awaited inline. This is the single owner
            # connection's ONE read loop — awaiting the full reply pipeline
            # here (several sequential LLM calls, crm-service round trips,
            # the actual send, then post-reply bookkeeping) used to block
            # this loop from reading the NEXT frame until all of that
            # finished. With more than one lead texting in around the same
            # time, every conversation after the first queued up behind
            # however long the one currently running took — a text platform
            # has many concurrent conversations, unlike a single voice call,
            # so serializing them here made replies look far slower than the
            # actual per-message work justified. asyncio.create_task lets
            # this frame's handling run concurrently while the loop moves on
            # to the next one immediately.
            asyncio.create_task(_handle_inbound_frame(from_phone, text))

        else:
            logger.info(f"[claw] unhandled frame type={frame_type!r}: {raw[:200]}")


async def _watchdog(last_activity: list):
    """Owner-only: forces a reconnect if literally nothing has arrived —
    not even the server's own {"type":"ping"} — for _ACTIVITY_TIMEOUT
    seconds. Their side is documented to drop us within ~2 minutes if we
    stop ponging, but that assumes frames can flow at all; a genuinely
    wedged connection can go silent in both directions with neither side's
    keepalive ever firing. This is the client-side backstop for that."""
    while True:
        await asyncio.sleep(10)
        idle = asyncio.get_event_loop().time() - last_activity[0]
        if idle > _ACTIVITY_TIMEOUT:
            raise RuntimeError(f"no frames received for {idle:.0f}s — connection presumed wedged")


async def _owner_session():
    """One connect-listen-until-dropped cycle. Raises on disconnect so the
    caller's reconnect loop can back off and retry."""
    async with websockets.connect(WS_URL, open_timeout=15) as ws:
        logger.info("[claw] connected as owner")
        send_lock = asyncio.Lock()
        last_activity = [asyncio.get_event_loop().time()]
        await asyncio.gather(
            _listen(ws, send_lock, last_activity),
            _pump_outbox(ws, send_lock),
            _watchdog(last_activity),
        )


async def _run():
    """Retries owner election forever. A worker that doesn't hold the lock
    just keeps checking periodically — if the current owner's process dies,
    Postgres releases the advisory lock automatically and the next check
    here picks it up, so failover needs no explicit handoff."""
    global _stopping
    backoff = 1
    while not _stopping:
        lock_conn = await asyncio.to_thread(_try_acquire_owner_lock)
        if lock_conn is None:
            await asyncio.sleep(10)
            continue

        logger.info("[claw] acquired owner lock")
        try:
            backoff = 1
            while not _stopping:
                try:
                    await _owner_session()
                except (websockets.exceptions.WebSocketException, OSError) as e:
                    logger.warning(f"[claw] connection dropped ({e}) — reconnecting in {backoff}s")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                except Exception:
                    logger.exception("[claw] unexpected error in owner session — reconnecting in {}s".format(backoff))
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
        finally:
            # Releasing/closing this connection drops the advisory lock, so
            # another worker can take over as owner.
            await asyncio.to_thread(lock_conn.close)
            logger.info("[claw] released owner lock")


def start_claw_messenger():
    global _owner_task, _stopping
    _stopping = False
    _owner_task = asyncio.create_task(_run())
    logger.info("[claw_messenger] Started — election + connection loop running in background")


async def stop_claw_messenger():
    global _owner_task, _stopping
    _stopping = True
    if _owner_task:
        _owner_task.cancel()
        try:
            await _owner_task
        except asyncio.CancelledError:
            pass
        _owner_task = None
