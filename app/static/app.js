/* Minimal client that renders /api/locations and /api/alerts, and won't 404. */

/** Utility: unique, sorted durations summary */
function formatDurations(slots) {
  const durations = [...new Set((slots || [])
    .map((s) => s.duration_minutes)
    .filter((n) => Number.isFinite(n)))]
    .sort((a, b) => a - b);
  return durations.length ? `Durations: ${durations.join(" / ")} min` : "";
}

const els = {
  lastSync: document.getElementById("lastSync"),
  locationCount: document.getElementById("locationCount"),
  durationSummary: document.getElementById("durationSummary"),
  availabilityList: document.getElementById("availabilityList"),
  alertsList: document.getElementById("alertsList"),
  refreshBtn: document.getElementById("refreshBtn"),
  alertsRefresh: document.getElementById("alertsRefresh"),
  timeFrom: document.getElementById("timeFromFilter"),
  timeTo: document.getElementById("timeToFilter"),
  clearFilters: document.getElementById("clearFiltersBtn"),
};

function setSyncNow() {
  els.lastSync.textContent = `Last sync: ${new Date().toLocaleString()}`;
}

function applyTimeFilters(slots) {
  const from = els.timeFrom?.value || "";
  const to = els.timeTo?.value || "";
  let filtered = [...(slots || [])];
  if (from) filtered = filtered.filter((s) => (s.start || "") >= from);
  if (to) filtered = filtered.filter((s) => (s.end || "") <= to);
  return filtered;
}

function renderAvailability(slots) {
  els.availabilityList.innerHTML = "";
  if (!slots?.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No availability found.";
    els.availabilityList.appendChild(empty);
    els.locationCount.textContent = "0 locations";
    els.durationSummary.textContent = "";
    return;
  }

  const locations = [...new Set(slots.map((s) => s.location || "Unknown"))].sort();
  els.locationCount.textContent = `${locations.length} locations`;
  els.durationSummary.textContent = formatDurations(slots);

  for (const s of slots) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div>
        <strong>${s.location || "Unknown"}</strong> — ${s.court || "—"}
        <div class="muted">${s.start || "?"} → ${s.end || "?"}</div>
      </div>
      <span class="pill">${Number.isFinite(s.duration_minutes) ? s.duration_minutes : "—"} min</span>
    `;
    els.availabilityList.appendChild(row);
  }
}

function renderAlerts(items) {
  els.alertsList.innerHTML = "";
  if (!items?.length) {
    els.alertsList.textContent = "No alerts yet.";
    return;
  }
  for (const a of items) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div>
        <strong>${a.label || "Alert"}</strong>
        <div class="muted">${a.location || ""}</div>
      </div>
      <span class="pill">${a.created_at ? new Date(a.created_at).toLocaleString() : ""}</span>
    `;
    els.alertsList.appendChild(row);
  }
}

async function fetchJSON(url) {
  const res = await fetch(url, { headers: { "cache-control": "no-cache" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

async function loadAll() {
  setSyncNow();

  // Your backend (per your logs) exposes:
  //   GET /api/locations  -> 200 OK
  //   GET /api/alerts?limit=15 -> 200 OK
  // We defensively handle shapes.
  try {
    const locations = await fetchJSON("/api/locations");
    // Expect either an array of slots or an object with a key holding slots.
    // Try common shapes:
    const slots =
      Array.isArray(locations)
        ? locations
        : locations?.slots ??
          locations?.data ??
          locations?.items ??
          [];
    renderAvailability(applyTimeFilters(slots));
  } catch (e) {
    console.error(e);
    renderAvailability([]);
  }

  try {
    const alerts = await fetchJSON("/api/alerts?limit=15");
    const list =
      Array.isArray(alerts)
        ? alerts
        : alerts?.alerts ?? alerts?.data ?? alerts?.items ?? [];
    renderAlerts(list);
  } catch (e) {
    console.error(e);
    renderAlerts([]);
  }
}

function boot() {
  loadAll();

  els.refreshBtn?.addEventListener("click", () => loadAll());
  els.alertsRefresh?.addEventListener("click", () => loadAll());
  els.clearFilters?.addEventListener("click", () => {
    if (els.timeFrom) els.timeFrom.value = "";
    if (els.timeTo) els.timeTo.value = "";
    loadAll();
  });
}

boot();
