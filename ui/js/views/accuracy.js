// Accuracy report, in plain words, from the pre-registered test report of the synthetic test pages
// (results/test_report.json, carried in the bundle as written). The real government scans are measured
// under their own pre-registration and show as pending until that is done.

import { S, COND } from "../store.js";
import { $, esc, int, rng } from "../util.js";

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"];
const word = (n) => (n >= 0 && n <= 20 ? WORDS[n] : String(n));
const k = (x) => x * 1000; // a share as wrong values in 1,000
const whole = (x) => Math.round(x);
const one = (x) => (x >= 1.95 ? String(Math.round(x)) : x.toFixed(1));
const pct = (x, d = 2) => `${(x * 100).toFixed(d)}%`;
const money4 = (x) => `$${x < 0.001 ? x.toFixed(4) : x.toFixed(3)}`;
const inOne = (share) => `1 in ${Math.max(1, Math.round(1 / share))}`;
const ci = (c, d = 2) => `${pct(c[0], d)} to ${pct(c[1], d)}`;

function dotGrid(red, gold, seed, label) {
  const g = rng(seed), c = new Array(1000).fill(0);
  const put = (n, v) => {
    let m = 0;
    while (m < n) {
      const i = Math.floor(g() * 1000);
      if (!c[i]) {
        c[i] = v;
        m++;
      }
    }
  };
  put(gold, 2);
  put(red, 1);
  return `<div class="dots" role="img" aria-label="${esc(label)}">${c.map((v) => (v === 1 ? '<i class="w"></i>' : v === 2 ? '<i class="p"></i>' : "<i></i>")).join("")}</div>`;
}

function rangeBar(lo, hi, est) {
  const x = (v) => (v / 80) * 100;
  return `<div class="range" aria-hidden="true"><div class="bar"><i style="left:${x(lo).toFixed(2)}%;width:${(x(hi) - x(lo)).toFixed(2)}%"></i><b style="left:${x(est).toFixed(2)}%"></b></div><div class="axis"><span>0</span><span>20</span><span>40</span><span>60</span><span>80 in 1,000</span></div></div>`;
}

// The risk-coverage curve the report measured: wrong values per 1,000 accepted against the share sent
// to a person, at each confidence cut-off it tried. Only those points are drawn.
function curve(points, single, arch) {
  const X = (v) => 44 + (v / 25) * 452, Y = (v) => 172 - (v / 50) * 156;
  let g = "";
  [0, 10, 20, 30, 40, 50].forEach((v) => (g += `<line x1="44" x2="496" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="36" y="${Y(v) + 4}" text-anchor="end">${v}</text>`));
  [0, 5, 10, 15, 20, 25].forEach((v) => (g += `<text x="${X(v)}" y="192" text-anchor="middle">${v} in 100</text>`));
  g += `<text x="44" y="6">Wrong in 1,000 accepted</text>`;
  g += `<polyline points="${points.map((p) => `${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(" ")}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="5 4"/>`;
  for (const p of points) g += `<circle class="pt" cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4"/>`;
  g += `<circle class="pt base" cx="${X(single.x)}" cy="${Y(single.y)}" r="5"/><text class="lbl" x="${X(single.x) + 10}" y="${Y(single.y) - 9}">Single read</text>`;
  g += `<circle class="pt arch" cx="${X(arch.x)}" cy="${Y(arch.y)}" r="5.5"/><text class="lbl" x="${X(arch.x) + 9}" y="${Y(arch.y) - 14}">Archivist</text>`;
  return g;
}

