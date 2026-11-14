"""Concurrency test: 30 threads call GET endpoints while ONE thread keeps posting new readings.

Start the API first (python app.py), then in a second window, from the backend/ folder:
    python tests/concurrency_test.py
Options: --threads 30  --seconds 20  --base-url http://localhost:5000/api

What it proves (and prints):
  1. No request fails (every GET answers 200 with valid JSON, every POST 201).
  2. No half-written data is ever seen: a reading becomes visible only together with its
     sub_index (insert + sub-index calculation are ONE transaction), so a reader never sees NULL.
  3. "total" always equals the rows returned (count and rows come from one snapshot).
  4. A reader never sees the data go backwards (a reading it saw earlier never disappears).
  5. After the run, every reading the writer was told about is in the database, with the same sub_index.

ISOLATION LEVEL used: REPEATABLE READ, the InnoDB default (we do not change it).
  * Plain GET routes run one SELECT, which reads one consistent snapshot and takes no locks, so
    readers never block the writer and the writer never blocks readers (MVCC).
  * /readings and /aqi-records run COUNT and the page query inside one transaction started with
    a consistent snapshot, so "total" always matches the rows even while readings are added.
  * Why not READ COMMITTED: the COUNT and the page query would see different data when a commit
    lands between them. Why not SERIALIZABLE: it turns plain SELECTs into locking reads, so the 30
    readers would queue behind the writer, and nothing here reads then writes based on what it read.
  * Duplicate readings are stopped by the UNIQUE key, not by the isolation level.

Only the Python standard library is used. Test rows go to the station TEST_CONCURRENCY_STATION
(remove them with tests/cleanup_test_data.sql).
"""
import argparse
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import Config  # noqa: E402  (reads ADMIN_KEY from the repo's .env)

STATION_NAME = "TEST_CONCURRENCY_STATION"
MAX_WRITES = 450          # keeps this run's readings under the 500-row page limit
WRITE_PAUSE = 0.05        # seconds between writer posts


