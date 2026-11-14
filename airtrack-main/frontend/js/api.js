// AirTrack API layer. Pages call these functions and never use fetch() directly.
// Load order in every page: js/config.js, then js/api.js.
// Every wrapper returns the backend JSON exactly as documented, for example
// getStations() -> { stations: [...] }, searchReadings() -> { total, limit, offset, rows: [...] }.
// Failures throw ApiError(status, message). The message is the backend's {"error": "..."} text.

// ---------- Errors ----------
class ApiError extends Error {
  constructor(status, message, body = null) {
    super(message);
    this.name = "ApiError";
    this.status = status; // 0 = could not reach the server; otherwise the HTTP status
    this.body = body;
  }
  get isNetwork() { return this.status === 0; }
  get isBadRequest() { return this.status === 400; }
  get isUnauthorized() { return this.status === 401; }
  get isNotFound() { return this.status === 404; }
  get isConflict() { return this.status === 409; }
}

// Turns any error into one friendly line for the UI.
// notFoundText lets a page say what a 404 means there, for example "No AQI data available for this date yet."
function describeError(err, notFoundText) {
  if (!(err instanceof ApiError)) return (err && err.message) || "Something went wrong.";
  if (err.isNetwork) {
    return USE_MOCK ? err.message : "Cannot reach the backend at " + API_BASE + ". Is it running (python app.py)?";
  }
  if (err.isUnauthorized) return "Unauthorized: the admin key is missing or wrong.";
  if (err.isNotFound && notFoundText) return notFoundText;
  return err.message || "Server error (" + err.status + ").";
}

// ---------- Admin key: kept in JS memory only, never stored or hardcoded ----------
let _adminKey = "";
function setAdminKey(key) { _adminKey = (key || "").trim(); }
function getAdminKey() { return _adminKey; }

// ---------- Helpers ----------
function _qs(params = {}) {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v).trim() !== "") sp.append(k, String(v).trim());
  });
  const s = sp.toString();
  return s ? "?" + s : "";
}
const _id = (v) => encodeURIComponent(v);

// ---------- Real backend ----------
async function _request(path, { method = "GET", body = null, admin = false, adminKey = null } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== null) headers["Content-Type"] = "application/json";
  if (admin) headers["X-Admin-Key"] = adminKey !== null ? adminKey : _adminKey;

  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body !== null ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, "Network error: " + e.message);
  }

  let data = null;
  try { data = await res.json(); } catch (_) { /* empty or non-JSON body */ }

  if (!res.ok) {
    const msg = (data && data.error) || res.statusText || "Request failed";
    throw new ApiError(res.status, msg, data);
  }
  return data;
}

// ---------- Mock backend (mirrors the real validation and error messages) ----------
const _POLLUTANTS = ["PM2.5", "PM10", "NO2", "SO2"];
const _mockCache = {};

const _mockDelay = () => new Promise((r) => setTimeout(r, MOCK_DELAY_MS));

async function _mockLoad(name) {
  if (!_mockCache[name]) {
    let res;
    try {
      res = await fetch(MOCK_BASE + "/" + name + ".json");
    } catch (e) {
      throw new ApiError(0, "Cannot load " + MOCK_BASE + "/" + name + ".json. Serve the frontend folder with a static server (python -m http.server 5500).");
    }
    if (!res.ok) throw new ApiError(res.status, "Mock file " + MOCK_BASE + "/" + name + ".json not found.");
    _mockCache[name] = await res.json();
  }
  return JSON.parse(JSON.stringify(_mockCache[name])); // clone, so callers may edit freely
}

function _mockInt(value, name, min, max, def) {
  if (value === undefined || value === null || value === "") return def;
  const n = Number(value);
  if (!Number.isInteger(n)) throw new ApiError(400, name + " must be an integer");
  if (min !== undefined && n < min) throw new ApiError(400, name + " must be at least " + min);
  if (max !== undefined && n > max) throw new ApiError(400, name + " must be at most " + max);
  return n;
}

function _mockDate(value, name) {
  if (value === undefined || value === null || value === "") return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new ApiError(400, name + " must be in YYYY-MM-DD format");
  const d = new Date(value + "T00:00:00Z");
  if (isNaN(d) || d.toISOString().slice(0, 10) !== value) throw new ApiError(400, name + " is not a real calendar date");
  return value;
}

