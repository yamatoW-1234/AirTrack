"""AirTrack backend entry point. Run with:  python app.py   (from the backend/ folder)"""
from datetime import date, datetime
from decimal import Decimal

from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

from config import Config
from errors import register_error_handlers
from routes.admin import admin_bp
from routes.public import public_bp
from routes.reports import reports_bp
from routes.search import search_bp


class AirTrackJSONProvider(DefaultJSONProvider):
    """Makes JSON match the contract.

    Flask's default turns Decimal into a string and datetime into an HTTP-date,
    and sorts keys alphabetically. The contract wants numbers, ISO times
    (YYYY-MM-DDTHH:MM:SS) and keys in the documented order.
    """

    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, datetime):  # check datetime before date (datetime is a subclass of date)
            return o.isoformat(timespec="seconds")
        if isinstance(o, date):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


def create_app():
    app = Flask(__name__)
    app.json = AirTrackJSONProvider(app)

    CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}})
    register_error_handlers(app)

    app.register_blueprint(public_bp, url_prefix="/api")
    app.register_blueprint(search_bp, url_prefix="/api")
    app.register_blueprint(reports_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")

    return app


app = create_app()

if __name__ == "__main__":
    # debug stays off on purpose: the debugger page would expose stack traces
    app.run(host="127.0.0.1", port=Config.API_PORT, debug=False, threaded=True)
