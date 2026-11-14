"""AirTrack API tests: at least one test per endpoint, plus bad-input cases.

Run from the backend/ folder (MySQL must be running and the database loaded):
    pip install pytest
    python -m pytest tests/test_api.py -v

The tests use Harsh's sample data (db/sample_data.sql + calc_subindex.sql + calc_daily_aqi.sql for
18-24 Oct 2026). Tests that WRITE use one fixed test station called TEST_PYTEST_STATION, so
re-running never piles up new stations. Remove test rows with tests/cleanup_test_data.sql.
"""
import itertools
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "import app" works

from app import app  # noqa: E402
from config import Config  # noqa: E402

TEST_STATION = "TEST_PYTEST_STATION"

# PM2.5 breakpoints from db/seed_reference.sql: (conc_low, conc_high, index_low, index_high)
PM25_BANDS = [(0, 30, 0, 50), (30, 60, 51, 100), (60, 90, 101, 200),
              (90, 120, 201, 300), (120, 250, 301, 400), (250, 500, 401, 500)]


def expected_pm25_sub_index(value):
    """Section 7 of the contract, written independently of the SQL used by the API."""
    c = Decimal(str(value))
    for low, high, i_low, i_high in PM25_BANDS:
        if low <= c < high:
            exact = Decimal(i_high - i_low) / Decimal(high - low) * (c - low) + i_low
            return int(exact.quantize(Decimal(1), rounding="ROUND_HALF_UP"))
    return 500  # at or above the top of the Severe range


# one random start per run, then one new minute per call, so reading times never repeat
_BASE_TIME = datetime(2030, 1, 1) + timedelta(days=random.randint(0, 3000))
_minutes = itertools.count()


def unique_time():
    return (_BASE_TIME + timedelta(minutes=next(_minutes))).strftime("%Y-%m-%dT%H:%M:%S")


# ---------- fixtures ----------

@pytest.fixture(scope="session")
def client():
    return app.test_client()


@pytest.fixture(scope="session", autouse=True)
def sample_data_loaded(client):
    r = client.get("/api/stations/1/aqi?date=2026-10-18")
    if r.status_code != 200:
        pytest.skip("Load db/sample_data.sql, run calc_subindex.sql and calc_daily_aqi.sql (18-24 Oct) first",
                    allow_module_level=False)


@pytest.fixture(scope="session")
def admin_headers():
    if not Config.ADMIN_KEY:
        pytest.skip("ADMIN_KEY is not set in .env")
    return {"X-Admin-Key": Config.ADMIN_KEY}


@pytest.fixture(scope="session")
def test_station(client, admin_headers):
    """The fixed test station with PM2.5 assigned (created on first run, reused afterwards)."""
    stations = client.get("/api/stations").get_json()["stations"]
    sid = next((s["station_id"] for s in stations if s["station_name"] == TEST_STATION), None)
    if sid is None:
        r = client.post("/api/admin/stations", headers=admin_headers,
                        json={"station_name": TEST_STATION, "location": "pytest", "station_type": "Test"})
        assert r.status_code == 201
        sid = r.get_json()["station_id"]
    r = client.post("/api/admin/station-pollutants", headers=admin_headers,
                    json={"station_id": sid, "pollutant": "PM2.5"})
    assert r.status_code in (201, 409)  # 409 = assigned on an earlier run
    return sid


def get_json(client, url, status=200):
    r = client.get(url)
    assert r.status_code == status, f"{url} -> {r.status_code} {r.get_data(as_text=True)[:200]}"
    return r.get_json()


# ---------- lookups ----------

def test_stations(client):
    body = get_json(client, "/api/stations")
    first = body["stations"][0]
    for key in ("station_id", "station_name", "location", "latitude", "longitude", "station_type", "status"):
        assert key in first
    assert any(s["station_name"] == "Anand Vihar, Delhi - DPCC" for s in body["stations"])


def test_pollutants(client):
    names = {p["pollutant_name"] for p in get_json(client, "/api/pollutants")["pollutants"]}
    assert {"PM2.5", "PM10", "NO2", "SO2"} <= names


def test_categories(client):
    cats = get_json(client, "/api/categories")["categories"]
    assert [c["category_id"] for c in cats] == [1, 2, 3, 4, 5, 6]
    assert all(c["color_code"].startswith("#") and len(c["color_code"]) == 7 for c in cats)


# ---------- per-station ----------

