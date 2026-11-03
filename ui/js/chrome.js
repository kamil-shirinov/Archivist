// What every view shares: the top bar, the run bar that says what the visitor is looking at (and where
// Archivist runs), the side bar's count, light and dark, and the density.

import { S, STEPS, READS, totals, runWords } from "./store.js";
import { $, esc, int } from "./util.js";

export function setDensity(d) {
  document.documentElement.dataset.density = d;
  $("d-comf").setAttribute("aria-pressed", String(d === "comfortable"));
  $("d-comp").setAttribute("aria-pressed", String(d === "compact"));
  try {
    localStorage.setItem("archivist-density", d);
  } catch (e) {
    /* private mode */
  }
}

export function setTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  const dark = t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  $("t-light").setAttribute("aria-pressed", String(!dark));
  $("t-dark").setAttribute("aria-pressed", String(dark));
  try {
    if (t) localStorage.setItem("archivist-theme", t);
    else localStorage.removeItem("archivist-theme");
  } catch (e) {
    /* private mode */
  }
}

export function initTheme() {
  let d = "comfortable", t = null;
  try {
    d = localStorage.getItem("archivist-density") || d;
    t = localStorage.getItem("archivist-theme");
  } catch (e) {
    /* private mode */
  }
  setDensity(d);
  setTheme(t);
  $("d-comf").addEventListener("click", () => setDensity("comfortable"));
  $("d-comp").addEventListener("click", () => setDensity("compact"));
  $("t-light").addEventListener("click", () => setTheme("light"));
  $("t-dark").addEventListener("click", () => setTheme("dark"));
  if (!/Mac|iPhone|iPad/.test(navigator.platform || "")) $("cmdk-key").textContent = "Ctrl K";
}

// The count on the review queue and anything else that follows what has been answered.
export function refresh() {
  const t = totals();
  $("nav-count").textContent = int(t.open);
}

const ARM = { hosted: "Hosted models", "open-weights": "Open-weight models", mixed: "Hosted reader, open-weight checker", unknown: "Models not recorded" };

// What kind of pages a run is on, in a few words.
export function pagesWhat(r = S.bundle.run) {
  if (r.source === "synthetic") return r.stage === "test" ? "Synthetic test pages" : "Synthetic development pages";
  return "Real pages, development";
}

function switchTo(runId) {
  const u = new URL(location.href);
  u.searchParams.set("run", runId);
  location.href = u.toString();
}

// The menus and panels that open from the bars: one is open at a time, and Escape or a click elsewhere
// closes it. Opening the palette closes them too.
const closers = new Set();
export function closePanels(except) {
  closers.forEach((close) => close !== except && close());
}

// --- run on -----------------------------------------------------------------------------
// A chip in the run bar and the panel it opens: the seven steps are the same whether the models are
// reached through Meta’s API (the default) or run on your own hardware, and only the two reads change.
// What the visitor is looking at is one recorded run; the panel says who ran what in it, from the bundle.

const WHERE = { hosted: "Meta’s API", "open-weights": "Your own hardware", mixed: "Meta’s API and your own hardware", unknown: "Not recorded" };
const HOST = { meta: "Meta’s API", baseten: "Baseten", fireworks: "Fireworks", modal: "Modal" };

// "Muse Spark Open on Baseten; SAM 3.1 on Meta’s API": who ran what in this recording.
function recorded(r = S.bundle.run) {
  const byHost = new Map();
  for (const m of r.models) {
    const host = HOST[m.backend] || m.backend;
    if (!byHost.has(host)) byHost.set(host, []);
    if (!byHost.get(host).includes(m.name)) byHost.get(host).push(m.name);
  }
  return [...byHost].map(([host, names]) => `${names.join(" and ")} on ${host}`).join("; ");
}

// The run of this collection and stage for each way of running, where one was recorded.
function whereRuns() {
  const r = S.bundle.run;
  const same = S.index.runs.filter((x) => x.collection === r.collection && x.stage === r.stage);
  return { api: same.find((x) => x.arm === "hosted"), own: same.find((x) => x.arm === "open-weights") };
}

function whereChip() {
  const r = S.bundle.run;
  return `<button class="where" id="where" data-where="${r.arm === "open-weights" ? "own" : "api"}" aria-haspopup="dialog" aria-expanded="false" aria-controls="where-panel" title="${esc(recorded())}"><span class="wdot"></span>Run on <b>${esc(WHERE[r.arm])}</b><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`;
}

function wherePanel() {
  const r = S.bundle.run, runs = whereRuns();
  const steps = STEPS.map(([k, title], i) => `<li${READS.includes(k) ? ' class="moves"' : ""}><i>${i + 1}</i>${esc(title)}</li>`).join("");
  const opt = (key, name, tag, what, caveat = "") => {
    const run = runs[key];
    const note = run ? `Recorded on ${int(run.pages)} pages. ${caveat}` : "No recording of these pages on Muse Spark Open.";
    return `<button class="wp-opt" data-where="${key}"${run ? ` data-run="${esc(run.run_id)}"` : " disabled"} aria-pressed="${!!run && run.run_id === S.entry.run_id}"><span class="wo-h"><b>${name}</b><span class="tag">${tag}</span></span><span class="wo-d">${what}</span><span class="wo-n">${note.trim()}</span></button>`;
  };
  return (
    `<h2>Run on</h2>` +
    `<p class="wp-sub">The same seven steps either way. Only the two reads, steps 2 and 5, are done by a different model.</p>` +
    `<ol class="wp-steps" aria-label="The seven steps">${steps}</ol>` +
    `<div class="wp-opts" role="group" aria-label="Run on">` +
    opt("api", "Meta’s API", "Default", "Muse Spark 1.3 does both reads, and SAM 3.1 looks for covered ink, all through Meta’s API.") +
    opt(
      "own",
      "Your own hardware",
      "Muse Spark Open",
      "Muse Spark Open, whose trained weights are published, does both reads, so they can run on machines you control. SAM 3.1 still runs on Meta’s API.",
      "Not yet proven on site: the recording ran Muse Spark Open on Baseten, and no measured run has kept a page on a bank’s own machines."
    ) +
    `</div>` +
    `<p class="wp-now">This recording, <b>${esc(r.run_id)}</b>: ${esc(recorded(r))}.</p>`
  );
}

