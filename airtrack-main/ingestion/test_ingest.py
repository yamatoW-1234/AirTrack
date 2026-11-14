"""
test_ingest.py - tests for ingest.py and csv_import.py (no internet needed).

Run from the repo root (venv active):
    python ingestion/test_ingest.py

It uses the real local DB, samples/*.json and samples/csv_test_wide.csv.
API failures are simulated by replacing functions, so no network is used.
Each check prints PASS or FAIL; exit code is 1 if anything failed.
"""

import logging
import os
import sys

import ogd_client
import load
import ingest
import csv_import

CSV_PATH = os.path.join(ingest.HERE, "samples", "csv_test_wide.csv")
STATION = "Anand Vihar, Delhi - DPCC"

failures = 0


class WarningCatcher(logging.Handler):
    """Collects the text of every WARNING (or worse) the ingest logger writes."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def check(name, condition):
    global failures
    print(("PASS  " if condition else "FAIL  ") + name)
    if not condition:
        failures += 1


def count_readings():
    """Number of rows in reading, read on its own connection."""
    conn = load.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM reading")
        n = cur.fetchone()[0]
        cur.close()
        conn.commit()  # end the read transaction
        return n
    finally:
        conn.close()


def main():
    ingest.setup_logging()

    # 1. sample run: exit 0, and a second run adds nothing
    print("\n-- 1. ingest.py --sample is idempotent")
    code1 = ingest.run_once(use_samples=True)
    n1 = count_readings()
    code2 = ingest.run_once(use_samples=True)
    n2 = count_readings()
    check("first sample run exits 0", code1 == 0)
    check("second sample run exits 0", code2 == 0)
    check("second sample run adds no readings (%d -> %d)" % (n1, n2), n1 == n2)

    # 2. CSV: exit 0, second run adds nothing
    print("\n-- 2. csv_import.py is idempotent")
    c1 = csv_import.run_csv(CSV_PATH, STATION)
    m1 = count_readings()
    c2 = csv_import.run_csv(CSV_PATH, STATION)
    m2 = count_readings()
    check("first csv run exits 0", c1 == 0)
    check("second csv run exits 0", c2 == 0)
    check("second csv run adds no readings (%d -> %d)" % (m1, m2), m1 == m2)

    # 3. CSV problems: exit 3 and nothing written
    print("\n-- 3. csv_import.py bad input")
    before = count_readings()
    check("missing --station exits 3", csv_import.run_csv(CSV_PATH, None) == 3)
    check("missing file exits 3",
          csv_import.run_csv(os.path.join(ingest.HERE, "no_such_file.csv"), STATION) == 3)
    check("nothing written by bad input", count_readings() == before)

    # 4. simulated failures inside run_once (functions are swapped, then restored)
    print("\n-- 4. exit codes for simulated failures")
    real_fetch = ogd_client.fetch_region
    real_load_batch = load.load_batch
    before = count_readings()
    try:
        def api_down():
            raise ogd_client.ApiUnavailableError("simulated outage")
        ogd_client.fetch_region = api_down
        check("API down exits 1", ingest.run_once() == 1)

        def api_rejects():
            raise ogd_client.ApiRejectedError("simulated 403")
        ogd_client.fetch_region = api_rejects
        check("API rejects key exits 1", ingest.run_once() == 1)

        def api_crashes():
            raise RuntimeError("simulated bug")
        ogd_client.fetch_region = api_crashes
        check("unexpected error exits 3", ingest.run_once() == 3)
    finally:
        ogd_client.fetch_region = real_fetch

    try:
        def load_fails(conn, rows, fail_after=None):
            raise load.LoadError("simulated load failure")
        load.load_batch = load_fails
        check("load failure exits 2", ingest.run_once(use_samples=True) == 2)
    finally:
        load.load_batch = real_load_batch

    check("simulated failures wrote nothing", count_readings() == before)

    # 5. an empty API answer is not an error, but it must be warned about
    print("\n-- 5. empty API answer logs a WARNING")
    before = count_readings()

    catcher = WarningCatcher()
    ingest.log.addHandler(catcher)
    try:
        ogd_client.fetch_region = lambda: []          # API answers with nothing
        empty_code = ingest.run_once()
    finally:
        ogd_client.fetch_region = real_fetch
        ingest.log.removeHandler(catcher)
    check("empty answer still exits 0", empty_code == 0)
    check("empty answer logs a WARNING about 0 records",
          any("0 records" in m for m in catcher.messages))
    check("empty answer wrote nothing", count_readings() == before)

    # a normal run must NOT produce that warning
    catcher2 = WarningCatcher()
    ingest.log.addHandler(catcher2)
    try:
        ingest.run_once(use_samples=True)
    finally:
        ingest.log.removeHandler(catcher2)
    check("normal sample run logs no 0-records warning",
          not any("0 records" in m for m in catcher2.messages))

    print("\n%s" % ("ALL PASSED" if failures == 0 else "%d CHECK(S) FAILED" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