const TARGET_TEXT = {
  H1: (h) => ["Fewer wrong values than reading once", `${one(k(h.numbers.headline.rate))} in 1,000 against ${one(k(h.numbers.baseline.rate))} in 1,000. Even Archivist’s worst likely figure, ${one(k(h.numbers.headline.ci95[1]))} in 1,000, ${h.numbers.headline.ci95[1] < h.numbers.baseline.ci95[0] ? "beats" : "does not beat"} the single read’s best, ${one(k(h.numbers.baseline.ci95[0]))}.`],
  H2: (h) => [`Catch at least ${whole(h.numbers.threshold * 100)} of every 100 wrong values`, `Caught ${h.numbers.caught} of ${h.numbers.wrong}, about ${whole(h.numbers.rate * 100)} in 100.`],
  H3: (h, r) => {
    const heavy = r.configurations.A.by_severity["3"];
    return [`Send no more than ${whole(h.numbers.threshold * 100)} in 100 values to a person`, `Sent ${int(h.numbers.review)} of ${int(h.numbers.fields)}, about ${whole(h.numbers.rate * 100)} in 100. ${int(heavy.n_review)} of them were on the most worn pages.`];
  },
  H4: (h) => [`With open-weight models only, fewer than ${whole(h.numbers.threshold * 1000)} wrong in 1,000`, `${whole(k(h.numbers.rate))} in 1,000: ${h.numbers.wrong} wrong among ${int(h.numbers.accepted)} accepted.`],
  H5: (h) => {
    const need = Math.ceil(h.numbers.threshold * h.numbers.planted - 1e-9), n = h.numbers;
    return [`Flag at least ${whole(n.threshold * 100)} of every 100 mistakes already in the original documents`, `Flagged ${n.found} of ${n.planted}.${n.found < need ? ` ${need - n.found === 1 ? "One more" : word(need - n.found) + " more"} would have met it.` : ""}`];
  },
};

