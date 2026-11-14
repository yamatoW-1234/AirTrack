"""Database access: one connection pool for the reader account, one for the writer account.

Rules for the whole backend:
- GET routes use fetch_all / fetch_one (reader account, SELECT only).
- Admin routes use transaction() (writer account); it commits on success, rolls back on any error.
- Always pass values as the params tuple with %s placeholders. Never build SQL with f-strings.
"""
import threading
import time
from contextlib import contextmanager

from mysql.connector import pooling
from mysql.connector.errors import PoolError

from config import Config

_pools = {}
_lock = threading.Lock()


def _make_pool(role):
    if role == "reader":
        user, password = Config.DB_READER_USER, Config.DB_READER_PASSWORD
        size, autocommit = Config.READER_POOL_SIZE, True  # each SELECT is its own transaction
    else:
        user, password = Config.DB_WRITER_USER, Config.DB_WRITER_PASSWORD
        size, autocommit = Config.WRITER_POOL_SIZE, False  # commit/rollback done explicitly

    if not user or password is None:
        raise RuntimeError(f"Missing DB_{role.upper()}_USER / DB_{role.upper()}_PASSWORD in .env")

    return pooling.MySQLConnectionPool(
        pool_name=f"airtrack_{role}",
        pool_size=size,
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        database=Config.DB_NAME,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=autocommit,
    )


def _get_pool(role):
    with _lock:
        if role not in _pools:
            _pools[role] = _make_pool(role)
        return _pools[role]


def _checkout(role):
    """Get a connection; if the pool is briefly empty, wait up to ~5 s instead of failing."""
    pool = _get_pool(role)
    for _ in range(50):
        try:
            return pool.get_connection()
        except PoolError:
            time.sleep(0.1)
    raise PoolError("Connection pool exhausted")


@contextmanager
def get_conn(role="reader"):
    conn = _checkout(role)
    try:
        yield conn
    finally:
        conn.close()  # returns the connection to the pool


def fetch_all(sql, params=()):
    """Run a SELECT with the reader account. Returns a list of dicts."""
    with get_conn("reader") as conn:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()


def fetch_one(sql, params=()):
    """Run a SELECT with the reader account. Returns one dict, or None if no row."""
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


@contextmanager
def transaction():
    """Writer account, one atomic unit of work.

    with transaction() as cur:
        cur.execute("INSERT ...", (a, b))
        cur.execute("SELECT ...", (c,))
    # commit happens when the block ends; any exception rolls everything back
    """
    with get_conn("writer") as conn:
        cur = conn.cursor(dictionary=True)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
