# Survey of the recurring table families: Treasury Bulletin, FRASER title 407

Made by `python -m archivist.ingest.survey` from the title hints in `data/real/manifest.json` (the first lines of each PDF's own OCR text). No model was called and no page image was looked at. 61 issues, 6,165 pages.

## How to read it

- A page's *title* is its table caption if the hint has one (`Table FD-1. - Summary of Federal Debt` gives `Summary of Federal Debt`), else the first hint line that reads as a heading: mostly letters, in title or upper case, not a unit line such as `(In millions of dollars)`. Table numbers and page numbers are dropped.
- Titles are merged into one family when their normalised text is at least 85% alike, or when one is the first 25+ characters of the other (the same heading wrapped at a different word), so OCR misspellings of a heading usually join. A family is shown under its commonest spelling.
- The OCR is poor on the 1939–1942 scans, so counts are approximate: a family can be split in two by a bad misreading, and two real tables with near-identical headings can be merged.
- A hint keeps only the first 100 characters of a line, so a caption that shares its line with a section heading can be cut short (`Statements of In`); such stubs form their own small families.
- Only families found in two or more issues are listed. Page counts are over all issues.

## Totals

| | pages |
|---|---:|
| all pages | 6,165 |
| in a family found in 2+ issues | 4,237 |
| in a title found in one issue only (230 titles) | 316 |
| skipped: no OCR text | 1,113 |
| skipped: no heading in the first lines | 499 |

## Recurring families (276)

| # | Title | Issues | Pages | Appears in (months: years) |
|--:|---|--:|--:|---|
| 1 | FEDERAL RECEIPTS AND EXPENDITURES | 48 | 101 | 01–12: 1939–1942 |
| 2 | CASH INCOME AND OUTGO OF THE TREASURY | 47 | 63 | 01–12: 1939, 1941–1942; 01–09, 11–12: 1940 |
| 3 | Gold Assets and Liabilities of the Treasury | 47 | 47 | 02–12: 1939; 01–12: 1940, 1942; 01–06, 08–12: 1941; 06: 1982 |
| 4 | BULLETIN | 45 | 69 | 01–12: 1939–1941; 01–03, 05–06, 08–09, 11–12: 1942 |
| 5 | Collections of Internal Revenue | 44 | 70 | 02–12: 1939, 1942; 01–12: 1940; 01–06, 09–12: 1941 |
| 6 | GOVERNMENTAL CORPORATIONS | 44 | 62 | 01–12: 1939–1941; 01–08: 1942 |
| 7 | Principal of Outstanding Obligations Guaranteed by the United States | 42 | 42 | 02–12: 1939; 01–12: 1940–1941; 01–07: 1942 |
| 8 | Short-Term Foreign Liabilities as Reported by Banks and Bankers | 39 | 121 | 01–12: 1939–1941; 01–03: 1942 |
| 9 | Security Transactions as Reported by Banks, Bankers, Brokers and Dealers | 39 | 66 | 01–12: 1939–1941; 01–03: 1942 |
| 10 | Net Capital Movement between the United States and Foreign Countries | 39 | 39 | 01–12: 1939–1941; 01–03: 1942 |
| 11 | Outstanding Forward Exchange Contracts as Reported by Banks | 39 | 39 | 01–12: 1939–1941; 01–03: 1942 |
| 12 | Purchases and Sales of Foreign Exchange, Spot and Forward, as Reported | 39 | 39 | 01–12: 1939–1941; 01–03: 1942 |
| 13 | Contents | 38 | 51 | 01–12: 1939–1940; 01–05: 1941; 06: 1982, 1987–1994 |
| 14 | CAPITAL MOVEMENTS BETWEEN | 38 | 38 | 02–12: 1939; 01–12: 1940–1941; 01–03: 1942 |
| 15 | Sources of Funds of Certain Governmental Corporations and Credit Agencies | 37 | 144 | 12: 1939; 01–12: 1940–1942 |
| 16 | Security Transactions In Joint Foreign Arbitrage Accounts as Reported | 37 | 37 | 01–12: 1939, 1941; 01–05, 07, 09–12: 1940; 01–03: 1942 |
| 17 | Net Movement of Silver to and from the United States | 35 | 35 | 02–12: 1939; 01–12: 1940–1941 |
| 18 | Receipts and Expenditures under Social Security Act | 35 | 35 | 02–12: 1939; 01–12: 1940; 01–04, 06–12: 1941; 01: 1942 |
| 19 | Commodities Imported Under Quota Provisions | 33 | 33 | 01–12: 1939; 01–10, 12: 1940; 01–09, 11: 1941 |
| 20 | Components of Silver Monetary Stock | 33 | 33 | 01–12: 1939, 1942; 01–09: 1940 |
| 21 | LIBRARY | 31 | 37 | 10–12: 1939; 01–03, 05, 07–12: 1940; 01–03, 08–12: 1941; 02–04, 09–12: 1942; 06: 1982, 1985, 1989 |
| 22 | Average Yields of Long-Term Treasury and Corporate Bonds | 29 | 31 | 07–12: 1941; 02–12: 1942; 06: 1983–1994 |
| 23 | Receipts and Expenditures Under Railroad Retirement and Railroad Unemployment | 29 | 29 | 08–10, 12: 1939; 01–12: 1940–1941; 01: 1942 |
| 24 | Assets and Liabilities of Governmental Corporations and Credit Agencies | 27 | 46 | 10–12: 1940; 01–12: 1941–1942 |
| 25 | Statement Showing Details of Major Financing Operations of the Treasury | 27 | 30 | 01, 03, 06, 11–12: 1939; 01, 03–05, 07–12: 1940; 01–12: 1941 |
| 26 | MISCELLANEOUS | 26 | 26 | 01–12: 1939–1940; 01–02: 1941 |
| 27 | OTHER MONETARY STATISTICS | 26 | 26 | 01–12: 1939–1940; 01–02: 1941 |
| 28 | Seigniorage on Silver | 26 | 26 | 11–12: 1940; 01–12: 1941–1942 |
| 29 | TREASURY GENERAL FUND AND PUBLIC DEBT | 26 | 26 | 01–12: 1939–1940; 01–02: 1941 |
| 30 | CASH INCOME AND OUTGO AND NET CASH OUTGO | 25 | 25 | 01–12: 1939–1940; 01: 1941 |
| 31 | Foreign Purchases and Sales of Long-Term Securities, | 24 | 33 | 10–12: 1940; 01–12: 1941; 01–03: 1942; 06: 1982, 1987, 1990–1991, 1993–1994 |
| 32 | Composition of General Fund | 24 | 24 | 01–12: 1939; 01–05, 07–10, 12: 1940; 01–02: 1941 |
| 33 | Holdings of Direct and Guaranteed Interest-Bearing Obligations of the United States Government | 24 | 24 | 01–12: 1939–1940 |
| 34 | Summary Distribution by Classes of Holders of Interest-Bearing Securities Issued | 24 | 24 | 01–12: 1941–1942 |
| 35 | Assets of the General Fund of the Treasury | 22 | 22 | 03–12: 1941; 01–12: 1942 |
| 36 | Customs Duties and Taxes Collected, and Values of Dutiable and Taxable Imports, | 22 | 22 | 02–03, 05–09: 1939; 10–12: 1940; 01–12: 1941 |
| 37 | GENERAL FUND OF THE TREASURY | 22 | 22 | 03–12: 1941; 01–12: 1942 |
| 38 | GOLD AND SILVER STATISTICS | 22 | 22 | 03–12: 1941; 01–12: 1942 |
| 39 | INTERNAL REVENUE STATISTICS | 22 | 22 | 03–12: 1941; 01–12: 1942 |
| 40 | Monthly Receipts, Expenditures and Excess of Expenditures | 21 | 36 | 05–12: 1939; 01–12: 1940; 01: 1941 |
| 41 | OTHER TREASURY STATISTICS | 21 | 21 | 03–12: 1941; 01–02, 04–12: 1942 |
| 42 | Summary of Criminal Cases in the United States | 21 | 21 | 01–06, 08–12: 1939; 01–10: 1940 |
| 43 | Summary Table on Receipts, Expenditures and Public Debt | 21 | 21 | 02–12: 1939; 01–10: 1940 |
| 44 | Vessels Cleared from the United States, Direct for Foreign Ports, | 20 | 38 | 05–12: 1940; 01–12: 1941 |
| 45 | Maturity Schedule of Securities Guaranteed by the United States^ | 19 | 19 | 08–12: 1940; 01–12: 1941; 01–02: 1942 |
| 46 | Value of Selected Currencies In Terms of Gold | 19 | 19 | 03–12: 1939; 01–09: 1940 |
| 47 | Summary Data from Treasury Survey of Ownership of Securities | 18 | 107 | 07–12: 1941; 01–12: 1942 |
| 48 | Detailed Analysis of Current Internal Revenue Collections!/ | 18 | 18 | 07–12: 1941; 01–12: 1942 |
| 49 | OWNERSHIP OF GOVERNMENT SECURITIES | 18 | 18 | 07–12: 1941; 01–12: 1942 |
| 50 | Summary of Internal Revenue Collections^ | 18 | 18 | 07–12: 1941; 01–12: 1942 |
| 51 | Bulletin of the Treasury Department, August 1942 | 17 | 37 | 01: 1939; 06–08, 10, 12: 1941; 01–08, 10–12: 1942 |
| 52 | Amount of Interest-bearing Debt Outstanding, the Computed Annual Interest | 17 | 17 | 01–04, 06, 08–12: 1939; 01–07: 1940 |
| 53 | Estimated Receipts from Taxes Imposed by Various Revenue Acts on Imports | 17 | 17 | 03, 05–12: 1939; 02–09: 1940 |
| 54 | Foreign Purchases and Sales and Net Purchases or Sales of U.S. Domestic Securities | 17 | 17 | 05–12: 1939; 01–09: 1940 |
| 55 | Statement of the Outstanding Publ | 17 | 17 | 03–12: 1941; 01–07: 1942 |
| 56 | Treasury Department Criminal Cases In the United States District Courts^ | 16 | 16 | 11–12: 1940; 01–12: 1941; 01–02: 1942 |
| 57 | Balance Sheet of the Exchange Stabilization Fund | 15 | 21 | 03, 07, 10: 1939; 01, 04, 07, 10: 1940–1942 |
| 58 | Analysis of Change In Balance of General Fund of the Treasury | 15 | 15 | 10–12: 1941; 01–12: 1942 |
| 59 | Analysis of Expenditures for (1) Revolving Funds and (2) Transfers to Trust Accounts, Etc | 15 | 15 | 10–12: 1941; 01–12: 1942 |
| 60 | Custom Duties and Taxes Collected, Estimated by Countries from which Imports Originated | 15 | 15 | 10–12: 1940; 01–12: 1941 |
| 61 | Expenditures - General | 15 | 15 | 05–12: 1939; 01–04, 06–07, 10: 1940 |
| 62 | Expenditures - Revolving Funds (Net), and Transfers to Trust Accounts, etc | 15 | 15 | 05–12: 1939; 01–07: 1940 |
| 63 | SUMMARY OF FISCAL STATISTICS | 15 | 15 | 10–12: 1941; 01–12: 1942 |
| 64 | CAPITAL MOVEMENTS | 14 | 70 | 01: 1939; 06: 1982–1994 |
| 65 | Means of Financing Cash Requirements | 14 | 15 | 10–12: 1941; 01–09, 11–12: 1942 |
| 66 | Computed Annual Interest Charge and Computed Rate of Interest on the Interest-Bearing Public Debt Ou | 14 | 14 | 09, 11–12: 1940; 01–06: 1941; 08–12: 1942 |
| 67 | Nonbanking Firms' Positions | 13 | 69 | 06: 1982–1994 |
| 68 | FEDERAL FISCAL OPERATIONS | 13 | 66 | 06: 1982–1994 |
| 69 | Maturity Schedule of Interest-Bearing Public Marketable Securities | 13 | 38 | 03–12: 1942; 06: 1992–1994 |
| 70 | Public Offerings of Marketable Securities | 13 | 31 | 06: 1982–1994 |
| 71 | FOREIGN CURRENCY POSITIONS | 13 | 30 | 06: 1982–1994 |
| 72 | Gross Obligations Incurred Outside the Federal Government by | 13 | 29 | 06: 1982–1994 |
| 73 | Total Liabilities by Country | 13 | 29 | 06: 1982–1994 |
| 74 | Total Claims by Country | 13 | 28 | 06: 1982–1994 |
| 75 | Allotments by Investor Classes for Public Marketable Securities | 13 | 22 | 06: 1982–1994 |
| 76 | FEDERAL OBLIGATIONS | 13 | 19 | 06: 1982–1994 |
| 77 | CUSTOMS STATISTICS | 13 | 13 | 03–12: 1941; 01–03: 1942 |
| 78 | Government Account Series | 13 | 13 | 06: 1982–1994 |
| 79 | Monetary Stocks of Gold and Silver | 13 | 13 | 10–12: 1940; 01–07, 09–10, 12: 1941 |
| 80 | Selected U.S. Liabilities to Foreigners | 13 | 13 | 06: 1982–1994 |
| 81 | Summary of Federal Debt | 13 | 13 | 06: 1982–1994 |
| 82 | Trust Funds | 13 | 13 | 10–12: 1941; 01, 04–12: 1942 |
| 83 | US TREASURY LIBRARY | 13 | 13 | 02, 06–10: 1941; 04–05, 07–10, 12: 1942 |
| 84 | Over-the-Counter Closing Quotations on Public Marketable Securities Issued by the | 12 | 36 | 01–12: 1942 |
| 85 | PUBLIC DEBT OPERATIONS | 12 | 28 | 06: 1982–1986, 1988–1994 |
| 86 | U.S. Currency and Coin Outstanding and in Circulation | 12 | 18 | 06: 1983–1994 |
| 87 | EXCHANGE STABILIZATION FUND | 12 | 17 | 06: 1983–1994 |
| 88 | Distribution of Federal Securities by Class of Investors and Type of Issues | 12 | 14 | 06: 1982–1986, 1988–1994 |
| 89 | Summary | 12 | 14 | 07: 1939; 10: 1941; 01, 04–12: 1942 |
| 90 | Analysis of General Expenditures | 12 | 12 | 10–12: 1941; 01–08, 11: 1942 |
| 91 | GOVERNMENT SECURITIES OUTSTANDING | 12 | 12 | 01–12: 1942 |
| 92 | Nonbanking Firms' Foreign Subsidiaries' Positions | 12 | 12 | 06: 1983–1994 |
| 93 | PRICES AND YIELDS OF GOVERNMENT SECURITIES | 12 | 12 | 01–12: 1942 |
| 94 | Summary of Fiscal Operations | 12 | 12 | 06: 1982–1985, 1987–1994 |
| 95 | Total Liabilities by Type, Payable in Dollars | 12 | 12 | 06: 1983–1994 |
| 96 | Treasury Holdings of Securities Issued by Government Corporations and Other Agencies | 12 | 12 | 06: 1983–1994 |
| 97 | Treasury Market Bid Yields at Constant Maturities: Bills, Notes, and Bonds | 12 | 12 | 06: 1983–1994 |
| 98 | 4.--Total Liabilities by Type and Country, Mar. 31, 1992, Preliminary, Con | 11 | 25 | 06: 1983, 1985–1994 |
| 99 | INTERNATIONAL FINANCIAL STATISTICS | 11 | 15 | 06: 1982–1991, 1993 |
| 100 | Budget Expenditures Classified as General, by Major Functions^ | 11 | 11 | 11–12: 1940; 01–09: 1941 |
| 101 | Customs Duties and Taxes Estimated, and Value of Dutiable | 11 | 11 | 10–12: 1939; 02–09: 1940 |
| 102 | Dollar Liabilities to, and Dollar Claims on, Foreigners | 11 | 11 | 06: 1983–1992, 1994 |
| 103 | Interest-Bearing Securities Issued by Government Agencies | 11 | 11 | 06: 1983–1984, 1986–1994 |
| 104 | Ratios of Index of Wholesale Prices | 11 | 11 | 02–12: 1939 |
| 105 | Sales and Redemptions by Period, Series E, EE, H, and HH | 11 | 11 | 06: 1983–1986, 1988–1994 |
| 106 | Social Security Act | 11 | 11 | 02–12: 1942 |
| 107 | Summary Table on Budget Receipts and Expenditures and Public Debt Outstanding | 11 | 11 | 11–12: 1940; 01–09: 1941 |
| 108 | FEDERAL DEBT | 10 | 25 | 06: 1982, 1985, 1987–1994 |
| 109 | TREASURY FINANCING OPERATIONS, JANUARY-MARCH 1987 | 10 | 24 | 06: 1982–1991 |
| 110 | Maturity Schedule of United States Government Interest-Bearing Public Debt Outstanding^ | 10 | 20 | 08–12: 1940; 01–05: 1941 |
| 111 | Statement of Sources of Funds of Certain Corporations and Agencies Maintaining Checking | 10 | 20 | 02–11: 1939 |
| 112 | DEPARTMENT OF THE TREASURY | 10 | 15 | 06: 1982, 1985–1990, 1992–1994 |
| 113 | U.S. SAVINGS BONDS AND NOTES | 10 | 11 | 06: 1983–1991, 1993 |
| 114 | "Maturity Distribution and Average Length of Marketable | 10 | 10 | 06: 1983–1987, 1990–1994 |
| 115 | ACCOUNT OF THE U.S. TREASURY | 10 | 10 | 06: 1983–1991, 1993 |
| 116 | Computed Duties Collected, by Countries | 10 | 10 | 11–12: 1939; 02–09: 1940 |
| 117 | PUBLIC DEBT OF THE UNITED STATES | 10 | 10 | 03–12: 1941 |
| 118 | Railroad Retirement Act | 10 | 10 | 02–09, 11–12: 1942 |
| 119 | Total Budget Receipts and Expenditures, by Months | 10 | 10 | 11: 1940; 01–09: 1941 |
| 120 | Sales Reported by Series, Classified by Denomination | 9 | 25 | 04–12: 1942 |
| 121 | Maturity Schedule | 9 | 17 | 06–12: 1941; 01–02: 1942 |
| 122 | Net Foreign Transactions in Long-Term Domestic Securities by Type and Country | 9 | 12 | 06: 1983–1987, 1989, 1992–1994 |
| 123 | Offerings of Bills | 9 | 10 | 06: 1982–1988, 1993–1994 |
| 124 | Total Claims on Foreigners by Type and Country Reported by Banks in the United Stat | 9 | 10 | 06: 1982, 1985–1987, 1989, 1991–1994 |
| 125 | Contents - (Continued) | 9 | 9 | 03–05, 07–12: 1941 |
| 126 | Federal Old-Age and Survivors Insurance Trust Fund^ | 9 | 9 | 02–03, 05–08, 10–12: 1942 |
| 127 | Gross Sales by States | 9 | 9 | 04–12: 1942 |
| 128 | Net Capital Movement to the United States, 1035 through August 1042 | 9 | 9 | 04–12: 1942 |
| 129 | Offerings and Maturities of Treasury Bills, Beginning April 1, 1941 | 9 | 9 | 04–12: 1942 |
| 130 | Offerings of Bills-Continued | 9 | 9 | 06: 1983–1991 |
| 131 | Public Debt Outstanding | 9 | 9 | 11–12: 1941; 01–07: 1942 |
| 132 | Redemptions by Series, Classified by Means of Payment | 9 | 9 | 04–12: 1942 |
| 133 | Schedules for Balance Sheet of the Exchange Stabilization Fund - (Continued) | 9 | 9 | 10: 1940; 01, 04, 07, 10: 1941–1942 |
| 134 | Statement of the Debt Position of the United States Government under Limitations | 9 | 9 | 10: 1940; 01, 04, 07, 10: 1941–1942 |
| 135 | Summary by Major Classifications | 9 | 9 | 02–03, 05–08, 10–12: 1942 |
| 136 | Total Claima by Type and Country as of December 31 1981 | 9 | 9 | 06: 1982–1990 |
| 137 | TREASURY | 9 | 9 | 08: 1939; 04: 1940; 06: 1983–1986, 1989, 1991–1992 |
| 138 | Maturity Schedule of Interest-Bearing Marketable Public Debt Securities Other than | 8 | 21 | 06: 1982, 1984, 1986–1991 |
| 139 | Sales Reported by Series, Classified by Type of Purchaser | 8 | 15 | 04–11: 1942 |
| 140 | Dollar Claims on Nonbank Foreigners | 8 | 8 | 06: 1982–1983, 1985–1987, 1992–1994 |
| 141 | REFERENCE | 8 | 8 | 02, 06, 08–09, 11–12: 1939; 03: 1940; 07: 1941 |
| 142 | SPECIAL REPORTS | 8 | 8 | 06: 1985, 1987–1991, 1993–1994 |
| 143 | Summary, by Series - (Continued) | 8 | 8 | 05–12: 1942 |
| 144 | Total Cla | 8 | 8 | 06: 1984–1991 |
| 145 | Total Liabilities and Claims by Type | 8 | 8 | 06: 1982, 1984–1987, 1989–1991 |
| 146 | YIELDS OF TREASURY BONDS AND NOTES, APR. 15. 1942 | 8 | 8 | 04–11: 1942 |
| 147 | MARKET YIELDS | 7 | 19 | 06: 1988–1994 |
| 148 | Appropriations and Net Contract Authorizations for the War Activities Program | 7 | 13 | 06–12: 1942 |
| 149 | Summary, by Series | 7 | 13 | 05–10, 12: 1942 |
| 150 | Foreign Purchases and Sales of Long-Term Securities, by Type and Country, During Fir | 7 | 12 | 06: 1983–1986, 1988–1989, 1992 |
| 151 | Sales Reported by Series, Classified by States - (Continued) | 7 | 8 | 06–12: 1942 |
| 152 | Ca0h Income and Outgo of the Treasury, by Major Classlflcatlons | 7 | 7 | 07–09: 1941; 01–02, 04, 10: 1942 |
| 153 | Estimated Ownership of Public Debt Securities by Private Investors | 7 | 7 | 06: 1982, 1989–1994 |
| 154 | Nonquarterly Tables and Reports | 7 | 7 | 06: 1988–1994 |
| 155 | Total Liabilities by Type of Holder | 7 | 7 | 06: 1986–1987, 1990–1994 |
| 156 | Weighted Average of Exchange Rate Changes for the Dollar | 7 | 7 | 06: 1982–1988 |
| 157 | — Direct and Guaranteed Loans, Dec. 31, 1986 —Continued | 6 | 18 | 06: 1987–1992 |
| 158 | FEDERAL AGENCIES' FINANCIAL REPORTS | 6 | 11 | 06: 1987–1992 |
| 159 | — Foreign Purchases and Sales of Long-Term Domestic Securities by Type | 6 | 8 | 06: 1983–1984, 1986, 1992–1994 |
| 160 | 0n-budget and Off-budget Receipts by Source-Continued | 6 | 6 | 06: 1986–1991 |
| 161 | Composition of the Public Debt | 6 | 6 | 01–06: 1939 |
| 162 | COPY No | 6 | 6 | 04–06: 1939; 05–06, 09: 1942 |
| 163 | Elements of Changes in Federal Reserve and Tax and Loan Note Account Balances-Con | 6 | 6 | 06: 1982, 1988–1992 |
| 164 | FINANCIAL OPERATIONS | 6 | 6 | 06: 1983, 1987–1991 |
| 165 | Information about the Superintendent of Documents Subscription Service | 6 | 6 | 06: 1989–1994 |
| 166 | Offerings of Marketable Issues of Treasury Bonds and Treasury Notes | 6 | 6 | 01–06: 1942 |
| 167 | Offerings of Marketable Issues of Treasury Bonds, Notes, and Certificates of Indebtedness | 6 | 6 | 07–12: 1942 |
| 168 | Other Commodities - with Quotas Applicable to Specific Countries | 6 | 6 | 10–12: 1941; 01–03: 1942 |
| 169 | Receipts and Expenditures Under Railroad Retirement Act | 6 | 6 | 03–07, 11: 1939 |
| 170 | TREASURY ISSUES | 5 | 20 | 06: 1988–1992 |
| 171 | Bulletin of the Treaaury Department, September 1042 | 5 | 8 | 09, 11–12: 1941; 09, 11: 1942 |
| 172 | Statement of the Public Debt and Guaranteed Obligations Outstanding | 5 | 7 | 08–12: 1942 |
| 173 | 0n-budget and Off-budget Outlays by Agency-Continued | 5 | 5 | 06: 1986–1989, 1991 |
| 174 | ADDITIONAL FINANCIAL MANAGEMENT SERVICE | 5 | 5 | 06: 1989–1992, 1994 |
| 175 | AVERAGE YIELDS OF LONG-TERM BONDS | 5 | 5 | 06: 1983–1987 |
| 176 | Bank Holdings of U.S. Government Obligations and Securities Guaranteed | 5 | 5 | 03, 06, 09: 1939; 04, 10: 1940 |
| 177 | Composition of the Interest-Bearing Public Debt | 5 | 5 | 08–12: 1942 |
| 178 | Imports of Cotton and Cotton Waste under Quota Provisions | 5 | 5 | 05–09: 1941 |
| 179 | INTERNATIONAL STATISTICS | 5 | 5 | 06: 1987–1991 |
| 180 | Participation in Payroll Savings Plans For War Savings Bonds^ | 5 | 5 | 08–12: 1942 |
| 181 | Products of Philippine Islands | 5 | 5 | 10, 12: 1941; 01–03: 1942 |
| 182 | Sales of Tax Series Treasury Notes!/ | 5 | 5 | 01–03, 11–12: 1942 |
| 183 | Sales of United States Savings Bonds!/ | 5 | 5 | 01–03, 12: 1942; 06: 1982 |
| 184 | SPRING ISSUE | 5 | 5 | 06: 1983–1984, 1989–1991 |
| 185 | Total Claims by Type | 5 | 5 | 06: 1982–1983, 1992–1994 |
| 186 | Treas. U.S. Treasury Dept | 5 | 5 | 04: 1941; 01, 03, 10–11: 1942 |
| 187 | Treasury Bill Offerings | 5 | 5 | 05, 08, 11: 1939; 02, 05: 1940 |
| 188 | U.S. CURRENCY AND COIN | 5 | 5 | 06: 1983–1987 |
| 189 | PROFILE OF THE ECONOMY | 4 | 26 | 06: 1991–1994 |
| 190 | TAX POLICY | 4 | 14 | 06: 1988–1991 |
| 191 | Budget Receipts by Source | 4 | 8 | 06: 1982–1985 |
| 192 | Glossary | 4 | 8 | 06: 1991–1994 |
| 193 | IV Contents | 4 | 8 | 06: 1988–1991 |
| 194 | TotaI Claims by Type and Country, Dec. 31, 1991, Preliminary | 4 | 7 | 06: 1991–1994 |
| 195 | Average Yields of Long-Term Treasury, Corporate, and Municipal Bonds, Con | 4 | 4 | 06: 1982, 1992–1994 |
| 196 | Federal Expenditures - Recovery and Relief | 4 | 4 | 01–04: 1939 |
| 197 | Imports of Wheat and Wheat Products | 4 | 4 | 10–12: 1941; 01: 1942 |
| 198 | MARKET BID YIELDS ON TREASURY SECURITIE':, VAP 31, 1983 | 4 | 4 | 06: 1983, 1985–1987 |
| 199 | NATIONAL BANK REPORT | 4 | 4 | 06: 1983–1986 |
| 200 | Nonmarketable U.S. Treasury Bonds and Notes Issued | 4 | 4 | 06: 1982, 1992–1994 |
| 201 | OWNERSHIP OF FEDERAL SECURITIES | 4 | 4 | 06: 1987, 1990–1991, 1993 |
| 202 | Statement of Sources of Funds of Certain Governmental Corporations | 4 | 4 | 02–05: 1939 |
| 203 | Summary of Federal Receipts and Expenditures | 4 | 4 | 01–04: 1939 |
| 204 | Summary Table - Change In Short-Term Foreign Liabilities and Assets | 4 | 4 | 03: 1939–1942 |
| 205 | The Treasury Bulletin is issued quarterly in March, June, September, and December by the Financial M | 4 | 4 | 06: 1991–1994 |
| 206 | Total Lcabilities by Type and Country, as of Dec. 31, 1986, Preliminary | 4 | 4 | 06: 1984–1985, 1987, 1989 |
| 207 | UNITED STATES | 4 | 4 | 06: 1982–1984, 1991 |
| 208 | Treasury Bulletin | 3 | 13 | 06: 1982, 1987–1988 |
| 209 | Amounts Outstanding and in Circulation, Mar. 31, 1992 | 3 | 6 | 06: 1992–1994 |
| 210 | Budget Outlays by Agency-Continued | 3 | 4 | 06: 1982, 1984–1985 |
| 211 | Government Securities, by Issues, and Other Securities Held as Investments (1) In Trust Funds | 3 | 4 | 01, 08: 1939; 02: 1940 |
| 212 | TREASURY DEPARTMENT | 3 | 4 | 07: 1941; 01, 07: 1942 |
| 213 | Budget Outlays by Agency | 3 | 3 | 06: 1982–1984 |
| 214 | CASH MANAGEMENT INITIATIVES | 3 | 3 | 06: 1984–1986 |
| 215 | FINANCIAL | 3 | 3 | 06: 1992–1994 |
| 216 | GOVERNMENT CORPORATIONS AND CREDIT | 3 | 3 | 09, 11–12: 1942 |
| 217 | Interest-Bearing Public Debt | 3 | 3 | 06: 1992–1994 |
| 218 | INTERNATIONAL | 3 | 3 | 06: 1992–1994 |
| 219 | Net Foreign Transactions m Long-Term Domestic Securities by Type and Country | 3 | 3 | 06: 1988, 1990–1991 |
| 220 | Public Debt and Guaranteed ObligationB Outstanding | 3 | 3 | 09–11: 1942 |
| 221 | Revisions In Statistics on Capital Movements between | 3 | 3 | 12: 1940; 03, 09: 1941 |
| 222 | Sales and Redemptions by Series, Cumulative through Mar. 31, 1992 | 3 | 3 | 06: 1992–1994 |
| 223 | Short-Tem Foreign Assets as Reported by Banks and Baitkere In the United States for May 1040 - (Cont | 3 | 3 | 08, 12: 1940; 09: 1941 |
| 224 | Social Security Program - (Continued) | 3 | 3 | 04, 09–10: 1942 |
| 225 | Trade-Weighted Index of Foreign Currency Value of the Dollar | 3 | 3 | 06: 1992–1994 |
| 226 | Treasury Bill Offerings since December 1, 1940 | 3 | 3 | 04, 10: 1941; 01: 1942 |
| 227 | U.S. Reserve Assets | 3 | 3 | 06: 1992–1994 |
| 228 | TECHNICAL PAPERS | 2 | 8 | 06: 1993–1994 |
| 229 | Treasury Survey of Ownership of Securities | 2 | 7 | 05–06: 1941 |
| 230 | TREASURY ISSUES INDEX | 2 | 6 | 06: 1990–1991 |
| 231 | FINANCIAL OPERATIONS OF GOVERNMENT AGENCIES AND FUNDS | 2 | 4 | 06: 1982–1983 |
| 232 | SUMMARY OF ACCOUNTS AND LOANS RECEIVABLE DUE FROM THE PUBLIC, AS OF SEPT. 30, 1983 AND 1982 | 2 | 4 | 06: 1984–1985 |
| 233 | ,--Highway Trust Fund | 2 | 2 | 06: 1983, 1993 |
| 234 | Abstracts of Recent Taxation Studies | 2 | 2 | 06: 1990–1991 |
| 235 | ACCOUNTS AND LOANS RECEIVABLE DUE FROM THE PUBLIC | 2 | 2 | 06: 1984–1985 |
| 236 | Accounts Receivable as of Sept. 30, 1983 | 2 | 2 | 06: 1984–1985 |
| 237 | ADDITIONAL TREASURY RELEASES ON FEDERAL FINANCES | 2 | 2 | 06: 1987–1988 |
| 238 | Airport and Airway Trust Fund | 2 | 2 | 06: 1983, 1993 |
| 239 | Allotments by Investor Classes on Subscriptions for Public MarkeUble Securities Part A | 2 | 2 | 06: 1982, 1987 |
| 240 | Amount OutstaiKllng, Computed Aimual Interest Charge, and Computed Rate of Interest on the Interest | 2 | 2 | 08, 10: 1940 |
| 241 | Country | 2 | 2 | 06: 1990–1991 |
| 242 | Direct and Guaranteed Loans, Dec. 31, 1990 | 2 | 2 | 06: 1991–1992 |
| 243 | DOLLARS | 2 | 2 | 11: 1941; 01: 1942 |
| 244 | EIements of Changes in Federal Reserve | 2 | 2 | 06: 1993–1994 |
| 245 | Estimated Amount of Securities Outstanding, Interest on Which Is Wholly | 2 | 2 | 12: 1939–1940 |
| 246 | Imports of Wheat and Wheat Flour | 2 | 2 | 02–03: 1942 |
| 247 | Income and Expense of Foreign and Domestic Offices and Subsidiaries of National Banks, Calendar Year | 2 | 2 | 06: 1985–1986 |
| 248 | INTRODUCTION: Capital Movements | 2 | 2 | 06: 1992, 1994 |
| 249 | INTRODUCTION: Exchange Stabilization Fund | 2 | 2 | 06: 1992, 1994 |
| 250 | INTRODUCTION: Federal Debt | 2 | 2 | 06: 1992, 1994 |
| 251 | INTRODUCTION: Federal Fiscal Operations | 2 | 2 | 06: 1992, 1994 |
| 252 | INTRODUCTION: Federal Obligations | 2 | 2 | 06: 1992, 1994 |
| 253 | INTRODUCTION: Foreign Currency Positions | 2 | 2 | 06: 1992, 1994 |
| 254 | INTRODUCTION: International Financial Statistics | 2 | 2 | 06: 1992, 1994 |
| 255 | INTRODUCTION: Market Yields | 2 | 2 | 06: 1992, 1994 |
| 256 | INTRODUCTION: Ownership of Federal Securities | 2 | 2 | 06: 1992, 1994 |
| 257 | INTRODUCTION: Public Debt Operations | 2 | 2 | 06: 1992, 1994 |
| 258 | INTRODUCTION: Savings Bonds and Notes | 2 | 2 | 06: 1992, 1994 |
| 259 | INTRODUCTION: Source and Availability of the | 2 | 2 | 06: 1992, 1994 |
| 260 | LCOPY No. 2 | 2 | 2 | 11: 1941; 08: 1942 |
| 261 | Maturity Distribution and Average Length of IVIarl<etable Interest- Bearing Public Debt | 2 | 2 | 06: 1988–1989 |
| 262 | Office of the Secretary • Department of the Treasury • Washington, D.C | 2 | 2 | 06: 1990, 1994 |
| 263 | Operating Income and Expense, and Dividends of National Banks, Calendar Year 1982 | 2 | 2 | 06: 1983–1984 |
| 264 | Receipts and Expenditures for Trust Accounts, Increment on Gold, Etc | 2 | 2 | 02–03: 1942 |
| 265 | SEMIANNUAL CUMULATIVE INDEX | 2 | 2 | 06, 12: 1941 |
| 266 | Spring Issue © Fiscal 1985 | 2 | 2 | 06: 1985–1986 |
| 267 | SPRING ISSUED SECOND QUARTER, FISCAL 1985 | 2 | 2 | 06: 1984–1985 |
| 268 | Summary Table - Change in Foreign Balances In Brokerage Accounts as Reported by Brokers | 2 | 2 | 03: 1939–1940 |
| 269 | Summary Table - Security Transactions Between the United States and Fore | 2 | 2 | 03: 1941–1942 |
| 270 | SUPPLEMENTARY LIABILITIES AND CLAIMS DATA REPORTED BY BANKS IN THE UNITED STATES | 2 | 2 | 06: 1983–1984 |
| 271 | THIS FORM CAN BE REPRODUCED | 2 | 2 | 06: 1987–1988 |
| 272 | TotaI Claims on Foreigners by Type and Country, Dec. 31, 1992 | 2 | 2 | 06: 1993–1994 |
| 273 | TreaBury BUI Offerings since January 1, 1941 | 2 | 2 | 07: 1941; 02: 1942 |
| 274 | Treasury Bill Offerings since July 1, 1030 | 2 | 2 | 11: 1940; 01: 1941 |
| 275 | Treasury Gold Receipts | 2 | 2 | 08, 11: 1941 |
| 276 | us. CURRENCY AND COIN OUTSTANDING | 2 | 2 | 06: 1988–1989 |

## Issues by side of the split

Development: 15 issues. Held-out: 46. See `data/real/split.json`.
