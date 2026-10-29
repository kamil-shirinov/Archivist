# Column layouts of the held-out deep-check pages, from the OCR layer

Made on 2026-10-29, during the deep check's re-reads and before the labels were drawn, with no model call and without touching the run. For each of the 58 deep-check pages, `procedure/column_layout.py` read the archive PDF's own OCR text layer (pdfium, through `archivist.templates.real_test.words`). It found the table's heading band, grouped the heading words into printed columns, and counted the columns of figures in the table body. The page's printed headings, in order, were then compared by a person reading this output against the template's figure columns. OCR spellings are normalised below ("Oermany" is Germany, "Tar East" is Far East). A heading the OCR layer lacks is not taken to be missing from the page; where that matters it is said.

The templates' figure columns, as approved from 1939 development pages:

- `short_term_foreign_liabilities_as`, `security_transactions_as_reported_by`, `outstanding_forward_exchange_contracts` (13): United Kingdom · France · Germany · Italy · Netherlands · Switzerland · Other Europe · Total Europe · Canada · Latin America · Far East · All other · Grand total
- `receipts_and_expenditures_under_railroad` (5): Taxes upon carriers and their employees · Administrative expenses · Transfers to Railroad Retirement Acct. · Transfers to Railroad Unemployment Insurance account · Total expenditures
- `total_claims_by_country` (8): Calendar year 1981 · June 1982 · Sept. 1982 · Dec. 1982 · Mar. 1983 · June 1983 · Sept. 1983 · Dec. 1983

## The layouts found

- **L17, the 17-column country layout** (security transactions and forward exchange, from 1940): Grand total · United Kingdom · France · Belgium · Germany · Italy · Netherlands · Sweden · Switzerland · Other Europe · Total Europe · Canada · Latin America · Japan, Korea and Manchuria · Other Asia · Total Asia · All other. Against the template: Grand total moved to the front; Belgium, Sweden, "Japan, Korea and Manchuria", Other Asia and Total Asia added; Far East not printed. Printed in full on 1941-04 p068 and 1941-09 p075; the project owner saw it by eye on 1941-02 p058.
- **SA, short-term liabilities split over two pages, page A, Europe** (15 columns): Grand total · United Kingdom · France · Belgium · Denmark · Finland · Germany · Italy · Netherlands · Norway · Sweden · Switzerland · Other Europe · Total Europe · Canada. Against the template: Grand total moved to the front; Belgium, Denmark, Finland, Norway and Sweden added; Latin America, Far East and All other not printed on this page. Printed in full on 1940-04 p055.
- **SB, short-term liabilities split over two pages, page B, Latin America and Asia** (15 columns): Argentina · Brazil · Chile · Cuba · Mexico · Panama and Canal Zone · Other Latin America · Total Latin America · China · Hong Kong · Japan, Korea and Manchuria · Philippine Islands · Other Asia · Total Asia · All other. Against the template: only Latin America (printed as "Total Latin America") and All other are printed; United Kingdom, France, Germany, Italy, Netherlands, Switzerland, Other Europe, Total Europe, Canada, Far East and Grand total are not. Printed in full on 1941-07 p071. Both pages carry the family's title and pass the title check.
- **RR6, the railroad layout from late 1940**: Receipts (total) · Administrative expenses · Transfers to Railroad Retirement account (Trust account) · Advances to Railroad Unemployment Insurance Account · Transfers to Railroad Unemployment Insurance Account · Excess of expenditures. Against the template: the receipts column is headed "Receipts, total" rather than "Taxes upon carriers and their employees"; "Advances to Railroad Unemployment Insurance Account" and "Excess of expenditures" added; "Total expenditures" not found in the OCR layer (one page, 1941-04 p019, shows a "Total" heading under Expenditures).

## By page

