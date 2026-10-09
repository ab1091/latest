import logging
import threading
import psycopg2
import psycopg2.extras
import psycopg2.pool
from core.config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool = None
# Guards _pool's lazy init. This service's route handlers are plain `def`,
# not `async def` — Starlette runs those in its own worker-thread pool
# automatically, so multiple requests can already reach this function on
# genuinely different OS threads at once (this was true before ai-service's
# own concurrency fix too, just harder to trigger before real concurrent
# inbound traffic existed). Without this lock, two threads could both see
# _pool is None and each construct their own ThreadedConnectionPool,
# silently leaking one of them. ThreadedConnectionPool itself is safe to
# share across threads once created; this only protects the one-time
# creation.
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                # See matching comment in ai-service/core/db.py — the DB server's
                # default session timezone is America/Los_Angeles, so every NOW()/
                # naive timestamp column was storing Pacific wall-clock values with
                # no tz marker, which the frontend then misread as already-local
                # time. Forcing UTC here fixes it going forward for every row this
                # service writes (leads, appointments, tasks, etc.) — historical
                # rows are unaffected, that's a separate migration.
                # Keepalives: see matching, confirmed-live comment in
                # ai-service/core/db.py — a pooled connection idle long enough goes
                # silently dead with no error until the next request grabs it,
                # which then hangs before failing with a DB timeout. Same fix
                # already proven for claw_messenger.py's dedicated connection.
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    2, 20, DATABASE_URL, options="-c TimeZone=UTC",
                    keepalives=1, keepalives_idle=15, keepalives_interval=5, keepalives_count=3,
                )
                logger.info("[db] Pool initialized (min=2, max=20, tz=UTC, keepalives=on)")
    return _pool


class _PooledConn:
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
        # MUST end the transaction before returning to the pool — see the
        # matching, confirmed-live comment in ai-service/core/db.py. Without
        # this, a connection released after a read-only SELECT goes back
        # into the pool still inside an open transaction, frozen on that
        # transaction's MVCC snapshot; the next caller to draw it from the
        # pool inherits that stale snapshot and silently stops seeing any
        # newer commits from other connections, with no error at all.
        # rollback() is always safe here even when nothing was written.
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
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        # Postgres closed this connection server-side (idle timeout, etc.)
        # while it sat in the pool — discard it and get a fresh one.
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
        conn = pool.getconn()
    return _PooledConn(conn)


def dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
