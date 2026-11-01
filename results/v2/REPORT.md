# P40 — boxes anchored to the table: development results

**Development only. The adoption rule fails; keep v1.**

The candidate is an opt-in `S0+table-v2` function beside the unchanged `S0+grid`. It uses this page’s unique OCR figures to establish columns and row consensus, equal-count label occurrences to distinguish repeated dates, and ruled lines/ink to bound cells. It takes the token physically in the named cell even when its value differs from the first read. Ambiguous cells retain v1 with an explicit source. No prompt, reader, template, decision, policy, tag or scorer changed.

The prewritten gate in PLAN.md requires strict pooled improvement in both whole-figure containment and blind re-read agreement, separately for both readers. Ties keep v1. The candidate hash and rule/sample hashes were recorded before paired re-reads.

| Reader | Whole OCR figure contained, v1 → v2 | Paired re-read agreement, v1 → v2 | Gate |
|---|---|---|---|
| meta | 2726/2739 (99.53%) → 2728/2739 (99.60%) | 406/600 (67.67%) → 372/600 (62.00%) | fail |
| baseten | 254/1003 (25.32%) → 1000/1003 (99.70%) | 52/200 (26.00%) → 102/200 (51.00%) | pass |

Fifteen Spark 1.3 drafting pages and the five P33 Baseten Open pages; no fresh extraction. Forty cells per page/reader, seed 40, fixed before v2 geometry: 600 Spark and 200 Open cells, both strategies on each cell. Re-reads use the existing prompts, crop padding, schema, 2,048-token allowance, retry and template canonical comparison. Spark reasons at minimal, Open at low as in P33. Failures/nulls count as disagreements. No sample cell is dropped.

| Reader | Family | Whole figure v1 → v2 | Agreement v1 → v2 |
|---|---|---|---|
| meta | outstanding_forward_exchange_contracts | 449/449 → 449/449 | 80/120 → 76/120 |
| meta | receipts_and_expenditures_under_railroad | 45/46 → 45/46 | 79/120 → 71/120 |
| meta | security_transactions_as_reported_by | 607/610 → 607/610 | 81/120 → 71/120 |
| meta | short_term_foreign_liabilities_as | 1026/1027 → 1026/1027 | 78/120 → 80/120 |
| meta | total_claims_by_country | 599/607 → 601/607 | 88/120 → 74/120 |
| baseten | outstanding_forward_exchange_contracts | 105/214 → 214/214 | 11/40 → 26/40 |
| baseten | receipts_and_expenditures_under_railroad | 14/15 → 14/15 | 24/40 → 21/40 |
| baseten | security_transactions_as_reported_by | 79/258 → 258/258 | 8/40 → 24/40 |
| baseten | short_term_foreign_liabilities_as | 0/317 → 317/317 | 0/40 → 16/40 |
| baseten | total_claims_by_country | 56/199 → 197/199 | 9/40 → 15/40 |

| Reader | OCR centre contained v1 → v2 | New figure-box sources |
|---|---|---|
| meta | 2728/2739 (99.60%) → 2728/2739 (99.60%) | table:ink: 1113/6674, table:ocr: 3571/6674, v1:grid: 1429/6674, v1:model: 325/6674, v1:ocr: 236/6674 |
| baseten | 267/1003 (26.62%) → 1000/1003 (99.70%) | table:ink: 436/2143, table:ocr: 1353/2143, v1:grid: 61/2143, v1:model: 252/2143, v1:ocr: 41/2143 |

Baseline diagnosis:

| Reader | Unique OCR references | Model one row high / low | V1 one row high / low | V1 full figure |
|---|---:|---:|---:|---:|
| meta | 2739 | 543 / 557 | 0 / 0 | 2726 |
| baseten | 1003 | 26 / 43 | 3 / 3 | 254 |

The strict containment proxy requires at least three digits, a unique first-read figure and a unique full-page OCR match. It does not use either predicted box to choose the reference. It is conditioned on first-read/OCR agreement and excludes short/repeated values; it is not human-scored citation accuracy or value accuracy. Row offsets round centre displacement divided by PDF line pitch; remote false digit matches and unavailable pitch remain in baseline.json.