function renderTest(r) {
  const cfg = r.configurations, A = cfg.A, B = cfg.B, C = cfg.C, base = cfg.baseline;
  const single = base.extraction_alone, arch = A.stats;
  const s1 = k(single.error_rate_accepted), a1 = k(arch.error_rate_accepted);
  const share = arch.review_rate, accepted = arch.n_accepted / r.n_fields;
  const lead = `Read once with no checks, about ${whole(s1)} in every 1,000 values went into the database wrong. Archivist let through about ${whole(a1)} in 1,000, ${word(whole(s1 / a1))} times fewer, by sending about ${inOne(share)} values to a person.`;
  const dotsA = whole(k(arch.errors_missed / r.n_fields)), review = whole(k(share)), accepts = whole(k(accepted)), unread = whole(k(arch.n_abstained / r.n_fields));
  const rc = A.stats.risk_coverage.map(([cov, risk]) => ({ x: (1 - cov) * 100, y: k(risk) })).sort((p, q) => p.x - q.x);
  const singlePt = { x: (1 - single.n_accepted / r.n_fields) * 100, y: s1 };
  const archPt = { x: share * 100, y: a1 };
  const sev = A.by_severity;
  const worst = Math.max(...Object.values(sev).map((v) => v.review_rate * 100));
  const arms = [
    ["Read once, no checks", s1, "None", base.cost.per_page_usd],
    ["Archivist, Meta’s hosted models", a1, `${whole(A.stats.review_rate * 100)} in 100`, A.cost.per_page_usd, "Headline"],
    ["Archivist, open-weight models only", k(B.stats.error_rate_accepted), `${whole(B.stats.review_rate * 100)} in 100`, B.cost.per_page_usd],
    ["Archivist, hosted reader with an open-weight checker", k(C.stats.error_rate_accepted), `${whole(C.stats.review_rate * 100)} in 100`, C.cost.per_page_usd],
  ];
  const wrongOf = (c) => `${c.errors_missed} of ${int(c.n_accepted)}, ${pct(c.error_rate_accepted)}`;
  const integrity = [
    ["Wrong among accepted, single read", `${wrongOf(single)} (95% interval ${ci(single.error_rate_accepted_ci95)})`],
    ["Wrong among accepted, Archivist", `${wrongOf(arch)} (${ci(arch.error_rate_accepted_ci95)})`],
    ["Wrong values caught", `${arch.errors_caught} of ${arch.n_wrong}, ${pct(arch.catch_rate)} (${ci(arch.catch_rate_ci95)})`],
    ["Sent to a person", `${int(arch.n_review)} of ${int(r.n_fields)}, ${pct(arch.review_rate)} (${ci(arch.review_rate_ci95)})`],
    ["Open-weight models only", `${B.stats.errors_missed} wrong of ${int(B.stats.n_accepted)} accepted, ${pct(B.stats.error_rate_accepted)} (${ci(B.stats.error_rate_accepted_ci95)})`],
    ["Mistakes in the original documents flagged", `${arch.source_errors_found} of ${arch.n_source_errors}, ${pct(arch.source_error_recall)}`],
    ["Correct values sent to a person", `${int(arch.false_alarms)} of ${int(arch.n_correct)}`],
    ["How the intervals work", `Resampling whole ${r.bootstrap.unit}s (${int(r.bootstrap.resamples)} resamples), because mistakes on one ${r.bootstrap.unit} aren’t independent`],
    ["Test set frozen before any run", `<span class="mono">sha256 ${esc(r.manifest_sha256.slice(0, 8))}…</span>`],
    ["Pre-registration", `<span class="mono">${esc(r.preregistration)}</span>`],
    ["Deviations from the plan", `Listed in full in ${esc(r.preregistration)}, under Deviations`],
    ["Reproduce every number", '<span class="mono">uv run python -m archivist.eval.test_report</span>'],
  ];
  const met = Object.values(r.hypotheses).filter((h) => h.met).length, total = Object.keys(r.hypotheses).length;
  $("acc-test").innerHTML = `
    <p class="acc-lead">${esc(lead)}</p>
    <div class="dotpair">
      <div class="panel dotcard"><h3>Read once, no checks</h3><div class="big">${whole(s1)}<small>wrong in every 1,000 values</small></div>${dotGrid(whole(s1), 0, 451, `1,000 values read once: ${whole(s1)} of them wrong`)}<div class="dotkey"><span class="w">Wrong value</span><span>Right value</span></div><p class="dotnote">All the values it reads go into the database, and about ${whole(s1)} in every 1,000 of them are wrong.</p>${rangeBar(k(single.error_rate_accepted_ci95[0]), k(single.error_rate_accepted_ci95[1]), s1)}<p class="fine">We’re 95% sure the true figure is between ${whole(k(single.error_rate_accepted_ci95[0]))} and ${whole(k(single.error_rate_accepted_ci95[1]))} in 1,000.</p></div>
      <div class="panel dotcard"><h3>With Archivist</h3><div class="big">${whole(a1)}<small>wrong in every 1,000 values it accepts</small></div>${dotGrid(dotsA, review, 452, `1,000 values with Archivist: ${review} sent to a person, and ${dotsA} wrong among the ${accepts} it accepted`)}<div class="dotkey"><span class="w">Wrong value</span><span class="p">Sent to a person</span><span>Right value</span></div><p class="dotnote">${review} go to a person first. Of the ${accepts} accepted on their own, ${dotsA} are wrong${unread ? `, and ${unread} weren’t read at all` : ""}.</p>${rangeBar(k(arch.error_rate_accepted_ci95[0]), k(arch.error_rate_accepted_ci95[1]), a1)}<p class="fine">We’re 95% sure the true figure is between ${one(k(arch.error_rate_accepted_ci95[0]))} and ${one(k(arch.error_rate_accepted_ci95[1]))} in 1,000.</p></div>
    </div>
    <div class="sec"><h2>${total === 5 ? "Five" : word(total)} targets, set before the test</h2><p class="secsub">Written down and published before Archivist saw a single test page. ${word(met).replace(/^./, (c) => c.toUpperCase())} ${met === 1 ? "was" : "were"} met${met < total ? `, and ${word(total - met)} ${total - met === 1 ? "was" : "were"} missed${total - met <= 2 ? " narrowly" : ""}` : ""}.</p><div class="panel"><ul class="targets">${Object.entries(r.hypotheses)
      .map(([id, h]) => {
        const [q, a] = TARGET_TEXT[id](h, r);
        return `<li><span class="q">${esc(q)}</span><span class="st ${h.met ? "st-ok" : "st-miss"}">${h.met ? "Met" : "Missed"}</span><span class="a">${esc(a)}</span></li>`;
      })
      .join("")}</ul></div></div>
    <div class="sec charts">
      <div class="panel chartp chart"><h3>Checking more by hand means fewer mistakes</h3><p>Measured at ${rc.length} confidence cut-offs: at the one Archivist used, ${whole(share * 100)} in 100 values go to a person and about ${one(a1)} in 1,000 accepted values are wrong.</p><svg id="ch-curve" viewBox="0 0 520 200" role="img" aria-label="Wrong values per 1,000 accepted against the share sent to a person, at each measured cut-off">${curve(rc, singlePt, archPt)}</svg><p class="fine">Straight lines join the measured points; nothing was measured between them.</p></div>
      <div class="panel chartp"><h3>Worn pages get checked more</h3><p>Share of values sent to a person, by the condition of the page. Most of the checking goes to the most worn pages.</p><div class="cond">${Object.entries(sev)
        .map(([i, v]) => `<div class="crow"><span>${COND[+i]}</span><span class="cb"><i style="width:${((v.review_rate * 100) / Math.max(50, worst)) * 100}%"></i></span><span class="cv">${whole(v.review_rate * 100)} in 100</span></div>`)
        .join("")}</div></div>
    </div>
    <div class="sec"><h2>Same test, different models</h2><p class="secsub">Each one ran once on the same ${r.n_pages} pages. With open-weight models only, Archivist let through ${one(k(B.stats.error_rate_accepted))} in 1,000, against ${one(a1)} with Meta’s hosted ones.</p><div class="panel"><div class="tw"><table class="tbl"><thead><tr><th>How it ran</th><th class="r">Wrong in 1,000 accepted</th><th class="r">Sent to a person</th><th class="r">Cost per page</th></tr></thead><tbody>${arms
      .map(([n, w, s, c, tag]) => `<tr><td>${esc(n)}${tag ? ` <span class="tag" style="margin-left:6px">${tag}</span>` : ""}</td><td class="r">${whole(w)}</td><td class="r">${s}</td><td class="r">${money4(c)}</td></tr>`)
      .join("")}</tbody></table></div></div></div>
    <details class="experts"><summary>For experts: exact figures, method and how to check them</summary><div class="panel" style="margin-top:12px"><dl class="integrity">${integrity.map(([a, b]) => `<div><dt>${a}</dt><dd>${b}</dd></div>`).join("")}</dl></div>
      <p class="fine" style="max-width:80ch">${esc(r.notes[0])}</p>${r.notes.slice(1).map((n) => `<p class="fine" style="max-width:80ch">${esc(n)}</p>`).join("")}</details>`;
}

