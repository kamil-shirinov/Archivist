# Page X-rays (P24)

Each image is one page drawn with how it was read. Made by `python -m archivist.templates.xray` from the cache and the committed run alone: both spend caps are set to zero first, so a read that is not cached stops that family, and no model is called. Each image has its legend at the top.

What the marks mean:

- **Box outline, by where the box came from.** Blue: OCR anchor, the figure's own box in the archive PDF's OCR layer. Purple: grid, the cell of the table's grid found in the page by plain code. Black dashed: the model's own box, the fallback. On the ledger card, sky blue is the model's box corrected from the page's ink (the model's own, before the fit, is the thin grey box) and black dashed is a box the fit left as it was.
- **Grid.** Sky-blue stripes are the table's columns, grey lines the edges of its row bands, skewed with the page. Found again by the same plain code the S0+grid strategy runs. A family tested under S0+ocr, before the grid existed, has its grid drawn for context only.
- **Occluders.** Orange boxes, hatched, are SAM boxes recorded for the page. The segmenter's backend keeps a box, a label and a score, not a mask, so a box is what is drawn.
- **Outcome of a cell, from the arithmetic test's own judgement.** Fill: green, a rule that covers the cell held; vermillion, a rule failed; yellow, the cell's two reads disagree. Mark: tick (passed), cross (failed), not-equal sign (reads disagree), ring (reads agree, no rule evaluated). A cell never read twice has neither. Blank cells are not drawn.

## Images

### `1939-01_p061.png` - outstanding_forward_exchange_contracts - 1939-01_p061

A page of the approved template `outstanding_forward_exchange_contracts`, page 1939-01_p061 of the Treasury Bulletin, development side of the split; the first page its committed evidence lists. Boxes by S0+ocr. The grid is for context only. The grid found 13 columns and 15 row bands. No SAM occluder is recorded for it: the template test never runs the segmenter, and the cache holds none for this page. The replay's page record differs from the committed one in agree 188 then, 199 now; P26 reads a space after a thousands comma ("29, 139") as part of the figure, so more reads agree now (results/templates/recount.md). The cells drawn are what the cache gives now.

Cells: 336 cells drawn (84 blank not drawn). boxes: 108 model, 228 ocr. reads: 199 agree, 111 disagree, 26 not re-read. rules: 83 passed, 0 failed, 253 not evaluated.

### `1939-08_p043.png` - receipts_and_expenditures_under_railroad - 1939-08_p043

A page of the approved template `receipts_and_expenditures_under_railroad`, page 1939-08_p043 of the Treasury Bulletin, development side of the split; the first page its committed evidence lists. Boxes by S0+ocr. The grid is for context only. The grid found 5 columns and 19 row bands. No SAM occluder is recorded for it: the template test never runs the segmenter, and the cache holds none for this page. The replay's page record is the committed one, count for count.

Cells: 102 cells drawn (0 blank not drawn). boxes: 76 model, 26 ocr. reads: 37 agree, 27 disagree, 38 not re-read. rules: 4 passed, 0 failed, 98 not evaluated.

### `1939-01_p055.png` - security_transactions_as_reported_by - 1939-01_p055

A page of the approved template `security_transactions_as_reported_by`, page 1939-01_p055 of the Treasury Bulletin, development side of the split; the first page its committed evidence lists. Boxes by S0+ocr. The grid is for context only. The grid found 13 columns and 48 row bands. No SAM occluder is recorded for it: the template test never runs the segmenter, and the cache holds none for this page. The replay's page record differs from the committed one in agree 557 then, 562 now; P26 reads a space after a thousands comma ("29, 139") as part of the figure, so more reads agree now (results/templates/recount.md). The cells drawn are what the cache gives now.

Cells: 684 cells drawn (156 blank not drawn). boxes: 332 model, 352 ocr. reads: 447 agree, 177 disagree, 60 not re-read. rules: 107 passed, 0 failed, 577 not evaluated.

### `1939-01_p051.png` - short_term_foreign_liabilities_as - 1939-01_p051

A page of the approved template `short_term_foreign_liabilities_as`, page 1939-01_p051 of the Treasury Bulletin, development side of the split; the first page its committed evidence lists. Boxes by S0+ocr. The grid is for context only. The grid found 2 columns and 40 row bands. No SAM occluder is recorded for it: the template test never runs the segmenter, and the cache holds none for this page. The replay's page record differs from the committed one in agree 429 then, 444 now; P26 reads a space after a thousands comma ("29, 139") as part of the figure, so more reads agree now (results/templates/recount.md). The cells drawn are what the cache gives now.

Cells: 570 cells drawn (130 blank not drawn). boxes: 189 model, 381 ocr. reads: 356 agree, 162 disagree, 52 not re-read. rules: 53 passed, 0 failed, 517 not evaluated.

### `test-archivist-A_card-02-2.png` - card-02-2 - synthetic ledger card, run test-archivist-A

Synthetic ledger card card-02-2 of the committed run test-archivist-A (citations S0+ink), chosen by the fixed rule in the module: the first card, in page order, with an occluded field, a failed check and a re-read that balances. Boxes, re-read status, checks and occluders are the run's own record (`results/runs/test-archivist-A/verdicts.jsonl`); 76 boxes were moved by the ink fit. A rule "passed" here means the field's re-read balances (an equation holds for it); "failed" means a check flagged the extracted value (arithmetic, words against figures, or against the memo); anything else is not evaluated. The image is read from the split's images; nothing is run on it.

Cells: 77 cells drawn (18 blank not drawn). boxes: 76 ink, 1 kept. reads: 21 agree, 55 disagree, 1 not re-read. rules: 5 passed, 27 failed, 45 not evaluated.

## Skipped

- `total_claims_by_country`: a read it needs is not in the cache under the current code: the lookup missed with both spend caps at zero, so nothing was called
