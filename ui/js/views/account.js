// One account: its sheet chain, how the balance moved, and the payment memos matched to its lines.

import { S, accountDetail, docStats, stc, shown } from "../store.js";
import { $, esc, num, money, parseDate, fmtDate, MONS, int } from "../util.js";

let no = null;

function kpis(d) {
  const open = d.cards.concat(d.memos).reduce((n, x) => n + docStats(x.page_id).open, 0);
  const cell = (l, v, sub, c = "") => `<div class="kpi ${c}"><div class="l">${l}</div><div class="v">${v}</div><div class="d">${sub}</div></div>`;
  $("ad-kpis").innerHTML = [
    cell("Opening balance", d.opening ? `£${esc(d.opening)}` : "—", d.cards[0] ? `Sheet ${d.cards[0].sheet ?? "?"} brought forward` : ""),
    cell("Closing balance", d.closing ? `£${esc(d.closing)}` : "—", d.cards.at(-1) ? `Sheet ${d.cards.at(-1).sheet ?? "?"} carried forward` : ""),
    cell("Transactions", int(d.txns.length), `Across ${d.cards.length} ledger ${d.cards.length === 1 ? "card" : "cards"}`),
    cell("Open items", int(open), "On this account’s cards and memos", open ? "warn" : "ok"),
  ].join("");
}

function chain(d) {
  const joint = (a, b, ok) => `<div class="joint" style="${ok === false ? "color:var(--bad)" : ""}"><svg viewBox="0 0 96 14" aria-hidden="true"><path d="M2 7h86M82 3l6 4-6 4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg><span>${esc(a ?? "—")} carried,<br>${esc(b ?? "—")} brought</span></div>`;
  const val = (page, name) => (S.fieldsByPage.get(page) || []).find((f) => f.name === name && f.line == null);
  $("chain").innerHTML = d.cards
    .map((c, i) => {
      const s = docStats(c.page_id), st = s.open ? "review" : s.exc ? "docerr" : "ok";
      const bf = val(c.page_id, "brought_forward"), cf = val(c.page_id, "carried_forward");
      let lead = "";
      if (i) {
        const prev = val(d.cards[i - 1].page_id, "carried_forward");
        const ok = prev?.value && bf?.value ? num(prev.value) === num(bf.value) : null;
        lead = joint(prev?.value, bf?.value, ok);
      }
      return `${lead}<div class="sheetbox" data-page="${esc(c.page_id)}"><div class="t">Sheet ${esc(c.sheet ?? "?")}${st === "docerr" ? '<span class="st st-docerr">Exceptions</span>' : stc(st)}</div><div class="d">${esc(c.doc?.when || "")}</div><div class="r"><span>Brought forward</span><span>${esc(shown(bf) || "—")}</span></div><div class="r"><span>Carried forward</span><span>${esc(shown(cf) || "—")}</span></div></div>`;
    })
    .join("");
  const missing = d.account.missing_sheets;
  if (missing.length) $("chain").insertAdjacentHTML("afterend", `<p class="fine">Missing from the chain: ${missing.map((n) => "sheet " + n).join(", ")}; balances across the gap aren’t compared.</p>`);
}

