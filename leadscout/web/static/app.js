// LeadScout dashboard: start background jobs, stream their log, draw the leads map.

function scoreColor(score) {
  const css = getComputedStyle(document.documentElement);
  if (score >= 60) return css.getPropertyValue("--hot").trim();
  if (score >= 40) return css.getPropertyValue("--warn").trim();
  return css.getPropertyValue("--muted").trim();
}

function renderMap(points) {
  if (!window.L || !points.length) return;
  const map = L.map("map", { scrollWheelZoom: false });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const bounds = [];
  for (const p of points) {
    const marker = L.circleMarker([p.lat, p.lon], {
      radius: 7, weight: 2, color: scoreColor(p.score ?? 0), fillOpacity: 0.55,
    }).addTo(map);
    const a = document.createElement("a");
    a.href = `/leads/${p.id}`;
    a.textContent = `${p.name} (${p.score ?? "–"})`;
    marker.bindPopup(a);
    bounds.push([p.lat, p.lon]);
  }
  map.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
}

const jobBox = document.getElementById("job");
const jobButtons = document.querySelectorAll("[data-job]");
let polling = null;

function showJob(job) {
  if (!jobBox || !job || !job.id) return;
  jobBox.hidden = false;
  document.getElementById("job-title").textContent = job.title;
  const status = document.getElementById("job-status");
  status.textContent = job.status;
  status.className = `job-status ${job.status}`;
  const log = document.getElementById("job-log");
  const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
  log.textContent = job.lines.join("\n");
  if (atBottom) log.scrollTop = log.scrollHeight;
  const running = job.status === "running";
  jobButtons.forEach((b) => (b.disabled = running));
  if (!running && polling) {
    clearInterval(polling);
    polling = null;
    setTimeout(() => location.reload(), 900); // refresh the numbers
  }
}

async function poll() {
  try {
    const r = await fetch("/api/job");
    showJob(await r.json());
  } catch (e) { /* server restarting; try again next tick */ }
}

jobButtons.forEach((btn) =>
  btn.addEventListener("click", async () => {
    if (btn.dataset.confirm && !confirm(btn.dataset.confirm)) return;
    jobButtons.forEach((b) => (b.disabled = true));
    const r = await fetch(`/jobs/${btn.dataset.job}`, { method: "POST", headers: { Accept: "application/json" } });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert(err.detail || "Could not start the job");
      jobButtons.forEach((b) => (b.disabled = false));
      return;
    }
    showJob(await r.json());
    if (!polling) polling = setInterval(poll, 1000);
  })
);

if (jobBox && document.querySelector("[data-job]:disabled")) polling = setInterval(poll, 1000);

