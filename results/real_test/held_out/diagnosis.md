# Why the real-scan scores came out as they did (P47)

A diagnosis of the wrong values behind the two held-out scores: version 1
(`results/real_test/held_out/score/`, Muse Spark 1.3 with S0+grid boxes) and open weights
(`results/real_openw/held_out/score/`, Muse Spark Open with S0+table-v2 boxes). It gives counts and
shares only, by stratum and family, and names no cell, page, value or label. It changes no score,
record or scoring rule, and nothing here replaces an official figure. Where a rate is given under
another convention, it is set beside the official one and marked as such. No model was called and
no page image or PDF was opened: everything comes from the committed records, labels and the two
score files. The script that did the work handles cells one at a time, so it is kept outside the
repository; only these aggregates are committed. The owner relabels 40 cells after this, so
nothing below is finer than a family.

## In short

- **On pages whose layout matches the template ("left out"), almost every wrong value is a dash
  read where the label is blank.** For version 1, 15 of the single read's 22 wrong values are
  this, and so are all 9 wrong values Archivist accepted. For open weights it is 14 of 25 and 4 of
  5. The reads write a printed dash as "-", as their prompt tells them. Every label for a nil cell
  is "blank". The template's comparison counts "-" as 0 and a blank as a blank, so every such pair
  scores as wrong. **The official score depends on this convention more than on anything else.**
  Counting the two alike (beside the official score, not replacing it), version 1's left-out
  error rates would be 3.2% for the single read and 0.0% for Archivist, instead of 16.7% and
  18.7%.
- **With every page kept, layout drift is the largest cause:** cells labelled "column not on this
  page", on pages printed after April 1940 in a layout the template does not describe. That is 60
  of version 1's 126 single-read wrong values and 12 of its 32 accepted ones (36 of 93 and 5 of
  13 for open weights). In 49 of version 1's 60, the read gave nothing for a column the page does
  not print, and the rule counts that as wrong.
- **Misalignment, digit misreads and everything else are small.** Version 1: 2, 6 and 11 of 126
  single-read wrong values, and 1, 0 and 1 of 32 accepted. Open weights: 4, 6 and 9 of 93, and 0,
  0 and 1 of 13. One wrong value in each configuration is a row not on the page.
- **Where the re-read looked:** apart from layout drift, the records show no accepted wrong value
  whose crop sat off its own read's row or column, for version 1. Open weights has one such crop
  and one crop that shares its box with another cell's. **Arithmetic:** of version 1's 14
  accepted wrong values that are not a dash-against-blank difference, 9 were in an identity that
  could not be checked because of the cell's own read (mostly a blank where a blank means
  "unknown"), and 5 were in an identity that held.

## Method

### Which wrong values

A wrong value is one the official scorer judges wrong (`labelling/score.py`, `judged`): every
labelled cell the read gave a value for that does not equal its label under
`TemplateType.canonical`, including "row not on the page" and "column not on this page". There are
four sets:

- version 1's single read;
- the version 1 values Archivist accepted (policy v2 status `accepted`, re-reads as run);
- open weights' single read (the field the open-weights runner matched to each drawn cell);
- the open-weights values Archivist accepted.

Each set is given in two layouts. **Kept** is all 400 drawn cells. **Left out** drops the cells on
the 40 changed-layout pages of the both-ways set.

