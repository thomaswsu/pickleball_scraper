const els = {
  availabilityList: document.getElementById("availability-list"),
  availabilityEmpty: document.getElementById("availability-empty"),
  lastSync: document.getElementById("last-sync"),
  refreshBtn: document.getElementById("refresh-button"),
  filterDate: document.getElementById("filter-date"),
  filterTimeFrom: document.getElementById("filter-time-from"),
  filterTimeTo: document.getElementById("filter-time-to"),
  filterCourt: document.getElementById("filter-court"),
  filterReset: document.getElementById("filter-reset"),
  watchForm: document.getElementById("watch-form"),
  watchMessage: document.getElementById("watch-form-message"),
  watchLocation: document.getElementById("watch-location"),
  watchLabel: document.getElementById("watch-label"),
  watchCourt: document.getElementById("watch-court"),
  watchDate: document.getElementById("watch-date"),
  watchTimeFrom: document.getElementById("watch-time-from"),
  watchTimeTo: document.getElementById("watch-time-to"),
  watchContact: document.getElementById("watch-contact"),
  watchNotes: document.getElementById("watch-notes"),
  watchersList: document.getElementById("watchers-list"),
  watchersRefresh: document.getElementById("watchers-refresh"),
  alertsList: document.getElementById("alerts-list"),
  alertsRefresh: document.getElementById("alerts-refresh"),
};

const state = {
  filters: {
    date: "",
    timeFrom: "",
    timeTo: "",
    court: "",
  },
  locations: [],
  watchers: [],
  alerts: [],
};

const DATE_FORMAT = {
  weekday: "short",
  month: "short",
  day: "numeric",
};

const TIME_FORMAT = {
  hour: "numeric",
  minute: "2-digit",
};

function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-cache",
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

function setLastSync(value) {
  if (!els.lastSync) return;
  const timestamp = value ? parseDate(value) : new Date();
  const formatted = timestamp
    ? timestamp.toLocaleString([], {
        hour: "numeric",
        minute: "2-digit",
        month: "short",
        day: "numeric",
      })
    : "—";
  els.lastSync.textContent = `Last sync ${formatted}`;
}

function formatSlot(slot) {
  const start = parseDate(slot.slot_time_local);
  const duration = Number.isFinite(slot.duration_minutes)
    ? slot.duration_minutes
    : null;
  const end = start && duration ? new Date(start.getTime() + duration * 60000) : null;
  const startLabel = start
    ? `${start.toLocaleDateString([], DATE_FORMAT)} · ${start.toLocaleTimeString([], TIME_FORMAT)}`
    : "Unknown start";
  const endLabel = end ? end.toLocaleTimeString([], TIME_FORMAT) : "";
  return {
    start,
    end,
    startLabel,
    endLabel,
    duration,
  };
}

function formatCourtLabel(slot) {
  const names = Array.isArray(slot.court_names) && slot.court_names.length
    ? slot.court_names
    : [slot.court_name || slot.court_id || "Court"];
  if (names.length <= 2) {
    return names.join(" • ");
  }
  const visible = names.slice(0, 2).join(" • ");
  return `${visible} +${names.length - 2} more`;
}

function toggleEmptyState(showEmpty) {
  if (!els.availabilityEmpty) return;
  if (showEmpty) {
    els.availabilityEmpty.classList.remove("hidden");
  } else {
    els.availabilityEmpty.classList.add("hidden");
  }
}

function renderAvailability() {
  if (!els.availabilityList) return;
  els.availabilityList.innerHTML = "";
  const active = state.locations.filter((loc) => (loc.slots || []).length > 0);

  toggleEmptyState(active.length === 0);

  active.forEach((loc) => {
    const card = document.createElement("article");
    card.className = "location-card";
    card.innerHTML = `
      <div>
        <h3>${loc.name}</h3>
        <p class="muted">${loc.address || ""}</p>
      </div>
    `;

    const list = document.createElement("ul");
    list.className = "slot-list";

    loc.slots.forEach((slot) => {
      const meta = formatSlot(slot);
      const row = document.createElement("li");
      row.className = "slot-row";
      row.innerHTML = `
        <div class="slot-meta">
          <strong>${formatCourtLabel(slot)}</strong>
          <span>${meta.startLabel}${meta.endLabel ? ` → ${meta.endLabel}` : ""}</span>
        </div>
        <div class="slot-meta">
          <span>Duration</span>
          <span class="chip">${meta.duration ?? "—"} min</span>
        </div>
      `;
      list.appendChild(row);
    });

    card.appendChild(list);
    els.availabilityList.appendChild(card);
  });
}

