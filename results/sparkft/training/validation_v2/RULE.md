# Coverage amendment, before archive inference/training

Scope: all five approved Treasury families enabled by config/real_test.toml.
Inventory full PDF OCR from development issues only, gated against split.json
before any PDF is opened. Candidate pages match an approved title pattern in
the first 1,024 characters, contain at least 20 numeric tokens, and are not a
contents page. Include the approved development evidence pages even if their
OCR title is corrupt, recording that discrepancy.

A known supported layout stratum is its approved single-panel template's row
mode and column schema plus page orientation (portrait/landscape). Record the
complete structural signature and every candidate. These five approved templates
have one declared layout each; do not claim to cover unknown or unsupported
layouts outside that inventory. Retain original validation pages, then fill each
family/layout stratum to at least three development pages, ordering candidates by
SHA256("sparkft-coverage-3402:<family>:<layout>:<page>"). No answer, model box or
accuracy score selects a page. If fewer than three nontraining pages exist,
withdraw the minimum necessary candidate training pages in the same hash order
before any training. Refuse a stratum with fewer than three available pages;
never use held-out pages or silently omit a layout.

This requires reserving all three claims-by-country development pages for
validation. Its 118 prepared answers leave training before any optimizer update.
The remaining three training pages retain 283 answers. Preserve the original
401-answer preparation as history; do not overwrite it.

Freeze the draw before references or base outputs. Reference semantics use cached
independent page reads where available. A cache miss may use a hosted Baseten read
through registry/cache/budget, within the original $5 task cap; never use a new
Meta/Fireworks call. Target values and boxes must match unique exact PDF OCR
numbers; never choose an OCR occurrence using either evaluated model's box.
These are model-assisted OCR proxies; record host/model/cache hashes and coverage.
At most 20 references per page, by the already-declared field hash rule. References
are evaluation-only; no new reference read becomes a training target.

Require at least three scorable pages in every family/layout before archive
training. Report per page, family and layout: reference support, exact value
accuracy, full OCR-figure containment, joint accuracy, invalid/missing outputs,
latency and cost. A missing comparison or deficient coverage rejects adoption.
The trained model must strictly improve pooled value accuracy AND containment,
and neither metric may decrease in ANY family or layout. No tolerance for a
one-cell family regression, no family pooling to hide it, no post hoc checkpoint
choice. Held-out data, the owner's labels and Glimmer files are never accessed.
