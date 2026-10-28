# Rediscovery: can the drafter find the rules our built-in types check?

Made by `python -m archivist.templates.rediscover`. A measurement, reported whatever it shows. The drafter (Muse Spark 1.3, the `drafter` role of `config/templates.toml`) was given 3 synthetic dev pages of each kind (dev split, seed 1001; pages drawn with `random.Random(1001)`) and the same prompt as every family: it never names a document type of ours. Each draft then went through the arithmetic test (read, cite, blind second read; identities evaluated on cells whose two reads agree).

Config: `{"drafter": {"backend": "meta", "model_id": "muse-spark-1.3-contributor"}, "extractor": {"backend": "meta", "model_id": "muse-spark-1.3-contributor"}, "rereader": {"backend": "meta", "model_id": "muse-spark-1.3-contributor"}}`

## Ledger cards: `rediscovery_cards`

Drafted from dev/card-01-1, dev/card-01-2, dev/card-02-1: "Line Date Particulars Debit Credit Balance", 20 rows (read) x 6 columns, 1 identities kept at drafting. Files: `results/templates/rediscovery/rediscovery_cards.yaml`, `results/templates/rediscovery/rediscovery_cards.evidence.json`.


| Page | Classified as the draft | Read | Needed cells read twice | Agree |
|---|---|---|--:|--:|
| dev/card-01-1 | yes | ok | 38 | 33 |
| dev/card-01-2 | yes | ok | 38 | 8 |
| dev/card-02-1 | yes | ok | 38 | 37 |

Known rules:

| Known rule | Expressible as a template identity | Found by |
|---|---|---|
| `running_balance`: each line's balance is the one before (the brought forward on line 1), less its debit, plus its credit | yes, line by line: an identity per line, since an identity can't name the row before | missed |
| `carried_forward`: the carried forward is the last line's balance | only for a full card: the last line used changes from card to card | missed |
| `one_side`: a line has a debit or a credit, not both or neither | no: not an equation | missed |
| `dates_ascend`: dates never go backwards down the card | no: an order, not an equation | missed |
| `cheques_ascend`: cheque numbers never go backwards down the card | no: an order, not an equation | missed |
| `carry_across_sheets`: the next sheet of the account brings forward what this one carried forward | no: across pages of one account, not tables of one issue | missed |
| `sequences_across_sheets`: dates and cheque numbers don't go backwards from one sheet to the next | no: an order across pages | missed |
| `account_and_holder`: an account's sheets share its number and holder, in sheet order | no: text across pages | missed |

Extra identities proposed (1):

| Identity | Equation | Test outcome | Held / evaluated | Not evaluated |
|---|---|---|--:|---|
| `running_balance_total`: Carried forward balance minus Brought forward balance equals sum of Credits minus sum of Debits | `20/balance − 01/balance = 02 + 03 + 04 + 05 + 06 + 07 + 08 + 09 + 10 + 11 + 12 + 13 + 14 + 15 + 16 + 17 + 18 + 19 − (02 + 03 + 04 + 05 + 06 + 07 + 08 + 09 + 10 + 11 + 12 + 13 + 14 + 15 + 16 + 17 + 18 + 19)` (for each table) | untested | 0 / 0 | the two reads of a cell disagree (3) |

## Payment memos: `rediscovery_memos`

Drafted from dev/memo-0011, dev/memo-0025, dev/memo-0027: "Payment Memorandum", 8 rows (fixed) x 2 columns, 0 identities kept at drafting. Files: `results/templates/rediscovery/rediscovery_memos.yaml`, `results/templates/rediscovery/rediscovery_memos.evidence.json`.


| Page | Classified as the draft | Read | Needed cells read twice | Agree |
|---|---|---|--:|--:|
| dev/memo-0011 | yes | ok | 0 | 0 |
| dev/memo-0025 | yes | ok | 0 | 0 |
| dev/memo-0027 | yes | ok | 0 | 0 |

Known rules:

| Known rule | Expressible as a template identity | Found by |
|---|---|---|
| `words_figures`: the amount in words is the amount in figures | no: words are text, and only figures enter an identity | missed |
| `memo_amount_posted`: the ledger line the memo cites debits the memo's amount | no: across pages, found by the reference's sheet and line | missed |
| `memo_date_before_posting`: the memo is dated no later than its posting and at most 30 days before it | no: an order across pages | missed |
| `memo_account`: the memo's account is the cited card's account | no: text across pages | missed |

Extra identities proposed (0):
