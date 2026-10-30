// One document: its page beside the record read from it, with a thread from a value to where it sits
// on the page, and, on the other tab, how it was read, step by step.

import { S, LBL, statusOf, fieldLabel, rulesOf, reasonSentence, docStats, heading, subtitle } from "../store.js";
import { PageView } from "../pageview.js";
import { wire, hideWire, follow, noAnim } from "../wire.js";
import { $, esc, fmtDate, frame } from "../util.js";
import { runFacts } from "./overview.js";

let pageId = null, doc = null, page = null, fields = [], pv = null;
let pinned = null, hot = null, tab = "page";

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const shown = (f) => (S.answers[f.field_id] ? S.answers[f.field_id].val : f.value);
const title = (id) => S.docById.get(id)?.title || id;

export function checkedBy(f) {
  const a = S.answers[f.field_id];
  if (a) return a.st === "you" ? "Reviewer, then the rules" : a.st === "docerr" ? "Reviewer; the page doesn’t add up" : "Reviewer; inferred, not read";
  if (f.status === "accepted") {
    const labels = [...new Set(rulesOf(f).filter((r) => r.ok).map((r) => r.label))];
    return cap([...labels.map((l) => l.toLowerCase()), "second read"].join(", "));
  }
  return cap(f.reasons.map(reasonSentence).join("; ") || "Sent to a person");
}

function vcell(f, cls = "") {
  if (!f) return `<td class="${cls}"></td>`;
  const st = statusOf(f), v = shown(f);
  if (!v && st === "ok") return `<td class="${cls}"></td>`;
  return `<td class="v vs-${st} ${cls}" data-field="${esc(f.field_id)}" tabindex="0" title="${LBL[st]}">${esc(v || "—")}</td>`;
}
const hcell = (f) => {
  if (!f) return "";
  const st = statusOf(f);
  return `<span><span class="k">${esc(fieldLabel(f))}</span><span class="v vs-${st}" data-field="${esc(f.field_id)}" tabindex="0" title="${LBL[st]}">${esc(shown(f) || "—")}</span></span>`;
};

const NUMERIC = new Set(["money", "count", "percent"]);

