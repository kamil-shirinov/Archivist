# Held-out scoring — Treasury Bulletin (PREREGISTRATION_REAL.md)

Code: `run-real-treasury` (b8ff15d), checked frozen; scorer sha256 `82e56a8613e7`. Weights' page counts: confirmed. Intervals: 95%, page bootstrap within strata (rates) or Wilson (counts).

Label files (sha256): `draw.json` b575cc271445abc1621bfd942362c7b3db6e61b9e26ceca83648f0b580492168, `layouts_checked.jsonl` e275a7aedbe8fde7a396b3c5ad3a1caa3db8a23ef7946a243b5767d81d0f9bdd, `labels.jsonl` 5f98f48235f3f4396594b11fe5ccd4d98b66c98629761efa330f80f3134de118, `pages_checked.jsonl` d511c97a98be9380d60acf027656190fcb80d84ad182f7e3bfbb987ee84455b2

## Labelled cells

| Variant | Cells | Single read error | Archivist error (accepted) | Catch rate | R1 |
|---|--:|---|---|---|---|
| left_out/as_run | 162 | 16.7% (8.2%–25.8%) | 18.7% (1.6%–31.8%) | 44.9% (27.9%–94.4%) | not met |
| left_out/failed_to_review | 162 | 16.7% (8.2%–25.8%) | 18.7% (1.6%–31.8%) | 44.9% (27.9%–94.4%) | not met |
| kept/as_run | 400 | 41.1% (30.6%–52.4%) | 36.9% (24.7%–50.4%) | 74.2% (60.3%–84.9%) | not met |
| kept/failed_to_review | 400 | 41.1% (30.6%–52.4%) | 36.3% (24.5%–50.1%) | 75.5% (62.3%–85.8%) | not met |

With classified-page weights instead (Deviations, 2026-10-30): left_out/as_run: single read 15.7% (9.1%–22.4%), Archivist 15.3% (2.2%–26.2%), R1 not met; left_out/failed_to_review: single read 15.7% (9.1%–22.4%), Archivist 15.3% (2.2%–26.2%), R1 not met; kept/as_run: single read 35.3% (27.6%–43.5%), Archivist 29.1% (19.4%–39.3%), R1 not met; kept/failed_to_review: single read 35.3% (27.6%–43.5%), Archivist 29.0% (19.2%–39.5%), R1 not met.

By stratum:

| Variant | Stratum | Single read error | Archivist error | Catch rate |
|---|---|---|---|---|
| left_out/as_run | 1939_1942 | 19.7% (7.4%–34.0%) | 24.7% (0.0%–42.2%) | 36.4% (20.9%–100.0%) |
| left_out/as_run | total_claims | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |
| left_out/failed_to_review | 1939_1942 | 19.7% (7.4%–34.0%) | 24.7% (0.0%–42.2%) | 36.4% (20.9%–100.0%) |
| left_out/failed_to_review | total_claims | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |
| kept/as_run | 1939_1942 | 44.4% (33.1%–57.2%) | 42.7% (29.0%–61.0%) | 74.0% (59.8%–85.2%) |
| kept/as_run | total_claims | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |
| kept/failed_to_review | 1939_1942 | 44.4% (33.1%–57.2%) | 42.3% (28.3%–61.5%) | 75.4% (61.7%–86.2%) |
| kept/failed_to_review | total_claims | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |

Labels and outcomes (variant: by choice; by outcome):

- left_out/as_run: {'blank': 15, 'cant_read': 5, 'not_on_page': 1, 'value': 141}; {'right': 135, 'wrong': 22, 'cant_read': 5, 'abstained': 0}
- left_out/failed_to_review: {'blank': 15, 'cant_read': 5, 'not_on_page': 1, 'value': 141}; {'right': 135, 'wrong': 22, 'cant_read': 5, 'abstained': 0}
- kept/as_run: {'blank': 50, 'cant_read': 19, 'column_not_on_page': 69, 'not_on_page': 1, 'value': 261}; {'right': 246, 'wrong': 126, 'cant_read': 19, 'abstained': 9}
- kept/failed_to_review: {'blank': 50, 'cant_read': 19, 'column_not_on_page': 69, 'not_on_page': 1, 'value': 261}; {'right': 246, 'wrong': 126, 'cant_read': 19, 'abstained': 9}

## Every deep-check cell

