# Survey of the recurring table families: Comptroller of the Currency annual reports, FRASER title 56

Made by `python -m archivist.ingest.survey_occ` from the title hints and OCR counts in `data/real_occ/manifest.json` (the first lines of each PDF's own OCR text, and counts over all of it). No model was called and no page image was looked at. 10 volumes in 8 years, 6,830 pages.

## How to read it

- A page's *title* is its table caption (`No. 46.—NUMBER OF NATIONAL BANKS IN EACH STATE ...`, or `TABLE XXXVIII.` and the line under it), found among the first lines of the hint once the running head (`REPORT OF THE COMPTROLLER OF THE CURRENCY. 123`, matched even when the OCR misreads it) and bare page numbers are set aside; else the first heading in capitals. Table numbers are dropped, as they restart every year.
- A page marked `Continued` with no caption of its own takes the title of the last titled page before it in the same volume; a table continued over many pages is one family.
- Titles are merged into one family when their text without numbers and months is at least 85% alike, or one is the start of the other. Numbers and months are dropped so that a title carrying a date still matches across years.
- A *table page* has at least 20 OCR lines that are mostly digits; a *table family* has at least 50% table pages. Prose sections with a capitalised heading are therefore left out. Only table families found in two or more years are listed (a year's two volumes count once); page counts are over all volumes.
- **C**, a statement of condition: the title names resources, liabilities or condition, or at least 50% of the family's table pages have a line that begins `Resources` or `Liabilities`. The abstracts print resources and liabilities on facing pages, so most pages carry one heading, not both.
- **T**, printed totals: at least 50% of the family's table pages have a line that begins `Total`. *With totals*, *With Resources* and *With Liabilities* count table pages.
- The OCR is imperfect, so counts are approximate: a family can be split in two by a bad misreading, and two real tables with near-identical titles can be merged. A hint keeps the first 4 lines of 100 characters, so a long title is cut.
- Families are made from the words of a title, so a table printed under a different title in different years is two families: the 1905 `ABSTRACT OF REPORTS OF THE NATIONAL BANKING ASSOCIATIONS` and the 1925 `ABSTRACT OF CONDITION OF NATIONAL BANKS` are two families, each found in one year only, so neither is listed.
- FRASER notes that for 1923 to 1941 the *Individual Statements of Condition of National Banks* were published as a separate supplement; the volumes of 1925, 1930, 1935 and 1940 therefore hold no individual statements, only aggregates.

## Totals

| | pages |
|---|---:|
| all pages | 6,830 |
| table pages in any table family | 4,416 |
| in a table family found in 2+ years | 3,202 |
| in a table family found in one year only (366 families) | 1,290 |
| skipped: no heading in the first lines | 2,096 |

## Statements of condition (resources and liabilities), found in 2+ years (50)

| # | Title | Flags | Dev years | Held-out years | Pages | With totals | With Resources | With Liabilities | Appears in |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|
| 1 | AGGREGATE RESOURCES AND LIABILITIES OF THE NATIONAL | CT | 2 | 4 | 129 | 125 | 53 | 90 | 1905, 1910, 1915, 1920, 1925, 1930 |
| 2 | PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS | CT | 2 | 3 | 175 | 157 | 68 | 2 | 1905, 1910, 1920, 1925, 1930 |
| 3 | ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS | CT | 1 | 3 | 368 | 363 | 193 | 343 | 1915, 1925, 1930, 1935 |
| 4 | Abstract of assets and liabilities of 1,007 active loan and trust companies June 29, | CT | 1 | 3 | 13 | 11 | 3 | 4 | 1920, 1925, 1930, 1935 |
| 5 | Principal items of resources and liabilities of each savings and State bank in the Dis | CT | 1 | 3 | 8 | 5 | 3 | 5 | 1915, 1925, 1930, 1935 |
| 6 | DATES OF REPORTS OF CONDITION OF NATIONAL BANKS FROM 1869 TO 1910 | C | 0 | 4 | 5 | 0 | 0 | 0 | 1910, 1915, 1920, 1935 |
| 7 | NUMBER, CAPITAL STOCK PAI D IN, CIRCULATION OUTSTANDING, AND AGGREGATE ASSETS OF NATIONAL BA 1863, T… | C | 2 | 2 | 5 | 1 | 3 | 0 | 1905, 1910, 1925, 1930 |
| 8 | Resources and liabilities of the first Bank of the United States | CT | 1 | 3 | 5 | 5 | 5 | 5 | 1905, 1910, 1915, 1920 |
| 9 | CONDENSED REPORTS OF THE RESOURCES AND LIABILITIES OF NATIONAL BANKS AT THE CLOSE OF BUSINESS | CT | 0 | 3 | 730 | 371 | 721 | 375 | 1910, 1915, 1920 |
| 10 | ABSTRACT OF THE STATE AND CONDITION OF THE NATIONAL BANKS ON NOVEMBER 17, DECEMBER | CT | 0 | 3 | 219 | 216 | 177 | 114 | 1910, 1915, 1920 |
| 11 | ABSTRACT OF REPORTS SINCE SEPTEMBER 1, 1909 | CT | 1 | 2 | 72 | 72 | 30 | 33 | 1905, 1910, 1915 |
| 12 | Principal items of assets and liabilities of national banks, classified according to d | CT | 0 | 3 | 18 | 18 | 1 | 0 | 1930, 1935, 1940 |
| 13 | Condition of foreign branches of National City Bank and Chase National Bank, of New Yo | C | 1 | 2 | 10 | 4 | 4 | 4 | 1925, 1930, 1935 |
| 14 | Abstract of resources and liabilities of 972 stock savings banks, June 80} | CT | 1 | 2 | 8 | 8 | 4 | 2 | 1925, 1930, 1935 |
| 15 | Individual statement of assets and liabilities of the 28 building and loan association | CT | 0 | 3 | 6 | 6 | 1 | 3 | 1930, 1935, 1940 |
| 16 | Abstract of reports of condition of loan and trust companies in the District of Columbia at date of… | CT | 1 | 2 | 5 | 5 | 2 | 4 | 1925, 1930, 1935 |
| 17 | Principal items of assets and liabilities of savings and State banks in the District of Columbia on… | C | 1 | 2 | 4 | 1 | 0 | 0 | 1925, 1930, 1935 |
| 18 | AGGREGATE RESOURCES AND LIABILITIES OF LOAN AND TRUST COMPANIES FROM | CT | 1 | 2 | 3 | 3 | 3 | 3 | 1905, 1910, 1920 |
| 19 | Aggregate resources and liabilities of mutual savings banks, Junet | CT | 0 | 3 | 3 | 3 | 3 | 3 | 1910, 1920, 1930 |
| 20 | Aggregate resources and liabilities of private banks, June, 1926 | CT | 1 | 2 | 3 | 3 | 1 | 3 | 1905, 1915, 1930 |
| 21 | ASSETS AND LIABILITIES OF ALL REPORTING BANKS IN | CT | 1 | 2 | 3 | 2 | 2 | 1 | 1920, 1925, 1930 |
| 22 | HIGHEST AND LOWEST POINTS REACHED IN THE PEINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BA… | CT | 1 | 2 | 3 | 3 | 2 | 1 | 1905, 1910, 1915 |
| 23 | RESOURCES—INTEREST-EARNING | C | 1 | 2 | 3 | 0 | 2 | 3 | 1925, 1930, 1935 |
| 24 | ASSETS AND LIABILITIES OF NATIONAL BANKS ON DECEMBER 30, 1939; MARCH | CT | 0 | 2 | 66 | 65 | 0 | 47 | 1935, 1940 |
| 25 | Abstract of reports of condition of 14,598 State banks, showing their condition at the | C | 0 | 2 | 29 | 0 | 10 | 12 | 1915, 1920 |
| 26 | LIST OF BUILDING AND LOAN ASSOCIATIONS IN THE DISTRICT | CT | 0 | 2 | 27 | 27 | 0 | 22 | 1915, 1920 |
| 27 | Abstract of resources and liabilities of 8,072 national banks, June SO, 1925 | CT | 1 | 1 | 15 | 15 | 6 | 4 | 1925, 1930 |
| 28 | Abstract of assets and liabilities of 10,622 active State (commercial), savings, and p | CT | 0 | 2 | 13 | 13 | 1 | 3 | 1930, 1935 |
| 29 | Assets and liabilities of active State (commercial) banks, June 29, 1940 | CT | 0 | 2 | 13 | 13 | 0 | 2 | 1935, 1940 |
| 30 | Assets and liabilities of active mutual savings banks, Dec. 30, 1939 | CT | 0 | 2 | 9 | 9 | 0 | 0 | 1935, 1940 |
| 31 | COMPARATIVE STATEMENT OF THE RESOURCES AND LIABILITIES OF STATE BANKS FROM 1873 TO 1910, INCLUSIVE | CT | 1 | 1 | 7 | 7 | 6 | 7 | 1905, 1910 |
| 32 | NATIONAL BANKS IN THE TRUST FIELD | CT | 0 | 2 | 7 | 5 | 0 | 5 | 1935, 1940 |
| 33 | Abstract of resources and liabilities of 20,769 State (commercial), savings, private b | CT | 1 | 1 | 6 | 6 | 2 | 2 | 1925, 1930 |
| 34 | Summary of resources and liabilities, receipts and disbursements of the 24 building and loan associa… | CT | 1 | 1 | 4 | 4 | 0 | 0 | 1925, 1930 |
| 35 | Aggregate resources and liabilities of State (commercial) banks | CT | 1 | 1 | 3 | 3 | 2 | 3 | 1925, 1930 |
| 36 | NUMBER, ASSETS, AND LIABILITIES OF STATE AND SAYINGS BANKS, LOAN AND TRUST COMPANIES, AND PRIVATE BA… | CT | 1 | 1 | 3 | 3 | 0 | 3 | 1905, 1910 |
| 37 | Abstract of reports of savings and State banks in the District of Columbia at date of each report du… | CT | 1 | 1 | 2 | 1 | 0 | 1 | 1910, 1925 |
| 38 | ABSTRACT OF THE RESOURCES AND LIABILITIES OF THE NATIONAL BANKS AT CLOSE OF BUSINESS SEPTEMBER 1, 19… | CT | 0 | 2 | 2 | 2 | 2 | 2 | 1910, 1915 |
| 39 | CHANGES IN THE PRINCIPAL ITEMS OF ASSETS AND LIABILITIES OF | CT | 0 | 2 | 2 | 2 | 1 | 1 | 1915, 1920 |
| 40 | EESOUECES OF LEADING- FOBEIGUT BAffKS OF ISSUE | CT | 1 | 1 | 2 | 2 | 1 | 0 | 1925, 1930 |
| 41 | FEDERAL RESERVE BANK NOTES | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1920, 1930 |
| 42 | NATIONAL BANK LIABILITIES ON ACCOUNT OF BILLS PAYABLE | CT | 1 | 1 | 2 | 2 | 0 | 1 | 1925, 1930 |
| 43 | NUMBER OF FAILURES, CAPITAL, ASSETS, LIABILITIES, AND DIVIDENDS PAID BY | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1910, 1920 |
| 44 | NUMBER OF STATE BANKS IN THE UNITED STATES WITH | C | 1 | 1 | 2 | 0 | 2 | 0 | 1905, 1910 |
| 45 | Number, assets, and liabilities of State banks, savings banks, loan and trust companie | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1915, 1920 |
| 46 | Principal items of assets and liabilities of each savings and State bank in the Distri | CT | 0 | 2 | 2 | 2 | 1 | 2 | 1915, 1935 |
| 47 | PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OP STATE, SAYINGS, AND PRIVATE | CT | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 48 | PRINCIPAL RESOURCES AND LIABILITIES IN THE YEARS 1834 TO 1872 | C | 1 | 1 | 2 | 0 | 2 | 2 | 1905, 1910 |
| 49 | SEPTEMBER 6, 1904, ARRANGED BY STATES AND RESERVE CITIES | CT | 1 | 1 | 2 | 2 | 0 | 2 | 1905, 1910 |
| 50 | Statement showing the condition of the 14 chartered banks of | CT | 1 | 1 | 2 | 2 | 2 | 2 | 1925, 1930 |

## Tables with printed totals, found in 2+ years (133)

| # | Title | Flags | Dev years | Held-out years | Pages | With totals | With Resources | With Liabilities | Appears in |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|
| 1 | NATIONAL BANKS CHARTERED DURING THE YEAR ENDED OCTOBER 31, 1905 | T | 2 | 6 | 39 | 38 | 0 | 0 | 1905, 1910, 1915, 1920, 1925, 1930, 1935, 1940 |
| 2 | NATIONAL-BANK NOTES ISSUED, REDEEMED, AND OUTSTANDING, BY DENOMINATIONS AND AMOUNTS, ON OCTO | T | 2 | 5 | 12 | 7 | 0 | 0 | 1905, 1910, 1915, 1920, 1925, 1930, 1935 |
| 3 | United States bonds on deposit to secure circulating notes of national | T | 2 | 5 | 8 | 7 | 0 | 0 | 1905, 1910, 1915, 1920, 1925, 1930, 1935 |
| 4 | AGGREGATE RESOURCES AND LIABILITIES OF THE NATIONAL | CT | 2 | 4 | 129 | 125 | 53 | 90 | 1905, 1910, 1915, 1920, 1925, 1930 |
| 5 | National banks restored to solvency after having been placed in charge of receivers | T | 1 | 5 | 10 | 6 | 0 | 0 | 1915, 1920, 1925, 1930, 1935, 1940 |
| 6 | PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS | CT | 2 | 3 | 175 | 157 | 68 | 2 | 1905, 1910, 1920, 1925, 1930 |
| 7 | PROFIT ON NATIONAL-BANK CIRCULATION | T | 2 | 3 | 7 | 4 | 0 | 0 | 1905, 1910, 1915, 1925, 1930 |
| 8 | Number and capital of State banks converted into national banking associations in each State and Ter… | T | 1 | 4 | 5 | 5 | 0 | 0 | 1905, 1910, 1930, 1935, 1940 |
| 9 | Taxes assessed on national-bank circulation, years ended June | T | 2 | 3 | 5 | 5 | 0 | 0 | 1905, 1910, 1915, 1925, 1930 |
| 10 | ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS | CT | 1 | 3 | 368 | 363 | 193 | 343 | 1915, 1925, 1930, 1935 |
| 11 | NATIONAL BANKS WHICH HAVE BEEN PLACED IN THE HANDS OF | T | 1 | 3 | 70 | 44 | 0 | 0 | 1905, 1910, 1915, 1920 |
| 12 | Reserve computation of national banks at date of each report during | T | 1 | 3 | 28 | 24 | 0 | 0 | 1920, 1925, 1930, 1935 |
| 13 | AUTHORIZED CAPITAL STOCK OF THE NATIONAL BANKS ON THE FIRST DAY OF EACH MONTH, ETC | T | 1 | 3 | 16 | 15 | 0 | 0 | 1905, 1910, 1915, 1920 |
| 14 | Abstract of assets and liabilities of 1,007 active loan and trust companies June 29, | CT | 1 | 3 | 13 | 11 | 3 | 4 | 1920, 1925, 1930, 1935 |
| 15 | EARNINGS AND DIVIDENDS OF NATIONAL BANKS | T | 1 | 3 | 13 | 11 | 0 | 0 | 1910, 1925, 1930, 1935 |
| 16 | CENTRAL RESERVE CITIES | T | 1 | 3 | 9 | 9 | 0 | 0 | 1915, 1925, 1930, 1935 |
| 17 | Principal items of resources and liabilities of each savings and State bank in the Dis | CT | 1 | 3 | 8 | 5 | 3 | 5 | 1915, 1925, 1930, 1935 |
| 18 | Authorized capital stock of national banks on the first day of each month from January 1, 1914, to N… | T | 1 | 3 | 6 | 6 | 0 | 0 | 1920, 1925, 1930, 1935 |
| 19 | Comparative statement of the transactions of the New York Clearing House for fifty-seven years and f… | T | 2 | 2 | 6 | 4 | 1 | 1 | 1905, 1910, 1925, 1930 |
| 20 | Resources and liabilities of the first Bank of the United States | CT | 1 | 3 | 5 | 5 | 5 | 5 | 1905, 1910, 1915, 1920 |
| 21 | Total number of national banks organized, consolidated under act | T | 1 | 3 | 5 | 4 | 0 | 0 | 1925, 1930, 1935, 1940 |
| 22 | SPECIE AND BANK-NOTE CIRCULATION OF THE UNITED STATES IN THE YEARS | T | 1 | 3 | 4 | 4 | 0 | 0 | 1905, 1910, 1915, 1920 |
| 23 | CONDENSED REPORTS OF THE RESOURCES AND LIABILITIES OF NATIONAL BANKS AT THE CLOSE OF BUSINESS | CT | 0 | 3 | 730 | 371 | 721 | 375 | 1910, 1915, 1920 |
| 24 | ABSTRACT OF THE STATE AND CONDITION OF THE NATIONAL BANKS ON NOVEMBER 17, DECEMBER | CT | 0 | 3 | 219 | 216 | 177 | 114 | 1910, 1915, 1920 |
| 25 | ABSTRACT OF REPORTS SINCE SEPTEMBER 1, 1909 | CT | 1 | 2 | 72 | 72 | 30 | 33 | 1905, 1910, 1915 |
| 26 | CAPITAL, NOMINAL ASSETS AT DATE OF FAILURE, COLLECTIONS FROM ASSETS | T | 0 | 3 | 53 | 52 | 0 | 0 | 1910, 1915, 1920 |
| 27 | LAWFUL MONEY RESERVE OF THE NATIONAL BANKS AT DATE OF | T | 1 | 2 | 53 | 46 | 0 | 0 | 1905, 1910, 1915 |
| 28 | Abstract of reports of earnings and dividends of national banks, by size of banks, for by Federal Re… | T | 1 | 2 | 45 | 41 | 0 | 0 | 1905, 1910, 1935 |
| 29 | Circulation of national banks at date of each report during the year ended | T | 1 | 2 | 38 | 29 | 0 | 0 | 1915, 1920, 1925 |
| 30 | Classification of deposits of national banks, as shown by reports from Oct. SI, 1914 | T | 0 | 3 | 36 | 26 | 0 | 0 | 1910, 1915, 1920 |
| 31 | Cash in vault of national banks at date of each report during year | T | 1 | 2 | 22 | 22 | 0 | 0 | 1920, 1925, 1930 |
| 32 | Principal items of assets and liabilities of national banks, classified according to d | CT | 0 | 3 | 18 | 18 | 1 | 0 | 1930, 1935, 1940 |
| 33 | BANK FAILURES OTHER THAN NATIONAL | T | 1 | 2 | 11 | 6 | 3 | 2 | 1920, 1925, 1930 |
| 34 | Abstract of resources and liabilities of 972 stock savings banks, June 80} | CT | 1 | 2 | 8 | 8 | 4 | 2 | 1925, 1930, 1935 |
| 35 | Individual statement of assets and liabilities of the 28 building and loan association | CT | 0 | 3 | 6 | 6 | 1 | 3 | 1930, 1935, 1940 |
| 36 | National banks, by States and geographical divisions, organized, failed, and reported | T | 1 | 2 | 6 | 5 | 0 | 0 | 1925, 1935, 1940 |
| 37 | SCHOOL SAVINGS BANKING | T | 1 | 2 | 6 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 38 | Abstract of reports of condition of loan and trust companies in the District of Columbia at date of… | CT | 1 | 2 | 5 | 5 | 2 | 4 | 1925, 1930, 1935 |
| 39 | MONEY IN THE UNITED STATES | T | 1 | 2 | 5 | 2 | 0 | 0 | 1920, 1925, 1930 |
| 40 | Comparative statement for 1915 and 1914 of the transactions of the New York Clearing House, showing… | T | 1 | 2 | 4 | 2 | 0 | 0 | 1905, 1915, 1920 |
| 41 | Dividends, 41 in number, paid to the creditors of 29 insolvent national banks during the past year,… | T | 1 | 2 | 4 | 4 | 0 | 0 | 1905, 1915, 1920 |
| 42 | AGGREGATE RESOURCES AND LIABILITIES OF LOAN AND TRUST COMPANIES FROM | CT | 1 | 2 | 3 | 3 | 3 | 3 | 1905, 1910, 1920 |
| 43 | Aggregate resources and liabilities of mutual savings banks, Junet | CT | 0 | 3 | 3 | 3 | 3 | 3 | 1910, 1920, 1930 |
| 44 | Aggregate resources and liabilities of private banks, June, 1926 | CT | 1 | 2 | 3 | 3 | 1 | 3 | 1905, 1915, 1930 |
| 45 | Amount, denomination, and cost of national-bank currency received from Bureau of Engraving and Print… | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 46 | ASSETS AND LIABILITIES OF ALL REPORTING BANKS IN | CT | 1 | 2 | 3 | 2 | 2 | 1 | 1920, 1925, 1930 |
| 47 | COIN AND PAPER CIRCULATION OF THE UNITED STATES FROM 1860 TO 1905, INCLUSIVE, WITH AMOUNT OF CIRCULA… | T | 1 | 2 | 3 | 3 | 0 | 0 | 1905, 1915, 1920 |
| 48 | Comparative statement of transactions of clearing-house associations in the 12 Federal | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 49 | HIGHEST AND LOWEST POINTS REACHED IN THE PEINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BA… | CT | 1 | 2 | 3 | 3 | 2 | 1 | 1905, 1910, 1915 |
| 50 | INSOLVENT NATIONAL BANKS | T | 1 | 2 | 3 | 2 | 0 | 0 | 1905, 1910, 1935 |
| 51 | INVESTMENTS OF NATIONAL BANKS | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 52 | National-bank currency issued to banks monthly from November | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 53 | National-bank notes issued daring each year from 1864 to 1915, sive; national-bank notes destroyed o… | T | 1 | 2 | 3 | 3 | 0 | 0 | 1905, 1910, 1915 |
| 54 | National-bank notes received at Currency Bureau and destroyed since establishment of the system | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 55 | Number and authorized capital of national banks chartered and the number and capital stock of banks… | T | 0 | 3 | 3 | 3 | 0 | 0 | 1910, 1935, 1940 |
| 56 | NUMBER AND CAPITAL OF NATIONAL BANKS IN EACH STATE REEXTENDED UNDER THE Ad1 | T | 1 | 2 | 3 | 2 | 0 | 0 | 1905, 1910, 1915 |
| 57 | Number and classification of national banks chartered monthly during the year ended October 31, 1930 | T | 0 | 3 | 3 | 3 | 1 | 0 | 1930, 1935, 1940 |
| 58 | SPECIE HELD BY THE NATIONAL BANKS IN NEW YORK CITY ON DATES INDICATED AND AVERAGES IN 1895 T | T | 1 | 2 | 3 | 3 | 0 | 0 | 1905, 1910, 1915 |
| 59 | Insolvent national banks, dates of organization, appointment of receiver, and additional assets, amo… | T | 0 | 2 | 80 | 59 | 0 | 0 | 1915, 1920 |
| 60 | ASSETS AND LIABILITIES OF NATIONAL BANKS ON DECEMBER 30, 1939; MARCH | CT | 0 | 2 | 66 | 65 | 0 | 47 | 1935, 1940 |
| 61 | INSOLVENT NATIONAL BANKS, DATES OF ORGANIZATION, APPOINTMENT OF SYSTEM, WITH AMOUNTS OF NOMINAL AND… | T | 1 | 1 | 60 | 43 | 0 | 0 | 1905, 1910 |
| 62 | NATIONAL BANKS THAT HAVE GONE INTO VOLUNTARY LIQUIDATION UNDER THE PROVISIONS OF SECTIONS 5220 AND 5… | T | 1 | 1 | 47 | 46 | 0 | 0 | 1905, 1910 |
| 63 | SPECIE AND CIRCULATION OF NATIONAL BANKS AT DATE OF | T | 1 | 1 | 38 | 35 | 0 | 0 | 1905, 1910 |
| 64 | LIST OF BUILDING AND LOAN ASSOCIATIONS IN THE DISTRICT | CT | 0 | 2 | 27 | 27 | 0 | 22 | 1915, 1920 |
| 65 | Abstract of reports of earnings and dividends of national banks for the period of 6 mo | T | 0 | 2 | 24 | 24 | 0 | 0 | 1930, 1935 |
| 66 | Abstract of resources and liabilities of 8,072 national banks, June SO, 1925 | CT | 1 | 1 | 15 | 15 | 6 | 4 | 1925, 1930 |
| 67 | National banks for which increase of capital has been authorized, under act Mar. 9, 1933, as amended… | T | 0 | 2 | 14 | 12 | 0 | 0 | 1935, 1940 |
| 68 | Abstract of assets and liabilities of 10,622 active State (commercial), savings, and p | CT | 0 | 2 | 13 | 13 | 1 | 3 | 1930, 1935 |
| 69 | Assets and liabilities of active State (commercial) banks, June 29, 1940 | CT | 0 | 2 | 13 | 13 | 0 | 2 | 1935, 1940 |
| 70 | National banks in charge of receivers during year ended October 81,1930, capital at da causes of fai… | T | 1 | 1 | 13 | 13 | 0 | 0 | 1925, 1930 |
| 71 | Dividends paid to creditors of insolvent national banks during the | T | 1 | 1 | 10 | 10 | 0 | 0 | 1925, 1930 |
| 72 | Assets and liabilities of active mutual savings banks, Dec. 30, 1939 | CT | 0 | 2 | 9 | 9 | 0 | 0 | 1935, 1940 |
| 73 | Loans and discounts of national banks, December 31, 1929, March 27 and September 24, | T | 0 | 2 | 8 | 8 | 0 | 0 | 1930, 1935 |
| 74 | NATIONAL BANKS IN LIQUIDATION UNDER SECTION 7, ACT JULY 12, 1882, WITH DATE OF EXPIRATION OF CHARTER… | T | 1 | 1 | 8 | 8 | 0 | 0 | 1905, 1910 |
| 75 | Classification of loans made by the national banks in the central reserve cities (New York, Chicago,… | T | 0 | 2 | 7 | 7 | 0 | 0 | 1915, 1920 |
| 76 | COMPARATIVE STATEMENT OF THE RESOURCES AND LIABILITIES OF STATE BANKS FROM 1873 TO 1910, INCLUSIVE | CT | 1 | 1 | 7 | 7 | 6 | 7 | 1905, 1910 |
| 77 | NATIONAL BANKS IN THE TRUST FIELD | CT | 0 | 2 | 7 | 5 | 0 | 5 | 1935, 1940 |
| 78 | Abstract of resources and liabilities of 20,769 State (commercial), savings, private b | CT | 1 | 1 | 6 | 6 | 2 | 2 | 1925, 1930 |
| 79 | Latvful money reserve of the national hanks | T | 1 | 1 | 6 | 6 | 0 | 0 | 1905, 1915 |
| 80 | National banks which have been placed in charge Name and location of bank | T | 0 | 2 | 6 | 5 | 0 | 0 | 1910, 1920 |
| 81 | Lawful money and classification of reserve held by national banks as shown by reports | T | 0 | 2 | 5 | 5 | 0 | 0 | 1915, 1920 |
| 82 | PER CAPITA DEMAND AND TIME AND SAVINGS DEPOSITS IN ALL | T | 0 | 2 | 5 | 5 | 0 | 0 | 1930, 1940 |
| 83 | Classification of loans and discounts by the national banks on June 23, 1915—Continued Cities, State… | T | 0 | 2 | 4 | 4 | 0 | 0 | 1910, 1915 |
| 84 | Federal reserve notes, segregated by series, printed, shipped, and canceled, issued to organization… | T | 0 | 2 | 4 | 4 | 0 | 0 | 1930, 1940 |
| 85 | MONETARY STOCK OF PRINCIPAL COUNTRIES OF THE WORLD | T | 0 | 2 | 4 | 4 | 0 | 0 | 1920, 1930 |
| 86 | No. 6g#—NATIONAL BANKS THAT HAVE GONE INTO VOLUNTARY LIQUIDATION UNDER THE | T | 1 | 1 | 4 | 4 | 0 | 0 | 1905, 1910 |
| 87 | Number, capital stock, and circulation outstanding of national banks issuing circulating notes, toge… | T | 0 | 2 | 4 | 4 | 0 | 0 | 1930, 1935 |
| 88 | Summary of resources and liabilities, receipts and disbursements of the 24 building and loan associa… | CT | 1 | 1 | 4 | 4 | 0 | 0 | 1925, 1930 |
| 89 | Aggregate resources and liabilities of State (commercial) banks | CT | 1 | 1 | 3 | 3 | 2 | 3 | 1925, 1930 |
| 90 | AT DATE OF EACH REPORT DURING YEAR ENDED AUGUST 25, 1905 | T | 1 | 1 | 3 | 3 | 0 | 0 | 1905, 1910 |
| 91 | CLASSIFICATION OF LOANS AND DISCOUNTS IN ALL BANKS | T | 0 | 2 | 3 | 3 | 0 | 0 | 1910, 1915 |
| 92 | Classification of loans, other investments, and deposits, together with the amount of | T | 0 | 2 | 3 | 3 | 1 | 1 | 1915, 1920 |
| 93 | INDIVIDUAL DEPOSITS IN ALL .REPORTING BANKS | T | 0 | 2 | 3 | 3 | 0 | 0 | 1915, 1920 |
| 94 | NATIONAL BANKS THE CORPORATE EXISTENCE OF WHICH WILL EXPIRE DURING THE YEAR ENDING OCTOBER 31 , 1906… | T | 1 | 1 | 3 | 2 | 0 | 0 | 1905, 1910 |
| 95 | NUMBER, ASSETS, AND LIABILITIES OF STATE AND SAYINGS BANKS, LOAN AND TRUST COMPANIES, AND PRIVATE BA… | CT | 1 | 1 | 3 | 3 | 0 | 3 | 1905, 1910 |
| 96 | Profit on national bank-note circulation, based upon a deposit of $100,000 United Stat Canal loan, a… | T | 0 | 2 | 3 | 3 | 0 | 0 | 1915, 1920 |
| 97 | RECEIVER, AND CLOSING, SINCE THE ORGANIZATION OF THE NATIONAL BANKING | T | 1 | 1 | 3 | 2 | 0 | 0 | 1905, 1910 |
| 98 | Abstract of reports of savings and State banks in the District of Columbia at date of each report du… | CT | 1 | 1 | 2 | 1 | 0 | 1 | 1910, 1925 |
| 99 | ABSTRACT OF THE RESOURCES AND LIABILITIES OF THE NATIONAL BANKS AT CLOSE OF BUSINESS SEPTEMBER 1, 19… | CT | 0 | 2 | 2 | 2 | 2 | 2 | 1910, 1915 |
| 100 | Amount of currency received by National Bank Redemption Agency for redemption during year ended June… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1925, 1935 |
| 101 | BANKS, LOAN AND TRUST COMPANIES, AND NATIONAL BANKS, FROM 1864 TO 1905 | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 102 | CERTIFICATES HELD BY NATIONAL BANKS AT DATE OF EACH REPORT FROM | T | 1 | 1 | 2 | 1 | 0 | 0 | 1905, 1910 |
| 103 | CHANGES IN THE PRINCIPAL ITEMS OF ASSETS AND LIABILITIES OF | CT | 0 | 2 | 2 | 2 | 1 | 1 | 1915, 1920 |
| 104 | CHANGES OF TITLE INCIDENT TO CONSOLIDATIONS OF NATIONAL | T | 1 | 1 | 2 | 1 | 0 | 0 | 1920, 1925 |
| 105 | Classification of Federal reserve currency redemptions, the amount redeemed, number of notes, cost o… | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 106 | CLASSIFICATION OF LOANS MADE BY THE NATIONAL BANKS IN THE CENTRAL RESERVE CITIES (NEW YORK, CITIES,… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 107 | CONVERSIONS OF STATE BANKS AND PRIMARY ORGANIZATIONS AS | T | 1 | 1 | 2 | 2 | 0 | 0 | 1920, 1925 |
| 108 | EESOUECES OF LEADING- FOBEIGUT BAffKS OF ISSUE | CT | 1 | 1 | 2 | 2 | 1 | 0 | 1925, 1930 |
| 109 | EXPENDITURES OF THE CURRENCY BUREAU | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1940 |
| 110 | FEDERAL RESERVE BANK NOTES | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1920, 1930 |
| 111 | Gold and silver coin, certificates, legal tenders, and other currency held by national banks at date… | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 112 | Gold, etc.f held by national banks in the central reserve city of New | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 113 | Gold, silver, etc., held by banks other than national in 1873 to 1920, inclusive.1 | T | 0 | 2 | 2 | 1 | 0 | 0 | 1915, 1920 |
| 114 | Insolvent national banks, dates of organization, appointment of receiver, nominal and additional ass… | T | 0 | 2 | 2 | 2 | 0 | 0 | 1915, 1920 |
| 115 | MUTILATED FEDERAL RESERVE BANK NOTES, BY DENOMINATIONS, RECEIVED AND DESTROYED SINCE ORGANIZATION OF | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 116 | NATIONAL BANK LIABILITIES ON ACCOUNT OF BILLS PAYABLE | CT | 1 | 1 | 2 | 2 | 0 | 1 | 1925, 1930 |
| 117 | NATIONAL BANKS THE AFFAIRS OF WHICH WERE CLOSED DURING THE YEAR ENDED OCTOBER 31, 1910, WITH DATE OF… | T | 1 | 1 | 2 | 1 | 0 | 0 | 1905, 1910 |
| 118 | National gold bank notes issued, 1870 to 1884 | T | 0 | 2 | 2 | 2 | 0 | 0 | 1915, 1920 |
| 119 | NATIONAL GOLD BANK NOTES ISSUED, REDEEMED, AND THE AMOUNT OUTSTANDING OCTOBER 31, 1910. Denomination | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 120 | National-bank notes outstanding and the amount and per cent of notes | T | 0 | 2 | 2 | 2 | 0 | 0 | 1910, 1920 |
| 121 | NATIONAL-BANK NOTES RECEIVED MONTHLY FOR REDEMPTION BY TH E COMPTROLLER OP THE CURRENCY DURING THE Y… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 122 | NUMBER OF FAILURES, CAPITAL, ASSETS, LIABILITIES, AND DIVIDENDS PAID BY | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1910, 1920 |
| 123 | Number of national banks increasing their capital stocky together with the amount of in | T | 0 | 2 | 2 | 2 | 0 | 0 | 1935, 1940 |
| 124 | NUMBER OF NATIONAL BANKS ORGANIZED, IN LIQUIDATION, AND IN OPERA TION, WITH THEIR CAPITAL, BONDS ON… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 125 | Number, assets, and liabilities of State banks, savings banks, loan and trust companie | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1915, 1920 |
| 126 | Number, capital stock, circulation outstanding, and total assets of national banks at date of each r… | T | 0 | 2 | 2 | 1 | 0 | 0 | 1915, 1935 |
| 127 | OTHER RESERVE CITIES | T | 0 | 2 | 2 | 2 | 0 | 0 | 1915, 1920 |
| 128 | Principal items of assets and liabilities of each savings and State bank in the Distri | CT | 0 | 2 | 2 | 2 | 1 | 2 | 1915, 1935 |
| 129 | PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OP STATE, SAYINGS, AND PRIVATE | CT | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 130 | SEPTEMBER 6, 1904, ARRANGED BY STATES AND RESERVE CITIES | CT | 1 | 1 | 2 | 2 | 0 | 2 | 1905, 1910 |
| 131 | Statement showing the condition of the 14 chartered banks of | CT | 1 | 1 | 2 | 2 | 2 | 2 | 1925, 1930 |
| 132 | TAXES ASSESSED ON CIRCULATION, DEPOSITS, AND CAPITAL OF NATIONAL | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 133 | YEARLY INCREASE OR DECREASE IN NATIONAL-BANK CIRCULATION FROM JANUARY 14, 1875, TO OCTOBER 31, 1904,… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |

## All recurring table families (162)

| # | Title | Flags | Dev years | Held-out years | Pages | With totals | With Resources | With Liabilities | Appears in |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|
| 1 | NATIONAL BANKS CHARTERED DURING THE YEAR ENDED OCTOBER 31, 1905 | T | 2 | 6 | 39 | 38 | 0 | 0 | 1905, 1910, 1915, 1920, 1925, 1930, 1935, 1940 |
| 2 | Names and compensation of officers and clerks in the office of the Comptroller of the Currency, Oct.… |  | 2 | 6 | 19 | 7 | 0 | 0 | 1905, 1910, 1915, 1920, 1925, 1930, 1935, 1940 |
| 3 | NATIONAL-BANK NOTES ISSUED, REDEEMED, AND OUTSTANDING, BY DENOMINATIONS AND AMOUNTS, ON OCTO | T | 2 | 5 | 12 | 7 | 0 | 0 | 1905, 1910, 1915, 1920, 1925, 1930, 1935 |
| 4 | United States bonds on deposit to secure circulating notes of national | T | 2 | 5 | 8 | 7 | 0 | 0 | 1905, 1910, 1915, 1920, 1925, 1930, 1935 |
| 5 | AGGREGATE RESOURCES AND LIABILITIES OF THE NATIONAL | CT | 2 | 4 | 129 | 125 | 53 | 90 | 1905, 1910, 1915, 1920, 1925, 1930 |
| 6 | National banks reported in liquidation from November 1, 1929, to October 31, 1930, the names, where… |  | 1 | 5 | 22 | 5 | 0 | 0 | 1915, 1920, 1925, 1930, 1935, 1940 |
| 7 | Comparative statement of the exchanges of the clearing houses of the United States for the years end… |  | 2 | 4 | 16 | 4 | 0 | 0 | 1905, 1910, 1920, 1925, 1930, 1935 |
| 8 | National banks restored to solvency after having been placed in charge of receivers | T | 1 | 5 | 10 | 6 | 0 | 0 | 1915, 1920, 1925, 1930, 1935, 1940 |
| 9 | Comptrollers and Deputy Comptrollers of the Currency, dates of appointment and resignation, and Stat… |  | 2 | 4 | 8 | 0 | 0 | 0 | 1905, 1910, 1925, 1930, 1935, 1940 |
| 10 | PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS | CT | 2 | 3 | 175 | 157 | 68 | 2 | 1905, 1910, 1920, 1925, 1930 |
| 11 | PROFIT ON NATIONAL-BANK CIRCULATION | T | 2 | 3 | 7 | 4 | 0 | 0 | 1905, 1910, 1915, 1925, 1930 |
| 12 | Number and capital of State banks converted into national banking associations in each State and Ter… | T | 1 | 4 | 5 | 5 | 0 | 0 | 1905, 1910, 1930, 1935, 1940 |
| 13 | Taxes assessed on national-bank circulation, years ended June | T | 2 | 3 | 5 | 5 | 0 | 0 | 1905, 1910, 1915, 1925, 1930 |
| 14 | ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS | CT | 1 | 3 | 368 | 363 | 193 | 343 | 1915, 1925, 1930, 1935 |
| 15 | NATIONAL BANKS WHICH HAVE BEEN PLACED IN THE HANDS OF | T | 1 | 3 | 70 | 44 | 0 | 0 | 1905, 1910, 1915, 1920 |
| 16 | Reserve computation of national banks at date of each report during | T | 1 | 3 | 28 | 24 | 0 | 0 | 1920, 1925, 1930, 1935 |
| 17 | AUTHORIZED CAPITAL STOCK OF THE NATIONAL BANKS ON THE FIRST DAY OF EACH MONTH, ETC | T | 1 | 3 | 16 | 15 | 0 | 0 | 1905, 1910, 1915, 1920 |
| 18 | Number, capital stock paid in, circulation outstanding, and aggregate assets of national banks, etc |  | 1 | 3 | 16 | 0 | 2 | 0 | 1905, 1910, 1915, 1920 |
| 19 | UNITED STATES BONDS—MONTHLY RANGE OF PRICES IN NEW YORK FROM JANUARY, 1900, TO OCTOBER 31, 1905 |  | 2 | 2 | 16 | 0 | 0 | 0 | 1905, 1910, 1915, 1925 |
| 20 | Abstract of assets and liabilities of 1,007 active loan and trust companies June 29, | CT | 1 | 3 | 13 | 11 | 3 | 4 | 1920, 1925, 1930, 1935 |
| 21 | EARNINGS AND DIVIDENDS OF NATIONAL BANKS | T | 1 | 3 | 13 | 11 | 0 | 0 | 1910, 1925, 1930, 1935 |
| 22 | CENTRAL RESERVE CITIES | T | 1 | 3 | 9 | 9 | 0 | 0 | 1915, 1925, 1930, 1935 |
| 23 | Principal items of resources and liabilities of each savings and State bank in the Dis | CT | 1 | 3 | 8 | 5 | 3 | 5 | 1915, 1925, 1930, 1935 |
| 24 | Authorized capital stock of national banks on the first day of each month from January 1, 1914, to N… | T | 1 | 3 | 6 | 6 | 0 | 0 | 1920, 1925, 1930, 1935 |
| 25 | Comparative statement of the transactions of the New York Clearing House for fifty-seven years and f… | T | 2 | 2 | 6 | 4 | 1 | 1 | 1905, 1910, 1925, 1930 |
| 26 | Changes of corporate title of national banks, year ended October |  | 1 | 3 | 5 | 2 | 0 | 0 | 1925, 1930, 1935, 1940 |
| 27 | DATES OF REPORTS OF CONDITION OF NATIONAL BANKS FROM 1869 TO 1910 | C | 0 | 4 | 5 | 0 | 0 | 0 | 1910, 1915, 1920, 1935 |
| 28 | NUMBER, CAPITAL STOCK PAI D IN, CIRCULATION OUTSTANDING, AND AGGREGATE ASSETS OF NATIONAL BA 1863, T… | C | 2 | 2 | 5 | 1 | 3 | 0 | 1905, 1910, 1925, 1930 |
| 29 | Resources and liabilities of the first Bank of the United States | CT | 1 | 3 | 5 | 5 | 5 | 5 | 1905, 1910, 1915, 1920 |
| 30 | Total number of national banks organized, consolidated under act | T | 1 | 3 | 5 | 4 | 0 | 0 | 1925, 1930, 1935, 1940 |
| 31 | Investment value of United States bonds—Panama Canal bonds |  | 1 | 3 | 4 | 0 | 0 | 0 | 1920, 1925, 1930, 1935 |
| 32 | SPECIE AND BANK-NOTE CIRCULATION OF THE UNITED STATES IN THE YEARS | T | 1 | 3 | 4 | 4 | 0 | 0 | 1905, 1910, 1915, 1920 |
| 33 | CONDENSED REPORTS OF THE RESOURCES AND LIABILITIES OF NATIONAL BANKS AT THE CLOSE OF BUSINESS | CT | 0 | 3 | 730 | 371 | 721 | 375 | 1910, 1915, 1920 |
| 34 | ABSTRACT OF THE STATE AND CONDITION OF THE NATIONAL BANKS ON NOVEMBER 17, DECEMBER | CT | 0 | 3 | 219 | 216 | 177 | 114 | 1910, 1915, 1920 |
| 35 | ABSTRACT OF REPORTS SINCE SEPTEMBER 1, 1909 | CT | 1 | 2 | 72 | 72 | 30 | 33 | 1905, 1910, 1915 |
| 36 | CAPITAL, NOMINAL ASSETS AT DATE OF FAILURE, COLLECTIONS FROM ASSETS | T | 0 | 3 | 53 | 52 | 0 | 0 | 1910, 1915, 1920 |
| 37 | LAWFUL MONEY RESERVE OF THE NATIONAL BANKS AT DATE OF | T | 1 | 2 | 53 | 46 | 0 | 0 | 1905, 1910, 1915 |
| 38 | Abstract of reports of earnings and dividends of national banks, by size of banks, for by Federal Re… | T | 1 | 2 | 45 | 41 | 0 | 0 | 1905, 1910, 1935 |
| 39 | Circulation of national banks at date of each report during the year ended | T | 1 | 2 | 38 | 29 | 0 | 0 | 1915, 1920, 1925 |
| 40 | Classification of deposits of national banks, as shown by reports from Oct. SI, 1914 | T | 0 | 3 | 36 | 26 | 0 | 0 | 1910, 1915, 1920 |
| 41 | Cash in vault of national banks at date of each report during year | T | 1 | 2 | 22 | 22 | 0 | 0 | 1920, 1925, 1930 |
| 42 | Principal items of assets and liabilities of national banks, classified according to d | CT | 0 | 3 | 18 | 18 | 1 | 0 | 1930, 1935, 1940 |
| 43 | GOLD, SILVER, COIN CERTIFICATES, LEGAL TENDERS, AND CURRENCY |  | 1 | 2 | 17 | 7 | 0 | 0 | 1905, 1910, 1920 |
| 44 | BANK FAILURES OTHER THAN NATIONAL | T | 1 | 2 | 11 | 6 | 3 | 2 | 1920, 1925, 1930 |
| 45 | Condition of foreign branches of National City Bank and Chase National Bank, of New Yo | C | 1 | 2 | 10 | 4 | 4 | 4 | 1925, 1930, 1935 |
| 46 | ABSTRACT OF REPORTS OP EARNINGS AND DIVIDENDS |  | 1 | 2 | 9 | 2 | 0 | 0 | 1905, 1910, 1915 |
| 47 | Abstract of resources and liabilities of 972 stock savings banks, June 80} | CT | 1 | 2 | 8 | 8 | 4 | 2 | 1925, 1930, 1935 |
| 48 | Individual statement of assets and liabilities of the 28 building and loan association | CT | 0 | 3 | 6 | 6 | 1 | 3 | 1930, 1935, 1940 |
| 49 | National banks, by States and geographical divisions, organized, failed, and reported | T | 1 | 2 | 6 | 5 | 0 | 0 | 1925, 1935, 1940 |
| 50 | SCHOOL SAVINGS BANKING | T | 1 | 2 | 6 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 51 | Abstract of reports of condition of loan and trust companies in the District of Columbia at date of… | CT | 1 | 2 | 5 | 5 | 2 | 4 | 1925, 1930, 1935 |
| 52 | MONEY IN THE UNITED STATES | T | 1 | 2 | 5 | 2 | 0 | 0 | 1920, 1925, 1930 |
| 53 | Comparative statement for 1915 and 1914 of the transactions of the New York Clearing House, showing… | T | 1 | 2 | 4 | 2 | 0 | 0 | 1905, 1915, 1920 |
| 54 | Dividends, 41 in number, paid to the creditors of 29 insolvent national banks during the past year,… | T | 1 | 2 | 4 | 4 | 0 | 0 | 1905, 1915, 1920 |
| 55 | NUMBER OF NATIONAL BANKS ORGANIZED, IN VOLUNTARY LIQUIDATION, INSOLVENT, AND NUMBER AND CAPITAL OF A… |  | 1 | 2 | 4 | 1 | 0 | 0 | 1905, 1910, 1915 |
| 56 | Principal items of assets and liabilities of savings and State banks in the District of Columbia on… | C | 1 | 2 | 4 | 1 | 0 | 0 | 1925, 1930, 1935 |
| 57 | AGGREGATE RESOURCES AND LIABILITIES OF LOAN AND TRUST COMPANIES FROM | CT | 1 | 2 | 3 | 3 | 3 | 3 | 1905, 1910, 1920 |
| 58 | Aggregate resources and liabilities of mutual savings banks, Junet | CT | 0 | 3 | 3 | 3 | 3 | 3 | 1910, 1920, 1930 |
| 59 | Aggregate resources and liabilities of private banks, June, 1926 | CT | 1 | 2 | 3 | 3 | 1 | 3 | 1905, 1915, 1930 |
| 60 | Amount, denomination, and cost of national-bank currency received from Bureau of Engraving and Print… | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 61 | ASSETS AND LIABILITIES OF ALL REPORTING BANKS IN | CT | 1 | 2 | 3 | 2 | 2 | 1 | 1920, 1925, 1930 |
| 62 | COIN AND PAPER CIRCULATION OF THE UNITED STATES FROM 1860 TO 1905, INCLUSIVE, WITH AMOUNT OF CIRCULA… | T | 1 | 2 | 3 | 3 | 0 | 0 | 1905, 1915, 1920 |
| 63 | Comparative statement of transactions of clearing-house associations in the 12 Federal | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 64 | Federal reserve notes outstanding according to weekly statement |  | 1 | 2 | 3 | 0 | 0 | 0 | 1925, 1930, 1935 |
| 65 | HIGHEST AND LOWEST POINTS REACHED IN THE PEINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BA… | CT | 1 | 2 | 3 | 3 | 2 | 1 | 1905, 1910, 1915 |
| 66 | INSOLVENT NATIONAL BANKS | T | 1 | 2 | 3 | 2 | 0 | 0 | 1905, 1910, 1935 |
| 67 | INVESTMENTS OF NATIONAL BANKS | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 68 | National-bank currency issued to banks monthly from November | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 69 | National-bank notes issued daring each year from 1864 to 1915, sive; national-bank notes destroyed o… | T | 1 | 2 | 3 | 3 | 0 | 0 | 1905, 1910, 1915 |
| 70 | National-bank notes received at Currency Bureau and destroyed since establishment of the system | T | 1 | 2 | 3 | 3 | 0 | 0 | 1925, 1930, 1935 |
| 71 | Number and authorized capital of national banks chartered and the number and capital stock of banks… | T | 0 | 3 | 3 | 3 | 0 | 0 | 1910, 1935, 1940 |
| 72 | NUMBER AND CAPITAL OF NATIONAL BANKS IN EACH STATE REEXTENDED UNDER THE Ad1 | T | 1 | 2 | 3 | 2 | 0 | 0 | 1905, 1910, 1915 |
| 73 | Number and classification of national banks chartered monthly during the year ended October 31, 1930 | T | 0 | 3 | 3 | 3 | 1 | 0 | 1930, 1935, 1940 |
| 74 | NUMBER OF NATIONAL BANKS, THEIR CAPITAL, SURPLUS, DIVIDENDS, NET |  | 1 | 2 | 3 | 0 | 0 | 0 | 1905, 1910, 1915 |
| 75 | RESOURCES—INTEREST-EARNING | C | 1 | 2 | 3 | 0 | 2 | 3 | 1925, 1930, 1935 |
| 76 | SPECIE HELD BY THE NATIONAL BANKS IN NEW YORK CITY ON DATES INDICATED AND AVERAGES IN 1895 T | T | 1 | 2 | 3 | 3 | 0 | 0 | 1905, 1910, 1915 |
| 77 | Insolvent national banks, dates of organization, appointment of receiver, and additional assets, amo… | T | 0 | 2 | 80 | 59 | 0 | 0 | 1915, 1920 |
| 78 | ASSETS AND LIABILITIES OF NATIONAL BANKS ON DECEMBER 30, 1939; MARCH | CT | 0 | 2 | 66 | 65 | 0 | 47 | 1935, 1940 |
| 79 | INSOLVENT NATIONAL BANKS, DATES OF ORGANIZATION, APPOINTMENT OF SYSTEM, WITH AMOUNTS OF NOMINAL AND… | T | 1 | 1 | 60 | 43 | 0 | 0 | 1905, 1910 |
| 80 | NATIONAL BANKS THAT HAVE GONE INTO VOLUNTARY LIQUIDATION UNDER THE PROVISIONS OF SECTIONS 5220 AND 5… | T | 1 | 1 | 47 | 46 | 0 | 0 | 1905, 1910 |
| 81 | SPECIE AND CIRCULATION OF NATIONAL BANKS AT DATE OF | T | 1 | 1 | 38 | 35 | 0 | 0 | 1905, 1910 |
| 82 | National banks in charge of receivers, dates of organization, assets, amounts collected from all sou… |  | 1 | 1 | 30 | 14 | 0 | 13 | 1925, 1930 |
| 83 | Abstract of reports of condition of 14,598 State banks, showing their condition at the | C | 0 | 2 | 29 | 0 | 10 | 12 | 1915, 1920 |
| 84 | LIST OF BUILDING AND LOAN ASSOCIATIONS IN THE DISTRICT | CT | 0 | 2 | 27 | 27 | 0 | 22 | 1915, 1920 |
| 85 | Abstract of reports of earnings and dividends of national banks for the period of 6 mo | T | 0 | 2 | 24 | 24 | 0 | 0 | 1930, 1935 |
| 86 | Abstract of resources and liabilities of 8,072 national banks, June SO, 1925 | CT | 1 | 1 | 15 | 15 | 6 | 4 | 1925, 1930 |
| 87 | National banks for which increase of capital has been authorized, under act Mar. 9, 1933, as amended… | T | 0 | 2 | 14 | 12 | 0 | 0 | 1935, 1940 |
| 88 | Abstract of assets and liabilities of 10,622 active State (commercial), savings, and p | CT | 0 | 2 | 13 | 13 | 1 | 3 | 1930, 1935 |
| 89 | Assets and liabilities of active State (commercial) banks, June 29, 1940 | CT | 0 | 2 | 13 | 13 | 0 | 2 | 1935, 1940 |
| 90 | National banks in charge of receivers during year ended October 81,1930, capital at da causes of fai… | T | 1 | 1 | 13 | 13 | 0 | 0 | 1925, 1930 |
| 91 | Dividends paid to creditors of insolvent national banks during the | T | 1 | 1 | 10 | 10 | 0 | 0 | 1925, 1930 |
| 92 | Assets and liabilities of active mutual savings banks, Dec. 30, 1939 | CT | 0 | 2 | 9 | 9 | 0 | 0 | 1935, 1940 |
| 93 | Loans and discounts of national banks, December 31, 1929, March 27 and September 24, | T | 0 | 2 | 8 | 8 | 0 | 0 | 1930, 1935 |
| 94 | NATIONAL BANKS IN LIQUIDATION UNDER SECTION 7, ACT JULY 12, 1882, WITH DATE OF EXPIRATION OF CHARTER… | T | 1 | 1 | 8 | 8 | 0 | 0 | 1905, 1910 |
| 95 | Classification of loans made by the national banks in the central reserve cities (New York, Chicago,… | T | 0 | 2 | 7 | 7 | 0 | 0 | 1915, 1920 |
| 96 | COMPARATIVE STATEMENT OF THE RESOURCES AND LIABILITIES OF STATE BANKS FROM 1873 TO 1910, INCLUSIVE | CT | 1 | 1 | 7 | 7 | 6 | 7 | 1905, 1910 |
| 97 | NATIONAL BANKS IN THE TRUST FIELD | CT | 0 | 2 | 7 | 5 | 0 | 5 | 1935, 1940 |
| 98 | Abstract of resources and liabilities of 20,769 State (commercial), savings, private b | CT | 1 | 1 | 6 | 6 | 2 | 2 | 1925, 1930 |
| 99 | Latvful money reserve of the national hanks | T | 1 | 1 | 6 | 6 | 0 | 0 | 1905, 1915 |
| 100 | National banks which have been placed in charge Name and location of bank | T | 0 | 2 | 6 | 5 | 0 | 0 | 1910, 1920 |
| 101 | Lawful money and classification of reserve held by national banks as shown by reports | T | 0 | 2 | 5 | 5 | 0 | 0 | 1915, 1920 |
| 102 | PER CAPITA DEMAND AND TIME AND SAVINGS DEPOSITS IN ALL | T | 0 | 2 | 5 | 5 | 0 | 0 | 1930, 1940 |
| 103 | RATIOS TO CAPITAL, AND TO CAPITAL AND SURPLUS, OP THE EARNINGS |  | 1 | 1 | 5 | 0 | 0 | 0 | 1905, 1910 |
| 104 | Classification of loans and discounts by the national banks on June 23, 1915—Continued Cities, State… | T | 0 | 2 | 4 | 4 | 0 | 0 | 1910, 1915 |
| 105 | DEPOSITS AND RESERVE OF NATIONAL BANKS ON OR ABOUT OCTOBER 1 OF |  | 1 | 1 | 4 | 0 | 0 | 0 | 1905, 1910 |
| 106 | Federal reserve notes, segregated by series, printed, shipped, and canceled, issued to organization… | T | 0 | 2 | 4 | 4 | 0 | 0 | 1930, 1940 |
| 107 | MONETARY STOCK OF PRINCIPAL COUNTRIES OF THE WORLD | T | 0 | 2 | 4 | 4 | 0 | 0 | 1920, 1930 |
| 108 | No. 6g#—NATIONAL BANKS THAT HAVE GONE INTO VOLUNTARY LIQUIDATION UNDER THE | T | 1 | 1 | 4 | 4 | 0 | 0 | 1905, 1910 |
| 109 | Number, capital stock, and circulation outstanding of national banks issuing circulating notes, toge… | T | 0 | 2 | 4 | 4 | 0 | 0 | 1930, 1935 |
| 110 | Summary of resources and liabilities, receipts and disbursements of the 24 building and loan associa… | CT | 1 | 1 | 4 | 4 | 0 | 0 | 1925, 1930 |
| 111 | Aggregate resources and liabilities of State (commercial) banks | CT | 1 | 1 | 3 | 3 | 2 | 3 | 1925, 1930 |
| 112 | AND DIVIDENDS OF NATIONAL BANKS IN EACH STATE, RESERVE C I Y, AND TERRITO SEPTEMBER 1, 1905 |  | 1 | 1 | 3 | 0 | 0 | 0 | 1905, 1910 |
| 113 | AT DATE OF EACH REPORT DURING YEAR ENDED AUGUST 25, 1905 | T | 1 | 1 | 3 | 3 | 0 | 0 | 1905, 1910 |
| 114 | CLASSIFICATION OF LOANS AND DISCOUNTS IN ALL BANKS | T | 0 | 2 | 3 | 3 | 0 | 0 | 1910, 1915 |
| 115 | Classification of loans, other investments, and deposits, together with the amount of | T | 0 | 2 | 3 | 3 | 1 | 1 | 1915, 1920 |
| 116 | INDIVIDUAL DEPOSITS IN ALL .REPORTING BANKS | T | 0 | 2 | 3 | 3 | 0 | 0 | 1915, 1920 |
| 117 | NATIONAL BANKS THE CORPORATE EXISTENCE OF WHICH WILL EXPIRE DURING THE YEAR ENDING OCTOBER 31 , 1906… | T | 1 | 1 | 3 | 2 | 0 | 0 | 1905, 1910 |
| 118 | NUMBER, ASSETS, AND LIABILITIES OF STATE AND SAYINGS BANKS, LOAN AND TRUST COMPANIES, AND PRIVATE BA… | CT | 1 | 1 | 3 | 3 | 0 | 3 | 1905, 1910 |
| 119 | Profit on national bank-note circulation, based upon a deposit of $100,000 United Stat Canal loan, a… | T | 0 | 2 | 3 | 3 | 0 | 0 | 1915, 1920 |
| 120 | RECEIVER, AND CLOSING, SINCE THE ORGANIZATION OF THE NATIONAL BANKING | T | 1 | 1 | 3 | 2 | 0 | 0 | 1905, 1910 |
| 121 | Abstract of reports of savings and State banks in the District of Columbia at date of each report du… | CT | 1 | 1 | 2 | 1 | 0 | 1 | 1910, 1925 |
| 122 | ABSTRACT OF THE RESOURCES AND LIABILITIES OF THE NATIONAL BANKS AT CLOSE OF BUSINESS SEPTEMBER 1, 19… | CT | 0 | 2 | 2 | 2 | 2 | 2 | 1910, 1915 |
| 123 | Amount of currency received by National Bank Redemption Agency for redemption during year ended June… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1925, 1935 |
| 124 | BANKS, LOAN AND TRUST COMPANIES, AND NATIONAL BANKS, FROM 1864 TO 1905 | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 125 | CERTIFICATES HELD BY NATIONAL BANKS AT DATE OF EACH REPORT FROM | T | 1 | 1 | 2 | 1 | 0 | 0 | 1905, 1910 |
| 126 | CHANGES IN THE PRINCIPAL ITEMS OF ASSETS AND LIABILITIES OF | CT | 0 | 2 | 2 | 2 | 1 | 1 | 1915, 1920 |
| 127 | CHANGES OF TITLE INCIDENT TO CONSOLIDATIONS OF NATIONAL | T | 1 | 1 | 2 | 1 | 0 | 0 | 1920, 1925 |
| 128 | Classification of Federal reserve currency redemptions, the amount redeemed, number of notes, cost o… | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 129 | CLASSIFICATION OF LOANS MADE BY THE NATIONAL BANKS IN THE CENTRAL RESERVE CITIES (NEW YORK, CITIES,… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 130 | CONVERSIONS OF STATE BANKS AND PRIMARY ORGANIZATIONS AS | T | 1 | 1 | 2 | 2 | 0 | 0 | 1920, 1925 |
| 131 | EESOUECES OF LEADING- FOBEIGUT BAffKS OF ISSUE | CT | 1 | 1 | 2 | 2 | 1 | 0 | 1925, 1930 |
| 132 | ERS, TOGETHER WITH CAPITAL AND SURPLUS AT DATE OF ORGANIZATION AND AT |  | 1 | 1 | 2 | 0 | 0 | 0 | 1905, 1910 |
| 133 | EXPENDITURES OF THE CURRENCY BUREAU | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1940 |
| 134 | FEDERAL RESERVE BANK NOTES | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1920, 1930 |
| 135 | Gold and silver coin, certificates, legal tenders, and other currency held by national banks at date… | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 136 | Gold, etc.f held by national banks in the central reserve city of New | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 137 | Gold, silver, etc., held by banks other than national in 1873 to 1920, inclusive.1 | T | 0 | 2 | 2 | 1 | 0 | 0 | 1915, 1920 |
| 138 | Insolvent national banks, dates of organization, appointment of receiver, nominal and additional ass… | T | 0 | 2 | 2 | 2 | 0 | 0 | 1915, 1920 |
| 139 | LAWFUL MONEY RESERVE OF THE NATIONAL BANKS AS RESERVE CITIES |  | 1 | 1 | 2 | 0 | 0 | 0 | 1905, 1910 |
| 140 | MUTILATED FEDERAL RESERVE BANK NOTES, BY DENOMINATIONS, RECEIVED AND DESTROYED SINCE ORGANIZATION OF | T | 0 | 2 | 2 | 2 | 0 | 0 | 1930, 1935 |
| 141 | NATIONAL BANK LIABILITIES ON ACCOUNT OF BILLS PAYABLE | CT | 1 | 1 | 2 | 2 | 0 | 1 | 1925, 1930 |
| 142 | NATIONAL BANKS THE AFFAIRS OF WHICH WERE CLOSED DURING THE YEAR ENDED OCTOBER 31, 1910, WITH DATE OF… | T | 1 | 1 | 2 | 1 | 0 | 0 | 1905, 1910 |
| 143 | National gold bank notes issued, 1870 to 1884 | T | 0 | 2 | 2 | 2 | 0 | 0 | 1915, 1920 |
| 144 | NATIONAL GOLD BANK NOTES ISSUED, REDEEMED, AND THE AMOUNT OUTSTANDING OCTOBER 31, 1910. Denomination | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 145 | National-bank notes outstanding and the amount and per cent of notes | T | 0 | 2 | 2 | 2 | 0 | 0 | 1910, 1920 |
| 146 | NATIONAL-BANK NOTES RECEIVED MONTHLY FOR REDEMPTION BY TH E COMPTROLLER OP THE CURRENCY DURING THE Y… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 147 | NUMBER OF COLONIAL AND STATE BANKS, THEIR CAPITAL, CIRCULATION, DEPOSITS, SPECIE, AND |  | 1 | 1 | 2 | 0 | 0 | 0 | 1905, 1910 |
| 148 | NUMBER OF FAILURES, CAPITAL, ASSETS, LIABILITIES, AND DIVIDENDS PAID BY | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1910, 1920 |
| 149 | Number of national banks increasing their capital stocky together with the amount of in | T | 0 | 2 | 2 | 2 | 0 | 0 | 1935, 1940 |
| 150 | NUMBER OF NATIONAL BANKS ORGANIZED, IN LIQUIDATION, AND IN OPERA TION, WITH THEIR CAPITAL, BONDS ON… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 151 | NUMBER OF STATE BANKS IN THE UNITED STATES WITH | C | 1 | 1 | 2 | 0 | 2 | 0 | 1905, 1910 |
| 152 | Number, assets, and liabilities of State banks, savings banks, loan and trust companie | CT | 0 | 2 | 2 | 2 | 0 | 1 | 1915, 1920 |
| 153 | Number, capital stock, circulation outstanding, and total assets of national banks at date of each r… | T | 0 | 2 | 2 | 1 | 0 | 0 | 1915, 1935 |
| 154 | OF NATIONAL BANKS IN THE UNITED STATES |  | 1 | 1 | 2 | 0 | 0 | 0 | 1905, 1910 |
| 155 | OTHER RESERVE CITIES | T | 0 | 2 | 2 | 2 | 0 | 0 | 1915, 1920 |
| 156 | Principal items of assets and liabilities of each savings and State bank in the Distri | CT | 0 | 2 | 2 | 2 | 1 | 2 | 1915, 1935 |
| 157 | PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OP STATE, SAYINGS, AND PRIVATE | CT | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 158 | PRINCIPAL RESOURCES AND LIABILITIES IN THE YEARS 1834 TO 1872 | C | 1 | 1 | 2 | 0 | 2 | 2 | 1905, 1910 |
| 159 | SEPTEMBER 6, 1904, ARRANGED BY STATES AND RESERVE CITIES | CT | 1 | 1 | 2 | 2 | 0 | 2 | 1905, 1910 |
| 160 | Statement showing the condition of the 14 chartered banks of | CT | 1 | 1 | 2 | 2 | 2 | 2 | 1925, 1930 |
| 161 | TAXES ASSESSED ON CIRCULATION, DEPOSITS, AND CAPITAL OF NATIONAL | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |
| 162 | YEARLY INCREASE OR DECREASE IN NATIONAL-BANK CIRCULATION FROM JANUARY 14, 1875, TO OCTOBER 31, 1904,… | T | 1 | 1 | 2 | 2 | 0 | 0 | 1905, 1910 |

## Volumes by side of the split

| Side | Years | Volumes | Pages |
|---|---|--:|--:|
| development | 1905, 1925 | 2 | 1,415 |
| held-out | 1910, 1915, 1920, 1930, 1935, 1940 | 8 | 5,415 |

See `data/real_occ/split.json`.
