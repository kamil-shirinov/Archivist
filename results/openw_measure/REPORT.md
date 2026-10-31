# P33 — Muse Spark Open: cost, speed and empty answers (DEVELOPMENT PAGES ONLY)

**Development-only measurement. Not a result, not a pre-registration.** Every page sent to a model
is an issue in the `development` list of `data/real/split.json`, checked in code before any file
was opened or any call made. Nothing held out was opened, listed or sent. No call was made to
Meta's API (its cap for this task is 0), so SAM is out.

## Fixed in advance (written 2026-10-30T22:35:07Z, before any call and before any page was read)

**The five pages.** For each of version 1's five families (`config/real_test.toml`), the lowest page
id among the pages its committed evidence file (`templates/<family>.evidence.json`) lists as tested,
which is also the first page the template was drafted from. Applied by `openw.measure pick`
(`pick.json`, 2026-10-30T22:34:47Z):

| Family | Page | Cells the read asks for |
| --- | --- | --: |
| short_term_foreign_liabilities_as | 1939-01_p051 | 700 |
| security_transactions_as_reported_by | 1939-01_p055 | 840 |
| outstanding_forward_exchange_contracts | 1939-01_p061 | 420 |
| receipts_and_expenditures_under_railroad | 1939-08_p043 | 102 |
| total_claims_by_country | 1982-06_p094 | 837 |

**The draw.** Per page, 40 cells with `random.Random(33).sample` over the page's eligible cells
sorted by id (eligible = what version 1's verify re-reads: read, boxed, not abstained). The speed test
uses 24 further cells a page, `random.Random(34).sample` over the cells left, eight a level. **Seed 33**
(and 34).

**Where the crops come from.** Baseten's read of the page (the order of HOSTS; Fireworks' read only for
a page whose Baseten read failed): the order fallback's blind guard and `grid.assign` run on it exactly
as `real_test.read_one` runs them, and each host re-reads the same crops.

