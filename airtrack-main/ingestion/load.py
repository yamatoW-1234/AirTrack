"""
load.py - Phase D: save one batch of clean rows ALL OR NOTHING.

Flow of load_batch(conn, rows):
    start transaction
      1. insert the readings (ON DUPLICATE KEY, so re-running adds nothing)
      2. run db/calc_subindex.sql       (fills sub_index where it is NULL)
      3. for each date in the batch: SET @d, run db/calc_daily_aqi.sql
    commit
    (any error -> rollback, nothing is saved)

Uses only the writer account from .env. Never prints passwords.
Run `python ingestion/load.py` from the repo root to check the DB connection
and see the station maps.
"""
import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db")
SUBINDEX_SQL = os.path.join(DB_DIR, "calc_subindex.sql")
DAILY_AQI_SQL = os.path.join(DB_DIR, "calc_daily_aqi.sql")

# ON DUPLICATE KEY (not INSERT IGNORE): a duplicate is silently skipped, but a
# foreign-key violation (pollutant not assigned to station) still raises an error.
INSERT_SQL = (
    "INSERT INTO reading "
    "(station_id, pollutant_id, reading_datetime, concentration_value) "
    "VALUES (%s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE reading_id = reading_id"
)

# Places where the testing hook can break the batch (used by Phase F).
FAIL_POINTS = ("insert", "subindex", "aqi")


class LoadError(Exception):
    """The batch was rolled back. The original error is in __cause__."""


class SimulatedFailure(Exception):
    """Raised on purpose by the fail_after testing hook."""


# ---------------------------------------------------------------- connection
def get_connection():
    """Connect as the writer account, autocommit OFF (we commit by hand)."""
    user = os.getenv("DB_WRITER_USER")
    password = os.getenv("DB_WRITER_PASSWORD")
    if not user or not password:
        raise LoadError("DB_WRITER_USER / DB_WRITER_PASSWORD missing in .env")
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "airtrack"),
        user=user,
        password=password,
    )
    conn.autocommit = False
    return conn


# ------------------------------------------------------------ lookup helpers
def load_station_ids(conn):
    """{station_name: station_id} from monitoring_station (never hard-code ids)."""
    cur = conn.cursor()
    cur.execute("SELECT station_name, station_id FROM monitoring_station")
    result = {name: sid for name, sid in cur.fetchall()}
    cur.close()
    conn.commit()  # a SELECT opens a transaction; end it so load_batch can start its own
    return result


def load_assigned(conn):
    """{station_id: set(pollutant_ids)} from station_pollutant."""
    cur = conn.cursor()
    cur.execute("SELECT station_id, pollutant_id FROM station_pollutant")
    result = {}
    for sid, pid in cur.fetchall():
        result.setdefault(sid, set()).add(pid)
    cur.close()
    conn.commit()
    return result


# ------------------------------------------------------------ reading SQL files
def read_sql_statements(path, skip_prefixes=()):
    """
    Read a .sql file and return its statements as a list of strings.
    Drops whole-line comments, the USE line (the connection already picked the
    database) and any line starting with one of skip_prefixes (upper case).
    Then splits on ';'. Safe here because Member 1's files have no ';' inside
    strings.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    kept = []
    for line in text.splitlines():
        s = line.strip().upper()
        if s.startswith("--") or s.startswith("USE "):
            continue
        if any(s.startswith(p) for p in skip_prefixes):
            continue
        kept.append(line)
    pieces = "\n".join(kept).split(";")
    return [p.strip() for p in pieces if p.strip()]


def _count(cur, table):
    cur.execute("SELECT COUNT(*) FROM " + table)  # table names are fixed by us
    return cur.fetchone()[0]


# ------------------------------------------------------------------ the loader
def load_batch(conn, rows, fail_after=None):
    """
    Save rows (dicts from transform.py) in ONE transaction.

    fail_after: testing hook. None = normal. "insert", "subindex" or "aqi" =
    raise SimulatedFailure right after that step (before commit), to prove the
    rollback leaves the database untouched.

    Returns a dict:
        submitted     rows given to us
        inserted      rows that were really new
        duplicates    submitted - inserted (already in the DB)
        dates         the dates the daily AQI was run for
        aqi_new       new aqi_record rows created
        aqi_affected  MySQL's affected-rows number for the daily statements
                      (1 = new row, 2 = changed row; only a rough indicator)
    Raises LoadError (after rollback) on any failure.
    """
    if fail_after is not None and fail_after not in FAIL_POINTS:
        raise ValueError("fail_after must be None or one of " + str(FAIL_POINTS))

    result = {"submitted": len(rows), "inserted": 0, "duplicates": 0,
              "dates": [], "aqi_new": 0, "aqi_affected": 0}
    if not rows:
        return result

    # Prepare everything that does not touch the database first.
    values = [
        (r["station_id"], r["pollutant_id"],
         r["reading_datetime"].replace("T", " "), r["concentration_value"])
        for r in rows
    ]
    dates = sorted({r["reading_datetime"][:10] for r in rows})  # 'YYYY-MM-DD'
    try:
        subindex_stmts = read_sql_statements(SUBINDEX_SQL)
        daily_stmts = read_sql_statements(DAILY_AQI_SQL, skip_prefixes=("SET @D",))
    except OSError as e:
        raise LoadError("cannot read a db/*.sql file: " + type(e).__name__) from e
    if len(daily_stmts) != 1:
        raise LoadError("calc_daily_aqi.sql should be ONE statement, found "
                        + str(len(daily_stmts)))

    cur = conn.cursor()
    try:
        conn.start_transaction()
        reading_before = _count(cur, "reading")
        aqi_before = _count(cur, "aqi_record")

        # 1. insert
        cur.executemany(INSERT_SQL, values)
        result["inserted"] = _count(cur, "reading") - reading_before
        result["duplicates"] = len(rows) - result["inserted"]
        if fail_after == "insert":
            raise SimulatedFailure("forced failure after insert")

        # 2. sub-index
        for stmt in subindex_stmts:
            cur.execute(stmt)
        if fail_after == "subindex":
            raise SimulatedFailure("forced failure after sub-index")

        # 3. daily AQI, once per date in the batch
        for d in dates:
            cur.execute("SET @d = %s", (d,))
            cur.execute(daily_stmts[0])
            result["aqi_affected"] += max(cur.rowcount, 0)
        result["dates"] = dates
        result["aqi_new"] = _count(cur, "aqi_record") - aqi_before
        if fail_after == "aqi":
            raise SimulatedFailure("forced failure after daily AQI")

        conn.commit()
        return result
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass  # if the connection is gone, MySQL already discarded the transaction
        raise LoadError("batch rolled back (" + type(e).__name__ + ": " + str(e) + ")") from e
    finally:
        cur.close()


# -------------------------------------------------- quick manual check
if __name__ == "__main__":
    conn = get_connection()
    ids = load_station_ids(conn)
    assigned = load_assigned(conn)
    print("Connected as writer. Stations in DB:")
    for name, sid in sorted(ids.items(), key=lambda x: x[1]):
        print("  ", sid, repr(name), sorted(assigned.get(sid, [])))
    conn.close()
