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

// Say, on every view, what the pages are, which run this is and which models read them.
export function labelRun() {
  const r = S.bundle.run, w = runWords();
  const cost = (r.extraction.cost_usd || 0) + (r.verification.cost_usd || 0);
  $("coll-name").textContent = r.collection;
  $("coll-what").textContent = r.source === "synthetic" ? "Synthetic test pages" : "Public-domain scans";
  $("sample").textContent = r.source === "synthetic" ? "Synthetic test pages" : "Public-domain scans";
  $("runbar").innerHTML =
    `<span class="st st-review">${r.source === "synthetic" ? "Synthetic test pages" : "Public-domain scans"}</span>` +
    `<span>Run <b>${esc(r.run_id)}</b>, policy ${esc(r.policy)}</span><span class="sep">·</span>` +
    `<span>Read by <b>${esc(w.models)}</b> (${esc(w.arm)})</span>`;
  $("side-foot").textContent =
    `Synthetic documents, made so every right answer is known; no real bank data. Run ${r.run_id}: ${w.models}, ${w.arm}. Cost of the run $${cost.toFixed(2)}.`;
  if (r.source !== "synthetic") $("side-foot").textContent = `Public-domain scans. Run ${r.run_id}: ${w.models}, ${w.arm}.`;
  document.title = `Archivist · ${r.collection} · ${r.run_id}`;
}