**Reasoning settings, step 3.** One probe page that is not one of the five (1939-12_p053), four figures
spread down it, boxed by the PDF's own text layer, each re-read once at every setting: none, minimal,
low, medium, high, xhigh, and "bogus" (a value no API should take: its error names the ones it does).
*Accepted*: at least one probe call at the setting got an answer (refused: every call an HTTP 4xx).
*Honoured*: on at least 3 of the 4 cells fewer reasoning tokens than "low" (output tokens where the
host reports no reasoning count) and a median ratio to "low" of at most 0.7. *The setting the re-reads
use on a host*: "minimal" if honoured (version 1's), else "none" if honoured, else "low".

**Empty answers, step 4.** Empty = the answer's text is empty. Retried once, the same crop and prompt,
with double the allowance (2,048 -> 4,096). An unparseable, non-empty answer is retried the same way and
counted apart. Version 1's own retry (the same prompt with a note, same allowance) is not made.

**Spend.** This task's caps, recorded in `caps.json` at the first start: each host's ledger total then
plus $3.80, so the two together stay under $8; Meta's at 0.

## Answers in short

1. **Does Muse Spark Open honour “minimal”?** No, on neither host. Both **accept** it (HTTP 200) but it
   reasons as much as “low”: on 200 re-reads a host, median reasoning tokens were 320 at “minimal” against
   289 at “low” on Baseten, and 249 against 250 on Fireworks (§3, §4). The lowest setting honoured is
   **“low”** on both. Baseten also takes “none” and Fireworks refuses it; neither honours anything below
   “low”. Version 1's re-reads at “minimal” therefore become re-reads at “low” in effect.
2. **How often does a re-read come back empty?** At “low”, **5 of 200 (2.5%, 95% 1.1–5.7%) on Baseten
   and 3 of 200 (1.5%, 0.5–4.3%) on Fireworks**; at “minimal” 4.0% and 1.0%. Every one of the 18 empties
   (of 800) spent the whole 2,048-token allowance on reasoning (finish reason “length”). Retried once at
   4,096, **17 of 18 were answered**. Spark 1.3 at “low” was about 1 in 6 (D33). A different failure is
   not rare on Fireworks: it answered a valid `null` (“can't read”) for **103 of 200 crops (51.5%)** at
   version 1's crop size, against 8–10 of 200 on Baseten; enlarged ×3 it answered 15 of 16 such crops
   (§4.3, §4.6).
3. **Cost.** A re-read costs **$0.0028 (Baseten) or $0.0024 (Fireworks)**, retries included, about 25
   times Spark 1.3's $0.00011. The full run at version 1's size is **about $97 on Baseten (range $82–121)**
   or **$77 on Fireworks (range $68–94)**, against $2.92 for version 1's whole deep check. **No option
   fits the cap that is left** ($55.77 on Baseten, $38.03 on Fireworks): I did not raise any cap (§7).
4. **Time.** At 8 calls at once Baseten ran **2.1 re-reads a second** (1 at once: 0.30; 4: 0.97), so
   the 29,018 re-reads take **3.8 to 8.3 hours** (8 or 4 at once) and the 58 page reads about 5 minutes more.
   Fireworks ran 0.39 a second at 8 at once (0.07 at 1, 0.28 at 4): **21 to 29 hours** for the re-reads,
   and one 700-cell page read never returned in 30 minutes. Version 1 took 12 h 9 min net.
5. **Not asked, but it changes what version 1 on open weights would verify:** Spark Open's own boxes sit
   far from the printed figures (§4.5), so version 1's OCR step anchors far fewer cells than it did for
   Spark 1.3 on four of the five pages (1–28% against 38–55%); most crops are of the wrong place, and a
   Baseten re-read matches Baseten's page read on only 29% of the cells re-read (§4.4, §4.5).

## 2. How version 1's deep check ran
Read with `git show run-real-treasury:<path>` from `src/archivist/templates/real_test.py` (570 lines),
`pipeline/extract.py`, `pipeline/reread.py`, `pipeline/verify.py`, `pipeline/occlusion.py`,
`templates/test.py`, `templates/grid.py`, `models/meta_api.py`, `config/real_test.toml` and
`config/templates.toml`; nothing was checked out and none of the run's records was opened.

**Calls a page made** (the classification belongs to the sweep, a separate stage run beforehand; the
deep check replays each page's class from the cache):

| # | Call | Model and setting | Allowance | Notes |
| --- | --- | --- | --- | --- |
| 1 | Sweep: classify the page among the five types | Muse Spark 1.3 Contributor, Meta API, reasoning `low`, structured output | 2,048 | one call a page, 4,569 pages, 4 at once; not part of the 58-page deep check |
| 2 | **Page read**: the whole table in context (`extract.read_page`, box strategy S0) | same model, `low`, `timeout_s = 1200` | `max(16,000, 4,000 + 40 x cells)`: 32,000 / 37,600 / 20,800 / 16,000 / 37,480 for the five families | the page image and the template's prompt; structured output; one more ask, with a note, if the answer does not parse |
| 3 | Blind guard (some pages only): `blind_check` re-reads 20 cells when the grid has no fixed row and as many bands as rows (the order fallback) | rereader, `minimal` | 2,048 | up to 8 at once inside the page |
| 4 | SAM stain check | `sam-3.1`, Meta API, prompts "stamp" and "stain", each its own request | n/a | 116 calls for 58 pages; a value is occluded when one box covers 10% of its own |
| 5 | **Blind re-read of every cell** read, boxed and not abstained (`verify.verify`, policy v2, no second looks) | Muse Spark 1.3 Contributor, reasoning `minimal`, 60 s timeout | 2,048 | a PNG crop of the cell's box padded 0.5 x its height above and below and 0.2 x its width either side; prompt from the column heading and the table's title, never a value; schema `{"value": string or null}`; 29,018 of them |

**Calls at once.** `deep --workers 8` (the documented command; the parser's own default is 4, and the
Deviations speak of "at most 8 re-reads in flight"): a thread pool of 8 pages reads and boxes, each page
holding up to 8 more threads in its guard; then `verify` runs SAM over 8 pages at once and the 29,018
re-reads in one pool of 8. The sweep ran 4 at once.

**Retries.** Transport: `_with_retries` retries an HTTP 429 or 5xx up to 3 times, after
0.5 s x 2^n plus up to as much again in jitter, and at least as long as a `Retry-After` header asks.
Anything else (a timeout, a connection error, a 4xx) is raised at once and not retried by the transport.
Parsing: a page read or a classification that does not parse is asked once more with a note appended
(a different request, so a different cache entry), then fails; a re-read that does not parse (an empty
answer included) is asked once more with its own note, then raises `ReReadFailed`. A failed page read
is logged to `failed.jsonl` and tried again on the next start; a failed re-read becomes a `failed`
re-read and its cell goes to review, and on the next start (from the cache) it is asked again. A
spend cap stops the run (`BudgetExceeded`). Every answered call is cached and in the ledger.

## 3. Reasoning settings (step 3)

Four figures of 1939-12_p053 (not one of the five pages), each boxed by the PDF's own text layer, each
re-read once at every setting (2,048-token allowance, version 1's prompt, schema and PNG padding). The APIs'
own error texts, got by sending `"bogus"`, list what they take: Baseten `minimal, low, medium, high, xhigh,
max, none`; Fireworks the same plus `adaptive`, and also an integer and a boolean. Those were probed too.

| Host | `reasoning_effort` | Answered of 4 | Refused (HTTP) | Reasoning tokens, median | Output tokens, median | Out of allowance (empty) | Fewer than “low” | Median ratio to “low” | Honoured |
| --- | --- | --: | --- | --: | --: | --: | --: | --: | --- |
| baseten | none | 4 | — | 268 | 286 | 0 | 1/4 | 1.14 | no |
| baseten | minimal | 4 | — | 220 | 238 | 0 | 2/4 | 1.01 | no |
| baseten | low | 4 | — | 248 | 266 | 0 | 0/4 | 1.00 | (reference) |
| baseten | medium | 4 | — | 554 | 572 | 1 | 0/4 | 2.08 | no |
| baseten | high | 4 | — | 666 | 683 | 1 | 0/4 | 1.75 | no |
| baseten | xhigh | 4 | — | 1,252 | 1,262 | 2 | 0/4 | 1.76 | no |
| baseten | max | 4 | — | 1,029 | 1,047 | 1 | 0/4 | 2.70 | no |
| baseten | bogus | 0 | 1 × 400 | — | — | 0 | — | — | — |
| fireworks | none | 0 | 4 × 400 | — | — | 0 | — | — | — |
| fireworks | minimal | 4 | — | 330 | 348 | 0 | 1/4 | 1.50 | no |
| fireworks | low | 4 | — | 226 | 244 | 0 | 0/4 | 1.00 | (reference) |
| fireworks | medium | 4 | — | 553 | 570 | 0 | 0/4 | 2.57 | no |
| fireworks | high | 3 + 1 timeout (60 s) | — | 1,265 | 1,282 | 0 | 0/3 | 5.30 | no |
| fireworks | xhigh | 4 | — | 988 | 1,006 | 0 | 0/4 | 4.72 | no |
| fireworks | max | 2 + 2 timeout (60 s) | — | 502 | 519 | 0 | 0/2 | 2.59 | no |
| fireworks | adaptive | 0 | 4 × 400 | — | — | 0 | — | — | — |
| fireworks | int64 | 0 | 4 × 400 | — | — | 0 | — | — | — |
| fireworks | false | 0 | 4 × 400 | — | — | 0 | — | — | — |
| fireworks | bogus | 0 | 1 × 400 | — | — | 0 | — | — | — |

- **Accepted is not honoured.** “minimal” and (on Baseten) “none” return HTTP 200 and spend what “low”
  spends: median reasoning tokens 220 and 268 against 248 on Baseten; 330 against 226 for “minimal” on
  Fireworks. The committed backends' own docstring says as much for Baseten (“would silently run at low”).
- **Fireworks refuses what would turn reasoning down**: `none` and `false` (“Muse Spark is a reasoning model;
  disabling thinking … is not supported”), an integer budget, and `adaptive` (“Use 'low', 'medium', 'high',
  or 'xhigh'”). `minimal` and `max` are accepted; `high` and `max` each timed out at 60 s on some cells.
- **The lowest honoured setting is “low” on both hosts**: a median of about 250 reasoning tokens for a
  one-cell re-read, against 758 for Spark 1.3 at “low” (D33). Rule applied: re-reads use “low”.
- The committed backends cannot even send “minimal” or “none” (their constructors refuse them); the
  measurement did so through a shim (§9).
- Four cells cannot settle it, so the main measurement also re-read the same 200 crops at “minimal”: it
  gave the same answer (§4.3).

## 4. The main measurement (step 4)

Five pages, one a family (the rule in “Fixed in advance”). Page reads at “low”, version 1's prompt, schema,
allowance (`max(16,000, 4,000 + 40 × cells)`) and a 1,200 s timeout. Boxes from **Baseten's read** (every
page's Baseten read succeeded), by `grid.assign` as `real_test.read_one` runs it (OCR anchors, then the grid,
then the model's own box; no page needed the order fallback's blind guard). 40 cells a page drawn with
`random.Random(33)`, the same 200 crops re-read on both hosts at “low” and at “minimal”.

### 4.1 Page reads

| Host | Page (family) | Cells | Seconds | Asks | Input | Output (reasoning) | Cost | Finish | D28 repairs | Cells with no box |
| --- | --- | --: | --: | --: | --: | --: | --: | --- | --: | --: |
| baseten | 1939-01_p051 (short-term) | 700 | 36 | 1 | 44,794 | 14,224 (474) | $0.1164 | stop | 0 | 0 |
| baseten | 1939-01_p055 (security) | 840 | 40 | 1 | 52,816 | 17,261 (1,098) | $0.1394 | stop | 0 | 42 |
| baseten | 1939-01_p061 (forward) | 420 | 33 | 1 | 29,073 | 9,698 (1,353) | $0.0776 | stop | 1 | 0 |
| baseten | 1939-08_p043 (railroad) | 102 | 16 | 1 | 10,481 | 3,377 (695) | $0.0274 | stop | 0 | 0 |
| baseten | 1982-06_p094 (claims) | 837 | 42 | 1 | 53,668 | 16,434 (437) | $0.1369 | stop | 0 | 81 |
| fireworks | 1939-01_p051 (short-term) | — | **no answer in 1,800 s** | — | — | — | not in ledger | — | — | — |
| fireworks | 1939-01_p055 (security) | 840 | 580 | 1 | 52,813 | 18,517 (2,464) | $0.1447 | stop | 0 | 0 |
| fireworks | 1939-01_p061 (forward) | 420 | 257 | 1 | 29,070 | 9,799 (1,454) | $0.0780 | stop | 1 | 0 |
| fireworks | 1939-08_p043 (railroad) | 102 | 74 | 1 | 10,478 | 2,628 (642) | $0.0243 | stop | 0 | 0 |
| fireworks | 1982-06_p094 (claims) | 837 | 449 | 1 | 53,665 | 17,000 (517) | $0.1393 | stop | 0 | 324 |

- Four of five Fireworks reads came back, in 74 to 580 s (Baseten 16 to 42 s). The fifth, the 700-cell
  short-term table, **had no answer after 30 minutes** although its timeout was 1,200 s: the connection
  stayed open (an idle-read timeout does not fire while bytes keep arriving, or the host held the request).
  I stopped the run by hand at 23:10:13 UTC and left that read failed; it is not in the ledger, and the host
  may have billed it. Resumed from the cache, nothing was asked twice.
- Each answered read is one ask: none had to be asked again. Baseten and Fireworks each closed one bracket
  (D28) in the forward-exchange read; no Markdown fence was removed anywhere. Both hosts' answers report a
  model id equal to the configured one (`meta-models/muse-spark-open-1026`,
  `accounts/fireworks/models/muse-spark-open`), so neither tells us the checkpoint.
- Input is mostly the JSON Schema, which these backends put in the prompt: 10,000 to 54,000 tokens a page.

### 4.2 Do the hosts give the same page read?

| Page | Cells compared | Same value | Share (95% Wilson) | Figure cells same | Text cells same |
| --- | --: | --: | --- | --: | --: |
| 1939-01_p055 | 840 | 829 | 98.7% (97.7–99.3%) | 780/780 | 49/60 |
| 1939-01_p061 | 420 | 420 | 100.0% (99.1–100.0%) | 390/390 | 30/30 |
| 1939-08_p043 | 102 | 85 | 83.3% (74.9–89.3%) | 85/85 | 0/17 |
| 1982-06_p094 | 837 | 834 | 99.6% (99.0–99.9%) | 741/744 | 93/93 |
| **all four** | **2199** | **2168** | **98.6%** (98.0–99.0%) | **1996/1999** (99.85%) | **172/200** |

On the four pages both hosts read, **figures agree on 1,996 of 1,999 cells (99.85%)**; of the 31
cells that differ, 28 are label text (leader dots kept by Baseten on the railroad periods, section headings cut
short by Fireworks) and 3 are figures on the claims page (two differ by a printed footnote letter “r”, one by a digit). Fireworks' own boxes were missing for 324 of the claims
page's 837 cells (Baseten 81).

### 4.3 Re-reads and empty answers

| Host, setting | Cells | Gave a value (a figure, text or blank) | Blank-or-figure “can't read” (`null`) | **Empty** | Unparseable | Error | Empty rate (95% Wilson) | Empty, retried at 4,096 → answered | Output tokens, median / mean / p90 | Reasoning tokens, median | Cost a re-read (retry included) | Seconds a call, median / p90 / max |
| --- | --: | --: | --: | --: | --: | --: | --- | --: | --- | --: | --: | --- |
| baseten, low | 200 | 187 | 8 (4.0%) | 5 | 0 | 0 | 2.5% (1.1–5.7%) | 4/5 | 303 / 509 / 1,212 | 289 | $0.00284 | 2.5 / 6.2 / 10.8 |
| baseten, minimal | 200 | 182 | 10 (5.0%) | 8 | 0 | 0 | 4.0% (2.0–7.7%) | 8/8 | 334 / 532 / 1,242 | 320 | $0.00290 | 2.6 / 6.5 / 10.4 |
| fireworks, low | 200 | 93 | 103 (51.5%) | 3 | 0 | 1 | 1.5% (0.5–4.3%) | 3/3 | 264 / 444 / 998 | 250 | $0.00237 | 8.1 / 26.1 / 55.8 |
| fireworks, minimal | 200 | 95 | 103 (51.5%) | 2 | 0 | 0 | 1.0% (0.3–3.6%) | 2/2 | 264 / 464 / 1,136 | 249 | $0.00245 | 8.0 / 29.5 / 53.2 |

- **Empty** means the answer's text was empty: the reasoning used the whole 2,048-token allowance and left
  none for the answer (all 18 had finish reason “length”). It is rare here, **1.0% to 4.0%** by host and
  setting, 2.25% over all 800, against about 17% for Spark 1.3 at “low”. “Minimal” did not help: Baseten
  had more empties at “minimal” than at “low” (8 against 5; not significant).
- **Retry at double the allowance** (4,096, once): 17 of the 18 were answered (a value or `null`); the one
  that stayed empty was a Baseten “low” cell. Version 1's own retry is the same prompt with a note at the
  same allowance; it was not made, so what it would do is not measured.
- **No unparseable answer** and no D28 repair among 800 re-reads. **One error**: a Fireworks 60 s timeout.
  No HTTP 429 or 5xx on either host in the whole task, so no transport retry ever ran.
- **`null` is the bigger problem, on Fireworks only.** It answered `{"value": null}` (“can't read”) for 103
  of 200 crops at both settings, on all five pages and every column, whatever the crop's height (42–66% in
  every quartile) or box source; Baseten did for 8 and 10. Under policy v2 a `null` re-read sends the cell
  to review.

### 4.4 Do the hosts give the same re-read, and does a re-read match the page read?

| Compared | Cells | Same | Share (95% Wilson) |
| --- | --: | --: | --- |
| Baseten vs Fireworks re-read of the same crop, at “low” (both gave a value) | 92 (of 200; the other 108 had no value from at least one host) | 57 | 62.0% (51.7–71.2%) |
| Baseten vs Fireworks re-read of the same crop, at “minimal” (both gave a value) | 95 (of 200; the other 105 had no value from at least one host) | 63 | 66.3% (56.3–75.0%) |
| baseten re-read at “low” vs baseten's page read | 190 | 55 | 28.9% (23.0–35.8%) |
| baseten re-read at “low” vs fireworks's page read | 153 | 46 | 30.1% (23.4–37.8%) |
| fireworks re-read at “low” vs baseten's page read | 96 | 20 | 20.8% (13.9–30.0%) |
| fireworks re-read at “low” vs fireworks's page read | 78 | 23 | 29.5% (20.5–40.4%) |

Only 92 crops got a value from both hosts, because Fireworks said `null` on half. The low agreement of every
re-read with a page read is mostly the crops, not the readers: see §4.5.

### 4.5 Where the model's own boxes are

Version 1 takes a cell's box from the PDF's text layer where the figure is found there, else from the grid,
else from the model. With Spark Open's page read:

| Page | Host's own boxes vs the PDF's text layer: cells matched, median shift (x, y px), within 25 px in y | Box sources of the cells to re-read (ocr / grid / model) | Committed evidence, Spark 1.3: cells anchored to the layer |
| --- | --- | --- | --- |
| 1939-01_p051 | 323 cells, (-39, 198), 0 | 7 / 57 / 636 | 353/700 (S0+ocr) |
| 1939-01_p055 | 268 cells, (-119, 102), 45 | 98 / 247 / 453 | 318/840 (S0+ocr) |
| 1939-01_p061 | 216 cells, (-56, 107), 42 | 116 / 91 / 213 | 221/420 (S0+ocr) |
| 1939-08_p043 | 15 cells, (-18, 16), 13 | 26 / 53 / 23 | 18/102 (S0+ocr) |
| 1982-06_p094 | 209 cells, (-31, 169), 8 | 101 / 46 / 609 | 461/837 (S0+grid) |

Spark Open's boxes sit systematically below and to the left of the printed figures, by a different amount
on each page (median 16 to 198 px down on Baseten's reads; 16 to 394 on Fireworks'), so the ±100 px window
of the OCR step rarely finds them and most cells are re-read from a crop of the model's own, wrong place.
By box source, a Baseten “low” re-read matched the page read for 19 of 26 OCR-anchored cells, 18 of 44
grid-boxed and 18 of 117 model-boxed. This is about the page read, not the re-read model, and it is
not something the three questions asked, but it will dominate version 1's review rate on open weights.

### 4.6 A diagnostic outside the measurement: Fireworks and small crops

Not version 1's crops. Of the 48 cells where Fireworks said `null` and Baseten gave a figure, 16 (drawn with
seed 33) were sent again to Fireworks at “low”, the crop enlarged ×3 (Lanczos). **15 of 16 got a value**,
11 of them the same text as Baseten's. So the `null`s come from the size of the crop (the median crop is
90 × 48 px), not from the model's reading; a fix would change version 1's crops.

## 5. Speed (step 5)

40 re-reads at “low” on cells no earlier step had read (the same 40 on both hosts for each level), 1, 4
and 8 at once, hosts one after the other. Two cells in a run sometimes cut the same crop and prompt as another
and were answered from the cache (free, instant); they are left out of the live-call counts and rates.

| Host | At once | Live calls (cache hits left out) | Wall seconds | Re-reads a second | Seconds a call, median / p90 / max | Layer overhead a call, mean / max (s) | `null` | Empty | Errors, retries |
| --- | --: | --: | --: | --: | --- | --- | --: | --: | --- |
| baseten | 1 | 39 (1 hits) | 129.8 | **0.300** | 3.0 / 5.3 / 8.1 | 0.13 / 0.15 | 6 | 1 | 0, 0 |
| baseten | 4 | 40 (0 hits) | 41.4 | **0.966** | 2.8 / 7.8 / 9.3 | 0.15 / 0.50 | 1 | 0 | 0, 0 |
| baseten | 8 | 38 (2 hits) | 17.9 | **2.117** | 2.7 / 5.4 / 6.8 | 0.23 / 0.90 | 3 | 0 | 0, 0 |
| fireworks | 1 | 39 (1 hits) | 559.3 | **0.070** | 10.7 / 31.1 / 41.7 | 0.13 / 0.14 | 18 | 0 | 0, 0 |
| fireworks | 4 | 40 (0 hits) | 142.3 | **0.281** | 8.9 / 29.2 / 45.9 | 0.15 / 0.51 | 22 | 1 | 0, 0 |
| fireworks | 8 | 38 (2 hits) | 98.0 | **0.388** | 9.8 / 28.5 / 48.4 | 0.21 / 0.89 | 14 | 0 | 0, 0 |

- **Baseten scales almost linearly** (×3.2 from 1 to 4 at once, ×2.2 from 4 to 8) at a median 2.7–3.0 s a
  call. **Fireworks does not** (×4.0, then ×1.4) and its calls take 9–11 s at the median with a 28–31 s p90:
  at 8 at once it does a fifth of Baseten's work. (P30 found Fireworks quicker on short answers; today it
  was about three times slower, so host speed is not a constant.) Beyond 8 at once was not measured.
