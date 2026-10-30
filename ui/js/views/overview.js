// Overview: how much of the run is verified, what is open and why, how the run went, and which accounts
// have the most still to do.

import { S, accountRows, docStats, reasonLabel, totals, runWords, isOpen, statusOf } from "../store.js";
import { pagesWhat } from "../chrome.js";
import { $, esc, int, toast } from "../util.js";

const longDate = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export function runFacts() {
  const r = S.bundle.run, v = r.verification, x = r.extraction;
  const pages = S.bundle.pages.length;
  const attempted = v.counts?.pages ?? pages; // a page the run recorded nothing for is left out of the bundle
  const cost = r.extraction_run === r.run_id ? v.cost_usd || 0 : (v.cost_usd || 0) + (x.cost_usd || 0); // one record, read and verified together
  const minutes = Math.round((new Date(v.finished_at) - new Date(v.started_at)) / 60000);
  const seconds = (new Date(v.finished_at) - new Date(v.started_at)) / 1000 / attempted;
  return { pages, attempted, cost, minutes, seconds, perPage: cost / attempted, read: longDate(v.finished_at) };
}

function counts() {
  const n = { ledger: 0, memo: 0, table: 0, other: 0 };
  for (const d of S.docs) n[d.kind]++;
  return n;
}

function render() {
  const r = S.bundle.run, t = totals(), f = runFacts(), n = counts(), w = runWords();
  $("ov-crumb").textContent = r.collection;
  const kinds = [n.ledger && `${n.ledger} ledger cards`, n.memo && `${n.memo} payment memos`, n.table && `${n.table} printed ${n.table === 1 ? "table" : "tables"}`, n.other && `${n.other} other pages`].filter(Boolean).join(", ");
  const what = r.source === "synthetic" ? `${f.pages} ${pagesWhat(r).toLowerCase()}` : `${f.pages} pages of the ${r.publication ? r.publication.title : "archive"}, development pages`;
  $("ov-sub").textContent = `${what}: ${kinds}. Read on ${f.read} by ${w.models}.${r.description ? " " + r.description : ""}`;
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
    ["Read", `${f.read}, ${f.attempted === f.pages ? `${f.pages} pages` : `${f.attempted} pages, ${f.pages} kept,`} in ${f.minutes} minutes`],
    ["Models", w.models],
    ["Rules applied", `${rules.size} rules, ${int(S.bundle.rule_results.length)} equations checked`],
    ["Cost", `$${f.cost.toFixed(2)}, about $${f.perPage.toFixed(3)} a page${f.attempted === f.pages ? "" : " read"}`],
    ["Run", `${r.run_id}, policy ${r.policy}`],
  ]
    .map(([k, v]) => `<div class="runrow"><dt>${k}</dt><dd>${esc(v)}</dd></div>`)
    .join("");

  const rows = accountRows().sort((a, b) => b.open - a.open || b.exc - a.exc);
  if (rows.length) {
    $("ov-pt").textContent = "Accounts with the most open items";
    $("ov-all").textContent = `All ${rows.length} accounts`;
    $("ov-all").href = "#accounts";
    $("ov-head").innerHTML = "<tr><th>Account</th><th>Holder</th><th>Period</th><th class=\"r\">Verified</th><th class=\"r\">Open items</th><th class=\"r\">Exceptions</th></tr>";
    $("ov-accts").innerHTML = rows
      .slice(0, 6)
      .map(
        (a) =>
          `<tr data-acct="${esc(a.account_no)}"><td class="id num">${esc(a.account_no)}</td><td>${esc(a.holder || "—")}</td><td class="m">${esc(a.period)}</td><td class="r">${Math.round(a.verified * 100)}%</td><td class="r">${a.open}</td><td class="r">${a.exc}</td></tr>`
      )
      .join("");
  } else {
    // No accounts on printed tables: the pages with the most still to do instead.
    const docs = S.docs.map((d) => ({ d, ...docStats(d.page_id) })).sort((a, b) => b.open - a.open).slice(0, 6);
    $("ov-pt").textContent = "Pages with the most open items";
    $("ov-all").textContent = `All ${S.docs.length} pages`;
    $("ov-all").href = "#documents";
    $("ov-head").innerHTML = "<tr><th>Page</th><th>Table</th><th class=\"r\">Values</th><th class=\"r\">Open items</th><th class=\"r\">Exceptions</th></tr>";
    $("ov-accts").innerHTML = docs
      .map(({ d, values, open, exc }) => `<tr data-page="${esc(d.page_id)}"><td class="id">${esc(d.title)}</td><td class="w">${esc(d.typeLabel)}</td><td class="r">${values}</td><td class="r">${open}</td><td class="r">${exc}</td></tr>`)
      .join("");
  }
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
    const tr = e.target.closest("tr[data-acct],tr[data-page]");
    if (!tr) return;
    location.hash = tr.dataset.acct ? `acct-${tr.dataset.acct}` : `doc-${tr.dataset.page}`;
  });
  $("ov-export").addEventListener("click", exportCsv);
}

export function enter() {
  render();
}
