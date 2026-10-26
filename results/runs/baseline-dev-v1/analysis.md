# Baseline error analysis: baseline-dev-v1

Run `baseline-dev-v1` (extractor `muse-spark-1.3-contributor`): 47 pages, 1385 fields, 53 wrong (3.8%). Written by `python -m archivist.eval.analyse`; no model calls. The same numbers are in `analysis.json`.

## 1. Wrong fields

A wrong field is anything the scorer does not count correct: misread, hallucinated, omitted or abstained. Each gets one category, by the first rule that matches:

- **blank**: omitted or abstained.
- **format**: the values differ only in spacing, punctuation, letter case, currency signs or leading zeros.
- **digit**: a money, date or number field with different digits.
- **text**: a text field with different words.

|  | fields | format | digit | text | blank | wrong | wrong % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ledger | 1140 | 0 | 19 | 6 | 2 | 27 | 2.4% |
| memo | 245 | 8 | 10 | 3 | 5 | 26 | 10.6% |
| severity 0 | 348 | 3 | 1 | 1 | 0 | 5 | 1.4% |
| severity 1 | 524 | 1 | 0 | 0 | 0 | 1 | 0.2% |
| severity 2 | 260 | 1 | 0 | 0 | 0 | 1 | 0.4% |
| severity 3 | 253 | 3 | 28 | 8 | 7 | 46 | 18.2% |
| **all** | 1385 | 8 | 29 | 9 | 7 | 53 | 3.8% |

Of the 9 text errors, 6 differ in digits only (a number inside a text field, such as a cheque number or a sheet and line reference).

### Every wrong field (53)

Occluded is yes when an artefact covers the field in the ground truth.

