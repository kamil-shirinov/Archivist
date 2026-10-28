# Can the table grid be found from the page alone?

Made by `python -m archivist.templates.grid_probe`: a feasibility probe in plain image code, no model call, on the development pages the drafts were drafted from; its thresholds were set by looking at these same pages, so it is not a held-out result. The body of the table is located from the first read's S0 boxes of its figure cells; inside it, with every unbroken stroke of a rule's length taken out, columns are the runs of pixel columns carrying more ink than the paper's floor, and rows are counted column by column as the bands of pixel rows carrying ink (found: the median over the columns, with its range). Ink: at or below the page's Otsu threshold. Ruled lines: unbroken strokes at least 25% of the page's width or height. Read: what the draft's first read found there (rows and figure columns with at least one figure). Boxes on a row: the share of the first read's figure boxes whose centre lies in a row band of the column found under it.

| Family | Page | Layout rows x figure columns | Rows read / found | Figure columns read / found | Boxes on a row | Ruled lines (across / down) |
|---|---|---|--:|--:|--:|--:|
| `outstanding_forward_exchange_contracts` | 1939-01_p061 | 5 x 13 | 4 / 4 (3-4) | 13 / 13 | 42% | 6 / 8 |
| `outstanding_forward_exchange_contracts` | 1939-07_p085 | 5 x 13 | 5 / 4 (3-5) | 13 / 12 | 48% | 10 / 10 |
| `outstanding_forward_exchange_contracts` | 1939-12_p060 | 5 x 13 | 4 / 4 (2-4) | 13 / 13 | 86% | 8 / 1 |
| `receipts_and_expenditures_under_railroad` | 1939-08_p043 | 17 x 5 | 17 / 10 (1-16) | 5 / 6 | 33% | 8 / 0 |
| `receipts_and_expenditures_under_railroad` | 1939-10_p024 | 17 x 5 | 17 / 12 (1-17) | 5 / 5 | 47% | 6 / 0 |
| `receipts_and_expenditures_under_railroad` | 1939-12_p025 | 17 x 5 | 17 / 13 (1-17) | 5 / 5 | 14% | 8 / 3 |
| `security_transactions_as_reported_by` | 1939-01_p055 | 60 x 13 | 48 / 37 (22-45) | 13 / 13 | 42% | 3 / 15 |
| `security_transactions_as_reported_by` | 1939-07_p075 | 60 x 13 | 40 / 30 (24-33) | 13 / 13 | 42% | 3 / 15 |
| `security_transactions_as_reported_by` | 1939-12_p055 | 60 x 13 | 48 / 24 (20-41) | 13 / 13 | 31% | 0 / 0 |
| `short_term_foreign_liabilities_as` | 1939-01_p051 | 50 x 13 | 40 / 36 (34-39) | 13 / 6 | 54% | 4 / 14 |
| `short_term_foreign_liabilities_as` | 1939-07_p071 | 50 x 13 | 41 / 31 (25-33) | 13 / 8 | 62% | 3 / 8 |
| `short_term_foreign_liabilities_as` | 1939-12_p053 | 50 x 13 | 40 / 29 (27-32) | 13 / 2 | 42% | 3 / 0 |
| `total_claims_by_country` | 1982-06_p094 | 93 x 8 | 86 / 79 (78-81) | 8 / 8 | 47% | 28 / 0 |
| `total_claims_by_country` | 1983-06_p092 | 93 x 8 | 86 / 81 (80-85) | 8 / 8 | 42% | 26 / 0 |
| `total_claims_by_country` | 1984-06_p058 | 93 x 8 | 86 / 69 (61-73) | 8 / 8 | 49% | 24 / 0 |
| `total_liabilities_by_country` | 1982-06_p091 | 86 x 9 | 86 / 82 (79-86) | 9 / 9 | 38% | 9 / 0 |
| `total_liabilities_by_country` | 1983-06_p097 | 86 x 9 | 86 / 73 (71-74) | 9 / 9 | 48% | 24 / 0 |
| `total_liabilities_by_country` | 1984-06_p055 | 86 x 9 | 86 / 76 (74-81) | 8 / 8 | 39% | 2 / 0 |
