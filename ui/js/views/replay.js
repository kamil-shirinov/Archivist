// Watch it work: the recorded read of one page, replayed value by value in the order the pipeline took:
// read and cited, snapped to the ink, checked for covered ink, read again blind, checked against the
// bookkeeping rules, decided. Nothing is called; every step is the run's own record (the bundle).

import { S, stc, statusOf, fieldLabel, rulesOf, reasonSentence, docStats } from "../store.js";
import { PageView } from "../pageview.js";
import { noAnim } from "../wire.js";
import { $, esc, int, reduced, frame } from "../util.js";
import { runFacts } from "./overview.js";

const WDUR = { read: 420, snap: 300, sam: 170, blind: 420, rules: 360, decide: 320 };
const STEPS = [
  ["recognise", "Recognise the page", "extractor"],
  ["read", "Read and cite", "extractor"],
  ["snap", "Snap to the ink", null],
  ["sam", "Look for covered ink", "segmenter"],
  ["blind", "Read again, blind", "rereader"],
  ["rules", "Check the rules", null],
  ["decide", "Decide", null],
];
const modelOf = (role) => (role ? S.bundle.run.models.find((m) => m.role === role)?.name || "A model" : "Plain code");
const eOf = (role) => (role === "segmenter" ? "sam" : role ? "spark" : "code");

let W = null; // the replay under way
let pageId = null, pv = null, fastForwarding = false, cells = [], speed = reduced ? 10 : 3;

const values = (pid) => (S.fieldsByPage.get(pid) || []).filter((f) => f.value || f.status !== "accepted");

function fresh(pid) {
  return { page: S.pageById.get(pid), fields: values(pid), i: -1, ph: -1, play: false, t: null, ended: false, s: stats(), log: [], counted: new Set(), nodes: new Map() };
}
function stats() {
  return { n: 0, ok: 0, rev: 0, rules: 0, fail: 0, reads: 0, tier1: 0, tier2: 0 };
}

const stage = () => $("wstage");
const hidden = () => $("v-replay").hidden;

function setStage(k, name) {
  document.querySelectorAll("#w-steps li").forEach((li) => li.classList.toggle("on", li.dataset.k === k));
  $("w-stagename").textContent = name || "Ready";
}

// The rule a value is shown against: a failed one, else the first that held.
function ruleOf(f) {
  const rs = rulesOf(f);
  return rs.find((r) => !r.ok) || rs[0] || null;
}

function kpis() {
  const s = W.s, N = W.fields.length, sam = W.page.sam;
  const covered = sam.length ? `${sam.length} ${sam.length === 1 ? "mark" : "marks"}<small>, ${new Set(sam.flatMap((d) => d.fields)).size} over values</small>` : "None found";
  $("w-kpis").innerHTML =
    [
      ["Values read", `${s.n}<small> of ${N}</small>`],
      ["Verified", String(s.ok)],
      ["Sent to a person", String(s.rev)],
      ["Rules checked", `${s.rules}<small>${s.fail ? `, ${s.fail} failed` : ""}</small>`],
      ["Covered ink", W.i >= 0 || W.ended ? covered : "—"],
      ["Blind re-reads", String(s.reads)],
    ]
      .map(([l, v]) => `<div><div class="l">${l}</div><div class="v">${v}</div></div>`)
      .join("") +
    `<div style="grid-column:1/-1"><div class="l">Cost of this page</div><div class="v">$${runFacts().perPage.toFixed(4)}<small> the run’s average a page</small></div></div>`;
  $("w-of").textContent = `${s.n} of ${N} values`;
  $("w-bar").style.width = `${N ? (s.n / N) * 100 : 0}%`;
}

function log(html) {
  W.log.unshift(html);
  W.log = W.log.slice(0, 7);
  $("w-log").innerHTML = W.log.map((x) => `<li>${x}</li>`).join("");
}

// A document in a sentence: "sheet 35", "Memo 034146", "December 1939, page 53".
const plain = (d) => (d.kind === "ledger" ? d.title.toLowerCase() : d.title);
const noun = (d) => (d.kind === "ledger" ? "a ledger card" : d.kind === "memo" ? "a payment memo" : d.kind === "table" ? "a printed table" : "a page");

