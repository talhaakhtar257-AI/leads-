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
    if (step.querySelector('input[name="categories"]') && !step.querySelector('input[name="categories"]:checked')
        && !step.querySelector("#extra_categories").value.trim()) {
      alert("Pick at least one kind of business.");
      return false;
    }
    return true;
  };
  next.addEventListener("click", () => { if (stepValid()) { i += 1; show(); } });
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