| page | sev | doc type | field | outcome | printed | predicted | occluded | category |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| card-03-2 | 3 | ledger | `hdr:account_no` | misread | `"34192727"` | `"34142727"` | yes | digit |
| card-03-2 | 3 | ledger | `01:date` | misread | `"02/01/86"` | `"02/01/76"` | yes | digit |
| card-03-2 | 3 | ledger | `01:description` | misread | `"STANDING ORDER RATES"` | `"STANDING ORDER COUNCIL"` | no | text |
| card-03-2 | 3 | ledger | `02:date` | misread | `"03/01/86"` | `"03/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `02:description` | abstained | `"DIRECT DEBIT ELECTRICITY"` | `null` | no | blank |
| card-03-2 | 3 | ledger | `03:date` | misread | `"09/01/86"` | `"04/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `04:date` | misread | `"14/01/86"` | `"11/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `04:description` | misread | `"CHQ 889341"` | `"CHQ 799341"` | no | text |
| card-03-2 | 3 | ledger | `05:date` | misread | `"14/01/86"` | `"14/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `06:date` | misread | `"18/01/86"` | `"17/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `07:date` | misread | `"22/01/86"` | `"22/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `08:date` | misread | `"24/01/86"` | `"24/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `08:description` | misread | `"CHQ 889342"` | `"CHQ 799342"` | no | text |
| card-03-2 | 3 | ledger | `09:date` | misread | `"27/01/86"` | `"27/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `10:date` | misread | `"30/01/86"` | `"30/01/76"` | no | digit |
| card-03-2 | 3 | ledger | `11:date` | misread | `"02/02/86"` | `"02/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `11:description` | misread | `"CHQ 889343"` | `"CHQ 799343"` | no | text |
| card-03-2 | 3 | ledger | `12:date` | misread | `"07/02/86"` | `"07/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `13:date` | misread | `"08/02/86"` | `"08/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `14:date` | misread | `"13/02/86"` | `"13/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `15:date` | misread | `"13/02/86"` | `"13/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `15:description` | misread | `"CHQ 889344"` | `"CHQ 799344"` | no | text |
| card-03-2 | 3 | ledger | `16:date` | misread | `"16/02/86"` | `"16/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `17:date` | misread | `"18/02/86"` | `"18/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `18:date` | misread | `"21/02/86"` | `"21/02/76"` | no | digit |
| card-03-2 | 3 | ledger | `18:description` | misread | `"CHQ 889345"` | `"CHQ 799345"` | no | text |
| card-03-2 | 3 | ledger | `hdr:carried_forward` | omitted | `"3,897.79"` | `""` | no | blank |
| memo-0003 | 0 | memo | `amount_words` | misread | `"Sixty-three pounds and forty-six pence"` | `"Sixty-three pounds and fortysix pence"` | no | format |
| memo-0008 | 3 | memo | `memo_no` | misread | `"008334"` | `"007334"` | no | digit |
| memo-0008 | 3 | memo | `account_no` | misread | `"17868679"` | `"17267679"` | no | digit |
| memo-0008 | 3 | memo | `amount_words` | misread | `"Sixty-eight pounds and forty-six pence"` | `"Sixty eight pounds and forty six pence"` | no | format |
| memo-0008 | 3 | memo | `ledger_ref` | misread | `"Sheet 38 / Line 04"` | `"Sheet 37 / Line 04"` | no | text |
| memo-0011 | 0 | memo | `memo_no` | misread | `"008337"` | `"009337"` | no | digit |
| memo-0011 | 0 | memo | `counterparty` | misread | `"Mrs Sharon Wong"` | `"Meadsharon Mong"` | no | text |
| memo-0011 | 0 | memo | `amount` | misread | `"346.30"` | `"346,30"` | no | format |
| memo-0011 | 0 | memo | `amount_words` | misread | `"Three hundred and forty-six pounds and thirty pence"` | `"Three hundred and fortysix pounds and thirty pence"` | no | format |
| memo-0013 | 3 | memo | `account_no` | abstained | `"69675442"` | `null` | yes | blank |
| memo-0016 | 3 | memo | `amount` | abstained | `"74.30"` | `null` | yes | blank |
| memo-0016 | 3 | memo | `amount_words` | misread | `"Seventy-four pounds and thirty pence"` | `"Seventy four pounds and thirty pence."` | yes | format |
| memo-0017 | 1 | memo | `amount_words` | misread | `"One hundred and sixty-five pounds and sixty-two pence"` | `"One hundred and sixty five pounds and sixty two pence"` | no | format |
| memo-0020 | 3 | memo | `memo_no` | misread | `"008346"` | `"008546"` | no | digit |
| memo-0020 | 3 | memo | `account_no` | misread | `"34192727"` | `"34/92727"` | no | digit |
| memo-0020 | 3 | memo | `counterparty` | misread | `"Wrenfield Assurance Society"` | `"Mayfield Assurance Society"` | no | text |
| memo-0020 | 3 | memo | `amount` | omitted | `"18.22"` | `""` | yes | blank |
| memo-0023 | 3 | memo | `account_no` | misread | `"34192727"` | `"34/42727"` | no | digit |
| memo-0025 | 3 | memo | `account_no` | misread | `"34192727"` | `"24392727"` | yes | digit |
| memo-0026 | 3 | memo | `memo_no` | misread | `"008352"` | `"007352"` | no | digit |
| memo-0026 | 3 | memo | `date` | misread | `"21/03/86"` | `"21/03/76"` | no | digit |
| memo-0026 | 3 | memo | `account_no` | misread | `"34192727"` | `"34142727"` | no | digit |
| memo-0026 | 3 | memo | `amount` | abstained | `"30.96"` | `null` | yes | blank |
| memo-0026 | 3 | memo | `amount_words` | misread | `"Thirty pounds and ninety-six pence"` | `"Thirty pounds and ninety six pence"` | no | format |
| memo-0029 | 3 | memo | `amount` | omitted | `"212.14"` | `""` | yes | blank |
| memo-0035 | 2 | memo | `ledger_ref` | misread | `"Sheet 8 / Line 14"` | `"Sheet 8 / Line 14."` | no | format |

## 2. Citation residuals

