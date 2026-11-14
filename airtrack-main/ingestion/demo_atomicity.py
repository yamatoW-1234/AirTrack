"""
demo_atomicity.py - Phase F, test 1 (Atomicity).

Shows, with screenshot-friendly output:
  1. counts BEFORE
  2. a batch that fails midway (forced failure AFTER the inserts, sub-index
     and daily AQI steps, just before COMMIT)  -> rolled back
  3. counts AFTER the failure: identical to BEFORE
  4. (after you press Enter) the SAME batch loaded without the failure
  5. counts AFTER the success: new rows are there

The data is MADE-UP TEST DATA (Anand Vihar, 19 Jan 2026, 16 hours of
PM2.5 and PM10). It is NOT live data. The writer account cannot DELETE,
so step 4 stays in the database until cleanup_sample_data.sql is run.

Run from the repo root:
    python ingestion/demo_atomicity.py
"""
import load
import ingest

TEST_DATE = "2026-01-19"          # must be empty; test_load.py uses 15, 16, 18 Jan
STATION_NAME = "Anand Vihar, Delhi - DPCC"
HOURS = 16                        # 16 hours -> the daily AQI rule is satisfied


def make_rows(station_id, pollutant_id, date, hours, value):
    """Same row format that transform() produces."""
    return [
        {"station_id": station_id, "pollutant_id": pollutant_id,
         "reading_datetime": "%sT%02d:00:00" % (date, h),
         "concentration_value": value}
        for h in range(hours)
    ]


def counts(conn):
    """(readings, aqi_records) in the whole DB. Ends with commit() because with
    autocommit off even a SELECT opens a transaction, and load_batch needs to
    start its own."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reading")
    readings = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM aqi_record")
    aqi = cur.fetchone()[0]
    cur.close()
    conn.commit()
    return readings, aqi


def count_on_test_date(conn):
    """(readings, aqi_records) that exist for TEST_DATE."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reading "
                "WHERE reading_datetime >= %s AND reading_datetime < "
                "DATE_ADD(%s, INTERVAL 1 DAY)", (TEST_DATE, TEST_DATE))
    readings = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM aqi_record WHERE record_date = %s",
                (TEST_DATE,))
    aqi = cur.fetchone()[0]
    cur.close()
    conn.commit()
    return readings, aqi


def main():
    ingest.setup_logging()
    log = ingest.log
    conn = load.get_connection()
    try:
        # Safety: the demo only makes sense on an empty date.
        if count_on_test_date(conn) != (0, 0):
            print("STOP: %s already has data. Pick another date in TEST_DATE."
                  % TEST_DATE)
            return 1

        anand = load.load_station_ids(conn)[STATION_NAME]
        batch = (make_rows(anand, 1, TEST_DATE, HOURS, 90.0)
                 + make_rows(anand, 2, TEST_DATE, HOURS, 100.0))

        print("\n=== ATOMICITY DEMO (made-up test data, %s) ===" % TEST_DATE)
        print("Batch: %d readings (PM2.5 and PM10, %d hours each)"
              % (len(batch), HOURS))

        # ---- 1. forced failure ----
        before = counts(conn)
        print("\n[1] BEFORE the failing batch:  readings=%d  aqi_records=%d"
              % before)
        print("    Loading with a forced failure after the AQI step "
              "(just before COMMIT)...")
        try:
            load.load_batch(conn, batch, fail_after="aqi")
            print("    UNEXPECTED: no error was raised")
        except load.LoadError as e:
            cause = type(e.__cause__).__name__
            log.error("DEMO: LOAD FAILED, batch rolled back: %s (cause %s)",
                      e, cause)
            print("    ERROR caught: %s (cause: %s)" % (e, cause))
        after = counts(conn)
        print("[2] AFTER the failing batch:   readings=%d  aqi_records=%d"
              % after)
        if before == after:
            print("    RESULT: counts unchanged -> the whole batch was "
                  "rolled back (all or nothing).")
        else:
            print("    PROBLEM: counts changed! Do not use this as evidence.")
            return 1

        # ---- 2. same batch, no failure ----
        input("\nPress Enter to load the SAME batch for real (this will be "
              "COMMITTED and stays until cleanup)... ")
        result = load.load_batch(conn, batch)
        log.info("DEMO: loaded without failure: %s", result)
        final = counts(conn)
        print("\n[3] Same batch WITHOUT the failure: %s" % result)
        print("[4] AFTER the successful batch: readings=%d  aqi_records=%d"
              % final)
        print("    Difference vs. BEFORE: +%d readings, +%d aqi_records"
              % (final[0] - before[0], final[1] - before[1]))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