def test_latest(client):
    body = get_json(client, "/api/stations/1/latest")
    assert body["station_id"] == 1
    assert {r["pollutant"] for r in body["readings"]} == {"PM2.5", "PM10", "NO2", "SO2"}
    assert all(r["sub_index"] is not None for r in body["readings"])


def test_aqi_known_values(client):
    """Hand-checked values from db/tests/expected.md."""
    a = get_json(client, "/api/stations/1/aqi?date=2026-10-18")
    assert (a["aqi_value"], a["category"]["name"], a["dominant_pollutant"]) == (359, "Very Poor", "PM2.5")
    b = get_json(client, "/api/stations/2/aqi?date=2026-10-21")
    assert (b["aqi_value"], b["category"]["name"], b["dominant_pollutant"]) == (77, "Satisfactory", "PM10")
    assert b["hours_of_data"] == 24 and b["category"]["color_code"].startswith("#")


def test_aqi_default_date_is_latest(client):
    body = get_json(client, "/api/stations/1/aqi")
    assert body["date"] >= "2026-10-24"


def test_summary_short_day_returns_only_existing_hours(client):
    """Station 2, PM2.5, 21 Oct has only 14 readings on purpose (the 16-hour rule case)."""
    body = get_json(client, "/api/stations/2/summary?date=2026-10-21")
    pm25 = next(p for p in body["pollutants"] if p["pollutant"] == "PM2.5")
    assert len(pm25["hourly"]) == 14
    assert pm25["min"] <= pm25["avg"] <= pm25["max"]


# ---------- search ----------

def test_readings_paging_and_total(client):
    body = get_json(client, "/api/readings?limit=3")
    assert body["limit"] == 3 and body["offset"] == 0 and len(body["rows"]) == 3
    assert body["total"] >= 2678
    times = [r["reading_datetime"] for r in body["rows"]]
    assert times == sorted(times, reverse=True)  # newest first
    page2 = get_json(client, "/api/readings?limit=3&offset=3")
    assert page2["rows"] != body["rows"]


def test_readings_filters_combine(client):
    body = get_json(client, "/api/readings?station_id=2&pollutant=PM2.5&from=2026-10-21&to=2026-10-21")
    assert body["total"] == 14 and len(body["rows"]) == 14
    assert all(r["pollutant"] == "PM2.5" and r["reading_datetime"].startswith("2026-10-21") for r in body["rows"])
    assert get_json(client, "/api/readings?station_id=1&pollutant=PM10&from=2026-10-18&to=2026-10-18")["total"] == 24
    assert get_json(client, "/api/readings?station_id=999")["total"] == 0


def test_aqi_records_filters(client):
    all_rows = get_json(client, "/api/aqi-records")
    assert all_rows["total"] >= 28
    one = get_json(client, "/api/aqi-records?station_id=1&from=2026-10-20&to=2026-10-22")
    assert one["total"] == 3 and {r["date"] for r in one["rows"]} == {"2026-10-20", "2026-10-21", "2026-10-22"}
    by_name = get_json(client, "/api/aqi-records?category=Very%20Poor")
    by_id = get_json(client, "/api/aqi-records?category=5")
    assert by_name["total"] == by_id["total"] > 0
    assert all(r["category"] == "Very Poor" for r in by_name["rows"])


# ---------- reports ----------

def test_report_compare_highest_first(client):
    body = get_json(client, "/api/reports/compare?date=2026-10-18")
    values = [s["aqi_value"] for s in body["stations"]]
    assert values == sorted(values, reverse=True) and values[0] == 359
    assert all("color_code" in s for s in body["stations"])


def test_report_most_polluted_matches_compare(client):
    top = get_json(client, "/api/reports/most-polluted?date=2026-10-18")
    first = get_json(client, "/api/reports/compare?date=2026-10-18")["stations"][0]
    assert (top["station_id"], top["aqi_value"]) == (first["station_id"], first["aqi_value"])
    assert top["dominant_pollutant"] == "PM2.5"
    assert "date" in get_json(client, "/api/reports/most-polluted")  # default = latest date


def test_report_average(client):
    monthly = get_json(client, "/api/reports/average?station_id=1&period=monthly")
    assert monthly["period"] == "monthly" and monthly["points"][0]["label"] == "2026-10"
    daily = get_json(client, "/api/reports/average?station_id=1&period=daily&from=2026-10-20&to=2026-10-22")
    assert [p["label"] for p in daily["points"]] == ["2026-10-20", "2026-10-21", "2026-10-22"]
    assert get_json(client, "/api/reports/average?station_id=2&from=2027-01-01")["points"] == []


