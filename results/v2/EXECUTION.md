# Execution record

- Worktree `.worktrees/v2`, branch `v2`, created from freshly fetched
  `origin/main` at `006faa9`. Main's working files were not edited. The user's
  explicit worktree/push-only instruction overrides AGENTS.md's default workflow.
- Read AGENTS.md, CLAUDE.md, DECISIONS.md (including D7, D20, D23, D32, D35,
  D37), the original pre-registration and the two requested development reports.
- The owner explicitly permitted `results/real_test/development/` for the Check
  and measurements. Everything else under `results/real_test/` remains forbidden.
  No held-out page or artifact was opened, and nothing ran on a held-out page.
- Main's cache and synthetic development/validation images are directory links.
  Real archive links expose only development issues/volumes, selected from each
  committed split/manifest; no held-out scan is linked. No permission bits on the
  main checkout were changed. A Python audit hook under ignored scratch refuses
  all writes resolving into main and reads under forbidden real-test paths.
  This is a Python-process guard, not a filesystem mount. The measurement's
  writable cache is local; only explicitly requested old cache entries are copied
  into it. The Check sets every model spend cap to zero.
- No new page extraction. Fifteen Spark 1.3 reads were reproduced from exact cache
  requests with caps zero. Five Open reads are P33's committed development reads.
  The fixed 800-cell draw is in draw.json, written before candidate geometry.
- Baseline geometry preceded PLAN.md. Geometry-only development found the two
  implementation bugs documented there. geometry_initial.json preserves that
  first pass's pooled counts. The final candidate was hashed in
  development_freeze.json before the paired re-read comparison.
- A first, sandboxed paired pass could use cache hits but every new API request
  failed to connect. It was stopped. Completed page records are preserved under
  failed_network_pass/; the interrupted page had no completed record. These
  records are infrastructure diagnostics, not the completed paired comparison.
  The same prompts/requests resumed with network access and the same local cache,
  canonical ledger and recorded caps. Only answered calls enter the existing
  ledger; transport failures have no reported token usage or billed cost.
- The final candidate is unchanged after the first paired re-read was observed.
  Tests use invented figures only. The pre-existing Sparkft audit now resolves
  immutable `633cdff^{commit}` instead of the deleted branch name. In this repo
  its actual path is `sparkft/boxes.py`, not `src/archivist/sparkft/boxes.py`.

Reproduction (after restoring the same development-only links and the model
response caches; acquisition itself has every spend cap zero):

```
uv run python -m archivist.templates.v2_measure acquire
uv run python -m archivist.templates.v2_measure baseline
uv run python -m archivist.templates.v2_measure geometry
uv run python -m archivist.templates.v2_measure diagnose
uv run python -m archivist.templates.v2_measure paired
uv run python -m archivist.templates.v2_measure summarize
```

`paired` is resumable from its saved per-page records and model-response cache;
existing answers are not requested again. The two hosts were allowed to finish
independently; eight workers per host, no added allowance or changed request.
All 20 page/reader samples completed. Candidate code, rule and draw still match
their pre-comparison SHA-256 hashes. No candidate change followed the re-read
results. Full-figure containment alone is insufficient: a two-pixel ink margin
also expands the padded re-read image. On some Spark cells that changes a formerly
agreeing answer into another figure, a formatting mismatch or an illegible read.

Check execution: the first full pytest pass hit two failures because the scratch
Python read guard also matched invented scorer-test records in temporary folders.
Those tests do not open real held-out records. The guard was narrowed to the
actual main/worktree real-test directories, retaining the same prohibition on
real held-out data. The two affected synthetic tests then passed. No scorer or
test implementation was changed for this issue; the exact full Check is repeated
with the corrected guard. Pre-commit on the staged task files passed all hooks.

The next Check attempt stopped during collection because newly installed hook
repositories under results/scratch/precommit exposed their own upstream tests to
pytest. The task-local hook cache was moved to hidden ignored .cache/ before the
final Check; no test discovery setting, project test, or dependency was changed.
The final Check runs exactly `uv run pytest -q && uv run python -m archivist.replay`,
unpiped, with the corrected read guard and both source links read-only in use.

Final exact unpiped Check: **1,520 tests passed**; replay passed for all 11 runs,
all three exports matched, and the canonical ledger remained at 83,142 lines.
The result is recorded in checks.json. No main working file or held-out artifact
was modified. No held-out v2 execution, tag, merge or adopted configuration exists.