Before any cause was tallied, the cells were rebuilt from the records and checked against the
published scores. In every layout, the outcome counts (right, wrong, can't read, abstained) and the
three as-run rates (single read error, Archivist error, catch rate) equal both `score.json` files
to the last digit. Statuses are as run. In the `failed_to_review` variant, version 1's kept
Archivist error is 36.3% instead of 36.9%. Splitting that variant by cause would need the re-reads'
cache keys, which are computed from the page images, so it is not split here.

### Rules, fixed before anything was counted

**Normalisation N (format only).** N is applied alike to the read's text and the label's text, and
a label of "blank" is the empty text.

1. *Marks.* Delete `*`, `†`, `‡` and `§`. Delete a footnote reference of the form `<digits>/`.
   Delete one letter p, r or e (either case) at the start or end, with or without a space.
2. *Nil.* After step 1, these are all nil: an empty text, a lone dash (`-`, `–`, `—` or `−`, or
   two of them), `.`, `…`, or a figure equal to zero. So a dash, a blank and a zero are the same.
3. *Separators.* Spaces are removed. A `,` or `.` followed by exactly three digits and then the
   end, a `,` or a `.` is a thousands separator and is dropped. Any other `,` or `.` is the
   decimal point. Parentheses or a leading dash make the figure negative.

Two texts are equal under N when both are nil, both are the same number, or both are the same text
after step 1 with case and spacing ignored. When N makes the difference, the step it needed is
recorded: nil, marks or separators.

**Causes.** The first rule that applies wins:

1. *Layout drift:* the label is "column not on this page".
2. *Row not on the page:* the label is "row not on the page".
3. *Format only:* the read and the label are equal under N.
4. *Misalignment:* either of two tests holds.
   - The label is a figure (not nil), and the same read gives that figure, under N, in an adjacent
     cell of the same page. Adjacent means the same row with the money column just left or right
     in the template's order, or the same column with the row just above or below.
   - The read's figure equals, under N, the label of an adjacent cell that was itself labelled.
5. *Digit misread:* the read and the label are both figures, and their digit strings either have
   the same length and differ in one or two places, or differ by one digit dropped or added.
6. *Other:* everything else, split into five kinds:
   - a figure read where the label is nil;
   - nil read where a figure is printed;
   - the same digits, with the point or the sign differing;
   - two figures further apart than a digit misread;
   - not a figure.

**Where the crop sat, for accepted wrong values, from the records alone.** Each accepted wrong
value gets one of four marks:

- *No labelled cell:* the label says the column or row is not printed, so the crop showed something
  else.
- *Out of line:* the crop's centre is nearer the median centre of another money column of the same
  read on that page than its own column's, or nearer another row's than its own row's. Medians are
  taken over the other cells' boxes.
- *Shared box:* the cell's box overlaps another cell's box from the same read on that page by an
  intersection over union of at least 0.5.
- *In line:* none of the above.

These tests cannot see a read whose whole column or row is shifted, because its boxes shift with
it. Only the page can show that, and this diagnosis does not open it.

**Arithmetic, for accepted wrong values.** For each value, every identity instance that includes
it is checked on the in-context values. The value gets one of three marks:

- no identity names the cell;
- named, and some instance held (it applied but did not see the error);
- named, but no instance could be checked: it could have caught the error but did not apply,
  with the reason (the cell's own value, another cell's value, an all-blank instance, or another
  table not found).

## 1. Causes, by stratum and family

Counts of wrong values. The weighted share row uses the score's own cell weights. "Left out" is
the same set without the 40 changed-layout pages, so the total-claims rows are the same in both
layouts.

#### Version 1, wrong values in the single read

| Layout | Group | Wrong | Layout drift | Row not on page | Format only | Misalignment | Digit misread | Other |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| kept | Short-term foreign liabilities | 51 | 46 | 0 | 1 | 0 | 1 | 3 |
| kept | Security transactions | 47 | 10 | 0 | 30 | 2 | 0 | 5 |
| kept | Forward exchange | 13 | 3 | 0 | 7 | 0 | 2 | 1 |
| kept | Railroad | 5 | 1 | 0 | 4 | 0 | 0 | 0 |
| kept | **1939–1942 stratum** | 116 | 60 | 0 | 42 | 2 | 3 | 9 |
| kept | Total claims by country | 10 | 0 | 1 | 4 | 0 | 3 | 2 |
| kept | **All** | 126 | 60 | 1 | 46 | 2 | 6 | 11 |
| kept | *All, weighted share* | | 54% | 0% | 33% | 2% | 2% | 8% |
| left out | Short-term foreign liabilities | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| left out | Security transactions | 9 | 0 | 0 | 9 | 0 | 0 | 0 |
| left out | Forward exchange | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| left out | Railroad | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| left out | **1939–1942 stratum** | 12 | 0 | 0 | 11 | 0 | 0 | 1 |
| left out | Total claims by country | 10 | 0 | 1 | 4 | 0 | 3 | 2 |
| left out | **All** | 22 | 0 | 1 | 15 | 0 | 3 | 3 |
| left out | *All, weighted share* | | 0% | 2% | 81% | 0% | 6% | 12% |

#### Version 1, wrong values Archivist accepted

| Layout | Group | Wrong | Layout drift | Row not on page | Format only | Misalignment | Digit misread | Other |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| kept | Short-term foreign liabilities | 8 | 7 | 0 | 0 | 0 | 0 | 1 |
| kept | Security transactions | 18 | 2 | 0 | 15 | 1 | 0 | 0 |
| kept | Forward exchange | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| kept | Railroad | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| kept | **1939–1942 stratum** | 30 | 12 | 0 | 16 | 1 | 0 | 1 |
| kept | Total claims by country | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| kept | **All** | 32 | 12 | 0 | 18 | 1 | 0 | 1 |
| kept | *All, weighted share* | | 37% | 0% | 56% | 3% | 0% | 4% |
| left out | Security transactions | 7 | 0 | 0 | 7 | 0 | 0 | 0 |
| left out | Other three 1939–1942 families | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| left out | **1939–1942 stratum** | 7 | 0 | 0 | 7 | 0 | 0 | 0 |
| left out | Total claims by country | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| left out | **All** | 9 | 0 | 0 | 9 | 0 | 0 | 0 |
| left out | *All, weighted share* | | 0% | 0% | 100% | 0% | 0% | 0% |

#### Open weights, wrong values in the single read

| Layout | Group | Wrong | Layout drift | Row not on page | Format only | Misalignment | Digit misread | Other |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| kept | Short-term foreign liabilities | 32 | 27 | 0 | 1 | 0 | 1 | 3 |
| kept | Security transactions | 29 | 5 | 0 | 21 | 0 | 1 | 2 |
| kept | Forward exchange | 12 | 3 | 0 | 7 | 0 | 1 | 1 |
| kept | Railroad | 5 | 1 | 0 | 4 | 0 | 0 | 0 |
| kept | **1939–1942 stratum** | 78 | 36 | 0 | 33 | 0 | 3 | 6 |
| kept | Total claims by country | 15 | 0 | 1 | 4 | 4 | 3 | 3 |
| kept | **All** | 93 | 36 | 1 | 37 | 4 | 6 | 9 |
| kept | *All, weighted share* | | 47% | 0% | 38% | 1% | 4% | 9% |
| left out | Short-term foreign liabilities | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| left out | Security transactions | 8 | 0 | 0 | 8 | 0 | 0 | 0 |
| left out | Forward exchange | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| left out | Railroad | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| left out | **1939–1942 stratum** | 10 | 0 | 0 | 10 | 0 | 0 | 0 |
| left out | Total claims by country | 15 | 0 | 1 | 4 | 4 | 3 | 3 |
| left out | **All** | 25 | 0 | 1 | 14 | 4 | 3 | 3 |
| left out | *All, weighted share* | | 0% | 2% | 77% | 8% | 6% | 6% |

#### Open weights, wrong values Archivist accepted

| Layout | Group | Wrong | Layout drift | Row not on page | Format only | Misalignment | Digit misread | Other |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| kept | Short-term foreign liabilities | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| kept | Security transactions | 6 | 0 | 0 | 6 | 0 | 0 | 0 |
| kept | Forward exchange | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| kept | Railroad | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| kept | **1939–1942 stratum** | 12 | 5 | 0 | 7 | 0 | 0 | 0 |
| kept | Total claims by country | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| kept | **All** | 13 | 5 | 0 | 7 | 0 | 0 | 1 |
| kept | *All, weighted share* | | 44% | 0% | 54% | 0% | 0% | 2% |
| left out | Security transactions | 3 | 0 | 0 | 3 | 0 | 0 | 0 |
| left out | Forward exchange | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| left out | Short-term foreign liabilities, Railroad | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| left out | **1939–1942 stratum** | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| left out | Total claims by country | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| left out | **All** | 5 | 0 | 0 | 4 | 0 | 0 | 1 |
| left out | *All, weighted share* | | 0% | 0% | 93% | 0% | 0% | 7% |

**Within the causes:**

- **Format only.** Every format-only wrong value needed the nil step except one in each
  configuration. Version 1 has 45 nil and 1 separators; open weights has 36 nil and 1 separators.
  Each separators case is a single read on a 1939–1942 changed-layout page, and neither was
  accepted. Footnote marks never made a difference: no read and no label among the scored cells
  carries a mark.
- **Other, version 1, kept single read (11).** 6 read nil where a figure is printed. 4 are two
  figures further apart than a digit misread. 1 is a figure read where the label is nil.
- **Other, open weights, kept single read (9).** 6 are figures further apart. 2 read nil where a
  figure is printed. 1 is a figure where the label is nil.
- **Other, accepted.** The one accepted "other" in each configuration is nil read where a figure
  is printed. It is in short-term foreign liabilities for version 1 and in total claims for open
  weights.
- **Misalignment.** Every misalignment found was by the first test: the label's figure stands in
  an adjacent cell of the same read. All 4 of open weights' are in total claims.
- **Layout drift: what the read gave for a column the page does not print.** Version 1: nothing
  (blank) in 49 of 60, a dash in 2, a figure in 9. Of the 12 it accepted, 7 are blank (the blind
  re-read also saw blank), 1 is a dash and 4 are figures. Open weights fills missing columns far
  more often: of its 36, a figure in 21, a dash in 6 and nothing in 9. Of the 5 it accepted, 4 are
  blank and 1 is a figure.

## 2. Accepted wrong values: the crop, and the arithmetic

| Configuration | Group | Wrong | Crop: no labelled cell | Crop: out of line | Crop: shared box | Crop: in line | Identity held | Identity named, did not apply | No identity names it |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Version 1 | Short-term foreign liabilities | 8 | 7 | 0 | 0 | 1 | 0 | 8 | 0 |
| Version 1 | Security transactions | 18 | 2 | 0 | 0 | 16 | 17 | 1 | 0 |
| Version 1 | Forward exchange | 3 | 3 | 0 | 0 | 0 | 3 | 0 | 0 |
| Version 1 | Railroad | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| Version 1 | **1939–1942 stratum** | 30 | 12 | 0 | 0 | 18 | 21 | 9 | 0 |
| Version 1 | Total claims by country | 2 | 0 | 0 | 0 | 2 | 1 | 1 | 0 |
| Version 1 | **All** | 32 | 12 | 0 | 0 | 20 | 22 | 10 | 0 |
| Open weights | Short-term foreign liabilities | 5 | 5 | 0 | 0 | 0 | 1 | 4 | 0 |
| Open weights | Security transactions | 6 | 0 | 0 | 0 | 6 | 6 | 0 | 0 |
| Open weights | Forward exchange | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 0 |
| Open weights | Railroad | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Open weights | **1939–1942 stratum** | 12 | 5 | 1 | 0 | 6 | 8 | 4 | 0 |
| Open weights | Total claims by country | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |
| Open weights | **All** | 13 | 5 | 1 | 1 | 6 | 8 | 4 | 1 |

Kept layout. In the left-out layout, version 1's 9 are all in line (8 identity held, 1 named but
not applied). Open weights' 5 are 3 in line, 1 out of line and 1 shared box (4 identity held, 1 no
identity).

