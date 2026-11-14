"""Settings for the AirTrack backend. Values come from the .env file in the repo root."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "airtrack")

    DB_READER_USER = os.getenv("DB_READER_USER")
    DB_READER_PASSWORD = os.getenv("DB_READER_PASSWORD")
    DB_WRITER_USER = os.getenv("DB_WRITER_USER")
    DB_WRITER_PASSWORD = os.getenv("DB_WRITER_PASSWORD")

    ADMIN_KEY = os.getenv("ADMIN_KEY")

    # Render injects the PORT environment variable automatically
    API_PORT = int(os.getenv("PORT", 5000))
    
    # Read CORS origins from environment, fallback to localhost for dev
    CORS_ORIGINS_STR = os.getenv("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
    CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(",")]

    DEFAULT_LIMIT = 100
    MAX_LIMIT = 500
    READER_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", 32))
    WRITER_POOL_SIZE = int(os.getenv("DB_WRITER_POOL_SIZE", 5))