"""AirTrack backend entry point. Run with: gunicorn app:app (on Render) or python app.py (locally)"""
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
    ensure_ascii = False
    sort_keys = False
    @staticmethod
    def default(o):
        if isinstance(o, Decimal): return float(o)
        if isinstance(o, datetime): return o.isoformat(timespec="seconds")
        if isinstance(o, date): return o.isoformat()
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
    # Bind to 0.0.0.0 so Render's router can access it
    app.run(host="0.0.0.0", port=Config.API_PORT, debug=False, threaded=True)
