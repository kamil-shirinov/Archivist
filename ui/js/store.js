// The run, loaded once, and what the views derive from it. Nothing here is invented: every value,
// box, flag and number comes from the exported bundle (data/bundles/<run>/bundle.json); the only
// state of the app's own is the visitor's answers in the review queue, kept in this browser.

import { getJSON, parseDate, fmtDate, longDate, monthYear, pad, MONTHS } from "./util.js";

export const S = {
  index: null,
  entry: null,
  bundle: null,
  bundleUrl: null,
  truth: null, // optional: the damage level each synthetic page was made at (truth.json, demo only)
  pageById: new Map(),
  fieldById: new Map(),
  fieldsByPage: new Map(),
  rulesByField: new Map(),
  accountByNo: new Map(),
  txByPage: new Map(),
  docs: [],
  docById: new Map(),
  docTypes: new Map(),
  answers: {},
};

export const LBL = {
  ok: "Verified",
  review: "Needs review",
  you: "Reviewed",
  docerr: "Exception",
  unread: "Not read",
};
export const stc = (st) => `<span class="st st-${st}">${LBL[st]}</span>`;
export const COND = ["Clean", "Light wear", "Moderate wear", "Heavy wear"];

const COLUMN = { date: "Date", description: "Description", debit: "Debit", credit: "Credit", balance: "Balance" };
const HEADER = {
  account_no: "Account number",
  holder: "Holder",
  sheet_no: "Sheet number",
  brought_forward: "Brought forward",
  carried_forward: "Carried forward",
};
const MEMO = {
  memo_no: "Memo number",
  date: "Date",
  account_no: "Account number",
  counterparty: "Pay to",
  amount: "Amount in figures",
  amount_words: "Amount in words",
  ledger_ref: "Ledger ref.",
};
const titleize = (s) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

// A table cell is named by its row's printed label and its column's printed heading.
export function rowLabel(f) {
  const type = S.docTypes.get(f.doc_type);
  const text = type?.columns.find((c) => c.kind === "text");
  const cell = text && S.fieldById.get(`T.${f.doc_type}:${f.page_id}:${f.row}:${text.key}`);
  const printed = (cell?.value || "").replace(/[.\s]+$/, "").trim();
  return printed || `Row ${f.row}`;
}
export const columnLabel = (f) => S.docTypes.get(f.doc_type)?.columns.find((c) => c.key === f.name)?.printed || titleize(f.name);

export function fieldLabel(f) {
  if (f.row != null) return `${rowLabel(f)}, ${columnLabel(f)}`;
  if (f.line != null) return `Line ${f.line}, ${(COLUMN[f.name] || titleize(f.name)).toLowerCase()}`;
  return (f.doc_type === "payment_memo" ? MEMO[f.name] : HEADER[f.name]) || titleize(f.name);
}

const lineField = (f, name) => S.fieldById.get(`L:${f.page_id}:${pad(f.line, 2)}:${name}`);
// Where a value sits, in words: "Line 14, 28 Sep 1976, standing order rates".
export function fieldContext(f) {
  if (f.row != null) return S.docById.get(f.page_id)?.title || "";
  if (f.line == null) return f.doc_type === "ledger_card" ? "Card header" : "";
  const date = lineField(f, "date")?.value, what = lineField(f, "description")?.value;
  return [`Line ${f.line}`, date && fmtDate(date), what && what.toLowerCase()].filter(Boolean).join(", ");
}

export const REASON = {
  read_mismatch: "Read mismatch",
  reread_illegible: "Second read illegible",
  reread_failed: "Second read failed",
  no_citation: "No box to read again",
  obscured: "Obscured by a stamp or stain",
  not_read: "Not read",
};
export const reasonLabel = (r) =>
  r.code === "rule_failed" ? S.bundle.rule_labels[r.rule] || r.rule : REASON[r.code] || r.code;
const REASON_SENTENCE = {
  read_mismatch: "the two reads disagree",
  reread_illegible: "the second read couldn’t make it out",
  reread_failed: "the second read failed",
  no_citation: "there is no box to read again",
  obscured: "a stamp or stain covers it",
  not_read: "it wasn’t read",
};
export const reasonSentence = (r) =>
  r.code === "rule_failed" ? `${(S.bundle.rule_labels[r.rule] || r.rule).toLowerCase()} fails` : REASON_SENTENCE[r.code];

// --- the visitor's answers --------------------------------------------------------------------------

const answersKey = () => `archivist-answers:${S.entry.run_id}`;
export function setAnswer(fieldId, answer) {
  S.answers[fieldId] = answer;
  try {
    localStorage.setItem(answersKey(), JSON.stringify(S.answers));
  } catch (e) {
    /* private mode: the answers last until the page closes */
  }
}
export function clearAnswers() {
  S.answers = {};
  try {
    localStorage.removeItem(answersKey());
  } catch (e) {
    /* nothing kept */
  }
}

// --- statuses ---------------------------------------------------------------------------------------

