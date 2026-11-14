(function () {
  const stationSelect = $("search-station");
  const pollutantSelect = $("search-pollutant");
  const categorySelect = $("search-category");
  const fromInput = $("search-from");
  const toInput = $("search-to");
  const readingsBody = $("readings-body");
  const dailyBody = $("daily-body");
  const readingsPager = $("readings-pager");
  const dailyPager = $("daily-pager");
  
  let stations = [], pollutants = [], categories = [];
  let readingsState = { offset: 0, total: 0 };
  let dailyState = { offset: 0, total: 0 };

  onReady(init);

  async function init() {
    try {
      [stations, pollutants, categories] = await Promise.all([loadStations(), loadPollutants(), loadCategories()]);
      fillSelect(stationSelect, stations, "station_id", "station_name", { keepFirst: true });
      fillSelect(pollutantSelect, pollutants, "pollutant_name", "pollutant_name", { keepFirst: true });
      categorySelect.innerHTML = '<option value="">All categories</option>';
      categories.forEach(c => { const opt = document.createElement("option"); opt.value = c.category_name; opt.textContent = c.category_name; categorySelect.appendChild(opt); });

      $("search-form").addEventListener("submit", (e) => { e.preventDefault(); readingsState.offset = 0; dailyState.offset = 0; search(); });
      $("reset-btn").addEventListener("click", () => { stationSelect.value = ""; pollutantSelect.value = ""; categorySelect.value = ""; fromInput.value = ""; toInput.value = ""; readingsState.offset = 0; dailyState.offset = 0; search(); });
      search();
    } catch (err) { showMessage($("message"), "error", describeError(err)); }
  }

  async function search() {
    const params = { station_id: stationSelect.value || undefined, from: fromInput.value || undefined, to: toInput.value || undefined, limit: PAGE_SIZE };
    params.pollutant = pollutantSelect.value || undefined; params.offset = readingsState.offset;
    try { const res = await searchReadings(params); readingsState.total = res.total; renderReadings(res.rows); renderPager(readingsPager, readingsState); } catch (err) { readingsBody.innerHTML = `<tr><td colspan="5">${describeError(err)}</td></tr>`; }

    params.category = categorySelect.value || undefined; params.offset = dailyState.offset;
    try { const res = await searchAqiRecords(params); dailyState.total = res.total; renderDaily(res.rows); renderPager(dailyPager, dailyState); } catch (err) { dailyBody.innerHTML = `<tr><td colspan="5">${describeError(err)}</td></tr>`; }
  }

  function renderReadings(rows) {
    readingsBody.textContent = "";
    if (!rows.length) { readingsBody.innerHTML = `<tr><td colspan="5">No readings found.</td></tr>`; return; }
    rows.forEach(r => { const tr = document.createElement("tr"); tr.appendChild(makeCell(r.station_name)); tr.appendChild(makeCell(r.pollutant)); tr.appendChild(makeCell(formatDateTime(r.reading_datetime))); tr.appendChild(makeCell(formatNumber(r.concentration), "num")); tr.appendChild(makeCell(r.sub_index !== null ? formatNumber(r.sub_index) : "—", "num")); readingsBody.appendChild(tr); });
  }

  function renderDaily(rows) {
    dailyBody.textContent = "";
    if (!rows.length) { dailyBody.innerHTML = `<tr><td colspan="5">No records found.</td></tr>`; return; }
    rows.forEach(r => { const tr = document.createElement("tr"); tr.appendChild(makeCell(formatDate(r.date))); tr.appendChild(makeCell(r.station_name)); tr.appendChild(makeCell(formatNumber(r.aqi_value), "num")); const cat = categoryByName(categories, r.category); const badge = makeEl("span", "badge", r.category); if (cat) applyAqiColor(badge, cat.color_code); const td = document.createElement("td"); td.appendChild(badge); tr.appendChild(td); tr.appendChild(makeCell(r.dominant_pollutant)); dailyBody.appendChild(tr); });
  }

  function renderPager(el, state) {
    el.textContent = "";
    const prev = makeEl("button", "btn btn-secondary btn-sm", "Previous"); prev.disabled = state.offset === 0; prev.addEventListener("click", () => { state.offset = Math.max(0, state.offset - PAGE_SIZE); search(); });
    const next = makeEl("button", "btn btn-secondary btn-sm", "Next"); next.disabled = state.offset + PAGE_SIZE >= state.total; next.addEventListener("click", () => { state.offset += PAGE_SIZE; search(); });
    const info = makeEl("span", null, `Page ${Math.floor(state.offset / PAGE_SIZE) + 1} · ${state.total} results`);
    el.appendChild(prev); el.appendChild(info); el.appendChild(next);
  }
})();