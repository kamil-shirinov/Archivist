# Open weights on the real scans — drawn cells not in Open's read, beside every rate

Reporting only (PREREGISTRATION_OPENW.md, Deviations): every rate below is copied from `score.json` (sha256 `a95582629c9e96ab07b5533c07edf117a8e8c535df4238b73273a154e7e19687`) as the frozen scorer wrote it. Beside each: how many of the drawn cells Open's read did not contain, of how many, and why. Such a cell gave no value, so it is outside the error rates; it is shown so that missing rows cannot make the rates look better.

**O1** (kept/as_run): not met, 27.1% (13.9%–49.9%); drawn cells not in Open's read: 62 of 400 (row_not_found 62).

| Variant | Measure | Version 1 | Open weights | Drawn cells not in Open's read |
|---|---|---|---|---|
| left_out/as_run | Wrong among accepted | 18.7% (1.6%–31.8%) | 13.6% (4.8%–30.7%) | 3 of 162 (row_not_found 3) |
| left_out/as_run | Single read error | 16.7% (8.2%–25.8%) | 16.4% (7.3%–27.7%) | 3 of 162 (row_not_found 3) |
| left_out/as_run | Wrong values caught | 44.9% (27.9%–94.4%) | 71.4% (59.9%–89.9%) | 3 of 162 (row_not_found 3) |
| left_out/as_run | Sent to a person | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) | 3 of 162 (row_not_found 3) |
| left_out/failed_to_review | Wrong among accepted | 18.7% (1.6%–31.8%) | 13.6% (4.8%–30.7%) | 3 of 162 (row_not_found 3) |
| left_out/failed_to_review | Single read error | 16.7% (8.2%–25.8%) | 16.4% (7.3%–27.7%) | 3 of 162 (row_not_found 3) |
| left_out/failed_to_review | Wrong values caught | 44.9% (27.9%–94.4%) | 71.4% (59.9%–89.9%) | 3 of 162 (row_not_found 3) |
| left_out/failed_to_review | Sent to a person | 50.0% (34.0%–73.6%) | 62.7% (41.3%–82.5%) | 3 of 162 (row_not_found 3) |
| kept/as_run | Wrong among accepted | 36.9% (24.7%–50.4%) | 27.1% (13.9%–49.9%) | 62 of 400 (row_not_found 62) |
| kept/as_run | Single read error | 41.1% (30.6%–52.4%) | 34.5% (22.1%–47.9%) | 62 of 400 (row_not_found 62) |
| kept/as_run | Wrong values caught | 74.2% (60.3%–84.9%) | 83.9% (73.1%–92.2%) | 62 of 400 (row_not_found 62) |
| kept/as_run | Sent to a person | 68.5% (57.9%–78.3%) | 60.0% (47.4%–72.6%) | 62 of 400 (row_not_found 62) |
| kept/failed_to_review | Wrong among accepted | 36.3% (24.5%–50.1%) | 27.1% (13.9%–49.9%) | 62 of 400 (row_not_found 62) |
| kept/failed_to_review | Single read error | 41.1% (30.6%–52.4%) | 34.5% (22.1%–47.9%) | 62 of 400 (row_not_found 62) |
| kept/failed_to_review | Wrong values caught | 75.5% (62.3%–85.8%) | 83.9% (73.1%–92.2%) | 62 of 400 (row_not_found 62) |
| kept/failed_to_review | Sent to a person | 69.5% (58.9%–79.5%) | 60.0% (47.4%–72.6%) | 62 of 400 (row_not_found 62) |

By stratum:

