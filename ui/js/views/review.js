// Review queue: the values a person is asked to settle, a page at a time. The page is shown with the
// value ringed, the cell cut from the scan beside what each read and each rule said, and the answer is
// the visitor's own; it is kept in this browser and nowhere else.

import { S, LBL, statusOf, isOpen, heading, subtitle, fieldLabel, fieldContext, reasonLabel, reasonSentence, rulesOf, setAnswer, totals } from "../store.js";
import { PageView } from "../pageview.js";
import { wire, hideWire, follow, noAnim } from "../wire.js";
import { refresh } from "../chrome.js";
import { $, esc, norm, reduced, toast, int, frame } from "../util.js";

let pageId = null, items = [], cur = 0, fitMode = false, intro = false, advance = null, pv = null;

const MONEY = new Set(["debit", "credit", "balance", "brought_forward", "carried_forward", "amount"]);
const ICON = {
  ok: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  docerr: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5l6 10.5H2z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 6.5v3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="11.4" r=".9" fill="currentColor"/></svg>',
  unread: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2.4 2.2"/></svg>',
};
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// The pages with something to settle, in the order of the documents.
const pagesWithOpen = () => S.docs.filter((d) => (S.fieldsByPage.get(d.page_id) || []).some(isOpen));
const reviewSet = (pid) => (S.fieldsByPage.get(pid) || []).filter((f) => f.status !== "accepted");
const doneAnswer = (f) => S.answers[f.field_id] || null;
const failingRule = (f) => rulesOf(f).find((r) => !r.ok);
const implied = (f) => f.flags.find((x) => x.suggested)?.suggested || failingRule(f)?.suggested || null;

// The values this field may be answered with: the reads and the proposal, once each.
function options(f) {
  const out = [];
  const add = (v, src) => {
    if (v == null || v === "" || out.some((o) => norm(o.v) === norm(v))) return;
    out.push({ v, src });
  };
  const same = f.value != null && f.reread != null && norm(f.value) === norm(f.reread);
  add(f.value, same ? "Both reads" : "First read, with the whole page");
  add(f.reread, "Second read, on its own");
  if (f.proposal) add(f.proposal, f.proposed_by === "check" ? "Proposed from the rules" : "Proposed from the second read");
  return out;
}

// --- the page ---------------------------------------------------------------------------------------

function dots() {
  pv.clearOverlay(".dot");
  const k = pv.page.text_height * 0.28;
  items.forEach((f, i) => {
    if (i === cur || doneAnswer(f) || !f.box) return;
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("class", "dot");
    r.setAttribute("x", f.box.x1 - k);
    r.setAttribute("y", f.box.y0 - k);
    r.setAttribute("width", 2 * k);
    r.setAttribute("height", 2 * k);
    r.setAttribute("rx", k / 3);
    pv.ov.appendChild(r);
  });
}

function marks() {
  pv.clearOverlay(".hl,.pen.hot,.sam,.tag");
  pv.ovh.innerHTML = "";
  const f = items[cur];
  if (!doneAnswer(f)) {
    pv.highlight(f);
    pv.loop(f, "red", { draw: true, hot: true });
    for (const o of f.occluders) {
      const d = S.pageById.get(pageId).sam.find((x) => x.label === o.label && x.box.x0 === o.box.x0 && x.box.y0 === o.box.y0);
      if (d) pv.detection(d);
    }
  }
  dots();
}

function cellMark(f) {
  pv.clearOverlay(`[data-field="${CSS.escape(f.field_id)}"]`);
  const a = doneAnswer(f);
  if (!a) return;
  if (a.st === "you") pv.tick(f);
  else pv.loop(f, a.st === "unread" ? "grey" : "red", { draw: true });
}

const cam = () => pv.camera({ box: fitMode ? null : items[cur].box, fit: fitMode });
function rWire() {
  const f = items[cur];
  if (fitMode || !f || doneAnswer(f) || $("v-review").hidden) return hideWire($("thread"));
  wire($("thread"), $("rv-main"), $("p-crop"), pv.target(f.field_id), $("stage"), "l");
}

// --- the panel --------------------------------------------------------------------------------------