def test_report_availability(client):
    rows = get_json(client, "/api/reports/availability")["rows"]
    assert len(rows) >= 16
    station_b = next(r for r in rows if r["station_name"] == "Sample Station B" and r["pollutant"] == "PM2.5")
    assert station_b["reading_count"] == 158  # 7 days x 24 hours minus the 10 missing on 21 Oct


# ---------- bad input: every one must give the error JSON, never SQL text or a stack trace ----------

BAD_REQUESTS = [
    ("/api/nonexistent", 404),
    ("/api/stations/abc/latest", 400),
    ("/api/stations/9999/latest", 404),
    ("/api/stations/1/aqi?date=18-10-2026", 400),
    ("/api/stations/1/aqi?date=2025-01-01", 404),
    ("/api/stations/9999/aqi", 404),
    ("/api/stations/1/summary?date=2026-02-30", 400),
    ("/api/readings?limit=501", 400),
    ("/api/readings?limit=0", 400),
    ("/api/readings?limit=abc", 400),
    ("/api/readings?offset=-1", 400),
    ("/api/readings?station_id=abc", 400),
    ("/api/readings?pollutant=CO2", 400),
    ("/api/readings?pollutant=PM2.5'%20OR%20'1'='1", 400),
    ("/api/readings?from=2026-13-01", 400),
    ("/api/readings?from=2026-10-20&to=2026-10-18", 400),
    ("/api/aqi-records?category=Awful", 400),
    ("/api/aqi-records?category=9", 400),
    ("/api/aqi-records?from=nope", 400),
    ("/api/aqi-records?station_id=0", 400),
    ("/api/reports/compare?date=2026-02-30", 400),
    ("/api/reports/compare?date=2026-12-25", 404),
    ("/api/reports/most-polluted?date=abc", 400),
    ("/api/reports/average", 400),
    ("/api/reports/average?station_id=1&period=weekly", 400),
    ("/api/reports/average?station_id=9999", 404),
    ("/api/reports/average?station_id=1&from=2026-10-22&to=2026-10-20", 400),
]


@pytest.mark.parametrize("url,status", BAD_REQUESTS)
def test_bad_input(client, url, status):
    r = client.get(url)
    assert r.status_code == status
    body = r.get_json()
    assert list(body) == ["error"] and isinstance(body["error"], str)
    text = body["error"].lower()
    assert "traceback" not in text and "sql" not in text and "mysql" not in text


# ---------- admin ----------