- **The model layer is safe to call from many threads**, and was (8 at once on both hosts, 1,155 calls
  across the task, no error from the layer): `Cache` single-flights an identical request under a thread
  lock and a file lock, `BudgetGuard` reserves and records under a lock, and the SDK client is shared. Each
  identical-request pair in a run was asked once. **One thing would limit it at higher concurrency**: every
  call's spend check re-reads and parses the whole spend ledger under the guard's lock (`BudgetGuard.spent`):
  0.126 s a call at 82,000 lines (it grows with the ledger). That is the “layer overhead” column
  (mean 0.13–0.23 s, worst 0.9 s at 8 at once, queueing on the lock) and caps the layer near 8 calls a
  second in total, which is not binding at 8 at once with 2.7 s calls (about 3 a second) but would be at about 20 at once.
  Keeping a running total in memory would remove it; I changed nothing.
- A call that times out or hangs is not in the ledger (no usage is returned), so the ledger understates
  what the host may bill: 4 timeouts at 60 s and the one 30-minute page read.

## 6. What is recorded for every call (step 6)

`results/openw_measure/calls.jsonl` has **1,155 lines, one for every call** through the model layer (cache
hits included, marked `cache_hit`). For a call that reached the host: `host`, `effort` (the role's
setting) and `effort_sent` (what went in the request), `response_model` (the id the response reports),
`input_tokens`, `cached_input_tokens`, `output_tokens` (reasoning included), `reasoning_tokens`,
`cost_usd`, `wall_s` (the whole call through cache, cap and retries), `http_s` (the host's part),
`finish_reason`, `empty`, `parse_ok` and `parse_error`, `brackets_closed` (a D28 repair), `retries`
and `failed_attempts` (each HTTP attempt that failed, with its status), `in_flight_at_start`, and on an
error `error.type`, `error.status` and a scrubbed message. Cell-level outcomes are in `rereads.jsonl`,
reads in `reads/`, boxes in `boxes/`, the draw in `draw.json`, speed in `speed.json`, the probe in
`probe.json`, the diagnostic in `diagnose.json`, every figure in this report in `summary.json`.

- Spend: **Baseten $2.0773, Fireworks $1.7487, $3.83 of the $8**, equal to the ledger's own lines to the cent
  (`recorded_cost_by_host` in `summary.json`). The caps for this task were each host's ledger total at the
  start plus $3.80 (`caps.json`); Meta's was 0, and no Meta call was made.
- Errors: Baseten 2 (HTTP 400, the invalid-value probes); Fireworks 18 HTTP 400 (refused settings) and 4
  timeouts at 60 s; no 429 and no 5xx; transport retries: 0.
- D28 repairs: 2 (one bracket each, in the two forward-exchange page reads). Fences removed: 0.

## 7. The full run at version 1's size (step 7)

58 pages, 33,114 cells read, 29,018 blind re-reads. Page reads are the measured page of each family priced
for its 12 (10 for claims) pages; re-reads are the 200 measured cells, weighted to the held-out mix of
cells, with a 95% bootstrap interval (cells resampled within each page, `default_rng(0)`). **Low / mid /
high**: pages at one ask each / as measured / every page asked twice; re-reads at the bootstrap's lower end
/ the weighted mean / its upper end. Time: low = 8 at once, high = 4 at once (version 1 ran 8), pages and
re-reads one after the other as version 1 ran them.

| Part | Host | Cost, low / mid / high | Hours, low – high |
| --- | --- | --- | --- |
| 58 page reads | baseten | $5.70 / $5.70 / $11.40 | 0.07 – 0.13 |
| 58 page reads | fireworks | $5.75 / $5.75 / $11.51 | 1.29 – 2.57 (a floor) |
| 29,018 re-reads | baseten | $75.82 / $91.64 / $109.36 | 3.81 – 8.34 |
| 29,018 re-reads | fireworks | $61.93 / $71.51 / $82.18 | 20.77 – 28.69 |

| Option | Cost, low / mid / high | Wall time, low – high | Needs from each host (low / mid / high) against what its cap has left | Fits? |
| --- | --- | --- | --- | --- |
| all Baseten | $82 / $97 / $121 | 3.9 – 8.5 h | baseten: $82 / $97 / $121 of $55.77 | no, at any of the three |
| all Fireworks | $68 / $77 / $94 | 22.1 – 31.3 h (a floor) | fireworks: $68 / $77 / $94 of $38.03 | no, at any of the three |
| page reads Baseten, re-reads Fireworks | $68 / $77 / $94 | 20.8 – 28.8 h | baseten: $6 / $6 / $11 of $55.77; fireworks: $62 / $72 / $82 of $38.03 | no, at any of the three |
| page reads Fireworks, re-reads Baseten | $82 / $97 / $121 | 5.1 – 10.9 h (a floor) | baseten: $76 / $92 / $109 of $55.77; fireworks: $6 / $6 / $12 of $38.03 | no, at any of the three |

- **No option fits.** The re-reads alone ($76 to $109 on Baseten, $62 to $82 on Fireworks) exceed what is left
  under the standing caps, which I took as the code's defaults, $80 and $40, less the ledger ($55.77 and
  $38.03 left; `.env` was not read). The two hosts together have $93.80 left, so only a split of the
  re-reads across both hosts, at the low end, could fit, and Fireworks' re-reads come back `null` half the time.
