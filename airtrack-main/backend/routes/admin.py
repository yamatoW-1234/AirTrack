"""Admin routes (all need the X-Admin-Key header): stations, pollutant assignment, add one reading.

These are the only routes that write. They use the writer database account, and every change
runs inside one transaction (all or nothing).
"""
import hmac
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import mysql.connector
from flask import Blueprint, jsonify, request

from config import Config
from db import transaction
from errors import ER_DUP_ENTRY, ER_NO_REFERENCED_ROW, ApiError
from validators import parse_date, parse_int

admin_bp = Blueprint("admin", __name__)

STATION_FIELDS = (
    "station_name", "location", "latitude", "longitude",
    "station_type", "status", "installation_date",
)
_DATETIME_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}")
_MAX_CONCENTRATION = Decimal("999999.99")  # DECIMAL(8,2)


# ---------- admin key ----------

@admin_bp.before_request
def require_admin_key():
    if request.method == "OPTIONS":
        return None  # a browser's CORS preflight never carries custom headers
    sent = request.headers.get("X-Admin-Key", "")
    expected = Config.ADMIN_KEY or ""
    # compare_digest takes the same time however many characters match (no timing leak)
    if not expected or not hmac.compare_digest(sent.encode("utf-8"), expected.encode("utf-8")):
        raise ApiError("Invalid or missing admin key", 401)


# ---------- small input helpers ----------

def _json_body():
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        raise ApiError("Request body must be a JSON object", 400)
    return body


def _only_fields(body, allowed):
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise ApiError("Unknown field(s): " + ", ".join(unknown), 400)


def _text(value, name, max_len, required=False):
    if value is None:
        if required:
            raise ApiError(f"{name} is required", 400)
        return None
    if not isinstance(value, str):
        raise ApiError(f"{name} must be text", 400)
    value = value.strip()
    if required and value == "":
        raise ApiError(f"{name} is required", 400)
    if len(value) > max_len:
        raise ApiError(f"{name} must be at most {max_len} characters", 400)
    return value or None


def _coordinate(value, name, low, high):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ApiError(f"{name} must be a number", 400)
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ApiError(f"{name} must be a number", 400)
    if not number.is_finite() or number < low or number > high:
        raise ApiError(f"{name} must be between {low} and {high}", 400)
    return number.quantize(Decimal("0.000001"))


def _int_field(body, name):
    value = body.get(name)
    if value is None or value == "":
        raise ApiError(f"{name} is required", 400)
    if isinstance(value, (bool, float)):
        raise ApiError(f"{name} must be an integer", 400)
    return parse_int(value, name, minimum=1)


def _clean_station(body, name_required):
    """Validate station fields and return {column: value}. Only whitelisted columns get through."""
    _only_fields(body, STATION_FIELDS)
    out = {}
    if "station_name" in body:
        out["station_name"] = _text(body["station_name"], "station_name", 100, required=True)
    elif name_required:
        raise ApiError("station_name is required", 400)
    if "location" in body:
        out["location"] = _text(body["location"], "location", 100)
    if "station_type" in body:
        out["station_type"] = _text(body["station_type"], "station_type", 30)
    if "latitude" in body:
        out["latitude"] = _coordinate(body["latitude"], "latitude", -90, 90)
    if "longitude" in body:
        out["longitude"] = _coordinate(body["longitude"], "longitude", -180, 180)
    if "status" in body:
        if body["status"] not in ("Active", "Inactive"):
            raise ApiError("status must be one of: Active, Inactive", 400)
        out["status"] = body["status"]
    if "installation_date" in body:
        raw = body["installation_date"]
        if raw is not None and not isinstance(raw, str):
            raise ApiError("installation_date must be in YYYY-MM-DD format", 400)
        out["installation_date"] = parse_date(raw, "installation_date")
    return out


