(function () {
  const compareDate = $("compare-date");
  const compareResult = $("compare-result");
  const trendStation = $("trend-station");
  const trendPeriod = $("trend-period");
  const trendChartHost = $("trend-chart");
  let stations = [], categories = [];
  let chart = null;

  onReady(init);

  async function init() {
    try {
      [stations, categories] = await Promise.all([loadStations(), loadCategories()]);
      fillSelect(trendStation, stations, "station_id", "station_name");
      $("compare-form").addEventListener("submit", (e) => { e.preventDefault(); loadCompare(); });
      $("trend-form").addEventListener("submit", (e) => { e.preventDefault(); loadTrend(); });
      loadCompare(); if (stations.length) loadTrend();
    } catch (err) { showMessage($("message"), "error", describeError(err)); }
  }

  async function loadCompare() {
    compareResult.textContent = ""; showLoading($("compare-loading"));
    try {
      const data = await getCompare(compareDate.value || undefined); showLoading($("compare-loading"), false);
      const table = document.createElement("table"); table.className = "data-table"; table.innerHTML = `<thead><tr><th>Station</th><th>AQI</th><th>Category</th></tr></thead><tbody></tbody>`;
      const tbody = table.querySelector("tbody");
      data.stations.forEach(s => { const tr = document.createElement("tr"); tr.appendChild(makeCell(s.station_name)); tr.appendChild(makeCell(formatNumber(s.aqi_value), "num")); const cat = categoryByName(categories, s.category); const badge = makeEl("span", "badge", s.category); if (cat) applyAqiColor(badge, cat.color_code); const td = document.createElement("td"); td.appendChild(badge); tr.appendChild(td); tbody.appendChild(tr); });
      compareResult.appendChild(table);
    } catch (err) { showLoading($("compare-loading"), false); compareResult.textContent = describeError(err, "No AQI records for that date."); }
  }

  async function loadTrend() {
    if (!trendStation.value) return; trendChartHost.textContent = ""; showLoading($("trend-loading"));
    try {
      const data = await getAverage(trendStation.value, trendPeriod.value); showLoading($("trend-loading"), false);
      if (typeof Chart === "undefined") { trendChartHost.textContent = "Chart.js not loaded."; return; }
      const canvas = makeEl("canvas"); canvas.id = "trend-canvas"; trendChartHost.appendChild(canvas);
      if (chart) chart.destroy();
      chart = new Chart(canvas, { type: "line", data: { labels: data.points.map(p => p.label), datasets: [{ label: "Average AQI", data: data.points.map(p => p.avg_aqi), borderColor: "#2563eb", backgroundColor: "rgba(37, 99, 235, 0.1)", fill: true, tension: 0.3 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, title: { display: true, text: "AQI" } } } } });
    } catch (err) { showLoading($("trend-loading"), false); trendChartHost.textContent = describeError(err); }
  }
})();