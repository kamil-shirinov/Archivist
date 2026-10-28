# Which Comptroller of the Currency tables get a drafted template

Made by `python -m archivist.templates.families_occ` before any template was drafted. No model was called and no held-out page was opened: families and their held-out counts are the survey's (`results/real_occ/survey.md`, from the manifest's title hints and OCR counts). Which survey families print one table was judged by looking at development pages only (1905 and 1925), listed below with each judgement.

## The rule

1. Kind: every member family is flagged by the survey a statement of condition (C) or a table with printed totals (T). A table is a statement of condition when a member is C.
2. One table in both development years: one survey family, or several printed under different titles in different years and judged the same table; with table pages in 1905 and in 1925 among the development pages it is judged for. A survey family that prints two different tables fails.
3. Recurs in held-out: pages in at least 2 held-out years, as the survey groups them.
4. Prints totals: in each development year a table page with a line that begins `Total`. Drafted from the first such page in each development year and, for a statement of condition where neither carries a Liabilities heading (or neither a Resources heading), from the first development page that does, so the draft sees both halves of a statement printed on facing pages.
5. Ranked by held-out page count, then name: the top 2 statements of condition, then the best of the rest, up to 4 in all.

The drafter is told only the table's printed title, as printed on its 1925 drafting page (read off the page image, since the OCR misreads some of its figures).

## How one table was told from two

Candidates are the survey families that pass rule 1 with table pages in both development years, and pairs of survey families that pass rule 1, each found in one development year only, whose titles name the same subject and whose held-out pages together could reach the last choice. Each was judged, in rank order until the choice was made, from the first table page of each member in each development year and the page facing it where the table is printed across two: one table when the stub and the measures are the same, allowing items added, dropped or renamed over twenty years. A family found only in held-out years is never merged in, since judging it would open a held-out page, so a table's held-out count is that of its development members and may be short (1910's `ABSTRACT OF REPORTS SINCE SEPTEMBER 1, 1909` reads like the abstract by States, but its one 1905 page is the District of Columbia's loan and trust companies, another table; 1935's and 1940's receivers' tables carry titles of their own). It may also be long, where a survey family holds another table too: `ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS` also holds 1925's abstract by Federal reserve district (Table 60), and the earnings family is titled after 1935's abstract by size of banks, so their held-out pages may include such tables. The abstract by States leads either way; but if the earnings family's 39 pages of 1935 are mostly another table, its count falls to 13, below National banks chartered (22), which would then be fourth. Telling which needs the held-out pages, so the survey's count stands.

| Table | Survey families (development years judged for) | Looked at | One table? | Why |
|---|---|---|---|---|
| Abstract of reports, arranged by States and reserve cities | `SUMMARY OF REPORTS OF NATIONAL BANKS SINCE SEPTEMBER 6, 1904` (1905); `SEPTEMBER 6, 1904, ARRANGED BY STATES AND RESERVE CITIES` (1905); `ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS` (1925) | 1905_p507, 1905_p508, 1925_p341 | yes | the same table retitled: 1905's Summary of reports of national banks since September 6, 1904, arranged by States and reserve cities, and 1925's Abstract of reports since October 10, 1924, arranged by States and reserve cities, each a state's resources and liabilities at each call of the year, one column per call with its number of banks, and a Total; 1905 prints resources and liabilities on facing pages and up to three states a page, 1925 both on one page, one state a page, and the items changed. The survey's ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS is taken for 1925 only: its 1905 pages are Tables I to IV, the abstracts of State, savings and private banks and of loan and trust companies, another table |
| Aggregate resources and liabilities of national banks | `AGGREGATE RESOURCES AND LIABILITIES OF THE NATIONAL` (1905, 1925); `Aggregate resources and liabilities of national banks from January, 1914, to September` (1925) | 1905_p399, 1925_p326 | yes | one survey family already, in both years: the national banks' aggregate resources (and, on the facing or the same page, liabilities) at each call, one panel a year, one column a call with its number of banks, and a Total; 1905 runs from 1863, 1925 from 1914. The 1925 title as the OCR reads it on two pages is the second member |
| Principal items of resources and liabilities of national banks | `PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS` (1905, 1925) | 1905_p570, 1925_p466 | no | two tables under one title: 1905's is each state's history, a row a year from 1863 with its number of banks, loans, bonds, cash, capital, surplus, profits, circulation, deposits and total assets; 1925's (Table 62) is each state's counties on one date, with other items. Neither is in both development years |
| Lawful money reserve / Reserve computation of national banks | `LAWFUL MONEY RESERVE OF THE NATIONAL BANKS AT DATE OF` (1905); `Reserve computation of national banks at date of each report during` (1925) | 1905_p160, 1905_p161, 1925_p318 | no | the same stub (central reserve cities, other reserve cities, states) but different measures: 1905 prints deposits and the lawful money held, amount and per cent, and on the facing page the reserve required; 1925 prints net amounts due from banks, the amount on which reserve is computed, the reserve required and that held with Federal reserve banks |
| National banks placed in the hands of (in charge of) receivers | `NATIONAL BANKS WHICH HAVE BEEN PLACED IN THE HANDS OF` (1905); `National banks in charge of receivers during year ended October 81,1930, capital at da causes of failure, dividends paid while solvent, circulation outstanding at date of failure, lawful` (1925) | 1905_p239, 1905_p240, 1925_p238 | yes | the same table retitled: each failed bank by name and location, its charter number, date and capital at organization, its dividends while solvent, its capital at failure, the receiver's appointment, the cause of failure, the lawful money deposited and the circulation; 1905 prints it across facing pages, grouped by year of failure with a Total line for each, 1925 on one page with total deposits at suspension |
| Specie and circulation / Circulation of national banks | `SPECIE AND CIRCULATION OF NATIONAL BANKS AT DATE OF` (1905); `Circulation of national banks at date of each report during the year ended` (1925) | 1905_p130, 1905_p131, 1925_p308 | no | the same stub but different measures: 1905 prints the banks' specie by kind (gold coin, gold certificates, clearing-house certificates, silver), 1925 the notes received from the Comptroller, on hand and outstanding at each call |
| Abstract of reports of earnings and dividends of national banks | `Abstract of reports of earnings and dividends of national banks, by size of banks, for by Federal Reserve districts` (1905); `EARNINGS AND DIVIDENDS OF NATIONAL BANKS` (1925) | 1905_p186, 1905_p187, 1925_p061 | yes | the same table, split by the survey's grouping rather than by its title: each state and reserve city with Total lines for each group of states, and the items of one earnings statement (capital, surplus, earnings, losses charged off, dividends); 1905 prints them across facing pages, 1925 across several, in thousands, with ratios |

