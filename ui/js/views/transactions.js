// Transactions: every used ledger line as data, joined to the payment memo posted to it, searched in
// plain words, with the page beside the line showing exactly where each value sits.

import { S, LBL, stc, statusOf, shown } from "../store.js";
import { PageView } from "../pageview.js";
import { wire, hideWire, follow } from "../wire.js";
import { checkedBy } from "./document.js";
import { $, esc, num, money, fmtDate, parseDate, MONS, MONTHS, toast, reduced, frame } from "../util.js";

const RANK = { docerr: 4, review: 3, unread: 2, you: 1, ok: 0 };
const STOP = new Set("in on to from the of for all every show find me any with and values value records record amounts amount what which where was were is are by at than made transactions transaction lines line".split(" "));
let qState = "", hits = [], sel = null, srcPage = null, pv = null, accountFilter = "";

const field = (t, col) => S.fieldById.get(t.field_ids[col]);
const txVal = (t, col) => shown(field(t, col));
function txStatus(t) {
  let s = "ok";
  for (const id of Object.values(t.field_ids)) {
    const st = statusOf(S.fieldById.get(id));
    if (RANK[st] > RANK[s]) s = st;
  }
  return s;
}
const memoOf = (t) => {
  const page = t.memos[0];
  if (!page) return null;
  const f = (n) => S.fieldsByPage.get(page)?.find((x) => x.name === n);
  return { page, no: S.docById.get(page)?.memo_no || page, payee: shown(f("counterparty")), amount: shown(f("amount")), date: shown(f("date")), agrees: t.memos_agree };
};
const dkey = (d) => (parseDate(d) ? +parseDate(d) : 0);

// --- the search -----------------------------------------------------------------------------------