| Variant | Cells | Review rate | Boxed OCR | Boxed grid | Boxed model |
|---|--:|---|---|---|---|
| left_out/as_run | 12494 | 52.9% (36.1%–71.0%) | 18.1% (7.2%–29.7%) | 24.6% (12.3%–36.5%) | 57.3% (36.9%–79.7%) |
| left_out/failed_to_review | 12494 | 53.0% (36.2%–71.0%) | 18.1% (7.2%–29.7%) | 24.6% (12.3%–36.5%) | 57.3% (36.9%–79.7%) |
| kept/as_run | 33114 | 66.3% (57.9%–74.5%) | 16.6% (12.1%–21.8%) | 11.1% (6.5%–16.2%) | 72.2% (64.2%–79.4%) |
| kept/failed_to_review | 33114 | 68.9% (60.2%–76.8%) | 16.6% (12.1%–21.8%) | 11.1% (6.5%–16.2%) | 72.2% (64.2%–79.4%) |

By family (kept/as_run):

| Family | Cells | Review rate | OCR | Grid | Model |
|---|--:|---|---|---|---|
| short_term_foreign_liabilities_as | 8400 | 80.9% (72.0%–89.8%) | 16.2% (7.2%–25.7%) | 0.4% (0.0%–1.1%) | 83.5% (74.0%–92.4%) |
| security_transactions_as_reported_by | 10080 | 56.4% (41.8%–71.4%) | 15.3% (8.2%–23.9%) | 15.8% (6.7%–25.3%) | 68.9% (53.7%–82.9%) |
| outstanding_forward_exchange_contracts | 5040 | 70.3% (57.3%–81.3%) | 30.5% (20.4%–40.2%) | 9.7% (4.1%–15.3%) | 59.9% (48.0%–71.3%) |
| receipts_and_expenditures_under_railroad | 1224 | 64.9% (56.0%–73.6%) | 22.7% (16.4%–27.8%) | 16.2% (4.2%–30.1%) | 61.1% (44.4%–76.0%) |
| total_claims_by_country | 8370 | 50.5% (29.1%–72.5%) | 9.5% (0.9%–19.9%) | 31.3% (15.0%–48.3%) | 59.2% (40.4%–78.1%) |

## Re-reads asked again

Keys {'unanswered_rereads.jsonl': 3322, 'unanswered_rereads_2.jsonl': 32}; 3416 cells (836 accepted as run); 34 labelled (5 accepted as run).

## Coverage by page

| Page | Family | Rows | Not returned | Left empty | Figure cells | Not returned | Left empty |
|---|---|--:|--:|--:|--:|--:|--:|
| 1940-01_p026 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1940-01_p051 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1940-01_p053 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1940-02_p028 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1940-02_p055 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1940-02_p057 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1940-02_p062 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1940-03_p060 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1940-04_p055 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1940-04_p059 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1940-06_p063 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1940-06_p069 | outstanding_forward_exchange_contracts | 30 | 0 | 0 | 390 | 0 | 0 |
| 1940-07_p031 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1940-08_p024 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1940-10_p023 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1940-10_p059 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1940-10_p062 | security_transactions_as_reported_by | 60 | 0 | 39 | 780 | 0 | 507 |
| 1940-11_p051 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1940-11_p060 | outstanding_forward_exchange_contracts | 30 | 0 | 0 | 390 | 0 | 0 |
| 1940-12_p024 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1940-12_p059 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1941-01_p022 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1941-01_p058 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1941-02_p024 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1941-02_p058 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1941-03_p056 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1941-03_p069 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1941-04_p019 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1941-04_p058 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1941-04_p059 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1941-04_p063 | security_transactions_as_reported_by | 60 | 0 | 39 | 780 | 0 | 507 |
| 1941-04_p068 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1941-05_p021 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1941-05_p062 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1941-06_p023 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1941-06_p065 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1941-07_p071 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1941-07_p074 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1941-08_p065 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1941-08_p069 | security_transactions_as_reported_by | 60 | 0 | 39 | 780 | 0 | 507 |
| 1941-08_p074 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1941-09_p065 | short_term_foreign_liabilities_as | 50 | 0 | 0 | 650 | 0 | 0 |
| 1941-09_p075 | outstanding_forward_exchange_contracts | 30 | 0 | 0 | 390 | 0 | 0 |
| 1941-10_p086 | security_transactions_as_reported_by | 60 | 0 | 0 | 780 | 0 | 0 |
| 1941-10_p087 | security_transactions_as_reported_by | 60 | 0 | 39 | 780 | 0 | 507 |
| 1941-10_p092 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1942-01_p025 | receipts_and_expenditures_under_railroad | 17 | 0 | 0 | 85 | 0 | 0 |
| 1942-03_p090 | outstanding_forward_exchange_contracts | 30 | 0 | 6 | 390 | 0 | 78 |
| 1985-06_p058 | total_claims_by_country | 93 | 0 | 0 | 744 | 0 | 0 |
| 1986-06_p060 | total_claims_by_country | 93 | 0 | 0 | 744 | 0 | 0 |
| 1987-06_p072 | total_claims_by_country | 93 | 0 | 0 | 744 | 0 | 0 |
| 1988-06_p103 | total_claims_by_country | 93 | 0 | 0 | 744 | 0 | 0 |
| 1989-06_p099 | total_claims_by_country | 93 | 0 | 0 | 744 | 0 | 0 |
| 1990-06_p103 | total_claims_by_country | 93 | 0 | 0 | 744 | 0 | 0 |
| 1991-06_p107 | total_claims_by_country | 93 | 0 | 0 | 744 | 0 | 0 |
| 1993-06_p097 | total_claims_by_country | 93 | 45 | 0 | 744 | 360 | 0 |
| 1993-06_p098 | total_claims_by_country | 93 | 49 | 0 | 744 | 392 | 0 |
| 1994-06_p099 | total_claims_by_country | 93 | 45 | 0 | 744 | 360 | 0 |

