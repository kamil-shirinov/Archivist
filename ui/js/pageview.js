// A scan with what the run found drawn over it, in the scan's own pixels: the pen loops and boxes
// the bundle carries, SAM's detections. The sheet is the scan at full size; a camera scales and moves
// it, so a stage can show the whole page or zoom to one value.

import { pageUrl } from "./store.js";
import { reduced, esc } from "./util.js";

const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

export class PageView {
  constructor(stage, page, label) {
    this.stage = stage;
    this.page = page;
    this.scale = 1;
    const { width: W, height: H } = page;
    this.sheet = document.createElement("div");
    this.sheet.className = "sheet";
    this.sheet.style.width = `${W}px`;
    this.sheet.style.height = `${H}px`;
    this.img = new Image();
    this.img.alt = label || `The scan of ${page.page_id}`;
    this.img.draggable = false;
    this.img.decoding = "async";
    this.img.src = pageUrl(page);
    this.ov = el("svg", { class: "ov", viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true", focusable: "false" });
    this.ovh = document.createElement("div");
    this.ovh.className = "ovh";
    this.sheet.append(this.img, this.ov, this.ovh);
    stage.querySelectorAll(":scope > .sheet").forEach((s) => s.remove());
    stage.prepend(this.sheet);
    this.marks = new Map(); // field id -> { stat, hot }
  }

  // --- the camera -----------------------------------------------------------------------------------

  // Fit the whole page, centred, in the stage.
  // Zoom to a box: the text about as tall on screen as the stage can use, and the box left of centre.
  camera({ box = null, fit = false, zoomCap = null } = {}) {
    const { width: W, height: H, text_height: th } = this.page;
    const sw = this.stage.clientWidth, sh = this.stage.clientHeight;
    const f = Math.min((sw - 24) / W, (sh - 24) / H);
    let s = f, tx, ty;
    this.stage.classList.toggle("zoomed", !fit && !!box);
    if (fit || !box) {
      tx = (sw - W * f) / 2;
      ty = (sh - H * f) / 2;
    } else {
      const cx = (box.x0 + box.x1) / 2, cy = (box.y0 + box.y1) / 2;
      s = Math.min(zoomCap || 2.4, Math.max(f * 1.5, 26 / th));
      tx = sw * (0.2 + 0.6 * (cx / W)) - cx * s;
      ty = sh * 0.46 - cy * s;
      tx = Math.min(24, Math.max(sw - W * s - 24, tx));
      ty = Math.min(24, Math.max(sh - H * s - 24, ty));
    }
    this.scale = s;
    this.sheet.style.transform = `translate(${tx}px,${ty}px) scale(${s})`;
    this.sheet.style.setProperty("--k", String(1 / s));
  }

  // A page set down in a box that grows to fit it, as wide as the box allows.
  fitWidth(pad = 14) {
    const { width: W, height: H } = this.page;
    const f = Math.min(1, (this.stage.clientWidth - 2 * pad) / W);
    this.scale = f;
    this.stage.style.height = `${Math.round(H * f + 2 * pad)}px`;
    this.sheet.style.transform = `translate(${pad}px,${pad}px) scale(${f})`;
    this.sheet.style.setProperty("--k", String(1 / f));
  }

  // --- marks ----------------------------------------------------------------------------------------

  // A pen loop round a value, in a tone (red for flagged, gold for pointing, grey for unread); where the
  // bundle has none for it, a rounded box round its citation instead.
  loop(field, tone, { draw = false, hot = false } = {}) {
    let node = null;
    const cls = `pen ${tone}${draw && !reduced ? " draw" : ""}`;
    if (field.loop) {
      node = el("path", { class: cls, d: field.loop.d, "stroke-width": field.loop.width, pathLength: 1 });
    } else if (field.box) {
      const b = field.box, pad = 4;
      node = el("rect", {
        class: `${cls} box`,
        x: b.x0 - pad,
        y: b.y0 - pad,
        width: b.x1 - b.x0 + 2 * pad,
        height: b.y1 - b.y0 + 2 * pad,
        rx: 6,
        "stroke-width": 3,
        pathLength: 1,
      });
    }
    if (!node) return null;
    node.dataset.field = field.field_id;
    this.ov.appendChild(node);
    const entry = this.marks.get(field.field_id) || {};
    entry[hot ? "hot" : "stat"] = node;
    this.marks.set(field.field_id, entry);
    return node;
  }

  highlight(field, { still = false } = {}) {
    const b = field.box;
    if (!b) return null;
    const r = el("rect", { class: `hl${still ? " still" : ""}`, x: b.x0 - 2, y: b.y0 - 2, width: b.x1 - b.x0 + 4, height: b.y1 - b.y0 + 4, rx: 3 });
    r.dataset.hl = field.field_id;
    this.ov.insertBefore(r, this.ov.firstChild);
    return r;
  }

  tick(field) {
    const ink = field.loop ? field.loop.ink : field.box && [field.box.x0, field.box.y0, field.box.x1, field.box.y1];
    if (!ink) return null;
    const k = this.page.text_height / 14;
    const g = el("g", { class: "tick-mark", transform: `translate(${ink[2] + 8 * k} ${(ink[1] + ink[3]) / 2 - 7 * k}) scale(${k})` });
    g.appendChild(el("path", { class: "tick", d: "M2 8l5 5L18 1", "stroke-width": 2.8 }));
    g.dataset.field = field.field_id;
    this.ov.appendChild(g);
    return g;
  }

  // A stamp or stain SAM 3.1 found over a value, boxed, with its name beside it.
  detection(d, { label = true, hit = false } = {}) {
    const b = d.box, pad = 5;
    const r = el("rect", { class: `sam${hit ? " hit" : ""}`, x: b.x0 - pad, y: b.y0 - pad, width: b.x1 - b.x0 + 2 * pad, height: b.y1 - b.y0 + 2 * pad, rx: 10 });
    this.ov.appendChild(r);
    let tag = null;
    if (label) {
      tag = document.createElement("span");
      tag.className = "tag samtag";
      tag.textContent = `${d.label === "stamp" ? "Stamp" : "Stain"} found by SAM 3.1`;
      tag.style.left = `${b.x0 - pad}px`;
      tag.style.top = `${b.y1 + pad + 3}px`;
      this.ovh.appendChild(tag);
    }
    return { rect: r, tag };
  }

  // A small badge on the page, in the scan's coordinates, that keeps its size on screen.
  badge(box, text, cls = "") {
    const s = document.createElement("span");
    s.className = `wm ${cls}`;
    s.textContent = text;
    s.style.left = `${box.x1 - 6}px`;
    s.style.top = `${box.y0 - 10}px`;
    this.ovh.appendChild(s);
    return s;
  }

  clearOverlay(selector) {
    this.ov.querySelectorAll(selector).forEach((n) => {
      if (n.dataset.field && this.marks.get(n.dataset.field)) {
        const m = this.marks.get(n.dataset.field);
        for (const k of ["stat", "hot"]) if (m[k] === n) delete m[k];
      }
      n.remove();
    });
  }

  // The element the thread should point at for a field: its hot loop, else its status loop.
  target(fieldId) {
    const m = this.marks.get(fieldId);
    return (m && (m.hot || m.stat)) || null;
  }

  // The field whose ink or box holds a point of the scan (the smallest, where boxes overlap).
  fieldAt(x, y, fields) {
    let best = null, area = Infinity;
    for (const f of fields) {
      const r = f.loop ? f.loop.ink : f.box && [f.box.x0, f.box.y0, f.box.x1, f.box.y1];
      if (!r) continue;
      const pad = 3;
      if (x < r[0] - pad || x > r[2] + pad || y < r[1] - pad || y > r[3] + pad) continue;
      const a = (r[2] - r[0]) * (r[3] - r[1]);
      if (a < area) {
        best = f;
        area = a;
      }
    }
    return best;
  }

  // A point on the screen as a point of the scan.
  toPage(clientX, clientY) {
    const r = this.sheet.getBoundingClientRect();
    return { x: ((clientX - r.left) / r.width) * this.page.width, y: ((clientY - r.top) / r.height) * this.page.height };
  }
}

export { esc };