- A re-read costs about **$0.0028**, mostly reasoning: a median 289 reasoning tokens against 15 for the
  answer; the input (335 tokens, 256 of them cached, billed as ordinary input) is about a sixth. Calls of 1,000
  output tokens or more are a sixth of the calls and 31–44% of the cost; one that uses the whole allowance
  costs $0.009. Version 1's whole deep check cost $2.92.
- The Fireworks time for page reads is a floor: the 700-cell read is counted at the 1,800 s it was stopped at.
  The Fireworks page-read cost for that family is Baseten's (same price; the matched pages' token counts
  agree to within 8%).
- A re-read's cost is per re-read, and does not depend on whether the crop is right; the review rate does.
- Not in the estimate: SAM (Meta's, replayed from the cache), the sweep (replayed), and any retry beyond the
  one at 4,096 tokens.

## 8. The code freeze (step 8), nothing changed

**Commits from `run-real-treasury` (b8ff15d) to main that touch paths the deep check used.** The deep check
imports 32 modules of `src/archivist` and reads `config/real_test.toml` and every file in `templates/`
(`frozen()` compares `src`, `config`, `templates`, `pyproject.toml` and `uv.lock`; the last two have not
changed). Four commits touch those paths:

| Commit | What it touches that the deep check uses | Could it change what version 1 does on single-layout pages? |
| --- | --- | --- |
| 9b6cf44 P21d, multi-panel templates | `doctypes/template.py` (panel classes; `TemplateType` split its prompt into `rows_and_columns`, gained `_id` and `rule_name`), `templates/test.py` (type hints, a panel branch in `read_pages`), `templates/draft.py` | **No.** For all five families the prompts, schemas, field ids, re-read prompts, the parse of a canned answer, the checks run on it, the output allowances and the template hashes are identical when the tag's code and main's code are run side by side (`openw/equivalence.py`, `equivalence_tag.json` against `equivalence_main.json`, equal). `test.py`'s functions the deep check calls (`output_tokens`, `blind_check`, `reread_cells`, `agreed`) differ in hints only. |
| a317068 P28, family choice | `templates/ocr.py` (an `frb-` branch in `words`), `templates/pages.py` (an `frb-` pattern and branch in `resolve`) | **No**: a Treasury reference takes the same path. |
| 3b6ab3f P28, four drafts | no imported module; adds `templates/frb_*` (draft files, loaded and validated at import, not enabled) | **No**, but `templates/` is part of what `frozen()` compares. |
| e9d30c2 P30, Fireworks | `models/budget.py` (a third entry in `BACKEND_CAPS`), `models/registry.py` (registers the backend), `templates/real_test.py` (`set_caps` uses `record.get(backend, 0.0)`) | **No** for any Meta call. It does change what `set_caps` does with a `caps.json` that has no Fireworks entry (cap 0 instead of a `KeyError`). |

The other commits since the tag (labels, scorer, deviations) touch `results/`, `labelling/` and the plan.
All the same, **`frozen()` fails on main** (`src` and `templates` differ from the tag), so the held-out runner
refuses to run there.

**Does the Check's replay cover a template run? No.** `replay.py` replays 11 runs, all synthetic ledger
cards and payment memos (`test-baseline`, `test-baseline-open`, three arms on dev, val and test); its own
docstring says an approved template “plays no part”. A template run is covered only by
`templates.test --replay` (drafts only; an approved template is never retested) and by `templates.recount`.
**Both conditions hold on main's code**, tried in this worktree before any file of mine existed: pytest
1,152 passed, and `replay` passed with all 11 runs identical and the ledger unchanged; and `recount` rewrote
`results/templates/recount.md` differing only in the quoted Meta spend ($4.3029 → $10.0476), which is how
the plan's Deviations read that condition (restored afterwards; that run needed the development pages of
the Comptroller and Federal Reserve sources linked as well).