The repeated-label diagnostic uses equal-count OCR stub occurrences in table order, independently of model-box proximity. It is exploratory, uses the candidate’s row resolver on the original v1 boxes, and does not enter the adoption gate:

| Reader | Matched figure cells | V1 one row high | V1 one row low | V1 farther away |
|---|---:|---:|---:|---:|
| meta | 2486 | 139 | 46 | 159 |
| baseten | 1028 | 18 | 12 | 766 |

Why: v1 searches for matching digits within 100 px of the model box, maps columns using model/nearby OCR centres and allows label matching only near the model’s row. Repeated dates can leave short values without anchors or preserve a wrong neighbouring band. Open’s page-specific drift is much larger than that window, so its wrong model positions propagate into the grid. Structural row and column anchors remove much of that dependence, but sparse/misread OCR still leaves fallbacks, and tighter/moved crops can reduce agreement. Neither OCR agreement nor re-read agreement proves correctness.

| Reader | Page | References | Full figure v1 → v2 | Agreement v1 → v2 |
|---|---|---:|---:|---:|
| meta | 1939-01_p051 | 317 | 317 → 317 | 25 → 23 |
| meta | 1939-07_p071 | 356 | 355 → 355 | 29 → 32 |
| meta | 1939-12_p053 | 354 | 354 → 354 | 24 → 25 |
| meta | 1939-01_p055 | 269 | 269 → 269 | 29 → 24 |
| meta | 1939-07_p075 | 111 | 109 → 109 | 22 → 21 |
| meta | 1939-12_p055 | 230 | 229 → 229 | 30 → 26 |
| meta | 1939-01_p061 | 214 | 214 → 214 | 32 → 28 |
| meta | 1939-07_p085 | 20 | 20 → 20 | 13 → 13 |
| meta | 1939-12_p060 | 215 | 215 → 215 | 35 → 35 |
| meta | 1939-08_p043 | 15 | 14 → 14 | 27 → 24 |
| meta | 1939-10_p024 | 15 | 15 → 15 | 27 → 28 |
| meta | 1939-12_p025 | 16 | 16 → 16 | 25 → 19 |
| meta | 1982-06_p094 | 248 | 247 → 247 | 29 → 28 |
| meta | 1983-06_p092 | 356 | 351 → 353 | 31 → 18 |
| meta | 1984-06_p058 | 3 | 1 → 1 | 28 → 28 |
| baseten | 1939-01_p051 | 317 | 0 → 317 | 0 → 16 |
| baseten | 1939-01_p055 | 258 | 79 → 258 | 8 → 24 |
| baseten | 1939-01_p061 | 214 | 105 → 214 | 11 → 26 |
| baseten | 1939-08_p043 | 15 | 14 → 14 | 24 → 21 |
| baseten | 1982-06_p094 | 199 | 56 → 197 | 9 → 15 |

Per-cell targets, boxes, sources, rejected row mappings, unmatched label counts and ruled-line diagnostics are in geometry.json; every paired answer and failure is under rereads/. The occurrence diagnostic is repeated_label_diagnostic.json. Sources use `table:ocr`, `table:ink`, or explicit `v1:ocr/grid/model` fallback. In particular 1984-06 p058 has only three strict OCR references and no v2 column mapping: that layout remains a limitation, rather than being inferred from another page.

Cost: Meta **$0.048652 / $5**, Baseten **$1.051417 / $5**; no new Fireworks, Glimmer or SAM calls. caps.json records starting totals and absolute ceilings; answered calls are in the canonical spend ledger. The failed sandbox network pass is preserved separately (EXECUTION.md); connection failures have no provider usage recorded. These are model-reported token costs, not invoices.

**No v2 run is frozen for adoption and no held-out pre-registration is drafted:** the prewritten gate failed. The development candidate is retained for review, with its failures. A future candidate needs another prospective development plan. If one qualifies, the requested draft must reuse the same 58 pages and 400 drawn cell IDs, reuse the first reads, re-read only those cells and use v1’s unchanged scorer and all reporting variants; any optional Open arm needs its own declared freeze and budget. This task authorizes no held-out run.
