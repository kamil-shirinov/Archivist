// Accounts: every account in the run, with its ledger cards, payment memos and how much is verified.

import { S, accountRows, accountDetail } from "../store.js";
import { $, esc, toast } from "../util.js";

function sheetsText(cards) {
  const n = cards.map((c) => c.sheet).filter((x) => x != null);
  if (!n.length) return "—";
  return n.length === 1 ? `Sheet ${n[0]}` : `Sheets ${Math.min(...n)} to ${Math.max(...n)}`;
}

function render() {
  const rows = accountRows().sort((a, b) => a.account_no.localeCompare(b.account_no));
  $("ac-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<span>Accounts</span>`;
  $("acct-rows").innerHTML = rows
    .map((a) => {
      const d = accountDetail(a.account_no);
      return `<tr data-acct="${esc(a.account_no)}"><td class="id num">${esc(a.account_no)}</td><td>${esc(a.holder || "—")}</td><td>${sheetsText(d.cards)}</td><td class="r">${d.memos.length}</td><td class="m">${esc(a.period)}</td><td class="r">${esc(d.opening ?? "—")}</td><td class="r">${esc(d.closing ?? "—")}</td><td class="r">${Math.round(a.verified * 100)}%</td><td class="r">${a.open}</td><td class="r">${a.exc}</td></tr>`;
    })
    .join("");
  $("ac-sub").textContent = `${rows.length} accounts in ${S.bundle.run.collection}: each with its ledger cards, payment memos and how much is verified. An account is a group of cards that read the same number; a card whose number was misread starts a group of its own.`;
}

export function init() {
  $("acct-rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-acct]");
    if (tr) location.hash = `acct-${tr.dataset.acct}`;
  });
  $("ac-export").addEventListener("click", () => toast("Export the accounts with archivist.export.database: accounts.csv in exports/<run>/."));
}

export function enter() {
  render();
}
