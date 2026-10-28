# Which Treasury families get a drafted template

Made by `python -m archivist.templates.families` before any template was drafted. No model was called and no held-out page was opened: families and their held-out counts are the survey's (`results/real/survey.md`, from the manifest's title hints), and only the development pages a family would be drafted from were read, through the PDF's own OCR text. Amended after drafting began, before any held-out page was touched: the families under "Set aside after the choice" were taken out and the next eligible family under the same rule took each one's place.

## The rule

1. A table, not a running heading: the family's title is not in capitals (the later bulletins print a section heading in capitals above each table's caption, and one heading covers several tables).
2. Found in development: pages in at least 2 development issues of one era (1939-1942 or 1982-1994: the era with more of its development pages). It is drafted from its first page in each such issue, at most 3, the issues spread evenly (first, middle, last).
3. Recurs in held-out: pages in at least 2 held-out issues of that era.
4. Prints totals: the word "total" is in the OCR text of every drafting page.
5. Ranked by held-out page count in its era, then title; the top 2 of each era, then the best of the rest from either era, up to 6 in all.

## Chosen (6)

| # | Family | Era | Held-out pages | Held-out issues | Development issues | Drafted from |
|--:|---|---|--:|--:|--:|---|
| 1 | `short_term_foreign_liabilities_as`: Short-Term Foreign Liabilities as Reported by Banks and Bankers | 1939-1942 | 97 | 27 | 12 | 1939-01_p051, 1939-07_p071, 1939-12_p053 |
| 2 | `security_transactions_as_reported_by`: Security Transactions as Reported by Banks, Bankers, Brokers and Dealers | 1939-1942 | 54 | 27 | 12 | 1939-01_p055, 1939-07_p075, 1939-12_p055 |
| 3 | `outstanding_forward_exchange_contracts`: Outstanding Forward Exchange Contracts as Reported by Banks | 1939-1942 | 27 | 27 | 12 | 1939-01_p061, 1939-07_p085, 1939-12_p060 |
| 4 | `receipts_and_expenditures_under_railroad`: Receipts and Expenditures Under Railroad Retirement and Railroad Unemployment | 1939-1942 | 25 | 25 | 4 | 1939-08_p043, 1939-10_p024, 1939-12_p025 |
| 5 | `total_claims_by_country`: Total Claims by Country | 1982-1994 | 22 | 10 | 3 | 1982-06_p094, 1983-06_p092, 1984-06_p058 |
| 6 | `total_liabilities_by_type_payable_in`: Total Liabilities by Type, Payable in Dollars | 1982-1994 | 10 | 10 | 2 | 1983-06_p088, 1984-06_p054 |

## Set aside after the choice (2)

| Family | Era | Held-out pages | Drafted from | Set aside on | Why |
|---|---|--:|---|---|---|
| Collections of Internal Revenue | 1939-1942 | 48 | 1939-02_p029, 1939-07_p023, 1939-12_p018 | 2026-10-28 | the title covers two different tables, collections by source of revenue and collections by period, and each is printed as two panels on one page (side by side, or one above the other); a page is classified as one type, so each would be one template with two panels, which the template language cannot yet describe. Its draft read the by-period table's columns across all three pages, two of which print the by-source table (results/templates/citations_dev.md) |
| Total Liabilities by Country | 1982-1994 | 24 | 1982-06_p091, 1983-06_p097, 1984-06_p055 | 2026-10-28 | not approved: its evidence is too thin, because the grid (S0+grid) cannot place rows on two of its three development pages (1983-06_p097, 1984-06_p055), so 6 of its 8 identities went untested (templates/total_liabilities_by_country.evidence.json) |

## Passed every rule but not chosen (12)

| Family | Era | Held-out pages |
|---|---|--:|
| Net Movement of Silver to and from the United States | 1939-1942 | 24 |
| Dollar Liabilities to, and Dollar Claims on, Foreigners | 1982-1994 | 9 |
| Foreign Purchases and Sales of Long-Term Securities, by Type and Country, During Fir | 1982-1994 | 9 |
| Interest-Bearing Securities Issued by Government Agencies | 1982-1994 | 9 |
| Expenditures - General | 1939-1942 | 7 |
| Expenditures - Revolving Funds (Net), and Transfers to Trust Accounts, etc | 1939-1942 | 7 |
| Dollar Claims on Nonbank Foreigners | 1982-1994 | 6 |
| Total Claima by Type and Country as of December 31 1981 | 1982-1994 | 6 |
| Total Liabilities and Claims by Type | 1982-1994 | 6 |
| — Foreign Purchases and Sales of Long-Term Domestic Securities by Type | 1982-1994 | 6 |
| Total Claims by Type | 1982-1994 | 3 |
| Treasury Bill Offerings | 1939-1942 | 2 |

## Excluded, by the first rule failed

