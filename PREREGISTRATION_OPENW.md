# Pre-registration — Muse Spark Open on the real scans, Treasury Bulletin held-out issues

Committed and tagged `prereg-real-openw` before Muse Spark Open has read any held-out page of the Treasury Bulletin. Nothing below may change after this commit. Any departure is recorded in the Deviations section at the end of this file and reported with the results. This plan adds one configuration to the real-pages test of `PREREGISTRATION_REAL.md` (version 1). It changes nothing in version 1: not its plan, records, labels, scorer or tags.

## What is being tested
The README's open-weights claim rests on synthetic pages (H4, arm B: 0.30% wrong among accepted). This run tests it on real scans. Muse Spark Open does both reads; Archivist checks them; a value is accepted under the same rules as version 1. The run is scored against the same 400 labelled cells.

## What was seen before this plan, and by whom
- The configuration was chosen on development pages only, after their results were seen (D58). P33 (`results/openw_measure/REPORT.md`) measured Muse Spark Open's settings, cost, speed and empty answers. P40 (`results/v2/REPORT.md`) measured the table-anchored boxes. P40's pre-written gate failed overall because Muse Spark 1.3's re-read agreement fell. For Muse Spark Open alone, the boxes moved onto the printed figure (25.32% to 99.70%) and re-read agreement rose (26% to 51%). Choosing these boxes for Open alone was decided after those results. It is not a pre-registered outcome of P40.
- No held-out page has been sent to Muse Spark Open. Version 1's held-out run has finished: its sweep, deep check and draw were committed at 00da8e1 and 6d35bae. The project owner is labelling its 400 cells, and version 1 is not yet scored. The author of this plan opened none of the held-out records while writing it.
- The runner was written in the same task as this plan. It was tried end to end on two development pages (below). It is committed right after this plan and tagged `run-real-openw`.

