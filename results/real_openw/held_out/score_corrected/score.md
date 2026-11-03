# Open weights on the real scans with the dash-corrected key, beside the official score

PREREGISTRATION_REAL.md and PREREGISTRATION_OPENW.md, Deviations, 2026-11-02. **The official score stands as scored** (`results/real_openw/held_out/score/`); it is shown first. The corrected key differs from the first-pass key only where the dash check found a dash printed in a cell first labelled blank; it is scored by `labelling/score_openw.py` and `labelling/score.py`'s own functions under unchanged rules.

Code: `run-real-openw` (1adee1f), checked frozen; scorer files (sha256): labelling/score_openw.py `84076c2ea11b`, labelling/score.py `82e56a8613e7`, labelling/score_corrected.py `ccf0f84ef199`. Intervals: 95%, page bootstrap within strata; Wilson for the relabel.

Files (sha256): `results/real_test/held_out/labels/draw.json` b575cc271445abc1621bfd942362c7b3db6e61b9e26ceca83648f0b580492168, `results/real_test/held_out/labels/labels.jsonl` 5f98f48235f3f4396594b11fe5ccd4d98b66c98629761efa330f80f3134de118, `results/real_test/held_out/labels/relabels.jsonl` 5861a0f5e8c1f543fef15a9f2966382beefb75dbd62ec12462dcb9c4ba24f2c0, `results/real_test/held_out/labels/dashes_checked.jsonl` 580fd0168f17f9596b84d110db4bcea826e70ed905e3c20212a1100d9a7d1f79, `results/real_test/held_out/score/score.json` 0c4d83bbee7ef00aa673dbb1d339778540fdd8605cb104a73c93d04822c898a0, `results/real_openw/held_out/score/score.json` a95582629c9e96ab07b5533c07edf117a8e8c535df4238b73273a154e7e19687, `results/real_openw/held_out/caps.json` f0d8879914f2b9154a2bf516b3e048980bce59ffa9b7a4fcc41f55cd9392f234, `results/real_openw/held_out/predictions.jsonl` 8a495e59b911e7cd06df6aacf5d72ddbcfd1af84cb3552d0154261fa37616f3d, `results/real_openw/held_out/boxes.jsonl` 58013fd0e35eeecf989294a8391cf6ce82b9fc995a72368b53a351ee0a0db0a9, `results/real_openw/held_out/cells.json` b05718c24b5c356a186fe55926517a325d1fc4e4c55a6a793335f35e3f3fb1ff, `results/real_openw/held_out/verdicts.jsonl` b52a9b86c4726513d86293f51c7639f98eca271c64e401874c1d5bda6c61803a, `results/real_openw/held_out/run.json` fd68a9e9c11da8aaeae7e19eef8cbfbf5feead03c48f9ce1053df750387a715d

## The key

First-pass blanks checked: 50 ({'1939_1942': 46, 'total_claims': 4}). Marks: dash printed 45, nothing printed 4, can't tell 1. Answers changed: 45 of 400 ({'1939_1942': 41, 'total_claims': 4}), each from blank to "-".

Relabel agreement: first pass key: 24 of 40 (44.6%–73.7%); corrected key: 29 of 40 (57.2%–83.9%). The plan's figure is the first-pass key's.

**O1** (official; below 1% wrong among accepted, kept/as_run): not met, 27.1% (13.9%–49.9%). In every variant: {'left_out/as_run': False, 'left_out/failed_to_review': False, 'kept/as_run': False, 'kept/failed_to_review': False}.

**O1** (corrected key; below 1% wrong among accepted, kept/as_run): not met, 12.5% (0.8%–36.1%). In every variant: {'left_out/as_run': True, 'left_out/failed_to_review': True, 'kept/as_run': False, 'kept/failed_to_review': False}.

O1 stands as scored; the corrected key's O1 is reported beside it and replaces nothing.