function populateLocationOptions() {
  if (!els.watchLocation) return;
  const current = els.watchLocation.value;
  const sorted = [...state.locations].sort((a, b) =>
    (a.name || a.id || "").localeCompare(b.name || b.id || "", undefined, {
      sensitivity: "base",
    }),
  );
  els.watchLocation.innerHTML =
    '<option value="">Choose a location</option>' +
    sorted
      .map(
        (loc) =>
          `<option value="${loc.id}">${loc.name || loc.id}</option>`,
      )
      .join("");
  if (current && state.locations.some((loc) => loc.id === current)) {
    els.watchLocation.value = current;
  }
}

function renderWatchers() {
  if (!els.watchersList) return;
  els.watchersList.innerHTML = "";
  if (!state.watchers.length) {
    els.watchersList.classList.add("muted");
    els.watchersList.textContent = "No alerts yet.";
    return;
  }
  state.watchers.forEach((watch) => {
    const card = document.createElement("div");
    card.className = "watch-card rounded-xl";
    card.dataset.id = watch.id;
    card.innerHTML = `
      <div>
        <strong>${watch.label || "Untitled alert"}</strong>
        <p class="muted">${watch.location_name || watch.location_id}</p>
      </div>
      <p class="status ${watch.active ? "active" : "paused"}">
        ${watch.active ? "ACTIVE" : "PAUSED"}
      </p>
      <p class="muted">${[
        watch.court_query ? `Court includes “${watch.court_query}”` : null,
        watch.target_date ? `Date ${watch.target_date}` : null,
        watch.time_from || watch.time_to
          ? `${watch.time_from || "??"} – ${watch.time_to || "??"}`
          : null,
      ]
        .filter(Boolean)
        .join(" · ") || "Any court / time"}
      </p>
      <div class="watch-card-actions">
        <button
          type="button"
          class="btn ghost"
          data-action="toggle"
          data-id="${watch.id}"
        >
          ${watch.active ? "Pause" : "Resume"}
        </button>
        <button
          type="button"
          class="btn ghost"
          data-action="delete"
          data-id="${watch.id}"
        >
          Delete
        </button>
      </div>
    `;
    els.watchersList.appendChild(card);
  });
  els.watchersList.classList.remove("muted");
}

function renderAlerts() {
  if (!els.alertsList) return;
  els.alertsList.innerHTML = "";
  if (!state.alerts.length) {
    els.alertsList.classList.add("muted");
    els.alertsList.textContent = "No alerts fired yet.";
    return;
  }
  state.alerts.forEach((alert) => {
    const created = parseDate(alert.created_at);
    const row = document.createElement("div");
    row.className = "alerts-row";
    row.innerHTML = `
      <div>
        <strong>${alert.watch_label || "Alert"}</strong>
        <span class="muted">${alert.court_name || alert.court_id}</span>
      </div>
      <span class="pill">
        ${created ? created.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : ""}
      </span>
    `;
    els.alertsList.appendChild(row);
  });
  els.alertsList.classList.remove("muted");
}

async function loadAvailability() {
  const params = new URLSearchParams();
  if (state.filters.date) params.set("date", state.filters.date);
  if (state.filters.timeFrom) params.set("time_from", state.filters.timeFrom);
  if (state.filters.timeTo) params.set("time_to", state.filters.timeTo);
  if (state.filters.court) params.set("court", state.filters.court);
  try {
    const query = params.toString();
    const data = await fetchJSON(
      query ? `/api/locations?${query}` : "/api/locations",
    );
    state.locations = data.locations || [];
    setLastSync(data.last_updated);
    populateLocationOptions();
    renderAvailability();
  } catch (err) {
    console.error(err);
    toggleEmptyState(true);
    if (els.availabilityList) {
      els.availabilityList.innerHTML =
        '<p class="muted">Failed to load availability.</p>';
    }
  }
}