function crop(f) {
  const el = $("p-crop");
  const r = f.loop ? f.loop.ink : f.box && [f.box.x0, f.box.y0, f.box.x1, f.box.y1];
  if (!r) {
    el.innerHTML = '<div class="none">No box was cited for this value.</div>';
    return;
  }
  const th = pv.page.text_height, px = th * 0.9, py = th * 0.7;
  const x0 = r[0] - px, y0 = r[1] - py, w = r[2] - r[0] + 2 * px, h = r[3] - r[1] + 2 * py;
  const cw = el.clientWidth || 340, ch = el.clientHeight || 84;
  const s = Math.min(cw / w, ch / h, 3.2);
  const url = new URL(pv.page.image.url, S.bundleUrl).href;
  el.innerHTML = `<i role="img" aria-label="The cited cell, cut from the scan" style="background-image:url('${url}');background-size:${pv.page.width * s}px ${pv.page.height * s}px;background-position:${(cw - w * s) / 2 - x0 * s}px ${(ch - h * s) / 2 - y0 * s}px"></i>`;
}

function whyText(f) {
  if (f.status === "abstained" && f.value == null) return "Muse Spark didn’t read this one, so it needs a person.";
  const bits = f.reasons.map(reasonSentence).filter(Boolean);
  return bits.length ? `${cap(bits.join(", and "))}.` : "Sent to a person.";
}

function renderPanel() {
  const f = items[cur], a = doneAnswer(f), st = statusOf(f);
  $("p-field").textContent = fieldLabel(f);
  $("p-status").className = `st st-${st}`;
  $("p-status").textContent = LBL[st];
  $("p-reasons").innerHTML = f.reasons.map((r) => `<span class="tag">${esc(reasonLabel(r))}</span>`).join("");
  crop(f);
  $("p-why").textContent = whyText(f);
  const rows = [];
  for (const r of rulesOf(f).filter((x) => !x.ok))
    rows.push(`<dt>${esc(r.label)}</dt><dd class="by">${esc(r.detail || "This check failed.")}</dd>${r.equation ? `<dd class="v fail">${esc(r.equation)}</dd>` : ""}`);
  rows.push(
    `<dt>Reads</dt><dd class="by">Muse Spark read this on the whole page, then again on its own</dd><dd class="v">${esc(f.value ?? "not read")} then ${esc(f.reread ?? ({ illegible: "couldn’t be made out", failed: "failed", no_citation: "no box", not_reread: "not read again" }[f.reread_status] || "—"))}</dd>`
  );
  $("p-ev").innerHTML = rows.join("");
  const opts = options(f);
  $("p-answer").hidden = !!a;
  $("other").hidden = true;
  $("other-err").hidden = true;
  $("other-in").value = "";
  $("p-ask").textContent = `What does the ${S.docById.get(pageId).kind === "memo" ? "memo" : "page"} say here?`;
  $("opts").innerHTML = opts.map((o, i) => `<button class="opt" data-v="${esc(o.v)}"><span class="k">${i + 1}</span><span><span class="ov">${esc(o.v)}</span><span class="src">${esc(o.src)}</span></span></button>`).join("");
  $("opt-row").innerHTML = `<button class="opt-sm" id="o-other"><span class="k">${opts.length + 1}</span>Something else</button><button class="opt-sm" id="o-unread"><span class="k">${opts.length + 2}</span>Can’t read it</button>`;
  $("o-other").addEventListener("click", openOther);
  $("o-unread").addEventListener("click", () => decide("unread"));
  $("other-in").placeholder = MONEY.has(f.name) ? `For example ${opts[0]?.v || "1,234.56"}` : f.name === "date" ? "For example 07/09/76" : f.name === "sheet_no" ? "Sheet number" : "What the page says";
  $("p-hint").innerHTML = `Answer from the crop; Archivist rechecks the rules after you answer. <kbd>1</kbd> to <kbd>${opts.length + 2}</kbd> answer, <kbd>J</kbd> and <kbd>K</kbd> move.`;
  $("outcome").hidden = !a;
  if (a) {
    $("outcome").className = `outcome ${a.st}`;
    $("out-icon").innerHTML = ICON[a.st === "you" ? "ok" : a.st];
    $("out-msg").textContent = a.msg;
    $("out-next").textContent = nextAfter() ? (nextAfter().same ? "Next item" : "Next page") : "Back to overview";
  }
  const trail = [`<b>${esc(modelOf("extractor"))}</b> read the page and cited this cell.`];
  trail.push(f.occluders.length ? `<b>SAM 3.1</b> found a ${esc(f.occluders.map((o) => o.label).join(" and a "))} covering part of it.` : "<b>SAM 3.1</b> found nothing covering it.");
  trail.push(
    f.reread_status === "agrees"
      ? `<b>${esc(modelOf("rereader"))}</b> read the cell again on its own, without the first answer, and got the same.`
      : f.reread_status === "disagrees"
        ? `<b>${esc(modelOf("rereader"))}</b> read the cell again on its own, without the first answer, and got a different value.`
        : `<b>${esc(modelOf("rereader"))}</b> tried to read the cell again on its own: ${esc({ illegible: "it couldn’t be made out", failed: "the read failed", no_citation: "there was no box to read", not_reread: "it wasn’t read again" }[f.reread_status] || f.reread_status)}.`
  );
  for (const r of rulesOf(f).filter((x) => !x.ok)) trail.push(`${esc(r.label)} failed: ${esc(r.detail || r.equation || "")}`);
  if (f.reasons.some((r) => r.code === "obscured")) trail.push("Obscured values always go to a person, whatever the arithmetic says.");
  if (a) trail.push(`You answered ${esc(a.val)}.`);
  $("p-trail").innerHTML = trail.map((t) => `<li>${t}</li>`).join("");
  const left = items.filter((x) => !doneAnswer(x)).length;
  $("q-list").innerHTML = items
    .map((x, i) => {
      const d = doneAnswer(x);
      return `<li${i === cur ? ' aria-current="true"' : ""}><button data-i="${i}"><span class="qf">${esc(fieldLabel(x))}</span><span class="qw">${esc(x.reasons.map(reasonLabel).join(", ") || "Not read")}</span><span class="qv">${esc(d ? (d.st === "unread" ? "—" : d.val) : x.value ?? "—")}${d ? `<span class="qs ${d.st}">${LBL[d.st]}</span>` : ""}</span></button></li>`;
    })
    .join("");
  $("q-count").textContent = `${left} open`;
  $("pos").textContent = `${cur + 1} of ${items.length} on this page`;
  $("prog").style.width = `${Math.max(2, ((items.length - left) / items.length) * 100)}%`;
  $("ctx").textContent = fieldContext(f);
}

