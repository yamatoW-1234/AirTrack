(function () {
  const keyInput = $("admin-key");
  const stSelect = $("st-select"), stForm = $("station-form");
  const stName = $("st-name"), stLocation = $("st-location"), stLat = $("st-lat"), stLon = $("st-lon");
  const stType = $("st-type"), stStatus = $("st-status"), stInstalled = $("st-installed");
  const stSave = $("st-save"), stClear = $("st-clear");
  const pStation = $("p-station"), pPollutant = $("p-pollutant"), pForm = $("pollutant-form"), pAssign = $("p-assign");

  onReady(init);

  async function init() {
    try {
      const stations = await loadStations();
      fillSelect(stSelect, stations, "station_id", "station_name", { keepFirst: true });
      fillSelect(pStation, stations, "station_id", "station_name", { keepFirst: true });
      
      stSelect.addEventListener("change", () => {
        if (!stSelect.value) return;
        const st = stations.find(s => String(s.station_id) === stSelect.value);
        if (st) { stName.value = st.station_name || ""; stLocation.value = st.location || ""; stLat.value = st.latitude ?? ""; stLon.value = st.longitude ?? ""; stType.value = st.station_type || ""; stStatus.value = st.status || ""; stInstalled.value = st.installation_date || ""; }
      });
      stClear.addEventListener("click", () => { stSelect.value = ""; stName.value = ""; stLocation.value = ""; stLat.value = ""; stLon.value = ""; stType.value = ""; stStatus.value = ""; stInstalled.value = ""; });
      
      stForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!keyInput.value.trim()) { showMessage($("admin-message"), "error", "Admin key is required."); return; }
        setAdminKey(keyInput.value.trim());
        const fields = { station_name: stName.value.trim(), location: stLocation.value.trim() || null, latitude: stLat.value ? Number(stLat.value) : null, longitude: stLon.value ? Number(stLon.value) : null, station_type: stType.value.trim() || null, status: stStatus.value || null, installation_date: stInstalled.value || null };
        stSave.disabled = true; stSave.textContent = "Saving…";
        try {
          if (stSelect.value) { await adminUpdateStation(stSelect.value, fields); showMessage($("admin-message"), "success", "Station updated."); }
          else { await adminAddStation(fields); showMessage($("admin-message"), "success", "Station created."); stSelect.value = ""; stName.value = ""; }
          invalidateStations();
          let stations = await loadStations();
        } catch (err) { showMessage($("admin-message"), "error", describeError(err)); }
        finally { stSave.disabled = false; stSave.textContent = "Save station"; }
      });
      
      pForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!keyInput.value.trim()) { showMessage($("admin-message"), "error", "Admin key is required."); return; }
        setAdminKey(keyInput.value.trim());
        pAssign.disabled = true; pAssign.textContent = "Saving…";
        try { await adminAssignPollutant(pStation.value, pPollutant.value); showMessage($("admin-message"), "success", "Pollutant assigned."); pPollutant.value = ""; }
        catch (err) { showMessage($("admin-message"), "error", describeError(err)); }
        finally { pAssign.disabled = false; pAssign.textContent = "Assign pollutant"; }
      });
    } catch (err) { showMessage($("admin-message"), "error", describeError(err)); }
  }
})();