// A printed table as a grid of its cells: a row for each row the page holds, a column for each the
// type names, every cell a value that can be pointed at.
function tableHTML() {
  const type = S.docTypes.get(doc.doc_type), by = new Map(fields.map((f) => [`${f.row}|${f.name}`, f]));
  if (fields.every((f) => f.value == null))
    return `<p class="why">None of this page’s ${fields.length} cells was read: the run recorded no value for any of them, so there is no record to show.</p>`;
  const rows = [...new Set(fields.map((f) => f.row))].filter((r) => type.columns.some((c) => {
    const f = by.get(`${r}|${c.key}`);
    return f && (f.value || statusOf(f) !== "ok");
  }));
  const head = type.columns.map((c) => `<th class="${NUMERIC.has(c.kind) ? "r" : ""}" title="${esc(c.printed)}">${esc(c.printed)}</th>`).join("");
  const body = rows
    .map((r, i) => `<tr><td class="ln">${i + 1}</td>${type.columns.map((c) => vcell(by.get(`${r}|${c.key}`), NUMERIC.has(c.kind) ? "r" : "pt")).join("")}</tr>`)
    .join("");
  return `<p class="cap" style="margin:0 0 8px">${esc(type.rows)}; figures in ${esc(type.unit)}.</p><div class="rwrap tall"><table class="rec2"><thead><tr><th>#</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function recordHTML() {
  if (doc.kind === "table") return tableHTML();
  const by = new Map(fields.map((f) => [`${f.line ?? ""}|${f.name}`, f]));
  const get = (line, name) => by.get(`${line ?? ""}|${name}`);
  if (doc.kind === "ledger") {
    const lines = [...new Set(fields.filter((f) => f.line != null).map((f) => f.line))].sort((a, b) => a - b);
    const rows =
      `<tr class="fwd"><td></td><td></td><td>Brought forward</td><td></td><td></td>${vcell(get(null, "brought_forward"), "r")}</tr>` +
      lines
        .map((n) => `<tr><td class="ln">${n}</td>${vcell(get(n, "date"))}${vcell(get(n, "description"), "pt")}${vcell(get(n, "debit"), "r")}${vcell(get(n, "credit"), "r")}${vcell(get(n, "balance"), "r")}</tr>`)
        .join("") +
      `<tr class="fwd"><td></td><td></td><td>Carried forward</td><td></td><td></td>${vcell(get(null, "carried_forward"), "r")}</tr>`;
    return `<div class="rhdr">${["account_no", "holder", "sheet_no"].map((n) => hcell(get(null, n))).join("")}</div><div class="rwrap"><table class="rec2"><thead><tr><th>Line</th><th>Date</th><th>Description</th><th class="r">Debit</th><th class="r">Credit</th><th class="r">Balance</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  const rows = fields.map((f) => `<tr><td>${esc(fieldLabel(f))}</td>${vcell(f)}<td class="hw">${esc(checkedBy(f))}</td></tr>`).join("");
  return `<div class="rwrap"><table class="rec2"><thead><tr><th>Field</th><th>Value</th><th>Checked by</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

// --- the page and its marks ----------------------------------------------------------------------

function statusMarks() {
  for (const f of fields) {
    const st = statusOf(f);
    if (st === "ok" || !f.box) continue;
    if (st === "you") pv.tick(f);
    else pv.loop(f, st === "unread" ? "grey" : "red");
  }
  for (const d of page.sam) pv.detection(d);
}

function dWire() {
  if (!hot || $("v-doc").hidden || tab !== "page") return hideWire($("dthread"));
  const rc = $("drecord").querySelector(`[data-field="${CSS.escape(hot)}"]`), to = pv.target(hot);
  if (!rc || !to) return hideWire($("dthread"));
  const bx = (rc.closest(".rwrap") || rc.closest(".rhdr") || rc).getBoundingClientRect(), c = rc.getBoundingClientRect();
  const from = { getBoundingClientRect: () => ({ left: bx.left, right: bx.left, top: c.top, bottom: c.bottom, height: c.height, width: 0 }) };
  wire($("dthread"), $("twin"), from, to, $("dpaper"), "l");
}

function setHot(id) {
  if (hot === id) return;
  if (hot) {
    const rc = $("drecord").querySelector(`[data-field="${CSS.escape(hot)}"]`);
    if (rc) {
      rc.classList.remove("hot");
      rc.closest("tr")?.classList.remove("hotrow");
    }
    pv.clearOverlay(`[data-hl="${CSS.escape(hot)}"]`);
    pv.clearOverlay(".pen.hot");
  }
  hot = null;
  hideWire($("dthread"));
  if (!id) return;
  const f = S.fieldById.get(id), rc = $("drecord").querySelector(`[data-field="${CSS.escape(id)}"]`);
  if (!f || !rc) return;
  hot = id;
  rc.classList.add("hot");
  rc.closest("tr")?.classList.add("hotrow");
  pv.highlight(f);
  const m = pv.marks.get(id);
  if (!(m && m.stat)) pv.loop(f, "gold", { draw: true, hot: true });
  follow(dWire, 600);
}

// --- the facts under the page ---------------------------------------------------------------------

function info() {
  const s = docStats(pageId), open = s.open, exc = s.exc;
  const cond = S.condition(pageId);
  $("dd-info").innerHTML = [
    ["Type", doc.typeLabel],
    ["Page", page.page_id],
    cond ? ["Condition", cond] : ["Scan", `${page.width} × ${page.height} px`],
    ["Values", `${s.values} read, ${s.values - open - exc} verified, ${open} open, ${exc} exceptions`],
  ]
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`)
    .join("");
}

const lineOf = (id) => /^L:[^:]+:(\d+):/.exec(id || "")?.[1];
const val = (id) => S.fieldById.get(id)?.value;