function parse(q) {
  const f = { toks: [] };
  let s = " " + q.toLowerCase().replace(/[£,]/g, "").replace(/\s+/g, " ") + " ";
  const take = (re, fn) => {
    const m = s.match(re);
    if (m) {
      fn(m);
      s = s.replace(m[0], " ");
    }
  };
  take(/\b(needs? review|needs? you|open items?|to review)\b/, () => (f.st = "review"));
  take(/\b(exceptions?|document errors?)\b/, () => (f.st = "docerr"));
  take(/\b(reviewed|confirmed)\b/, () => (f.st = "you"));
  take(/\bverified\b/, () => (f.st = "ok"));
  take(/\bsheet\s*(\d{1,3})\b/, (m) => (f.sheet = +m[1]));
  take(/\bmemos?\s*(?:no\.?\s*)?(\d{4,6})\b/, (m) => (f.memo = m[1].padStart(6, "0")));
  take(/\b(?:with (?:a )?memos?|memos?)\b/, () => (f.hasMemo = 1));
  take(/\b(?:cheques?|chqs?)\s*(?:no\.?\s*)?(\d{6})\b/, (m) => (f.chq = m[1]));
  take(/\b(payments?|paid|debits?|money out|spent|outgoings?)\b/, () => (f.dir = "out"));
  take(/\b(receipts?|received|credits?|deposits?|money in|income)\b/, () => (f.dir = "in"));
  take(/\bbetween (\d+(?:\.\d+)?) and (\d+(?:\.\d+)?)\b/, (m) => {
    f.min = +m[1];
    f.max = +m[2];
    f.incl = 1;
  });
  take(/(?:\bover\b|\babove\b|\bmore than\b|\bgreater than\b|>)\s*(\d+(?:\.\d+)?)/, (m) => (f.min = +m[1]));
  take(/(?:\bunder\b|\bbelow\b|\bless than\b|<)\s*(\d+(?:\.\d+)?)/, (m) => (f.max = +m[1]));
  const lower = MONS.map((x) => x.toLowerCase());
  take(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:19)?(\d\d)\b/, (m) => {
    f.mon = lower.indexOf(m[1]) + 1;
    f.yr = +m[2];
  });
  take(/\b(january|february|march|april|june|july|august|september|sept|october|november|december)\b/, (m) => (f.mon = lower.indexOf(m[1].slice(0, 3)) + 1));
  take(/\b19(\d\d)\b/, (m) => (f.yr = +m[1]));
  take(/\b(\d+\.\d\d)\b/, (m) => (f.eq = +m[1]));
  s.split(" ").forEach((w) => {
    w = w.replace(/[^a-z0-9’'\-]/g, "");
    if (w.length >= 3 && !STOP.has(w)) f.toks.push(w);
  });
  return f;
}

function matchTx(t, f) {
  const st = txStatus(t), db = num(txVal(t, "debit")), cr = num(txVal(t, "credit")), bl = num(txVal(t, "balance"));
  if (f.st && st !== f.st) return false;
  if (f.sheet && t.sheet !== f.sheet) return false;
  const m = memoOf(t);
  if (f.memo && !(m && m.no === f.memo)) return false;
  if (f.hasMemo && !m) return false;
  if (f.chq && !(t.description || "").includes(f.chq)) return false;
  if (f.dir === "out" && isNaN(db)) return false;
  if (f.dir === "in" && isNaN(cr)) return false;
  const amt = f.dir === "in" ? cr : f.dir === "out" ? db : isNaN(db) ? cr : db;
  if (f.min != null && !(f.incl ? amt >= f.min : amt > f.min)) return false;
  if (f.max != null && !(f.incl ? amt <= f.max : amt < f.max)) return false;
  if (f.eq != null && ![db, cr, bl].some((v) => !isNaN(v) && Math.abs(v - f.eq) < 0.001)) return false;
  if (f.mon || f.yr) {
    const d = parseDate(txVal(t, "date"));
    if (!d) return false;
    if (f.mon && d.getUTCMonth() + 1 !== f.mon) return false;
    if (f.yr && d.getUTCFullYear() % 100 !== f.yr) return false;
  }
  const hay = `${t.description || ""} ${m ? m.payee + " memo " + m.no : ""} sheet ${t.sheet}`.toLowerCase();
  return f.toks.every((w) => hay.includes(w));
}

function chipsFor(f) {
  const c = [];
  if (f.st) c.push(["Status", LBL[f.st].toLowerCase()]);
  if (f.sheet) c.push(["Sheet", String(f.sheet)]);
  if (f.memo) c.push(["Memo", f.memo]);
  if (f.hasMemo) c.push(["Has", "a payment memo"]);
  if (f.chq) c.push(["Cheque", f.chq]);
  if (f.dir) c.push(["Direction", f.dir === "out" ? "money out" : "money in"]);
  if (f.min != null && f.max != null) c.push(["Amount", `£${money(f.min)} to £${money(f.max)}`]);
  else if (f.min != null) c.push(["Amount", `over £${money(f.min)}`]);
  else if (f.max != null) c.push(["Amount", `under £${money(f.max)}`]);
  if (f.eq != null) c.push(["Amount", `exactly £${money(f.eq)}`]);
  if (f.mon || f.yr) c.push(["Date", `${f.mon ? MONTHS[f.mon - 1] : ""} ${f.yr ? "19" + String(f.yr).padStart(2, "0") : ""}`.trim()]);
  f.toks.forEach((t) => c.push(["Contains", `“${t}”`]));
  return c;
}

// Examples drawn from this run's own transactions, so each one finds something.
function examples() {
  const T = S.bundle.transactions, out = ["Payments over 100"];
  const d = parseDate(T.find((t) => parseDate(t.date))?.date);
  if (d) out.push(`${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`);
  const payee = T.map(memoOf).find((m) => m?.payee);
  if (payee) out.push(payee.payee.split(/\s+/)[0].replace(/[^\w’'-]/g, ""));
  const chq = T.map((t) => /CHQ\s*(\d{6})/i.exec(t.description || "")).find(Boolean);
  if (chq) out.push(`Cheque ${chq[1]}`);
  const amt = T.find((t) => /^\d+\.\d\d$/.test(t.debit || ""));
  if (amt) out.push(amt.debit);
  out.push("Needs review");
  return out;
}

function runSearch() {
  const f = parse(qState), ch = chipsFor(f);
  $("chips").innerHTML = qState.trim()
    ? ch.map((c) => `<span class="qchip">${c[0]}<b>${esc(c[1])}</b></span>`).join("") + (ch.length ? "" : `<span class="try">No filters recognised; showing everything.</span>`) + `<button class="clear" id="clear">Clear</button>`
    : `<span class="try">Examples:</span>` + examples().map((t) => `<button data-try="${esc(t)}">${esc(t)}</button>`).join("");
  const all = S.bundle.transactions.filter((t) => !accountFilter || t.account_no === accountFilter);
  hits = all.filter((t) => matchTx(t, f)).sort((a, b) => dkey(txVal(a, "date")) - dkey(txVal(b, "date")) || (a.sheet ?? 0) - (b.sheet ?? 0) || a.line - b.line);
  $("tx-count").textContent = `${hits.length} of ${all.length} transactions`;
  $("tx-acct").textContent = accountFilter ? `Account ${accountFilter}` : `All accounts`;
  if (!hits.length) {
    $("tx-rows").innerHTML = `<tr><td colspan="7" class="empty">No transactions match. Try a payee, an amount like ${esc(examples().at(-2))}, a month or a cheque number.</td></tr>`;
    sel = null;
    $("drawer").hidden = true;
    hideWire($("tthread"));
    return;
  }
  $("drawer").hidden = false;
  if (!hits.includes(sel)) sel = hits[0];
  const index = new Map(S.bundle.transactions.map((t, i) => [t, i]));
  $("tx-rows").innerHTML = hits
    .map((t) => {
      const m = memoOf(t);
      return `<tr data-i="${index.get(t)}"${t === sel ? ' aria-selected="true"' : ""}><td class="m num">${esc(fmtDate(txVal(t, "date")))}</td><td>${esc(t.description || "")}</td><td>${m ? esc(m.payee) : '<span class="m">—</span>'}</td><td class="r">${esc(txVal(t, "debit"))}</td><td class="r">${esc(txVal(t, "credit"))}</td><td class="r">${esc(txVal(t, "balance"))}</td><td>${stc(txStatus(t))}</td></tr>`;
    })
    .join("");
  showTx(sel);
}

// --- the page beside it ---------------------------------------------------------------------------

const amountField = (t) => (t.debit ? field(t, "debit") : field(t, "credit")) || field(t, "balance");

function tWire() {
  const tr = $("tx-rows").querySelector('tr[aria-selected="true"]');
  if (!sel || !tr || !pv || $("v-transactions").hidden) return hideWire($("tthread"));
  const f = amountField(sel), to = f && pv.target(f.field_id), r = tr.getBoundingClientRect();
  const box = (tr.closest(".tw") || tr).getBoundingClientRect(), right = Math.min(r.right, box.right);
  const from = { getBoundingClientRect: () => ({ left: r.left, right, top: r.top, bottom: r.bottom, height: r.height, width: right - r.left }) };
  wire($("tthread"), $("txgrid"), from, to, $("tstage"), "r");
}

function showTx(t) {
  const page = S.pageById.get(t.page_id), stage = $("tstage"), a = amountField(t);
  if (t.page_id !== srcPage || !pv) {
    srcPage = t.page_id;
    pv = new PageView(stage, page);
    for (const f of S.fieldsByPage.get(t.page_id) || []) if (statusOf(f) === "review" && f.box) pv.loop(f, "red");
    pv.camera({ fit: true });
  }
  pv.clearOverlay(".hl,.pen.hot");
  if (a) {
    pv.highlight(a);
    if (!pv.marks.get(a.field_id)?.stat) pv.loop(a, "gold", { draw: true, hot: true });
  }
  frame(() => {
    pv.camera({ box: a?.box, zoomCap: 1.7 });
    follow(tWire, reduced ? 0 : 950);
  });
  const st = txStatus(t);
  $("d-title").textContent = `${fmtDate(txVal(t, "date"))}, ${(t.description || "").charAt(0) + (t.description || "").slice(1).toLowerCase()}`;
  $("d-sub").textContent = `Sheet ${t.sheet ?? "?"}, line ${t.line}, page ${t.page_id}`;
  $("d-status").className = `st st-${st}`;
  $("d-status").textContent = LBL[st];
  const W = page.width, H = page.height, g = (v) => Math.round(v * 1000);
  const cols = [["Date", "date"], ["Description", "description"], [t.debit ? "Debit" : "Credit", t.debit ? "debit" : "credit"], ["Balance", "balance"]];
  $("d-fields").innerHTML = cols
    .map(([n, c]) => {
      const f = field(t, c);
      if (!f) return "";
      const b = f.box ? `[${g(f.box.x0 / W)}, ${g(f.box.y0 / H)}, ${g(f.box.x1 / W)}, ${g(f.box.y1 / H)}]` : "no box";
      return `<div><dt>${n}</dt><dd><span class="v">${esc(shown(f))}</span><span class="c">${b}</span><span style="display:block;font-size:12px;color:var(--ink-3);margin-top:2px">${esc(checkedBy(f))}</span></dd><dd>${stc(statusOf(f))}</dd></div>`;
    })
    .join("");
  const m = memoOf(t);
  $("d-memo").innerHTML = m
    ? `<div class="memo-card"><div><span class="k">Payment memo ${esc(m.no)}</span>${esc(m.payee)}, £${esc(m.amount)}, dated ${esc(fmtDate(m.date))}. <span style="color:${m.agrees === false ? "var(--bad)" : m.agrees ? "var(--ok)" : "var(--ink-3)"};font-weight:500">${m.agrees === false ? "Doesn’t agree" : m.agrees ? "Agrees" : "Not compared"}</span></div><button data-page="${esc(m.page)}">Open memo</button></div>`
    : "";
}

export function init() {
  $("q").addEventListener("input", (e) => {
    qState = e.target.value;
    runSearch();
  });
  $("chips").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    qState = b.id === "clear" ? "" : b.dataset.try;
    $("q").value = qState;
    runSearch();
    $("q").focus();
  });
  $("tx-rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-i]");
    if (!tr) return;
    sel = S.bundle.transactions[+tr.dataset.i];
    $("tx-rows").querySelectorAll("tr").forEach((x) => x.removeAttribute("aria-selected"));
    tr.setAttribute("aria-selected", "true");
    showTx(sel);
  });
  $("d-open").addEventListener("click", () => {
    if (!sel) return;
    const f = amountField(sel);
    location.hash = `doc-${sel.page_id}${f ? `?pin=${encodeURIComponent(f.field_id)}` : ""}`;
  });
  $("d-memo").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) location.hash = `doc-${b.dataset.page}`;
  });
  $("tx-export").addEventListener("click", () => toast("Export the transactions with archivist.export.database: transactions.csv in exports/<run>/."));
}

export function enter(arg, query) {
  accountFilter = query.get("account") || "";
  if (query.has("q")) qState = query.get("q");
  $("tx-crumb").innerHTML = `<a href="#overview">${esc(S.bundle.run.collection)}</a>/<span>Transactions</span>`;
  frame(() => {
    $("q").value = qState;
    srcPage = null;
    pv = null;
    runSearch();
  });
}
export function resize() {
  if (sel && pv) {
    const a = amountField(sel);
    pv.camera({ box: a?.box, zoomCap: 1.7 });
    tWire();
  }
}
export const scroll = tWire;
export const entered = tWire; // the entrance is over: the thread can point at content that is no longer moving
export function leave() {
  hideWire($("tthread"));
}