export function init() {
  $("acc-set").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-a]");
    if (!b) return;
    $("acc-set").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    $("acc-test").hidden = b.dataset.a !== "test";
    $("acc-real").hidden = b.dataset.a !== "real";
  });
}

export function enter() {
  const run = S.bundle.run, acc = S.bundle.accuracy;
  $("ev-crumb").innerHTML = `<a href="#overview">${esc(run.collection)}</a>/<span>Accuracy report</span>`;
  if (!acc) {
    const dev = run.stage === "development", f = S.bundle.fields;
    const read = f.filter((x) => x.value != null);
    const agree = read.filter((x) => x.reread_status === "agrees").length;
    const held = S.bundle.rule_results.filter((x) => x.ok).length, failed = S.bundle.rule_results.length - held;
    $("ev-sub").textContent = dev ? "These are development pages, so there is nothing here to measure." : "There is no pre-registered test report for this run.";
    $("acc-test").innerHTML = `<div class="panel pending"><h2>${dev ? "Development pages: no measured result" : "No test report"}</h2><p>${
      dev
        ? `The pages in this collection were used to draft the document types and test their rules, so what Archivist did on them says nothing about how often it is right: a measure needs pages that tuned nothing, with the right answers known. The measured results are the pre-registered test on the synthetic pages (the Box 14 collection) and, for real pages, the test whose results are pending.`
        : `The accuracy report comes from the pre-registered test on the synthetic test pages. This run (${esc(run.run_id)}) was made on the ${esc(run.split)} pages, which have none.`
    }</p>${
      dev
        ? `<p>What the run recorded, as it stands, is not an accuracy:</p><dl class="integrity" style="max-width:560px"><div><dt>Cells in the run</dt><dd>${int(f.length)}</dd></div><div><dt>Cells read</dt><dd>${int(read.length)}</dd></div><div><dt>Second read agreed</dt><dd>${int(agree)} of ${int(read.length)}</dd></div><div><dt>Sent to a person</dt><dd>${int(f.filter((x) => x.status === "review").length)}</dd></div><div><dt>Rules that held</dt><dd>${int(held)}</dd></div><div><dt>Rules that failed</dt><dd>${int(failed)}</dd></div></dl>`
        : ""
    }</div>`;
    return;
  }
  const r = acc.report;
  $("ev-sub").textContent = `How often Archivist puts a wrong value in the database. Measured once, on ${r.n_pages} synthetic pages it had never seen, against targets written down before the test.`;
  $("acc-test-btn").querySelector(".c").textContent = String(r.n_pages);
  renderTest(r);
}
