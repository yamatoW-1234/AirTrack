"""
csv_import.py - load a CPCB-style CSV through the SAME pipeline as the API.

Usage (from the repo root, venv active):
    python ingestion/csv_import.py file.csv --station "Anand Vihar, Delhi - DPCC"

--station is needed only if the file has no station column.

Two layouts are understood (headers are matched ignoring case and units):
  WIDE: one date column + one column per pollutant, e.g.
        From Date | PM2.5 (ug/m3) | PM10 (ug/m3) | NO2 (ug/m3) | SO2 (ug/m3)
  LONG: one row per reading, columns like
        station | datetime | pollutant | value

How it reuses the existing code:
  Each CSV cell is turned into a dict shaped like an API record
  (station, pollutant_id, avg_value, last_update). transform() then validates
  it exactly as for API data, and load_batch() saves it all or nothing and
  runs the sub-index and daily AQI calculations.

Exit codes: 0 success, 2 load failed (rolled back), 3 bad file/other.
"""

import argparse
import csv
import os
import sys
from datetime import datetime

import load
from transform import transform, POLLUTANT_IDS
from ingest import setup_logging, log, EXIT_OK, EXIT_DB, EXIT_OTHER

# header names we accept (compared in lower case)
DATETIME_NAMES = ("from date", "datetime", "timestamp", "date",
                  "reading_datetime", "last_update")
STATION_NAMES = ("station", "station_name", "site")
POLLUTANT_COL_NAMES = ("pollutant", "pollutant_id")
VALUE_COL_NAMES = ("value", "avg_value", "concentration")

# date formats we try, in order
DATE_FORMATS = (
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)


class CsvFormatError(Exception):
    """The file does not look like a layout we understand."""


def to_api_date(text):
    """Turn a CSV date into the API format DD-MM-YYYY HH:MM:SS.
    If no format fits, return the text unchanged so transform() counts it
    as bad_date instead of crashing."""
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%d-%m-%Y %H:%M:%S")
        except ValueError:
            pass
    return text


def pollutant_from_header(header):
    """'PM2.5 (ug/m3)' -> 'PM2.5'. Returns None if not one of our 4."""
    name = header.split("(")[0].strip().upper()
    return name if name in POLLUTANT_IDS else None


def first_match(lower_headers, names):
    """Return the real header for the first accepted name present, else None."""
    for name in names:
        if name in lower_headers:
            return lower_headers[name]
    return None


def csv_to_records(path, station_arg=None):
    """Read the CSV and return a list of API-shaped record dicts."""
    records = []
    with open(path, newline="", encoding="utf-8-sig") as f:  # utf-8-sig drops Excel's BOM
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        lower = {h.strip().lower(): h for h in headers}

        date_col = first_match(lower, DATETIME_NAMES)
        if date_col is None:
            raise CsvFormatError("no date column found (looked for: %s)"
                                 % ", ".join(DATETIME_NAMES))
        station_col = first_match(lower, STATION_NAMES)
        if station_col is None and not station_arg:
            raise CsvFormatError("file has no station column; use --station")

        poll_col = first_match(lower, POLLUTANT_COL_NAMES)
        value_col = first_match(lower, VALUE_COL_NAMES)
        wide_cols = [(h, pollutant_from_header(h)) for h in headers
                     if pollutant_from_header(h)]

        if poll_col and value_col:
            layout = "long"
        elif wide_cols:
            layout = "wide"
        else:
            raise CsvFormatError("found neither pollutant columns (wide) "
                                 "nor pollutant+value columns (long)")
        log.info("csv layout: %s", layout)

        for row in reader:
            station = (row[station_col] if station_col else station_arg).strip()
            when = to_api_date(row[date_col])

            if layout == "wide":
                # unpivot: one API-style record per pollutant column
                for header, pollutant in wide_cols:
                    records.append({
                        "station": station,
                        "pollutant_id": pollutant,
                        "avg_value": (row[header] or "").strip(),
                        "last_update": when,
                    })
            else:
                name = (row[poll_col] or "").strip()
                records.append({
                    "station": station,
                    "pollutant_id": name.upper() if name.upper() in POLLUTANT_IDS else name,
                    "avg_value": (row[value_col] or "").strip(),
                    "last_update": when,
                })
    return records


def run_csv(path, station_arg=None):
    """Import one CSV file. Never raises; returns an exit code."""
    log.info("CSV IMPORT START file=%s", os.path.basename(path))
    code = EXIT_OK
    conn = None
    try:
        if not os.path.isfile(path):
            log.error("file not found: %s", path)
            return EXIT_OTHER

        records = csv_to_records(path, station_arg)
        log.info("records built from csv: %d", len(records))

        conn = load.get_connection()
        station_ids = load.load_station_ids(conn)
        assigned = load.load_assigned(conn)

        rows, report = transform(records, station_ids, assigned=assigned)
        log.info("transform report: %s", dict(report))

        counts = load.load_batch(conn, rows)
        log.info(
            "loaded: submitted=%d inserted=%d duplicates=%d dates=%s "
            "aqi_new=%d aqi_affected=%d",
            counts["submitted"], counts["inserted"], counts["duplicates"],
            counts["dates"], counts["aqi_new"], counts["aqi_affected"],
        )
    except CsvFormatError as e:
        log.error("CSV format problem: %s", e)
        code = EXIT_OTHER
    except load.LoadError as e:
        log.error("LOAD FAILED, batch rolled back: %s", e.__cause__ or e)
        code = EXIT_DB
    except Exception as e:
        log.error("UNEXPECTED ERROR: %s", type(e).__name__)
        code = EXIT_OTHER
    finally:
        if conn is not None:
            conn.close()
    log.info("CSV IMPORT END exit_code=%d", code)
    return code


def main():
    parser = argparse.ArgumentParser(description="Import a CPCB-style CSV")
    parser.add_argument("csv_file")
    parser.add_argument("--station", help="station name if the file has no station column")
    args = parser.parse_args()
    setup_logging()
    return run_csv(args.csv_file, args.station)


if __name__ == "__main__":
    sys.exit(main())
