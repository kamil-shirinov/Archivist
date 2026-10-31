// What the live view and the header share: the local server's API, the mode, and the mode pill.
// Loaded only in the local app (archivist.live), never on the published site (D12, D13).

import { $ } from "../util.js";

const meta = document.querySelector('meta[name="archivist-live"]');
export const API = meta ? meta.content : null;

async function send(path, init) {
  const res = await fetch(API + path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(body.error || `${res.status} ${res.statusText}`), { status: res.status });
  return body;
}
export const api = {
  get: (path) => send(path),
  // A read is begun by the app alone: a JSON body and a header no other site's form or script can send.
  post: (path, body) =>
    send(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Archivist-Live": "1" }, body: JSON.stringify(body) }),
};

const KEY = "archivist-live-mode";
const read = () => {
  try {
    return sessionStorage.getItem(KEY) === "live" ? "live" : "replay"; // Replay unless Live calls is chosen
  } catch (e) {
    return "replay";
  }
};

// mode: what the next read will be, or what the read under way is; busy: a read is under way.
export const state = { mode: read(), busy: false };
const listeners = new Set();
export const onChange = (fn) => listeners.add(fn);

export function set(change) {
  Object.assign(state, change);
  try {
    sessionStorage.setItem(KEY, state.mode);
  } catch (e) {
    /* private mode: the choice lasts until the page is left */
  }
  pill();
  for (const fn of listeners) fn(state);
}

// The mode, on every view and at every width, in two words: "Live calls" or "Replay". It follows the
// read under way, never a setting that has been left behind.
export function pill() {
  const p = $("mode-pill");
  if (!p) return;
  p.dataset.mode = state.mode;
  p.toggleAttribute("data-busy", state.busy);
  p.textContent = state.mode === "live" ? "Live calls" : "Replay";
  p.title =
    state.mode === "live"
      ? "Reads ask the Meta models and are paid for from the spend caps; answers already in the cache are not asked again."
      : "Reads play answers already in the cache: no model is asked and nothing is spent.";
}