// The balance after every line, in the order of the sheets, against its date.
function balance(d) {
  const pts = d.txns
    .map((t) => ({ d: parseDate(t.date), b: num(t.balance), sheet: t.page_id }))
    .filter((p) => p.d && Number.isFinite(p.b));
  if (pts.length < 2) {
    $("balchart").innerHTML = "";
    return;
  }
  const xs = pts.map((p) => +p.d), x0 = Math.min(...xs), x1 = Math.max(...xs), top = Math.max(...pts.map((p) => p.b)) * 1.1 || 1, low = Math.min(0, ...pts.map((p) => p.b));
  const X = (t) => 70 + ((t - x0) / (x1 - x0 || 1)) * 1110, Y = (b) => 200 - ((b - low) / (top - low)) * 180;
  let g = "";
  const step = 10 ** Math.floor(Math.log10(top)) / 2;
  for (let v = Math.ceil(low / step) * step; v < top; v += step) g += `<line x1="70" x2="1180" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="62" y="${Y(v) + 4}" text-anchor="end">£${int(Math.round(v))}</text>`;
  const first = new Date(x0), months = (x1 - x0) / 2.6e9;
  for (let m = 0; m <= Math.min(12, Math.floor(months)); m++) {
    const t = Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + m + 1, 1);
    if (t <= x1) g += `<text x="${X(t)}" y="224" text-anchor="middle">${MONS[new Date(t).getUTCMonth()]} ${new Date(t).getUTCFullYear()}</text>`;
  }
  g += `<polyline points="${pts.map((p) => `${X(+p.d).toFixed(1)},${Y(p.b).toFixed(1)}`).join(" ")}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>`;
  let prev = null;
  for (const p of pts) {
    if (prev && p.sheet !== prev) g += `<line x1="${X(+p.d)}" x2="${X(+p.d)}" y1="14" y2="200" stroke="var(--line-2)" stroke-dasharray="3 3"/>`;
    prev = p.sheet;
  }
  $("balchart").innerHTML = g;
}

function memos(d) {
  const val = (page, name) => (S.fieldsByPage.get(page) || []).find((f) => f.name === name);
  $("ad-memos").innerHTML = d.memos.length
    ? d.memos
        .map((m) => {
          const link = S.bundle.links.find((l) => l.kind === "memo_line" && l.source === m.page_id);
          const chip = !link || link.agrees == null ? '<span class="st st-unread">Not compared</span>' : link.agrees ? '<span class="st st-ok">Agrees</span>' : '<span class="st st-docerr">Doesn’t agree</span>';
          return `<tr data-page="${esc(m.page_id)}"><td class="id num">${esc(m.memo_no || m.page_id)}</td><td class="m">${esc(fmtDate(shown(val(m.page_id, "date"))))}</td><td>${esc(shown(val(m.page_id, "counterparty")) || "—")}</td><td class="r">${esc(shown(val(m.page_id, "amount")) || "—")}</td><td>${esc(shown(val(m.page_id, "ledger_ref")) || "—")}</td><td>${chip}</td></tr>`;
        })
        .join("")
    : `<tr><td colspan="6" class="empty">No payment memo was read for this account.</td></tr>`;
}

function render() {
  const d = accountDetail(no);
  if (!d) {
    location.hash = "accounts";
    return;
  }
  const a = d.account;
  $("ad-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<a href="#accounts">Accounts</a>/<span>${esc(no)}</span>`;
  $("ad-t").textContent = a.holder || `Account ${no}`;
  const n = d.cards.map((c) => c.sheet).filter((x) => x != null);
  const dates = d.cards.flatMap((c) => c.doc?.dates || []).sort((x, y) => x - y);
  const period = dates.length ? `, ${MONS[dates[0].getUTCMonth()]} ${dates[0].getUTCFullYear()} to ${MONS[dates.at(-1).getUTCMonth()]} ${dates.at(-1).getUTCFullYear()}` : "";
  $("ad-sub").textContent = `Account ${no}. ${n.length ? `Ledger ${n.length === 1 ? "card" : "cards"} ${n.length === 1 ? n[0] : `${Math.min(...n)} to ${Math.max(...n)}`}` : "No ledger card"} with ${d.memos.length} payment ${d.memos.length === 1 ? "memo" : "memos"}${period}.`;
  document.querySelectorAll("#chain + .fine").forEach((x) => x.remove());
  kpis(d);
  chain(d);
  balance(d);
  memos(d);
}

export function init() {
  $("chain").addEventListener("click", (e) => {
    const b = e.target.closest("[data-page]");
    if (b) location.hash = `doc-${b.dataset.page}`;
  });
  $("ad-memos").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-page]");
    if (tr) location.hash = `doc-${tr.dataset.page}`;
  });
  $("ad-tx").addEventListener("click", () => (location.hash = `transactions?account=${no}`));
  $("ad-review").addEventListener("click", () => {
    const d = accountDetail(no);
    const first = d.cards.concat(d.memos).find((c) => docStats(c.page_id).open);
    location.hash = first ? `review-${first.page_id}` : "review";
  });
}

export function enter(arg) {
  no = arg;
  render();
}
