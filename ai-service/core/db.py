import os
import logging
import threading
import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

DATABASE_URL        = os.environ.get("DATABASE_URL", "")
DEFAULT_BUSINESS_ID = os.environ.get("DEFAULT_BUSINESS_ID", "bus_001")

_pool: psycopg2.pool.ThreadedConnectionPool = None
# Guards _pool's lazy init. Inbound SMS handling now runs each message on
# its own real OS thread (see core/claw_messenger.py's _handle_inbound_frame)
# so multiple conversations' first-ever DB calls can genuinely race here —
# without this lock, two threads could both see _pool is None and each
# construct their own ThreadedConnectionPool, silently leaking one of them
# (its connections never returned, never closed). ThreadedConnectionPool
# itself is safe to share across threads once created; this only protects
# the one-time creation.
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                # The DB server's own default session timezone is America/Los_Angeles
                # (confirmed via SHOW timezone) — every NOW() call and every naive
                # `timestamp without time zone` column was storing plain Pacific
                # wall-clock numbers with no tz marker attached. Neither backend ever
                # overrode this, so the frontend (parsing those naive strings as if
                # they were already local time) displayed times up to ~12h off from
                # reality — confirmed live against a call that had just ended.
                # Forcing every pooled connection to UTC fixes this going forward;
                # it does NOT retroactively correct already-stored rows, which still
                # hold Pacific-labeled values — that's a separate, deliberately
                # unstarted data migration (real historical data, needs sign-off).
                #
                # Keepalives: a pooled connection idle long enough goes
                # silently dead with no error until the next request grabs
                # it, which then hangs before failing with a DB timeout —
                # confirmed live. Same fix already proven for
                # claw_messenger.py's dedicated connection and crm-service's
                # pool.
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    2, 20, DATABASE_URL, options="-c TimeZone=UTC",
                    keepalives=1, keepalives_idle=15, keepalives_interval=5, keepalives_count=3,
                )
                logger.info("[db] Connection pool initialized (min=2, max=20, tz=UTC, keepalives=on)")
    return _pool


class _PooledConn:
    """Wraps a pooled connection so .close() returns it to the pool."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        # MUST end the transaction before returning to the pool. psycopg2
        # connections default to autocommit=False, so even a read-only
        # SELECT leaves an open transaction — and an open transaction holds
        # its MVCC snapshot forever, regardless of how much later "idle"
        # time passes. A connection returned here without rollback/commit
        # goes back into the pool still inside that transaction; the next
        # caller who happens to draw it from the pool inherits it and keeps
        # querying against that same frozen snapshot, seeing zero new
        # commits from anywhere else — silently, with no error, for as long
        # as that connection keeps getting reused. Confirmed live: exactly
        # this made the callback poller (core/callback_scheduler.py) run
        # every 30s and log "executed successfully" while never once seeing
        # newly-queued scheduled_callbacks rows — it had been polling a
        # stale snapshot. rollback() is always safe here even when nothing
        # was written; it just ends the transaction cleanly.
        try:
            self._conn.rollback()
        except Exception:
            pass
        try:
            _get_pool().putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass


def get_conn() -> _PooledConn:
    return _PooledConn(_get_pool().getconn())


def get_dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