Population: fields read correctly that carry a citation, the same fields citation accuracy is computed on; 216 of them are cells printed blank. Δ is the predicted box centre minus the true one, so a positive Δy is a box below the ink. Cells show mean (sd).

| doc type | n | Δx px | Δx % of width | Δy px | Δy % of height | mean abs Δy px |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ledger | 1113 | -3.8 (16.2) | -0.22 (0.95) | -23.9 (25.7) | -2.17 (2.33) | 25.4 |
| memo | 219 | -11.2 (17.2) | -1.02 (1.56) | +6.0 (19.0) | +0.43 (1.36) | 16.1 |

Fit of Δy = a·y + b, with y the true centre in pixels (a is a pure ratio; b is in pixels). The Δx line fits Δx = a·x + b the same way, for comparison: a uniform coordinate-frame error would show in both axes.

| doc type | fit | a | b px | R² |
| --- | --- | ---: | ---: | ---: |
| ledger | Δy on y | -0.0595 | +12.5 | 0.316 |
| ledger | Δx on x | -0.0165 | +11.8 | 0.288 |
| ledger | Δy on y, per page (12 pages, 68–95 points each) | median -0.0600 (-0.098 to -0.005) | — | median 0.839 |
| memo | Δy on y | -0.0071 | +9.5 | 0.006 |
| memo | Δx on x | -0.0320 | +4.0 | 0.094 |
| memo | Δy on y, per page (31 pages, 5–7 points each) | median -0.0165 (-0.046 to +0.039) | — | median 0.526 |

Reading Δy: a pooled R² of at least 0.5 counts as proportional to position, below 0.1 as no link to position (roughly constant if the mean offset is at least as large as the spread, otherwise just scatter), in between as mixed.

- **ledger**: proportional to position within each page, with a slope that differs from page to page: a coordinate-frame (scale) issue. Pooled R² 0.32, slope -0.059; Δy mean -23.9 px, sd 25.7 px. Page by page the lines fit better: median R² 0.84 over 12 pages, slopes -0.098 to -0.005 at the 10th to 90th percentile.
- **memo**: neither: no link to position and an offset small next to the scatter. Pooled R² 0.01, slope -0.007; Δy mean +6.0 px, sd 19.0 px. Page by page the lines fit better: median R² 0.53 over 31 pages, slopes -0.046 to +0.039 at the 10th to 90th percentile, so the drift runs both ways on different pages; each line rests on only 5–7 points.

## 3. Citation accuracy under three rules

Over the same fields as section 2, each rule judged on its own; a citation on another page fails all three.

| doc type | n | predicted centre inside the true box (the scorer's rule) | true centre inside the predicted box | IoU of at least 0.3 |
| --- | ---: | ---: | ---: | ---: |
| ledger | 1113 | 43.4% (483) | 40.3% (449) | 40.4% (450) |
| memo | 219 | 53.4% (117) | 59.8% (131) | 53.4% (117) |
| all | 1332 | 45.1% (600) | 43.5% (580) | 42.6% (567) |

## 4. The 5 worst pages

Ranked by wrong fields, then severity, then page id.

| # | page | doc type | severity | wrong / fields | format | digit | text | blank | wrong and occluded | artefacts |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | card-03-2 | ledger | 3 | 27 / 95 | 0 | 19 | 6 | 2 | 2 | 4× stain |
| 2 | memo-0026 | memo | 3 | 5 / 7 | 1 | 3 | 0 | 1 | 1 | 2× handwritten_amendment, 1× signature, 2× stamp |
| 3 | memo-0008 | memo | 3 | 4 / 7 | 1 | 2 | 1 | 0 | 0 | 2× handwritten_amendment, 1× signature, 1× stain |
| 4 | memo-0020 | memo | 3 | 4 / 7 | 0 | 2 | 1 | 1 | 1 | 1× handwritten_amendment, 1× signature, 2× stamp |
| 5 | memo-0011 | memo | 0 | 4 / 7 | 2 | 1 | 1 | 0 | 0 | 1× signature |

Together they hold 44 of the 53 wrong fields.
