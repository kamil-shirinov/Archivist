# Modern scanned sources, 1980 to 2000: a survey (P24)

Made by `python -m archivist.ingest.survey_modern`. No model was called and no page was sent anywhere. At most two issues of each source were downloaded to a scratch directory outside the repo, read for the checks below and not kept in it. Every request carried only the project's public User-Agent. Nothing is ingested and no data file is added.

## Summary

| source | on FRASER | rights | last year still a scan | pages a year, 1980 to 2000 |
| --- | --- | --- | --- | --- |
| Federal Reserve Bulletin | yes | statement: "No Copyright - United States (NoC-US)" | 2000, the end of the range (FRASER's label: through 2005) | 2,032 on average (252 issues) |
| FDIC annual reports and Statistics on Banking | yes | none shown; federal agency | 2000, the end of the range | 129 on average (22 reports) |
| Monthly Treasury Statement | no | none shown; federal agency | 1998, the last bound volume (later monthly files are far smaller) | 383 and 384 in the 2 volumes counted, each a fiscal year |

## Recommendation

**Ingest the Federal Reserve Bulletin (Board of Governors of the Federal Reserve System), 1980 to 2000: 21 issues (June), 3,604 pages.**

- Rights: FRASER shows "No Copyright - United States (NoC-US)" for the title, the same statement as the Treasury Bulletin.
- Scan: a downloaded issue verified as a scan with an OCR layer in 2000; FRASER's label says reformatted digital on every one of its 252 issues 1980 to 2000. The ingest of data/real and data/real_occ already reads this kind of PDF.
- Tables: 32 recurring tables print a total in the issue(s) read, the kind of table the arithmetic test needs.
- Size: 3,604 pages against 6,830 in the larger source already ingested. Every issue of the range would be 42,673 pages; the choices, by issues a year:

| issues a year | which | issues | pages | within the bound |
| --- | --- | --- | --- | --- |
| 12 | every month | 252 | 42,673 | no |
| 4 | Mar, Jun, Sep, Dec | 84 | 14,212 | no |
| 2 | Jun, Dec | 42 | 7,257 | no |
| 1 | Jun | 21 | 3,604 | yes |

How the sources rank under the rule:

| source | rights | verified scan | recurring tables with a total | eligible |
| --- | --- | --- | --- | --- |
| Federal Reserve Bulletin | FRASER statement | 2000 | 32 | yes |
| FDIC annual reports and Statistics on Banking | federal agency, no statement | 2000 | 2 | only 2 recurring tables print a total |
| Monthly Treasury Statement | federal agency, no statement | 1998 | 8 | yes |

The rule: A source is eligible when (1) its rights are settled enough to start from: FRASER shows its statement, "No Copyright - United States (NoC-US)", or shows none and the publisher is an agency of the US Government (17 U.S.C. § 105, D38's basis); (2) a downloaded issue is a scan, most sampled pages an image with an OCR layer; and (3) at least three recurring tables print a total. Eligible sources are ranked by the kind of rights first (FRASER's statement before a basis) and then by how many recurring tables print a total. The years are 1980 to the last year verified as a scan; the issues are the most a year of 12, 4, 2 or 1 (all twelve months, March-June-September-December, June and December, June) that keep the pages at or under 6,830, the size of the larger source already ingested.

The rule was written after the page counts and the first table counts had been seen, so it describes the choice; it is not a test the choice passed blind. Nothing here is ingested: this is only a survey.

## Federal Reserve Bulletin

Publisher: Board of Governors of the Federal Reserve System. Served by FRASER, title 62.

### Rights

FRASER's rights statement for the title: "No Copyright - United States (NoC-US)".

The Board of Governors is an independent agency of the US Government, so the Bulletin is a work of the US Government (17 U.S.C. § 105) apart from FRASER's statement.

Borderline, for you to decide (not decided here):

- The pages were not read for material from outside the Board (a table or chart credited to another source); FRASER's statement is for the title as a whole.

### Scan or text

FRASER's own label (`digitalOrigin` in the item's metadata) is "reformatted digital" on 252 of the 252 issues from 1980 to 2000, and on the one issue a year read for 2001, 2002, 2003, 2004, 2005 (5 of 5). The title note says the paper Bulletin ended in 2006.

