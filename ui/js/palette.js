// ⌘K: jump to a view, an account, a document or a value in the run.

import { S, accountRows, fieldLabel } from "./store.js";
import { $, esc } from "./util.js";

const NAV = [
  ["Overview", "overview"],
  ["Review queue", "review"],
  ["Accounts", "accounts"],
  ["Transactions", "transactions"],
  ["Documents", "documents"],
  ["Watch it work", "replay"],
  ["Accuracy report", "accuracy"],
  ["Document types", "types"],
];
let items = [], sel = 0;

function data(q) {
  q = q.trim().toLowerCase();
  const out = [];
  NAV.forEach(([name, hash]) => {
    if (!q || name.toLowerCase().includes(q)) out.push({ g: "Go to", t: name, s: "", run: () => (location.hash = hash) });
  });
  for (const a of accountRows()) {
    if (!q || `${a.account_no} ${a.holder || ""}`.toLowerCase().includes(q))
      out.push({ g: "Accounts", t: a.holder || a.account_no, s: a.account_no, run: () => (location.hash = `acct-${a.account_no}`) });
  }
  for (const d of S.docs) {
    const sub = d.kind === "memo" ? `Payment memo${d.holder ? ", " + d.holder : ""}` : `Ledger card${d.account_no ? ", " + d.account_no : ""}`;
    if (!q || `${d.title} ${sub} ${d.page_id}`.toLowerCase().includes(q))
      out.push({ g: "Documents", t: d.title, s: sub, run: () => (location.hash = `doc-${d.page_id}`) });
  }
  if (q.length >= 2) {
    let n = 0;
    for (const f of S.bundle.fields) {
      if (!f.value || !f.value.toLowerCase().includes(q)) continue;
      const d = S.docById.get(f.page_id);
      out.push({ g: "Values", t: f.value, s: `${fieldLabel(f)} · ${d ? d.title : f.page_id}`, run: () => (location.hash = `doc-${f.page_id}?pin=${encodeURIComponent(f.field_id)}`) });
      if (++n >= 12) break;
    }
  }
  return out.slice(0, 40);
}

function render() {
  items = data($("gq").value);
  sel = Math.min(sel, Math.max(0, items.length - 1));
  let g = "";
  $("pal-list").innerHTML = items.length
    ? items
        .map((it, i) => {
          const head = it.g !== g ? `<div class="pal-g">${it.g}</div>` : "";
          g = it.g;
          return `${head}<div class="pal-i" role="option" data-i="${i}" aria-selected="${i === sel}">${esc(it.t)}<span>${esc(it.s)}</span></div>`;
        })
        .join("")
    : `<div class="pal-g">Nothing matches. Try an account number, a memo number, a payee or an amount.</div>`;
  const cur = $("pal-list").querySelector('[aria-selected="true"]');
  if (cur) cur.scrollIntoView({ block: "nearest" });
}

export function open() {
  $("pal").hidden = false;
  $("gq").value = "";
  sel = 0;
  render();
  setTimeout(() => $("gq").focus(), 0);
}
export const close = () => ($("pal").hidden = true);

export function init() {
  $("cmdk").addEventListener("click", open);
  $("pal").addEventListener("click", (e) => {
    if (e.target === $("pal")) close();
    const it = e.target.closest(".pal-i");
    if (it) {
      close();
      items[+it.dataset.i].run();
    }
  });
  $("gq").addEventListener("input", () => {
    sel = 0;
    render();
  });
  $("gq").addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowDown") {
      e.preventDefault();
      sel = Math.min(sel + 1, items.length - 1);
      render();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      sel = Math.max(sel - 1, 0);
      render();
    } else if (e.key === "Enter") {
      e.preventDefault();
      const it = items[sel];
      if (it) {
        close();
        it.run();
      }
    }
  });
}