async function loadWatchers() {
  try {
    const data = await fetchJSON("/api/watchers");
    state.watchers = data || [];
    renderWatchers();
  } catch (err) {
    console.error(err);
  }
}

async function loadAlerts() {
  try {
    const data = await fetchJSON("/api/alerts?limit=20");
    state.alerts = data || [];
    renderAlerts();
  } catch (err) {
    console.error(err);
  }
}

function bindFilters() {
  let courtInputTimer = null;
  if (els.filterDate) {
    els.filterDate.addEventListener("change", () => {
      state.filters.date = els.filterDate.value;
      loadAvailability();
    });
  }
  if (els.filterTimeFrom) {
    els.filterTimeFrom.addEventListener("change", () => {
      state.filters.timeFrom = els.filterTimeFrom.value;
      loadAvailability();
    });
  }
  if (els.filterTimeTo) {
    els.filterTimeTo.addEventListener("change", () => {
      state.filters.timeTo = els.filterTimeTo.value;
      loadAvailability();
    });
  }
  if (els.filterCourt) {
    els.filterCourt.addEventListener("input", () => {
      window.clearTimeout(courtInputTimer);
      courtInputTimer = window.setTimeout(() => {
        state.filters.court = els.filterCourt.value.trim();
        loadAvailability();
      }, 250);
    });
  }
  if (els.filterReset) {
    els.filterReset.addEventListener("click", () => {
      state.filters = { date: "", timeFrom: "", timeTo: "", court: "" };
      if (els.filterDate) els.filterDate.value = "";
      if (els.filterTimeFrom) els.filterTimeFrom.value = "";
      if (els.filterTimeTo) els.filterTimeTo.value = "";
      if (els.filterCourt) els.filterCourt.value = "";
      loadAvailability();
    });
  }
}

function setWatchMessage(text, variant = "success") {
  if (!els.watchMessage) return;
  els.watchMessage.textContent = text;
  els.watchMessage.style.color =
    variant === "error" ? "var(--danger)" : "var(--accent)";
}

function collectWatchPayload() {
  return {
    location_id: els.watchLocation?.value || "",
    label: els.watchLabel?.value?.trim() || null,
    court_query: els.watchCourt?.value?.trim() || null,
    target_date: els.watchDate?.value || null,
    time_from: els.watchTimeFrom?.value || null,
    time_to: els.watchTimeTo?.value || null,
    contact: els.watchContact?.value?.trim() || null,
    notes: els.watchNotes?.value?.trim() || null,
  };
}

function resetWatchForm() {
  if (!els.watchForm) return;
  els.watchForm.reset();
}

function bindWatchForm() {
  if (!els.watchForm) return;
  els.watchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!els.watchLocation?.value) {
      setWatchMessage("Pick a location before saving.", "error");
      return;
    }
    try {
      setWatchMessage("Saving…");
      await fetchJSON("/api/watchers", {
        method: "POST",
        body: JSON.stringify(collectWatchPayload()),
      });
      setWatchMessage("Alert saved!");
      resetWatchForm();
      loadWatchers();
    } catch (err) {
      console.error(err);
      setWatchMessage("Failed to save alert.", "error");
    }
  });
}

function bindWatchersList() {
  if (!els.watchersList) return;
  els.watchersList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (!id) return;
    try {
      if (action === "toggle") {
        await fetchJSON(`/api/watchers/${id}/toggle`, { method: "POST" });
      } else if (action === "delete") {
        await fetchJSON(`/api/watchers/${id}`, { method: "DELETE" });
      }
      await loadWatchers();
    } catch (err) {
      console.error(err);
    }
  });
}

function bindSidebarButtons() {
  els.watchersRefresh?.addEventListener("click", loadWatchers);
  els.alertsRefresh?.addEventListener("click", loadAlerts);
}

function boot() {
  bindFilters();
  bindWatchForm();
  bindWatchersList();
  bindSidebarButtons();
  els.refreshBtn?.addEventListener("click", () => loadAvailability());
  loadAvailability();
  loadWatchers();
  loadAlerts();
}

boot();