function initWhere() {
  const chip = $("where");
  const panel = document.createElement("div");
  panel.className = "where-panel";
  panel.id = "where-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Run on");
  panel.hidden = true;
  panel.innerHTML = wherePanel();
  document.body.appendChild(panel);
  const place = () => {
    const r = chip.getBoundingClientRect();
    panel.style.left = `${Math.max(8, Math.min(r.right - panel.offsetWidth, innerWidth - panel.offsetWidth - 8))}px`;
    panel.style.top = `${r.bottom + 6}px`;
  };
  const close = () => {
    panel.hidden = true;
    chip.setAttribute("aria-expanded", "false");
  };
  closers.add(close);
  chip.addEventListener("click", () => {
    if (!panel.hidden) return close();
    closePanels(close);
    panel.hidden = false;
    chip.setAttribute("aria-expanded", "true");
    place();
    (panel.querySelector('[aria-pressed="true"]') || panel.querySelector("button:not(:disabled)"))?.focus({ preventScroll: true });
  });
  panel.addEventListener("click", (e) => {
    const b = e.target.closest("[data-where]");
    if (!b || b.disabled) return;
    if (b.dataset.run !== S.entry.run_id) switchTo(b.dataset.run);
    else close();
  });
  document.addEventListener("click", (e) => {
    if (!panel.hidden && !panel.contains(e.target) && !chip.contains(e.target)) close();
  });
  addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || panel.hidden) return;
    close();
    chip.focus();
  });
  addEventListener("scroll", () => !panel.hidden && close(), { passive: true });
  addEventListener("resize", close);
  addEventListener("hashchange", close);
}

function collMenu() {
  const by = new Map();
  for (const x of S.index.runs) {
    if (!by.has(x.collection)) by.set(x.collection, []);
    by.get(x.collection).push(x);
  }
  return [...by]
    .map(
      ([name, runs]) =>
        `<div class="cm-g"><b>${esc(name)}</b>${runs.find((x) => x.description) ? `<p>${esc(runs.find((x) => x.description).description)}</p>` : ""}</div>` +
        runs
          .map(
            (x) =>
              `<button class="cm-i" data-run="${esc(x.run_id)}" aria-current="${x.run_id === S.entry.run_id}"><span>${esc(ARM[x.arm])}, ${esc([...new Set(x.models)].join(" and "))}</span><small>${x.source === "synthetic" ? "Synthetic" : "Real"} ${x.stage} pages · ${x.pages} pages · ${esc(x.run_id)}</small></button>`
          )
          .join("")
    )
    .join("");
}

function initCollMenu() {
  const menu = document.createElement("div");
  menu.className = "coll-menu panel";
  menu.id = "coll-menu";
  menu.hidden = true;
  menu.innerHTML = collMenu();
  document.body.appendChild(menu);
  const place = () => {
    const r = $("coll").getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${r.bottom + 6}px`;
  };
  const close = () => (menu.hidden = true);
  closers.add(close);
  $("coll").addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    if (!menu.hidden) {
      closePanels(close);
      place();
    }
  });
  menu.addEventListener("click", (e) => {
    const b = e.target.closest("[data-run]");
    if (b && b.dataset.run !== S.entry.run_id) switchTo(b.dataset.run);
    else close();
  });
  document.addEventListener("click", (e) => {
    if (!menu.contains(e.target)) close();
  });
  addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });
  addEventListener("resize", close);
}

// Say, on every view, what the pages are, which run this is and which models read them.
export function labelRun() {
  const r = S.bundle.run, w = runWords(), what = pagesWhat(r), pub = r.publication;
  const cost = r.extraction_run === r.run_id ? r.verification.cost_usd || 0 : (r.extraction.cost_usd || 0) + (r.verification.cost_usd || 0);
  $("coll-name").textContent = r.collection;
  $("coll-what").textContent = what;
  $("sample").textContent = r.source === "synthetic" ? what : "Development pages";
  $("runbar").innerHTML =
    `<span class="st st-review">${esc(what)}</span>` +
    (r.source !== "synthetic" ? `<span>Used to draft and test the rules, so not a measured result</span><span class="sep">·</span>` : "") +
    `<span>Run <b>${esc(r.run_id)}</b>, policy ${esc(r.policy)}</span><span class="sep">·</span>` +
    `<span>Read by <b>${esc(w.models)}</b> (${esc(w.arm)})</span>` +
    (pub ? `<span class="sep">·</span><span>${esc(pub.title)}, ${esc(pub.publisher)}. ${esc(pub.rights)}</span>` : "") +
    whereChip();
  $("side-foot").textContent =
    r.source === "synthetic"
      ? `Synthetic documents, made so every right answer is known; no real bank data. Run ${r.run_id}: ${w.models}, ${w.arm}. Cost of the run $${cost.toFixed(2)}.`
      : `${pub ? pub.title + " pages" : "Real pages"} from a public archive, development pages only. Run ${r.run_id}: ${w.models}, ${w.arm}. Cost of the run $${cost.toFixed(2)}.`;
  document.title = `Archivist · ${r.collection} · ${r.run_id}`;
  initCollMenu();
  initWhere();
}