| Rule | Families | Of which with 10+ held-out pages |
|---|--:|---|
| 1 | 68 | FEDERAL RECEIPTS AND EXPENDITURES (89); FEDERAL FISCAL OPERATIONS (62); CAPITAL MOVEMENTS (57); BULLETIN (54); CASH INCOME AND OUTGO OF THE TREASURY (51); GOVERNMENTAL CORPORATIONS (39); LIBRARY (31); CAPITAL MOVEMENTS BETWEEN (27); PUBLIC DEBT OPERATIONS (24); FEDERAL DEBT (22); GENERAL FUND OF THE TREASURY (22); GOLD AND SILVER STATISTICS (22); INTERNAL REVENUE STATISTICS (22); FOREIGN CURRENCY POSITIONS (21); OTHER TREASURY STATISTICS (21); TREASURY FINANCING OPERATIONS, JANUARY-MARCH 1987 (19); OWNERSHIP OF GOVERNMENT SECURITIES (18); EXCHANGE STABILIZATION FUND (15); FEDERAL OBLIGATIONS (15); SUMMARY OF FISCAL STATISTICS (15); DEPARTMENT OF THE TREASURY (14); MISCELLANEOUS (14); OTHER MONETARY STATISTICS (14); TREASURY GENERAL FUND AND PUBLIC DEBT (14); CASH INCOME AND OUTGO AND NET CASH OUTGO (13); CUSTOMS STATISTICS (13); US TREASURY LIBRARY (13); GOVERNMENT SECURITIES OUTSTANDING (12); INTERNATIONAL FINANCIAL STATISTICS (12); PRICES AND YIELDS OF GOVERNMENT SECURITIES (12); PUBLIC DEBT OF THE UNITED STATES (10) |
| 2 | 130 | Sources of Funds of Certain Governmental Corporations and Credit Agencies (140); Summary Data from Treasury Survey of Ownership of Securities (107); Assets and Liabilities of Governmental Corporations and Credit Agencies (46); Vessels Cleared from the United States, Direct for Foreign Ports, (38); Bulletin of the Treasury Department, August 1942 (36); Over-the-Counter Closing Quotations on Public Marketable Securities Issued by the (36); Seigniorage on Silver (26); Sales Reported by Series, Classified by Denomination (25); Summary Distribution by Classes of Holders of Interest-Bearing Securities Issued (24); 4.--Total Liabilities by Type and Country, Mar. 31, 1992, Preliminary, Con (23); Assets of the General Fund of the Treasury (22); Maturity Schedule of Interest-Bearing Public Marketable Securities (20); Maturity Schedule of United States Government Interest-Bearing Public Debt Outstanding^ (20); Maturity Schedule of Securities Guaranteed by the United States^ (19); Detailed Analysis of Current Internal Revenue Collections!/ (18); Summary of Internal Revenue Collections^ (18); Maturity Schedule (17); Statement of the Outstanding Publ (17); Treasury Department Criminal Cases In the United States District Courts^ (16); Analysis of Change In Balance of General Fund of the Treasury (15); Analysis of Expenditures for (1) Revolving Funds and (2) Transfers to Trust Accounts, Etc (15); Custom Duties and Taxes Collected, Estimated by Countries from which Imports Originated (15); Means of Financing Cash Requirements (15); Sales Reported by Series, Classified by Type of Purchaser (15); Computed Annual Interest Charge and Computed Rate of Interest on the Interest-Bearing Public Debt Ou (14); Foreign Purchases and Sales of Long-Term Securities, (14); Appropriations and Net Contract Authorizations for the War Activities Program (13); Monetary Stocks of Gold and Silver (13); Summary (13); Summary, by Series (13); Trust Funds (13); Analysis of General Expenditures (12); Budget Expenditures Classified as General, by Major Functions^ (11); Social Security Act (11); Summary Table on Budget Receipts and Expenditures and Public Debt Outstanding (11); Railroad Retirement Act (10); Total Budget Receipts and Expenditures, by Months (10) |
| 3 | 12 | - |
| 4 | 46 | Nonbanking Firms' Positions (55); Gold Assets and Liabilities of the Treasury (35); Principal of Outstanding Obligations Guaranteed by the United States (31); Net Capital Movement between the United States and Foreign Countries (27); Purchases and Sales of Foreign Exchange, Spot and Forward, as Reported (27); Public Offerings of Marketable Securities (26); Security Transactions In Joint Foreign Arbitrage Accounts as Reported (25); Receipts and Expenditures under Social Security Act (24); Gross Obligations Incurred Outside the Federal Government by (23); Statement Showing Details of Major Financing Operations of the Treasury (22); Commodities Imported Under Quota Provisions (21); Components of Silver Monetary Stock (21); Monthly Receipts, Expenditures and Excess of Expenditures (20); Maturity Schedule of Interest-Bearing Marketable Public Debt Securities Other than (19); Allotments by Investor Classes for Public Marketable Securities (18); Contents (17); U.S. Currency and Coin Outstanding and in Circulation (16); Balance Sheet of the Exchange Stabilization Fund (15); Customs Duties and Taxes Collected, and Values of Dutiable and Taxable Imports, (15); Composition of General Fund (12); Holdings of Direct and Guaranteed Interest-Bearing Obligations of the United States Government (12); Distribution of Federal Securities by Class of Investors and Type of Issues (11); Average Yields of Long-Term Treasury and Corporate Bonds (10); Government Account Series (10); Net Foreign Transactions in Long-Term Domestic Securities by Type and Country (10); Nonbanking Firms' Foreign Subsidiaries' Positions (10); Selected U.S. Liabilities to Foreigners (10); Summary of Criminal Cases in the United States (10); Summary of Federal Debt (10); Summary Table on Receipts, Expenditures and Public Debt (10); Treasury Holdings of Securities Issued by Government Corporations and Other Agencies (10); Treasury Market Bid Yields at Constant Maturities: Bills, Notes, and Bonds (10) |
