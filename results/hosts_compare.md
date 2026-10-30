# Muse Spark Open on Baseten and on Fireworks

Muse Spark Open on Baseten and on Fireworks, single-pass extraction of the same development pages, same prompts, same effort, read live (scratch cache) and timed. 95% intervals are page-bootstrap.

| | baseten | fireworks |
| --- | --- | --- |
| pages read / asked | 16 / 16 | 16 / 16 |
| calls (failed) | 32 (0) | 32 (0) |
| retries (429, 5xx) | 0 | 0 |
| second asks (answer unusable) | 0 | 0 |
| closing-bracket repairs | 2 | 2 |
| call seconds, median / p90 / max | 7.044 / 12.403 / 13.752 | 4.262 / 32.763 / 39.513 |
| page seconds, median / p90 / max | 13.293 / 21.747 / 22.354 | 9.167 / 39.005 / 43.352 |
| wall seconds / pages a minute | 64.2 / 14.96 | 67.7 / 14.18 |
| tokens in / out | 104732 / 16511 | 104636 / 16801 |
| cost, total / per page | $0.2011 / $0.0126 | $0.2022 / $0.0126 |
| ledger read call seconds, median / max; tokens a second | 12.456 / 12.909; 198.1 | 34.828 / 39.513; 70.0 |
| memo read call seconds, median / max; tokens a second | 7.001 / 8.874; 64.4 | 6.383 / 8.946; 72.6 |
| field accuracy | 0.9849 | 0.9892 |

## Host against host
- 16 pages in both, 464 fields, 460 the same value = 0.9914 (95% 0.9750 to 0.9982)
- same and right 456, same and wrong 4
- differ 4: only the first right 1, only the second right 3, neither right 0

## Baseten against its own P13 reads (noise floor)
- 16 pages in both, 464 fields, 464 the same value = 1.0000 (95% 1.0000 to 1.0000)
- same and right 457, same and wrong 7
- differ 0: only the first right 0, only the second right 0, neither right 0

## Caveats
- Development data only: synthetic ledger cards and payment memos from data/dev, every third page. Nothing here was scored on the frozen test set or on a held-out real page.
- The two hosts are not known to serve the same checkpoint: Baseten's slug ends in -1026, Fireworks lists one id with no revision suffix.
- Hosts ran one after the other, not at the same time, so speed carries whatever load each had in its few minutes; four pages were read at once on each.
- Cost is tokens times the price in the config (both $1.25 input, $4.25 output per 1M, cached input billed as ordinary input), not either host's invoice.
- Cards and memos are pooled in the agreement figures; a card has 95 values and a memo about ten, so cards weigh most. 'by_doc_type' separates them.