function head() {
  const d = S.docById.get(pageId);
  $("w-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<span>Watch it work</span>`;
  $("w-sub").textContent = `A replay of the recorded run on ${plain(d)}: every value read, snapped to the ink, read again blind, checked against the bookkeeping rules and decided. Nothing is called; this is the run’s own record.`;
  $("w-src").innerHTML = S.docs.map((x) => `<option value="${esc(x.page_id)}"${x.page_id === pageId ? " selected" : ""}>${esc(x.kind === "table" ? x.title : `${x.title}, ${x.typeLabel.toLowerCase()}`)}</option>`).join("");
  $("w-steps").innerHTML = STEPS.map(([k, t, role]) => `<li data-k="${k}" data-e="${eOf(role)}"><b>${t}</b><span>${esc(modelOf(role))}</span></li>`).join("");
  $("wbadge").textContent = d.kind === "table" ? `${d.typeLabel}, ${d.title}` : `${d.typeLabel}, ${d.title.toLowerCase()}`;
  $("w-ff").textContent = `Fast-forward the other ${S.docs.length - 1} pages`;
}

function setup(pid) {
  clearTimeout(W?.t);
  pageId = pid;
  W = fresh(pid);
  head();
  pv = new PageView(stage(), W.page);
  for (const d of W.page.sam) {
    const { rect } = pv.detection(d, { label: false });
    rect.classList.add("wsam");
    rect.style.opacity = 0;
  }
  $("wbadge").classList.remove("on");
  setStage(null, "Ready");
  $("w-log").innerHTML = "";
  const d = S.docById.get(pid);
  $("w-now").innerHTML = W.fields.length
    ? `<h3>${esc(d.title)}${d.holder ? `, ${esc(d.holder)}’s account` : ""}</h3><p class="sub" style="margin:0">Press Play to watch Archivist work through the page one value at a time: the same steps, in the same order, as the recorded run. Values it can’t confirm go to a person.</p>`
    : `<h3>${esc(d.title)}</h3><p class="sub" style="margin:0">${esc(W.page.failure || "This page has no values to replay.")}</p>`;
  $("w-play").disabled = !W.fields.length;
  $("w-play").textContent = "Play";
  kpis();
  cellsDraw();
  frame(() => {
    if (!hidden()) noAnim(pv.sheet, () => pv.camera({ fit: true }));
  });
}

function cam(f) {
  if (hidden() || !pv) return;
  if (!f || !f.box || speed >= 10 || W.ended) return pv.camera({ fit: true });
  pv.camera({ box: f.box, zoomCap: speed <= 1 ? 3 : 2 });
}

function now(f, ph) {
  const second = f.reread, agree = f.reread_status === "agrees", rule = ruleOf(f);
  const covered = f.occluders.length > 0;
  const row = (t, on, html) => `<dt>${t}</dt><dd>${ph >= on ? html : '<span class="wait">…</span>'}</dd>`;
  const m = (role) => esc(modelOf(role));
  const secondText = second != null ? `<span class="mono">${esc(second)}</span> <span class="${agree ? "ok" : "dis"}">${agree ? "✓ agrees" : "≠ disagrees"}</span>` : `<span class="dis">${esc({ illegible: "couldn’t be made out", failed: "the read failed", no_citation: "no box to read", not_reread: "not read again" }[f.reread_status] || f.reread_status)}</span>`;
  $("w-now").innerHTML =
    `<h3>${esc(fieldLabel(f))}</h3><dl class="wdl">` +
    row("First read", 0, `<span class="mono">${esc(f.value ?? "not read")}</span><span class="e">${m("extractor")}, reading the whole page</span>`) +
    row("Box", 1, `${f.box && f.original_box && JSON.stringify(f.box) !== JSON.stringify(f.original_box) ? "Snapped onto the printed ink" : "Kept where it was cited"}<span class="e">Plain code, from the page itself</span>`) +
    row("Covered ink", 2, covered ? `<span class="dis">${esc(f.occluders.map((o) => `A ${o.label} covers part of the cell`).join("; "))}</span><span class="e">${m("segmenter")}</span>` : `Nothing covering it<span class="e">${m("segmenter")}</span>`) +
    row("Second read", 3, `${secondText}<span class="e">${m("rereader")}, shown only this cell</span>`) +
    row("Rule", 4, rule ? `${esc(rule.label)} <span class="${rule.ok ? "ok" : "no"}">${rule.ok ? "✓" : "✗"}</span><span class="e mono">${esc(rule.equation || rule.detail || "")}</span>` : `No rule applies here<span class="e">Both reads must agree</span>`) +
    row("Decision", 5, f.status !== "accepted" ? `${stc("review")}<span class="e">${esc(f.reasons.map(reasonSentence).join(", ") ? f.reasons.map(reasonSentence).join(", ").replace(/^./, (c) => c.toUpperCase()) + "." : "Sent to a person.")}</span>` : `${stc("ok")}<span class="e">${rule ? "Two reads and a rule agree" : "Two reads agree"}</span>`) +
    "</dl>";
}

const SVG = "http://www.w3.org/2000/svg";
function rect(box, cls) {
  const r = document.createElementNS(SVG, "rect");
  r.setAttribute("class", `wbx ${cls}`);
  r.setAttribute("x", box.x0);
  r.setAttribute("y", box.y0);
  r.setAttribute("width", box.x1 - box.x0);
  r.setAttribute("height", box.y1 - box.y0);
  r.setAttribute("rx", 3);
  pv.ov.appendChild(r);
  return r;
}

function step() {
  clearTimeout(W.t);
  if (!W.play) return;
  const N = W.fields, sp = speed, next = (ms) => (W.t = setTimeout(step, Math.max(20, ms / sp)));
  if (W.i === -1 && W.ph === -1) {
    W.ph = 0;
    setStage("recognise", "Recognising the page");
    $("wbadge").classList.add("on");
    log(`<b>Page</b> recognised as ${noun(S.docById.get(pageId))} <span class="st st-ok">${esc(modelOf("extractor"))}</span>`);
    return next(1300);
  }
  if (W.i === -1 && W.ph === 0) {
    W.ph = 1;
    setStage("sam", "Looking for covered ink");
    if (!hidden()) {
      const sc = $("wscan");
      sc.style.setProperty("--wh", `${stage().clientHeight}px`);
      sc.classList.remove("on");
      void sc.offsetWidth;
      sc.classList.add("on");
    }
    setTimeout(() => {
      pv.ov.querySelectorAll(".wsam").forEach((n) => (n.style.opacity = 1));
      const sam = W.page.sam;
      log(sam.length ? `<b>${esc(modelOf("segmenter"))}</b> found ${sam.length} ${sam.length === 1 ? "mark" : "marks"} over values: ${sam.filter((d) => d.label === "stamp").length} stamp, ${sam.filter((d) => d.label === "stain").length} stain` : `<b>${esc(modelOf("segmenter"))}</b> found nothing covering the ink`);
      kpis();
    }, Math.max(40, 1100 / sp));
    return next(1700);
  }
  if (W.i === -1) {
    W.i = 0;
    W.ph = -1;
  }
  if (W.i >= N.length) return end();
  const f = N[W.i], flagged = f.status !== "accepted", slow = flagged ? 2.2 : 1;
  const node = W.nodes.get(f.field_id) || {};
  W.nodes.set(f.field_id, node);
  if (W.ph === -1) {
    W.ph = 0;
    setStage("read", "Reading and citing");
    cam(f);
    if (f.box && !node.raw) node.raw = rect(f.original_box || f.box, "");
    now(f, 0);
    return next(WDUR.read * slow);
  }
  if (W.ph === 0) {
    W.ph = 1;
    setStage("snap", "Snapping to the ink");
    if (f.box) {
      if (node.raw && f.original_box && JSON.stringify(f.box) !== JSON.stringify(f.original_box)) node.raw.classList.add("ghost");
      node.snap = rect(f.box, "snap");
      if (node.raw && !node.raw.classList.contains("ghost")) node.raw.remove();
    }
    now(f, 1);
    return next(WDUR.snap * slow);
  }
  if (W.ph === 1) {
    W.ph = 2;
    setStage("sam", "Checking for covered ink");
    const hit = W.page.sam.filter((d) => f.occluders.some((o) => o.label === d.label && o.box.x0 === d.box.x0 && o.box.y0 === d.box.y0));
    pv.ov.querySelectorAll(".wsam").forEach((n, i) => n.classList.toggle("hit", hit.includes(W.page.sam[i])));
    now(f, 2);
    return next((hit.length ? 900 : WDUR.sam) * slow);
  }
  if (W.ph === 2) {
    W.ph = 3;
    setStage("blind", "Reading again, blind");
    const agree = f.reread_status === "agrees";
    if (f.reread_status !== "not_reread") W.s.reads++;
    if (node.snap) {
      node.snap.classList.add(agree ? "agree" : "disagree");
      node.badge = pv.badge(f.box, agree ? "✓" : "≠", agree ? "" : "disagree");
    }
    now(f, 3);
    kpis();
    return next(WDUR.blind * slow);
  }
  if (W.ph === 3) {
    W.ph = 4;
    const rule = ruleOf(f);
    setStage("rules", "Checking the rules");
    for (const r of rulesOf(f))
      if (!W.counted.has(r.rule_id)) {
        W.counted.add(r.rule_id);
        W.s.rules++;
        if (!r.ok) W.s.fail++;
      }
    if (rule && !rule.ok && node.snap) {
      node.snap.classList.add("fail");
      if (node.badge) {
        node.badge.textContent = "✗";
        node.badge.className = "wm fail";
      }
    }
    now(f, 4);
    kpis();
    return next((rule ? WDUR.rules : 120) * slow);
  }
  if (W.ph === 4) {
    W.ph = 5;
    setStage("decide", "Deciding");
    if (node.snap) {
      node.snap.classList.remove("agree", "disagree", "fail");
      node.snap.classList.add(flagged ? "v-review" : "v-ok");
      if (!flagged) node.badge?.remove();
    }
    if (flagged) pv.loop(f, "red", { draw: true });
    W.s.n++;
    if (flagged) W.s.rev++;
    else {
      W.s.ok++;
      if (rulesOf(f).length) W.s.tier1++;
      else W.s.tier2++;
    }
    now(f, 5);
    kpis();
    log(`<b>${esc(fieldLabel(f))}</b> ${esc(f.value ?? "not read")} ${stc(flagged ? "review" : "ok")}`);
    return next(WDUR.decide * slow);
  }
  if (W.ph === 5) {
    W.i++;
    W.ph = -1;
    return step();
  }
}

function end() {
  W.play = false;
  W.ended = true;
  clearTimeout(W.t);
  $("w-play").textContent = "Replay";
  setStage(null, "Done");
  cam(null);
  const s = W.s, d = S.docById.get(pageId);
  const act = s.rev ? `<button class="primary" onclick="location.hash='review-${pageId}'">Review the ${s.rev} open ${s.rev === 1 ? "item" : "items"}</button>` : `<button class="primary" onclick="location.hash='doc-${pageId}'">Open ${esc(plain(d))}</button>`;
  $("w-now").innerHTML = `<h3>${esc(d.title)} done</h3><p class="sub" style="margin:0">${s.n} values. Every value either passed two independent reads, and a rule where one applies, or went to a person.</p>
  <div class="wtiers"><div><b>${s.tier1}</b><span>Two reads and a rule agree</span></div><div><b>${s.tier2}</b><span>Two reads agree, no rule applies</span></div><div><b>${s.rev}</b><span>Sent to a person</span></div></div>${act}`;
  kpis();
  log(`<b>${esc(d.title)}</b> done: ${s.ok} verified, ${s.rev} to a person`);
}

// --- the whole box ----------------------------------------------------------------------------------

const outcome = (d) => {
  const s = docStats(d.page_id);
  return s.exc ? "r" : s.open ? "a" : "g";
};
function cellsDraw(reveal = 0) {
  cells = S.docs.map((d) => outcome(d));
  $("w-cells").innerHTML = S.docs
    .map((d, i) => `<i data-p="${esc(d.page_id)}" title="${esc(d.title)}" class="${[i < reveal ? cells[i] : "", d.page_id === pageId ? "cur" : ""].join(" ").trim()}"></i>`)
    .join("");
  $("w-boxsum").innerHTML = reveal ? "" : `${esc(S.docById.get(pageId).title)} first, then the rest of ${esc(S.bundle.run.collection)} at speed.`;
}

function fastForward() {
  if (fastForwarding) return;
  fastForwarding = true;
  $("w-ff").disabled = true;
  const t0 = performance.now(), dur = reduced ? 0 : 4200, f = runFacts();
  const tot = { pages: S.docs.length, values: S.bundle.fields.length, ok: 0, rev: 0, exc: 0 };
  for (const x of S.bundle.fields) {
    const st = statusOf(x);
    if (st === "ok" || st === "you") tot.ok++;
    else if (st === "docerr") tot.exc++;
    else tot.rev++;
  }
  (function tick(now) {
    const p = dur ? Math.min(1, (now - t0) / dur) : 1, k = Math.max(1, Math.round(p * cells.length));
    cellsDraw(k);
    const v = (x) => int(Math.round(x * p));
    $("w-boxsum").innerHTML = `<b>${k}</b> of ${tot.pages} pages · <b>${v(tot.values)}</b> values · <b>${v(tot.ok)}</b> verified · <b>${v(tot.rev)}</b> sent to a person · <b>${v(tot.exc)}</b> where the document itself may be wrong`;
    if (p < 1) requestAnimationFrame(tick);
    else {
      $("w-boxsum").innerHTML += `<br>The recorded run took ${f.minutes} minutes and cost $${f.cost.toFixed(2)}, about $${f.perPage.toFixed(3)} a page. <a href="#accuracy">How accurate is it?</a>`;
      fastForwarding = false;
      $("w-ff").disabled = false;
    }
  })(t0);
}

function play() {
  if (W.ended) setup(pageId);
  W.play = !W.play;
  $("w-play").textContent = W.play ? "Pause" : "Play";
  if (W.play) step();
  else clearTimeout(W.t);
}
function pause() {
  if (W?.play) {
    W.play = false;
    clearTimeout(W.t);
    $("w-play").textContent = "Play";
  }
}

export function init() {
  $("w-play").addEventListener("click", play);
  $("w-restart").addEventListener("click", () => {
    pause();
    setup(pageId);
  });
  $("w-ff").addEventListener("click", fastForward);
  $("w-speed").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-s]");
    if (!b) return;
    speed = +b.dataset.s;
    $("w-steps").classList.toggle("fast", speed >= 10);
    $("w-speed").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    if (speed >= 10) cam(null);
  });
  $("w-src").addEventListener("change", (e) => (location.hash = `replay-${e.target.value}`));
  $("w-cells").addEventListener("click", (e) => {
    const c = e.target.closest("i[data-p]");
    if (c) location.hash = `replay-${c.dataset.p}`;
  });
  $("w-speed").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(+x.dataset.s === speed)));
  $("w-steps").classList.toggle("fast", speed >= 10);
}

export function enter(arg) {
  const pid = arg && S.docById.has(arg) ? arg : pageId || (S.docs.find((d) => (S.fieldsByPage.get(d.page_id) || []).some((f) => f.status !== "accepted")) || S.docs[0]).page_id;
  if (pid !== pageId || !W) {
    pause();
    setup(pid);
  } else frame(() => cam(W.i >= 0 && W.i < W.fields.length ? W.fields[W.i] : null));
}
export function resize() {
  if (pv && W) cam(W.i >= 0 && W.i < W.fields.length ? W.fields[W.i] : null);
}
export function leave() {
  pause();
}