| Variant | Measure | Key | Version 1 (Muse Spark 1.3) | Open weights (Muse Spark Open) |
|---|---|---|---|---|
| left_out/as_run | Wrong among accepted | **official** | 18.7% (1.6%–31.8%) | 13.6% (4.8%–30.7%) |
| left_out/as_run | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 1.0% (0.0%–5.1%) |
| left_out/as_run | Single read error | **official** | 16.7% (8.2%–25.8%) | 16.4% (7.3%–27.7%) |
| left_out/as_run | Single read error | corrected | 3.2% (1.2%–6.5%) | 3.8% (1.3%–8.6%) |
| left_out/as_run | Wrong values caught | **official** | 44.9% (27.9%–94.4%) | 71.4% (59.9%–89.9%) |
| left_out/as_run | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | 90.9% (57.1%–100.0%) |
| left_out/as_run | Sent to a person | **official** | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) |
| left_out/as_run | Sent to a person | corrected | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) |
| left_out/failed_to_review | Wrong among accepted | **official** | 18.7% (1.6%–31.8%) | 13.6% (4.8%–30.7%) |
| left_out/failed_to_review | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 1.0% (0.0%–5.1%) |
| left_out/failed_to_review | Single read error | **official** | 16.7% (8.2%–25.8%) | 16.4% (7.3%–27.7%) |
| left_out/failed_to_review | Single read error | corrected | 3.2% (1.2%–6.5%) | 3.8% (1.3%–8.6%) |
| left_out/failed_to_review | Wrong values caught | **official** | 44.9% (27.9%–94.4%) | 71.4% (59.9%–89.9%) |
| left_out/failed_to_review | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | 90.9% (57.1%–100.0%) |
| left_out/failed_to_review | Sent to a person | **official** | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) |
| left_out/failed_to_review | Sent to a person | corrected | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) |
| kept/as_run | Wrong among accepted | **official** | 36.9% (24.7%–50.4%) | 27.1% (13.9%–49.9%) |
| kept/as_run | Wrong among accepted | corrected | 16.3% (6.1%–33.3%) | 12.5% (0.8%–36.1%) |
| kept/as_run | Single read error | **official** | 41.1% (30.6%–52.4%) | 34.5% (22.1%–47.9%) |
| kept/as_run | Single read error | corrected | 27.8% (16.0%–40.9%) | 21.9% (9.5%–36.9%) |
| kept/as_run | Wrong values caught | **official** | 74.2% (60.3%–84.9%) | 83.9% (73.1%–92.2%) |
| kept/as_run | Wrong values caught | corrected | 83.1% (71.1%–92.9%) | 88.3% (75.8%–98.9%) |
| kept/as_run | Sent to a person | **official** | 68.5% (57.9%–78.3%) | 60.0% (47.4%–72.6%) |
| kept/as_run | Sent to a person | corrected | 68.5% (57.9%–78.3%) | 60.0% (47.4%–72.6%) |
| kept/failed_to_review | Wrong among accepted | **official** | 36.3% (24.5%–50.1%) | 27.1% (13.9%–49.9%) |
| kept/failed_to_review | Wrong among accepted | corrected | 15.0% (5.3%–31.8%) | 12.5% (0.8%–36.1%) |
| kept/failed_to_review | Single read error | **official** | 41.1% (30.6%–52.4%) | 34.5% (22.1%–47.9%) |
| kept/failed_to_review | Single read error | corrected | 27.8% (16.0%–40.9%) | 21.9% (9.5%–36.9%) |
| kept/failed_to_review | Wrong values caught | **official** | 75.5% (62.3%–85.8%) | 83.9% (73.1%–92.2%) |
| kept/failed_to_review | Wrong values caught | corrected | 85.1% (74.4%–93.6%) | 88.3% (75.8%–98.9%) |
| kept/failed_to_review | Sent to a person | **official** | 69.5% (58.9%–79.5%) | 60.0% (47.4%–72.6%) |
| kept/failed_to_review | Sent to a person | corrected | 69.5% (58.9%–79.5%) | 60.0% (47.4%–72.6%) |

By stratum:

| Variant | Stratum | Measure | Key | Version 1 | Open weights |
|---|---|---|---|---|---|
| left_out/as_run | 1939_1942 | Wrong among accepted | **official** | 24.7% (0.0%–42.2%) | 15.6% (5.7%–39.4%) |
| left_out/as_run | 1939_1942 | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 0.0% (0.0%–0.0%) |
| left_out/as_run | 1939_1942 | Single read error | **official** | 19.7% (7.4%–34.0%) | 16.9% (3.1%–33.5%) |
| left_out/as_run | 1939_1942 | Single read error | corrected | 1.9% (0.0%–6.4%) | 0.0% (0.0%–0.0%) |
| left_out/as_run | 1939_1942 | Wrong values caught | **official** | 36.4% (20.9%–100.0%) | 61.4% (33.6%–76.8%) |
| left_out/as_run | 1939_1942 | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | — |
| left_out/as_run | 1939_1942 | Sent to a person | **official** | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) |
| left_out/as_run | 1939_1942 | Sent to a person | corrected | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) |
| left_out/as_run | total_claims | Wrong among accepted | **official** | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| left_out/as_run | total_claims | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 5.3% (0.0%–18.8%) |
| left_out/as_run | total_claims | Single read error | **official** | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| left_out/as_run | total_claims | Single read error | corrected | 6.2% (3.3%–8.8%) | 11.3% (3.9%–22.5%) |
| left_out/as_run | total_claims | Wrong values caught | **official** | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| left_out/as_run | total_claims | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | 90.9% (57.1%–100.0%) |
| left_out/as_run | total_claims | Sent to a person | **official** | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| left_out/as_run | total_claims | Sent to a person | corrected | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| left_out/failed_to_review | 1939_1942 | Wrong among accepted | **official** | 24.7% (0.0%–42.2%) | 15.6% (5.7%–39.4%) |
| left_out/failed_to_review | 1939_1942 | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 0.0% (0.0%–0.0%) |
| left_out/failed_to_review | 1939_1942 | Single read error | **official** | 19.7% (7.4%–34.0%) | 16.9% (3.1%–33.5%) |
| left_out/failed_to_review | 1939_1942 | Single read error | corrected | 1.9% (0.0%–6.4%) | 0.0% (0.0%–0.0%) |
| left_out/failed_to_review | 1939_1942 | Wrong values caught | **official** | 36.4% (20.9%–100.0%) | 61.4% (33.6%–76.8%) |
| left_out/failed_to_review | 1939_1942 | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | — |
| left_out/failed_to_review | 1939_1942 | Sent to a person | **official** | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) |
| left_out/failed_to_review | 1939_1942 | Sent to a person | corrected | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) |
| left_out/failed_to_review | total_claims | Wrong among accepted | **official** | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| left_out/failed_to_review | total_claims | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 5.3% (0.0%–18.8%) |
| left_out/failed_to_review | total_claims | Single read error | **official** | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| left_out/failed_to_review | total_claims | Single read error | corrected | 6.2% (3.3%–8.8%) | 11.3% (3.9%–22.5%) |
| left_out/failed_to_review | total_claims | Wrong values caught | **official** | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| left_out/failed_to_review | total_claims | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | 90.9% (57.1%–100.0%) |
| left_out/failed_to_review | total_claims | Sent to a person | **official** | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| left_out/failed_to_review | total_claims | Sent to a person | corrected | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| kept/as_run | 1939_1942 | Wrong among accepted | **official** | 42.7% (29.0%–61.0%) | 30.0% (14.4%–57.6%) |
| kept/as_run | 1939_1942 | Wrong among accepted | corrected | 19.2% (6.8%–43.3%) | 13.4% (0.0%–40.9%) |
| kept/as_run | 1939_1942 | Single read error | **official** | 44.4% (33.1%–57.2%) | 37.1% (23.3%–52.2%) |
| kept/as_run | 1939_1942 | Single read error | corrected | 30.1% (17.1%–45.1%) | 23.3% (8.9%–39.7%) |
| kept/as_run | 1939_1942 | Wrong values caught | **official** | 74.0% (59.8%–85.2%) | 83.4% (71.2%–92.3%) |
| kept/as_run | 1939_1942 | Wrong values caught | corrected | 82.7% (70.7%–92.2%) | 88.2% (73.7%–100.0%) |
| kept/as_run | 1939_1942 | Sent to a person | **official** | 69.8% (58.7%–81.0%) | 58.1% (43.6%–71.4%) |
| kept/as_run | 1939_1942 | Sent to a person | corrected | 69.8% (58.7%–81.0%) | 58.1% (43.6%–71.4%) |
| kept/as_run | total_claims | Wrong among accepted | **official** | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| kept/as_run | total_claims | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 5.3% (0.0%–18.8%) |
| kept/as_run | total_claims | Single read error | **official** | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| kept/as_run | total_claims | Single read error | corrected | 6.2% (3.3%–8.8%) | 11.3% (3.9%–22.5%) |
| kept/as_run | total_claims | Wrong values caught | **official** | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| kept/as_run | total_claims | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | 90.9% (57.1%–100.0%) |
| kept/as_run | total_claims | Sent to a person | **official** | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| kept/as_run | total_claims | Sent to a person | corrected | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| kept/failed_to_review | 1939_1942 | Wrong among accepted | **official** | 42.3% (28.3%–61.5%) | 30.0% (14.4%–57.6%) |
| kept/failed_to_review | 1939_1942 | Wrong among accepted | corrected | 17.8% (6.0%–41.2%) | 13.4% (0.0%–40.9%) |
| kept/failed_to_review | 1939_1942 | Single read error | **official** | 44.4% (33.1%–57.2%) | 37.1% (23.3%–52.2%) |
| kept/failed_to_review | 1939_1942 | Single read error | corrected | 30.1% (17.1%–45.1%) | 23.3% (8.9%–39.7%) |
| kept/failed_to_review | 1939_1942 | Wrong values caught | **official** | 75.4% (61.7%–86.2%) | 83.4% (71.2%–92.3%) |
| kept/failed_to_review | 1939_1942 | Wrong values caught | corrected | 84.7% (74.1%–93.4%) | 88.2% (73.7%–100.0%) |
| kept/failed_to_review | 1939_1942 | Sent to a person | **official** | 70.9% (59.6%–82.5%) | 58.1% (43.6%–71.4%) |
| kept/failed_to_review | 1939_1942 | Sent to a person | corrected | 70.9% (59.6%–82.5%) | 58.1% (43.6%–71.4%) |
| kept/failed_to_review | total_claims | Wrong among accepted | **official** | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| kept/failed_to_review | total_claims | Wrong among accepted | corrected | 0.0% (0.0%–0.0%) | 5.3% (0.0%–18.8%) |
| kept/failed_to_review | total_claims | Single read error | **official** | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| kept/failed_to_review | total_claims | Single read error | corrected | 6.2% (3.3%–8.8%) | 11.3% (3.9%–22.5%) |
| kept/failed_to_review | total_claims | Wrong values caught | **official** | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| kept/failed_to_review | total_claims | Wrong values caught | corrected | 100.0% (100.0%–100.0%) | 90.9% (57.1%–100.0%) |
| kept/failed_to_review | total_claims | Sent to a person | **official** | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| kept/failed_to_review | total_claims | Sent to a person | corrected | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |

Labels and outcomes (variant: open weights official; corrected):

- left_out/as_run: {'right': 129, 'wrong': 25, 'cant_read': 5, 'abstained': 3}; {'right': 143, 'wrong': 11, 'cant_read': 5, 'abstained': 3}
- left_out/failed_to_review: {'right': 129, 'wrong': 25, 'cant_read': 5, 'abstained': 3}; {'right': 143, 'wrong': 11, 'cant_read': 5, 'abstained': 3}
- kept/as_run: {'right': 225, 'wrong': 93, 'cant_read': 19, 'abstained': 63}; {'right': 261, 'wrong': 57, 'cant_read': 19, 'abstained': 63}
- kept/failed_to_review: {'right': 225, 'wrong': 93, 'cant_read': 19, 'abstained': 63}; {'right': 261, 'wrong': 57, 'cant_read': 19, 'abstained': 63}

Corrected key, open weights with classified-page weights instead: left_out/as_run: wrong among accepted 1.9% (0.0%–8.4%); left_out/failed_to_review: wrong among accepted 1.9% (0.0%–8.4%); kept/as_run: wrong among accepted 7.4% (1.2%–21.4%); kept/failed_to_review: wrong among accepted 7.4% (1.2%–21.4%).

Coverage (the same under both keys): how the 400 drawn cells were found in Open's read {'fixed_row': 100, 'label': 238, 'row_not_found': 62}; by stratum {'1939_1942': {'label': 238, 'row_not_found': 62}, 'total_claims': {'fixed_row': 100}}. A cell Open's read did not contain gives no value and is outside the error rates.