// Setup wizard: one step at a time when JavaScript is on (all steps show without it).
const wizard = document.querySelector("form.wizard");
if (wizard) {
  const steps = [...wizard.querySelectorAll(".step")];
  const back = wizard.querySelector(".js-back");
  const next = wizard.querySelector(".js-next");
  const finish = wizard.querySelector(".js-finish");
  const progress = wizard.querySelector(".js-progress");
  let i = 0;
  wizard.classList.add("js");
  const show = () => {
    steps.forEach((s, n) => s.classList.toggle("current", n === i));
    back.hidden = i === 0;
    next.hidden = i === steps.length - 1;
    finish.hidden = i !== steps.length - 1;
    progress.textContent = `Step ${i + 1} of ${steps.length}`;
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const stepValid = () => {
    const step = steps[i];
    for (const el of step.querySelectorAll("input[required], textarea[required]")) {
      if (!el.checkValidity()) { el.reportValidity(); return false; }
    }
    const custom = step.querySelector('input[name="service"][value="custom"]');
    if (custom && custom.checked && !step.querySelector(".js-service-custom").value.trim()) {
      alert("Type what you sell in the 'Something else' box.");
      return false;
    }
    const area = step.querySelector("#location");
    if (area && !area.value.trim() && !step.querySelector('input[name="center_lat"]').value) {
      alert("Type an area or click the map to choose where to search.");
      return false;
    }
    if (step.querySelector('input[name="categories"]') && !step.querySelector('input[name="categories"]:checked')
        && !step.querySelector("#extra_categories").value.trim()) {
      alert("Pick at least one kind of business.");
      return false;
    }
    return true;
  };
  next.addEventListener("click", () => {
    if (stepValid()) { i += 1; show(); document.dispatchEvent(new Event("wizard:step")); }
  });
  back.addEventListener("click", () => { i -= 1; show(); });
  show();
}

// "Other" message language: show the text box only when it's chosen.
document.querySelectorAll('select[name="language"]').forEach((sel) => {
  const other = sel.parentElement.querySelector(".js-language-other");
  if (!other) return;
  const sync = () => { other.hidden = sel.value !== "other"; };
  sel.addEventListener("change", sync);
  sync();
});

// Typing in "Something else" selects that option.
document.querySelectorAll(".js-service-custom").forEach((input) => {
  input.addEventListener("focus", () => {
    const radio = input.closest("label").querySelector('input[type="radio"]');
    if (radio) radio.checked = true;
  });
});

// Area picker: find a typed place or click the map; the circle shows the search radius.
function initAreaPicker() {
  const el = document.getElementById("area-map");
  if (!el || !window.L) return;
  const form = el.closest("form");
  const latInput = form.querySelector('input[name="center_lat"]');
  const lonInput = form.querySelector('input[name="center_lon"]');
  const radius = form.querySelector("#radius_km");
  const status = form.querySelector(".js-area-status");
  const area = form.querySelector("#location");
  const map = L.map(el).setView([25, 55], 2);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  let marker = null, circle = null;

  const place = (lat, lon, zoomToFit) => {
    latInput.value = lat.toFixed(6);
    lonInput.value = lon.toFixed(6);
    const km = parseFloat(radius.value) || 5;
    if (!marker) {
      marker = L.marker([lat, lon], { draggable: true, icon: L.divIcon({ className: "pin", html: "📍", iconSize: [28, 28], iconAnchor: [14, 26] }) }).addTo(map);
      marker.on("dragend", () => { const p = marker.getLatLng(); place(p.lat, p.lng, false); });
      circle = L.circle([lat, lon], { radius: km * 1000, weight: 2, fillOpacity: 0.08 }).addTo(map);
    } else {
      marker.setLatLng([lat, lon]);
      circle.setLatLng([lat, lon]);
      circle.setRadius(km * 1000);
    }
    if (zoomToFit) map.fitBounds(circle.getBounds(), { padding: [20, 20] });
    status.textContent = `Centre pinned at ${lat.toFixed(4)}, ${lon.toFixed(4)}. Drag the pin or click elsewhere to move it.`;
  };

  map.on("click", (e) => place(e.latlng.lat, e.latlng.lng, false));
  radius.addEventListener("input", () => {
    if (circle) { circle.setRadius((parseFloat(radius.value) || 5) * 1000); map.fitBounds(circle.getBounds(), { padding: [20, 20] }); }
  });

  const find = async () => {
    const q = area.value.trim();
    if (!q) { area.focus(); return; }
    status.textContent = "Searching…";
    try {
      const r = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      const data = await r.json();
      if (!r.ok) { status.textContent = data.detail || "Place not found."; return; }
      place(data.lat, data.lon, true);
    } catch (e) {
      status.textContent = "Couldn't search the map. Check your internet connection.";
    }
  };
  form.querySelector(".js-find-area").addEventListener("click", find);
  area.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); find(); } });
  // Typing a different area moves the pin there, so the text and the pin never disagree.
  area.addEventListener("change", () => { if (area.value.trim()) find(); });

  if (el.dataset.lat && el.dataset.lon) {
    place(parseFloat(el.dataset.lat), parseFloat(el.dataset.lon), true);
  } else if (area.value.trim()) {
    find();
  }
  // The wizard shows step 2 later; Leaflet needs to re-measure once it's visible.
  document.addEventListener("wizard:step", () => {
    setTimeout(() => { map.invalidateSize(); if (circle) map.fitBounds(circle.getBounds(), { padding: [20, 20] }); }, 50);
  });
}