// For a printed table there are no links to other pages: what it has is rules, each applied wherever
// the page's cells allow, so the section lists them, how often each held and where one failed.
function rulesSection() {
  $("dd-links-h").textContent = "Rules";
  const by = new Map();
  for (const r of S.bundle.rule_results.filter((x) => x.page_id === pageId)) {
    if (!by.has(r.rule)) by.set(r.rule, { label: r.label, held: 0, failed: [] });
    const e = by.get(r.rule);
    if (r.ok) e.held++;
    else e.failed.push(r);
  }
  $("dd-links").innerHTML = by.size
    ? [...by.values()]
        .map((e) => {
          const total = e.held + e.failed.length;
          const chip = e.failed.length ? '<span class="bad">Failed</span>' : '<span class="ok">Holds</span>';
          return `<div class="lnk ${e.failed.length ? "bad" : ""}"><span class="k">${esc(e.label)}</span>Held in ${e.held} of ${total} places where every cell was read. ${chip}${e.failed.map((f) => `<span class="t">${esc(f.equation || f.detail || "")}</span>`).join("")}</div>`;
        })
        .join("")
    : `<div class="lnk mute"><span class="k">No rules applied</span>No rule could be applied to this page: too few of its cells were read.</div>`;
}

function connections() {
  $("dd-links-h").textContent = "Connections";
  if (doc.kind === "table") return rulesSection();
  const out = [];
  const add = (k, text, agrees, note) => out.push({ k, text, agrees, note });
  for (const l of S.bundle.links) {
    if (l.kind === "sheet_sheet" && (l.source === pageId || l.target === pageId)) {
      const from = l.source === pageId;
      const parts = [];
      if (l.checks.carry != null) parts.push(`${title(l.source)} carries forward ${val(l.source_fields[0]) || "—"}; ${title(l.target)} brings forward ${val(l.target_fields[0]) || "—"}.`);
      if (l.checks.dates != null) parts.push(l.checks.dates ? "Its dates carry on in order." : "Its dates go backwards across the two sheets.");
      add(from ? `To ${title(l.target).toLowerCase()}` : `From ${title(l.source).toLowerCase()}`, parts.join(" ") || "Not compared.", l.agrees, l.note);
    } else if (l.kind === "memo_line" && (l.source === pageId || l.target === pageId)) {
      const memo = l.source, mdoc = S.docById.get(memo);
      if (l.target && l.source === pageId) {
        const line = lineOf(l.target_fields[1]);
        const parts = [`The ledger shows ${val(l.target_fields[2]) || "no debit"} on ${fmtDate(val(l.target_fields[1]))}.`];
        const amount = S.fieldById.get(l.source_fields[2])?.value;
        if (l.checks.amount != null) parts.push(l.checks.amount ? "The memo pays that amount." : `The memo pays ${amount}, not that.`);
        if (l.checks.date != null) parts.push(l.checks.date ? "Its date is in step with the posting." : `It is dated ${fmtDate(val(l.source_fields[3]))}, out of step with the posting.`);
        add(`${title(l.target)}, line ${Number(line)}`, parts.join(" "), l.agrees, l.note);
      } else if (l.target === pageId) {
        const line = lineOf(l.target_fields[1]);
        add(`${mdoc ? mdoc.title : memo}`, `Pays line ${Number(line)}, ${val(l.source_fields[2]) || "—"}, to ${val(`M:${memo}:counterparty`) || "—"}.`, l.agrees, l.note);
      } else add(`Memo reference`, l.note || "The memo’s ledger line wasn’t found.", l.agrees, null);
    } else if (l.kind === "card_account" && l.source === pageId) {
      add(`Account ${l.target ?? "unknown"}`, l.note || `This card reads the account’s number.`, l.agrees, null);
    }
  }
  $("dd-links").innerHTML = out.length
    ? out
        .map((c) => {
          const cls = c.agrees === true ? "" : c.agrees === false ? "bad" : "mute";
          const chip = c.agrees === true ? '<span class="ok">Agrees</span>' : c.agrees === false ? '<span class="bad">Doesn’t agree</span>' : '<span class="mute">Not compared</span>';
          return `<div class="lnk ${cls}"><span class="k">${esc(c.k)}</span>${esc(c.text)} ${chip}${c.note && !c.text.includes(c.note) ? `<span class="t">${esc(c.note)}</span>` : ""}</div>`;
        })
        .join("")
    : `<div class="lnk mute"><span class="k">No connections</span>Nothing in the run links to this page.</div>`;
}

