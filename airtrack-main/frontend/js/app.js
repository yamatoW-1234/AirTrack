/* =========================================================
   AirTrack — Shared Application Module
   ========================================================= */
(function () {
  "use strict";

  const API_BASE = ""; 
  const PAGE_SIZE = 20;

  const ADMIN_KEY_STORAGE = "airtrack_admin_key";
  window.AirTrack = window.AirTrack || {};
  window.AirTrack.getAdminKey = () => sessionStorage.getItem(ADMIN_KEY_STORAGE) || "";
  window.AirTrack.setAdminKey = (v) => {
    if (v) sessionStorage.setItem(ADMIN_KEY_STORAGE, v);
    else sessionStorage.removeItem(ADMIN_KEY_STORAGE);
  };

  const AQI_CATEGORIES = [
    { key: "Good",         label: "Good",                    min: 0,   max: 50,  css: "aqi-good" },
    { key: "Satisfactory", label: "Satisfactory",            min: 51,  max: 100, css: "aqi-satisfactory" },
    { key: "Moderate",     label: "Moderately Polluted",     min: 101, max: 200, css: "aqi-moderate" },
    { key: "Poor",         label: "Poor",                    min: 201, max: 300, css: "aqi-poor" },
    { key: "Very Poor",    label: "Very Poor",               min: 301, max: 400, css: "aqi-verypoor" },
    { key: "Severe",       label: "Severe",                  min: 401, max: 500, css: "aqi-severe" },
  ];

  function categoryFor(aqi) {
    const n = Number(aqi);
    if (!Number.isFinite(n)) return null;
    return AQI_CATEGORIES.find(c => n >= c.min && n <= c.max) || null;
  }
  window.AirTrack.categoryFor = categoryFor;
  window.AirTrack.AQI_CATEGORIES = AQI_CATEGORIES;

  function aqiBadge(aqi) {
    const c = categoryFor(aqi);
    if (!c) return `<span class="badge">—</span>`;
    return `<span class="badge ${c.css}"><span class="badge-dot"></span>${c.label} (${aqi})</span>`;
  }
  window.AirTrack.aqiBadge = aqiBadge;

  async function api(path, { method = "GET", body, admin = false, query } = {}) {
    const url = new URL(API_BASE + path, window.location.origin);
    if (query) Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
    const headers = { "Accept": "application/json" };
    if (body && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    if (admin) {
      const key = window.AirTrack.getAdminKey();
      if (!key) throw new Error("Admin key is required for this action.");
      headers["X-Admin-Key"] = key;
    }
    const res = await fetch(url.toString(), { method, headers, body, credentials: "same-origin" });
    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await res.json().catch(() => ({})) : await res.text();
    if (!res.ok) {
      const msg = (data && (data.error || data.message)) || `Request failed (${res.status})`;
      throw new Error(msg);
    }
    return data;
  }
  window.AirTrack.api = api;

  function ensureToastHost() {
    let host = document.querySelector(".toast-host");
    if (!host) {
      host = document.createElement("div");
      host.className = "toast-host";
      document.body.appendChild(host);
    }
    return host;
  }
  function toast(message, type = "info", duration = 3500) {
    const host = ensureToastHost();
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateX(12px)";
      el.style.transition = "all .2s";
      setTimeout(() => el.remove(), 220);
    }, duration);
  }
  window.AirTrack.toast = toast;

  function setLoading(el, loading, loadingText = "Loading…") {
    if (!el) return;
    if (loading) {
      el.dataset.prevHtml = el.innerHTML;
      el.innerHTML = `<div class="loading"><span class="spinner"></span>${loadingText}</div>`;
    } else if (el.dataset.prevHtml) {
      el.innerHTML = el.dataset.prevHtml;
      delete el.dataset.prevHtml;
    }
  }
  window.AirTrack.setLoading = setLoading;

  function setEmpty(el, text = "No data available") {
    if (!el) return;
    el.innerHTML = `<div class="empty">${text}</div>`;
  }
  window.AirTrack.setEmpty = setEmpty;

  function todayISO() {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  }
  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }
  function formatDateTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  window.AirTrack.todayISO = todayISO;
  window.AirTrack.formatDate = formatDate;
  window.AirTrack.formatDateTime = formatDateTime;

  function fmtNum(n, digits = 1) {
    const v = Number(n);
    if (!Number.isFinite(v)) return "—";
    return v.toLocaleString(undefined, { maximumFractionDigits: digits });
  }
  window.AirTrack.fmtNum = fmtNum;

  function markActiveNav() {
    const path = window.location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav a").forEach(a => {
      const href = a.getAttribute("href") || "";
      const target = href.split("/").pop();
      a.classList.toggle("active", target === path || (path === "" && target === "index.html"));
    });
  }

  function svgLine(points, width, height, color = "#2563eb") {
    if (!points || points.length === 0) return "";
    const xs = points.map(p => p.x), ys = points.map(p => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const padX = 28, padY = 20;
    const sx = v => padX + (maxX === minX ? 0 : ((v - minX) / (maxX - minX)) * (width - padX * 2));
    const sy = v => height - padY - (maxY === minY ? 0 : ((v - minY) / (maxY - minY)) * (height - padY * 2));
    const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
    const area = d + ` L${sx(points[points.length - 1].x).toFixed(1)},${(height - padY).toFixed(1)} L${sx(points[0].x).toFixed(1)},${(height - padY).toFixed(1)} Z`;
    return `
      <defs>
        <linearGradient id="grad-${color.replace('#','')}" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.25"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path d="${area}" fill="url(#grad-${color.replace('#','')})" />
      <path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      ${points.map(p => `<circle cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="2.5" fill="${color}"/>`).join("")}
    `;
  }
  function svgBars(values, width, height, color = "#2563eb") {
    if (!values || values.length === 0) return "";
    const max = Math.max(...values.map(v => v.y), 1);
    const padX = 28, padY = 20;
    const bw = Math.max(4, (width - padX * 2) / values.length - 4);
    return values.map((v, i) => {
      const x = padX + i * ((width - padX * 2) / values.length) + 2;
      const h = (v.y / max) * (height - padY * 2);
      const y = height - padY - h;
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${color}" rx="3"/>`;
    }).join("");
  }
  window.AirTrack.svgLine = svgLine;
  window.AirTrack.svgBars = svgBars;

  document.addEventListener("DOMContentLoaded", () => {
    markActiveNav();
    window.addEventListener("unhandledrejection", (e) => {
      console.error("Unhandled rejection:", e.reason);
      toast(e.reason?.message || "Something went wrong.", "error");
    });
  });

  window.AirTrack.PAGE_SIZE = PAGE_SIZE;
})();