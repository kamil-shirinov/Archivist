# Open weights on the real scans — scoring (PREREGISTRATION_OPENW.md)

Code: `run-real-openw` (1adee1f), checked frozen; scorer sha256 `84076c2ea11b`, rules (labelling/score.py) sha256 `82e56a8613e7`. The same 400 drawn cells and labels for both; intervals 95%, page bootstrap within strata.

Files (sha256): `draw.json` b575cc271445abc1621bfd942362c7b3db6e61b9e26ceca83648f0b580492168, `layouts_checked.jsonl` e275a7aedbe8fde7a396b3c5ad3a1caa3db8a23ef7946a243b5767d81d0f9bdd, `labels.jsonl` 5f98f48235f3f4396594b11fe5ccd4d98b66c98629761efa330f80f3134de118, `pages_checked.jsonl` d511c97a98be9380d60acf027656190fcb80d84ad182f7e3bfbb987ee84455b2, `results/real_test/held_out/score/score.json` 0c4d83bbee7ef00aa673dbb1d339778540fdd8605cb104a73c93d04822c898a0, `results/real_openw/held_out/caps.json` f0d8879914f2b9154a2bf516b3e048980bce59ffa9b7a4fcc41f55cd9392f234, `results/real_openw/held_out/predictions.jsonl` 8a495e59b911e7cd06df6aacf5d72ddbcfd1af84cb3552d0154261fa37616f3d, `results/real_openw/held_out/boxes.jsonl` 58013fd0e35eeecf989294a8391cf6ce82b9fc995a72368b53a351ee0a0db0a9, `results/real_openw/held_out/cells.json` b05718c24b5c356a186fe55926517a325d1fc4e4c55a6a793335f35e3f3fb1ff, `results/real_openw/held_out/verdicts.jsonl` b52a9b86c4726513d86293f51c7639f98eca271c64e401874c1d5bda6c61803a, `results/real_openw/held_out/run.json` fd68a9e9c11da8aaeae7e19eef8cbfbf5feead03c48f9ce1053df750387a715d

**O1** (below 1% wrong among accepted, kept/as_run): not met, 27.1% (13.9%–49.9%). In every variant: {'left_out/as_run': False, 'left_out/failed_to_review': False, 'kept/as_run': False, 'kept/failed_to_review': False}.

| Variant | Measure | Version 1 (Muse Spark 1.3) | Open weights (Muse Spark Open) |
|---|---|---|---|
| left_out/as_run | Wrong among accepted | 18.7% (1.6%–31.8%) | 13.6% (4.8%–30.7%) |
| left_out/as_run | Single read error | 16.7% (8.2%–25.8%) | 16.4% (7.3%–27.7%) |
| left_out/as_run | Wrong values caught | 44.9% (27.9%–94.4%) | 71.4% (59.9%–89.9%) |
| left_out/as_run | Sent to a person | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) |
| left_out/failed_to_review | Wrong among accepted | 18.7% (1.6%–31.8%) | 13.6% (4.8%–30.7%) |
| left_out/failed_to_review | Single read error | 16.7% (8.2%–25.8%) | 16.4% (7.3%–27.7%) |
| left_out/failed_to_review | Wrong values caught | 44.9% (27.9%–94.4%) | 71.4% (59.9%–89.9%) |
| left_out/failed_to_review | Sent to a person | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) |
| kept/as_run | Wrong among accepted | 36.9% (24.7%–50.4%) | 27.1% (13.9%–49.9%) |
| kept/as_run | Single read error | 41.1% (30.6%–52.4%) | 34.5% (22.1%–47.9%) |
| kept/as_run | Wrong values caught | 74.2% (60.3%–84.9%) | 83.9% (73.1%–92.2%) |
| kept/as_run | Sent to a person | 68.5% (57.9%–78.3%) | 60.0% (47.4%–72.6%) |
| kept/failed_to_review | Wrong among accepted | 36.3% (24.5%–50.1%) | 27.1% (13.9%–49.9%) |
| kept/failed_to_review | Single read error | 41.1% (30.6%–52.4%) | 34.5% (22.1%–47.9%) |
| kept/failed_to_review | Wrong values caught | 75.5% (62.3%–85.8%) | 83.9% (73.1%–92.2%) |
| kept/failed_to_review | Sent to a person | 69.5% (58.9%–79.5%) | 60.0% (47.4%–72.6%) |

By stratum:

| Variant | Stratum | Measure | Version 1 | Open weights |
|---|---|---|---|---|
| left_out/as_run | 1939_1942 | Wrong among accepted | 24.7% (0.0%–42.2%) | 15.6% (5.7%–39.4%) |
| left_out/as_run | 1939_1942 | Single read error | 19.7% (7.4%–34.0%) | 16.9% (3.1%–33.5%) |
| left_out/as_run | 1939_1942 | Wrong values caught | 36.4% (20.9%–100.0%) | 61.4% (33.6%–76.8%) |
| left_out/as_run | 1939_1942 | Sent to a person | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) |
| left_out/as_run | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| left_out/as_run | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| left_out/as_run | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| left_out/as_run | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| left_out/failed_to_review | 1939_1942 | Wrong among accepted | 24.7% (0.0%–42.2%) | 15.6% (5.7%–39.4%) |
| left_out/failed_to_review | 1939_1942 | Single read error | 19.7% (7.4%–34.0%) | 16.9% (3.1%–33.5%) |
| left_out/failed_to_review | 1939_1942 | Wrong values caught | 36.4% (20.9%–100.0%) | 61.4% (33.6%–76.8%) |
| left_out/failed_to_review | 1939_1942 | Sent to a person | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) |
| left_out/failed_to_review | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| left_out/failed_to_review | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| left_out/failed_to_review | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| left_out/failed_to_review | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| kept/as_run | 1939_1942 | Wrong among accepted | 42.7% (29.0%–61.0%) | 30.0% (14.4%–57.6%) |
| kept/as_run | 1939_1942 | Single read error | 44.4% (33.1%–57.2%) | 37.1% (23.3%–52.2%) |
| kept/as_run | 1939_1942 | Wrong values caught | 74.0% (59.8%–85.2%) | 83.4% (71.2%–92.3%) |
| kept/as_run | 1939_1942 | Sent to a person | 69.8% (58.7%–81.0%) | 58.1% (43.6%–71.4%) |
| kept/as_run | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| kept/as_run | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| kept/as_run | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| kept/as_run | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |
| kept/failed_to_review | 1939_1942 | Wrong among accepted | 42.3% (28.3%–61.5%) | 30.0% (14.4%–57.6%) |
| kept/failed_to_review | 1939_1942 | Single read error | 44.4% (33.1%–57.2%) | 37.1% (23.3%–52.2%) |
| kept/failed_to_review | 1939_1942 | Wrong values caught | 75.4% (61.7%–86.2%) | 83.4% (71.2%–92.3%) |
| kept/failed_to_review | 1939_1942 | Sent to a person | 70.9% (59.6%–82.5%) | 58.1% (43.6%–71.4%) |
| kept/failed_to_review | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) |
| kept/failed_to_review | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) |
| kept/failed_to_review | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) |
| kept/failed_to_review | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) |

Labels and outcomes (variant: by outcome, version 1; open weights):

- left_out/as_run: {'right': 135, 'wrong': 22, 'cant_read': 5, 'abstained': 0}; {'right': 129, 'wrong': 25, 'cant_read': 5, 'abstained': 3}
- left_out/failed_to_review: {'right': 135, 'wrong': 22, 'cant_read': 5, 'abstained': 0}; {'right': 129, 'wrong': 25, 'cant_read': 5, 'abstained': 3}
- kept/as_run: {'right': 246, 'wrong': 126, 'cant_read': 19, 'abstained': 9}; {'right': 225, 'wrong': 93, 'cant_read': 19, 'abstained': 63}
- kept/failed_to_review: {'right': 246, 'wrong': 126, 'cant_read': 19, 'abstained': 9}; {'right': 225, 'wrong': 93, 'cant_read': 19, 'abstained': 63}

Open weights with classified-page weights instead: left_out/as_run: wrong among accepted 11.9% (3.6%–25.7%); left_out/failed_to_review: wrong among accepted 11.9% (3.6%–25.7%); kept/as_run: wrong among accepted 20.9% (11.3%–36.5%); kept/failed_to_review: wrong among accepted 20.9% (11.3%–36.5%).

## How the drawn cells were found in Open's read

{'fixed_row': 100, 'label': 238, 'row_not_found': 62}; by stratum {'1939_1942': {'label': 238, 'row_not_found': 62}, 'total_claims': {'fixed_row': 100}}; 258 at the drawn cell's own position; statuses {'abstained': 6, 'accepted': 70, 'no_value': 62, 'review': 262}. Box sources of the cells found: {'table:ink': 6, 'table:ocr': 33, 'v1:grid': 46, 'v1:model': 218, 'v1:ocr': 35}. Re-reads asked again: {'cells': 0, 'drawn': 0}.

## The run

`{"pages_read": 58, "failed": [], "page_tries": {}, "order_guard": {"pages": 2, "cells_reread": 40, "used": 1}, "verification_pass": 1, "cost_usd": {"meta": 0.0, "baseten": 6.737917, "fireworks": 0.0, "modal_glimmer_sorter": 0.0}, "cost_full_usd": 0.9740600000000006, "started_at": "2026-11-02T09:34:16+00:00", "finished_at": "2026-11-02T09:41:53+00:00"}`; stalled: False.
