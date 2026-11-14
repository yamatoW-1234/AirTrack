"""transform.py - turns raw OGD records into clean rows for the reading table.

No network and no database in this file, so it can be tested offline.
The caller passes in the lookup maps.

    rows, report = transform(raw_records, station_ids)

Each row: {station_id, pollutant_id, reading_datetime, concentration_value}
report:   a Counter of how many records were kept or skipped, per reason.
"""
import math
from collections import Counter
from datetime import datetime

# Verified on live data (Phase B): exact pollutant strings -> ids from seed_reference.sql
POLLUTANT_IDS = {"PM2.5": 1, "PM10": 2, "NO2": 3, "SO2": 4}

API_DATE_FORMAT = "%d-%m-%Y %H:%M:%S"     # e.g. 31-10-2026 17:00:00

# Skip reasons (the keys of the report)
KEPT = "kept"
UNKNOWN_STATION = "unknown_station"
UNKNOWN_POLLUTANT = "unknown_pollutant"
NOT_ASSIGNED = "pollutant_not_assigned_to_station"
MISSING_VALUE = "missing_value"
NON_NUMERIC = "non_numeric_value"
NEGATIVE = "negative_value"
BAD_DATE = "bad_date"
DUPLICATE = "duplicate_in_batch"


def parse_value(text):
    """Convert the API text to a rounded float.

    Returns (number, None) if fine, or (None, reason) if it must be skipped.
    """
    if text is None:
        return None, MISSING_VALUE
    text = str(text).strip()
    if text == "" or text.upper() == "NA":
        return None, MISSING_VALUE
    try:
        number = float(text)
    except ValueError:
        return None, NON_NUMERIC
    if not math.isfinite(number):          # float("nan") and float("inf") parse, so catch them
        return None, NON_NUMERIC
    if number < 0:
        return None, NEGATIVE
    return round(number, 2), None          # DECIMAL(8,2)


def parse_date(text):
    """Parse 'DD-MM-YYYY HH:MM:SS'. Returns an ISO string 'YYYY-MM-DDTHH:MM:SS' or None."""
    try:
        return datetime.strptime(str(text).strip(), API_DATE_FORMAT).isoformat()
    except ValueError:
        return None


def transform(records, station_ids, pollutant_ids=POLLUTANT_IDS, assigned=None):
    """Clean a list of raw records.

    station_ids : dict  station_name -> station_id   (from the DB, or hand-made in tests)
    assigned    : optional dict  station_id -> set of pollutant_ids allowed for that station.
                  If None, the 'not assigned' check is skipped.
    """
    rows = []
    report = Counter()
    seen = set()

    for rec in records:
        # 1. station: exact text match (some real names carry a trailing space)
        station_id = station_ids.get(rec.get("station"))
        if station_id is None:
            report[UNKNOWN_STATION] += 1
            continue

        # 2. pollutant (CO, NH3, OZONE end up here: we ignore them on purpose)
        pollutant_id = pollutant_ids.get(rec.get("pollutant_id"))
        if pollutant_id is None:
            report[UNKNOWN_POLLUTANT] += 1
            continue

        # 3. is this pollutant measured at this station?
        if assigned is not None and pollutant_id not in assigned.get(station_id, set()):
            report[NOT_ASSIGNED] += 1
            continue

        # 4. value
        value, reason = parse_value(rec.get("avg_value"))
        if reason:
            report[reason] += 1
            continue

        # 5. date
        when = parse_date(rec.get("last_update"))
        if when is None:
            report[BAD_DATE] += 1
            continue

        # 6. same station + pollutant + time twice in one batch: keep the first
        key = (station_id, pollutant_id, when)
        if key in seen:
            report[DUPLICATE] += 1
            continue
        seen.add(key)

        rows.append({
            "station_id": station_id,
            "pollutant_id": pollutant_id,
            "reading_datetime": when,
            "concentration_value": value,
        })
        report[KEPT] += 1

    return rows, report


def print_report(report, total):
    """Readable skip report."""
    print("Records in:", total)
    for reason, count in sorted(report.items()):
        print("  {:<36} {}".format(reason, count))