**What the held-out runner would need to run a second configuration** (read from `real_test.py`; nothing
changed):

1. A way to name the configuration: `CONFIG = config/real_test.toml` is a constant and `deep` takes no `--config`.
2. **Its own output directory.** The directory is `results/real_test/held_out/` and a start resumes from what
   is there: with the first run's `predictions.jsonl` complete, a second configuration would read nothing, run
   its re-reads over the first run's reads, and **overwrite `verdicts.jsonl` and `run.json`**.
3. The same 58 pages. They come from `titles.jsonl` and `sample.json` of the first run's sweep (Spark 1.3's
   classes): a second sweep on another model would classify 4,569 pages again and could draw other pages. The
   second run must read those two files and not redo the sweep.
4. Caps for its hosts. `caps()` records Meta and Baseten only; main's `set_caps` then gives Fireworks 0. An
   allowance for each host used must be recorded, and Meta's kept for SAM's replay (identical images, so
   cache hits: free) from the same cache.
5. **Backends that can carry version 1.** The committed Baseten and Fireworks backends have a fixed 60 s timeout
   and no `timeout_s` (a page read needs minutes: 16 to 580 s here), and refuse “minimal”. A config naming
   `timeout_s` or `minimal` would not load. That is a change under `src/archivist/models/`, a frozen path.