// --- how it was read --------------------------------------------------------------------------------

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
function stepView(s) {
  const f = s.facts, e = s.key === "sam" ? "sam" : s.model ? "spark" : "code";
  const type = doc.kind === "ledger" ? "ledger card" : doc.kind === "memo" ? "payment memo" : page.doc_type;
  switch (s.key) {
    case "recognise":
      return { e, b: "Recognised the page", p: `A ${type}, matching a registered document type.` };
    case "read":
      return { e, b: `Read and cited ${plural(f.values, "value", "values")}`, p: `Each value read together with the box it came from on the page${f.not_read ? `, ${f.not_read} of them not read at all` : ""}.` };
    case "snap":
      return { e, b: "Snapped every box to the ink", p: `${f.moved} of ${plural(f.boxes, "box", "boxes")} moved, so each citation points at the printed figures themselves.` };
    case "sam":
      return {
        e,
        b: "Looked for covered ink",
        p: f.detections
          ? `Found ${plural(f.stamps, "stamp", "stamps")} and ${plural(f.stains, "stain", "stains")} over values; ${plural(f.values_covered, "value is", "values are")} under them.`
          : "Nothing covering the ink.",
      };
    case "blind": {
      const p = [`${f.agree} agreed with the first read`, `${f.disagree} didn’t`];
      if (f.illegible) p.push(`${f.illegible} couldn’t be made out`);
      if (f.failed) p.push(`${f.failed} couldn’t be read again`);
      return { e, b: "Read every value again, blind", p: `${p.join(", ")}.` };
    }
    case "rules":
      return { e, b: "Checked the bookkeeping rules", p: f.failed ? `${plural(f.applied, "check", "checks")}; ${f.failed} failed: ${f.failed_rules}.` : `${plural(f.applied, "check", "checks")}, and all passed.` };
    default:
      return { e, b: "Decided", p: `${f.accepted} verified, ${f.review} sent to a person${f.abstained ? `, ${f.abstained} not read` : ""}.` };
  }
}

function renderHist() {
  const f = runFacts();
  const steps = page.steps.map(stepView).map((s, i) => ({ ...s, t: `Step ${i + 1}`, w: page.steps[i].model || "Plain code" }));
  for (const field of fields) {
    const a = S.answers[field.field_id];
    if (a)
      steps.push({
        e: "person",
        t: new Date(a.t).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        b: a.st === "you" ? `Confirmed the ${fieldLabel(field).toLowerCase()}` : a.st === "docerr" ? `Raised an exception on the ${fieldLabel(field).toLowerCase()}` : `Marked the ${fieldLabel(field).toLowerCase()} not readable`,
        p: a.st === "you" ? `Saved as ${a.val}. Both reads and this answer are kept in this browser.` : a.st === "docerr" ? `Saved as printed, ${a.val}, and raised as an error in the page itself.` : "Recorded as inferred, not read.",
        w: "You",
      });
  }
  const open = docStats(pageId).open;
  if (open) steps.push({ e: "wait", t: "Now", b: "Waiting for a person", p: `${open} ${open === 1 ? "value is" : "values are"} in the review queue.`, w: "" });
  $("dh-when").textContent = f.read;
  $("dh-list").innerHTML = steps
    .map((x) => `<li data-e="${x.e}"><span class="t">${esc(x.t)}</span><span class="rail"><i></i></span><div class="b"><b>${esc(x.b)}</b>${x.w ? `<span class="hby">${esc(x.w)}</span>` : ""}<p>${esc(x.p)}</p></div></li>`)
    .join("");
  const models = [...new Set(S.bundle.run.models.map((m) => m.name))].join(" and ");
  $("dh-side").innerHTML = `<h3>Kept for good</h3><p>Every value is stored with both reads, the box it was cited from, the rules it met and the decision, so anyone can see how each one got into the database.</p><dl class="hsum"><div><dt>Time to read</dt><dd>About ${Math.round(f.seconds)} seconds a page, on average</dd></div><div><dt>Cost</dt><dd>About $${f.perPage.toFixed(3)} a page, on average</dd></div><div><dt>Models</dt><dd>${esc(models)}</dd></div></dl><button class="primary" id="dh-replay">Replay this read</button>`;
  $("dh-replay").addEventListener("click", () => (location.hash = `replay-${pageId}`));
}

// --- the view -------------------------------------------------------------------------------------

