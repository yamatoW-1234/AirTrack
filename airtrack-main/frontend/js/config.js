const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.protocol === "file:";
const API_BASE = isLocal ? "http://localhost:5000/api" : "https://YOUR-BACKEND-NAME.onrender.com/api"; 
const USE_MOCK = isLocal; 
const MOCK_BASE = "mock";
const MOCK_DELAY_MS = 350;
const MOCK_DATA_FROM = "2026-10-18";
const MOCK_DATA_TO = "2026-10-24";
const PAGE_SIZE = 25;
