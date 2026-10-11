// LeadScout dashboard: start background jobs, stream their log, draw the leads map.

function scoreColor(score) {
  const css = getComputedStyle(document.documentElement);
  if (score >= 60) return css.getPropertyValue("--hot").trim();
  if (score >= 40) return css.getPropertyValue("--warn").trim();
  return css.getPropertyValue("--muted").trim();
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

// Map tiles: OpenStreetMap first; if its tiles fail to load, switch to CARTO (also free, built on OSM data).
const TILE_LAYERS = [
  ["https://tile.openstreetmap.org/{z}/{x}/{y}.png",
   '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'],
  ["https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
   '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'],
];

function addBaseLayer(map) {
  let index = 0, failures = 0, loaded = false, layer = null;
  const note = document.createElement("div");
  note.className = "map-note";
  note.hidden = true;
  map.getContainer().appendChild(note);
  const use = (i) => {
    if (layer) map.removeLayer(layer);
    index = i; failures = 0; loaded = false;
    layer = L.tileLayer(TILE_LAYERS[i][0], { maxZoom: 19, subdomains: "abcd", attribution: TILE_LAYERS[i][1] });
    layer.on("tileload", () => { loaded = true; note.hidden = true; });
    layer.on("tileerror", () => {
      failures += 1;
      if (!loaded && failures >= 3) {
        if (index + 1 < TILE_LAYERS.length) use(index + 1);
        else { note.textContent = "Map pictures can't load (check your internet). You can still type a place."; note.hidden = false; }
      }
    });
    layer.addTo(map);
  };
  use(0);
}

function renderMap(points) {
  if (!window.L || !points.length) return;
  const map = L.map("map", { scrollWheelZoom: false });
  addBaseLayer(map);
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

// Place search. Suggestions come straight from Photon (free, OSM-based) in the browser; if that fails,
// LeadScout's own server looks the place up (OpenStreetMap Nominatim, then Photon).
async function searchPlaces(q, limit = 6) {
  try {
    const r = await fetch(`https://photon.komoot.io/api/?q=${encodeURIComponent(q)}&limit=${limit}`);
    if (r.ok) {
      const data = await r.json();
      return (data.features || []).map((f) => {
        const p = f.properties || {};
        const title = p.name || p.street || p.city || p.county || p.state || q;
        const detail = [p.district, p.city !== title ? p.city : null, p.state, p.country]
          .filter((x, i, arr) => x && arr.indexOf(x) === i).join(", ");
        return { lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0], title, detail };
      });
    }
  } catch (e) { /* fall through to the server */ }
  const r = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Place not found.");
  return [{ lat: data.lat, lon: data.lon, title: q, detail: "" }];
}

// Area picker: type to get suggestions, drag the map to look around, click (or drag the pin) to set the centre.
function initAreaPicker() {
  const el = document.getElementById("area-map");
  if (!el || !window.L) return;
  const form = el.closest("form");
  const latInput = form.querySelector('input[name="center_lat"]');
  const lonInput = form.querySelector('input[name="center_lon"]');
  const radius = form.querySelector("#radius_km");
  const status = form.querySelector(".js-area-status");
  const area = form.querySelector("#location");
  const list = form.querySelector("#area-suggestions");
  const map = L.map(el, { dragging: true, scrollWheelZoom: true, tap: true }).setView([30.4, 69.3], 5);
  addBaseLayer(map);
  let marker = null, circle = null, results = [], active = -1, typingTimer = null, lastQuery = "";

  const fit = () => { if (circle) map.fitBounds(circle.getBounds(), { padding: [20, 20] }); };
  const place = (lat, lon, zoomToFit) => {
    latInput.value = lat.toFixed(6);
    lonInput.value = lon.toFixed(6);
    const km = parseFloat(radius.value) || 5;
    if (!marker) {
      marker = L.marker([lat, lon], { draggable: true, icon: L.divIcon({ className: "pin", html: "📍", iconSize: [28, 28], iconAnchor: [14, 26] }) }).addTo(map);
      marker.on("dragend", () => { const p = marker.getLatLng(); place(p.lat, p.lng, false); });
      circle = L.circle([lat, lon], { radius: km * 1000, weight: 2, fillOpacity: 0.08, interactive: false }).addTo(map);
    } else {
      marker.setLatLng([lat, lon]);
      circle.setLatLng([lat, lon]);
      circle.setRadius(km * 1000);
    }
    if (zoomToFit) fit();
    status.textContent = `Centre pinned at ${lat.toFixed(4)}, ${lon.toFixed(4)}. Drag the pin or click elsewhere to move it.`;
  };

  const closeList = () => { list.hidden = true; area.setAttribute("aria-expanded", "false"); active = -1; };
  const choose = (res) => {
    if (res.detail) area.value = [res.title, res.detail].join(", ");
    closeList();
    place(res.lat, res.lon, true);
  };
  const showList = (items, message) => {
    list.innerHTML = "";
    results = items;
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = message || "No places found. Try adding the city, or click the map.";
      list.appendChild(li);
    }
    items.forEach((res, i) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.textContent = res.title;
      if (res.detail) { const small = document.createElement("small"); small.textContent = res.detail; li.appendChild(small); }
      li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(res); });
      li.addEventListener("mouseenter", () => highlight(i));
      list.appendChild(li);
    });
    list.hidden = false;
    area.setAttribute("aria-expanded", "true");
    active = -1;
  };
  const highlight = (i) => {
    active = i;
    [...list.children].forEach((li, n) => li.setAttribute("aria-selected", String(n === i)));
  };
  const suggest = async (q) => {
    lastQuery = q;
    try {
      const items = await searchPlaces(q);
      if (q === lastQuery) showList(items);
    } catch (e) {
      if (q === lastQuery) showList([], e.message);
    }
  };
  const find = async () => {
    const q = area.value.trim();
    if (!q) { area.focus(); return; }
    status.textContent = "Searching…";
    try {
      const items = await searchPlaces(q, 1);
      if (!items.length) { status.textContent = "Place not found. Try adding the city and country, or click the map."; return; }
      closeList();
      place(items[0].lat, items[0].lon, true);
    } catch (e) {
      status.textContent = e.message || "Couldn't search the map. Check your internet connection.";
    }
  };

  area.addEventListener("input", () => {
    clearTimeout(typingTimer);
    const q = area.value.trim();
    if (q.length < 3) { closeList(); return; }
    typingTimer = setTimeout(() => suggest(q), 350);
  });
  area.addEventListener("keydown", (e) => {
    if (!list.hidden && results.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      highlight((active + (e.key === "ArrowDown" ? 1 : -1) + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (!list.hidden && active >= 0) choose(results[active]); else find();
    } else if (e.key === "Escape") {
      closeList();
    }
  });
  area.addEventListener("blur", () => setTimeout(closeList, 150));
  form.querySelector(".js-find-area").addEventListener("click", find);
  form.querySelector(".js-my-location").addEventListener("click", () => {
    if (!navigator.geolocation) { status.textContent = "This browser can't share your location."; return; }
    status.textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(
      (pos) => place(pos.coords.latitude, pos.coords.longitude, true),
      () => { status.textContent = "Location not shared. Type a place or click the map instead."; },
      { enableHighAccuracy: false, timeout: 10000 },
    );
  });

  map.on("click", (e) => place(e.latlng.lat, e.latlng.lng, false));
  radius.addEventListener("input", () => {
    if (circle) { circle.setRadius((parseFloat(radius.value) || 5) * 1000); fit(); }
  });

  if (el.dataset.lat && el.dataset.lon) {
    place(parseFloat(el.dataset.lat), parseFloat(el.dataset.lon), true);
  } else if (area.value.trim()) {
    find();
  }
  // The wizard shows step 2 later; Leaflet needs to re-measure once it's visible.
  document.addEventListener("wizard:step", () => setTimeout(() => { map.invalidateSize(); fit(); }, 50));
  window.addEventListener("resize", () => map.invalidateSize());
}