The check, of the kind P20 made (images with an OCR layer, or real text fonts), on pages sampled evenly through each downloaded issue: a page is a scan when images cover at least 90% of it, and its text is an OCR layer when most of its text objects are invisible (text render mode 3) or sit under the covering image. Real text would show as visible text with no covering image.

| issue | pages | MB | KB a page | pages sampled | scan with an OCR layer | scan, almost no text | real text or other | text objects sampled |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| June 2000 | 157 | 44.1 | 281 | 12 | 12 | 0 | 0 | 14,449 invisible, 0 under the image, of 14,569 |

Verified as a scan with an OCR layer, by the check on a downloaded issue: 2000, the last year of the range; FRASER's label says reformatted digital through 2005.

### Size

252 issues from 1980 to 2000, 42,673 pages in all; 69 to 285 pages per issue, median 166. Pages come from FRASER's item metadata (the extent).

| year | issues | pages | pages per issue (shortest / median / longest) |
| --- | --- | --- | --- |
| 1980 | 12 | 2,039 | 148 / 163 / 211 |
| 1981 | 12 | 1,950 | 131 / 156 / 212 |
| 1982 | 12 | 1,823 | 116 / 162 / 205 |
| 1983 | 12 | 1,966 | 142 / 164 / 203 |
| 1984 | 12 | 1,843 | 69 / 157 / 211 |
| 1985 | 12 | 2,034 | 132 / 170 / 205 |
| 1986 | 12 | 1,912 | 140 / 158 / 183 |
| 1987 | 12 | 2,031 | 140 / 166 / 210 |
| 1988 | 12 | 1,899 | 124 / 166 / 199 |
| 1989 | 12 | 1,951 | 136 / 155 / 206 |
| 1990 | 12 | 2,180 | 130 / 181 / 229 |
| 1991 | 12 | 2,116 | 146 / 171 / 222 |
| 1992 | 12 | 2,064 | 140 / 175 / 205 |
| 1993 | 12 | 2,268 | 158 / 174 / 285 |
| 1994 | 12 | 2,212 | 156 / 182 / 220 |
| 1995 | 12 | 2,219 | 150 / 187 / 238 |
| 1996 | 12 | 2,215 | 158 / 180 / 221 |
| 1997 | 12 | 2,053 | 133 / 179 / 207 |
| 1998 | 12 | 2,150 | 146 / 169 / 217 |
| 1999 | 12 | 1,863 | 135 / 154 / 172 |
| 2000 | 12 | 1,885 | 125 / 158 / 179 |

### Tables

June 2000: 60 captioned tables, 32 with a line that begins "Total" after the caption.

Tables with printed totals in June 2000. One issue was taken, so recurrence is not shown by comparing issues: the Bulletin numbers its regular tables (A-section, "1.10" to "3.xx") and lists the irregular ones separately, as special tables, in its own guide.