def http(method, url, body=None, admin=False, timeout=15):
    """Returns (status, parsed_json_or_None). Never raises for HTTP error statuses."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if admin:
        headers["X-Admin-Key"] = Config.ADMIN_KEY or ""
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


class Results:
    """Thread-safe counters and a short list of example problems."""

    def __init__(self):
        self.lock = threading.Lock()
        self.counts = {"gets": 0, "get_errors": 0, "null_sub_index": 0, "total_mismatch": 0,
                       "went_backwards": 0, "writes_ok": 0, "write_duplicates": 0, "write_errors": 0}
        self.examples = []
        self.written = {}  # reading_datetime -> sub_index the API told the writer

    def add(self, key, n=1, example=None):
        with self.lock:
            self.counts[key] += n
            if example and len(self.examples) < 10:
                self.examples.append(example)


def setup_station(base):
    """Find or create the test station and assign PM2.5 to it. Returns station_id."""
    status, body = http("GET", f"{base}/stations")
    sid = next((s["station_id"] for s in body["stations"] if s["station_name"] == STATION_NAME), None)
    if sid is None:
        status, body = http("POST", f"{base}/admin/stations", admin=True,
                            body={"station_name": STATION_NAME, "location": "concurrency test", "station_type": "Test"})
        if status != 201:
            sys.exit(f"Could not create the test station: {status} {body}. Is ADMIN_KEY set in .env?")
        sid = body["station_id"]
    status, body = http("POST", f"{base}/admin/station-pollutants", admin=True,
                        body={"station_id": sid, "pollutant": "PM2.5"})
    if status not in (201, 409):
        sys.exit(f"Could not assign PM2.5: {status} {body}")
    return sid


def writer(base, sid, start_time, stop, res):
    """One thread that keeps adding readings, one per call (each call is one DB transaction)."""
    i = 0
    while not stop.is_set() and i < MAX_WRITES:
        when = (start_time + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S")
        i += 1
        value = round(random.uniform(5, 600), 2)
        status, body = http("POST", f"{base}/admin/readings", admin=True,
                            body={"station_id": sid, "pollutant": "PM2.5",
                                  "reading_datetime": when, "concentration_value": value})
        if status == 201 and isinstance(body.get("sub_index"), int) and 0 <= body["sub_index"] <= 500:
            with res.lock:
                res.written[when] = body["sub_index"]
            res.add("writes_ok")
        elif status == 409:
            res.add("write_duplicates")
        else:
            res.add("write_errors", example=f"POST {when} value {value} -> {status} {body}")
        time.sleep(WRITE_PAUSE)


def reader(base, sid, day_from, day_to, stop, res):
    """One of the 30 threads: loops over GET endpoints and checks what it gets back."""
    window = f"station_id={sid}&pollutant=PM2.5&from={day_from}&to={day_to}&limit=500"
    urls = [
        f"{base}/stations", f"{base}/pollutants", f"{base}/categories",
        f"{base}/stations/1/latest", f"{base}/stations/1/aqi?date=2026-10-18",
        f"{base}/stations/1/summary?date=2026-10-18", f"{base}/stations/{sid}/latest",
        f"{base}/aqi-records?station_id=1", f"{base}/reports/compare?date=2026-10-18",
        f"{base}/reports/most-polluted", f"{base}/reports/average?station_id=1&period=monthly",
        f"{base}/reports/availability",
        f"{base}/readings?{window}", f"{base}/readings?{window}",  # the busiest one, twice as often
    ]
    last_total = 0
    while not stop.is_set():
        url = random.choice(urls)
        status, body = http("GET", url)
        res.add("gets")
        if status != 200 or body is None:
            res.add("get_errors", example=f"GET {url} -> {status} {str(body)[:120]}")
            continue
        if url.endswith(window):
            rows = body["rows"]
            nulls = sum(1 for r in rows if r["sub_index"] is None)
            if nulls:
                res.add("null_sub_index", nulls, example=f"{nulls} half-written reading(s) seen in {url}")
            if body["total"] <= 500 and body["total"] != len(rows):
                res.add("total_mismatch", example=f"total={body['total']} but {len(rows)} rows")
            if body["total"] < last_total:
                res.add("went_backwards", example=f"total fell from {last_total} to {body['total']}")
            last_total = max(last_total, body["total"])
        elif "/stations/" in url and url.endswith("/latest") and f"/stations/{sid}/" in url:
            if any(r["sub_index"] is None for r in body["readings"]):
                res.add("null_sub_index", example=f"NULL sub_index in {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--threads", type=int, default=30, help="reader threads (default 30)")
    parser.add_argument("--seconds", type=int, default=20, help="how long to run (default 20)")
    parser.add_argument("--base-url", default=f"http://localhost:{Config.API_PORT}/api")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    status, _ = http("GET", f"{base}/stations")
    if status != 200:
        sys.exit(f"The API is not answering at {base} (status {status}). Start it with: python app.py")
    sid = setup_station(base)

    # this run's readings go into their own random day, so the 500-row window holds only them
    start_time = datetime(2030, 1, 1) + timedelta(days=random.randint(0, 3000), hours=random.randint(0, 6))
    day_from = start_time.date().isoformat()
    day_to = (start_time + timedelta(days=1)).date().isoformat()

    res, stop = Results(), threading.Event()
    threads = [threading.Thread(target=writer, args=(base, sid, start_time, stop, res))]
    threads += [threading.Thread(target=reader, args=(base, sid, day_from, day_to, stop, res))
                for _ in range(args.threads)]
    print(f"Running {args.threads} reader threads + 1 writer thread for {args.seconds} s against {base} ...")
    began = time.time()
    for t in threads:
        t.start()
    time.sleep(args.seconds)
    stop.set()
    for t in threads:
        t.join()
    elapsed = time.time() - began

    # final check: everything the writer was told must now be in the database, unchanged
    status, body = http("GET", f"{base}/readings?station_id={sid}&pollutant=PM2.5"
                               f"&from={day_from}&to={day_to}&limit=500")
    in_db = {r["reading_datetime"]: r["sub_index"] for r in body["rows"]} if status == 200 else {}
    missing = [k for k in res.written if k not in in_db]
    changed = [k for k, v in res.written.items() if k in in_db and in_db[k] != v]

    c = res.counts
    print()
    print(f"Time                         : {elapsed:.1f} s")
    print(f"GET requests (30 threads)    : {c['gets']}  ({c['gets'] / elapsed:.0f} per second)")
    print(f"GET errors                   : {c['get_errors']}")
    print(f"Readings added by the writer : {c['writes_ok']}  (duplicates skipped: {c['write_duplicates']}, "
          f"write errors: {c['write_errors']})")
    print(f"Half-written rows seen       : {c['null_sub_index']}   (reading visible without its sub_index)")
    print(f"total != rows returned       : {c['total_mismatch']}")
    print(f"Data went backwards          : {c['went_backwards']}")
    print(f"Final check                  : {len(in_db)} readings in the database, "
          f"{len(missing)} missing, {len(changed)} with a different sub_index")
    for line in res.examples:
        print("  example:", line)

    problems = (c["get_errors"] + c["null_sub_index"] + c["total_mismatch"] + c["went_backwards"]
                + c["write_errors"] + len(missing) + len(changed))
    if c["writes_ok"] == 0:
        problems += 1
        print("The writer added no readings, so nothing was tested.")
    print()
    print("RESULT: PASS - no errors, no half-written data" if problems == 0 else "RESULT: FAIL")
    sys.exit(0 if problems == 0 else 1)


if __name__ == "__main__":
    main()