## Chosen (4)

| # | Family | Kind | Held-out pages | Held-out years | Drafted from | Title given |
|--:|---|---|--:|---|---|---|
| 1 | `occ_abstract_by_states`: Abstract of reports, arranged by States and reserve cities | C | 255 | 1910, 1915, 1930, 1935 | 1905_p507, 1925_p342 | Abstract of reports since October 10, 1924, arranged by States and reserve cities |
| 2 | `occ_aggregate_resources_liabilities`: Aggregate resources and liabilities of national banks | C | 87 | 1910, 1915, 1920, 1930 | 1905_p395, 1925_p326, 1905_p398 | Aggregate resources and liabilities of national banks from January, 1914, to September, 1925 |
| 3 | `occ_banks_in_charge_of_receivers`: National banks placed in the hands of (in charge of) receivers | T | 61 | 1910, 1915, 1920, 1930 | 1905_p239, 1925_p238 | National banks in charge of receivers, year ended October 31, 1925, capital at date of organization and at date of failure, causes of failure, dividends paid while solvent, circulation outstanding at date of failure, lawful money deposited with Treasurer of the United States to redeem circulation, and total deposits at date of suspension |
| 4 | `occ_earnings_and_dividends`: Abstract of reports of earnings and dividends of national banks | T | 52 | 1910, 1930, 1935 | 1905_p186, 1925_p061 | Abstract of reports of earnings and dividends of national banks for the year ended June 30, 1925 |

## Passed every rule but not chosen (4)

Not judged: each is one survey family in both development years, ranked below the last choice, so whether its two years print one table was not looked at.

| Family | Kind | Held-out pages | Held-out years |
|---|---|--:|---|
| NATIONAL BANKS CHARTERED DURING THE YEAR ENDED OCTOBER 31, 1905 | T | 22 | 1910, 1915, 1920, 1930, 1935, 1940 |
| PROFIT ON NATIONAL-BANK CIRCULATION | T | 5 | 1910, 1915, 1930 |
| Comparative statement of the transactions of the New York Clearing House for fifty-seven years and for each year, number of banks, aggregate capital, clearings, balances, average of | T | 4 | 1910, 1930 |
| Taxes assessed on national-bank circulation, years ended June | T | 3 | 1910, 1915, 1930 |

## Excluded

| Table | Held-out pages | First rule failed |
|---|--:|---|
| Principal items of resources and liabilities of national banks | 81 | 2: two tables, judged from development pages |
| Lawful money reserve / Reserve computation of national banks | 61 | 2: two tables, judged from development pages |
| Specie and circulation / Circulation of national banks | 55 | 2: two tables, judged from development pages |
| NATIONAL-BANK NOTES ISSUED, REDEEMED, AND OUTSTANDING, BY DENOMINATIONS AND AMOUNTS, ON OCTO | 9 | 4: a development year has no table page with a Total line |
| United States bonds on deposit to secure circulating notes of national | 5 | 4: a development year has no table page with a Total line |
| NUMBER, CAPITAL STOCK PAI D IN, CIRCULATION OUTSTANDING, AND AGGREGATE ASSETS OF NATIONAL BA 1863, TO AUGUST 25, 1905, TOGETHER WITH THE TOTAL AMOUNT OF MONEY IN | 2 | 4: a development year has no table page with a Total line |
