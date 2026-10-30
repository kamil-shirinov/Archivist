// Document types: what Archivist can read, the rules that must hold on each, the evidence each rule
// held on when its template was tested, and who approved it. From the bundle's doc_types, which the
// exporter reads from the approved template files and their evidence.

import { S } from "../store.js";
import { $, esc, int, toast } from "../util.js";
import { longDate } from "../util.js";

const day = (iso) => longDate(new Date(`${iso}T00:00:00Z`));
const short = (sha) => `${sha.slice(0, 8)}…`;
const OUTCOME = { holds: ["st-ok", "Holds"], "sometimes fails": ["st-review", "Sometimes fails"], rejected: ["st-docerr", "Rejected"], untested: ["st-unread", "Untested"] };

function evidenceCell(rule) {
  const e = rule.evidence;
  if (!e) return '<span class="m">Measured in the accuracy report</span>';
  const [cls, label] = OUTCOME[e.outcome] || ["st-unread", e.outcome];
  const why = Object.entries(e.not_evaluated).map(([k, v]) => `${int(v)} ${k}`).join("; ");
  const places = (n) => `${int(n)} ${n === 1 ? "place" : "places"}`;
  return `<span class="st ${cls}">${label}</span> Held in ${int(e.held)} of ${places(e.evaluated)} where every cell was read twice and agreed${e.failed ? `, failed in ${int(e.failed)}` : ""}. It applies in ${places(e.applies)} on the tested pages${why ? `; the rest weren’t evaluated: ${esc(why)}` : ""}.`;
}

function rulesTable(t) {
  return `<div class="tw"><table class="tbl"><thead><tr><th>Rule</th>${t.kind === "template" ? "<th>Equation</th>" : ""}<th>${t.kind === "template" ? "Evidence it held on" : "Where it is measured"}</th></tr></thead><tbody>${t.rules
    .map(
      (r) =>
        `<tr><td class="w"><b>${esc(r.label)}</b>${r.for_each ? `<div class="m">for each ${esc(r.for_each)}</div>` : ""}</td>${t.kind === "template" ? `<td class="w mono" style="font-size:12px">${esc(r.equation || "")}</td>` : ""}<td class="w">${evidenceCell(r)}</td></tr>`
    )
    .join("")}</tbody></table></div>`;
}

function approval(a) {
  const rows = [
    ["Approved by", `${esc(a.approved_by)}, on ${day(a.approved_on)}, rule by rule, on the evidence below`],
    ["Drafted by", `${esc(a.drafted_by)}, on ${day(a.drafted_on)}, from ${a.drafted_from.map(esc).join(", ")}`],
  ];
  if (a.tested_on) rows.push(["Tested", `${day(a.tested_on)}, on ${a.tested_pages.map(esc).join(", ")}: each page read twice, every rule evaluated on the cells whose two reads agree`]);
  if (a.evidence_file) rows.push(["Evidence file", `<span class="mono">${esc(a.evidence_file)}</span>, sha256 <span class="mono">${esc(short(a.evidence_sha256))}</span>, recorded at approval: the template stops loading if the file changes`]);
  if (a.dropped.length) rows.push(["Left out at approval", a.dropped.map(esc).join("; ")]);
  return `<dl class="integrity" style="margin-top:12px;grid-template-columns:minmax(0,1fr)">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
}

function card(t, open) {
  const status =
    t.kind === "built-in" ? '<span class="st st-ok">Built in</span>' : `<span class="st st-ok">Approved</span>`;
  const used = t.enabled ? `Read in this run: ${int(t.pages)} ${t.pages === 1 ? "page" : "pages"}` : "Not read in this run";
  const who = t.approval ? ` Approved by ${esc(t.approval.approved_by)} on ${day(t.approval.approved_on)}.` : "";
  const cols = t.columns.map((c) => `<span class="tag" title="${esc(c.kind)}">${esc(c.printed)}</span>`).join(" ");
  return `<details class="panel type-d"${open ? " open" : ""}><summary><div><h2>${esc(t.title)}</h2><p>${esc(t.description.replace(/\.$/, ""))}.${who}</p></div><div class="tys">${status}<span class="m">${used}</span></div></summary>
    <div class="type-b">
      <p class="cap" style="margin:0 0 6px">What it reads${t.unit ? `, figures in ${esc(t.unit)}` : ""}: ${esc(t.rows)}</p>
      <div class="tags">${cols}</div>
      <h3 class="ty-h">Rules</h3>${rulesTable(t)}
      ${t.approval ? `<h3 class="ty-h">Approval</h3>${approval(t.approval)}` : '<p class="fine">A built-in type is defined in code, not in a template file; its checks are measured on the synthetic test set in the accuracy report.</p>'}
    </div></details>`;
}

export function init() {
  $("ty-list").addEventListener("click", (e) => {
    if (e.target.closest("#draft-type")) toast("Drafting a new type from sample pages happens in the local app, where the models run.");
  });
}

export function enter() {
  const all = [...S.bundle.doc_types];
  $("ty-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<span>Document types</span>`;
  const tpl = all.filter((t) => t.kind === "template").length;
  $("ty-sub").textContent = `What Archivist knows how to read: ${all.length - tpl} built in and ${tpl} approved from sample pages, and the rules that must hold on each. Only approved templates are listed; a draft is never read.`;
  const first = all.find((t) => t.enabled && t.pages) || all[0];
  $("ty-list").innerHTML =
    all.map((t) => card(t, t.name === first.name)).join("") +
    `<div class="panel type new"><div><h2>New type from sample pages</h2><p>Upload two or three sample pages. Muse Spark drafts the fields and rules; you approve them before anything is read.</p></div><button id="draft-type">Draft a new type</button></div>`;
}
