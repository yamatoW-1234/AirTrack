"""
ingest.py - run the whole ingestion pipeline.

Usage (from the repo root, venv active):
    python ingestion/ingest.py --once       fetch live data from the API and load it
    python ingestion/ingest.py --sample     same pipeline, but read samples/*.json
    python ingestion/ingest.py schedule     run the --once logic every hour

Pipeline for one run (ONE batch for all region stations):
    fetch -> connect -> look up station ids -> transform -> load_batch

Exit codes (useful for Windows Task Scheduler):
    0 = success
    1 = API problem (no key, key rejected, API down)
    2 = database / load problem (the batch was rolled back)
    3 = anything else unexpected

Empty answer (Phase F): if a run fetches 0 records, it is NOT an error
(exit code stays 0), but a WARNING line is written to the log so an empty
feed cannot pass unnoticed.
"""

import argparse
import glob
import json
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

import schedule

import ogd_client
import load
from transform import transform

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
SAMPLES_DIR = os.path.join(HERE, "samples")

EXIT_OK = 0
EXIT_API = 1
EXIT_DB = 2
EXIT_OTHER = 3

log = logging.getLogger("ingest")


def setup_logging():
    """Log to the console and to logs/ingest.log (a new file each midnight)."""
    if log.handlers:  # already set up, do not add handlers twice
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = TimedRotatingFileHandler(
        os.path.join(LOG_DIR, "ingest.log"),
        when="midnight", backupCount=30, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log.setLevel(logging.INFO)
    log.addHandler(file_handler)
    log.addHandler(console_handler)


def read_samples():
    """Read every samples/*.json file and return one list of raw records."""
    records = []
    paths = sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.json")))
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):      # saved as {"records": [...]}
            data = data.get("records", [])
        records.extend(data)
    log.info("read %d sample files", len(paths))
    return records


def run_once(use_samples=False):
    """One full ingestion run. Never raises; returns an exit code."""
    started = datetime.now()
    source = "samples" if use_samples else "api"
    log.info("RUN START source=%s", source)

    code = EXIT_OK
    conn = None
    try:
        # 1. get the raw records (before opening the DB connection)
        if use_samples:
            records = read_samples()
        else:
            log.info("stations requested: %d", len(ogd_client.load_region()))
            records = ogd_client.fetch_region()
        log.info("rows fetched: %d", len(records))

        # An empty answer is not an error, but it must be visible in the log.
        # (Seen on 1 Nov 2026: the API answered HTTP 200 with total = 0.)
        if len(records) == 0:
            log.warning("%s returned 0 records, nothing to load "
                        "(the feed may be empty)", source)

        # 2. connect and look up ids by name (never hard-coded)
        conn = load.get_connection()
        station_ids = load.load_station_ids(conn)
        assigned = load.load_assigned(conn)

        # 3. clean and validate
        rows, report = transform(records, station_ids, assigned=assigned)
        log.info("transform report: %s", dict(report))

        # 4. save all or nothing, then sub-index and daily AQI
        counts = load.load_batch(conn, rows)
        log.info(
            "loaded: submitted=%d inserted=%d duplicates=%d dates=%s "
            "aqi_new=%d aqi_affected=%d",
            counts["submitted"], counts["inserted"], counts["duplicates"],
            counts["dates"], counts["aqi_new"], counts["aqi_affected"],
        )

    except (ogd_client.MissingApiKeyError,
            ogd_client.ApiRejectedError,
            ogd_client.ApiUnavailableError) as e:
        # these messages never contain the key or the URL
        log.error("API problem: %s: %s", type(e).__name__, e)
        code = EXIT_API
    except load.LoadError as e:
        log.error("LOAD FAILED, batch rolled back: %s", e.__cause__ or e)
        code = EXIT_DB
    except Exception as e:
        # only the type name: some exception texts can contain the URL/key
        log.error("UNEXPECTED ERROR: %s", type(e).__name__)
        code = EXIT_OTHER
    finally:
        if conn is not None:
            conn.close()

    seconds = (datetime.now() - started).total_seconds()
    log.info("RUN END exit_code=%d duration=%.1fs", code, seconds)
    return code


def run_scheduler():
    """Run run_once() now, then at 5 minutes past every hour, until Ctrl+C."""
    def job():
        try:
            run_once()
        except Exception as e:  # run_once should never raise; belt and braces
            log.error("scheduler job crashed: %s", type(e).__name__)

    log.info("scheduler started (runs now, then at :05 of every hour). Ctrl+C to stop.")
    job()
    schedule.every().hour.at(":05").do(job)
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("scheduler stopped by user")


def main():
    parser = argparse.ArgumentParser(description="AirTrack ingestion")
    parser.add_argument("command", nargs="?", choices=["schedule"],
                        help="'schedule' = run every hour until stopped")
    parser.add_argument("--once", action="store_true",
                        help="fetch live data and load it once")
    parser.add_argument("--sample", action="store_true",
                        help="load samples/*.json instead of calling the API")
    args = parser.parse_args()

    chosen = [args.command == "schedule", args.once, args.sample]
    if sum(chosen) != 1:
        parser.error("choose exactly one of: --once, --sample, schedule")

    setup_logging()
    if args.command == "schedule":
        run_scheduler()
        return EXIT_OK
    return run_once(use_samples=args.sample)


if __name__ == "__main__":
    sys.exit(main())
