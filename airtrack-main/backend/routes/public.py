"""Public GET routes: lookups, latest readings, daily AQI, 24-hour summary."""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from db import fetch_all, fetch_one
from errors import ApiError
from validators import parse_date, parse_int

public_bp = Blueprint("public", __name__)


def _station_id(raw):
    """Read {id} from the URL, validate it (400 if not a number), and check it exists (404)."""
    sid = parse_int(raw, "station_id", minimum=1)
    if fetch_one("SELECT 1 AS ok FROM monitoring_station WHERE station_id = %s", (sid,)) is None:
        raise ApiError("Station not found", 404)
    return sid


# ---------- lookups ----------

@public_bp.get("/stations")
def list_stations():
    rows = fetch_all(
        "SELECT station_id, station_name, location, latitude, longitude, station_type, status "
        "FROM monitoring_station ORDER BY station_id"
    )
    return jsonify({"stations": rows})


@public_bp.get("/pollutants")
def list_pollutants():
    rows = fetch_all(
        "SELECT pollutant_id, pollutant_name, unit FROM pollutant ORDER BY pollutant_id"
    )
    return jsonify({"pollutants": rows})


@public_bp.get("/categories")
def list_categories():
    rows = fetch_all(
        "SELECT category_id, category_name, min_aqi, max_aqi, color_code, health_impact "
        "FROM aqi_category ORDER BY category_id"
    )
    return jsonify({"categories": rows})


# ---------- per-station data ----------

@public_bp.get("/stations/<station_id>/latest")
def station_latest(station_id):
    """Newest reading of each pollutant at this station (sub_index can be null)."""
    sid = _station_id(station_id)
    rows = fetch_all(
        "SELECT p.pollutant_name AS pollutant, r.concentration_value AS concentration, "
        "       r.sub_index, r.reading_datetime "
        "FROM reading r "
        "JOIN pollutant p ON p.pollutant_id = r.pollutant_id "
        "WHERE r.station_id = %s "
        "  AND r.reading_datetime = ("
        "      SELECT MAX(r2.reading_datetime) FROM reading r2 "
        "      WHERE r2.station_id = r.station_id AND r2.pollutant_id = r.pollutant_id) "
        "ORDER BY p.pollutant_id",
        (sid,),
    )
    return jsonify({"station_id": sid, "readings": rows})


@public_bp.get("/stations/<station_id>/aqi")
def station_aqi(station_id):
    """Daily AQI. No date given -> the latest date that has an AQI. 404 if none yet."""
    sid = _station_id(station_id)
    d = parse_date(request.args.get("date"))

    base = (
        "SELECT a.record_date, a.aqi_value, c.category_name, c.color_code, c.health_impact, "
        "       p.pollutant_name AS dominant_pollutant, a.hours_of_data, a.last_updated "
        "FROM aqi_record a "
        "JOIN aqi_category c ON c.category_id = a.category_id "
        "JOIN pollutant p ON p.pollutant_id = a.dominant_pollutant_id "
        "WHERE a.station_id = %s "
    )
    if d is None:
        rec = fetch_one(base + "ORDER BY a.record_date DESC LIMIT 1", (sid,))
        if rec is None:
            raise ApiError("No AQI has been calculated for this station yet", 404)
    else:
        rec = fetch_one(base + "AND a.record_date = %s", (sid, d))
        if rec is None:
            raise ApiError("No AQI for this station on that date", 404)

    return jsonify({
        "station_id": sid,
        "date": rec["record_date"],
        "aqi_value": rec["aqi_value"],
        "category": {
            "name": rec["category_name"],
            "color_code": rec["color_code"],
            "health_impact": rec["health_impact"],
        },
        "dominant_pollutant": rec["dominant_pollutant"],
        "hours_of_data": rec["hours_of_data"],
        "last_updated": rec["last_updated"],
    })


@public_bp.get("/stations/<station_id>/summary")
def station_summary(station_id):
    """Per-pollutant avg/min/max plus the hourly values of one day.

    No date given -> the latest date that has readings (works even before any AQI exists).
    Only hours that really exist are returned (no padding to 24).
    """
    sid = _station_id(station_id)
    d = parse_date(request.args.get("date"))

    if d is None:
        row = fetch_one(
            "SELECT MAX(reading_datetime) AS latest FROM reading WHERE station_id = %s", (sid,)
        )
        if row["latest"] is None:
            return jsonify({"station_id": sid, "date": None, "pollutants": []})
        d = row["latest"].date()

    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)  # range instead of DATE(col) = ... so the index can be used

    # One statement = one consistent snapshot. The window (OVER w) puts the day's
    # avg/min/max on every hourly row of that pollutant, so no second query is needed.
    rows = fetch_all(
        "SELECT p.pollutant_name AS pollutant, HOUR(r.reading_datetime) AS hr, "
        "       r.concentration_value AS concentration, r.sub_index, "
        "       AVG(r.concentration_value) OVER w AS avg_c, "
        "       MIN(r.concentration_value) OVER w AS min_c, "
        "       MAX(r.concentration_value) OVER w AS max_c "
        "FROM reading r "
        "JOIN pollutant p ON p.pollutant_id = r.pollutant_id "
        "WHERE r.station_id = %s AND r.reading_datetime >= %s AND r.reading_datetime < %s "
        "WINDOW w AS (PARTITION BY r.pollutant_id) "
        "ORDER BY r.pollutant_id, r.reading_datetime",
        (sid, start, end),
    )

    pollutants = {}
    for r in rows:
        item = pollutants.setdefault(r["pollutant"], {
            "pollutant": r["pollutant"],
            "avg": round(float(r["avg_c"]), 2),
            "min": float(r["min_c"]),
            "max": float(r["max_c"]),
            "hourly": [],
        })
        item["hourly"].append({
            "hour": r["hr"],
            "concentration": r["concentration"],
            "sub_index": r["sub_index"],
        })

    return jsonify({"station_id": sid, "date": d, "pollutants": list(pollutants.values())})