**Where the re-read's crop sat.**

- **Version 1:** 12 of its 32 accepted wrong values have no labelled cell: the column is not
  printed, so the crop showed something else. In 7 of them both the read and the re-read saw
  nothing there. None of the other 20 sits
  out of line with its read's row or column or shares another cell's box. 18 of those 20 are dash
  against blank, which says nothing about position, and the other 2 are the one misalignment and
  the one "other".
- **Open weights:** 5 of 13 have no labelled cell. 1 is out of line (a dash against blank in
  forward exchange). 1 shares its box with another cell (total claims, nil read where a figure is
  printed). 6 are in line.

**Box sources of the accepted wrong values.** Version 1: model 24, grid 5, OCR 3. Open weights:
`v1:model` 10, `v1:grid` 3, none from table-v2's own anchors. As section 3 explains, a crop counted
"in line" here could still sit on a shifted column.

**Arithmetic.**

- **Version 1:** an identity names all 32. For 22 an instance held: 17 dash against blank (the
  read's dash counts as 0 and the sum balanced; arithmetic cannot know the label is blank) and 5
  layout drift. For 10, an identity named the cell but no instance could be checked, so it could
  have caught the error but did not apply. In 9 of them the reason was the cell's own read: 7
  layout drift, 1 misalignment and 1 other, all a blank where the column's blank means "unknown"
  or a value that is not a figure. In 1 (a dash against blank) the reason was another cell's
  value. So of the 14 accepted wrong values that are not a dash-against-blank difference, 9 had no
  checkable identity because of their own blank, and 5 were in identities that held.
- **Open weights:** 8 held (7 dash against blank, 1 layout drift). 4 were named but not applied
  (layout drift, the cell's own value). 1 is in no identity at all (total claims).

## 3. Do the reads and the labels write nil and marks alike?

The official rule (`TemplateType.canonical`) reads a figure as its value. A lone dash is 0, and an
empty text is blank, which is not 0. Footnote marks are not removed: a figure carrying one stops
being a figure and is compared as text. Separators are taken as thousands commas and a decimal
point. On each side:

- **The reads.** The read prompt says: *A dash printed in a cell is copied as "-".* The blind
  re-read copies "exactly as printed" and gives "" for a blank cell.
- **The labels.** The labelling page offers a printed value "typed as printed", or **Blank**.
- **Over the scored cells.** These are the cells each read gave a value for, not counting those
  labelled row or column not printed. No label is a typed dash or a zero: every nil label is
  "blank". The read wrote a dash on 45 of those cells for version 1 and on 36 for open weights,
  and every one is scored wrong. The read wrote blank where the label is blank on 4 cells for
  version 1 and on 1 for open weights, and those are right.

**The official score depends on this convention, and it is the largest single effect in it.** One
more thing in the rule is uneven. The comparison ignores a column's `blank_means`, so the
difference counts even in forward exchange and railroad, whose templates say a blank there *is*
zero. Their identities count a dash and a blank alike. That covers 11 of the 45 dash-against-blank
cells for version 1 and 11 of the 36 for open weights; the rest are in columns where a blank means
"unknown".

Which side is right on a given cell cannot be settled from the records. The blind re-read is a
second, independent look at the same cell:

- version 1 (45 cells): it saw a dash on 25, a blank on 15 and a figure on 5;
- open weights (36 cells): a blank on 21, a dash on 9, a figure on 3, and 3 without a usable
  answer.

So some of these cells print a dash and some may print nothing. Only the page shows which, and
looking would be a cell-by-cell check, so it belongs after the relabel.

**The other conventions do not matter.** No read or label among the scored cells carries a
footnote mark. Commas against a dot made the difference on 1 cell in each configuration, a single
read on a changed-layout page that was not accepted. No zero is written either way.

## Rates beside the official ones

These rates are not the score, and none was pre-registered. They use the score's weights,
intervals and functions (`score.estimate`, as run), with one convention changed, so a reader can
see what each cause is worth. Each cell gives the rate with its 95% interval.

| Configuration | Layout | Variant | Single read error | Archivist error | R1 by its rule |
|---|---|---|---|---|---|
| Version 1 | left out | **official** | 16.7% (8.2–25.8) | 18.7% (1.6–31.8) | not met |
| Version 1 | left out | dash, blank, zero alike (N) | 3.2% (1.2–6.5) | 0.0% (0.0–0.0) | would be met |
| Version 1 | kept | **official** | 41.1% (30.6–52.4) | 36.9% (24.7–50.4) | not met |
| Version 1 | kept | N | 27.4% (15.6–40.6) | 16.3% (6.1–33.3) | not met |
| Version 1 | kept | layout-drift cells given no value | 24.4% (18.0–30.9) | 26.9% (16.2–37.5) | not met |
| Version 1 | kept | both | 6.7% (3.7–10.3) | 3.0% (0.0–9.0) | not met |
| Open weights | left out | **official** | 16.4% (7.3–27.7) | 13.6% (4.8–30.7) | — |
| Open weights | left out | N | 3.8% (1.3–8.6) | 1.0% (0.0–5.1) | — |
| Open weights | kept | **official** (O1's variant) | 34.5% (22.1–47.9) | 27.1% (13.9–49.9) | — |
| Open weights | kept | N | 21.4% (9.0–36.5) | 12.5% (0.8–36.1) | — |
| Open weights | kept | layout-drift cells given no value | 21.8% (14.2–30.9) | 17.3% (7.7–31.3) | — |
| Open weights | kept | both | 6.1% (2.7–10.5) | 0.7% (0.0–3.0) | — |

R1 and O1 stand as scored: R1 not met in any variant, and O1 not met at 27.1%. The 0.7% in the
last row comes from two changes to the rules, neither of them pre-registered, and is not O1.
Open weights' rates also leave out the drawn cells it gave no value for: 63 in all, 62 of them
rows it found no match for, as its score's coverage line says.

## What each cause would change if fixed

Each figure is the as-run point estimate when that cause's wrong values are made right, all else
as scored. Layout drift is the exception: its cells are given no value, which is what a template
that knew the column was not printed would do. These are upper bounds on what a fix could do.

| Cause | V1 single read, kept | V1 Archivist, kept | V1 Archivist, left out | Open single read, kept | Open Archivist, kept |
|---|---|---|---|---|---|
| *(official)* | 41.1% | 36.9% | 18.7% | 34.5% | 27.1% |
| Dash against blank (format only) | 27.4% | 16.3% | 0.0% | 21.4% | 12.5% |
| Layout drift | 24.4% | 26.9% | 18.7% | 21.8% | 17.3% |
| Misalignment | 40.4% | 35.6% | 18.7% | 34.0% | 27.1% |
| Digit misread | 40.1% | 36.9% | 18.7% | 33.0% | 27.1% |
| Other | 37.8% | 35.5% | 18.7% | 31.5% | 26.5% |
| Row not on the page | 41.1% | 36.9% | 18.7% | 34.4% | 27.1% |

In plain words:

- **The dash-against-blank convention** is a scoring and labelling question, not a reading
  error. Settling it means deciding, in a new pre-registered rule, whether a printed dash and a
  blank count alike, at least where the template says a blank is zero. Labelling would then
  follow that rule. Of all the possible fixes, it moves version 1's same-layout result the most:
  from Archivist accepting more wrong values than the single read gives (18.7% against 16.7%) to
  accepting none (0.0% against 3.2%).
- **Layout drift** is a template problem. The 1939–1942 tables changed their columns from April
  1940, and the templates describe the earlier layout. Templates for the later layouts, or a
  check that refuses a page whose printed headings differ from its template's, would take
  version 1's kept single-read error from 41.1% to about 24%. The fix matters more in kind for
  open weights: 21 of its 36 drift errors are figures put in a column that is not printed,
  against 9 of version 1's 60.
- **Misalignment, digit misreads, a missing row and the rest** are the reading errors proper.
  Together they are 20 of version 1's 126 single-read wrong values and 2 of its 32 accepted ones.
  Fixing any one moves a headline rate by at most about three points. With both fixes above,
  these are what remains: version 1 single read 6.7% and Archivist 3.0%, and open weights single
  read 6.1% and Archivist 0.7%, kept.
- **The arithmetic checks** miss accepted errors mainly where the cell's own read is blank in a
  column whose blank means "unknown" (9 of version 1's 14 substantive accepted errors). Reading
  such a blank as an open question rather than letting it pass would send those cells to review,
  but it would also send many right blanks there.

## Limits

- One labeller, and the cause rules are this diagnosis's own, written before the tally. Another
  reasonable N (say, one that keeps a dash apart from a blank in columns where a blank means
  "unknown") would move some cells between "format only" and "other".
- The crop tests use the read's own boxes. A read whose whole column is shifted carries its boxes
  with it and looks in line, so "in line" is not proof that the crop sat on the labelled cell.
  Only the pages could show that, and none was opened.
- Counts are small: 32 and 13 accepted wrong values in all. Family-level counts rest on 10 to 12
  pages each.
- Statuses are as run. The `failed_to_review` variant, which moves a few of version 1's accepted
  cells to review, is not split by cause.
