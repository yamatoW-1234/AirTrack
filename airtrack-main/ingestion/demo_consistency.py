"""
demo_consistency.py - Phase F, test 2 (Consistency).

Part A: MySQL itself rejects bad rows (the database is the last guard).
   A1. station/pollutant pair not in station_pollutant -> foreign key error
   A2. negative concentration_value                    -> CHECK error
   Both inserts are rolled back, so nothing is written.
Part B: transform() skips the same kinds of bad rows BEFORE they reach MySQL,
   and counts the reason for each.

All data here is made up for the demo. Run from the repo root:
    python ingestion/demo_consistency.py
"""
import mysql.connector

import load
from transform import transform, print_report

STATION_NAME = "Anand Vihar, Delhi - DPCC"
TEST_DATETIME = "2026-01-20 05:00:00"     # made-up; the inserts are rejected anyway


def counts(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reading")
    n = cur.fetchone()[0]
    cur.close()
    conn.commit()
    return n


def try_insert(conn, label, station_id, pollutant_id, value):
    """Try one INSERT. Print what MySQL says. Always roll back."""
    sql = ("INSERT INTO reading (station_id, pollutant_id, reading_datetime, "
           "concentration_value) VALUES (%s, %s, %s, %s)")
    print("\n%s" % label)
    print("  INSERT station_id=%s, pollutant_id=%s, value=%s"
          % (station_id, pollutant_id, value))
    cur = conn.cursor()
    try:
        cur.execute(sql, (station_id, pollutant_id, TEST_DATETIME, value))
        print("  UNEXPECTED: MySQL accepted the row")
    except mysql.connector.Error as e:
        print("  REJECTED by MySQL  errno=%s" % e.errno)
        print("  message: %s" % e.msg)
    finally:
        cur.close()
        conn.rollback()


def find_unassigned_pair(station_ids, assigned):
    """A (station_id, pollutant_id) that is NOT in station_pollutant."""
    for sid in sorted(station_ids.values()):
        for pid in (1, 2, 3, 4):
            if pid not in assigned.get(sid, set()):
                return sid, pid
    return None


def main():
    conn = load.get_connection()
    try:
        station_ids = load.load_station_ids(conn)
        assigned = load.load_assigned(conn)
        anand = station_ids[STATION_NAME]

        print("=== CONSISTENCY DEMO (made-up test data) ===")
        before = counts(conn)
        print("reading rows BEFORE: %d" % before)

        # ---------- Part A: the database refuses ----------
        print("\n--- Part A: MySQL rejects bad rows ---")

        pair = find_unassigned_pair(station_ids, assigned)
        if pair is None:
            # every real pair is assigned, so use a station that does not exist
            pair = (9999, 1)
            print("\n(All existing station/pollutant pairs are assigned, "
                  "so A1 uses station_id 9999, which is in no station_pollutant row.)")
        try_insert(conn, "A1. Pair not in station_pollutant (foreign key):",
                   pair[0], pair[1], 50.0)

        try_insert(conn, "A2. Negative concentration (CHECK constraint):",
                   anand, 1, -5.0)

        after = counts(conn)
        print("\nreading rows AFTER: %d  (%s)"
              % (after, "unchanged" if after == before else "CHANGED!"))

        # ---------- Part B: transform skips them first ----------
        print("\n--- Part B: transform() skips bad records and counts why ---")
        good_date = "01-11-2026 05:00:00"
        records = [
            {"station": STATION_NAME, "pollutant_id": "PM2.5",
             "avg_value": "80", "last_update": good_date},           # kept
            {"station": STATION_NAME, "pollutant_id": "SO2",
             "avg_value": "-5", "last_update": good_date},           # negative
            {"station": STATION_NAME, "pollutant_id": "NO2",
             "avg_value": "NA", "last_update": good_date},           # missing
            {"station": STATION_NAME, "pollutant_id": "CO",
             "avg_value": "1.2", "last_update": good_date},          # unknown pollutant
            {"station": "No Such Station", "pollutant_id": "PM2.5",
             "avg_value": "50", "last_update": good_date},           # unknown station
            {"station": STATION_NAME, "pollutant_id": "PM10",
             "avg_value": "abc", "last_update": good_date},          # not a number
        ]
        rows, report = transform(records, station_ids, assigned=assigned)
        print_report(report, len(records))
        print("rows that would be sent to MySQL: %d" % len(rows))

        # pollutant-not-assigned check: pretend Anand Vihar only has PM2.5
        pretend = dict(assigned)
        pretend[anand] = {1}
        rec2 = [{"station": STATION_NAME, "pollutant_id": "PM10",
                 "avg_value": "90", "last_update": good_date}]
        rows2, report2 = transform(rec2, station_ids, assigned=pretend)
        print("\nPretending Anand Vihar is assigned only PM2.5 and sending a PM10 record:")
        print_report(report2, len(rec2))
        print("rows that would be sent to MySQL: %d" % len(rows2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