| table | caption | pages | total lines | a total line |
| --- | --- | --- | --- | --- |
| 1.10 | RESERVES, MONEY STOCK, AND DEBT MEASURES | 1 | 1 | 1 Total -6.6 -15.4 -7.9 4.2 7.5 9.4 47.0 |
| 1.12 | RESERVES AND BORROWINGS Depository Institutions1 | 1 | 6 | 2 Total vault cash3 44,742 44,293 60,499 |
| 1.17 | FEDERAL RESERVE OPEN MARKET TRANSACTIONS1 | 1 | 1 | 42 Total net change in System Open Marke |
| 1.18 | FEDERAL RESERVE BANKS Condition and Federal Reserve Note Sta | 1 | 7 | 10 Total U.S. Treasury securities3 501,8 |
| 1.19 | FEDERAL RESERV E BANK S Maturity Distribution of Loan and Se | 1 | 3 | 1 Total loans 117 108 108 98 1,629 124 1 |
| 1.20 | AGGREGATE RESERVES OF DEPOSITORY INSTITUTIONS AND MONETARY B | 1 | 3 | 1 Total reserves3 50.16 46.86 44.90 41.5 |
| 1.26 | COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities | 6 | 20 | 16 Total assets6 5,258.7 5,395.2 5,431.7 |
| 1.32 | COMMERCIAL PAPER AND BANKERS DOLLAR ACCEPTANCES OUTSTANDING | 1 | 1 | 1 Total amount of reporting banks' accep |
| 1.41 | GROSS PUBLIC DEBT OF U.S. TREASURY Types and Ownership | 1 | 1 | 1 Total gross public debt 5,323.2 5,502. |
| 1.43 | U.S. GOVERNMENT SECURITIES DEALERS Positions and Financing1 | 1 | 1 | 40 Total |
| 1.51 | DOMESTIC FINANCE COMPANIES Assets and Liabilities1 | 1 | 2 | 9 Total assets 910.0 979.5 l,131.9r 949. |
| 1.52 | DOMESTIC FINANCE COMPANIES Owned and Managed Receivables1 | 1 | 2 | 1 Total 810.5 875.8 993.9 972.8 980.6 98 |
| 1.53 | MORTGAGE MARKETS Mortgages on New Homes | 1 | 1 | 17 Total 164,421 255,010 324,443 315,968 |
| 1.55 | CONSUMER CREDIT1 | 1 | 2 | 1 Total |
| 1.57 | FUNDS RAISED IN U.S. CREDIT MARKETS1 | 2 | 5 | 1 Total net borrowing by domestic nonfin |
| 1.58 | SUMMARY OF FINANCIAL TRANSACTIONS1 | 1 | 3 | 1 Total net lending in credit markets 1, |
| 1.59 | SUMMARY OF CREDIT MARKET DEBT OUTSTANDING1 | 1 | 4 | 1 Total credit market debt owed by |
| 1.60 | SUMMARY OF FINANCIAL ASSETS AND LIABILITIES1 | 1 | 4 | 1 Total credit market assets 18,444.0 19 |
| 2.12 | OUTPUT, CAPACITY, AND CAPACITY UTILIZATION1 | 1 | 2 | 1 Total industry 136.1 137.7 139.5 141.7 |
| 2.13 | INDUSTRIAL PRODUCTION Indexes and Gross Value1 | 2 | 5 | 1 Total index 100.0 137.1 135.1 135.5 13 |
| 2.14 | HOUSING AND CONSTRUCTION | 1 | 1 | 21 Total put in place 617,877 664,451 70 |
| 2.16 | GROSS DOMESTIC PRODUCT AND INCOME | 1 | 3 | 1 Total 8,300.8 8,759.9 9,256.1 8,947.6  |
| 2.17 | PERSONAL INCOME AND SAVING | 1 | 1 | 1 Total personal income 6,951.1 7,358.9  |
| 3.12 | U.S. RESERVE ASSETS | 1 | 1 | 1 Total 75,090 69,954 81,755 73,414 73,2 |
| 3.17 | LIABILITIES TO FOREIGNERS Reported by Banks in the United St | 2 | 2 | 1 Total, all foreigners 1,283,027 1,347, |
| 3.18 | BANKS' OWN CLAIMS ON FOREIGNERS Reported by Banks in the Uni | 1 | 1 | 1 Total, all foreigners 708,225 734,995  |
| 3.19 | BANKS' OWN AND DOMESTIC CUSTOMERS' CLAIMS ON FOREIGNERS Repo | 1 | 1 | 1 Total 852,852 875,891 943,357 901,046r |
| 3.20 | BANKS' OWN CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Ban | 1 | 1 | 1 Total 258,106 276,550 250,418 242,348  |
| 3.21 | CLAIMS ON FOREIGN COUNTRIES | 1 | 1 | 1 Total |
| 3.22 | LIABILITIES TO UNAFFILIATED FOREIGNERS Reported by Nonbankin | 1 | 1 | 1 Total 61,782 57,382 46,570 49,279 46,5 |
| 3.23 | CLAIMS ON UNAFFILIATED FOREIGNERS Reported by Nonbanking Bus | 1 | 1 | 1 Total 65,897 68,128 77,462 67,976 77,4 |
| 3.25 | MARKETABLE U.S. TREASURY BONDS AND NOTES Foreign Transaction | 1 | 1 | 1 Total estimated 49,039 -9,953 15,106 1 |

## FDIC annual reports and Statistics on Banking

Publisher: Federal Deposit Insurance Corporation. Served by FRASER, titles 3768 (annual reports) and 125 (Statistics on Banking); the FDIC's own site, fdic.gov, also holds some annual reports.

### Rights

FRASER shows no rights statement for the title.

The FDIC is an independent agency of the US Government, so its reports are works of the US Government (17 U.S.C. § 105), the reasoning D38 records for the Comptroller.

- Statistics on Banking, FRASER title 125: FRASER shows no rights statement.
- Bank Operating Statistics, FRASER title 9318: FRASER's statement is "No Copyright - United States (NoC-US)".

