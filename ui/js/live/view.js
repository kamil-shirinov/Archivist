// Read a page: the local app's live view (P35). Pick a development page, press Read live (or Replay),
// and watch the existing pipeline work: the seven steps lighting up in order, each Meta model call
// listed as it happens with its model, latency, tokens, cost and whether it was asked or answered
// from the cache, and the values appearing on the scan in their boxes. When the read ends, the page
// opens in the normal document view and review queue.
//
// Everything on screen comes from the event stream archivist.live sends (server-sent events); the
// browser asks for nothing but that, and the page gate is the server's.

import { PageView } from "../pageview.js";
import { noAnim } from "../wire.js";
import { $, esc, int, reduced, frame, toast } from "../util.js";
import { api, state, set, onChange } from "./core.js";

const STEPS = [
  ["recognise", "Recognise the page", "extractor"],
  ["read", "Read and cite", "extractor"],
  ["snap", "Snap to the ink", null],
  ["sam", "Look for covered ink", "segmenter"],
  ["blind", "Read again, blind", "rereader"],
  ["rules", "Check the rules", null],
  ["decide", "Decide", null],
];
const TITLE = Object.fromEntries(STEPS.map(([k, t]) => [k, t]));
const SVG = "http://www.w3.org/2000/svg";
const ROLE_E = { segmenter: "sam", extractor: "spark", rereader: "spark" };
const AUTO = "archivist-live-auto";

let status = null, groups = [], pages = new Map();
let page = null, pv = null; // the page picked, and its scan on the stage
let R = null; // the read being shown
let source = null; // its event stream
let ticker = null;