function modelOf(role) {
  return S.bundle.run.models.find((m) => m.role === role)?.name || "The model";
}

function header() {
  const d = S.docById.get(pageId), t = totals();
  $("rv-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<a href="#review">Review queue</a>/<span>${esc(d.title)}</span>`;
  $("rv-t").textContent = heading(d);
  const open = items.filter((f) => isOpen(f)).length;
  $("rv-sub").textContent = `${subtitle(d)} ${open} open ${open === 1 ? "item" : "items"} on this page; ${int(t.open)} open in ${S.bundle.run.collection}.`;
  const list = pagesWithOpen();
  $("rv-prev-page").disabled = list.length < 2;
  $("rv-next-page").disabled = list.length < 2;
}

// --- answering --------------------------------------------------------------------------------------

function nextAfter() {
  const here = items.findIndex((x, i) => i !== cur && !doneAnswer(x) && i > cur);
  const any = items.findIndex((x, i) => i !== cur && !doneAnswer(x));
  if (here >= 0 || any >= 0) return { same: true, i: here >= 0 ? here : any };
  const next = pagesWithOpen().find((d) => d.page_id !== pageId);
  return next ? { same: false, page: next.page_id } : null;
}

function decide(kind, value) {
  const f = items[cur];
  if (doneAnswer(f)) return;
  const rule = failingRule(f), want = implied(f);
  let a;
  if (kind === "unread") {
    a = { st: "unread", val: "Not readable", msg: `Marked not readable.${want ? ` The ${rule.label.toLowerCase()} implies ${want}.` : ""} That’s recorded as inferred, not read.` };
  } else if (want && norm(value) === norm(want)) {
    a = { st: "you", val: value, msg: `Reviewed: ${value} fits the ${rule.label.toLowerCase()}. Your answer and both reads are kept in the decision trail.` };
  } else if (rule && want) {
    a = { st: "docerr", val: value, msg: `The page itself doesn’t add up here: ${rule.equation || rule.detail}. Recorded as printed and raised as an exception in the source document.` };
  } else {
    a = { st: "you", val: value, msg: `Reviewed: ${value}. Your answer and both reads are kept in the decision trail.` };
  }
  a.t = new Date().toISOString();
  setAnswer(f.field_id, a);
  cellMark(f);
  renderPanel();
  header();
  refresh();
  hideWire($("thread"));
  toast(a.st === "you" ? `${a.val} reviewed and saved` : a.st === "docerr" ? "Saved as printed and raised as an exception" : "Saved as not readable");
  const next = nextAfter(), me = cur;
  if (next && next.same) advance = setTimeout(() => { if (cur === me && !$("v-review").hidden) go(next.i); }, 2200); // long enough to read what was decided, whatever the motion settings
}

function openOther() {
  $("other").hidden = false;
  $("other-in").focus();
}
function saveOther() {
  const f = items[cur], v = $("other-in").value.trim(), e = $("other-err");
  let out = null, msg = "";
  if (MONEY.has(f.name)) {
    const s = v.replace(/£/g, "");
    if (/^-?\d[\d,]*\.\d{2}$/.test(s)) out = s;
    else msg = "Enter an amount with pence, like 1,234.56.";
  } else if (f.name === "date") {
    if (/^\d{2}\/\d{2}\/\d{2,4}$/.test(v)) out = v;
    else msg = "Enter a date like 07/09/76.";
  } else if (f.name === "sheet_no") {
    if (/^\d{1,3}$/.test(v)) out = String(+v);
    else msg = "Enter the sheet number in figures.";
  } else if (v) out = v;
  else msg = "Enter what the page says.";
  if (out == null) {
    e.textContent = msg;
    e.hidden = false;
    $("other-in").focus();
    return;
  }
  decide("other", out);
}

function go(i) {
  clearTimeout(advance);
  cur = (i + items.length) % items.length;
  fitMode = false;
  $("fit").textContent = "Whole page";
  marks();
  renderPanel();
  cam();
  follow(rWire, reduced ? 0 : 900);
}

function load(pid) {
  pageId = pid;
  items = reviewSet(pid);
  const first = items.findIndex(isOpen);
  cur = first >= 0 ? first : 0;
  const stage = $("stage");
  pv = new PageView(stage, S.pageById.get(pid));
  header();
  intro = false;
  frame(() => {
    fitMode = true;
    noAnim(pv.sheet, cam);
    marks();
    renderPanel();
    setTimeout(() => {
      fitMode = false;
      cam();
      follow(rWire, 1000);
    }, reduced ? 0 : 450);
  });
}

function nothingOpen() {
  $("rv-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<span>Review queue</span>`;
  $("rv-t").textContent = "Nothing is open";
  $("rv-sub").textContent = "Every value that went to a person has been answered in this browser.";
  $("rv-main").hidden = true;
}

export function init() {
  $("opts").addEventListener("click", (e) => {
    const b = e.target.closest(".opt");
    if (b) decide("read", b.dataset.v);
  });
  $("other-save").addEventListener("click", saveOther);
  $("other-in").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveOther();
    }
  });
  $("other-in").addEventListener("input", () => ($("other-err").hidden = true));
  $("out-next").addEventListener("click", () => {
    const n = nextAfter();
    if (!n) location.hash = "overview";
    else if (n.same) go(n.i);
    else location.hash = `review-${n.page}`;
  });
  $("q-list").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (b) go(+b.dataset.i);
  });
  $("fit").addEventListener("click", () => {
    fitMode = !fitMode;
    $("fit").textContent = fitMode ? "Focus on the value" : "Whole page";
    cam();
    follow(rWire, 900);
  });
  const step = (dir) => {
    const list = pagesWithOpen();
    if (!list.length) return;
    const i = list.findIndex((x) => x.page_id === pageId);
    location.hash = `review-${list[(i + dir + list.length) % list.length].page_id}`;
  };
  $("rv-prev-page").addEventListener("click", () => step(-1));
  $("rv-next-page").addEventListener("click", () => step(1));
  $("rv-open").addEventListener("click", () => (location.hash = `doc-${pageId}`));
}