| Variant | Stratum | Measure | Version 1 | Open weights | Drawn cells not in Open's read |
|---|---|---|---|---|---|
| left_out/as_run | 1939_1942 | Wrong among accepted | 24.7% (0.0%–42.2%) | 15.6% (5.7%–39.4%) | 3 of 62 (row_not_found 3) |
| left_out/as_run | 1939_1942 | Single read error | 19.7% (7.4%–34.0%) | 16.9% (3.1%–33.5%) | 3 of 62 (row_not_found 3) |
| left_out/as_run | 1939_1942 | Wrong values caught | 36.4% (20.9%–100.0%) | 61.4% (33.6%–76.8%) | 3 of 62 (row_not_found 3) |
| left_out/as_run | 1939_1942 | Sent to a person | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) | 3 of 62 (row_not_found 3) |
| left_out/as_run | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) | 0 of 100 |
| left_out/as_run | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) | 0 of 100 |
| left_out/as_run | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) | 0 of 100 |
| left_out/as_run | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) | 0 of 100 |
| left_out/failed_to_review | 1939_1942 | Wrong among accepted | 24.7% (0.0%–42.2%) | 15.6% (5.7%–39.4%) | 3 of 62 (row_not_found 3) |
| left_out/failed_to_review | 1939_1942 | Single read error | 19.7% (7.4%–34.0%) | 16.9% (3.1%–33.5%) | 3 of 62 (row_not_found 3) |
| left_out/failed_to_review | 1939_1942 | Wrong values caught | 36.4% (20.9%–100.0%) | 61.4% (33.6%–76.8%) | 3 of 62 (row_not_found 3) |
| left_out/failed_to_review | 1939_1942 | Sent to a person | 47.6% (25.6%–86.4%) | 54.7% (27.0%–82.8%) | 3 of 62 (row_not_found 3) |
| left_out/failed_to_review | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) | 0 of 100 |
| left_out/failed_to_review | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) | 0 of 100 |
| left_out/failed_to_review | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) | 0 of 100 |
| left_out/failed_to_review | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) | 0 of 100 |
| kept/as_run | 1939_1942 | Wrong among accepted | 42.7% (29.0%–61.0%) | 30.0% (14.4%–57.6%) | 62 of 300 (row_not_found 62) |
| kept/as_run | 1939_1942 | Single read error | 44.4% (33.1%–57.2%) | 37.1% (23.3%–52.2%) | 62 of 300 (row_not_found 62) |
| kept/as_run | 1939_1942 | Wrong values caught | 74.0% (59.8%–85.2%) | 83.4% (71.2%–92.3%) | 62 of 300 (row_not_found 62) |
| kept/as_run | 1939_1942 | Sent to a person | 69.8% (58.7%–81.0%) | 58.1% (43.6%–71.4%) | 62 of 300 (row_not_found 62) |
| kept/as_run | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) | 0 of 100 |
| kept/as_run | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) | 0 of 100 |
| kept/as_run | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) | 0 of 100 |
| kept/as_run | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) | 0 of 100 |
| kept/failed_to_review | 1939_1942 | Wrong among accepted | 42.3% (28.3%–61.5%) | 30.0% (14.4%–57.6%) | 62 of 300 (row_not_found 62) |
| kept/failed_to_review | 1939_1942 | Single read error | 44.4% (33.1%–57.2%) | 37.1% (23.3%–52.2%) | 62 of 300 (row_not_found 62) |
| kept/failed_to_review | 1939_1942 | Wrong values caught | 75.4% (61.7%–86.2%) | 83.4% (71.2%–92.3%) | 62 of 300 (row_not_found 62) |
| kept/failed_to_review | 1939_1942 | Sent to a person | 70.9% (59.6%–82.5%) | 58.1% (43.6%–71.4%) | 62 of 300 (row_not_found 62) |
| kept/failed_to_review | total_claims | Wrong among accepted | 4.5% (0.0%–11.9%) | 5.3% (0.0%–18.8%) | 0 of 100 |
| kept/failed_to_review | total_claims | Single read error | 10.3% (6.2%–13.8%) | 15.5% (7.6%–25.8%) | 0 of 100 |
| kept/failed_to_review | total_claims | Wrong values caught | 80.0% (50.0%–100.0%) | 93.3% (71.4%–100.0%) | 0 of 100 |
| kept/failed_to_review | total_claims | Sent to a person | 55.0% (36.3%–72.2%) | 80.0% (63.8%–92.1%) | 0 of 100 |

With classified-page weights instead:

- left_out/as_run: wrong among accepted 11.9% (3.6%–25.7%); drawn cells not in Open's read: 3 of 162 (row_not_found 3)
- left_out/failed_to_review: wrong among accepted 11.9% (3.6%–25.7%); drawn cells not in Open's read: 3 of 162 (row_not_found 3)
- kept/as_run: wrong among accepted 20.9% (11.3%–36.5%); drawn cells not in Open's read: 62 of 400 (row_not_found 62)
- kept/failed_to_review: wrong among accepted 20.9% (11.3%–36.5%); drawn cells not in Open's read: 62 of 400 (row_not_found 62)
