# Survey of the recurring numbered tables with printed totals: Federal Reserve Bulletin, FRASER title 62

Made by `python -m archivist.ingest.survey_frb` from the title hints and OCR counts in `data/real_frb/manifest.json` (the first lines of each PDF's own OCR text, and the numbered captions and Total lines found in all of it). No model was called and no page image was looked at. 24 June issues, 4,017 pages.

## How to read it

- A *table* in one issue is a number from the statistics section (`1.26`, `3.17`): a line that begins with a number of the form `d.dd` and a caption in capitals (`1.26 COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities`). A caption repeated on later pages (`Continued`) is the same table. Its months, years and `Continued` are dropped from the title, which the hint cuts at 100 characters.
- A *Total line* is a line that begins `Total` or `Totals`, after a row number if it has one (`16 Total assets`), found after the table's caption on its page; those before a page's first caption belong to the table the page continues. They are lines, not tables: a table can print several (`Total, all foreigners`, `Total vault cash`).
- Across issues a table is its number *and* its title: the titles of one number are merged when their text without numbers and months is at least 85% alike, or one is the start of the other, so a number reused for another table is listed apart (see the section on numbers with more than one title).
- *Recurring*: found in at least 50% of the 24 issues. *Printed totals*: at least 50% of the issues the table is found in print a Total line. The rules were written before the pages were looked at and are applied unchanged to all of them.
- The OCR is imperfect, so counts are approximate: a caption misread (`1.l2`) is a table missed in that issue, a table printed below another on a page is found only if its caption is read, and a Total line is counted only if the OCR keeps `Total` at the start of the line. Whether a table's *figures* add up to its totals is not looked at here.

## Pages

| | pages |
|---|---:|
| all pages | 4,017 |
| with a numbered caption | 1,413 |
| with 20+ figure lines and no numbered caption (a table continued from an earlier page, or one that is not numbered) | 308 |

## Issues

| Issue | Side | Pages | Numbered tables | With a Total line |
|---|---|--:|--:|--:|
| 1980-06 | development | 183 | 41 | 27 |
| 1981-06 | held-out | 152 | 60 | 22 |
| 1982-06 | held-out | 148 | 76 | 36 |
| 1983-06 | held-out | 164 | 76 | 37 |
| 1984-06 | held-out | 156 | 79 | 42 |
| 1985-06 | held-out | 205 | 68 | 36 |
| 1986-06 | held-out | 165 | 73 | 36 |
| 1987-06 | held-out | 210 | 75 | 38 |
| 1988-06 | held-out | 137 | 74 | 41 |
| 1989-06 | held-out | 145 | 78 | 43 |
| 1990-06 | development | 162 | 77 | 41 |
| 1991-06 | held-out | 222 | 72 | 38 |
| 1992-06 | held-out | 141 | 71 | 33 |
| 1993-06 | held-out | 165 | 67 | 34 |
| 1994-06 | held-out | 173 | 68 | 33 |
| 1995-06 | held-out | 167 | 68 | 34 |
| 1996-06 | held-out | 219 | 67 | 34 |
| 1997-06 | held-out | 157 | 63 | 31 |
| 1998-06 | held-out | 205 | 61 | 29 |
| 1999-06 | held-out | 171 | 59 | 32 |
| 2000-06 | development | 157 | 60 | 32 |
| 2001-06 | held-out | 142 | 60 | 32 |
| 2002-06 | held-out | 134 | 60 | 28 |
| 2003-06 | held-out | 137 | 38 | 20 |

## Recurring numbered tables with printed totals (30)

| # | Table | Title | Issues (of 24) | Dev (of 3) | Held-out (of 21) | Issues with a Total line | Total lines | Pages | Appears in (months: years) |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|
| 1 | 1.10 | RESERVES, MONEY STOCK, LIQUID ASSETS, AND DEBT MEASURES | 16 | 1 | 15 | 16 | 22 | 16 | 06: 1984–1999 |
| 2 | 1.12 | RESERVES AND BORROWINGS Depository Institutions1 | 22 | 2 | 20 | 22 | 192 | 22 | 06: 1981–2002 |
| 3 | 1.17 | FEDERAL RESERVE OPEN MARKET TRANSACTIONS1 | 23 | 2 | 21 | 21 | 26 | 23 | 06: 1981–2003 |
| 4 | 1.18 | FEDERAL RESERVE BANKS Condition and Federal Reserve Note Statements1 | 24 | 3 | 21 | 24 | 171 | 24 | 06: 1980–2003 |
| 5 | 1.19 | FEDERAL RESERVE BANKS Maturity Distribution of Loan and Security Holding | 19 | 2 | 17 | 12 | 43 | 19 | 06: 1983–1986, 1988–1992, 1994–2003 |
| 6 | 1.20 | AGGREGATE RESERVES OF DEPOSITORY INSTITUTIONS AND MONETARY BASE1 | 19 | 2 | 17 | 19 | 82 | 19 | 06: 1983–1984, 1986–2002 |
| 7 | 1.23 | LOANS AND SECURITIES All Commercial Banks1 | 14 | 2 | 12 | 14 | 58 | 14 | 06: 1980–1993 |
| 8 | 1.24 | MAJOR NONDEPOSIT FUNDS OF COMMERCIAL BANKS1 | 12 | 1 | 11 | 12 | 18 | 12 | 06: 1982–1993 |
| 9 | 1.25 | ASSETS AND LIABILITIES OF COMMERCIAL BANKING INSTITUTIONS Last-Wednesday-of-Month Series | 12 | 1 | 11 | 12 | 58 | 12 | 06: 1981–1992 |
| 10 | 1.32 | COMMERCIAL PAPER AND BANKERS DOLLAR ACCEPTANCES OUTSTANDING | 20 | 2 | 18 | 20 | 57 | 20 | 06: 1982–2001 |
| 11 | 1.37 | SELECTED FINANCIAL INSTITUTIONS Selected Assets and Liabilities | 12 | 1 | 11 | 10 | 11 | 12 | 06: 1982–1993 |
| 12 | 1.41 | GROSS PUBLIC DEBT OF U.S. TREASURY Types and Ownership | 22 | 2 | 20 | 22 | 22 | 22 | 06: 1982–2003 |
| 13 | 1.50 | TOTAL NONFARM BUSINESS EXPENDITURES on New Plant and Equipment | 12 | 1 | 11 | 10 | 10 | 12 | 06: 1983–1992, 1994–1995 |
| 14 | 1.51 | DOMESTIC FINANCE COMPANIES Assets and Liabilities1 | 21 | 2 | 19 | 20 | 46 | 21 | 06: 1983–2003 |
| 15 | 1.53 | MORTGAGE MARKETS Mortgages on New Homes | 12 | 1 | 11 | 12 | 22 | 12 | 06: 1992–2003 |
| 16 | 1.57 | FUNDS RAISED IN U.S. CREDIT MARKETS1 | 21 | 2 | 19 | 21 | 118 | 31 | 06: 1983–2003 |
| 17 | 1.59 | SUMMARY OF CREDIT MARKET DEBT OUTSTANDING1 | 14 | 2 | 12 | 14 | 59 | 14 | 06: 1989–2002 |
| 18 | 2.12 | OUTPUT, CAPACITY, AND CAPACITY UTILIZATION1 | 18 | 2 | 16 | 18 | 39 | 18 | 06: 1985–1992, 1994–2003 |
| 19 | 2.13 | INDUSTRIAL PRODUCTION Indexes and Gross Value1 | 23 | 2 | 21 | 22 | 70 | 37 | 06: 1981–2003 |
| 20 | 2.14 | HOUSING AND CONSTRUCTION | 21 | 2 | 19 | 21 | 21 | 21 | 06: 1981, 1983–2002 |
| 21 | 2.17 | PERSONAL INCOME AND SAVING | 23 | 3 | 20 | 23 | 23 | 23 | 06: 1980–2002 |
| 22 | 3.12 | U.S. RESERVE ASSETS | 22 | 2 | 20 | 19 | 19 | 22 | 06: 1981–1984, 1986–2003 |
| 23 | 3.14 | FOREIGN BRANCHES OF U.S. BANKS Balance Sheet Data1 | 12 | 1 | 11 | 12 | 140 | 13 | 06: 1982–1993 |
| 24 | 3.17 | LIABILITIES TO FOREIGNERS Reported by Banks in the United States1 | 19 | 2 | 17 | 18 | 27 | 28 | 06: 1982–1984, 1986–1987, 1989–2002 |
| 25 | 3.18 | BANKS' OWN CLAIMS ON FOREIGNERS Reported by Banks in the United States1 | 21 | 2 | 19 | 19 | 19 | 21 | 06: 1982–2002 |
| 26 | 3.19 | BANKS' OWN AND DOMESTIC CUSTOMERS' CLAIMS ON FOREIGNERS Reported by Banks in the | 22 | 2 | 20 | 20 | 22 | 22 | 06: 1982–2003 |
| 27 | 3.20 | BANKS' OWN CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Banks in the United States1 | 22 | 2 | 20 | 22 | 25 | 24 | 06: 1982–2003 |
| 28 | 3.21 | CLAIMS ON FOREIGN COUNTRIES Held by U.S. Offices and Foreign Branches of U.S.-Chartered Ba… | 15 | 2 | 13 | 14 | 14 | 15 | 06: 1982–1994, 1999–2000 |
| 29 | 3.22 | LIABILITIES TO UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in | 22 | 2 | 20 | 20 | 27 | 22 | 06: 1982–2003 |
| 30 | 3.23 | CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in | 22 | 2 | 20 | 21 | 21 | 22 | 06: 1982–2003 |

## Recurring numbered tables without printed totals (32)

| # | Table | Title | Issues (of 24) | Dev (of 3) | Held-out (of 21) | Issues with a Total line | Total lines | Pages | Appears in (months: years) |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|
| 1 | 1.11 | RESERVES OF DEPOSITORY INSTITUTIONS AND RESERVE BANK CREDIT | 21 | 2 | 19 | 0 | 0 | 21 | 06: 1982–2002 |
| 2 | 1.14 | FEDERAL RESERVE BANK INTEREST RATES | 24 | 3 | 21 | 0 | 0 | 24 | 06: 1980–2003 |
| 3 | 1.15 | RESERVE REQUIREMENTS OF DEPOSITORY INSTITUTIONS1 | 21 | 2 | 19 | 0 | 0 | 21 | 06: 1983–2003 |
| 4 | 1.21 | MONEY STOCK, LIQUID ASSETS, AND DEBT MEASURES1 | 16 | 1 | 15 | 0 | 0 | 16 | 06: 1984–1999 |
| 5 | 1.33 | PRIME RATE CHARGED BY BANKS on Short-Term Business Loans | 22 | 2 | 20 | 0 | 0 | 22 | 06: 1982–2003 |
| 6 | 1.35 | INTEREST RATES Money and Capital Markets | 23 | 2 | 21 | 0 | 0 | 23 | 06: 1981–2003 |
| 7 | 1.36 | STOCK MARKET Selected Statistics | 22 | 2 | 20 | 7 | 14 | 22 | 06: 1981–2002 |
| 8 | 1.38 | FEDERAL FISCAL AND FINANCING OPERATIONS | 21 | 2 | 19 | 0 | 0 | 21 | 06: 1982–2002 |
| 9 | 1.39 | U.S. BUDGET RECEIPTS AND OUTLAYS1 | 21 | 2 | 19 | 7 | 7 | 21 | 06: 1982–2002 |
| 10 | 1.40 | FEDERAL DEBT SUBJECT TO STATUTORY LIMITATION | 22 | 2 | 20 | 0 | 0 | 22 | 06: 1982–2003 |
| 11 | 1.42 | U.S. GOVERNMENT SECURITIES DEALERS Transactions1 | 20 | 2 | 18 | 0 | 0 | 20 | 06: 1983–2002 |
| 12 | 1.43 | U.S. GOVERNMENT SECURITIES DEALERS Positions and Financing1 | 21 | 2 | 19 | 6 | 6 | 21 | 06: 1983–2003 |
| 13 | 1.44 | FEDERAL AND FEDERALLY SPONSORED CREDIT AGENCIES Debt Outstanding | 20 | 2 | 18 | 0 | 0 | 20 | 06: 1983–2002 |
| 14 | 1.45 | NEW SECURITY ISSUES Tax-Exempt State and Local Governments | 21 | 2 | 19 | 0 | 0 | 21 | 06: 1983–2003 |
| 15 | 1.46 | NEW SECURITY ISSUES U.S. Corporations | 21 | 2 | 19 | 1 | 1 | 21 | 06: 1983–2003 |
| 16 | 1.47 | OPEN-END INVESTMENT COMPANIES Net Sales and Assets1 | 20 | 2 | 18 | 0 | 0 | 20 | 06: 1983–1992, 1994–2003 |
| 17 | 1.48 | CORPORATE PROFITS AND THEIR DISTRIBUTION | 19 | 2 | 17 | 0 | 0 | 19 | 06: 1983–1992, 1994–2002 |
| 18 | 1.54 | MORTGAGE DEBT OUTSTANDING1 | 20 | 2 | 18 | 0 | 0 | 20 | 06: 1983–1984, 1986–2003 |
| 19 | 1.56 | TERMS OF CONSUMER INSTALLMENT CREDIT1 | 15 | 1 | 14 | 1 | 3 | 15 | 06: 1982–1996 |
| 20 | 2.10 | NONFINANCIAL BUSINESS ACTIVITY Selected Measures | 21 | 2 | 19 | 0 | 0 | 21 | 06: 1981–1997, 1999–2002 |
| 21 | 2.11 | LABOR FORCE, EMPLOYMENT, AND UNEMPLOYMENT | 18 | 2 | 16 | 1 | 2 | 18 | 06: 1985–2002 |
| 22 | 2.15 | CONSUMER AND PRODUCER PRICES | 23 | 3 | 20 | 1 | 2 | 23 | 06: 1980–2002 |
| 23 | 3.10 | U.S. INTERNATIONAL TRANSACTIONS Summary | 22 | 2 | 20 | 1 | 1 | 22 | 06: 1981–2002 |
| 24 | 3.11 | U.S. FOREIGN TRADE1 | 22 | 3 | 19 | 2 | 13 | 22 | 06: 1980–1984, 1986–2002 |
| 25 | 3.13 | FOREIGN OFFICIAL ASSETS HELD AT FEDERAL RESERVE BANKS1 | 21 | 2 | 19 | 0 | 0 | 21 | 06: 1982–1984, 1986–2003 |
| 26 | 3.15 | SELECTED U.S. LIABILITIES TO FOREIGN OFFICIAL INSTITUTIONS | 22 | 2 | 20 | 2 | 2 | 22 | 06: 1982–2003 |
| 27 | 3.16 | LIABILITIES TO AND CLAIMS ON FOREIGNERS Reported by Banks in the United States | 24 | 3 | 21 | 2 | 2 | 24 | 06: 1980–2003 |
| 28 | 3.24 | FOREIGN TRANSACTIONS IN SECURITIES | 21 | 2 | 19 | 0 | 0 | 21 | 06: 1982–2002 |
| 29 | 3.25 | MARKETABLE U.S. TREASURY BONDS AND NOTES Foreign Transactions | 22 | 2 | 20 | 9 | 9 | 22 | 06: 1982–2003 |
| 30 | 3.26 | DISCOUNT RATES OF FOREIGN CENTRAL BANKS | 19 | 2 | 17 | 0 | 0 | 19 | 06: 1980–1998 |
| 31 | 3.27 | FOREIGN SHORT-TERM INTEREST RATES | 19 | 2 | 17 | 0 | 0 | 19 | 06: 1980–1998 |
| 32 | 3.28 | FOREIGN EXCHANGE RATES1 | 19 | 2 | 17 | 0 | 0 | 19 | 06: 1980–1998 |

## Numbered tables found in fewer than 50% of the issues (112)

| # | Table | Title | Issues (of 24) | Dev (of 3) | Held-out (of 21) | Issues with a Total line | Total lines | Pages | Appears in (months: years) |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|
| 1 | 1.10 | MONETARY AGGREGATES AND INTEREST RATES | 4 | 1 | 3 | 4 | 10 | 4 | 06: 1980–1983 |
| 2 | 1.10 | RESERVES, MONEY STOCK, AND DEBT MEASURES | 3 | 1 | 2 | 3 | 3 | 3 | 06: 2000–2002 |
| 3 | 1.10 | RESERVES AND MONEY STOCK MEASURES | 1 | 0 | 1 | 1 | 1 | 1 | 06: 2003 |
| 4 | 1.11 | FACTORS AFFECTING MEMBER BANK RESERVES | 1 | 1 | 0 | 0 | 0 | 1 | 06: 1980 |
| 5 | 1.11 | RESERVE BALANCES OF DEPOSITORY INSTITUTIONS1 | 1 | 0 | 1 | 1 | 30 | 1 | 06: 2003 |
| 6 | 1.12 | RESERVES AND BORROWINGS Member Banks | 1 | 1 | 0 | 1 | 4 | 1 | 06: 1980 |
| 7 | 1.13 | SELECTED BORROWINGS IN IMMEDIATELY AVAILABLE FUNDS Large Banks1 | 11 | 1 | 10 | 0 | 0 | 11 | 06: 1987–1997 |
| 8 | 1.13 | FEDERAL FUNDS AND REPURCHASE AGREEMENTS Large Member Banks' | 5 | 0 | 5 | 0 | 0 | 5 | 06: 1982–1986 |
| 9 | 1.15 | DEPOSITORY INSTITUTIONS RESERVE REQUIREMENTS1 | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 10 | 1.16 | MAXIMUM INTEREST RATES PAYABLE on Time and Savings Deposits at Federally Insured Instituti… | 7 | 1 | 6 | 3 | 3 | 7 | 06: 1980–1986 |
| 11 | 1.19 | FEDERAL RESERVE BANKS | 3 | 0 | 3 | 1 | 4 | 3 | 06: 1982, 1987, 1993 |
| 12 | 1.20 | BANK DEBITS AND DEPOSIT TURNOVER | 1 | 0 | 1 | 0 | 0 | 1 | 06: 1982 |
| 13 | 1.21 | MONEY STOCK MEASURES AND COMPONENTS | 4 | 1 | 3 | 1 | 1 | 4 | 06: 1980–1983 |
| 14 | 1.21 | MONE Y STOC K AN D DEB T MEASURES 1 | 3 | 1 | 2 | 0 | 0 | 3 | 06: 2000–2002 |
| 15 | 1.21 | MONEY STOCK MEASURES1 | 1 | 0 | 1 | 0 | 0 | 1 | 06: 2003 |
| 16 | 1.22 | BAN K DEBITS AN D DEPOSIT TURNOVER | 11 | 1 | 10 | 0 | 0 | 11 | 06: 1983–1993 |
| 17 | 1.22 | DEPOSIT INTEREST RATES AND AMOUNTS OUTSTANDING Commercial and BIF-insured saving banks1 | 3 | 0 | 3 | 0 | 0 | 3 | 06: 1994–1996 |
| 18 | 1.22 | AGGREGATE RESERVES OF DEPOSITORY INSTITUTIONS AND MONETARY BASE1 | 1 | 0 | 1 | 1 | 3 | 1 | 06: 1982 |
| 19 | 1.23 | BANK DEBITS AND DEPOSIT TURNOVER1 | 3 | 0 | 3 | 0 | 0 | 3 | 06: 1994–1996 |
| 20 | 1.24 | ASSETS AND LIABILITIES OF COMMERCIAL BANKING INSTITUTIONS Last-Wednesday-of-Month Series | 1 | 1 | 0 | 1 | 2 | 1 | 06: 1980 |
| 21 | 1.25 | ASSETS AN D LIABILITIES OF COMMERCIAL BANKS1 | 1 | 0 | 1 | 1 | 9 | 2 | 06: 1993 |
| 22 | 1.25 | COMMERCIAL BANK ASSETS AND LIABILITIES Call-Date Series | 1 | 1 | 0 | 1 | 21 | 1 | 06: 1980 |
| 23 | 1.26 | COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities1 | 7 | 1 | 6 | 7 | 137 | 43 | 06: 1997–2003 |
| 24 | 1.26 | ALL LARGE WEEKLY REPORTING COMMERCIAL BANKS with Domestic Assets of 1.4 Billion or More on | 6 | 0 | 6 | 6 | 23 | 6 | 06: 1982–1987 |
| 25 | 1.26 | ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS1 | 6 | 1 | 5 | 6 | 24 | 9 | 06: 1988–1993 |
| 26 | 1.26 | ASSETS AND LIABILITIES OF COMMERCIAL BANKS1 | 3 | 0 | 3 | 3 | 22 | 6 | 06: 1994–1996 |
| 27 | 1.27 | LARGE WEEKLY REPORTING COMMERCIAL BANKS with Domestic Assets of 1 Billion or More on | 3 | 0 | 3 | 2 | 6 | 3 | 06: 1982–1984 |
| 28 | 1.27 | ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS | 3 | 0 | 3 | 3 | 7 | 6 | 06: 1994–1996 |
| 29 | 1.28 | LARGE WEEKLY REPORTING COMMERCIAL BANKS IN NEW YORK CITY Assets and Liabilities | 7 | 0 | 7 | 7 | 23 | 7 | 06: 1981–1987 |
| 30 | 1.28 | ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS | 3 | 1 | 2 | 3 | 15 | 3 | 06: 1988–1990 |
| 31 | 1.28 | LARGE WEEKLY REPORTING U.S. BRANCHES AND AGENCIES OF FOREIGN BANKS | 3 | 0 | 3 | 3 | 9 | 3 | 06: 1994–1996 |
| 32 | 1.29 | LARGE WEEKLY REPORTING COMMERCIAL BANKS Balance Sheet Memoranda | 4 | 0 | 4 | 4 | 35 | 4 | 06: 1981–1984 |
| 33 | 1.29 | LARGE WEEKLY REPORTING COMMERCIAL BANKS IN NEW YORK CITY Assets and Liabilities | 1 | 1 | 0 | 1 | 3 | 1 | 06: 1980 |
| 34 | 1.30 | LARGE WEEKLY REPORTING U.S. BRANCHES AND AGENCIES OF FOREIGN BANKS WITH ASSETS OF | 10 | 1 | 9 | 10 | 40 | 10 | 06: 1984–1993 |
| 35 | 1.30 | LARGE WEEKLY REPORTING COMMERCIAL BANKS Balance Sheet Memoranda | 1 | 1 | 0 | 1 | 11 | 1 | 06: 1980 |
| 36 | 1.30 | LARGE WEEKLY REPORTING COMMERCIAL BANKS Domestic Classified Commercial and Industrial Loan… | 2 | 0 | 2 | 1 | 1 | 2 | 06: 1982–1983 |
| 37 | 1.31 | GROSS DEMAND DEPOSITS Individuals, Partnerships, and Corporations1 | 9 | 1 | 8 | 0 | 0 | 9 | 06: 1982–1990 |
| 38 | 1.32 | COMMERCIAL PAPER OUTSTANDING | 2 | 0 | 2 | 0 | 0 | 2 | 06: 2002–2003 |
| 39 | 1.34 | TERM S O F LENDIN G A T COMMERCIA L BANK S Survey of Loans Made , 6-10 | 3 | 0 | 3 | 0 | 0 | 3 | 06: 1982–1984 |
| 40 | 1.36 | INTEREST RATES Money and Capital Markets | 1 | 1 | 0 | 1 | 2 | 1 | 06: 1980 |
| 41 | 1.37 | SAVINGS INSTITUTIONS Selected Assets and Liabilities | 1 | 0 | 1 | 1 | 2 | 1 | 06: 1981 |
| 42 | 1.38 | SAVINGS INSTITUTIONS Selected Assets and Liabilities | 1 | 1 | 0 | 1 | 1 | 1 | 06: 1980 |
| 43 | 1.39 | FEDERAL FISCAL AND FINANCING OPERATIONS | 1 | 1 | 0 | 0 | 0 | 1 | 06: 1980 |
| 44 | 1.40 | U.S. BUDGET RECEIPTS AND OUTLAYS | 1 | 1 | 0 | 1 | 1 | 1 | 06: 1980 |
| 45 | 1.42 | U.S. GOVERNMENT MARKETABLE SECURITIES Ownership, by maturity | 2 | 0 | 2 | 2 | 2 | 2 | 06: 1981–1982 |
| 46 | 1.43 | U.S. GOVERNMENT SECURITIES DEALERS Transactions | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 47 | 1.43 | U.S. GOVERNMENT MARKETABLE SECURITIES Ownership, by maturity | 1 | 1 | 0 | 1 | 1 | 1 | 06: 1980 |
| 48 | 1.44 | U.S. GOVERNMENT SECURITIES DEALERS Positions and Financing | 1 | 0 | 1 | 0 | 0 | 1 | 06: 1982 |
| 49 | 1.44 | U.S. GOVERNMENT SECURITIES DEALERS Transactions | 1 | 1 | 0 | 0 | 0 | 1 | 06: 1980 |
| 50 | 1.45 | FEDERAL AND FEDERALLY SPONSORED CREDIT AGENCIES Debt outstanding | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 51 | 1.46 | NEW SECURITY ISSUES of State and Local Governments | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 52 | 1.46 | FEDERAL AND FEDERALLY SPONSORED CREDIT AGENCIES Debt outstanding | 1 | 1 | 0 | 0 | 0 | 1 | 06: 1980 |
| 53 | 1.47 | NEW SECURITY ISSUES of Corporations | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 54 | 1.48 | OPEN-END INVESTMENT COMPANIES Net Sales and Asset Position | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 55 | 1.49 | NONFINANCIAL CORPORATIONS Assets and Liabilities | 5 | 0 | 5 | 0 | 0 | 5 | 06: 1983–1987 |
| 56 | 1.49 | CORPORATE PROFITS AND THEIR DISTRIBUTION | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 57 | 1.50 | NONFINANCIAL CORPORATIONS Current Assets and Liabilities | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 58 | 1.51 | TOTAL NONFARM BUSINESS EXPENDITURES on New Plant and Equipment | 2 | 0 | 2 | 2 | 2 | 2 | 06: 1981–1982 |
| 59 | 1.52 | DOMESTIC FINANCE COMPANIES Business Credit Outstanding and Net Change1 | 9 | 1 | 8 | 9 | 12 | 9 | 06: 1983–1984, 1986–1992 |
| 60 | 1.52 | DOMESTIC FINANCE COMPANIES Owned and Managed Receivables1 | 6 | 1 | 5 | 6 | 12 | 6 | 06: 1998–2003 |
| 61 | 1.52 | DOMESTIC FINANCE COMPANIES Consumer, Real Estate, and Business Credit1 | 4 | 0 | 4 | 4 | 10 | 4 | 06: 1994–1997 |
| 62 | 1.52 | DOMESTIC FINANCE COMPANIES Assets and Liabilities | 2 | 0 | 2 | 2 | 5 | 2 | 06: 1981–1982 |
| 63 | 1.52 | DOMESTI C FINANC E COMPANIE S Business Credit | 1 | 0 | 1 | 1 | 1 | 1 | 06: 1985 |
| 64 | 1.52 | DOMESTIC FINANCE COMPANIES1 | 1 | 0 | 1 | 1 | 2 | 1 | 06: 1993 |
| 65 | 1.53 | MORTGAGE MARKETS | 9 | 1 | 8 | 9 | 18 | 9 | 06: 1983–1991 |
| 66 | 1.53 | DOMESTIC FINANCE COMPANIES Business Credit | 2 | 0 | 2 | 1 | 1 | 2 | 06: 1981–1982 |
| 67 | 1.53 | DOMESTIC FINANCE COMPANIES Assets and Liabilities | 1 | 1 | 0 | 1 | 5 | 1 | 06: 1980 |
| 68 | 1.54 | MORTGAGE MARKETS | 2 | 0 | 2 | 1 | 2 | 2 | 06: 1981–1982 |
| 69 | 1.55 | CONSUMER INSTALLMENT CREDIT1 | 11 | 1 | 10 | 11 | 33 | 11 | 06: 1983, 1986–1991, 1993–1996 |
| 70 | 1.55 | CONSUMER CREDIT1 | 7 | 1 | 6 | 7 | 15 | 7 | 06: 1997–2003 |
| 71 | 1.55 | CONSUMER INSTALLMENT CREDIT Total Outstanding, and Net ChangeA | 3 | 0 | 3 | 3 | 7 | 3 | 06: 1984–1985, 1992 |
| 72 | 1.55 | MORTGAGE DEBT OUTSTANDING | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 73 | 1.56 | TERMS OF CONSUMER CREDIT1 | 6 | 1 | 5 | 0 | 0 | 6 | 06: 1997–2002 |
| 74 | 1.56 | CONSUMER INSTALLMENT CREDIT1 Total Outstanding, and Net Change | 1 | 0 | 1 | 0 | 0 | 1 | 06: 1981 |
| 75 | 1.57 | CONSUMER INSTALLMENT CREDIT Extensions and Liquidations | 2 | 0 | 2 | 0 | 0 | 2 | 06: 1981–1982 |
| 76 | 1.57 | CONSUMER INSTALLMENT CREDIT1 Total Outstanding, and Net Change | 1 | 1 | 0 | 1 | 2 | 1 | 06: 1980 |
| 77 | 1.58 | SUMMARY OF FINANCIAL TRANSACTIONS1 | 11 | 1 | 10 | 11 | 34 | 11 | 06: 1993–2003 |
| 78 | 1.58 | DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS | 10 | 1 | 9 | 10 | 64 | 10 | 06: 1983–1992 |
| 79 | 1.58 | FUNDS RAISED IN U.S. CREDIT MARKETS | 2 | 0 | 2 | 2 | 8 | 2 | 06: 1981–1982 |
| 80 | 1.58 | CONSUMER INSTALLMENT CREDIT Extensions and Liquidations | 1 | 1 | 0 | 1 | 5 | 1 | 06: 1980 |
| 81 | 1.59 | DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS | 2 | 0 | 2 | 2 | 14 | 2 | 06: 1981–1982 |
| 82 | 1.60 | SUMMARY OF FINANCIAL ASSETS AND LIABILITIES1 | 11 | 1 | 10 | 9 | 38 | 11 | 06: 1993–2003 |
| 83 | 1.60 | SUMMARY OF CREDIT MARKET CLAIMS, BY HOLDER | 4 | 1 | 3 | 4 | 26 | 4 | 06: 1989–1992 |
| 84 | 1.60 | DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS | 1 | 1 | 0 | 1 | 7 | 1 | 06: 1980 |
| 85 | 2.11 | OUTPUT, CAPACITY, AND CAPACITY UTILIZATION | 4 | 0 | 4 | 1 | 2 | 4 | 06: 1981–1984 |
| 86 | 2.12 | LABOR FORCE, EMPLOYMENT, AND UNEMPLOYMENT | 4 | 1 | 3 | 1 | 2 | 4 | 06: 1980–1983 |
| 87 | 2.16 | GROSS DOMESTIC PRODUCT AND INCOME | 11 | 1 | 10 | 10 | 28 | 11 | 06: 1992–2002 |
| 88 | 2.16 | GROSS NATIONAL PRODUCT AND INCOME | 11 | 1 | 10 | 9 | 18 | 11 | 06: 1981–1991 |
| 89 | 3.13 | FOREIGN BRANCHES OF U.S. BANKS Balance Sheet Data | 1 | 0 | 1 | 1 | 12 | 1 | 06: 1981 |
| 90 | 3.14 | SELECTED U.S. LIABILITIES TO FOREIGN OFFICIAL INSTITUTIONS | 1 | 0 | 1 | 0 | 0 | 1 | 06: 1981 |
| 91 | 3.15 | LIABILITIES TO AND CLAIMS ON FOREIGNERS Reported by Banks in the United States | 1 | 0 | 1 | 0 | 0 | 1 | 06: 1981 |
| 92 | 3.17 | BANKS’ OWN CLAIMS ON FOREIGNERS Reported by Banks in the United States | 2 | 1 | 1 | 1 | 1 | 2 | 06: 1980–1981 |
| 93 | 3.18 | BANKS’ OWN AND DOMESTIC CUSTOMERS’ CLAIMS ON FOREIGNERS Reported by Banks in the | 2 | 1 | 1 | 1 | 1 | 2 | 06: 1980–1981 |
| 94 | 3.19 | BANKS’ OWN CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Banks in the United States | 1 | 0 | 1 | 0 | 0 | 1 | 06: 1981 |
| 95 | 3.20 | CLAIMS ON FOREIGN COUNTRIES Held by U.S. Offices and Foreign Branches of U.S.-Chartered Ba… | 1 | 0 | 1 | 0 | 0 | 1 | 06: 1981 |
| 96 | 3.21 | CLAIMS ON FOREIGN COUNTRIES Held by U.S. and Foreign Offices of U.S. Banks' | 6 | 0 | 6 | 6 | 6 | 6 | 06: 1995–1998, 2001–2002 |
| 97 | 3.21 | MARKETABLE U.S. TREASURY BONDS AND NOTES | 2 | 1 | 1 | 0 | 0 | 2 | 06: 1980–1981 |
| 98 | 3.22 | FOREIGN OFFICIAL ASSETS HELD AT FEDERAL RESERVE BANKS | 2 | 1 | 1 | 0 | 0 | 2 | 06: 1980–1981 |
| 99 | 3.23 | FOREIGN TRANSACTIONS IN SECURITIES | 2 | 1 | 1 | 0 | 0 | 2 | 06: 1980–1981 |
| 100 | 3.24 | LIABILITIES TO UN AFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in the | 2 | 1 | 1 | 1 | 1 | 2 | 06: 1980–1981 |
| 101 | 3.25 | CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in the | 2 | 1 | 1 | 2 | 2 | 2 | 06: 1980–1981 |
| 102 | 3.28 | FOREIGN EXCHANGE RATES AND INDEXES OF THE FOREIGN EXCHANGE VALUE OF THE U.S. DOLLAR1 | 4 | 1 | 3 | 0 | 0 | 4 | 06: 2000–2003 |
| 103 | 4.10 | TIME AND SAVINGS DEPOSITS Held by Insured Commercial Banks on Recent Survey Dates | 1 | 1 | 0 | 1 | 1 | 1 | 06: 1980 |
| 104 | 4.11 | SMALL-DENOMINATION TIME AND SAVINGS DEPOSITS Held by Insured Commercial Banks on Jan. 30 | 1 | 1 | 0 | 0 | 0 | 3 | 06: 1980 |
| 105 | 4.12 | AVERAGE OF MOST COMMON INTEREST RATES PAID on Various Categories of Time and Savings Depos… | 1 | 1 | 0 | 0 | 0 | 1 | 06: 1980 |
| 106 | 4.20 | DOMESTIC AND FOREIGN OFFICES, Insured Commercial Bank Assets and Liabilities1 2 | 4 | 1 | 3 | 4 | 113 | 6 | 06: 1987–1990 |
| 107 | 4.20 | DOMESTIC AND FOREIGN OFFICES, Commercial Banks with Assets of 100 Million or over1 | 1 | 0 | 1 | 1 | 18 | 1 | 06: 1984 |
| 108 | 4.21 | DOMESTIC OFFICES, Insured Commercial Banks with Assets of 100 Million or more or with fore… | 4 | 1 | 3 | 4 | 103 | 6 | 06: 1987–1990 |
| 109 | 4.21 | DOMESTIC OFFICES, Insured Commercial Banks with Assets of 100 Million or over | 1 | 0 | 1 | 1 | 14 | 1 | 06: 1984 |
| 110 | 4.22 | DOMESTIC OFFICES, Insured Commercial Bank Assets and Liabilities1 | 5 | 1 | 4 | 5 | 139 | 7 | 06: 1984, 1987–1990 |
| 111 | 4.23 | TERMS OF LENDING AT COMMERCIAL BANKS Survey of Loans Made, 4-8, ' | 2 | 0 | 2 | 2 | 27 | 4 | 06: 1985, 1989 |
| 112 | 4.30 | ASSETS AND LIABILITIES of U.S. Branches and Agencies of Foreign Banks, 31, ' | 6 | 1 | 5 | 6 | 122 | 10 | 06: 1981, 1984, 1988–1991 |

## Numbers with more than one title (60)

A number whose captions fall into two or more families is either a table renamed, a number reused for another table, or an OCR misreading. Each family is a row above; this lists the numbers so that they are not taken for one table.

| Table | Titles |
|---|---|
| 1.10 | RESERVES, MONEY STOCK, LIQUID ASSETS, AND DEBT MEASURES (16) / MONETARY AGGREGATES AND INTEREST RATES (4) / RESERVES, MONEY STOCK, AND DEBT MEASURES (3) / RESERVES AND MONEY STOCK MEASURES (1) |
| 1.11 | RESERVES OF DEPOSITORY INSTITUTIONS AND RESERVE BANK CREDIT (21) / FACTORS AFFECTING MEMBER BANK RESERVES (1) / RESERVE BALANCES OF DEPOSITORY INSTITUTIONS1 (1) |
| 1.12 | RESERVES AND BORROWINGS Depository Institutions1 (22) / RESERVES AND BORROWINGS Member Banks (1) |
| 1.13 | SELECTED BORROWINGS IN IMMEDIATELY AVAILABLE FUNDS Large Banks1 (11) / FEDERAL FUNDS AND REPURCHASE AGREEMENTS Large Member Banks' (5) |
| 1.15 | RESERVE REQUIREMENTS OF DEPOSITORY INSTITUTIONS1 (21) / DEPOSITORY INSTITUTIONS RESERVE REQUIREMENTS1 (2) |
| 1.19 | FEDERAL RESERVE BANKS Maturity Distribution of Loan and Security Holding (19) / FEDERAL RESERVE BANKS (3) |
| 1.20 | AGGREGATE RESERVES OF DEPOSITORY INSTITUTIONS AND MONETARY BASE1 (19) / BANK DEBITS AND DEPOSIT TURNOVER (1) |
| 1.21 | MONEY STOCK, LIQUID ASSETS, AND DEBT MEASURES1 (16) / MONEY STOCK MEASURES AND COMPONENTS (4) / MONE Y STOC K AN D DEB T MEASURES 1 (3) / MONEY STOCK MEASURES1 (1) |
| 1.22 | BAN K DEBITS AN D DEPOSIT TURNOVER (11) / DEPOSIT INTEREST RATES AND AMOUNTS OUTSTANDING Commercial and BIF-insured saving banks1 (3) / AGGREGATE RESERVES OF DEPOSITORY INSTITUTIONS AND MONETARY BASE1 (1) |
| 1.23 | LOANS AND SECURITIES All Commercial Banks1 (14) / BANK DEBITS AND DEPOSIT TURNOVER1 (3) |
| 1.24 | MAJOR NONDEPOSIT FUNDS OF COMMERCIAL BANKS1 (12) / ASSETS AND LIABILITIES OF COMMERCIAL BANKING INSTITUTIONS Last-Wednesday-of-Month Series (1) |
| 1.25 | ASSETS AND LIABILITIES OF COMMERCIAL BANKING INSTITUTIONS Last-Wednesday-of-Month Series (12) / ASSETS AN D LIABILITIES OF COMMERCIAL BANKS1 (1) / COMMERCIAL BANK ASSETS AND LIABILITIES Call-Date Series (1) |
| 1.26 | COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities1 (7) / ALL LARGE WEEKLY REPORTING COMMERCIAL BANKS with Domestic Assets of 1.4 Billion or More on (6) / ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS1 (6) / ASSETS AND LIABILITIES OF COMMERCIAL BANKS1 (3) |
| 1.27 | LARGE WEEKLY REPORTING COMMERCIAL BANKS with Domestic Assets of 1 Billion or More on (3) / ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS (3) |
| 1.28 | LARGE WEEKLY REPORTING COMMERCIAL BANKS IN NEW YORK CITY Assets and Liabilities (7) / ASSETS AND LIABILITIES OF LARGE WEEKLY REPORTING COMMERCIAL BANKS (3) / LARGE WEEKLY REPORTING U.S. BRANCHES AND AGENCIES OF FOREIGN BANKS (3) |
| 1.29 | LARGE WEEKLY REPORTING COMMERCIAL BANKS Balance Sheet Memoranda (4) / LARGE WEEKLY REPORTING COMMERCIAL BANKS IN NEW YORK CITY Assets and Liabilities (1) |
| 1.30 | LARGE WEEKLY REPORTING U.S. BRANCHES AND AGENCIES OF FOREIGN BANKS WITH ASSETS OF (10) / LARGE WEEKLY REPORTING COMMERCIAL BANKS Balance Sheet Memoranda (1) / LARGE WEEKLY REPORTING COMMERCIAL BANKS Domestic Classified Commercial and Industrial Loan… (2) |
| 1.32 | COMMERCIAL PAPER AND BANKERS DOLLAR ACCEPTANCES OUTSTANDING (20) / COMMERCIAL PAPER OUTSTANDING (2) |
| 1.36 | STOCK MARKET Selected Statistics (22) / INTEREST RATES Money and Capital Markets (1) |
| 1.37 | SELECTED FINANCIAL INSTITUTIONS Selected Assets and Liabilities (12) / SAVINGS INSTITUTIONS Selected Assets and Liabilities (1) |
| 1.38 | FEDERAL FISCAL AND FINANCING OPERATIONS (21) / SAVINGS INSTITUTIONS Selected Assets and Liabilities (1) |
| 1.39 | U.S. BUDGET RECEIPTS AND OUTLAYS1 (21) / FEDERAL FISCAL AND FINANCING OPERATIONS (1) |
| 1.40 | FEDERAL DEBT SUBJECT TO STATUTORY LIMITATION (22) / U.S. BUDGET RECEIPTS AND OUTLAYS (1) |
| 1.42 | U.S. GOVERNMENT SECURITIES DEALERS Transactions1 (20) / U.S. GOVERNMENT MARKETABLE SECURITIES Ownership, by maturity (2) |
| 1.43 | U.S. GOVERNMENT SECURITIES DEALERS Positions and Financing1 (21) / U.S. GOVERNMENT SECURITIES DEALERS Transactions (2) / U.S. GOVERNMENT MARKETABLE SECURITIES Ownership, by maturity (1) |
| 1.44 | FEDERAL AND FEDERALLY SPONSORED CREDIT AGENCIES Debt Outstanding (20) / U.S. GOVERNMENT SECURITIES DEALERS Positions and Financing (1) / U.S. GOVERNMENT SECURITIES DEALERS Transactions (1) |
| 1.45 | NEW SECURITY ISSUES Tax-Exempt State and Local Governments (21) / FEDERAL AND FEDERALLY SPONSORED CREDIT AGENCIES Debt outstanding (2) |
| 1.46 | NEW SECURITY ISSUES U.S. Corporations (21) / NEW SECURITY ISSUES of State and Local Governments (2) / FEDERAL AND FEDERALLY SPONSORED CREDIT AGENCIES Debt outstanding (1) |
| 1.47 | OPEN-END INVESTMENT COMPANIES Net Sales and Assets1 (20) / NEW SECURITY ISSUES of Corporations (2) |
| 1.48 | CORPORATE PROFITS AND THEIR DISTRIBUTION (19) / OPEN-END INVESTMENT COMPANIES Net Sales and Asset Position (2) |
| 1.49 | NONFINANCIAL CORPORATIONS Assets and Liabilities (5) / CORPORATE PROFITS AND THEIR DISTRIBUTION (2) |
| 1.50 | TOTAL NONFARM BUSINESS EXPENDITURES on New Plant and Equipment (12) / NONFINANCIAL CORPORATIONS Current Assets and Liabilities (2) |
| 1.51 | DOMESTIC FINANCE COMPANIES Assets and Liabilities1 (21) / TOTAL NONFARM BUSINESS EXPENDITURES on New Plant and Equipment (2) |
| 1.52 | DOMESTIC FINANCE COMPANIES Business Credit Outstanding and Net Change1 (9) / DOMESTIC FINANCE COMPANIES Owned and Managed Receivables1 (6) / DOMESTIC FINANCE COMPANIES Consumer, Real Estate, and Business Credit1 (4) / DOMESTIC FINANCE COMPANIES Assets and Liabilities (2) / DOMESTI C FINANC E COMPANIE S Business Credit (1) / DOMESTIC FINANCE COMPANIES1 (1) |
| 1.53 | MORTGAGE MARKETS Mortgages on New Homes (12) / MORTGAGE MARKETS (9) / DOMESTIC FINANCE COMPANIES Business Credit (2) / DOMESTIC FINANCE COMPANIES Assets and Liabilities (1) |
| 1.54 | MORTGAGE DEBT OUTSTANDING1 (20) / MORTGAGE MARKETS (2) |
| 1.55 | CONSUMER INSTALLMENT CREDIT1 (11) / CONSUMER CREDIT1 (7) / CONSUMER INSTALLMENT CREDIT Total Outstanding, and Net ChangeA (3) / MORTGAGE DEBT OUTSTANDING (2) |
| 1.56 | TERMS OF CONSUMER INSTALLMENT CREDIT1 (15) / TERMS OF CONSUMER CREDIT1 (6) / CONSUMER INSTALLMENT CREDIT1 Total Outstanding, and Net Change (1) |
| 1.57 | FUNDS RAISED IN U.S. CREDIT MARKETS1 (21) / CONSUMER INSTALLMENT CREDIT Extensions and Liquidations (2) / CONSUMER INSTALLMENT CREDIT1 Total Outstanding, and Net Change (1) |
| 1.58 | SUMMARY OF FINANCIAL TRANSACTIONS1 (11) / DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS (10) / FUNDS RAISED IN U.S. CREDIT MARKETS (2) / CONSUMER INSTALLMENT CREDIT Extensions and Liquidations (1) |
| 1.59 | SUMMARY OF CREDIT MARKET DEBT OUTSTANDING1 (14) / DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS (2) |
| 1.60 | SUMMARY OF FINANCIAL ASSETS AND LIABILITIES1 (11) / SUMMARY OF CREDIT MARKET CLAIMS, BY HOLDER (4) / DIRECT AND INDIRECT SOURCES OF FUNDS TO CREDIT MARKETS (1) |
| 2.11 | LABOR FORCE, EMPLOYMENT, AND UNEMPLOYMENT (18) / OUTPUT, CAPACITY, AND CAPACITY UTILIZATION (4) |
| 2.12 | OUTPUT, CAPACITY, AND CAPACITY UTILIZATION1 (18) / LABOR FORCE, EMPLOYMENT, AND UNEMPLOYMENT (4) |
| 2.16 | GROSS DOMESTIC PRODUCT AND INCOME (11) / GROSS NATIONAL PRODUCT AND INCOME (11) |
| 3.13 | FOREIGN OFFICIAL ASSETS HELD AT FEDERAL RESERVE BANKS1 (21) / FOREIGN BRANCHES OF U.S. BANKS Balance Sheet Data (1) |
| 3.14 | FOREIGN BRANCHES OF U.S. BANKS Balance Sheet Data1 (12) / SELECTED U.S. LIABILITIES TO FOREIGN OFFICIAL INSTITUTIONS (1) |
| 3.15 | SELECTED U.S. LIABILITIES TO FOREIGN OFFICIAL INSTITUTIONS (22) / LIABILITIES TO AND CLAIMS ON FOREIGNERS Reported by Banks in the United States (1) |
| 3.17 | LIABILITIES TO FOREIGNERS Reported by Banks in the United States1 (19) / BANKS’ OWN CLAIMS ON FOREIGNERS Reported by Banks in the United States (2) |
| 3.18 | BANKS' OWN CLAIMS ON FOREIGNERS Reported by Banks in the United States1 (21) / BANKS’ OWN AND DOMESTIC CUSTOMERS’ CLAIMS ON FOREIGNERS Reported by Banks in the (2) |
| 3.19 | BANKS' OWN AND DOMESTIC CUSTOMERS' CLAIMS ON FOREIGNERS Reported by Banks in the (22) / BANKS’ OWN CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Banks in the United States (1) |
| 3.20 | BANKS' OWN CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Banks in the United States1 (22) / CLAIMS ON FOREIGN COUNTRIES Held by U.S. Offices and Foreign Branches of U.S.-Chartered Ba… (1) |
| 3.21 | CLAIMS ON FOREIGN COUNTRIES Held by U.S. Offices and Foreign Branches of U.S.-Chartered Ba… (15) / CLAIMS ON FOREIGN COUNTRIES Held by U.S. and Foreign Offices of U.S. Banks' (6) / MARKETABLE U.S. TREASURY BONDS AND NOTES (2) |
| 3.22 | LIABILITIES TO UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in (22) / FOREIGN OFFICIAL ASSETS HELD AT FEDERAL RESERVE BANKS (2) |
| 3.23 | CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in (22) / FOREIGN TRANSACTIONS IN SECURITIES (2) |
| 3.24 | FOREIGN TRANSACTIONS IN SECURITIES (21) / LIABILITIES TO UN AFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in the (2) |
| 3.25 | MARKETABLE U.S. TREASURY BONDS AND NOTES Foreign Transactions (22) / CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Nonbanking Business Enterprises in the (2) |
| 3.28 | FOREIGN EXCHANGE RATES1 (19) / FOREIGN EXCHANGE RATES AND INDEXES OF THE FOREIGN EXCHANGE VALUE OF THE U.S. DOLLAR1 (4) |
| 4.20 | DOMESTIC AND FOREIGN OFFICES, Insured Commercial Bank Assets and Liabilities1 2 (4) / DOMESTIC AND FOREIGN OFFICES, Commercial Banks with Assets of 100 Million or over1 (1) |
| 4.21 | DOMESTIC OFFICES, Insured Commercial Banks with Assets of 100 Million or more or with fore… (4) / DOMESTIC OFFICES, Insured Commercial Banks with Assets of 100 Million or over (1) |

## Issues by side of the split

| Side | Issues | Pages |
|---|--:|--:|
| development | 1980-06, 1990-06, 2000-06 | 502 |
| held-out | 1981-06, 1982-06, 1983-06, 1984-06, 1985-06, 1986-06, 1987-06, 1988-06, 1989-06, 1991-06, 1992-06, 1993-06, 1994-06, 1995-06, 1996-06, 1997-06, 1998-06, 1999-06, 2001-06, 2002-06, 2003-06 | 3,515 |

See `data/real_frb/split.json`.