const ms = (v) => (v < 1000 ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(1)} s`);
const usd = (v) => `$${Number(v).toFixed(4)}`;
const stage = () => $("lstage");

export function markup() {
  return `
  <div class="crumbs"><a href="#overview">Archivist</a>/<span>Read a page</span></div>
  <div class="ph"><div><h1 id="l-t">Read a page</h1><p class="sub" id="l-sub">Pick a development page and watch Archivist read it: every step, and every call to a Meta model, as it happens.</p></div>
    <div class="actions">
      <div class="seg" id="l-mode" role="group" aria-label="Mode"><button data-m="live" aria-pressed="false">Live calls</button><button data-m="replay" aria-pressed="true">Replay</button></div>
      <div class="seg" id="l-speed" role="group" aria-label="Replay speed" hidden><button data-s="1" aria-pressed="true">1×</button><button data-s="3" aria-pressed="false">3×</button><button data-s="10" aria-pressed="false">10×</button></div>
      <button id="l-stop" hidden>Stop</button>
      <button class="primary" id="l-go">Replay</button>
    </div></div>
  <div class="lpick">
    <label><span>Page</span><select id="l-page" aria-label="Page to read"></select></label>
    <label class="lfilter"><span class="sr">Filter the pages</span><input id="l-filter" type="search" placeholder="Filter pages" autocomplete="off"></label>
    <label id="l-arm-l"><span>Models</span><select id="l-arm" aria-label="Which models read it"></select></label>
  </div>
  <p class="lnote" id="l-note" role="status"></p>
  <ol class="wsteps" id="l-steps"></ol>
  <div class="wgrid">
    <div>
      <div class="stage" id="lstage"><div class="wscan" id="lscan"></div><div class="wbadge" id="lbadge"></div></div>
      <div class="wprog"><i id="l-bar"></i></div>
    </div>
    <aside class="wside lside" id="l-side">
      <div class="panel"><div class="panel-h"><h2>Now</h2><span class="tag" id="l-stage">Ready</span></div><div class="panel-b wnow" id="l-now" aria-live="polite"></div></div>
      <div class="panel lcalls"><div class="panel-h"><h2>Model calls</h2><span class="tag" id="l-tally">none yet</span></div><ol class="lcall-list" id="l-calls" aria-live="off"></ol></div>
    </aside>
  </div>`;
}

// --- the picker ---------------------------------------------------------------------------------

const current = () => pages.get($("l-page").value) || null;

function fillPages() {
  const q = $("l-filter").value.trim().toLowerCase(), keep = $("l-page").value || sessionStorage.getItem("archivist-live-page");
  $("l-page").innerHTML = groups
    .map((g) => {
      const rows = g.pages.filter((p) => !q || `${p.label} ${p.family} ${p.ref}`.toLowerCase().includes(q));
      if (!rows.length) return "";
      return `<optgroup label="${esc(g.title)}">${rows
        .map((p) => `<option value="${esc(p.ref)}"${p.scan ? "" : " disabled"}>${p.read_before ? "● " : ""}${esc(p.label)}${p.family && g.id === "treasury" ? ` — ${esc(p.family)}` : ""}${p.scan ? "" : " (not downloaded)"}</option>`)
        .join("")}</optgroup>`;
    })
    .join("");
  if (keep && [...$("l-page").options].some((o) => o.value === keep && !o.disabled)) $("l-page").value = keep;
  else {
    const first = [...$("l-page").options].find((o) => !o.disabled);
    if (first) $("l-page").value = first.value;
  }
}

async function pick() {
  const ref = $("l-page").value;
  if (!ref) return void showPage(null);
  try {
    sessionStorage.setItem("archivist-live-page", ref);
  } catch (e) {
    /* private mode */
  }
  const info = await api.get(`page?ref=${encodeURIComponent(ref)}`).catch((e) => (toast(e.message), null));
  if (info && !state.busy) showPage(info);
  controls();
}

function showPage(info) {
  page = info;
  pv = null;
  stage().querySelectorAll(":scope > .sheet").forEach((s) => s.remove());
  $("lbadge").classList.remove("on");
  if (!info) return;
  pv = new PageView(stage(), { page_id: info.page_id, width: info.width, height: info.height, text_height: 16, image: { url: `${apiBase()}image?ref=${encodeURIComponent(info.ref)}` } }, `The scan of ${info.label}`);
  $("lbadge").textContent = info.label;
  $("lbadge").classList.add("on");
  frame(() => noAnim(pv.sheet, () => pv.camera({ fit: true })));
}
const apiBase = () => document.querySelector('meta[name="archivist-live"]').content;

function arms() {
  $("l-arm").innerHTML = (status?.arms || [])
    .map((a) => `<option value="${esc(a.id)}">${esc(a.title)}: ${esc(a.models.join(", "))}</option>`)
    .join("");
  $("l-arm").value = sessionStorage.getItem("archivist-live-arm") || "a";
  if ($("l-arm").value !== (sessionStorage.getItem("archivist-live-arm") || "a")) $("l-arm").value = "a";
}

// --- controls -----------------------------------------------------------------------------------

function missing() {
  const p = current();
  if (!p || !status) return [];
  return p.ref.includes("/") ? status.arms.find((a) => a.id === $("l-arm").value)?.missing_keys || [] : status.treasury.missing_keys;
}

function controls() {
  const live = state.mode === "live", busy = state.busy, p = current();
  document.querySelectorAll("#l-mode button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.m === state.mode)));
  document.querySelectorAll("#l-mode button").forEach((b) => (b.disabled = busy));
  $("l-speed").hidden = live;
  const treasury = p && !p.ref.includes("/");
  $("l-arm-l").hidden = !!treasury;
  $("l-page").disabled = $("l-filter").disabled = $("l-arm").disabled = busy;
  $("l-stop").hidden = !busy;
  const lack = live ? missing() : [];
  const go = $("l-go");
  go.textContent = busy ? "Reading…" : live ? "Read live" : "Replay";
  go.disabled = busy || !p || !!lack.length || (!live && !status?.replay.available);
  let note = "";
  if (!status) note = "Asking the local server…";
  else if (!pages.size) note = "No development page is on this machine yet. The Treasury Bulletin scans come from uv run python -m archivist.ingest.fraser --source treasury; the synthetic pages are rebuilt into data/dev/images/ by uv run python -m archivist.replay.";
  else if (live && lack.length) note = `Live calls need ${lack.join(" and ")}: set it in your environment or in .env, restart the app, or switch to Replay.`;
  else if (!live && !status.replay.available) note = "Replay plays answers from cache/, and nothing is cached on this machine yet. Read a page with Live calls first.";
  else if (live) {
    const c = status.caps.meta, b = status.caps.baseten;
    note = `Live calls ask the Meta models and are paid for: $${c.spent.toFixed(2)} of the $${c.cap.toFixed(0)} cap spent on Meta’s API${b.spent ? `, $${b.spent.toFixed(2)} of $${b.cap.toFixed(0)} on Baseten` : ""}. Answers already in the cache are not asked again.`;
  } else note = "Replay plays answers already in the cache at the pace they were first given. No model is asked and nothing is spent. ● marks pages an earlier run read.";
  $("l-note").textContent = note;
  $("l-note").dataset.mode = state.mode;
  $("l-sub").textContent = live ? "Archivist reads the page now: every call below is a call to a Meta model, or an answer already in the cache." : "A rehearsal: the same read, played from the cache.";
}

async function refresh() {
  try {
    [status, { groups }] = await Promise.all([api.get("status"), api.get("pages")]);
  } catch (e) {
    status = null;
    $("l-note").textContent = `The local server did not answer: ${e.message}`;
    return;
  }
  pages = new Map(groups.flatMap((g) => g.pages.map((p) => [p.ref, p])));
  arms();
  fillPages();
  await pick();
  controls();
  if (status.running && !state.busy) attach(status.running);
}

// --- a read -------------------------------------------------------------------------------------

function reset() {
  clearInterval(ticker);
  source?.close();
  R = { id: null, mode: state.mode, nodes: new Map(), calls: new Map(), sam: [], t0: performance.now(), n: { live: 0, cache: 0, failed: 0, cost: 0 }, reread: { done: 0, total: 0 }, values: 0, names: {}, ended: false, last: -1, quiet: false };
  $("l-steps").innerHTML = STEPS.map(([k, t, role]) => `<li data-k="${k}" data-e="${role ? ROLE_E[role] : "code"}"><b>${t}</b><span>${role ? "A model" : "Plain code"}</span></li>`).join("");
  $("l-calls").innerHTML = "";
  $("l-tally").textContent = "none yet";
  $("l-stage").textContent = "Starting";
  $("l-bar").style.width = "0";
  if (pv) pv.ov.replaceChildren(), pv.ovh.replaceChildren();
}

async function go() {
  const p = current();
  if (!p || state.busy) return;
  try {
    sessionStorage.setItem("archivist-live-arm", $("l-arm").value);
  } catch (e) {
    /* private mode */
  }
  const speed = +document.querySelector("#l-speed [aria-pressed=true]")?.dataset.s || 1;
  let started;
  try {
    started = await api.post("read", { page: p.ref, mode: state.mode, arm: $("l-arm").value, speed });
  } catch (e) {
    $("l-note").textContent = e.message;
    $("l-note").dataset.mode = "error";
    return;
  }
  attach(started.session);
}

async function attach(id) {
  const body = await api.get(`session/${id}`).catch(() => null);
  if (!body) return;
  const first = body.events[0];
  if (first) await showPageFor(first.page);
  reset();
  // The steps and the panels come up to the top of the window, so the calls are in view as they happen.
  $("l-steps").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
  setTimeout(fitSide, reduced ? 50 : 700);
  R.quiet = true; // what already happened is drawn at once
  for (const e of body.events) apply(e);
  R.quiet = false;
  if (R.ended) return finish();
  source = new EventSource(`${apiBase()}events/${id}?after=${R.last}`);
  source.onmessage = (m) => {
    const e = JSON.parse(m.data);
    if (e.seq > R.last) apply(e);
    if (R.ended) {
      source.close();
      finish();
    }
  };
}

async function showPageFor(ref) {
  if (page?.ref === ref && pv) return;
  const info = await api.get(`page?ref=${encodeURIComponent(ref)}`).catch(() => null);
  if (info) showPage(info);
}

function finish() {
  set({ busy: false });
  controls();
  refreshStatus();
}
async function refreshStatus() {
  status = await api.get("status").catch(() => status);
  controls();
}

// --- the stream ---------------------------------------------------------------------------------

const rect = (box, cls) => {
  const r = document.createElementNS(SVG, "rect");
  r.setAttribute("class", `wbx ${cls}`);
  place(r, box);
  r.setAttribute("rx", 3);
  pv.ov.appendChild(r);
  return r;
};
const place = (r, b) => {
  r.setAttribute("x", b.x0);
  r.setAttribute("y", b.y0);
  r.setAttribute("width", b.x1 - b.x0);
  r.setAttribute("height", b.y1 - b.y0);
};

const WHAT = {
  recognise: (m) => `${m("extractor")} is asked what kind of page this is.`,
  read: (m) => `${m("extractor")} reads every value on the page and says where each one is.`,
  snap: () => "Plain code moves each box onto the printed ink.",
  sam: (m) => `${m("segmenter")} looks for stamps and stains that cover a value.`,
  blind: (m) => `${m("rereader")} reads each value again, one cell at a time, without seeing the first answer.`,
  rules: () => "Plain code checks the values against the page’s own arithmetic.",
  decide: () => "Every value is accepted, or sent to a person.",
};
const model = (role) => R.names[role] || "A model";

function now(step, extra = "") {
  const t = TITLE[step] || "Done";
  $("l-now").innerHTML = `<h3>${esc(t)}</h3><p class="sub" style="margin:0">${esc(WHAT[step]?.(model) || "")}</p>${extra}`;
}

function tally() {
  const n = R.n, sec = ((performance.now() - R.t0) / 1000).toFixed(1);
  const calls = n.live + n.cache + n.failed;
  $("l-tally").textContent = calls ? `${calls} ${calls === 1 ? "call" : "calls"} · ${n.live} live · ${n.cache} cache · ${usd(n.cost)}` : "none yet";
  $("l-bar").style.width = R.reread.total ? `${Math.min(100, (R.reread.done / R.reread.total) * 100)}%` : "0";
  return sec;
}

function callRow(e) {
  const li = document.createElement("li");
  li.className = "lcall run";
  li.dataset.id = e.id;
  li.dataset.e = ROLE_E[e.role] || "spark";
  li.innerHTML = `<span class="lc-src">${R?.mode === "replay" ? "Playing" : "Asking"}</span><div class="lc-main"><b>${esc(e.model)}</b><span>${esc(TITLE[e.step] || e.role)}${e.detail ? ` · “${esc(e.detail)}”` : ""}</span></div><span class="lc-t">0.0 s</span><div class="lc-meta">${esc(e.backend)} · ${esc(e.model_id)}</div>`;
  li.title = `${e.model_id} on ${e.backend}`;
  li.dataset.t0 = String(performance.now());
  return li;
}

function callDone(e) {
  const li = R.calls.get(e.id) || $("l-calls").appendChild(callRow(e));
  R.calls.set(e.id, li);
  li.classList.remove("run");
  const src = !e.ok ? "failed" : e.source;
  li.classList.add(src);
  li.querySelector(".lc-src").textContent = { live: "Live", cache: "Cache", failed: "Failed" }[src];
  const t = li.querySelector(".lc-t");
  // A live call shows how long it took; a cache hit never asked a model, so it shows only how long
  // the answer took when it was first asked, as "was ...".
  t.textContent = e.latency_ms == null ? "—" : e.source === "cache" ? `was ${ms(e.latency_ms)}` : ms(e.latency_ms);
  t.classList.toggle("was", e.source === "cache");
  t.title = { measured: "how long the call took", recorded: "how long it took when it was first asked", nominal: "no timing was recorded; played at a stand-in pace", none: "no timing was recorded" }[e.latency_of] || "";
  const meta = li.querySelector(".lc-meta");
  if (!e.ok) meta.textContent = e.error || "the call failed";
  else if (e.role === "segmenter") meta.textContent = `one image · ${e.source === "live" ? usd(e.cost_usd) : `not charged (cached; ${usd(e.cost_full_usd)} when asked)`}`;
  else meta.textContent = `${int(e.input_tokens)} in · ${int(e.output_tokens)} out · ${e.source === "live" ? usd(e.cost_usd) : `not charged (cached; ${usd(e.cost_full_usd)} when asked)`}`;
  const list = $("l-calls");
  if (list.scrollHeight - list.scrollTop - list.clientHeight < 80) list.scrollTop = list.scrollHeight;
  if (e.step === "blind") R.reread.done++;
}

function apply(e) {
  R.last = e.seq;
  switch (e.type) {
    case "session": {
      R.id = e.session_id;
      R.mode = e.mode;
      R.page = e.page;
      R.names = Object.fromEntries(e.models.map((m) => [m.role, m.name]));
      set({ mode: e.mode, busy: true });
      controls();
      document.querySelectorAll("#l-steps li").forEach((li) => {
        const role = STEPS.find(([k]) => k === li.dataset.k)[2];
        if (role) li.querySelector("span").textContent = R.names[role];
      });
      $("l-now").innerHTML = `<h3>${e.mode === "live" ? "Reading live" : "Replaying"}</h3><p class="sub" style="margin:0">${esc(e.models.map((m) => m.name).filter((n, i, a) => a.indexOf(n) === i).join(", "))}${e.mode === "replay" ? `, played from the cache${e.speed > 1 ? ` at ${e.speed}×` : ""}` : ""}.</p>`;
      ticker = setInterval(() => {
        document.querySelectorAll("#l-calls .lcall.run").forEach((li) => (li.querySelector(".lc-t").textContent = ms(performance.now() - +li.dataset.t0)));
        if (R && !R.ended) tally();
      }, 100);
      break;
    }
    case "step": {
      const li = document.querySelector(`#l-steps li[data-k="${e.step}"]`);
      if (e.state === "start") {
        document.querySelectorAll("#l-steps li.on").forEach((x) => x.classList.remove("on"));
        li.classList.add("on");
        $("l-stage").textContent = TITLE[e.step];
        now(e.step);
        if (e.step === "sam" && !R.quiet && !reduced && pv) {
          const sc = $("lscan");
          sc.style.setProperty("--wh", `${stage().clientHeight}px`);
          sc.classList.remove("on");
          void sc.offsetWidth;
          sc.classList.add("on");
        }
      } else if (e.state === "done") {
        li.classList.remove("on");
        li.classList.add("done");
      }
      if (e.state !== "start" && Object.keys(e.facts || {}).length) facts(e);
      break;
    }
    case "call_start": {
      const li = callRow(e);
      R.calls.set(e.id, li);
      $("l-calls").appendChild(li);
      $("l-calls").scrollTop = $("l-calls").scrollHeight;
      break;
    }
    case "call": {
      if (e.ok) {
        R.n[e.source]++;
        R.n.cost += e.cost_usd;
      } else R.n.failed++;
      callDone(e);
      tally();
      break;
    }
    case "values": {
      R.values = e.count;
      R.reread.total = e.to_reread;
      e.fields.forEach((f, i) => {
        if (!f.box || !pv) return;
        const r = rect(f.box, "raw new");
        r.style.animationDelay = `${R.quiet ? 0 : Math.min(i, 70) * 14}ms`;
        R.nodes.set(f.field_id, { r, f });
      });
      now("read", `<dl class="wdl" style="margin-top:10px"><dt>Values</dt><dd class="mono">${int(e.count)}</dd><dt>Cited as</dt><dd>${esc(e.cited_as)}</dd></dl>`);
      break;
    }
    case "boxes": {
      for (const [id, b] of Object.entries(e.moved)) {
        const n = R.nodes.get(id);
        if (n && b) {
          place(n.r, b);
          n.r.classList.add("snap");
        }
      }
      break;
    }
    case "detections": {
      if (!pv) break;
      for (const g of e.regions) {
        const { rect: r } = pv.detection({ label: g.label, box: g.box }, { label: false });
        r.classList.add("wsam", "hit");
        R.sam.push(r);
      }
      break;
    }
    case "verdicts": {
      for (const v of e.fields) {
        const n = R.nodes.get(v.field_id);
        if (!n) continue;
        n.r.classList.remove("raw", "snap", "new");
        n.r.classList.add(v.status === "accepted" ? "v-ok" : v.status === "review" ? "v-review" : "v-none");
      }
      break;
    }
    case "done":
      R.ended = true;
      R.done = e;
      clearInterval(ticker);
      R.runId = e.run_id;
      R.pageId = e.page_id;
      summary(e);
      break;
    case "error":
      R.ended = true;
      R.failed = e;
      clearInterval(ticker);
      $("l-stage").textContent = e.kind === "stopped" ? "Stopped" : "Stopped with an error";
      $("l-now").innerHTML = `<h3>${e.kind === "stopped" ? "Stopped" : e.kind === "not_cached" ? "Not in the cache" : "The read did not finish"}</h3><p class="sub" style="margin:0">${esc(e.message)}</p>`;
      tally();
      break;
  }
}