function setTab(t) {
  tab = t;
  $("dd-tabs").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tab === t)));
  $("dd-pagetab").hidden = t !== "page";
  $("dd-histtab").hidden = t !== "hist";
  if (t === "hist") {
    hideWire($("dthread"));
    renderHist();
  } else
    frame(() => {
      pv.fitWidth();
      if (pinned) setHot(pinned);
      dWire();
    });
}

function renderDoc() {
  hot = null;
  $("dd-home").textContent = S.bundle.run.collection;
  $("dd-crumb").textContent = doc.title;
  $("dd-t").textContent = heading(doc);
  $("dd-sub").textContent = subtitle(doc);
  $("drecord").innerHTML = page.doc_type === "failed" ? `<p class="why">${esc(page.failure || "This page couldn’t be read.")}</p>` : recordHTML();
  pv = new PageView($("dpaper"), page);
  statusMarks();
  info();
  connections();
  const i = S.docs.findIndex((d) => d.page_id === pageId);
  $("dd-prev").disabled = i <= 0;
  $("dd-next").disabled = i >= S.docs.length - 1;
  frame(() => {
    noAnim(pv.sheet, () => pv.fitWidth()); // a page opens where it belongs, not zooming in under the entrance
    if (pinned) setHot(pinned);
    else hideWire($("dthread"));
    if (tab === "hist") renderHist();
  });
}

const fieldFromRecord = (e) => {
  const t = e.target.closest("[data-field]");
  return t && $("drecord").contains(t) ? t.dataset.field : null;
};

export function init() {
  $("dd-prev").addEventListener("click", () => {
    const i = S.docs.findIndex((d) => d.page_id === pageId);
    if (i > 0) location.hash = `doc-${S.docs[i - 1].page_id}`;
  });
  $("dd-next").addEventListener("click", () => {
    const i = S.docs.findIndex((d) => d.page_id === pageId);
    if (i < S.docs.length - 1) location.hash = `doc-${S.docs[i + 1].page_id}`;
  });
  $("dd-tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (b) setTab(b.dataset.tab);
  });
  const rec = $("drecord"), paper = $("dpaper");
  rec.addEventListener("mouseover", (e) => {
    const id = fieldFromRecord(e);
    if (id) setHot(id);
  });
  rec.addEventListener("mouseleave", () => setHot(pinned));
  rec.addEventListener("click", (e) => {
    const id = fieldFromRecord(e);
    if (!id) return;
    pinned = pinned === id ? null : id;
    setHot(pinned || id);
  });
  rec.addEventListener("focusin", (e) => {
    const id = fieldFromRecord(e);
    if (id) setHot(id);
  });
  rec.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const id = fieldFromRecord(e);
    if (id) {
      pinned = pinned === id ? null : id;
      setHot(pinned || id);
    }
  });
  const atPoint = (e) => {
    const { x, y } = pv.toPage(e.clientX, e.clientY);
    return pv.fieldAt(x, y, fields)?.field_id || null;
  };
  paper.addEventListener("mousemove", (e) => {
    const id = atPoint(e);
    if (id && $("drecord").querySelector(`[data-field="${CSS.escape(id)}"]`)) setHot(id);
  });
  paper.addEventListener("mouseleave", () => setHot(pinned));
  paper.addEventListener("click", (e) => {
    const id = atPoint(e);
    if (!id || !$("drecord").querySelector(`[data-field="${CSS.escape(id)}"]`)) return;
    pinned = pinned === id ? null : id;
    setHot(pinned || id);
  });
}

export function enter(arg, query) {
  if (!S.docById.has(arg)) {
    location.hash = "documents";
    return;
  }
  pageId = arg;
  doc = S.docById.get(arg);
  page = S.pageById.get(arg);
  fields = S.fieldsByPage.get(arg) || [];
  pinned = query.get("pin") && S.fieldById.has(query.get("pin")) ? query.get("pin") : null;
  frame(renderDoc);
}

export function resize() {
  if (!pv) return;
  pv.fitWidth();
  dWire();
}
export const scroll = dWire;
export const entered = dWire; // the entrance is over: the thread can point at content that is no longer moving
export function leave() {
  hideWire($("dthread"));
}
