# Held-out scoring with the dash-corrected key, beside the official score (version 1)

PREREGISTRATION_REAL.md and PREREGISTRATION_OPENW.md, Deviations, 2026-11-02. **The official score stands as scored** (`results/real_test/held_out/score/`); it is shown first. The corrected key differs from the first-pass key only where the dash check found a dash printed in a cell first labelled blank; it is scored by `labelling/score.py`'s own functions under unchanged rules.

Code: `run-real-treasury` (b8ff15d), checked frozen; scorer files (sha256): labelling/score.py `82e56a8613e7`, labelling/score_corrected.py `ccf0f84ef199`. Intervals: 95%, page bootstrap within strata; Wilson for the relabel.

Files (sha256): `results/real_test/held_out/labels/draw.json` b575cc271445abc1621bfd942362c7b3db6e61b9e26ceca83648f0b580492168, `results/real_test/held_out/labels/labels.jsonl` 5f98f48235f3f4396594b11fe5ccd4d98b66c98629761efa330f80f3134de118, `results/real_test/held_out/labels/relabels.jsonl` 5861a0f5e8c1f543fef15a9f2966382beefb75dbd62ec12462dcb9c4ba24f2c0, `results/real_test/held_out/labels/dashes_checked.jsonl` 580fd0168f17f9596b84d110db4bcea826e70ed905e3c20212a1100d9a7d1f79, `results/real_test/held_out/score/score.json` 0c4d83bbee7ef00aa673dbb1d339778540fdd8605cb104a73c93d04822c898a0

## The key

First-pass blanks checked: 50 ({'1939_1942': 46, 'total_claims': 4}). Marks: dash printed 45, nothing printed 4, can't tell 1. Answers changed: 45 of 400 ({'1939_1942': 41, 'total_claims': 4}), each from blank to "-".

Relabel agreement: first pass key: 24 of 40 (44.6%–73.7%); corrected key: 29 of 40 (57.2%–83.9%). The plan's figure is the first-pass key's.

## Labelled cells

| Variant | Key | Single read error | Archivist error (accepted) | Catch rate | R1 |
|---|---|---|---|---|---|
| left_out/as_run | **official** | 16.7% (8.2%–25.8%) | 18.7% (1.6%–31.8%) | 44.9% (27.9%–94.4%) | not met |
| left_out/as_run | corrected | 3.2% (1.2%–6.5%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) | met |
| left_out/failed_to_review | **official** | 16.7% (8.2%–25.8%) | 18.7% (1.6%–31.8%) | 44.9% (27.9%–94.4%) | not met |
| left_out/failed_to_review | corrected | 3.2% (1.2%–6.5%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) | met |
| kept/as_run | **official** | 41.1% (30.6%–52.4%) | 36.9% (24.7%–50.4%) | 74.2% (60.3%–84.9%) | not met |
| kept/as_run | corrected | 27.8% (16.0%–40.9%) | 16.3% (6.1%–33.3%) | 83.1% (71.1%–92.9%) | not met |
| kept/failed_to_review | **official** | 41.1% (30.6%–52.4%) | 36.3% (24.5%–50.1%) | 75.5% (62.3%–85.8%) | not met |
| kept/failed_to_review | corrected | 27.8% (16.0%–40.9%) | 15.0% (5.3%–31.8%) | 85.1% (74.4%–93.6%) | not met |

By stratum:

| Variant | Stratum | Key | Single read error | Archivist error | Catch rate |
|---|---|---|---|---|---|
| left_out/as_run | 1939_1942 | **official** | 19.7% (7.4%–34.0%) | 24.7% (0.0%–42.2%) | 36.4% (20.9%–100.0%) |
| left_out/as_run | 1939_1942 | corrected | 1.9% (0.0%–6.4%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) |
| left_out/as_run | total_claims | **official** | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |
| left_out/as_run | total_claims | corrected | 6.2% (3.3%–8.8%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) |
| left_out/failed_to_review | 1939_1942 | **official** | 19.7% (7.4%–34.0%) | 24.7% (0.0%–42.2%) | 36.4% (20.9%–100.0%) |
| left_out/failed_to_review | 1939_1942 | corrected | 1.9% (0.0%–6.4%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) |
| left_out/failed_to_review | total_claims | **official** | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |
| left_out/failed_to_review | total_claims | corrected | 6.2% (3.3%–8.8%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) |
| kept/as_run | 1939_1942 | **official** | 44.4% (33.1%–57.2%) | 42.7% (29.0%–61.0%) | 74.0% (59.8%–85.2%) |
| kept/as_run | 1939_1942 | corrected | 30.1% (17.1%–45.1%) | 19.2% (6.8%–43.3%) | 82.7% (70.7%–92.2%) |
| kept/as_run | total_claims | **official** | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |
| kept/as_run | total_claims | corrected | 6.2% (3.3%–8.8%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) |
| kept/failed_to_review | 1939_1942 | **official** | 44.4% (33.1%–57.2%) | 42.3% (28.3%–61.5%) | 75.4% (61.7%–86.2%) |
| kept/failed_to_review | 1939_1942 | corrected | 30.1% (17.1%–45.1%) | 17.8% (6.0%–41.2%) | 84.7% (74.1%–93.4%) |
| kept/failed_to_review | total_claims | **official** | 10.3% (6.2%–13.8%) | 4.5% (0.0%–11.9%) | 80.0% (50.0%–100.0%) |
| kept/failed_to_review | total_claims | corrected | 6.2% (3.3%–8.8%) | 0.0% (0.0%–0.0%) | 100.0% (100.0%–100.0%) |

Labels and outcomes (variant: official; corrected):

- left_out/as_run: {'right': 135, 'wrong': 22, 'cant_read': 5, 'abstained': 0}; {'right': 150, 'wrong': 7, 'cant_read': 5, 'abstained': 0}
- left_out/failed_to_review: {'right': 135, 'wrong': 22, 'cant_read': 5, 'abstained': 0}; {'right': 150, 'wrong': 7, 'cant_read': 5, 'abstained': 0}
- kept/as_run: {'right': 246, 'wrong': 126, 'cant_read': 19, 'abstained': 9}; {'right': 291, 'wrong': 81, 'cant_read': 19, 'abstained': 9}
- kept/failed_to_review: {'right': 246, 'wrong': 126, 'cant_read': 19, 'abstained': 9}; {'right': 291, 'wrong': 81, 'cant_read': 19, 'abstained': 9}

Corrected key with classified-page weights instead: left_out/as_run: single read 4.0% (1.9%–6.7%), Archivist 0.0% (0.0%–0.0%), R1 met; left_out/failed_to_review: single read 4.0% (1.9%–6.7%), Archivist 0.0% (0.0%–0.0%), R1 met; kept/as_run: single read 20.8% (12.5%–30.5%), Archivist 9.7% (3.8%–19.2%), R1 not met; kept/failed_to_review: single read 20.8% (12.5%–30.5%), Archivist 8.9% (3.4%–18.2%), R1 not met.
