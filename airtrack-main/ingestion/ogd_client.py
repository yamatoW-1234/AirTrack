"""ogd_client.py - fetches raw air-quality records from the OGD API (data.gov.in).

Run from the repo root:
    python ingestion/ogd_client.py                       (tests Anand Vihar)
    python ingestion/ogd_client.py "Vivek Vihar, Delhi - DPCC"

Rules: the API key is read from .env and is NEVER printed or saved.
"""
import datetime
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
load_dotenv(os.path.join(HERE, "..", ".env"))

RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
URL = "https://api.data.gov.in/resource/" + RESOURCE_ID
# The gateway answers 502 to Python's default User-Agent (found in Phase B).
HEADERS = {"User-Agent": "curl/8.0", "Accept": "*/*"}
TIMEOUT = (10, 120)          # (connect seconds, read seconds)
MAX_TRIES = 3
RETRY_STATUS = (500, 502, 503, 504)
PAGE_SIZE = 500
SAMPLES_DIR = os.path.join(HERE, "samples")


# ---------- our own error types (messages never contain the key or URL) ----------
class MissingApiKeyError(Exception):
    """OGD_API_KEY is not set in .env."""


class ApiRejectedError(Exception):
    """The API answered with a 4xx status (bad key, bad request). Retrying will not help."""


class ApiUnavailableError(Exception):
    """The API could not be reached or kept failing after all retries."""


def get_api_key():
    key = os.getenv("OGD_API_KEY")
    if not key or not key.strip():
        raise MissingApiKeyError("OGD_API_KEY is missing in .env")
    return key.strip()


def _get_page(params):
    """One HTTP request with retries. Returns the parsed JSON dict."""
    last_problem = "unknown"
    for attempt in range(1, MAX_TRIES + 1):
        try:
            resp = requests.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as e:
            # Only the exception TYPE is kept: the message can contain the URL + key.
            last_problem = type(e).__name__
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    last_problem = "reply was not valid JSON"
            elif resp.status_code in RETRY_STATUS:
                last_problem = "HTTP " + str(resp.status_code)
            else:
                # 400 / 401 / 403 ...: retrying with the same key will not help
                raise ApiRejectedError("API rejected the request: HTTP " + str(resp.status_code))
        if attempt < MAX_TRIES:
            wait = 5 * (2 ** (attempt - 1))      # 5 s, then 10 s
            print("  attempt", attempt, "failed (" + last_problem + "), retrying in", wait, "s")
            time.sleep(wait)
    raise ApiUnavailableError("API unavailable after " + str(MAX_TRIES) + " tries (" + last_problem + ")")


def fetch_station(station_name, pollutant_id=None):
    """Return ALL raw record dicts for one station (pages through with offset)."""
    key = get_api_key()
    records = []
    offset = 0
    while True:
        params = {
            "api-key": key,
            "format": "json",
            "limit": PAGE_SIZE,
            "offset": offset,
            "filters[station]": station_name,
        }
        if pollutant_id:
            params["filters[pollutant_id]"] = pollutant_id
        data = _get_page(params)
        page = data.get("records") or []
        records.extend(page)
        total = int(data.get("total", len(records)))
        offset += PAGE_SIZE
        if not page or offset >= total:
            break
    return records


def load_region():
    """Return the list of station dicts from config/region.json."""
    path = os.path.join(HERE, "config", "region.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["stations"]


def fetch_region():
    """Fetch raw records for every station in region.json, as one combined list.

    If any station fails, the error is passed up and NOTHING is returned,
    so a batch is never half-fetched.
    """
    all_records = []
    for st in load_region():
        all_records.extend(fetch_station(st["station_name"]))
    return all_records


def save_raw_response(records, name):
    """Save raw records to samples/<name>_<timestamp>.json. Refuses if the key is inside."""
    text = json.dumps({"records": records}, indent=2)
    key = os.getenv("OGD_API_KEY")
    if key and key.strip() and key.strip() in text:
        raise RuntimeError("API key found in data; refusing to save")
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(SAMPLES_DIR, name + "_" + stamp + ".json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "Anand Vihar, Delhi - DPCC"
    try:
        if arg == "--region":
            rows = fetch_region()
            arg = "whole region (5 stations)"
        else:
            rows = fetch_station(arg)
    except (MissingApiKeyError, ApiRejectedError, ApiUnavailableError) as e:
        print("FAILED:", e)
        sys.exit(1)
    station = arg
    print("Station:", repr(station))
    print("Records fetched:", len(rows))
    for r in rows:
        print(" ", r.get("pollutant_id"), r.get("avg_value"), r.get("last_update"))