// The reads agree and a rule still fails, with nothing covering the value: the page itself may be
// wrong, not the reading of it.
export const isException = (f) =>
  f.status === "review" &&
  f.reread_status === "agrees" &&
  f.reasons.some((r) => r.code === "rule_failed") &&
  !f.reasons.some((r) => r.code === "obscured");

export function statusOf(f) {
  const answered = S.answers[f.field_id];
  if (answered) return answered.st;
  if (f.status === "accepted") return "ok";
  if (f.status === "abstained") return "unread";
  return isException(f) ? "docerr" : "review";
}
export const isOpen = (f) => {
  const st = statusOf(f);
  return st === "review" || st === "unread";
};

export function docStats(pageId) {
  const fields = S.fieldsByPage.get(pageId) || [];
  let open = 0, exc = 0;
  for (const f of fields) {
    const st = statusOf(f);
    if (st === "review" || st === "unread") open++;
    else if (st === "docerr") exc++;
  }
  return { values: fields.length, open, exc };
}
export const docStatus = (d) => {
  const s = docStats(d.page_id);
  return s.open ? "review" : s.exc ? "docerr" : "ok";
};

export function totals() {
  let ok = 0, open = 0, exc = 0;
  for (const f of S.bundle.fields) {
    const st = statusOf(f);
    if (st === "ok" || st === "you") ok++;
    else if (st === "docerr") exc++;
    else open++;
  }
  return { ok, open, exc, all: S.bundle.fields.length };
}

// What this field's rules say, failed ones first.
export const rulesOf = (f) => S.rulesByField.get(f.field_id) || [];

// --- loading ----------------------------------------------------------------------------------------

export const pageUrl = (page) => new URL(page.image.url, S.bundleUrl).href;

export async function boot() {
  const meta = document.querySelector('meta[name="archivist-bundles"]');
  const root = new URL(meta ? meta.content : "../data/bundles/", document.baseURI);
  S.index = await getJSON(new URL("index.json", root));
  const asked = new URLSearchParams(location.search).get("run");
  S.entry =
    S.index.runs.find((r) => r.run_id === asked) ||
    S.index.runs.find((r) => r.arm === "hosted" && r.split === "test") ||
    S.index.runs[0];
  if (!S.entry) throw new Error("data/bundles/index.json lists no run");
  S.bundleUrl = new URL(S.entry.path, root);
  S.bundle = await getJSON(S.bundleUrl);
  S.truth = S.entry.truth ? await getJSON(new URL(`${S.entry.run_id}/truth.json`, root)) : null;
  try {
    S.answers = JSON.parse(localStorage.getItem(answersKey()) || "{}");
  } catch (e) {
    S.answers = {};
  }
  derive();
}

function derive() {
  const b = S.bundle;
  S.pageById = new Map(b.pages.map((p) => [p.page_id, p]));
  S.fieldById = new Map(b.fields.map((f) => [f.field_id, f]));
  S.fieldsByPage = new Map(b.pages.map((p) => [p.page_id, p.field_ids.map((id) => S.fieldById.get(id)).filter(Boolean)]));
  S.rulesByField = new Map();
  for (const r of b.rule_results)
    for (const id of r.fields) {
      if (!S.rulesByField.has(id)) S.rulesByField.set(id, []);
      S.rulesByField.get(id).push(r);
    }
  for (const list of S.rulesByField.values()) list.sort((x, y) => x.ok - y.ok);
  S.accountByNo = new Map(b.accounts.map((a) => [a.account_no, a]));
  S.txByPage = new Map();
  for (const t of b.transactions) {
    if (!S.txByPage.has(t.page_id)) S.txByPage.set(t.page_id, []);
    S.txByPage.get(t.page_id).push(t);
  }
  const severity = S.truth ? new Map(S.truth.pages.map((p) => [p.page_id, p.severity])) : null;
  S.condition = (pageId) => (severity && severity.has(pageId) ? COND[severity.get(pageId)] : null);
  S.docTypes = new Map(b.doc_types.map((t) => [t.name, t]));
  S.docs = b.documents.map((d) => {
    const page = S.pageById.get(d.page_id);
    const type = S.docTypes.get(d.doc_type);
    const kind = d.doc_type === "ledger_card" ? "ledger" : d.doc_type === "payment_memo" ? "memo" : type?.kind === "template" ? "table" : "other";
    const account = d.account_no ? S.accountByNo.get(d.account_no) : null;
    const issueLabel = page.issue ? issueName(page.issue) : null;
    const title =
      kind === "ledger" && d.sheet != null
        ? `Sheet ${d.sheet}`
        : kind === "memo" && d.memo_no
          ? `Memo ${d.memo_no}`
          : kind === "table"
            ? `${issueLabel}, page ${page.number}`
            : d.page_id;
    const dates = (S.txByPage.get(d.page_id) || []).map((t) => parseDate(t.date)).filter(Boolean).sort((x, y) => x - y);
    const memoDate = kind === "memo" ? (S.fieldsByPage.get(d.page_id) || []).find((f) => f.name === "date")?.value : null;
    const sort = dates.length ? +dates[0] : memoDate && parseDate(memoDate) ? +parseDate(memoDate) : page.issue ? Date.UTC(+page.issue.slice(0, 4), +page.issue.slice(5) - 1, 1) + (page.number || 0) : 0;
    const when = dates.length
      ? `${longDate(dates[0])} to ${longDate(dates.at(-1))}`
      : memoDate
        ? fmtDate(memoDate)
        : issueLabel || "—";
    return {
      ...d,
      kind,
      title,
      holder: account?.holder || null,
      when,
      sort,
      dates,
      typeLabel: kind === "ledger" ? "Ledger card" : kind === "memo" ? "Payment memo" : kind === "table" ? type.title : d.doc_type === "failed" ? "Not read" : d.doc_type,
    };
  });
  // The order a box is read in: by account, then by date, then by name.
  S.docs.sort(
    (x, y) =>
      (x.account_no || "￿").localeCompare(y.account_no || "￿") || x.sort - y.sort || x.title.localeCompare(y.title, "en", { numeric: true })
  );
  S.docById = new Map(S.docs.map((d) => [d.page_id, d]));
}