function facts(e) {
  const f = e.facts, bits = [];
  if (e.step === "recognise" && f.doc_type) bits.push(["Recognised as", f.doc_type.replace(/_/g, " ")], ...(f.title_confirmed == null ? [] : [["Printed title", f.title_confirmed ? "matches an approved title" : "does not match an approved title"]]));
  if (e.step === "snap") bits.push(["Boxes", `${int(f.boxes || 0)}, ${int(f.moved || 0)} moved`]);
  if (e.step === "sam") bits.push(["Covered ink", f.detections ? `${f.detections} found, over ${f.values_covered} values` : "none found"]);
  if (e.step === "blind") bits.push(["Second reads", `${int(f.agree || 0)} agree, ${int(f.disagree || 0)} differ`]);
  if (e.step === "rules") bits.push(["Rules", f.flagged ? `${f.flagged} values flagged` : "no value flagged"]);
  if (e.step === "decide") bits.push(["Decided", `${int(f.accepted || 0)} verified, ${int(f.review || 0)} to a person`]);
  if (!bits.length) return;
  const extra = `<dl class="wdl" style="margin-top:10px">${bits.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  now(e.step, extra);
}

function summary(e) {
  const t = e.totals, secs = t.elapsed_s;
  $("l-stage").textContent = "Done";
  document.querySelectorAll("#l-steps li").forEach((li) => (li.classList.remove("on"), li.classList.add("done")));
  tally();
  if (e.outcome !== "read") {
    $("l-now").innerHTML = `<h3>${e.outcome === "unsupported" ? "Not one of the supported pages" : "No values were read"}</h3><p class="sub" style="margin:0">${e.outcome === "unsupported" ? "The model recognised the page as none of the document types Archivist is set up to read, so nothing was extracted. It never forces a page into a type." : "The page was recognised but no value could be read from it."}</p>`;
    return;
  }
  const live = R.mode === "live";
  const auto = sessionStorage.getItem(AUTO) !== "0";
  $("l-now").innerHTML = `<h3>Read in ${secs.toFixed(1)} s</h3>
    <p class="sub" style="margin:0">${t.calls} calls: ${t.live} ${live ? "to the models" : "live"}, ${t.cache} answered from the cache. ${live ? `Spent ${usd(t.cost_usd)}.` : "Nothing was asked and nothing was spent."}</p>
    <div class="wtiers"><div><b>${int(e.accepted)}</b><span>Verified</span></div><div><b>${int(e.review)}</b><span>Sent to a person</span></div><div><b>${live ? usd(t.cost_usd) : "$0"}</b><span>Spent</span></div></div>
    <div class="lactions"><button class="primary" id="l-open">Open the document</button>${e.review ? `<button id="l-review">Review the ${e.review} open ${e.review === 1 ? "item" : "items"}</button>` : ""}<button id="l-again">Read another page</button></div>
    <label class="lauto"><input type="checkbox" id="l-auto"${auto ? " checked" : ""}> Open the document when it finishes</label>`;
  $("l-open").onclick = () => openRun("doc");
  if ($("l-review")) $("l-review").onclick = () => openRun("review");
  $("l-again").onclick = () => again();
  $("l-auto").onchange = (ev) => sessionStorage.setItem(AUTO, ev.target.checked ? "1" : "0");
  if (auto && !R.quiet && location.hash.startsWith("#live")) R.opening = setTimeout(() => $("l-auto")?.checked && openRun("doc"), reduced ? 600 : 2600);
}

function again() {
  clearTimeout(R?.opening);
  reset();
  showPage(page);
  $("l-now").innerHTML = "";
  controls();
}

// The normal document view and review queue, on the bundle this read wrote.
function openRun(view) {
  clearTimeout(R.opening);
  const u = new URL(location.href);
  u.search = "";
  u.searchParams.set("run", R.runId);
  u.hash = `${view}-${R.pageId}`;
  location.href = u.toString();
}

// --- the view contract ---------------------------------------------------------------------------

export function init() {
  $("l-steps").innerHTML = STEPS.map(([k, t, role]) => `<li data-k="${k}" data-e="${role ? ROLE_E[role] : "code"}"><b>${t}</b><span>${role ? "A model" : "Plain code"}</span></li>`).join("");
  $("l-now").innerHTML = `<h3>Choose a page</h3><p class="sub" style="margin:0">Pick a development page, then start a read. The seven steps light up here as Archivist works, and each call to a model is listed beside the page.</p>`;
  $("l-mode").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-m]");
    if (b && !state.busy) {
      set({ mode: b.dataset.m });
      controls();
    }
  });
  $("l-speed").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-s]");
    if (b) $("l-speed").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
  $("l-page").addEventListener("change", pick);
  $("l-arm").addEventListener("change", controls);
  $("l-filter").addEventListener("input", () => (fillPages(), pick()));
  $("l-go").addEventListener("click", go);
  $("l-stop").addEventListener("click", () => R?.id && api.post("cancel", { session: R.id }).catch(() => {}));
  onChange(controls);
}

// The side column is as tall as what is left of the window below where it starts (or below the header
// once it has stuck there), so the call list is never pushed out of sight.
function fitSide() {
  const side = $("l-side");
  if (!side || $("v-live").hidden || innerWidth <= 1180) return side && (side.style.maxHeight = "");
  side.style.maxHeight = `${Math.max(320, innerHeight - Math.max(side.getBoundingClientRect().top, 70) - 16)}px`;
}

export function scroll() {
  fitSide();
}

export function enter() {
  if (!status) refresh();
  else if (!state.busy) refreshStatus();
  frame(() => {
    fitSide();
    if (pv && !$("v-live").hidden) noAnim(pv.sheet, () => pv.camera({ fit: true }));
  });
}
export function resize() {
  fitSide();
  if (pv && !$("v-live").hidden) pv.camera({ fit: true });
}
export function leave() {}
