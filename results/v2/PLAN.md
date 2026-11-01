# P40 development comparison rule — written before implementing or testing v2

2026-11-01. Development only. No held-out page, label, draw, deep-check record,
or other held-out result will be opened. The original pre-registration, decisions,
prompts, readers, templates, policy and scorer stay unchanged.

Baseline audit: the 15 original drafting pages of the five approved Treasury
families, using cached Spark 1.3 reads, plus P33's five cached Baseten Open reads.
The immutable inputs are hashed in baseline.json. All page access passes
`templates.pages.resolve` before read/PDF access. Cached reads that are absent
are reported missing, never replaced by a fresh extraction. The baseline audit
was run before writing this rule. It found that unique long figures largely
rescue Spark 1.3 through v1's OCR step, whereas Open still has large row offsets.
This reference excludes repeated/short/absent OCR figures, precisely where the
repeated-label fault may occur: it cannot estimate that fault's population rate.

Diagnostic row offset = predicted centre y minus unique OCR figure centre y,
divided by the median PDF line pitch (12–70 px gaps after 8 px clustering), rounded
to an integer. Report model and v1 offsets separately, including -1, +1, farther,
and unavailable. This is an OCR geometry proxy, not correctness or a human label.
Inspect repeated labels separately by counting matching stub-label occurrences
in table row order, never nearest to a model box. Report unresolved labels.

Candidate: **S0+table-v2**, a separate function beside S0+grid. No global coordinate
conversion and no fitted constants from other pages. Locate numeric columns using
unique figures in this page's OCR, rejecting non-monotone columns. Locate rows by
unambiguous OCR stub labels, repeated labels only when their occurrence counts
match, and consensus of unique figures in a row. Use table ink/rules and exact
count gaps for rows/columns the text layer cannot settle. Reject conflicting or
ambiguous mappings. A structurally located cell takes the OCR token(s) physically
in that row/column, irrespective of the first-read value; otherwise a box on its
ink/grid. Unresolved cells retain v1 with an explicit fallback source. Record each
source and page diagnostics. Values, abstentions and field IDs never change.

Fixed paired re-read sample: 40 eligible figure cells per page/reader, or all on a
smaller page, sampled with `random.Random(40).sample` from field IDs sorted before
v2 is applied. Eligible = non-abstained, nonempty first read, boxed, money column.
The sample is frozen to draw.json before v2 is tested. Both strategies re-read
exactly these cells with the existing reread prompt, crop padding, schema,
allowance, retry and canonical comparison. Spark 1.3 uses templates.toml's minimal;
Open uses the existing Baseten low role (P33 found minimal not honoured). Failed,
null or illegible re-reads count as disagreement, never disappear. No SAM calls.
V1's order guard, when applicable, is the existing 15/20 blind guard; all guard
calls count toward the same caps and are recorded.

Containment: whole OCR figure inside the cited box, not merely its centre. Use the
strict P34-style independent-of-predicted-position proxy: at least three digits,
unique among first-read figure values and unique in the full PDF text layer.
Score both strategies on exactly those references; report every page and family,
centre containment and source shares too. These references are value-conditioned
and not independent accuracy labels. Additional occurrence-based row diagnostics
are exploratory and cannot change the adoption threshold.

**Adoption rule:** freeze v2 only if, separately for Spark 1.3 and Baseten Open,
(1) pooled full-figure containment strictly increases and (2) pooled paired
re-read agreement strictly increases. A tie keeps v1. Report every family/page,
including regressions and unmapped cells. No confidence/significance claim from
this development choice. Freeze only after all fixed samples complete; missing
samples fail the gate. No tuning after seeing the paired re-read comparison.

Task allowances: at most $5 additional Meta and $5 additional Baseten, enforced
from the canonical ledger's starting totals plus those allowances, capped again
by the existing standing limits. Fireworks and Glimmer receive no new allowance.
Measurements use a worktree-local writable cache; main's cache and development
scans are read-only inputs. Check uses main's cache with all spend caps zero.

If adopted, commit a **draft only** separate pre-registration: same 58 pages and
same 400 cell IDs as v1, reuse the first reads, re-read only those 400 cells,
existing scoring and all its reporting variants unchanged. No sweep, new draw,
new first read or held-out run here. Optional Open arm must align to those exact
cell IDs and have its own declared budget/freeze before execution. No new tag,
merge or held-out authorization is created by this task. Push branch v2 only.

Implementation record, before paired re-reads: the first geometry-only candidate
exposed two bugs: gaps between sparse column anchors were treated as one column,
and a numeric OCR token with an alphabetic footnote prefix was discarded. Column
pitch now divides by template index distance; numeric-dominant OCR tokens keep
footnote prefixes. This was development implementation work after the rule and
before freezing the candidate or examining any paired re-read. The first geometry
pass is preserved as geometry_initial.json. The gate and sample are unchanged.
