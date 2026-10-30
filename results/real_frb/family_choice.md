# Which Federal Reserve Bulletin tables get a drafted template

Made by `python -m archivist.templates.families_frb` before any template was drafted. No model was called and no page image was opened: tables, their issues and their pages are the survey's (`results/real_frb/survey.md`), from the manifest's numbered captions and Total lines. A table is a number together with its title, never a number alone, since numbers are reused for other tables over the years.

## The rule

1. Prints totals: at least half of the issues it is found in print a Total line after its caption (the survey's rule), and so does every development issue it is drafted from.
2. Found in development: in at least 2 of the development issues (June 1980, 1990 and 2000). Drafted from its first page in each, at most 3.
3. Recurs in held-out: in at least 2 held-out issues.
4. Ranked first by kind, tables of bank assets and liabilities first, then by held-out page count, then by number; the top 4 are chosen. A table is one of bank assets and liabilities when its title names banks (bank, banks, banking, depository institutions) and what they hold or owe (assets, liabilities, condition, balance sheet, claims, loans and securities).

The drafter is told only the printed title: the number and caption as the OCR reads them on the first drafting page, a footnote mark at the end dropped, or, where the OCR cut the caption short, as read off that page's image (3.19, on frb-1990-06_p130).

## Chosen (4)

| # | Family | Table | Bank assets and liabilities | Held-out pages | Held-out issues | Development issues | Drafted from | Title given |
|--:|---|---|---|--:|--:|--:|---|---|
| 1 | `frb_3_17_liabilities_to_foreigners` | 3.17 LIABILITIES TO FOREIGNERS Reported by Banks in the United States1 | yes | 25 | 17 | 2 | frb-1990-06_p127, frb-2000-06_p131 | 3.17 LIABILITIES TO FOREIGNERS Reported by Banks in the United States |
| 2 | `frb_3_20_banks_own_claims_on` | 3.20 BANKS' OWN CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Banks in the United States1 | yes | 22 | 20 | 2 | frb-1990-06_p130, frb-2000-06_p134 | 3.20 BANKS' OWN CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Banks in the United States |
| 3 | `frb_1_18_federal_reserve_banks_condition` | 1.18 FEDERAL RESERVE BANKS Condition and Federal Reserve Note Statements1 | yes | 21 | 21 | 3 | frb-1980-06_p109, frb-1990-06_p077, frb-2000-06_p088 | 1.18 FEDERAL RESERVE BANKS Condition and Federal Reserve Note Statements |
| 4 | `frb_3_19_banks_own_and_domestic` | 3.19 BANKS' OWN AND DOMESTIC CUSTOMERS' CLAIMS ON FOREIGNERS Reported by Banks in the | yes | 20 | 20 | 2 | frb-1990-06_p130, frb-2000-06_p134 | 3.19 BANKS' OWN AND DOMESTIC CUSTOMERS' CLAIMS ON FOREIGNERS Reported by Banks in the United States |

## Passed every rule but not chosen (18)

| Table | Bank assets and liabilities | Held-out pages | Held-out issues |
|---|---|--:|--:|
| 3.18 BANKS' OWN CLAIMS ON FOREIGNERS Reported by Banks in the United States1 | yes | 19 | 19 |
| 3.21 CLAIMS ON FOREIGN COUNTRIES Held by U.S. Offices and Foreign Branches of U.S.-Chartered Banks1 | yes | 13 | 13 |
| 1.23 LOANS AND SECURITIES All Commercial Banks1 | yes | 12 | 12 |
| 2.13 INDUSTRIAL PRODUCTION Indexes and Gross Value1 | no | 33 | 21 |
| 1.57 FUNDS RAISED IN U.S. CREDIT MARKETS1 | no | 28 | 19 |
| 1.17 FEDERAL RESERVE OPEN MARKET TRANSACTIONS1 | no | 21 | 21 |
| 1.12 RESERVES AND BORROWINGS Depository Institutions1 | no | 20 | 20 |
| 1.41 GROSS PUBLIC DEBT OF U.S. TREASURY Types and Ownership | no | 20 | 20 |
| 2.17 PERSONAL INCOME AND SAVING | no | 20 | 20 |
| 3.12 U.S. RESERVE ASSETS | no | 20 | 20 |
| 3.22 LIABILITIES TO UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in | no | 20 | 20 |
| 3.23 CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in | no | 20 | 20 |
| 1.51 DOMESTIC FINANCE COMPANIES Assets and Liabilities1 | no | 19 | 19 |
| 2.14 HOUSING AND CONSTRUCTION | no | 19 | 19 |
| 1.32 COMMERCIAL PAPER AND BANKERS DOLLAR ACCEPTANCES OUTSTANDING | no | 18 | 18 |
| 1.20 AGGREGATE RESERVES OF DEPOSITORY INSTITUTIONS AND MONETARY BASE1 | no | 17 | 17 |
| 2.12 OUTPUT, CAPACITY, AND CAPACITY UTILIZATION1 | no | 16 | 16 |
| 1.59 SUMMARY OF CREDIT MARKET DEBT OUTSTANDING1 | no | 12 | 12 |

## Tables with printed totals excluded, by the first rule failed

| Table | Rule failed | Development issues | Held-out issues |
|---|--:|--:|--:|
| 1.19 FEDERAL RESERVE BANKS Maturity Distribution of Loan and Security Holding | 1 | 2 | 17 |
| 1.50 TOTAL NONFARM BUSINESS EXPENDITURES on New Plant and Equipment | 1 | 1 | 11 |
| 1.10 MONETARY AGGREGATES AND INTEREST RATES | 2 | 1 | 3 |
| 1.10 RESERVES AND MONEY STOCK MEASURES | 2 | 0 | 1 |
| 1.10 RESERVES, MONEY STOCK, AND DEBT MEASURES | 2 | 1 | 2 |
| 1.10 RESERVES, MONEY STOCK, LIQUID ASSETS, AND DEBT MEASURES | 2 | 1 | 15 |
| 1.11 RESERVE BALANCES OF DEPOSITORY INSTITUTIONS1 | 2 | 0 | 1 |
| 1.12 RESERVES AND BORROWINGS Member Banks | 2 | 1 | 0 |
| 1.22 AGGREGATE RESERVES OF DEPOSITORY INSTITUTIONS AND MONETARY BASE1 | 2 | 0 | 1 |
| 1.24 ASSETS AND LIABILITIES OF COMMERCIAL BANKING INSTITUTIONS Last-Wednesday-of-Month Series | 2 | 1 | 0 |
| 1.24 MAJOR NONDEPOSIT FUNDS OF COMMERCIAL BANKS1 | 2 | 1 | 11 |
| 1.25 ASSETS AN D LIABILITIES OF COMMERCIAL BANKS1 | 2 | 0 | 1 |
| 1.25 ASSETS AND LIABILITIES OF COMMERCIAL BANKING INSTITUTIONS Last-Wednesday-of-Month Series | 2 | 1 | 11 |
| 1.25 COMMERCIAL BANK ASSETS AND LIABILITIES Call-Date Series | 2 | 1 | 0 |
| 1.26 ALL LARGE WEEKLY REPORTING COMMERCIAL BANKS with Domestic Assets of 1.4 Billion or More on | 2 | 0 | 6 |
| 1.26 ASSETS AND LIABILITIES OF COMMERCIAL BANKS1 | 2 | 0 | 3 |
| 1.26 ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS1 | 2 | 1 | 5 |
| 1.26 COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities1 | 2 | 1 | 6 |
| 1.27 ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS | 2 | 0 | 3 |
| 1.27 LARGE WEEKLY REPORTING COMMERCIAL BANKS with Domestic Assets of 1 Billion or More on | 2 | 0 | 3 |
| 1.28 ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS | 2 | 1 | 2 |
| 1.28 LARGE WEEKLY REPORTING COMMERCIAL BANKS IN NEW YORK CITY Assets and Liabilities | 2 | 0 | 7 |
| 1.28 LARGE WEEKLY REPORTING U.S. BRANCHES AND AGENCIES OF FOREIGN BANKS | 2 | 0 | 3 |
| 1.29 LARGE WEEKLY REPORTING COMMERCIAL BANKS Balance Sheet Memoranda | 2 | 0 | 4 |
| 1.29 LARGE WEEKLY REPORTING COMMERCIAL BANKS IN NEW YORK CITY Assets and Liabilities | 2 | 1 | 0 |
| 1.30 LARGE WEEKLY REPORTING COMMERCIAL BANKS Balance Sheet Memoranda | 2 | 1 | 0 |
| 1.30 LARGE WEEKLY REPORTING COMMERCIAL BANKS Domestic Classified Commercial and Industrial Loans | 2 | 0 | 2 |
| 1.30 LARGE WEEKLY REPORTING U.S. BRANCHES AND AGENCIES OF FOREIGN BANKS WITH ASSETS OF | 2 | 1 | 9 |
| 1.36 INTEREST RATES Money and Capital Markets | 2 | 1 | 0 |
| 1.37 SAVINGS INSTITUTIONS Selected Assets and Liabilities | 2 | 0 | 1 |
| 1.37 SELECTED FINANCIAL INSTITUTIONS Selected Assets and Liabilities | 2 | 1 | 11 |
| 1.38 SAVINGS INSTITUTIONS Selected Assets and Liabilities | 2 | 1 | 0 |
| 1.40 U.S. BUDGET RECEIPTS AND OUTLAYS | 2 | 1 | 0 |
| 1.42 U.S. GOVERNMENT MARKETABLE SECURITIES Ownership, by maturity | 2 | 0 | 2 |
| 1.43 U.S. GOVERNMENT MARKETABLE SECURITIES Ownership, by maturity | 2 | 1 | 0 |
| 1.51 TOTAL NONFARM BUSINESS EXPENDITURES on New Plant and Equipment | 2 | 0 | 2 |
| 1.52 DOMESTI C FINANC E COMPANIE S Business Credit | 2 | 0 | 1 |
| 1.52 DOMESTIC FINANCE COMPANIES Assets and Liabilities | 2 | 0 | 2 |
| 1.52 DOMESTIC FINANCE COMPANIES Business Credit Outstanding and Net Change1 | 2 | 1 | 8 |
| 1.52 DOMESTIC FINANCE COMPANIES Consumer, Real Estate, and Business Credit1 | 2 | 0 | 4 |
| 1.52 DOMESTIC FINANCE COMPANIES Owned and Managed Receivables1 | 2 | 1 | 5 |
| 1.52 DOMESTIC FINANCE COMPANIES1 | 2 | 0 | 1 |
| 1.53 DOMESTIC FINANCE COMPANIES Assets and Liabilities | 2 | 1 | 0 |
| 1.53 DOMESTIC FINANCE COMPANIES Business Credit | 2 | 0 | 2 |
| 1.53 MORTGAGE MARKETS | 2 | 1 | 8 |
| 1.53 MORTGAGE MARKETS Mortgages on New Homes | 2 | 1 | 11 |
| 1.54 MORTGAGE MARKETS | 2 | 0 | 2 |
| 1.55 CONSUMER CREDIT1 | 2 | 1 | 6 |
| 1.55 CONSUMER INSTALLMENT CREDIT Total Outstanding, and Net ChangeA | 2 | 0 | 3 |
| 1.55 CONSUMER INSTALLMENT CREDIT1 | 2 | 1 | 10 |
| 1.57 CONSUMER INSTALLMENT CREDIT1 Total Outstanding, and Net Change | 2 | 1 | 0 |
| 1.58 CONSUMER INSTALLMENT CREDIT Extensions and Liquidations | 2 | 1 | 0 |
| 1.58 DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS | 2 | 1 | 9 |
| 1.58 FUNDS RAISED IN U.S. CREDIT MARKETS | 2 | 0 | 2 |
| 1.58 SUMMARY OF FINANCIAL TRANSACTIONS1 | 2 | 1 | 10 |
| 1.59 DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS | 2 | 0 | 2 |
| 1.60 DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS | 2 | 1 | 0 |
| 1.60 SUMMARY OF CREDIT MARKET CLAIMS, BY HOLDER | 2 | 1 | 3 |
| 1.60 SUMMARY OF FINANCIAL ASSETS AND LIABILITIES1 | 2 | 1 | 10 |
| 2.16 GROSS DOMESTIC PRODUCT AND INCOME | 2 | 1 | 10 |
| 2.16 GROSS NATIONAL PRODUCT AND INCOME | 2 | 1 | 10 |
| 3.13 FOREIGN BRANCHES OF U.S. BANKS Balance Sheet Data | 2 | 0 | 1 |
| 3.14 FOREIGN BRANCHES OF U.S. BANKS Balance Sheet Data1 | 2 | 1 | 11 |
| 3.17 BANKS’ OWN CLAIMS ON FOREIGNERS Reported by Banks in the United States | 2 | 1 | 1 |
| 3.18 BANKS’ OWN AND DOMESTIC CUSTOMERS’ CLAIMS ON FOREIGNERS Reported by Banks in the | 2 | 1 | 1 |
| 3.21 CLAIMS ON FOREIGN COUNTRIES Held by U.S. and Foreign Offices of U.S. Banks' | 2 | 0 | 6 |
| 3.24 LIABILITIES TO UN AFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in the | 2 | 1 | 1 |
| 3.25 CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in the | 2 | 1 | 1 |
| 4.10 TIME AND SAVINGS DEPOSITS Held by Insured Commercial Banks on Recent Survey Dates | 2 | 1 | 0 |
| 4.20 DOMESTIC AND FOREIGN OFFICES, Commercial Banks with Assets of 100 Million or over1 | 2 | 0 | 1 |
| 4.20 DOMESTIC AND FOREIGN OFFICES, Insured Commercial Bank Assets and Liabilities1 2 | 2 | 1 | 3 |
| 4.21 DOMESTIC OFFICES, Insured Commercial Banks with Assets of 100 Million or more or with foreign office | 2 | 1 | 3 |
| 4.21 DOMESTIC OFFICES, Insured Commercial Banks with Assets of 100 Million or over | 2 | 0 | 1 |
| 4.22 DOMESTIC OFFICES, Insured Commercial Bank Assets and Liabilities1 | 2 | 1 | 4 |
| 4.23 TERMS OF LENDING AT COMMERCIAL BANKS Survey of Loans Made, 4-8, ' | 2 | 0 | 2 |
| 4.30 ASSETS AND LIABILITIES of U.S. Branches and Agencies of Foreign Banks, 31, ' | 2 | 1 | 5 |