// What a document is called at the head of its page, and the line under it.
export function heading(d) {
  if (d.kind === "ledger") return `Ledger card, ${d.title.toLowerCase()}`;
  if (d.kind === "memo") return `Payment memo ${d.memo_no || ""}`.trim();
  if (d.kind === "table") return S.pageById.get(d.page_id).title;
  return d.page_id;
}
export function subtitle(d) {
  if (d.kind === "table") {
    const pub = S.bundle.run.publication, page = S.pageById.get(d.page_id);
    return `${pub ? pub.title + ", " : ""}${issueName(page.issue)}, page ${page.number}${pub ? `. ${pub.publisher}. ${pub.rights}.` : "."}`;
  }
  const acct = d.account_no ? `Account ${d.account_no}${d.holder ? ", " + d.holder : ""}.` : "Account not read.";
  if (d.kind === "memo") {
    const ref = (S.fieldsByPage.get(d.page_id) || []).find((x) => x.name === "ledger_ref")?.value;
    return `${acct} ${ref ? `Pays ${ref.toLowerCase().replace(" / ", ", ")}.` : ""}`.trim();
  }
  return `${acct} ${d.when === "—" ? "" : d.when + "."}`.trim();
}

export const issueName = (issue) => `${MONTHS[+issue.slice(5, 7) - 1]} ${issue.slice(0, 4)}`;

// --- per account ------------------------------------------------------------------------------------

export function accountRows() {
  const by = new Map();
  for (const d of S.docs) {
    if (!d.account_no || !S.accountByNo.has(d.account_no)) continue; // a memo whose account no card has is in no account
    if (!by.has(d.account_no)) by.set(d.account_no, { account_no: d.account_no, holder: d.holder, docs: [], dates: [], values: 0, open: 0, exc: 0 });
    const row = by.get(d.account_no);
    const s = docStats(d.page_id);
    row.docs.push(d);
    row.values += s.values;
    row.open += s.open;
    row.exc += s.exc;
    row.dates.push(...d.dates);
  }
  return [...by.values()].map((row) => {
    row.dates.sort((x, y) => x - y);
    row.period = row.dates.length ? `${monthYear(row.dates[0])} to ${monthYear(row.dates.at(-1))}` : "—";
    row.verified = row.values ? (row.values - row.open - row.exc) / row.values : 0;
    return row;
  });
}

// An account's cards in sheet order, its memos, and its opening and closing balance as the first
// card brings forward and the last carries forward.
export function accountDetail(no) {
  const account = S.accountByNo.get(no);
  if (!account) return null;
  const cards = account.sheets.map((sh) => ({ ...sh, doc: S.docById.get(sh.page_id) }));
  const memos = S.docs.filter((d) => d.kind === "memo" && d.account_no === no);
  const val = (pageId, name) => (S.fieldsByPage.get(pageId) || []).find((f) => f.name === name && f.line == null);
  const first = cards[0], last = cards.at(-1);
  return {
    account,
    cards,
    memos,
    opening: first ? val(first.page_id, "brought_forward")?.value : null,
    closing: last ? val(last.page_id, "carried_forward")?.value : null,
    txns: S.bundle.transactions.filter((t) => t.account_no === no),
  };
}
export const shown = (f) => (f && S.answers[f.field_id] ? S.answers[f.field_id].val : f?.value ?? "");

// --- words about the run ----------------------------------------------------------------------------

export function runWords() {
  const r = S.bundle.run;
  const models = r.models.map((m) => m.name);
  const uniq = [...new Set(models)];
  return {
    pages: r.source === "synthetic" ? "synthetic test pages" : "public-domain scans",
    arm: { hosted: "hosted models on Meta’s API", "open-weights": "open-weight models", mixed: "a hosted reader with an open-weight checker", unknown: "models not recorded" }[r.arm],
    models: uniq.join(", "),
    run: r.run_id,
  };
}