Borderline, for you to decide (not decided here):

- FRASER shows no rights statement for title 3768 or title 125, so, as for the Comptroller, the ingest would need a recorded basis in place of one; whether that basis is enough here is not decided. (It does show one for another FDIC title, Bank Operating Statistics, title 9318.)
- The pages were not read for material that is not the FDIC's own (photographs, tables credited to others).

### Scan or text

FRASER's metadata labels the title "reformatted digital" and gives no label for the individual reports.

The check, of the kind P20 made (images with an OCR layer, or real text fonts), on pages sampled evenly through each downloaded issue: a page is a scan when images cover at least 90% of it, and its text is an OCR layer when most of its text objects are invisible (text render mode 3) or sit under the covering image. Real text would show as visible text with no covering image.

| issue | pages | MB | KB a page | pages sampled | scan with an OCR layer | scan, almost no text | real text or other | text objects sampled |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Annual Report, 1985 | 88 | 23.6 | 269 | 12 | 10 | 2 | 0 | 0 invisible, 701 under the image, of 821 |
| Annual Report, 2000 | 112 | 35.4 | 316 | 12 | 8 | 4 | 0 | 0 invisible, 595 under the image, of 715 |

Verified as a scan with an OCR layer, by the check on a downloaded issue: 2000, the last year of the range.

A cross-check without downloading: the FDIC's own site holds a copy of the annual report for 1982 to 1995 and reports its length to a HEAD request. The two reports downloaded, verified above as scans, run to 269 and 316 KB a page; the FDIC's copies run from 225 to 542 KB a page, the same order. The copy FRASER serves for 1985 is byte for byte the same length as the FDIC's, so it is the same file. The FDIC's site has no copy at that address for 1980, 1981, 1996, 1997, 1998, 1999, 2000.

| year | pages (FRASER) | MB (fdic.gov) | KB a page |
| --- | --- | --- | --- |
| 1982 | 56 | 21.8 | 390 |
| 1983 | 72 | 28.7 | 399 |
| 1984 | 72 | 16.8 | 233 |
| 1985 | 88 | 23.6 | 269 |
| 1986 | 78 | 18.2 | 233 |
| 1987 | 80 | 32.9 | 411 |
| 1988 | 94 | 33.6 | 357 |
| 1989 | 136 | 69.8 | 514 |
| 1990 | 100 | 24.4 | 244 |
| 1991 | 148 | 33.3 | 225 |
| 1992 | 188 | 77.2 | 411 |
| 1993 | 156 | 52.8 | 338 |
| 1994 | 140 | 40.8 | 291 |
| 1995 | 128 | 69.3 | 542 |


### Size

22 reports from 1980 to 2000, 2,710 pages in all; 56 to 320 pages per report, median 128. Pages come from FRASER's item metadata (the extent).

| year | reports | pages | pages per report (shortest / median / longest) |
| --- | --- | --- | --- |
| 1980 | 1 | 320 | 320 / 320 / 320 |
| 1981 | 2 | 236 | 96 / 140 / 140 |
| 1982 | 1 | 56 | 56 / 56 / 56 |
| 1983 | 1 | 72 | 72 / 72 / 72 |
| 1984 | 1 | 72 | 72 / 72 / 72 |
| 1985 | 1 | 88 | 88 / 88 / 88 |
| 1986 | 1 | 78 | 78 / 78 / 78 |
| 1987 | 1 | 80 | 80 / 80 / 80 |
| 1988 | 1 | 94 | 94 / 94 / 94 |
| 1989 | 1 | 136 | 136 / 136 / 136 |
| 1990 | 1 | 100 | 100 / 100 / 100 |
| 1991 | 1 | 148 | 148 / 148 / 148 |
| 1992 | 1 | 188 | 188 / 188 / 188 |
| 1993 | 1 | 156 | 156 / 156 / 156 |
| 1994 | 1 | 140 | 140 / 140 / 140 |
| 1995 | 1 | 128 | 128 / 128 / 128 |
| 1996 | 1 | 130 | 130 / 130 / 130 |
| 1997 | 1 | 128 | 128 / 128 / 128 |
| 1998 | 1 | 144 | 144 / 144 / 144 |
| 1999 | 1 | 104 | 104 / 104 / 104 |
| 2000 | 1 | 112 | 112 / 112 / 112 |