| Family | Page | Layout | Headings found in the OCR layer / figure columns counted | Notes |
|---|---|---|---|---|
| short-term | 1940-01 p051 | cannot be checked | 17 words in the OCR layer | |
| short-term | 1940-02 p055 | cannot be checked | 26 words in the OCR layer | |
| short-term | 1940-04 p055 | **SA, changed** | 15 of 15 / 15 | |
| short-term | 1940-10 p059 | **SA, changed** | 14 of 15 / 15 | France not in the OCR layer |
| short-term | 1940-11 p051 | **SB, changed** | 5 of 15 / 4 | the OCR layer has only the first five headings |
| short-term | 1941-03 p056 | **SA, changed** | 10 of 15 / 16 | |
| short-term | 1941-04 p058 | **SA, changed** | 12 of 15 / 14 | |
| short-term | 1941-04 p059 | **SB, changed** | 14 of 15 / 5 | |
| short-term | 1941-06 p065 | **SB, changed** | 9 of 15 / 9 | |
| short-term | 1941-07 p071 | **SB, changed** | 15 of 15 / 17 | |
| short-term | 1941-08 p065 | **SB, changed** | 13 of 15 / 16 | |
| short-term | 1941-09 p065 | **SA, changed** | 12 of 15 / 17 | |
| security | 1940-01 p053 | same as the template | 13 of 13 in order / 13 | |
| security | 1940-02 p057 | same as far as the OCR layer reaches | 9 of 13 in order / 8 | United Kingdom to Canada in the template's order; Latin America, Far East, All other and Grand total not in the OCR layer |
| security | 1940-04 p059 | **L17, changed** | 15 of 17 / 15 | |
| security | 1940-06 p063 | **L17, changed** | 10 of 17 / 6 | |
| security | 1940-10 p062 | cannot be checked | 26 words in the OCR layer | |
| security | 1941-03 p069 | **a different table** | — | "Revisions – Security Transactions … for the period November 9, 1940 through August 28, 1941": columns of purchases and sales for foreign account (Grand total and Far East under each), not countries. Both the classifier and the title check passed it, since its title contains the family's. |
| security | 1941-04 p063 | **L17, changed** | 16 of 17 / 3 | |
| security | 1941-05 p062 | **L17, changed** | 12 of 17 / 15 | |
| security | 1941-07 p074 | **L17, changed** | 12 of 17 / 15 | |
| security | 1941-08 p069 | **L17, changed** | 14 of 17 / 1 | |
| security | 1941-10 p086 | **L17, changed** | 14 of 17 / 2 | |
| security | 1941-10 p087 | **L17, changed** | 14 of 17 / 2 | |
| forward | 1940-02 p062 | same as the template | 13 of 13 in order / 13 | |
| forward | 1940-03 p060 | same as the template | 13 of 13 in order / 12 | |
| forward | 1940-06 p069 | **L17, changed** | 9 of 17 / 16 | |
| forward | 1940-11 p060 | **L17, changed** | 13 of 17 / 14 | |
| forward | 1940-12 p059 | **L17, changed** | 13 of 17 / 14 | |
| forward | 1941-01 p058 | **L17, changed** | 13 of 17 / 6 | |
| forward | 1941-02 p058 | cannot be checked from the OCR layer; **L17 by eye** | 18 words in the OCR layer | checked by the project owner |
| forward | 1941-04 p068 | **L17, changed** | 17 of 17 / 11 | |
| forward | 1941-08 p074 | **L17, changed** | 16 of 17 / 14 | |
| forward | 1941-09 p075 | **L17, changed** | 17 of 17 / 13 | |
| forward | 1941-10 p092 | **L17, changed** | 16 of 17 / 13 | |
| forward | 1942-03 p090 | **L17, changed** | 14 of 17 / 11 | |
| railroad | 1940-01 p026 | cannot be checked | no column headings in the OCR layer | |
| railroad | 1940-02 p028 | same as the template | 5 of 5 in order / 4 | |
| railroad | 1940-07 p031 | **changed** | 5 / 3 | the receipts column headed "Receipts, total"; the other four as the template |
| railroad | 1940-08 p024 | **changed** | 5 / 3 | as 1940-07 p031 |
| railroad | 1940-10 p023 | **RR6, changed** | 5 / 4 | "Transfers to Railroad Unemployment Insurance Account" not in the OCR layer |
| railroad | 1940-12 p024 | cannot be checked | no column headings in the OCR layer | |
| railroad | 1941-01 p022 | cannot be checked | 24 words in the OCR layer | |
| railroad | 1941-02 p024 | **RR6, changed** | 6 / 5 | |
| railroad | 1941-04 p019 | **RR6, changed** | 7 / 5 | a "Total" heading under Expenditures, before Administrative expenses |
| railroad | 1941-05 p021 | **RR6, changed** | 6 / 4 | |
| railroad | 1941-06 p023 | **RR6, changed** | 6 / 5 | |
| railroad | 1942-01 p025 | **changed** | 5 / 6 | Receipts total · Administrative expenses · Transfers to Railroad Retirement account · Transfers to Railroad Unemployment Insurance Account · Excess of expenditures |
| total claims | 1985-06 p058 to 1994-06 p099, 10 pages | cannot be checked | the OCR layer has no column headings beyond fragments ("Calendar year", "Sept.", "Dec. p") and few or no figures | The template's headings name the dates 1981 to 1983, so on every later issue each heading prints other dates by design; whether the columns are still a calendar year followed by seven quarter-ends needs a look by eye. |

## Summary

| Family | Pages | Same as the template | Changed | A different table | Cannot be checked from the OCR layer |
|---|--:|--:|--:|--:|--:|
| short-term foreign liabilities | 12 | 0 | 10 (5 SA, 5 SB) | 0 | 2 |
| security transactions | 12 | 1, and 1 as far as the OCR reaches | 8 (L17) | 1 | 1 |
| forward exchange | 12 | 2 | 10 (L17), 1 of them by eye | 0 | 0 after the check by eye |
| railroad | 12 | 1 | 8 | 0 | 3 |
| total claims | 10 | 0 | 0 | 0 | 10 |

The 1939 layouts the templates describe hold only on the earliest held-out issues in the sample (January to March 1940). From April 1940 the short-term and security tables print more columns, in another order, and the short-term table is split over two pages; the forward-exchange table does the same by June 1940 (its April and May issues are not in the sample); from July 1940 the railroad table's columns change too. Of the 58 deep-check pages, 36 print a changed layout, 1 is a different table, 4 match their template (and 1 more as far as its OCR layer reaches), and 16 cannot be checked from their OCR layer.
