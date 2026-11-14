"""One place that turns every failure into the contract's {"error": "message"} JSON."""
import mysql.connector
from flask import jsonify
from werkzeug.exceptions import HTTPException

# MySQL error numbers we translate into friendly answers
ER_DUP_ENTRY = 1062          # UNIQUE violated -> 409
ER_NO_REFERENCED_ROW = 1452  # FK violated (e.g. pollutant not assigned to station) -> 400
ER_CHECK_VIOLATED = 3819     # CHECK violated (e.g. negative concentration) -> 400


class ApiError(Exception):
    """Raise this from any route: raise ApiError("limit must be 1-500", 400)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(e):
        return jsonify({"error": e.message}), e.status

    @app.errorhandler(mysql.connector.Error)
    def handle_db_error(e):
        if e.errno == ER_DUP_ENTRY:
            return jsonify({"error": "Duplicate record"}), 409
        if e.errno == ER_NO_REFERENCED_ROW:
            return jsonify({"error": "Invalid reference: unknown station, or pollutant is not assigned to this station"}), 400
        if e.errno == ER_CHECK_VIOLATED:
            return jsonify({"error": "Value rejected by a database rule (for example a negative concentration)"}), 400
        app.logger.exception("Database error")  # full details go to the server log only
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        # 404 unknown URL, 405 wrong method, etc.
        return jsonify({"error": e.name}), e.code

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        app.logger.exception("Unhandled error")
        return jsonify({"error": "Internal server error"}), 500