function _mockRange(from, to) {
  if (from && to && from > to) throw new ApiError(400, "from must not be after to");
}

async function _mockStation(stationId) {
  const sid = _mockInt(stationId, "station_id", 1);
  const st = (await _mockLoad("stations")).stations.find((s) => s.station_id === sid);
  if (!st) throw new ApiError(404, "Station not found");
  return st;
}

function _round1(x) { return Math.round(x * 10) / 10; }

// ---------- Public API: lookups ----------
async function getStations() {
  if (!USE_MOCK) return _request("/stations");
  await _mockDelay();
  return _mockLoad("stations"); // { stations: [{station_id, station_name, location, latitude, longitude, station_type, status}] }
}

async function getPollutants() {
  if (!USE_MOCK) return _request("/pollutants");
  await _mockDelay();
  return _mockLoad("pollutants"); // { pollutants: [{pollutant_id, pollutant_name, unit}] }
}

async function getCategories() {
  if (!USE_MOCK) return _request("/categories");
  await _mockDelay();
  return _mockLoad("categories"); // { categories: [{category_id, category_name, min_aqi, max_aqi, color_code, health_impact}] }
}

// ---------- Public API: per station ----------
// Newest reading of each pollutant. Returns { station_id, readings: [{pollutant, concentration, sub_index, reading_datetime}] }.
// Note: no station name and no unit in this response; get them from getStations() / getPollutants().
async function getLatest(stationId) {
  if (!USE_MOCK) return _request("/stations/" + _id(stationId) + "/latest");
  await _mockDelay();
  const st = await _mockStation(stationId);
  const d = await _mockLoad("latest");
  d.station_id = st.station_id;
  return d;
}

// Daily AQI. Omit date for the latest date that has an AQI. Throws ApiError(404) when there is none.
// Returns { station_id, date, aqi_value, category: {name, color_code, health_impact}, dominant_pollutant, hours_of_data, last_updated }.
async function getAqi(stationId, date) {
  if (!USE_MOCK) return _request("/stations/" + _id(stationId) + "/aqi" + _qs({ date }));
  await _mockDelay();
  const st = await _mockStation(stationId);
  const d = _mockDate(date, "date");
  const ref = await _mockLoad("aqi");
  if (!d && ref.station_id === st.station_id) return ref;

  const rows = (await _mockLoad("aqi-records")).rows.filter((r) => r.station_id === st.station_id);
  const rec = d ? rows.find((r) => r.date === d) : rows.reduce((a, b) => (!a || b.date > a.date ? b : a), null);
  if (!rec) throw new ApiError(404, d ? "No AQI for this station on that date" : "No AQI has been calculated for this station yet");
  const cat = (await _mockLoad("categories")).categories.find((c) => c.category_name === rec.category);
  return {
    station_id: rec.station_id,
    date: rec.date,
    aqi_value: rec.aqi_value,
    category: { name: cat.category_name, color_code: cat.color_code, health_impact: cat.health_impact },
    dominant_pollutant: rec.dominant_pollutant,
    hours_of_data: 24,
    last_updated: rec.date + "T23:59:00",
  };
}

// Per pollutant avg/min/max plus the hourly values of one day. Omit date for the latest day with readings.
// Only hours that exist are returned (no padding to 24). A day without readings is 200 with pollutants: [].
// Returns { station_id, date, pollutants: [{pollutant, avg, min, max, hourly: [{hour, concentration, sub_index}]}] }.
// Mock note: every station and in-range date gets the same hourly sample.
async function getSummary(stationId, date) {
  if (!USE_MOCK) return _request("/stations/" + _id(stationId) + "/summary" + _qs({ date }));
  await _mockDelay();
  const st = await _mockStation(stationId);
  const d = _mockDate(date, "date");
  const ref = await _mockLoad("summary");
  const day = d || ref.date;
  if (day < MOCK_DATA_FROM || day > MOCK_DATA_TO) return { station_id: st.station_id, date: day, pollutants: [] };
  ref.station_id = st.station_id;
  ref.date = day;
  return ref;
}