## Pages and cells: version 1's, chosen again by nothing
- **Pages:** the 58 pages of version 1's deep check (`results/real_test/held_out/sample.json`, committed at 00da8e1), at most 12 a family. Each is read as the family version 1's sweep and title check gave it. No page is classified, so no classifier call is made, and no page is added, dropped or replaced.
- **Cells:** the 400 cells of version 1's draw (`results/real_test/held_out/labels/draw.json`, committed at 6d35bae): 300 from the four 1939–1942 families and 100 from `total_claims_by_country`. They keep the draw's weights (the confirmed pages, as version 1's Deviations of 2026-10-30 fix them) and the owner's first labels. The relabel pass and the 50-page classification check measure the labeller and the classifier, so they are not repeated.
- **SAM 3.1's detections:** version 1's, replayed. The run asks SAM exactly as version 1 did: the same image bytes, prompts ("stamp", "stain"), model and settings, so the same cache key. This run's Meta cap is the Meta total of the spend ledger, so a SAM call that is not cached is refused, never made.
- The runner records the sha256 of each version 1 record it reads (`inputs_sha256` in `run.json`).

## Frozen system
- **Plan:** this file, at the commit tagged `prereg-real-openw`.
- **Code:** the commit tagged `run-real-openw`. Its runner (`src/archivist/templates/real_openw.py`) runs the held-out side only when nothing under `src`, `config`, `templates`, `labelling`, `pyproject.toml` and `uv.lock` differs from that tag, tracked or untracked. It checks this before any held-out page or record is opened. `labelling/` is frozen too, so the scorer and the rules it imports (`labelling/score.py`) are fixed.
- **Templates:** the five approved ones, byte for byte version 1's (sha256 as in `PREREGISTRATION_REAL.md`: 156a9632…, 7659ec40…, 3bc2e576…, 8b6d3cf7…, aba101be…).
- **Config:** `config/real_openw.toml`, sha256 e9ca6ebe6d86cd382fcb59e635794428c2e8a3b8fa9e47253a42d2b502e0a50e.
- **Boxes:** `src/archivist/templates/table_v2.py`, sha256 0d323889f344dc06e5397fbd798a07ec4e1c0199198ef4e7ff353111da7a212b. This is the file P40 froze before its paired re-reads (`results/v2/development_freeze.json`).
- **Same reads as version 1:** for the five families, this code builds the same prompts, schemas, field ids, re-read prompts, output allowances, canned-answer parse and checks as `run-real-treasury`. P33's offline equivalence script (`openw/equivalence.py`) was rerun on this code; its output equals the tag's except for the module path it records. `read_page`, `verify`, `reread`, `occlusion` and `grid` take the same paths as at that tag.
- **What the code adds:** a `timeout_s` setting for the Baseten backend (`src/archivist/models/baseten_api.py`). It is not part of the cache key, as meta_api's isn't, and its default stays 60 s, so no committed run changes. It also adds the runner, its config, the scorer (`labelling/score_openw.py`) and their tests. `python -m archivist.replay` passes on it.

## Models and settings
- **Muse Spark Open** (`meta-models/muse-spark-open-1026`) on Baseten, with the settings P33 measured:
  - It reads each table in context at reasoning "low". The output allowance is version 1's (`max(16,000, 4,000 + 40 × cells)`), the timeout 1,200 s.
  - It re-reads each drawn cell blind at reasoning "low": "minimal" is accepted but not honoured on Baseten (P33 §3). The rest is version 1's: crop, padding, prompt, schema, 2,048-token allowance, and its one retry with a note for an answer that does not parse. P33's suggested retry at double the allowance is not adopted, so that the rules stay version 1's.
  - The backend's own repairs are logged and leave the values unchanged: a Markdown fence around the whole answer is removed, and closing brackets are added to an answer that finished one short (D28).
- **SAM 3.1** (`sam-3.1`) on the Meta Model API, replayed from the cache as above.
- No other model. No call to Fireworks or Muse Glimmer: their caps are 0.

## Boxes
Every cell's box comes from S0+table-v2 (D58). It anchors columns on the page's unique OCR figures and rows on unambiguous stub labels, a repeated label only where its counts match, and bounds each cell by ink and ruled lines. A cell it cannot settle keeps S0+grid's box, made exactly as in version 1: OCR anchor, then the table's grid, then the model's own box, with the order fallback's blind guard where it applies (20 cells re-read by Open). Each cell records its source (`table:ocr`, `table:ink`, `v1:ocr`, `v1:grid`, `v1:model`).

## Finding a drawn cell in Open's read
The draw names cells by version 1's first read, and Open's read may return rows in other positions. The labeller found each cell by its section, its row's printed label and which occurrence of that label it is, and its column (`PREREGISTRATION_REAL.md`, Deviations). The row's position was only a hint. So, in `real_openw.match`:
- A fixed row (`total_claims_by_country`) is the template's row of that key.
- A read row is the row of Open's read that has the same label and is the same occurrence of it. Labels are compared folded to letters and digits, lower case, leader dots dropped. Occurrences are counted from the top of the table, or of the same section in a table read in sections, over the rows the read gave a label.
- A drawn row that version 1's read gave no label is found by its position, as the labeller found it.
- The column is the same.
- A cell whose row has no match, or whose page Open did not read, gets no value from Open. Like a cell the read abstained on, it is outside both error rates, and it is counted by why (`cells.json`).

## Policy and the drawn cells
- Policy v2 (`src/archivist/pipeline/verify.py`), unchanged, with no second looks. A value is accepted only when the in-context read and the blind re-read agree under the template's comparison, no identity involving it fails on the in-context values, and it has a box. Occluded values are accepted only if everything agrees.
- Every value of every page enters the identities, as in version 1. Only the 400 drawn cells are re-read.
- A cell's status (accepted or review) depends on three things: its own re-read, the identities on the in-context values, and what covers it. So the status here is the one a run re-reading every cell would give. Proposed corrections depend on the re-reads of neighbouring cells, which are not asked. They are not reported.

## Rules for the run
- One run. Nothing is changed between or during its starts: code, prompts, templates, settings or config.
- A start resumes from the run's own cache:
  - A page read is never read twice.
  - A page that failed (a timeout, an HTTP 429 or 5xx after the transport's three retries, an answer that will not parse after its one retry) is tried again on each start, up to 3 starts in all. After that it stays failed, and its drawn cells get no value.
  - An answer is never re-requested because of its content.
- A re-read that fails sends its cell to review. If any did, the run may be started again with the identical command, up to 3 verification passes in all. Only the failed re-reads are asked again; every answered one comes from the cache, and each pass's verdicts are kept (`verdicts.pass<n>.jsonl`). The results give every outcome these cells affect both ways: as run, and with those cells sent to review as failed re-reads.
- The run's own cache is `results/scratch/real_openw/held_out/cache`. It is seeded entry by entry from `cache/`, which it never writes.
- Where it runs:
  - Preferably from the main checkout. Its frozen paths must equal the tag's, so that its spend ledger is the canonical one.
  - Otherwise from a detached worktree of the tag. Its new ledger lines are then appended to main's ledger, in order, with nothing else changed.
  - Nothing is committed in that checkout while the run writes to the ledger.
- All run records are committed, including any first passes and any stall: `caps.json`, `predictions.jsonl`, `boxes.jsonl`, `failed.jsonl`, `cells.json`, `verdicts*.jsonl`, `run.json`, `stall.json`.

## Expected calls, cost and time
Estimated from P33's development measurement before any held-out page: page reads priced by family from its measured reads, and re-reads at its weighted cost with its bootstrap range.

| Part | Calls | Cost | Time |
|---|--:|--:|--:|
| 58 page reads (12 a family, 10 total-claims pages) | 58, or 116 if every page is asked twice | about $5.70 (at most $11.40) | about 5 to 10 minutes at 8 at once (16 to 42 s a page on Baseten in P33) |
| 400 blind re-reads | 400, plus a retry for any answer that does not parse | about $1.26 (range $1.05 to $1.51) | about 3 to 7 minutes (2.1 a second at 8 at once) |
| The order fallback's guard | none expected (no page needed it in P33 or in the development test); at most 20 a page | $0 (at most $3.25) | — |
| SAM 3.1 | 0 paid; at most 116 detections replayed (two prompts on each page with a drawn cell) | $0 | — |
| **All** | about 460 | **about $7 (at most about $16)** | **about 15 to 30 minutes** |

**Spend cap.** Baseten may spend at most **$20.00** on this run, all starts together. At the first start `caps.json` records Baseten's cap as its total in `results/spend_ledger.jsonl` plus $20.00, Meta's as its total (so no Meta call can be made) and every other backend's as 0. Every later start reads the same file. The standing caps are not raised. Baseten's $80 has $53.79 left after this task's development test, so the $20 fits. A run that reaches the cap stops; going past it is a deviation.

**Stop rule, if Baseten fails or stalls.**
1. *A stall:* calls are in flight and none has ended for 30 minutes. The runner stops itself and writes `stall.json`. That counts as a failure, resumed with the identical command.
2. *Baseten fails:* after 3 starts a quarter or more of the 58 pages (15 or more) are still unread, or the run has not written its verdicts within 48 hours of its first start, or a SAM call turns out not to be cached. The run is then stopped and reported as **incomplete**. Its records are committed, it is not scored, and no O1 result is claimed. Nothing moves to another host or model; Fireworks stays dropped (D56). The README keeps the real-scan open-weights result as pending.
3. Fewer pages than that failing does not stop the run. Their drawn cells get no value and are counted.

## What is reported, whatever it shows
Scored once by `labelling/score_openw.py`, from a detached checkout of `run-real-openw`. That happens only after version 1's score (`results/real_test/held_out/score/score.json`), the labels and this run's records are committed and pushed:

    git worktree add --detach <wt> run-real-openw && (cd <wt> && uv sync --frozen)
    cd <wt> && .venv/bin/python -m labelling.score_openw --data <main checkout>

- **The scorer's rules are version 1's**, applied by version 1's own functions (`labelling/score.py`):
  - A read is right when it equals the label under `TemplateType.canonical`.
  - "Row not on the page" and "column not on this page" count as wrong.
  - "Can't read", and a cell given no value, are outside every error rate and counted.
  - Weights come from the draw; the intervals are 2,000 page resamples within strata, seed 0.
- **The measures**, on the same drawn cells for both configurations, overall and by stratum (1939–1942; total claims):
  - wrong values among accepted (Archivist's error rate);
  - the single read's error rate;
  - wrong values caught: the share of the single read's wrong values not accepted;
  - sent to a person: the share of the drawn cells sent to review.
- **Both ways**, as version 1 reports them:
  - layouts: the 40 changed-layout pages' cells left out, or kept;
  - re-reads: as run, or the re-reads asked again sent to review. For Open these are the cells whose re-read failed in an earlier pass; for version 1, its 3,354 re-reads asked again, as `labelling/score.py` names them.
- **Side by side with version 1's hosted result.** Version 1's measures are worked out again here, from its own records, on the same cells. The scorer refuses to report unless its error rates and catch rate equal version 1's `score.json` to the last digit, in every variant and stratum. Version 1's "sent to a person" is given over the same 400 cells, so the two can be compared. Its every-cell review rate stays in its own score.
- The headline is also given with classified-page weights instead, as in version 1.
- **How the cells were found:**
  - by label, fixed row, position or not found, by stratum;
  - how many were found at the drawn cell's own position;
  - their statuses;
  - the box sources of the cells found;
  - the order guard's calls;
  - pages that failed, cost and time.

## One pre-set target (criterion fixed now)
- **O1:** Muse Spark Open's error rate among accepted cells is **below 1%**. This mirrors the synthetic H4, and like H4 it is judged on the rate itself, not its interval. It is judged in the variant **kept/as_run**: every drawn cell, the changed-layout pages kept, re-reads as run. It is shown in every other variant as well. O1 is reported as met or not met, with its numbers, whatever the outcome. It is not a comparison with version 1 and claims nothing about one.

## Limits, stated before the results
- **Two things change at once.** Version 1 is Muse Spark 1.3 with S0+grid. This run is Muse Spark Open with S0+table-v2. The side-by-side compares two configurations, not two models.
- **The box choice was made after seeing development results**, Open's among them, and P40's gate for adopting the boxes failed overall (D58). The pages here are held out, but the choice was not pre-registered before those results.
- **The cells were drawn from version 1's read.** A row version 1 did not return, or left empty, was never sampled, even where Open reads it. A drawn row Open reads under another label gets no value from Open and is counted.
- **Few accepted cells.** With 400 cells, of which many go to review, O1 rests on the weighted cells Open accepts. Below 1% may mean at most one or two wrong values, and the interval says how uncertain that is.
- **The re-reads.** Only the drawn cells are re-read, so proposed corrections are not measured, and the every-cell review rate and box shares of version 1 have no counterpart here.
- **The labels.** There is one labeller, the project's author, and the labels were given blind to both configurations' reads.
- **One host, Baseten.** This is not on-site: Muse Spark Open runs on Baseten's machines and SAM's detections came from Meta's API in version 1.

## The development test of the runner (development pages only)
On 2026-11-02, `python -m archivist.templates.real_openw deep --side development --pages 1939-12_p025 1939-12_p060`. These are a railroad page and a forward-exchange page that version 1's trial read and its title check confirmed; its wrong-table pages are refused. A stand-in draw took 20 cells a page with `random.Random(4004)`.
- Both pages were read in one ask each. One closing bracket was added (D28).
- All 40 cells were found by label, at their own positions.
- Box sources of the 40: 20 `table:ocr`, 1 `table:ink`, 9 `v1:grid`, 6 `v1:model`, 4 `v1:ocr`.
- No order guard was needed and no SAM call was paid for.
- The 40 re-reads were answered: 29 agreed, 10 disagreed, 1 illegible. Policy v2 accepted 29 and sent 11 to review.
- Baseten $0.2074, Meta $0, 50 seconds.
- A second start refused ("finished"), and the held-out side refused without the tag.
- After the test, one field was added to `run.json` (`inputs_sha256`), and nothing else changed. On the final code, replayed from the run's own cache with every cap at zero, `predictions.jsonl`, `boxes.jsonl`, `cells.json` and `verdicts.jsonl` came out byte-identical.
- Records are in `results/real_openw/development/`. Nothing is scored there, since development pages have no labels.

## Deviations
- 2026-11-02, after the run had started from the main checkout on `run-real-openw` (1adee1f) and before any result was seen: **a coverage line added to the reporting, by the project owner. It only adds reporting.** Beside every headline rate, the results also state how many of the 400 drawn cells Open's read did not contain, of how many, and why (page not read, row not found). That applies overall, by stratum and in every variant, beside O1, and in the classified-weights line. Such a cell gives no value and is outside the error rates, so missing rows could otherwise make the rates look better. The frozen scorer (`labelling/score_openw.py` at the tag) is unchanged and runs as planned. A separate script outside the frozen paths, `openw/coverage.py`, runs once after it. It reads `score.json` as the scorer wrote it, and `cells.json`, checked against the sha256 the score records and against the score's own tally of how cells were found. It writes `score/coverage.json` and `coverage.md` beside them. No rate, rule, target, cell, weight, setting or record changes, and the run is not touched. The tags stay where they were when the run started: `prereg-real-openw` on 8418a22, `run-real-openw` on 1adee1f. Nothing committed with this entry is under the runner's frozen paths, so a checkout updated to it still passes the runner's gate. Also recorded: CLAUDE.md's hard rule now allows a held-out run only by a pre-registered runner on its own pushed tag. The runner checks its tag and frozen paths; that the tag is pushed is checked by hand.
- 2026-11-02, after the run and before anything was scored: **the runner did not record the commit it ran on, so a provenance note was added beside the records, by the project owner; not a change to the run.** The run was made in the main checkout on `run-real-openw` (1adee1f), from 09:34:16 to 09:41:53 UTC. It read 58 of 58 pages in one verification pass, with no failed page and no stall. It spent $6.737917 on Baseten, within its $20 allowance, and $0 on Meta. `src/archivist/templates/real_openw.py` writes no commit, tag or HEAD into its records; that was an omission when it was built. The held-out side starts only after its gate passes, which requires the tag and no difference under the frozen paths, so the run is known to have started on frozen code. Before anything was committed, the checkout was checked and the result written to `results/real_openw/held_out/provenance.json`, marked as written after the run. HEAD was the tag's commit, with no tracked or untracked difference under the frozen paths. The runner's code and config were checked out at 09:34:13–14 UTC, just before the start. The spend ledger only gained lines: 373, all Baseten, from 09:34:33 to 09:41:40, summing to `run.json`'s cost. The six records are committed exactly as the run wrote them, and their sha256 are in that file. No label file was committed with them.
- 2026-11-02, after the official score and before the relabel, and before any page has been looked at for this purpose: **the dash check of the first-pass blanks, and a corrected-key score reported beside the official one, by the project owner.** This is the same check declared in `PREREGISTRATION_REAL.md`'s Deviations of the same date, applied to this run's score. It adds to what is reported, and changes no rule, draw, label, record, official score or O1. *What the diagnosis found* (`results/real_test/held_out/diagnosis.md`, P47, counts only): on the pages whose layout matches their template, most wrong values are a dash in the read where the first-pass label is blank. For this run, that is 14 of the single read's 25 wrong values and 4 of the 5 wrong values Archivist accepted; for version 1 it is 15 of 22 and all 9. The read prompt has a printed dash copied as "-", and Open's reads did so on 36 scored cells. None of the 400 first-pass labels is a typed dash. Every nil label is blank, which the template's comparison keeps apart from "-", so each such pair scores as wrong. Open's blind re-read is split on those 36 cells: a blank on 21, a dash on 9, a figure on 3, and 3 without a usable answer. So only the pages can settle which side is right. *The relabel goes ahead as planned:* version 1's 40 cells. This plan does not repeat the relabel. It follows the written rule, now stated on the labelling page: a printed dash is typed "-", and Blank means nothing is printed in the cell. *The dash check:* once the relabel is complete, every cell whose standing first-pass answer is blank (50 of the 400) is checked by eye on its page and marked **dash printed**, **nothing printed** or **can't tell**. Every such cell is checked, whatever either configuration's reads gave for it, so the check cannot favour the reads. It runs on the labelling server's `/dashcheck`, which shows no read and no verdict of either configuration. The marks are kept in `results/real_test/held_out/labels/dashes_checked.jsonl`. *The corrected key:* where a dash is printed, the corrected answer is "-". "Nothing printed" and "can't tell" leave the answer blank, and no other answer changes. It is the same key for both configurations, and `labels.jsonl` is not edited. *Reporting:* this run's official score (`results/real_openw/held_out/score/`) and O1 stay exactly as scored, and they are always reported first. Beside them goes a corrected-key score, computed under the unchanged rules: `labelling/score.py`'s comparison, the measures of `labelling/score_openw.py`, the draw's weights, both layouts and both re-read variants, and the intervals. That includes O1's rate in every variant, which is reported beside O1 and replaces nothing. It also includes version 1's side-by-side figures on the same key, and the coverage line of the first entry above, which the key does not change. With it go how many answers changed, overall and by stratum, with the marks counted, and the relabel's agreement with a Wilson 95% interval. That agreement is given with the first-pass key, which is the plan's figure, and with the corrected key. *How it is computed:* `labelling/score_corrected.py open_weights`, prepared now and not run, on the code tagged `run-real-openw`, from a detached checkout of the tag. It runs with that tag's own `labelling/` (`score_openw.py` and `score.py`, frozen by the tag), and refuses any other. The tag refuses untracked files under `labelling/`, so this file is run by its path from the main checkout: `cd <wt> && PYTHONPATH=. .venv/bin/python <main>/labelling/score_corrected.py open_weights --data <main>`. It runs `score_openw()` twice. First it scores the committed key, and refuses unless that reproduces this run's `score/score.json` to the last digit: O1, both configurations' measures in every variant and stratum, the classified-weights line, and how the cells were found. Then it scores the corrected key, with only the first-pass answers it reads replaced. In that second run, version 1's figures are on the corrected key too, so `score_openw`'s check that they equal version 1's official score is passed over there; the first run makes that check. It refuses unless `labels.jsonl`, `score_openw.py` and `score.py` are the files this run's official score recorded. It also refuses unless the labels, the dash marks, both official scores and this run's records are committed and pushed, every relabel answer predates the first mark, and every first-pass blank, and no other cell, has a mark. It writes `results/real_openw/held_out/score_corrected/` once, and never writes `score/` or a label file. *The order:* relabel; dash check; commit and push `relabels.jsonl` and `dashes_checked.jsonl`; run `score_corrected version_1` on `run-real-treasury` and `score_corrected open_weights` on `run-real-openw`; commit both `score_corrected/` folders on their own.
- 2026-11-03, a pointer, not a departure: `PREREGISTRATION_REAL.md`'s Deviations entry of the same date, **dated columns in Total Claims, and cells the dash check could not correct**, applies to this run too, since it is scored against the same labels and the same corrected key. It changes no score, rule, label or record here.
- 2026-11-03, a pointer, on the project owner's instruction: the entry of the same date in `PREREGISTRATION_REAL.md` applies to this run too. The published figures for open weights lead with the corrected key and give the official figure, as registered, beside it. O1 stands as scored, and the score files are unchanged.
