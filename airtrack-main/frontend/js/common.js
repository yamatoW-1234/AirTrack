// Shared helpers for every page. Load after config.js and api.js, before the page script.
// API data is always put into the page with textContent (never innerHTML), so nothing from the server can inject markup.

const $ = (id) => document.getElementById(id);

function onReady(fn) {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
  else fn();
}

// ---------- Loading, empty and error states ----------
function showLoading(el, on = true) {
  if (el) el.hidden = !on;
}

// type: "error" | "empty" | "info" | "success"
function showMessage(el, type, text) {
  if (!el) return;
  el.className = "notice " + type;
  el.setAttribute("role", type === "error" ? "alert" : "status");
  el.textContent = text;
  el.hidden = false;
}

function clearMessage(el) {
  if (!el) return;
  el.hidden = true;
  el.textContent = "";
}

function show(el) { if (el) el.hidden = false; }
function hide(el) { if (el) el.hidden = true; }

// ---------- Small DOM builders ----------
function makeEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = text;
  return el;
}

function makeCell(text, className) {
  return makeEl("td", className, text);
}

// Fills a <select>. keepFirst: true keeps the existing first option (for example "All stations").
function fillSelect(select, items, valueKey, labelKey, { keepFirst = false } = {}) {
  const start = keepFirst ? 1 : 0;
  while (select.options.length > start) select.remove(start);
  items.forEach((it) => select.appendChild(new Option(it[labelKey], it[valueKey])));
}

// ---------- Cached lookups (each is fetched once per page load) ----------
const _commonCache = {};
function _once(key, loader) {
  if (!_commonCache[key]) {
    _commonCache[key] = loader().catch((e) => { delete _commonCache[key]; throw e; });
  }
  return _commonCache[key];
}
function loadStations() { return _once("stations", async () => (await getStations()).stations); }
function loadPollutants() { return _once("pollutants", async () => (await getPollutants()).pollutants); }
function loadCategories() { return _once("categories", async () => (await getCategories()).categories); }

// Remember the chosen station while moving between pages (this browser tab only).
function getSavedStation() {
  try { return sessionStorage.getItem("airtrack.station"); } catch (_) { return null; }
}
function saveStation(id) {
  try { sessionStorage.setItem("airtrack.station", String(id)); } catch (_) { /* storage blocked: ignore */ }
}
// Select the saved station if it still exists, otherwise leave the first one selected.
function selectSavedStation(select, stations) {
  const saved = getSavedStation();
  if (saved && stations.some((s) => String(s.station_id) === saved)) select.value = saved;
}

// ---------- AQI colours ----------
// Picks dark or white text so it stays readable on the category colour (yellow needs dark text).
function textColorFor(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return "#ffffff";
  const n = parseInt(m[1], 16);
  const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return lum > 0.6 ? "#1c2430" : "#ffffff";
}

// Sets the CSS variables used by .aqi-card, .badge, .pcard, .highlight, .swatch ...
function applyAqiColor(el, hex) {
  if (!el) return;
  if (hex) {
    el.style.setProperty("--aqi-color", hex);
    el.style.setProperty("--aqi-text", textColorFor(hex));
  } else {
    el.style.removeProperty("--aqi-color");
    el.style.removeProperty("--aqi-text");
  }
}

function categoryByName(categories, name) {
  return categories.find((c) => c.category_name === name) || null;
}

// The category whose min_aqi..max_aqi range contains the value (sub-indexes use the same ranges).
function categoryForValue(categories, value) {
  if (value === null || value === undefined) return null;
  return categories.find((c) => value >= c.min_aqi && value <= c.max_aqi) || null;
}

// ---------- Formatting ----------
const _MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-10-24" -> "24 Oct 2026". Parsed by hand so the time zone can never shift the day.
function formatDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  if (!m) return iso || "--";
  return Number(m[3]) + " " + _MONTHS[Number(m[2]) - 1] + " " + m[1];
}

// "2026-10-24T23:59:00" -> "24 Oct 2026, 23:59"
function formatDateTime(iso) {
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/.exec(iso || "");
  if (!m) return formatDate(iso);
  return formatDate(m[1]) + ", " + m[2] + ":" + m[3];
}

function formatNumber(value, maxDigits = 2) {
  if (value === null || value === undefined || value === "") return "n/a";
  return Number(value).toLocaleString("en-IN", { maximumFractionDigits: maxDigits });
}

// Today in the browser's local time as YYYY-MM-DD.
function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

// ---------- Every page ----------
function initCommon() {
  const banner = $("mock-banner");
  if (banner && USE_MOCK) {
    banner.textContent = "Showing sample data from the mock folder (USE_MOCK is true in js/config.js). Set it to false to use the Flask backend.";
    banner.hidden = false;
  }
}
onReady(initCommon);