// ---------- Public API: search (paged) ----------
// params: station_id, pollutant, from, to (YYYY-MM-DD), limit (1-500, default 100), offset.
// Returns { total, limit, offset, rows: [{station_name, pollutant, reading_datetime, concentration, sub_index}] }, newest first.
// The backend has no category filter on readings; the category filter belongs to searchAqiRecords().
async function searchReadings(params = {}) {
  if (!USE_MOCK) return _request("/readings" + _qs(params));
  await _mockDelay();
  const sid = _mockInt(params.station_id, "station_id", 1);
  const pollutant = String(params.pollutant || "").trim();
  const from = _mockDate(params.from, "from");
  const to = _mockDate(params.to, "to");
  _mockRange(from, to);
  const limit = _mockInt(params.limit, "limit", 1, 500, 100);
  const offset = _mockInt(params.offset, "offset", 0, undefined, 0);

  let rows = (await _mockLoad("readings")).rows;
  if (sid !== undefined) {
    const st = (await _mockLoad("stations")).stations.find((s) => s.station_id === sid);
    rows = st ? rows.filter((r) => r.station_name === st.station_name) : [];
  }
  if (pollutant) {
    if (!_POLLUTANTS.includes(pollutant)) throw new ApiError(400, "Unknown pollutant (use PM2.5, PM10, NO2 or SO2)");
    rows = rows.filter((r) => r.pollutant === pollutant);
  }
  if (from) rows = rows.filter((r) => r.reading_datetime.slice(0, 10) >= from);
  if (to) rows = rows.filter((r) => r.reading_datetime.slice(0, 10) <= to);
  return { total: rows.length, limit, offset, rows: rows.slice(offset, offset + limit) };
}

// params: station_id, from, to, category (name like "Very Poor" or id 1-6), limit, offset.
// Returns { total, rows: [{station_id, station_name, date, aqi_value, category, dominant_pollutant}] }, newest date first.
// Note: this response has NO limit/offset keys, so the page must remember the limit/offset it sent.
async function searchAqiRecords(params = {}) {
  if (!USE_MOCK) return _request("/aqi-records" + _qs(params));
  await _mockDelay();
  const sid = _mockInt(params.station_id, "station_id", 1);
  const from = _mockDate(params.from, "from");
  const to = _mockDate(params.to, "to");
  _mockRange(from, to);
  const category = String(params.category || "").trim();
  const limit = _mockInt(params.limit, "limit", 1, 500, 100);
  const offset = _mockInt(params.offset, "offset", 0, undefined, 0);

  let rows = (await _mockLoad("aqi-records")).rows;
  if (sid !== undefined) rows = rows.filter((r) => r.station_id === sid);
  if (from) rows = rows.filter((r) => r.date >= from);
  if (to) rows = rows.filter((r) => r.date <= to);
  if (category) {
    const cats = (await _mockLoad("categories")).categories;
    const c = /^\d+$/.test(category)
      ? cats.find((x) => x.category_id === Number(category))
      : cats.find((x) => x.category_name === category);
    if (!c) throw new ApiError(400, "Unknown category (use a name like Poor or an id from 1 to 6)");
    rows = rows.filter((r) => r.category === c.category_name);
  }
  return { total: rows.length, rows: rows.slice(offset, offset + limit) };
}

// ---------- Public API: reports ----------
// All stations on one date, highest AQI first. Omit date for the latest date. 404 if no AQI for that date.
// Returns { date, stations: [{station_id, station_name, aqi_value, category, color_code}] }.
async function getCompare(date) {
  if (!USE_MOCK) return _request("/reports/compare" + _qs({ date }));
  await _mockDelay();
  const d = _mockDate(date, "date");
  if (!d) return _mockLoad("compare");
  const rows = (await _mockLoad("aqi-records")).rows.filter((r) => r.date === d);
  if (!rows.length) throw new ApiError(404, "No AQI records for that date");
  const cats = (await _mockLoad("categories")).categories;
  rows.sort((a, b) => b.aqi_value - a.aqi_value || a.station_name.localeCompare(b.station_name));
  return {
    date: d,
    stations: rows.map((r) => ({
      station_id: r.station_id,
      station_name: r.station_name,
      aqi_value: r.aqi_value,
      category: r.category,
      color_code: cats.find((c) => c.category_name === r.category).color_code,
    })),
  };
}

