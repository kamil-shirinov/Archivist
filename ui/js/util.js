// Small helpers shared by every view.

export const $ = (id) => document.getElementById(id);

// Run fn once layout is up to date. Normally that is the next frame; while a view transition is
// swapping the content (rendering is paused then, so no frame would come) the layout is forced
// at once, which every caller can bear: they only read sizes and draw.
let sync = false;
export const setSync = (on) => (sync = on);
export const frame = (fn) => (sync ? fn() : requestAnimationFrame(fn));
export const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

export const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

export const num = (s) => parseFloat(String(s).replace(/[,£\s]/g, ""));
export const money = (x) =>
  Number(x).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const int = (x) => Number(x).toLocaleString("en-GB");
export const pad = (n, w) => String(n).padStart(w, "0");
export const norm = (s) => String(s).replace(/[\s,£]/g, "").toLowerCase();

export const MONS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// Dates as the records print them, day/month/year with a two-digit year read as 19yy, like the checks.
export function parseDate(text) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/.exec(String(text ?? "").trim());
  if (!m) return null;
  const d = +m[1], mo = +m[2], y = +m[3] < 100 ? 1900 + +m[3] : +m[3];
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return new Date(Date.UTC(y, mo - 1, d));
}
export const fmtDate = (text) => {
  const d = parseDate(text);
  return d ? `${d.getUTCDate()} ${MONS[d.getUTCMonth()]} ${d.getUTCFullYear()}` : text ? String(text) : "—";
};
export const longDate = (d) => `${d.getUTCDate()} ${MONS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
export const monthYear = (d) => `${MONS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;

// A seeded generator, for what is only arranged (the dots of a chart), never measured.
export function rng(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let toastTimer;
export function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("on"), 3200);
}

export async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${url}`);
  return res.json();
}

// "about 1 in 5" for a share: the nearest whole number of values out of which one is it.
export const oneIn = (share) => (share > 0 ? `1 in ${Math.max(1, Math.round(1 / share))}` : "none");
export const per = (share, n) => Math.round(share * n);