6. A new tag and gate. `frozen()` compares with `TAG`, the pre-registration says no Baseten model is used and
   that each configuration runs once, and `labelling.score` refuses any code but the tag's. A second
   configuration needs its own tag, gate and pre-registration entry, and scoring on the 400 labels (drawn from
   the first read's rows) needs the second read to have returned those cells.

## 9. What was done differently from the brief, and the limits

**The main checkout.** The only two things done there: `git worktree add -b openw-measure .worktrees/openw
main` (which also writes `.git/worktrees/openw` and the branch ref) and one line, `.worktrees/openw`,
appended to `.git/info/exclude`. Its `git status` before and after is identical: the one untracked file, your
live `results/real_test/held_out/labels/labels.jsonl`. I only ran `git status` there, which can refresh its index.

**In the worktree.**
- `data/real` is not linked whole. The worktree already holds its three tracked files, so a directory link
  would have clobbered them, and the gitignore rule `data/real/pages/` matches a directory, not a link to one.
  I made real `pages/` and `pdf/` directories (ignored) and linked **only the 15 development issues** into
  them (and, for the `recount` check, the development volumes/issues of the other two sources). Nothing
  held out is reachable from the worktree, none was read, and no link is tracked (`git status` shows none).
- `cache/` is an APFS copy of main's cache (read-only on main) so that the Check's replay can run; the
  measurement's own calls used `results/scratch/openw/cache`. The held-out run's entries in the copy
  were not opened.
- `.env` is a symlink to main's; I never read it. The two hosts' variables were checked for presence only.
- New files only: `openw/` (code, config, `equivalence.py`), `tests/test_openw_measure.py`,
  `results/openw_measure/`, plus the appended lines of `results/spend_ledger.jsonl`. No committed config,
  template or frozen path was edited, and `src/`, `config/` and `templates/` are as on main.

**A shim, not the committed backends alone.** Calls go registry → cache → budget → backend as always, through
`OpenwBaseten` and `OpenwFireworks`, which are the committed classes (same name, so the same ledger lines,
caps and cache keys; same payload, schema in the prompt and repairs) with three differences: they take
“none” and “minimal”, which the committed constructors refuse; their timeout is 1,200 s for the page-read
roles (version 1's) instead of the fixed 60; and they record every HTTP attempt (`openw/spy.py`).

**Added after the first results were seen** (the “fixed in advance” section is unchanged above): (a) the
settings the APIs' error texts named (`max`, `adaptive`, an integer, a boolean); (b) the second arm, the
same 200 crops at “minimal”, because the four-cell probe left it open; (c) the upscaling diagnostic in §4.6,
which is not version 1's crops; (d) the 30-minute limit on the Fireworks page read, which I set while it was
running; (e) counting speed over live calls only, after two cells turned out to share a crop.

**Limits.** One page a family, 40 cells a page: the cost ranges are bootstrap intervals over those cells and
the pages' own token counts, not a held-out sample. One speed run for each host and level, hosts one after the
other, so load at the time is in the numbers; page reads ran 5 at once on a host, not 8. Prices are the
config's ($1.25 input, $4.25 output a million, cached input at the full rate), not an invoice, and a timed-out
or hung call is not in them. “Empty” is an answer with no text; `null` is a different outcome and is reported
apart. Nothing here is scored for correctness: there are no labels for these pages.

**Not touched:** no held-out page was opened, listed or sent; no call to Meta's API was made (its cap was 0);
no cap was changed; PREREGISTRATION_REAL.md is unchanged.

## 10. Recommendation, for you to decide

1. **One host: Baseten, for both jobs.** Fireworks has the same price and nothing in return: page reads 4 to
   13 times slower (and one never came back), re-reads about a fifth of Baseten's speed at 8 at once, and
   `null` on half of version 1's crops unless they are enlarged. If a second host is needed only for cap
   room, give it the page reads (its figures matched Baseten's on 99.85% of cells), not the re-reads, and
   expect at least 1.3 hours for them and the risk of a hung call.
2. **Reasoning setting: “low”, for page reads and re-reads.** “Minimal” is accepted but not honoured, so
   pre-register “low” and say why; the committed backends refuse “minimal” anyway. Keep a retry rule for the
   2.5% of re-reads that come back empty: one more ask at double the allowance fixed 17 of 18.
3. **Calls at once: 8**, as version 1 ran, for about 2.1 re-reads a second on Baseten (4 at once would
   double the time). Faster than that was not measured; the ledger parse limits the layer to about 8 calls a
   second whatever the host does.
4. **Code to freeze: a new tag, not today's main as it is.** Main behaves exactly as the tag does for the
   five single-layout families (§8), and its replay and recount hold, but the open-weights backends cannot
   run version 1 (60 s timeout, no `timeout_s`), and the runner has no second configuration. Freeze main plus
   the smallest additions: `timeout_s` for the two backends, a `--config` and an output directory of its own
   for the runner, reading the first run's sweep and `sample.json`, and caps for the hosts used; keep prompts,
   schema, templates, pipeline and `grid` as they are; run pytest, replay and recount at that tag.
5. **Decide about the boxes before pre-registering.** On open weights version 1's box step, unchanged, will
   anchor few cells and send most crops to the wrong place, so a large share will be reviewed: a result
   worth pre-registering as expected, or a reason to change the box step (a different configuration).
6. **Expected cost and time on Baseten: about $97 (range $82–121) and 3.9 to 8.5 hours**, plus roughly
   5 minutes for the 58 page reads. **It does not fit the $55.77 left under Baseten's cap**; whether to raise
   the cap, split the re-reads over both hosts' remaining $93.80, or run fewer pages is your decision, and I
   changed nothing. Version 1's whole deep check cost $2.92 and ran 12 h 9 min.