def _reading_datetime(value):
    if not isinstance(value, str) or not _DATETIME_RE.fullmatch(value.strip()):
        raise ApiError("reading_datetime is required in the form 2026-10-23T14:00:00", 400)
    try:
        when = datetime.strptime(value.strip().replace(" ", "T"), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise ApiError("reading_datetime is not a real date and time", 400)
    if when.year < 1000:
        raise ApiError("reading_datetime year is out of range", 400)
    return when


def _concentration(value):
    if value is None or value == "":
        raise ApiError("concentration_value is required", 400)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ApiError("concentration_value must be a number", 400)
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ApiError("concentration_value must be a number", 400)
    if not number.is_finite():
        raise ApiError("concentration_value must be a number", 400)
    if number < 0:
        raise ApiError("concentration_value must not be negative", 400)
    if number > _MAX_CONCENTRATION:
        raise ApiError("concentration_value is too large", 400)
    return number.quantize(Decimal("0.01"))


# ---------- stations ----------

@admin_bp.post("/admin/stations")
def add_station():
    fields = _clean_station(_json_body(), name_required=True)
    columns = list(fields)  # only whitelisted column names, never user text
    with transaction() as cur:
        cur.execute(
            "INSERT INTO monitoring_station (" + ", ".join(columns) + ") "
            "VALUES (" + ", ".join(["%s"] * len(columns)) + ")",
            tuple(fields[c] for c in columns),
        )
        new_id = cur.lastrowid
    return jsonify({"station_id": new_id}), 201


@admin_bp.put("/admin/stations/<station_id>")
def update_station(station_id):
    sid = parse_int(station_id, "station_id", minimum=1)
    fields = _clean_station(_json_body(), name_required=False)
    if not fields:
        raise ApiError("Send at least one field to change", 400)
    columns = list(fields)
    with transaction() as cur:
        cur.execute("SELECT station_id FROM monitoring_station WHERE station_id = %s FOR UPDATE", (sid,))
        if cur.fetchone() is None:
            raise ApiError("Station not found", 404)
        cur.execute(
            "UPDATE monitoring_station SET " + ", ".join(f"{c} = %s" for c in columns) +
            " WHERE station_id = %s",
            tuple(fields[c] for c in columns) + (sid,),
        )
    return jsonify({"station_id": sid}), 200


# ---------- which station measures which pollutant ----------

@admin_bp.post("/admin/station-pollutants")
def assign_pollutant():
    body = _json_body()
    _only_fields(body, ("station_id", "pollutant"))
    sid = _int_field(body, "station_id")
    name = _text(body.get("pollutant"), "pollutant", 10, required=True)
    with transaction() as cur:
        cur.execute("SELECT 1 AS ok FROM monitoring_station WHERE station_id = %s", (sid,))
        if cur.fetchone() is None:
            raise ApiError("Station not found", 404)
        cur.execute("SELECT pollutant_id, pollutant_name FROM pollutant WHERE pollutant_name = %s", (name,))
        pollutant = cur.fetchone()
        if pollutant is None:
            raise ApiError("Unknown pollutant (use PM2.5, PM10, NO2 or SO2)", 400)
        try:
            cur.execute(
                "INSERT INTO station_pollutant (station_id, pollutant_id) VALUES (%s, %s)",
                (sid, pollutant["pollutant_id"]),
            )
        except mysql.connector.Error as e:
            if e.errno == ER_DUP_ENTRY:
                raise ApiError("This pollutant is already assigned to the station", 409) from e
            raise
    return jsonify({"station_id": sid, "pollutant": pollutant["pollutant_name"]}), 201


# ---------- one reading ----------

@admin_bp.post("/admin/readings")
def add_reading():
    """Insert one reading and calculate its sub-index, in ONE transaction.

    Atomicity: if anything fails after the INSERT (or the INSERT itself is rejected),
    the whole transaction rolls back and no half-finished reading is left behind.
    """
    body = _json_body()
    _only_fields(body, ("station_id", "pollutant", "reading_datetime", "concentration_value"))
    sid = _int_field(body, "station_id")
    name = _text(body.get("pollutant"), "pollutant", 10, required=True)
    when = _reading_datetime(body.get("reading_datetime"))
    value = _concentration(body.get("concentration_value"))

    with transaction() as cur:
        cur.execute("SELECT 1 AS ok FROM monitoring_station WHERE station_id = %s", (sid,))
        if cur.fetchone() is None:
            raise ApiError("Station not found", 404)
        cur.execute("SELECT pollutant_id FROM pollutant WHERE pollutant_name = %s", (name,))
        pollutant = cur.fetchone()
        if pollutant is None:
            raise ApiError("Unknown pollutant (use PM2.5, PM10, NO2 or SO2)", 400)
        pid = pollutant["pollutant_id"]

        # 1) insert. The composite FK (station_id, pollutant_id) -> station_pollutant is what
        #    rejects a pollutant that is not assigned to this station.
        try:
            cur.execute(
                "INSERT INTO reading (station_id, pollutant_id, reading_datetime, concentration_value) "
                "VALUES (%s, %s, %s, %s)",
                (sid, pid, when, value),
            )
        except mysql.connector.Error as e:
            if e.errno == ER_NO_REFERENCED_ROW:
                raise ApiError(f"Pollutant {name} is not assigned to station {sid}", 400) from e
            if e.errno == ER_DUP_ENTRY:
                raise ApiError("A reading for this station, pollutant and time already exists", 409) from e
            raise
        reading_id = cur.lastrowid

        # 2) sub-index: same formula and capping as db/calc_subindex.sql, for this one row.
        cur.execute(
            "UPDATE reading r "
            "JOIN breakpoint b ON b.pollutant_id = r.pollutant_id "
            "                 AND r.concentration_value >= b.conc_low "
            "                 AND r.concentration_value <  b.conc_high "
            "SET r.sub_index = ROUND("
            "      (b.index_high - b.index_low) / (b.conc_high - b.conc_low) "
            "      * (r.concentration_value - b.conc_low) + b.index_low) "
            "WHERE r.reading_id = %s",
            (reading_id,),
        )
        # at or above the top of the Severe range -> capped at 500
        cur.execute(
            "UPDATE reading r "
            "JOIN breakpoint b ON b.pollutant_id = r.pollutant_id AND b.category_id = 6 "
            "                 AND r.concentration_value >= b.conc_high "
            "SET r.sub_index = 500 "
            "WHERE r.reading_id = %s AND r.sub_index IS NULL",
            (reading_id,),
        )
        cur.execute("SELECT sub_index FROM reading WHERE reading_id = %s", (reading_id,))
        sub_index = cur.fetchone()["sub_index"]
    # the block ended without an error -> committed
    return jsonify({"reading_id": reading_id, "sub_index": sub_index}), 201