def test_admin_needs_the_key(client, admin_headers):
    payload = {"station_id": 1, "pollutant": "PM2.5", "reading_datetime": unique_time(), "concentration_value": 10}
    assert client.post("/api/admin/readings", json=payload).status_code == 401
    assert client.post("/api/admin/readings", json=payload, headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.put("/api/admin/stations/1", json={"location": "x"}).status_code == 401


def test_admin_station_add_update_and_bad_input(client, admin_headers, test_station):
    # add: duplicate name -> 409, missing/invalid fields -> 400
    assert client.post("/api/admin/stations", headers=admin_headers, json={"station_name": TEST_STATION}).status_code == 409
    for bad in ({"location": "no name"}, {"station_name": "S", "status": "Broken"},
                {"station_name": "S", "latitude": 95}, {"station_name": "S", "colour": "red"}):
        assert client.post("/api/admin/stations", headers=admin_headers, json=bad).status_code == 400
    # update
    r = client.put(f"/api/admin/stations/{test_station}", headers=admin_headers,
                   json={"location": "pytest location", "status": "Active"})
    assert r.status_code == 200
    stations = client.get("/api/stations").get_json()["stations"]
    assert next(s for s in stations if s["station_id"] == test_station)["location"] == "pytest location"
    assert client.put("/api/admin/stations/9999", headers=admin_headers, json={"location": "x"}).status_code == 404
    assert client.put(f"/api/admin/stations/{test_station}", headers=admin_headers, json={}).status_code == 400
    assert client.put(f"/api/admin/stations/{test_station}", headers=admin_headers,
                      json={"station_name": "Sample Station B"}).status_code == 409


def test_admin_assign_pollutant(client, admin_headers, test_station):
    r = client.post("/api/admin/station-pollutants", headers=admin_headers,
                    json={"station_id": test_station, "pollutant": "PM2.5"})
    assert r.status_code == 409  # already assigned by the fixture
    assert client.post("/api/admin/station-pollutants", headers=admin_headers,
                       json={"station_id": 9999, "pollutant": "PM2.5"}).status_code == 404
    assert client.post("/api/admin/station-pollutants", headers=admin_headers,
                       json={"station_id": test_station, "pollutant": "CO"}).status_code == 400


def test_admin_reading_calculates_sub_index_and_is_searchable(client, admin_headers, test_station):
    when = unique_time()
    r = client.post("/api/admin/readings", headers=admin_headers,
                    json={"station_id": test_station, "pollutant": "PM2.5",
                          "reading_datetime": when, "concentration_value": 182.4})
    assert r.status_code == 201
    body = r.get_json()
    assert body["sub_index"] == expected_pm25_sub_index(182.4) == 349
    day = when[:10]
    found = get_json(client, f"/api/readings?station_id={test_station}&from={day}&to={day}&limit=500")
    row = next(x for x in found["rows"] if x["reading_datetime"] == when)
    assert row["concentration"] == 182.4 and row["sub_index"] == 349


@pytest.mark.parametrize("value", [0, 29.99, 30, 59.5, 90, 120, 249.99, 250, 499.99, 500, 1000])
def test_admin_reading_sub_index_boundaries(client, admin_headers, test_station, value):
    r = client.post("/api/admin/readings", headers=admin_headers,
                    json={"station_id": test_station, "pollutant": "PM2.5",
                          "reading_datetime": unique_time(), "concentration_value": value})
    assert r.status_code == 201
    assert r.get_json()["sub_index"] == expected_pm25_sub_index(value)


def test_admin_reading_rejections(client, admin_headers, test_station):
    when = unique_time()
    ok = {"station_id": test_station, "pollutant": "PM2.5", "reading_datetime": when, "concentration_value": 50}
    # pollutant not assigned to this station -> 400 (composite foreign key)
    r = client.post("/api/admin/readings", headers=admin_headers, json={**ok, "pollutant": "PM10"})
    assert r.status_code == 400 and "not assigned" in r.get_json()["error"]
    assert client.post("/api/admin/readings", headers=admin_headers, json={**ok, "station_id": 9999}).status_code == 404
    # bad values -> 400
    for bad in (-5, "abc", None, True, 10_000_000, ""):
        assert client.post("/api/admin/readings", headers=admin_headers,
                           json={**ok, "concentration_value": bad}).status_code == 400
    for bad in ("2026-11-03", "2026-13-01T00:00:00", "2026-11-03T01:00:00Z", None):
        assert client.post("/api/admin/readings", headers=admin_headers,
                           json={**ok, "reading_datetime": bad}).status_code == 400
    assert client.post("/api/admin/readings", headers=admin_headers, json={**ok, "sub_index": 1}).status_code == 400
    # duplicate -> 409, and the first copy is untouched
    assert client.post("/api/admin/readings", headers=admin_headers, json=ok).status_code == 201
    assert client.post("/api/admin/readings", headers=admin_headers, json={**ok, "concentration_value": 99}).status_code == 409


def test_admin_reading_rolls_back_when_it_fails_midway(client, admin_headers, test_station, monkeypatch):
    """Atomicity: a failure AFTER the insert must leave no reading behind."""
    import contextlib
    import routes.admin as admin_module

    real_transaction = admin_module.transaction

    @contextlib.contextmanager
    def failing_transaction():
        with real_transaction() as cur:
            original = cur.execute

            def execute(sql, params=()):
                if sql.startswith("SELECT sub_index"):  # the last step of the route
                    raise RuntimeError("forced failure")
                return original(sql, params)

            cur.execute = execute
            yield cur

    when = unique_time()
    day = when[:10]
    before = get_json(client, f"/api/readings?station_id={test_station}&from={day}&to={day}")["total"]
    monkeypatch.setattr(admin_module, "transaction", failing_transaction)
    r = client.post("/api/admin/readings", headers=admin_headers,
                    json={"station_id": test_station, "pollutant": "PM2.5",
                          "reading_datetime": when, "concentration_value": 120})
    monkeypatch.undo()
    assert r.status_code == 500 and r.get_json() == {"error": "Internal server error"}
    after = get_json(client, f"/api/readings?station_id={test_station}&from={day}&to={day}")["total"]
    assert after == before
