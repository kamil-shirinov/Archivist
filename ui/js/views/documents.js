// Documents: every page in the run, filterable by type, account and status.

import { S, accountRows, docStats, docStatus, stc } from "../store.js";
import { $, esc, int } from "../util.js";

let dType = "", dPage = 0;
const PER = 25;

function filterButtons() {
  const n = { ledger: 0, memo: 0, table: 0, other: 0 };
  for (const d of S.docs) n[d.kind]++;
  const buttons = [["", "All", S.docs.length]];
  if (n.ledger) buttons.push(["ledger", "Ledger cards", n.ledger]);
  if (n.memo) buttons.push(["memo", "Payment memos", n.memo]);
  if (n.table) buttons.push(["table", "Printed tables", n.table]);
  if (n.other) buttons.push(["other", "Other pages", n.other]);
  $("f-type").innerHTML = buttons
    .map(([t, label, c]) => `<button data-t="${t}" aria-pressed="${t === dType}">${label}<span class="c">${int(c)}</span></button>`)
    .join("");
}

const hasAccounts = () => S.docs.some((d) => d.account_no);

function render() {
  $("dc-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<span>Documents</span>`;
  $("dc-sub").textContent = `Every page in ${S.bundle.run.collection}. Filter by type, account or status.${S.bundle.run.description ? " " + S.bundle.run.description : ""}`;
  const accounts = hasAccounts(), hasCondition = !!S.truth;
  $("f-acct-l").hidden = !accounts;
  $("doc-head").innerHTML = accounts
    ? `<tr><th>Document</th><th>Type</th><th>Account</th><th>Holder</th><th>Date or period</th>${hasCondition ? "<th>Condition</th>" : ""}<th class="r">Values</th><th class="r">Open</th><th class="r">Exceptions</th><th>Status</th></tr>`
    : `<tr><th>Document</th><th>Table</th><th>Issue</th><th class="r">Values</th><th class="r">Open</th><th class="r">Exceptions</th><th>Status</th></tr>`;
  const a = $("f-acct").value, s = $("f-st").value, q = $("f-q").value.trim().toLowerCase();
  const rows = S.docs.filter(
    (d) =>
      (!dType || d.kind === dType) &&
      (!a || d.account_no === a) &&
      (!s || docStatus(d) === s) &&
      (!q || `${d.title} ${d.page_id} ${d.typeLabel}`.toLowerCase().includes(q))
  );
  const pages = Math.max(1, Math.ceil(rows.length / PER));
  dPage = Math.min(dPage, pages - 1);
  const view = rows.slice(dPage * PER, dPage * PER + PER);
  $("doc-rows").innerHTML = view.length
    ? view
        .map((d) => {
          const st = docStats(d.page_id), status = d.doc_type === "failed" || d.doc_type === "unsupported" ? "unread" : docStatus(d);
          const chip = status === "docerr" ? '<span class="st st-docerr">Exceptions</span>' : stc(status);
          const tail = `<td class="r">${st.values}</td><td class="r">${st.open || "—"}</td><td class="r">${st.exc || "—"}</td><td class="lst">${chip}</td>`;
          return accounts
            ? `<tr data-page="${esc(d.page_id)}"><td class="id">${esc(d.title)}</td><td>${esc(d.typeLabel)}</td><td class="num">${esc(d.account_no || "—")}</td><td>${esc(d.holder || "—")}</td><td class="m">${esc(d.when)}</td>${hasCondition ? `<td class="m">${esc(S.condition(d.page_id) || "—")}</td>` : ""}${tail}</tr>`
            : `<tr data-page="${esc(d.page_id)}"><td class="id">${esc(d.title)}</td><td class="w">${esc(d.typeLabel)}</td><td class="m">${esc(d.when)}</td>${tail}</tr>`;
        })
        .join("")
    : `<tr><td colspan="10" class="empty">No documents match. Clear a filter or search for a sheet, a memo number or a page.</td></tr>`;
  $("doc-count").textContent = rows.length ? `Showing ${dPage * PER + 1} to ${dPage * PER + view.length} of ${int(rows.length)}` : "No documents";
  $("pg-prev").disabled = dPage === 0;
  $("pg-next").disabled = dPage >= pages - 1;
}

export function init() {
  $("f-acct").innerHTML =
    '<option value="">All accounts</option>' +
    accountRows()
      .map((a) => `<option value="${esc(a.account_no)}">${esc(a.account_no)}${a.holder ? ", " + esc(a.holder) : ""}</option>`)
      .join("");
  filterButtons();
  $("f-type").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-t]");
    if (!b) return;
    dType = b.dataset.t;
    dPage = 0;
    filterButtons();
    render();
  });
  for (const id of ["f-acct", "f-st", "f-q"])
    $(id).addEventListener("input", () => {
      dPage = 0;
      render();
    });
  $("pg-prev").addEventListener("click", () => {
    dPage--;
    render();
  });
  $("pg-next").addEventListener("click", () => {
    dPage++;
    render();
  });
  $("doc-rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-page]");
    if (tr) location.hash = `doc-${tr.dataset.page}`;
  });
}

export function enter(arg, query) {
  const account = query.get("account");
  if (account && S.accountByNo.has(account)) $("f-acct").value = account;
  dPage = 0;
  render();
}
