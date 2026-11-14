"""
demo_isolation.py - Phase F, test 3 (Isolation).

This script opens a writer transaction, inserts 24 MADE-UP readings
(Anand Vihar, PM2.5, 21 Jan 2026), then WAITS without committing.
While it waits, you run a SELECT in a second Workbench tab. That tab must
NOT see the 24 uncommitted rows (InnoDB default isolation: REPEATABLE READ).
At the end the script ROLLS BACK, so nothing stays in the database.

Note: this uses its own plain INSERT transaction, not load_batch(). It shows
what InnoDB guarantees for any writer transaction like the loader's.

Run from the repo root:
    python ingestion/demo_isolation.py
"""
import time

import load

STATION_NAME = "Anand Vihar, Delhi - DPCC"
TEST_DATE = "2026-01-21"
HOLD_SECONDS = 90


def count_all(cur):
    cur.execute("SELECT COUNT(*) FROM reading")
    return cur.fetchone()[0]


def main():
    conn = load.get_connection()          # autocommit is OFF
    try:
        station_id = load.load_station_ids(conn)[STATION_NAME]

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM reading WHERE reading_datetime >= %s "
                    "AND reading_datetime < DATE_ADD(%s, INTERVAL 1 DAY)",
                    (TEST_DATE, TEST_DATE))
        if cur.fetchone()[0] != 0:
            conn.commit()
            print("STOP: %s already has data. Pick another TEST_DATE." % TEST_DATE)
            return 1
        conn.commit()

        print("=== ISOLATION DEMO (made-up test data, rolled back at the end) ===")
        conn.start_transaction()
        before = count_all(cur)
        print("Writer window: reading rows before insert: %d" % before)

        rows = [(station_id, 1, "%s %02d:00:00" % (TEST_DATE, h), 70.0)
                for h in range(24)]
        cur.executemany(
            "INSERT INTO reading (station_id, pollutant_id, reading_datetime, "
            "concentration_value) VALUES (%s, %s, %s, %s)", rows)
        inside = count_all(cur)
        print("Writer window: inserted 24 rows, NOT committed. "
              "Count seen INSIDE this transaction: %d" % inside)

        print("\n>>> NOW go to the second Workbench tab and run:")
        print("      SELECT @@transaction_isolation;")
        print("      SELECT COUNT(*) FROM reading;")
        print("    It should still show %d (not %d). Take a screenshot of both windows."
              % (before, inside))
        print("    Holding the transaction open for %d seconds...\n" % HOLD_SECONDS)

        for left in range(HOLD_SECONDS, 0, -10):
            print("    %d s left" % left)
            time.sleep(10)

        conn.rollback()
        after = count_all(cur)
        conn.commit()
        print("\nWriter window: ROLLED BACK. Reading rows now: %d (started at %d)"
              % (after, before))
        return 0
    finally:
        # If you press Ctrl+C, close() makes MySQL roll back the open transaction.
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
