"""Settings for the AirTrack backend. Values come from the .env file in the repo root."""
import os
from pathlib import Path

from dotenv import load_dotenv

# .env lives in the repo root (one level above backend/) and is never committed
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "airtrack")

    # Two accounts: reader for GET routes, writer for admin POST/PUT
    DB_READER_USER = os.getenv("DB_READER_USER")
    DB_READER_PASSWORD = os.getenv("DB_READER_PASSWORD")
    DB_WRITER_USER = os.getenv("DB_WRITER_USER")
    DB_WRITER_PASSWORD = os.getenv("DB_WRITER_PASSWORD")

    ADMIN_KEY = os.getenv("ADMIN_KEY")

    API_PORT = 5000
    CORS_ORIGINS = ["http://localhost:5500", "http://127.0.0.1:5500"]

    # Paging rules from the contract
    DEFAULT_LIMIT = 100
    MAX_LIMIT = 500

    # mysql-connector allows at most 32 connections per pool.
    # The reader pool is big so the 30-thread concurrency test does not starve.
    READER_POOL_SIZE = 32
    WRITER_POOL_SIZE = 5
