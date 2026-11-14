"""
test_load.py - Phase D checks for load.py (runs against the REAL local database).

Run from the repo root:   python ingestion/test_load.py

Tests:
  1. Loading every file in samples/ twice leaves the reading count unchanged
  2. sub_index is filled for all readings
  3. 16 hourly readings (2 pollutants) -> aqi_record; 15 hours -> none
  4. A forced failure at each step leaves the DB exactly as before
  5. A foreign-key violation (pollutant not assigned) rolls the whole batch back

NOTE: tests 3-5 use made-up readings on January 2026 dates (far from real data).
The writer account cannot DELETE, so the successful test rows stay until you run
cleanup_sample_data.sql before the final long run (it empties reading/aqi_record).
"""
import glob
import json
import os
import sys

import load
from transform import transform

SAMPLES = os.path.join(os.path.dirname(__file__), "samples")
DATE_16H = "2026-01-15"   # gets 16 hours -> AQI expected
DATE_15H = "2026-01-16"   # gets 15 hours -> no AQI expected
DATE_FAIL = "2026-01-18"  # used only by the failure tests, must stay empty

failures = []


def check(name, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + name + ("  " + extra if extra else ""))
    if not ok:
        failures.append(name)


def counts(conn):
    """(reading rows, aqi_record rows, readings with NULL sub_index)."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reading")
    r = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM aqi_record")
    a = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM reading WHERE sub_index IS NULL")
    n = cur.fetchone()[0]
    cur.close()
    conn.commit()  # end the read snapshot so the next count sees fresh data
    return r, a, n


def make_rows(station_id, pollutant_id, date, hours, value):
    return [
        {"station_id": station_id, "pollutant_id": pollutant_id,
         "reading_datetime": "%sT%02d:00:00" % (date, h),
         "concentration_value": value}
        for h in range(hours)
    ]


def sample_batches():
    """Yield (file name, raw records) for each JSON file in samples/."""
    for path in sorted(glob.glob(os.path.join(SAMPLES, "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records", []) if isinstance(data, dict) else data
        if records:
            yield os.path.basename(path), records
        else:
            print("skip (no records):", os.path.basename(path))


def aqi_row(conn, station_id, date):
    cur = conn.cursor()
    cur.execute("SELECT aqi_value, dominant_pollutant_id, hours_of_data "
                "FROM aqi_record WHERE station_id = %s AND record_date = %s",
                (station_id, date))
    row = cur.fetchone()
    cur.close()
    conn.commit()
    return row


def main():
    conn = load.get_connection()
    station_ids = load.load_station_ids(conn)
    assigned = load.load_assigned(conn)
    anand = station_ids["Anand Vihar, Delhi - DPCC"]

    # ---- 1. samples twice
    print("\n== 1. Load samples/ twice ==")
    batches = list(sample_batches())
    for name, records in batches:
        rows, _ = transform(records, station_ids, assigned=assigned)
        res = load.load_batch(conn, rows)
        print("   first pass ", name, res["submitted"], "submitted,", res["inserted"], "new")
    after_first = counts(conn)
    second_inserted = 0
    for name, records in batches:
        rows, _ = transform(records, station_ids, assigned=assigned)
        res = load.load_batch(conn, rows)
        second_inserted += res["inserted"]
        print("   second pass", name, res["submitted"], "submitted,", res["inserted"], "new")
    after_second = counts(conn)
    check("reading count unchanged after second load", after_first[0] == after_second[0],
          "(%d -> %d)" % (after_first[0], after_second[0]))
    check("second pass inserted 0 new rows", second_inserted == 0)

    # ---- 2. sub_index filled
    print("\n== 2. sub_index ==")
    check("no reading has NULL sub_index", after_second[2] == 0,
          "(NULL count = %d)" % after_second[2])

    # ---- 3. 16-hour rule
    print("\n== 3. 16-hour rule ==")
    batch = (make_rows(anand, 1, DATE_16H, 16, 90.0)      # PM2.5, high
             + make_rows(anand, 2, DATE_16H, 16, 100.0)   # PM10, lower
             + make_rows(anand, 1, DATE_15H, 15, 90.0)
             + make_rows(anand, 2, DATE_15H, 15, 100.0))
    res = load.load_batch(conn, batch)
    print("  ", res)
    row16 = aqi_row(conn, anand, DATE_16H)
    row15 = aqi_row(conn, anand, DATE_15H)
    check("16 hours -> aqi_record exists", row16 is not None, str(row16))
    if row16:
        check("hours_of_data = 16", row16[2] == 16)
        check("dominant pollutant is PM2.5 (id 1)", row16[1] == 1)
    check("15 hours -> NO aqi_record", row15 is None)
    again = load.load_batch(conn, batch)
    check("re-loading the same batch inserts 0 new rows", again["inserted"] == 0)

    # ---- 4. forced failures roll back
    print("\n== 4. Forced failure -> rollback ==")
    bad_batch = (make_rows(anand, 1, DATE_FAIL, 16, 90.0)
                 + make_rows(anand, 2, DATE_FAIL, 16, 100.0))
    for point in load.FAIL_POINTS:
        before = counts(conn)
        try:
            load.load_batch(conn, bad_batch, fail_after=point)
            check("fail_after=" + point + " raised an error", False)
            continue
        except load.LoadError as e:
            cause = type(e.__cause__).__name__
        after = counts(conn)
        check("fail_after=%s: DB unchanged" % point, before == after,
              "(%s, cause %s)" % (after, cause))
    check("no AQI row for the failed date", aqi_row(conn, anand, DATE_FAIL) is None)

    # ---- 5. foreign-key violation
    print("\n== 5. Pollutant not assigned (FK) -> rollback ==")
    good = make_rows(anand, 1, DATE_FAIL, 1, 50.0)
    bad = [{"station_id": anand, "pollutant_id": 99,
            "reading_datetime": DATE_FAIL + "T01:00:00", "concentration_value": 10.0}]
    before = counts(conn)
    errno = None
    try:
        load.load_batch(conn, good + bad)
        check("FK violation raised an error", False)
    except load.LoadError as e:
        errno = getattr(e.__cause__, "errno", None)
    after = counts(conn)
    check("FK error is MySQL 1452", errno == 1452, "(errno %s)" % errno)
    check("the valid row in the same batch was NOT saved", before == after)

    conn.close()
    print("\n" + ("ALL TESTS PASSED" if not failures else "FAILED: " + ", ".join(failures)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
