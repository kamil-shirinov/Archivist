// What every view shares: the top bar, the run bar that says what the visitor is looking at, the side
// bar's count, light and dark, and the density.

import { S, totals, runWords } from "./store.js";
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
const ARM_SHORT = { hosted: "Hosted", "open-weights": "Open weights", mixed: "Mixed", unknown: "—" };

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

// The runs of the collection being looked at, as a switch: the same pages, read by another arm.
function runSwitch() {
  const r = S.bundle.run;
  const same = S.index.runs.filter((x) => x.collection === r.collection && x.stage === r.stage);
  if (same.length < 2) return "";
  return `<div class="seg runswitch" role="group" aria-label="Which run">${same
    .map((x) => `<button data-run="${esc(x.run_id)}" aria-pressed="${x.run_id === r.run_id}" title="${esc(x.models.filter((m, i, a) => a.indexOf(m) === i).join(", "))}">${ARM_SHORT[x.arm]}</button>`)
    .join("")}</div>`;
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
  $("coll").addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    if (!menu.hidden) place();
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
    runSwitch();
  $("runbar").querySelectorAll("[data-run]").forEach((b) => b.addEventListener("click", () => b.dataset.run !== r.run_id && switchTo(b.dataset.run)));
  $("side-foot").textContent =
    r.source === "synthetic"
      ? `Synthetic documents, made so every right answer is known; no real bank data. Run ${r.run_id}: ${w.models}, ${w.arm}. Cost of the run $${cost.toFixed(2)}.`
      : `${pub ? pub.title + " pages" : "Real pages"} from a public archive, development pages only. Run ${r.run_id}: ${w.models}, ${w.arm}. Cost of the run $${cost.toFixed(2)}.`;
  document.title = `Archivist · ${r.collection} · ${r.run_id}`;
  initCollMenu();
}
