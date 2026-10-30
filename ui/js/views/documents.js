// Documents: every page in the run, filterable by type, account and status.

import { S, accountRows, docStats, docStatus, stc } from "../store.js";
import { $, esc, int } from "../util.js";

let dType = "", dPage = 0;
const PER = 25;

function filterButtons() {
  const n = { ledger: 0, memo: 0, other: 0 };
  for (const d of S.docs) n[d.kind]++;
  const buttons = [["", "All", S.docs.length], ["ledger", "Ledger cards", n.ledger], ["memo", "Payment memos", n.memo]];
  if (n.other) buttons.push(["other", "Other pages", n.other]);
  $("f-type").innerHTML = buttons
    .map(([t, label, c]) => `<button data-t="${t}" aria-pressed="${t === dType}">${label}<span class="c">${int(c)}</span></button>`)
    .join("");
}

function render() {
  $("dc-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<span>Documents</span>`;
  const a = $("f-acct").value, s = $("f-st").value, q = $("f-q").value.trim().toLowerCase();
  const hasCondition = !!S.truth;
  $("th-cond").hidden = !hasCondition;
  const rows = S.docs.filter(
    (d) =>
      (!dType || d.kind === dType) &&
      (!a || d.account_no === a) &&
      (!s || docStatus(d) === s) &&
      (!q || `${d.title} ${d.page_id}`.toLowerCase().includes(q))
  );
  const pages = Math.max(1, Math.ceil(rows.length / PER));
  dPage = Math.min(dPage, pages - 1);
  const view = rows.slice(dPage * PER, dPage * PER + PER);
  $("doc-rows").innerHTML = view.length
    ? view
        .map((d) => {
          const st = docStats(d.page_id), status = d.doc_type === "failed" || d.doc_type === "unsupported" ? "unread" : docStatus(d);
          const chip = status === "docerr" ? '<span class="st st-docerr">Exceptions</span>' : stc(status);
          return `<tr data-page="${esc(d.page_id)}"><td class="id">${esc(d.title)}</td><td>${esc(d.typeLabel)}</td><td class="num">${esc(d.account_no || "—")}</td><td>${esc(d.holder || "—")}</td><td class="m">${esc(d.when)}</td>${hasCondition ? `<td class="m">${esc(S.condition(d.page_id) || "—")}</td>` : ""}<td class="r">${st.values}</td><td class="r">${st.open || "—"}</td><td class="r">${st.exc || "—"}</td><td class="lst">${chip}</td></tr>`;
        })
        .join("")
    : `<tr><td colspan="10" class="empty">No documents match. Clear a filter or search for a sheet or memo number.</td></tr>`;
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
