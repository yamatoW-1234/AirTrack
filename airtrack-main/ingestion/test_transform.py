"""test_transform.py - offline test for transform.py (no network, no database).

Run from the repo root:
    python ingestion/test_transform.py
"""
import glob
import json
import os
import re

from transform import (transform, print_report, KEPT, UNKNOWN_STATION, UNKNOWN_POLLUTANT,
                       NOT_ASSIGNED, MISSING_VALUE, NON_NUMERIC, NEGATIVE, BAD_DATE, DUPLICATE)

HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "samples", "*.json")

# Hand-made station map (the real one will come from the database in Phase D).
STATION_IDS = {
    "Anand Vihar, Delhi - DPCC": 1,
    "Vivek Vihar, Delhi - DPCC": 5,
    "IHBAS, Dilshad Garden, Delhi - CPCB": 6,
    "Patparganj, Delhi - DPCC": 7,
    "ITO, Delhi - CPCB": 8,
}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def read_records(path):
    """Samples come in two shapes: a full response dict, or {'records': [...]}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["records"] if isinstance(data, dict) else data


def make(**changes):
    """One good record, with some fields changed."""
    rec = {"station": "Anand Vihar, Delhi - DPCC", "pollutant_id": "PM2.5",
           "last_update": "31-10-2026 17:00:00", "avg_value": "68"}
    rec.update(changes)
    return rec


def test_samples():
    files = sorted(glob.glob(SAMPLES))
    assert files, "no sample files found in ingestion/samples/"
    for path in files:
        records = read_records(path)
        rows, report = transform(records, STATION_IDS)
        print("\n==", os.path.basename(path))
        print_report(report, len(records))
        assert len(rows) > 0, "no valid rows produced"
        assert sum(report.values()) == len(records), "every record must be counted once"
        for r in rows:
            assert set(r) == {"station_id", "pollutant_id", "reading_datetime", "concentration_value"}
            assert r["station_id"] in STATION_IDS.values()
            assert r["pollutant_id"] in (1, 2, 3, 4)
            assert ISO.match(r["reading_datetime"]), r["reading_datetime"]
            assert isinstance(r["concentration_value"], float) and r["concentration_value"] >= 0
    print("\nPASS: samples")


def test_bad_records():
    bad = [
        make(avg_value="NA"),                                  # missing_value
        make(avg_value="  ", pollutant_id="PM10"),             # missing_value (blank)
        make(avg_value="-5", pollutant_id="NO2"),              # negative_value
        make(avg_value="abc", pollutant_id="SO2"),             # non_numeric_value
        make(avg_value="nan", station="ITO, Delhi - CPCB"),    # non_numeric_value
        make(last_update="2026/10/31 17:00", station="ITO, Delhi - CPCB", pollutant_id="PM10"),  # bad_date
        make(station="Nowhere, Delhi"),                        # unknown_station
        make(station="Anand Vihar, Delhi - DPCC "),            # trailing space -> unknown_station
        make(pollutant_id="CO"),                               # unknown_pollutant
    ]
    rows, report = transform(bad, STATION_IDS)
    print("\n== hand-made bad records")
    print_report(report, len(bad))
    assert rows == [], "no bad record may become a row"
    assert report[MISSING_VALUE] == 2
    assert report[NEGATIVE] == 1
    assert report[NON_NUMERIC] == 2
    assert report[BAD_DATE] == 1
    assert report[UNKNOWN_STATION] == 2
    assert report[UNKNOWN_POLLUTANT] == 1
    assert report[KEPT] == 0
    print("PASS: bad records")


def test_rounding_duplicates_assigned():
    # rounding to 2 decimals, text -> float
    rows, _ = transform([make(avg_value="12.3456")], STATION_IDS)
    assert rows[0]["concentration_value"] == 12.35
    assert rows[0]["reading_datetime"] == "2026-10-31T17:00:00"

    # same station + pollutant + time twice -> first kept, second skipped
    rows, report = transform([make(avg_value="10"), make(avg_value="99")], STATION_IDS)
    assert len(rows) == 1 and rows[0]["concentration_value"] == 10.0
    assert report[DUPLICATE] == 1

    # same pollutant at a different time is a different reading: both kept
    rows, report = transform([make(), make(last_update="31-10-2026 18:00:00")], STATION_IDS)
    assert len(rows) == 2 and report[DUPLICATE] == 0

    # pollutant not assigned to the station (station 1 allowed only PM10 here)
    rows, report = transform([make()], STATION_IDS, assigned={1: {2}})
    assert rows == [] and report[NOT_ASSIGNED] == 1
    print("PASS: rounding, duplicates, not-assigned")


if __name__ == "__main__":
    test_samples()
    test_bad_records()
    test_rounding_duplicates_assigned()
    print("\nALL TESTS PASSED")
