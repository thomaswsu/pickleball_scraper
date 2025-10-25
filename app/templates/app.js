/**
 * Returns a human-friendly durations summary for a set of slots.
 * Each slot should have a numeric `duration_minutes` property.
 */
function formatDurations(slots) {
  const durations = [...new Set(
    (slots || []).map((slot) => slot.duration_minutes).filter((n) => Number.isFinite(n))
  )].sort((a, b) => a - b);

  if (!durations.length) return "";
  return `Durations: ${durations.join(" / ")} min`;
}

// --- Demo data ---
const demoSlots = [
  { location: "Presidio Wall", court: "Court 1", start: "07:00", end: "08:00", duration_minutes: 60 },
  { location: "Louis Sutter", court: "Lights", start: "19:00", end: "20:30", duration_minutes: 90 }
];

const listEl = document.getElementById("availabilityList");
const refreshBtn = document.getElementById("refreshBtn");

function renderAvailability(slots) {
  listEl.innerHTML = "";
  if (!slots.length) {
    listEl.textContent = "No availability found.";
    return;
  }

  for (const s of slots) {
    const div = document.createElement("div");
    div.innerHTML = `
      <strong>${s.location}</strong> — ${s.court}<br />
      ${s.start} → ${s.end} (${s.duration_minutes} min)
    `;
    div.style.marginBottom = "8px";
    listEl.appendChild(div);
  }

  const summary = document.createElement("div");
  summary.style.color = "#555";
  summary.textContent = formatDurations(slots);
  listEl.appendChild(summary);
}

refreshBtn.addEventListener("click", () => renderAvailability(demoSlots));

// Initial render
renderAvailability(demoSlots);
