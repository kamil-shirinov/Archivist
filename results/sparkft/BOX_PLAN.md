# P34 — cached box diagnostic, fixed before OCR matching

2026-10-31. No new model calls. Read only the five P33 page reads directly from
`openw-measure`, pinned to its current commit before reading. Check each page ID
against `data/real/split.json` before loading its cached response, image or PDF.

Match figure cells only, excluding labels, blanks, signs without digits and
abstentions. A match requires at least three digits after the existing OCR
confusion correction, exactly one occurrence in the entire page's OCR layer,
and exactly one claim by the host's returned figure cells. Match by text only:
never select the nearest occurrence using a model box. This produces diagnostic
anchors, not independent human labels or full-table accuracy.

Compare identity, undoing the existing 0–1000 conversion (pixels mistaken for
normalised coordinates), an extra 0–1000 conversion, PDF-point scaling, vertical
reflection and swapped axes. Also compare a translation and diagonal affine fit
learned from the *other pages* of the same host (leave-one-page-out). For a
per-page diagnostic only, sort anchors by SHA256(`sparkft-box:<field_id>`), fit on
the first floor(80%) and measure on the remainder. Fit no candidate on its own
scoring anchors. Apply an affine transform to both box corners without inflation.

Report figure-box full containment of the OCR word, OCR-centre containment,
median centre error and centre offsets. The first metric is the main one.
A simple conversion qualifies as a reusable fix only if it achieves at least
90% full containment on every measured page, improves pooled containment, and
has at least ten scoring anchors per page. A page-specific fit is a diagnostic,
not a reusable coordinate conversion. No production setting changes on an
in-sample fit or an improvement confined to a subset of pages.

This diagnostic uses development pages already read in P33. It is separate from
any future fine-tuning validation and cannot establish generalisation.