By family:

| Family | Pages | Rows | Not returned | Left empty | Figure cells | Not returned | Left empty |
|---|--:|--:|--:|--:|--:|--:|--:|
| outstanding_forward_exchange_contracts | 12 | 360 | 0 | 54 | 4680 | 0 | 702 |
| receipts_and_expenditures_under_railroad | 12 | 204 | 0 | 0 | 1020 | 0 | 0 |
| security_transactions_as_reported_by | 12 | 720 | 0 | 156 | 9360 | 0 | 2028 |
| short_term_foreign_liabilities_as | 12 | 600 | 0 | 0 | 7800 | 0 | 0 |
| total_claims_by_country | 10 | 930 | 139 | 0 | 7440 | 1112 | 0 |

## Identities, changed-layout pages against the others

| Identity | Changed: held / failed / unchecked | Other: held / failed / unchecked |
|---|---|---|
| outstanding_forward_exchange_contracts.grand_total | 244 / 14 / 0 | 48 / 0 / 0 |
| outstanding_forward_exchange_contracts.total_europe | 0 / 258 / 0 | 48 / 0 / 0 |
| outstanding_forward_exchange_contracts.total_purchase_breakdown | 548 / 11 / 0 | 104 / 0 / 0 |
| outstanding_forward_exchange_contracts.total_sale_breakdown | 544 / 15 / 0 | 104 / 0 / 0 |
| receipts_and_expenditures_under_railroad.total_expenditures | 166 / 3 / 1 | 33 / 0 / 1 |
| security_transactions_as_reported_by.grand_total | 309 / 9 / 126 | 108 / 0 / 12 |
| security_transactions_as_reported_by.total_europe | 165 / 213 / 66 | 108 / 0 / 12 |
| short_term_foreign_liabilities_as.grand_total | 0 / 0 / 500 | 89 / 1 / 10 |
| short_term_foreign_liabilities_as.total_europe | 21 / 191 / 288 | 90 / 0 / 10 |
| total_claims_by_country.grand_total | 0 / 0 / 0 | 63 / 1 / 16 |
| total_claims_by_country.total_africa | 0 / 0 / 0 | 53 / 8 / 19 |
| total_claims_by_country.total_asia | 0 / 0 / 0 | 45 / 18 / 17 |
| total_claims_by_country.total_europe | 0 / 0 / 0 | 27 / 26 / 27 |
| total_claims_by_country.total_foreign | 0 / 0 / 0 | 51 / 4 / 25 |
| total_claims_by_country.total_international | 0 / 0 / 0 | 25 / 3 / 52 |
| total_claims_by_country.total_latin | 0 / 0 / 0 | 50 / 16 / 14 |
| total_claims_by_country.total_other | 0 / 0 / 0 | 64 / 0 / 16 |

## Template drift (total claims)

