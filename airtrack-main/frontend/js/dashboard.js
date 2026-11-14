// Dashboard: pick a station -> latest daily AQI card + latest reading of every pollutant.
(function () {
  const stationSelect = $("station-select");
  let categories = [];
  let pollutants = [];
  let loadToken = 0;

  onReady(init);

  async function init() {
    showLoading($("loading"));
    try {
      const [stations, cats, pols] = await Promise.all([loadStations(), loadCategories(), loadPollutants()]);
      categories = cats;
      pollutants = pols;
      renderLegend();
      fillSelect(stationSelect, stations, "station_id", "station_name");
      if (!stations.length) {
        showLoading($("loading"), false);
        showMessage($("message"), "empty", "No stations found in the database yet.");
        return;
      }
      selectSavedStation(stationSelect, stations);
      stationSelect.addEventListener("change", () => {
        saveStation(stationSelect.value);
        loadDashboard();
      });
      loadDashboard();
    } catch (err) {
      showLoading($("loading"), false);
      showMessage($("message"), "error", describeError(err));
    }
  }

  async function loadDashboard() {
    const token = ++loadToken;
    const stationId = stationSelect.value;
    hide($("content"));
    clearMessage($("message"));
    showLoading($("loading"));

    const [aqiRes, latestRes] = await Promise.allSettled([getAqi(stationId), getLatest(stationId)]);
    if (token !== loadToken) return;
    showLoading($("loading"), false);

    const hardFailure = [aqiRes, latestRes].find(
      (r) => r.status === "rejected" && !(r.reason instanceof ApiError && r.reason.isNotFound)
    );
    if (hardFailure) {
      showMessage($("message"), "error", describeError(hardFailure.reason));
      return;
    }

    const aqi = aqiRes.status === "fulfilled" ? aqiRes.value : null;
    const latest = latestRes.status === "fulfilled" ? latestRes.value : null;
    const hasReadings = latest && latest.readings.length > 0;

    if (!aqi && !hasReadings) {
      showMessage($("message"), "empty", "No AQI or readings are available for this station yet.");
      return;
    }

    show($("content"));
    renderAqi(aqi);
    renderReadings(latest, aqi ? aqi.dominant_pollutant : null);

    if (!aqi) {
      showMessage($("message"), "empty", "No AQI has been calculated for this station yet. Showing the latest readings only.");
    } else if (aqi.date < todayISO()) {
      showMessage($("message"), "info", "No AQI for today yet. Showing the latest available daily AQI, from " + formatDate(aqi.date) + ".");
    }
  }

  function renderAqi(aqi) {
    const card = $("aqi-card");
    if (!aqi) { hide(card); return; }
    show(card);
    $("aqi-number").textContent = aqi.aqi_value;
    $("aqi-category").textContent = aqi.category.name;
    $("aqi-date").textContent = formatDate(aqi.date);
    $("aqi-hours").textContent = aqi.hours_of_data !== null && aqi.hours_of_data !== undefined
      ? "· " + aqi.hours_of_data + " of 24 hours of data"
      : "";
    $("aqi-health").textContent = aqi.category.health_impact;
    $("aqi-dominant").textContent = aqi.dominant_pollutant;
    $("aqi-updated").textContent = formatDateTime(aqi.last_updated);
    applyAqiColor(card, aqi.category.color_code);
  }

  function renderReadings(latest, dominant) {
    const wrap = $("pollutant-cards");
    wrap.textContent = "";
    if (!latest || !latest.readings.length) {
      $("readings-time").textContent = "No readings for this station yet.";
      return;
    }
    const newest = latest.readings.map((r) => r.reading_datetime).sort().pop();
    $("readings-time").textContent = "Newest reading: " + formatDateTime(newest);
    latest.readings.forEach((r) => {
      const unit = (pollutants.find((p) => p.pollutant_name === r.pollutant) || {}).unit || "";
      const cat = categoryForValue(categories, r.sub_index);
      const card = makeEl("div", "pcard" + (r.pollutant === dominant ? " dominant" : ""));
      applyAqiColor(card, cat ? cat.color_code : null);
      const name = makeEl("div", "pname", r.pollutant);
      if (r.pollutant === dominant) name.appendChild(makeEl("span", "tag", "Dominant"));
      card.appendChild(name);
      const value = makeEl("div", "pvalue", formatNumber(r.concentration));
      value.appendChild(makeEl("span", "punit", " " + unit));
      card.appendChild(value);
      const sub = r.sub_index === null || r.sub_index === undefined
        ? "Sub-index: not calculated"
        : "Sub-index: " + r.sub_index + (cat ? " · " + cat.category_name : "");
      card.appendChild(makeEl("div", "psub", sub));
      card.appendChild(makeEl("div", "ptime", formatDateTime(r.reading_datetime)));
      wrap.appendChild(card);
    });
  }

  function renderLegend() {
    const list = $("legend");
    list.textContent = "";
    categories.forEach((c) => {
      const li = makeEl("li");
      const swatch = makeEl("span", "swatch");
      applyAqiColor(swatch, c.color_code);
      li.appendChild(swatch);
      li.appendChild(makeEl("span", null, c.category_name + " (" + c.min_aqi + "–" + c.max_aqi + ")"));
      list.appendChild(li);
    });
  }
})();