// Station with the highest AQI on a date (omit date for the latest). 404 if none.
// Returns { date, station_id, station_name, aqi_value, category, dominant_pollutant }. No color_code here:
// look it up in getCategories() by category name.
async function getMostPolluted(date) {
  if (!USE_MOCK) return _request("/reports/most-polluted" + _qs({ date }));
  await _mockDelay();
  const d = _mockDate(date, "date");
  if (!d) return _mockLoad("most-polluted");
  const rows = (await _mockLoad("aqi-records")).rows.filter((r) => r.date === d);
  if (!rows.length) throw new ApiError(404, "No AQI records for that date");
  rows.sort((a, b) => b.aqi_value - a.aqi_value || a.station_id - b.station_id);
  const r = rows[0];
  return {
    date: d,
    station_id: r.station_id,
    station_name: r.station_name,
    aqi_value: r.aqi_value,
    category: r.category,
    dominant_pollutant: r.dominant_pollutant,
  };
}

// Average AQI of one station per day or month. period: "daily" (default) | "monthly". from/to optional dates.
// Returns { station_id, period, points: [{label, avg_aqi}] } where label is YYYY-MM-DD or YYYY-MM.
async function getAverage(stationId, period = "daily", from = "", to = "") {
  if (!USE_MOCK) return _request("/reports/average" + _qs({ station_id: stationId, period, from, to }));
  await _mockDelay();
  if (stationId === undefined || stationId === null || stationId === "") throw new ApiError(400, "station_id is required");
  const st = await _mockStation(stationId);
  if (period !== "daily" && period !== "monthly") throw new ApiError(400, "period must be one of: daily, monthly");
  const f = _mockDate(from, "from");
  const t = _mockDate(to, "to");
  _mockRange(f, t);

  if (st.station_id === 1 && !f && !t) return (await _mockLoad("average"))[period];

  let rows = (await _mockLoad("aqi-records")).rows.filter((r) => r.station_id === st.station_id);
  if (f) rows = rows.filter((r) => r.date >= f);
  if (t) rows = rows.filter((r) => r.date <= t);
  const groups = {};
  rows.forEach((r) => {
    const label = period === "monthly" ? r.date.slice(0, 7) : r.date;
    (groups[label] = groups[label] || []).push(r.aqi_value);
  });
  const points = Object.keys(groups).sort().map((label) => ({
    label,
    avg_aqi: _round1(groups[label].reduce((a, b) => a + b, 0) / groups[label].length),
  }));
  return { station_id: st.station_id, period, points };
}

// ---------- Public API: admin (every call sends X-Admin-Key) ----------
// key: pass the typed key explicitly, or leave null to use the one stored with setAdminKey().
// Mock rule: an empty key or the key "wrong" gives 401, so the error state can be tested.
async function _mockAdmin(key, work) {
  await _mockDelay();
  const k = key !== null && key !== undefined ? key : _adminKey;
  if (!k || k === "wrong") throw new ApiError(401, "Invalid or missing admin key");
  return work();
}

// Add a station. Fields: station_name (required), location, latitude, longitude, station_type,
// status ("Active" | "Inactive"), installation_date (YYYY-MM-DD). Returns { station_id } (201).
function adminAddStation(fields, key = null) {
  if (!USE_MOCK) return _request("/admin/stations", { method: "POST", body: fields, admin: true, adminKey: key });
  return _mockAdmin(key, () => {
    if (!String(fields.station_name || "").trim()) throw new ApiError(400, "station_name is required");
    return { station_id: 6 };
  });
}

// Update a station: send only the fields to change. Returns { station_id } (200).
function adminUpdateStation(stationId, fields, key = null) {
  if (!USE_MOCK) return _request("/admin/stations/" + _id(stationId), { method: "PUT", body: fields, admin: true, adminKey: key });
  return _mockAdmin(key, () => {
    if (!Object.keys(fields).length) throw new ApiError(400, "Send at least one field to change");
    return { station_id: Number(stationId) };
  });
}

// Assign a pollutant to a station by NAME ("PM2.5", "PM10", "NO2", "SO2"). Returns { station_id, pollutant } (201).
// 409 if it is already assigned.
function adminAssignPollutant(stationId, pollutant, key = null) {
  if (!USE_MOCK) {
    return _request("/admin/station-pollutants", {
      method: "POST",
      body: { station_id: Number(stationId), pollutant },
      admin: true,
      adminKey: key,
    });
  }
  return _mockAdmin(key, () => {
    if (!_POLLUTANTS.includes(pollutant)) throw new ApiError(400, "Unknown pollutant (use PM2.5, PM10, NO2 or SO2)");
    return { station_id: Number(stationId), pollutant };
  });
}
