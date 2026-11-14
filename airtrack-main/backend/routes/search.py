"""Search routes: /readings and /aqi-records with optional filters (any combination) and paging."""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from db import fetch_one, get_conn
from errors import ApiError
from validators import check_range, parse_date, parse_int, parse_paging

search_bp = Blueprint("search", __name__)


def _run_page(count_sql, rows_sql, params, limit, offset):
    """Return (total, rows) from ONE consistent snapshot.

    Both queries run inside a single REPEATABLE READ transaction, so while the ingestion job
    or an admin POST is inserting new readings, `total` always matches the rows that are
    returned. Without this, the count could include a reading that the page query does not.
    """
    with get_conn("reader") as conn:
        conn.start_transaction(consistent_snapshot=True, isolation_level="REPEATABLE READ")
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(count_sql, params)
            total = cur.fetchone()["total"]
            cur.execute(rows_sql + " LIMIT %s OFFSET %s", params + (limit, offset))
            rows = cur.fetchall()
        finally:
            cur.close()
            conn.commit()  # ends the read-only transaction before the connection goes back to the pool
    return total, rows


def _day_range(date_from, date_to):
    """Inclusive dates -> [start, end) datetimes, so the (station_id, reading_datetime) index can be used."""
    start = datetime.combine(date_from, datetime.min.time()) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time()) if date_to else None
    return start, end


@search_bp.get("/readings")
def search_readings():
    """GET /readings?station_id=&pollutant=&from=&to=&limit=&offset=  (newest first)."""
    station_id = parse_int(request.args.get("station_id"), "station_id", minimum=1)
    pollutant = (request.args.get("pollutant") or "").strip()
    date_from = parse_date(request.args.get("from"), "from")
    date_to = parse_date(request.args.get("to"), "to")
    check_range(date_from, date_to)
    limit, offset = parse_paging(request.args)

    where, params = [], []
    if station_id is not None:
        where.append("r.station_id = %s")
        params.append(station_id)
    if pollutant:
        row = fetch_one("SELECT pollutant_id FROM pollutant WHERE pollutant_name = %s", (pollutant,))
        if row is None:
            raise ApiError("Unknown pollutant (use PM2.5, PM10, NO2 or SO2)", 400)
        where.append("r.pollutant_id = %s")
        params.append(row["pollutant_id"])
    start, end = _day_range(date_from, date_to)
    if start is not None:
        where.append("r.reading_datetime >= %s")
        params.append(start)
    if end is not None:
        where.append("r.reading_datetime < %s")
        params.append(end)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total, rows = _run_page(
        "SELECT COUNT(*) AS total FROM reading r" + clause,
        "SELECT s.station_name, p.pollutant_name AS pollutant, r.reading_datetime, "
        "       r.concentration_value AS concentration, r.sub_index "
        "FROM reading r "
        "JOIN monitoring_station s ON s.station_id = r.station_id "
        "JOIN pollutant p ON p.pollutant_id = r.pollutant_id"
        + clause +
        " ORDER BY r.reading_datetime DESC, r.reading_id DESC",
        tuple(params), limit, offset,
    )
    return jsonify({"total": total, "limit": limit, "offset": offset, "rows": rows})


@search_bp.get("/aqi-records")
def search_aqi_records():
    """GET /aqi-records?station_id=&from=&to=&category=&limit=&offset=  (newest date first).

    category can be the category name (Poor, "Very Poor", ...) or its id (1-6).
    """
    station_id = parse_int(request.args.get("station_id"), "station_id", minimum=1)
    date_from = parse_date(request.args.get("from"), "from")
    date_to = parse_date(request.args.get("to"), "to")
    check_range(date_from, date_to)
    category = (request.args.get("category") or "").strip()
    limit, offset = parse_paging(request.args)

    where, params = [], []
    if station_id is not None:
        where.append("a.station_id = %s")
        params.append(station_id)
    if date_from is not None:
        where.append("a.record_date >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append("a.record_date <= %s")
        params.append(date_to)
    if category:
        if category.isdigit():
            row = fetch_one("SELECT category_id FROM aqi_category WHERE category_id = %s", (int(category),))
        else:
            row = fetch_one("SELECT category_id FROM aqi_category WHERE category_name = %s", (category,))
        if row is None:
            raise ApiError("Unknown category (use a name like Poor or an id from 1 to 6)", 400)
        where.append("a.category_id = %s")
        params.append(row["category_id"])
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total, rows = _run_page(
        "SELECT COUNT(*) AS total FROM aqi_record a" + clause,
        "SELECT a.station_id, s.station_name, a.record_date AS `date`, a.aqi_value, "
        "       c.category_name AS category, p.pollutant_name AS dominant_pollutant "
        "FROM aqi_record a "
        "JOIN monitoring_station s ON s.station_id = a.station_id "
        "JOIN aqi_category c ON c.category_id = a.category_id "
        "JOIN pollutant p ON p.pollutant_id = a.dominant_pollutant_id"
        + clause +
        " ORDER BY a.record_date DESC, a.station_id",
        tuple(params), limit, offset,
    )
    return jsonify({"total": total, "rows": rows})
