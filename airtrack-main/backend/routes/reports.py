"""Report routes: compare stations, most polluted station, average AQI over time, data availability."""
from flask import Blueprint, jsonify, request

from db import fetch_all, fetch_one
from errors import ApiError
from validators import check_range, parse_choice, parse_date, parse_int

reports_bp = Blueprint("reports", __name__)


def _day_rows(select_sql, date_value, order_sql):
    """Run a one-statement query for one date. No date -> the latest date that has any AQI.

    COALESCE(%s, (SELECT MAX(...))) does the defaulting inside the same statement, so the
    date and the rows always come from the same snapshot.
    """
    sql = (
        select_sql +
        " WHERE a.record_date = COALESCE(%s, (SELECT MAX(record_date) FROM aqi_record)) " +
        order_sql
    )
    rows = fetch_all(sql, (date_value,))
    if not rows:
        if date_value is None:
            raise ApiError("No AQI has been calculated yet", 404)
        raise ApiError("No AQI records for that date", 404)
    return rows


@reports_bp.get("/reports/compare")
def compare_stations():
    """All stations that have an AQI on the date, highest AQI first."""
    d = parse_date(request.args.get("date"))
    rows = _day_rows(
        "SELECT a.record_date, a.station_id, s.station_name, a.aqi_value, "
        "       c.category_name AS category, c.color_code "
        "FROM aqi_record a "
        "JOIN monitoring_station s ON s.station_id = a.station_id "
        "JOIN aqi_category c ON c.category_id = a.category_id",
        d,
        "ORDER BY a.aqi_value DESC, s.station_name",
    )
    return jsonify({
        "date": rows[0]["record_date"],
        "stations": [
            {k: r[k] for k in ("station_id", "station_name", "aqi_value", "category", "color_code")}
            for r in rows
        ],
    })


@reports_bp.get("/reports/most-polluted")
def most_polluted():
    """The single station with the highest AQI on the date (ties: lowest station_id)."""
    d = parse_date(request.args.get("date"))
    rows = _day_rows(
        "SELECT a.record_date, a.station_id, s.station_name, a.aqi_value, "
        "       c.category_name AS category, p.pollutant_name AS dominant_pollutant "
        "FROM aqi_record a "
        "JOIN monitoring_station s ON s.station_id = a.station_id "
        "JOIN aqi_category c ON c.category_id = a.category_id "
        "JOIN pollutant p ON p.pollutant_id = a.dominant_pollutant_id",
        d,
        "ORDER BY a.aqi_value DESC, a.station_id LIMIT 1",
    )
    r = rows[0]
    return jsonify({
        "date": r["record_date"],
        "station_id": r["station_id"],
        "station_name": r["station_name"],
        "aqi_value": r["aqi_value"],
        "category": r["category"],
        "dominant_pollutant": r["dominant_pollutant"],
    })


@reports_bp.get("/reports/average")
def average_aqi():
    """Average AQI of one station per day or per month (GROUP BY on the date)."""
    raw_id = request.args.get("station_id")
    if raw_id is None or raw_id == "":
        raise ApiError("station_id is required", 400)
    sid = parse_int(raw_id, "station_id", minimum=1)
    period = parse_choice(request.args.get("period"), "period", ("daily", "monthly"), default="daily")
    date_from = parse_date(request.args.get("from"), "from")
    date_to = parse_date(request.args.get("to"), "to")
    check_range(date_from, date_to)

    if fetch_one("SELECT 1 AS ok FROM monitoring_station WHERE station_id = %s", (sid,)) is None:
        raise ApiError("Station not found", 404)

    # The date format goes in as a parameter (not typed into the SQL) because a literal % in the
    # SQL text would clash with the %s placeholders.
    label_format = "%Y-%m" if period == "monthly" else "%Y-%m-%d"
    where, params = ["station_id = %s"], [label_format, sid]
    if date_from is not None:
        where.append("record_date >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append("record_date <= %s")
        params.append(date_to)

    rows = fetch_all(
        "SELECT DATE_FORMAT(record_date, %s) AS label, ROUND(AVG(aqi_value), 1) AS avg_aqi "
        "FROM aqi_record WHERE " + " AND ".join(where) +
        " GROUP BY label ORDER BY label",
        tuple(params),
    )
    return jsonify({"station_id": sid, "period": period, "points": rows})


@reports_bp.get("/reports/availability")
def availability():
    """How much data each station has per pollutant (assigned pollutants with no readings show 0)."""
    rows = fetch_all(
        "SELECT s.station_name, p.pollutant_name AS pollutant, "
        "       COUNT(r.reading_id) AS reading_count, "
        "       MIN(r.reading_datetime) AS `first`, MAX(r.reading_datetime) AS `last` "
        "FROM station_pollutant sp "
        "JOIN monitoring_station s ON s.station_id = sp.station_id "
        "JOIN pollutant p ON p.pollutant_id = sp.pollutant_id "
        "LEFT JOIN reading r ON r.station_id = sp.station_id AND r.pollutant_id = sp.pollutant_id "
        "GROUP BY s.station_id, s.station_name, p.pollutant_id, p.pollutant_name "
        "ORDER BY s.station_id, p.pollutant_id"
    )
    return jsonify({"rows": rows})
