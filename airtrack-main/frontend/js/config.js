// AirTrack frontend configuration.
// Flip USE_MOCK to false once the Flask backend is running (python app.py in backend/).
const API_BASE = "http://localhost:5000/api";
const USE_MOCK = true;

// Mock mode: JSON files live in frontend/mock/ (path is relative to the HTML page).
const MOCK_BASE = "mock";
const MOCK_DELAY_MS = 350; // fake network delay so loading spinners are visible

// Dates covered by the mock data. Same range as the sample data in the database
// (db/calc_daily_aqi.sql is run for 2026-10-18 .. 2026-10-24). Other dates answer 404, like the real API.
const MOCK_DATA_FROM = "2026-10-18";
const MOCK_DATA_TO = "2026-10-24";

// Rows per page in the search tables (backend allows 1-500, default 100).
const PAGE_SIZE = 25;