export function enter(arg) {
  const list = pagesWithOpen();
  let pid = arg && S.docById.has(arg) && reviewSet(arg).length ? arg : null;
  if (!pid) {
    if (!list.length) return nothingOpen();
    pid = list[0].page_id;
    if (arg !== pid) {
      history.replaceState(history.state, "", `#review-${pid}`); // keep the entry's scroll tag
    }
  }
  $("rv-main").hidden = false;
  load(pid);
}

export function resize() {
  if (!pv || !items.length) return;
  cam();
  rWire();
}
export const scroll = () => items.length && rWire();
export const entered = () => items.length && rWire(); // the entrance is over: the thread can point at content that is no longer moving
export function leave() {
  hideWire($("thread"));
  clearTimeout(advance);
}
export function key(e) {
  if ($("v-review").hidden || !items.length) return;
  const k = e.key.toLowerCase();
  if (k === "j") go(cur + 1);
  else if (k === "k") go(cur - 1);
  else if (!doneAnswer(items[cur])) {
    const opts = options(items[cur]), n = +k;
    if (n >= 1 && n <= opts.length) decide("read", opts[n - 1].v);
    else if (n === opts.length + 1) {
      e.preventDefault();
      openOther();
    } else if (n === opts.length + 2) decide("unread");
  }
}
