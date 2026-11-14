// 24-hour summary: station + date -> hourly line chart per pollutant and an avg/min/max table.
(function () {
  const stationSelect = $("station-select");
  const dateInput = $("date-input");
  const COLORS = { "PM2.5": "#d62728", PM10: "#ff7f0e", NO2: "#1f77b4", SO2: "#2ca02c" };
  const SPARE_COLORS = ["#7f7f7f", "#9467bd", "#8c564b", "#e377c2"];

  let stations = [];
  let pollutants = [];
  let current = null; // the summary currently on screen, so the chart can be redrawn without a new request
  let chart = null;
  let loadToken = 0;

  onReady(init);

  async function init() {
    showLoading($("loading"));
    try {
      [stations, pollutants] = await Promise.all([loadStations(), loadPollutants()]);
      fillSelect(stationSelect, stations, "station_id", "station_name");
      if (!stations.length) {
        showLoading($("loading"), false);
        showMessage($("message"), "empty", "No stations found in the database yet.");
        return;
      }
      selectSavedStation(stationSelect, stations);

      stationSelect.addEventListener("change", () => { saveStation(stationSelect.value); loadSummary(); });
      $("summary-form").addEventListener("submit", (e) => { e.preventDefault(); loadSummary(); });
      document.querySelectorAll('input[name="metric"]').forEach((r) => r.addEventListener("change", renderChart));

      loadSummary();
    } catch (err) {
      showLoading($("loading"), false);
      showMessage($("message"), "error", describeError(err));
    }
  }

  async function loadSummary() {
    const token = ++loadToken;
    const stationId = stationSelect.value;
    const date = dateInput.value;
    hide($("content"));
    clearMessage($("message"));
    showLoading($("loading"));

    try {
      let data = await getSummary(stationId, date || undefined);
      let note = null;

      // Chosen day has no readings: fall back to the latest day that has some.
      if (date && data.pollutants.length === 0) {
        const latest = await getSummary(stationId);
        if (latest.pollutants.length > 0) {
          note = "No readings for " + formatDate(date) + ". Showing the latest available day (" + formatDate(latest.date) + ").";
          data = latest;
          dateInput.value = latest.date;
        }
      }
      if (token !== loadToken) return;
      showLoading($("loading"), false);

      if (data.pollutants.length === 0) {
        showMessage($("message"), "empty", date
          ? "No readings for this station on " + formatDate(date) + "."
          : "No readings for this station yet.");
        return;
      }

      current = data;
      const station = stations.find((s) => String(s.station_id) === String(stationId));
      $("summary-title").textContent = (station ? station.station_name : "Station " + stationId) + " · " + formatDate(data.date);
      show($("content"));
      renderChart();
      renderTable();
      if (note) showMessage($("message"), "info", note);
    } catch (err) {
      if (token !== loadToken) return;
      showLoading($("loading"), false);
      showMessage($("message"), "error", describeError(err));
    }
  }

  function unitOf(name) {
    return (pollutants.find((p) => p.pollutant_name === name) || {}).unit || "";
  }

  function renderChart() {
    if (!current) return;
    if (typeof Chart === "undefined") {
      showMessage($("message"), "error", "The chart library (Chart.js) could not be loaded. Check your internet connection and reload.");
      return;
    }
    const metric = document.querySelector('input[name="metric"]:checked').value; // "concentration" | "sub_index"
    const labels = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0") + ":00");

    const datasets = current.pollutants.map((p, i) => {
      const byHour = {};
      p.hourly.forEach((h) => { byHour[h.hour] = h[metric]; });
      const color = COLORS[p.pollutant] || SPARE_COLORS[i % SPARE_COLORS.length];
      return {
        label: p.pollutant,
        // null leaves a gap for hours that have no reading
        data: labels.map((_, h) => (byHour[h] === undefined ? null : byHour[h])),
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        pointRadius: 2,
        tension: 0.25,
        spanGaps: false,
      };
    });

    const firstUnit = unitOf(current.pollutants[0].pollutant);
    if (chart) chart.destroy();
    chart = new Chart($("hourly-chart"), {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                if (ctx.parsed.y === null) return null;
                const unit = metric === "concentration" ? " " + unitOf(ctx.dataset.label) : "";
                return ctx.dataset.label + ": " + ctx.parsed.y + unit;
              },
            },
          },
        },
        scales: {
          x: { title: { display: true, text: "Hour of day" } },
          y: {
            beginAtZero: true,
            title: { display: true, text: metric === "sub_index" ? "Sub-index (0–500)" : "Concentration (" + firstUnit + ")" },
          },
        },
      },
    });
  }

  function renderTable() {
    const body = $("summary-body");
    body.textContent = "";
    current.pollutants.forEach((p) => {
      const tr = document.createElement("tr");
      const unit = unitOf(p.pollutant);
      tr.appendChild(makeCell(unit ? p.pollutant + " (" + unit + ")" : p.pollutant));
      tr.appendChild(makeCell(formatNumber(p.avg), "num"));
      tr.appendChild(makeCell(formatNumber(p.min), "num"));
      tr.appendChild(makeCell(formatNumber(p.max), "num"));
      tr.appendChild(makeCell(p.hourly.length, "num"));
      body.appendChild(tr);
    });
  }
})();