- 1989-06_p099: {"prints_ireland_row": true, "prints_gdr_row": true, "total_europe": {"held": 0, "failed": 8, "unchecked": 0}, "cells_flagged_by_total_europe": 208, "flagged_by_status": {"review": 208}, "labelled_cells": {"right": 7, "wrong": 1, "cant_read": 0, "abstained": 0}}
- 1990-06_p103: {"prints_ireland_row": true, "prints_gdr_row": true, "total_europe": {"held": 2, "failed": 6, "unchecked": 0}, "cells_flagged_by_total_europe": 156, "flagged_by_status": {"review": 156}, "labelled_cells": {"right": 13, "wrong": 0, "cant_read": 0, "abstained": 0}}
- 1991-06_p107: {"prints_ireland_row": true, "prints_gdr_row": true, "total_europe": {"held": 0, "failed": 7, "unchecked": 1}, "cells_flagged_by_total_europe": 182, "flagged_by_status": {"review": 182}, "labelled_cells": {"right": 13, "wrong": 2, "cant_read": 1, "abstained": 0}}
- 1993-06_p097: {"prints_ireland_row": true, "prints_gdr_row": false, "total_europe": {"held": 0, "failed": 0, "unchecked": 8}, "cells_flagged_by_total_europe": 0, "flagged_by_status": {}, "labelled_cells": {"right": 5, "wrong": 0, "cant_read": 0, "abstained": 0}, "gdr_figure_cells": 8, "gdr_figure_cells_read": 0, "gdr_read_by_status": {}, "gdr_read_flags": 0, "gdr_labelled_cells": {"right": 0, "wrong": 0, "cant_read": 0, "abstained": 0}}
- 1993-06_p098: {"prints_ireland_row": false, "prints_gdr_row": false, "total_europe": {"held": 0, "failed": 0, "unchecked": 8}, "cells_flagged_by_total_europe": 0, "flagged_by_status": {}, "labelled_cells": {"right": 6, "wrong": 1, "cant_read": 1, "abstained": 0}, "gdr_figure_cells": 8, "gdr_figure_cells_read": 0, "gdr_read_by_status": {}, "gdr_read_flags": 0, "gdr_labelled_cells": {"right": 0, "wrong": 0, "cant_read": 0, "abstained": 0}}
- 1994-06_p099: {"prints_ireland_row": true, "prints_gdr_row": false, "total_europe": {"held": 0, "failed": 0, "unchecked": 8}, "cells_flagged_by_total_europe": 0, "flagged_by_status": {}, "labelled_cells": {"right": 5, "wrong": 0, "cant_read": 0, "abstained": 0}, "gdr_figure_cells": 8, "gdr_figure_cells_read": 0, "gdr_read_by_status": {}, "gdr_read_flags": 0, "gdr_labelled_cells": {"right": 0, "wrong": 0, "cant_read": 0, "abstained": 0}}

## The Revisions page

1941-03_p069: a different table (Revisions – Security Transactions …), confirmed by both the classifier and the title check, which accepts any page whose title contains the family's approved title: a weakness of the title check. {"cells": 840, "by_status": {"accepted": 19, "review": 821}, "labelled_cells": {"right": 0, "wrong": 5, "cant_read": 2, "abstained": 0}}

## Pages set aside (sweep)

```
{
  "pages": 4569,
  "classified": 4569,
  "failed": 0,
  "by_family": {
    "short_term_foreign_liabilities_as": {
      "classified": 54,
      "confirmed": 44,
      "type_unconfirmed": 10
    },
    "security_transactions_as_reported_by": {
      "classified": 95,
      "confirmed": 42,
      "type_unconfirmed": 53
    },
    "outstanding_forward_exchange_contracts": {
      "classified": 27,
      "confirmed": 19,
      "type_unconfirmed": 8
    },
    "receipts_and_expenditures_under_railroad": {
      "classified": 63,
      "confirmed": 21,
      "type_unconfirmed": 42
    },
    "total_claims_by_country": {
      "classified": 52,
      "confirmed": 10,
      "type_unconfirmed": 42
    }
  },
  "set_aside_by_classifier": 4278,
  "set_aside_by_title_check": 155,
  "by_era": {
    "1939-1942": {
      "outstanding_forward_exchange_contracts": 27,
      "receipts_and_expenditures_under_railroad": 63,
      "security_transactions_as_reported_by": 87,
      "short_term_foreign_liabilities_as": 54,
      "unsupported": 3015
    },
    "1982-1994": {
      "security_transactions_as_reported_by": 8,
      "total_claims_by_country": 52,
      "unsupported": 1263
    }
  }
}
```

## SAM's detections

```
{
  "pages": 58,
  "pages_with_a_detection": 0,
  "by_prompt": {
    "stain": {
      "pages_with_a_detection": 0,
      "detections": 0
    },
    "stamp": {
      "pages_with_a_detection": 0,
      "detections": 0
    }
  },
  "cells_occluded": 0,
  "cells_occluded_by_label": {}
}
```

## Relabel agreement

`{"status": "pending", "relabelled": 0, "of": 40}`

## Classification check

`{"status": "done", "right": 50, "of": 50, "wilson": [0.9286524008666414, 1.0], "wrong_pages": []}`