Statistics on Banking, FRASER title 125: 1 item in range (Statistics on Banking), 410 pages in all; FRASER labels it "reformatted digital". Not downloaded or checked.

Bank Operating Statistics, FRASER title 9318: 4 items in range (1980, 1981, 1982, 1983), 1,792 pages in all; FRASER labels it "reformatted digital". Not downloaded or checked.

### Tables

Annual Report, 1985: 7 captioned tables, 7 with a line that begins "Total" after the caption.
Annual Report, 2000: 4 captioned tables, 4 with a line that begins "Total" after the caption.

Tables found in both Annual Report, 1985 and Annual Report, 2000, with how many pages carry each and how many total lines each prints:

| table | caption (first) | pages | total lines | pages | total lines | a total line |
| --- | --- | --- | --- | --- | --- | --- |
| Statements of Financial Position | Statements of Financial Position | 3 | 3 | 5 | 28 | Total Assets |
| Statements of Income | Statements of Income | 2 | 8 | 4 | 6 | Total Income |

## Monthly Treasury Statement

Publisher: Bureau of the Fiscal Service, US Department of the Treasury. Served by the Fiscal Service's own site (fiscal.treasury.gov): not on FRASER.

### Rights

FRASER: not found there. The title index of FRASER was searched by letter (M, T, U, D, R) and a web search made; neither shows a Monthly Treasury Statement. The letter pages did not look complete (FRASER's "Monthly Review" is missing from the M page, for one), so this is not proof that FRASER has none. The Fiscal Service's historical page, which lists the volumes below, shows no rights statement.

The Bureau of the Fiscal Service is a bureau of the Department of the Treasury and the Statement is its own publication, a work of the US Government (17 U.S.C. § 105).

Borderline, for you to decide (not decided here):

- The page gives no rights statement. It says "Most copies are from the Treasury Library collection with help from the Copyright and Scholarly Communications department of Kent State University Libraries", so some volumes are copies from elsewhere.
- It is not on FRASER, so the FRASER gate (fraser.check_sources) and ingest cannot take it as they are; a new ingest and a recorded basis would be needed.
- The file names of volumes 14, 15, 25, 26, 27 end in -hc or -ks; the page does not say what they mean.

### Scan or text

Not a FRASER item, so there is no FRASER label; the check below is of the files.

The check, of the kind P20 made (images with an OCR layer, or real text fonts), on pages sampled evenly through each downloaded issue: a page is a scan when images cover at least 90% of it, and its text is an OCR layer when most of its text objects are invisible (text render mode 3) or sit under the covering image. Real text would show as visible text with no covering image.

| issue | pages | MB | KB a page | pages sampled | scan with an OCR layer | scan, almost no text | real text or other | text objects sampled |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Volume 18, October 1985 - September 1986 | 383 | 34.8 | 91 | 12 | 12 | 0 | 0 | 6,205 invisible, 0 under the image, of 6,205 |
| Volume 27, October 1997 - September 1998 | 384 | 19.3 | 50 | 12 | 12 | 0 | 0 | 6,460 invisible, 0 under the image, of 6,460 |

Verified as a scan with an OCR layer, by the check on a downloaded issue: 1998, the last year of this source in the range.

The monthly files the Fiscal Service lists for October 1998 to December 2000 (27 of them, sizes by HEAD, not downloaded) run from 0.1 to 0.4 MB, median 0.2 MB. A bound volume is 1.6 to 7.2 MB a month. The monthly files are an order of magnitude smaller, which fits text and not page images; that is an inference from size, not a check of the files, so the last year verified as a scan stays 1998.

### Size

Each volume is the twelve monthly statements of a fiscal year (two years in volumes 22 to 24). Pages are known only for the volumes downloaded; bytes are known for every volume.

| volume | MB | pages |  |
| --- | --- | --- | --- |
| Volume 12, October 1979 - September 1980 | 37.7 | - |  |
| Volume 13, October 1980 - September 1981 | 38.6 | - |  |
| Volume 14, October 1981 - September 1982 | 22.7 | - |  |
| Volume 15, October 1982 - September 1983 | 20.9 | - |  |
| Volume 16, October 1983 - September 1984 | 32.0 | - |  |
| Volume 17, October 1984 - September 1985 | 34.9 | - |  |
| Volume 18, October 1985 - September 1986 | 34.8 | 383 | downloaded and counted |
| Volume 19, October 1986 - September 1987 | 35.8 | - |  |
| Volume 20, October 1987 - September 1988 | 35.2 | - |  |
| Volume 21, October 1988 - September 1989 | 34.0 | - |  |
| Volume 22, October 1989 - September 1991 | 68.0 | - |  |
| Volume 23, October 1991 - September 1993 | 66.1 | - |  |
| Volume 24, October 1993 - September 1995 | 64.7 | - |  |
| Volume 25, October 1995 - September 1996 | 19.4 | - |  |
| Volume 26, October 1996 - September 1997 | 86.0 | - |  |
| Volume 27, October 1997 - September 1998 | 19.3 | 384 | downloaded and counted |

### Tables

Volume 18, October 1985 - September 1986: 9 captioned tables, 9 with a line that begins "Total" after the caption.
Volume 27, October 1997 - September 1998: 9 captioned tables, 8 with a line that begins "Total" after the caption.

Tables found in both Volume 18, October 1985 - September 1986 and Volume 27, October 1997 - September 1998, with how many pages carry each and how many total lines each prints:

| table | caption (first) | pages | total lines | pages | total lines | a total line |
| --- | --- | --- | --- | --- | --- | --- |
| Table 1 | Summary of Receipts, Outlays, and the Deficit/Surplus of the | 12 | 2 | 12 | 0 | Total 2 733,996 945,927 211,931 |
| Table 2 | Summary of Budget and Off-Budget Results and Financing of th | 12 | 61 | 12 | 67 | Total budget and off-budget results: |
| Table 3 | Summary of Receipts and Outlays of the U.S. Government, (in  | 12 | 45 | 12 | 23 | Total 57,881 57,881 52,251 779,850 |
| Table 4 | Receipts of the U.S. Government, (in millions) | 14 | 142 | 12 | 154 | Total-Individual income taxes |
| Table 5 | Outlays of the U.S. Government, and Other Per ods (in millio | 156 | 934 | 155 | 990 | Total—Legislative Branch 143 2 140 143 2 |
| Table 6 | Means of Financing the Deficit co Disposition of Surplus by  | 74 | 249 | 96 | 250 | Total public debt securities 8,746 8,746 |
| Table 7 | Receipts and Outlays of the U.S. Government by Month, Fiscal | 24 | 79 | 24 | 98 | Total-budget receipts this year |
| Table 8 | Effects of Federal Trust Fund Transactions on Budget Results | 12 | 27 | 12 | 24 | Total trust fund receipts and outlays .. |
| Table 9 | Summary of Receipts by Source, and Outlays by Function of th | 12 | 36 | 12 | 35 | Total 57,881 57,881 52,251 |

## Method and limits

- Downloads are capped at 2 issues a source, enforced in code by a ledger. Every transfer of an issue's bytes is in it, kept or not:

| source | file | MB | kept | note |
| --- | --- | --- | --- | --- |
| frb | frb_061985.pdf | - | no | a one-byte Range test: FRASER ignored the header and sent the whole file, which was discarded unread (curl to /dev/null); counted against the cap |
| frb | frb_062000.pdf | 44.1 | yes | downloaded for the survey |
| fdic | fdic_ar_1985.pdf | 23.6 | yes | downloaded for the survey |
| fdic | fdic_ar_2000.pdf | 35.4 | yes | downloaded for the survey |
| mts | vol-18-mts-oct85-sep86.pdf | 34.8 | yes | downloaded for the survey |
| mts | vol-27-mts-oct97-sep98-hc.pdf | 19.3 | yes | downloaded for the survey |

- 367 pages, metadata records and file sizes were asked for, one request each (each answer is kept in the scratch directory and never asked for twice), with a pause between requests; the issues above are the only files downloaded.
- FRASER's HEAD answers a length of 0 and it ignores a range request, so the size of one of its issues is known only once downloaded. The checks of an issue's pages therefore cover only the issues downloaded; for the other years the evidence is FRASER's label, the publisher's own copies where they exist, and file sizes. A check of one issue a year would need about 19 more downloads of each source, which the cap forbids.
- Sampled pages are spread evenly through an issue (at most 12). A table is found by its caption in the OCR text; OCR noise can split or miss one, and a line that begins "Total" may not carry its figures on the same line. Counts are a guide to which tables to look at, not a measurement of them.
