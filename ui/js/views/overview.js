// Overview: how much of the run is verified, what is open and why, how the run went, and which accounts
// have the most still to do.

import { S, accountRows, reasonLabel, totals, runWords, isOpen, statusOf } from "../store.js";
import { $, esc, int, toast } from "../util.js";

const longDate = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export function runFacts() {
  const r = S.bundle.run, v = r.verification, x = r.extraction;
  const pages = S.bundle.pages.length;
  const cost = (v.cost_usd || 0) + (x.cost_usd || 0);
  const minutes = Math.round((new Date(v.finished_at) - new Date(v.started_at)) / 60000);
  const seconds = (new Date(v.finished_at) - new Date(v.started_at)) / 1000 / pages;
  return { pages, cost, minutes, seconds, perPage: cost / pages, read: longDate(v.finished_at) };
}

function counts() {
  const n = { ledger: 0, memo: 0, other: 0 };
  for (const d of S.docs) n[d.kind]++;
  return n;
}

function render() {
  const r = S.bundle.run, t = totals(), f = runFacts(), n = counts(), w = runWords();
  $("ov-crumb").textContent = r.collection;
  const kinds = [n.ledger && `${n.ledger} ledger cards`, n.memo && `${n.memo} payment memos`, n.other && `${n.other} other pages`].filter(Boolean).join(", ");
  $("ov-sub").textContent = `${f.pages} ${w.pages}, ${kinds}. Read on ${f.read} by ${w.models}.`;
  const pct = (x) => `${(x / t.all * 100).toFixed(1)}%`;
  $("ov-kpis").innerHTML = [
    ["ok", "Values verified", pct(t.ok), `${int(t.ok)} of ${int(t.all)} values`],
    ["warn", "Open review items", int(t.open), "Values a person needs to confirm"],
    ["bad", "Exceptions", int(t.exc), "Both reads agree, yet a rule fails"],
    ["", "Documents", int(f.pages), kinds],
  ]
    .map(([c, l, v, d]) => `<div class="kpi ${c}"><div class="l">${l}</div><div class="v">${v}</div><div class="d">${d}</div></div>`)
    .join("");
  const share = (x) => `${(x / t.all * 100).toFixed(2)}%`;
  $("ov-sbar").setAttribute("aria-label", `${pct(t.ok)} verified, ${pct(t.open)} open, ${pct(t.exc)} exceptions`);
  $("ov-sbar").innerHTML = `<i style="width:${share(t.ok)};background:var(--ok)"></i><i style="width:${share(t.open)};background:var(--warn)"></i><i style="width:${share(t.exc)};background:var(--bad)"></i>`;

  // Open items by reason: how many open values each reason names (a value can have more than one).
  const by = new Map();
  for (const field of S.bundle.fields) {
    if (!isOpen(field) && statusOf(field) !== "docerr") continue;
    for (const label of new Set(field.reasons.map(reasonLabel))) by.set(label, (by.get(label) || 0) + 1);
  }
  const top = [...by].sort((a, b) => b[1] - a[1]).slice(0, 7);
  $("reasons").innerHTML = top.length
    ? top.map(([label, c]) => `<div class="reason"><span>${esc(label)}</span><span class="b"><i style="width:${(c / top[0][1]) * 100}%"></i></span><span class="n">${int(c)}</span></div>`).join("")
    : `<p style="margin:0;color:var(--ink-2)">Nothing is open.</p>`;

  const rules = new Set(S.bundle.rule_results.map((x) => x.rule));
  $("runinfo").innerHTML = [
    ["Read", `${f.read}, ${f.pages} pages in ${f.minutes} minutes`],
    ["Models", w.models],
    ["Rules applied", `${rules.size} ledger and memo rules, ${int(S.bundle.rule_results.length)} equations checked`],
    ["Cost", `$${f.cost.toFixed(2)}, about $${f.perPage.toFixed(3)} a page`],
    ["Run", `${r.run_id}, policy ${r.policy}`],
  ]
    .map(([k, v]) => `<div class="runrow"><dt>${k}</dt><dd>${esc(v)}</dd></div>`)
    .join("");

  const rows = accountRows().sort((a, b) => b.open - a.open || b.exc - a.exc);
  $("ov-all").textContent = `All ${rows.length} accounts`;
  $("ov-accts").innerHTML = rows
    .slice(0, 6)
    .map(
      (a) =>
        `<tr data-acct="${esc(a.account_no)}"><td class="id num">${esc(a.account_no)}</td><td>${esc(a.holder || "—")}</td><td class="m">${esc(a.period)}</td><td class="r">${Math.round(a.verified * 100)}%</td><td class="r">${a.open}</td><td class="r">${a.exc}</td></tr>`
    )
    .join("");
}

async function exportCsv() {
  const url = new URL(`../../../exports/${S.entry.run_id}/field_values.csv`, S.bundleUrl);
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.statusText);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await res.blob());
    a.download = `${S.entry.run_id}-field_values.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    toast("The export files aren’t part of this hosted copy. Run archivist.export.database to write them.");
  }
}

export function init() {
  $("ov-accts").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-acct]");
    if (tr) location.hash = `documents?account=${tr.dataset.acct}`;
  });
  $("ov-export").addEventListener("click", exportCsv);
}

export function enter() {
  render();
}
