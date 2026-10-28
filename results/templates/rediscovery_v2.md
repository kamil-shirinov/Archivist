# Rediscovery: can the drafter find the rules our built-in types check?

Made by `python -m archivist.templates.rediscover`. A measurement, reported whatever it shows; the second, after the template language gained a cell of the previous row. The drafter (Muse Spark 1.3, the `drafter` role of `config/templates.toml`) was given 3 synthetic val pages of each kind (val split, seed 2002; pages drawn with `random.Random(2002)`) and the same prompt as every family, which describes what the template language can express and never names a document type of ours nor a rule of theirs. Each draft then went through the arithmetic test (read, cite, blind second read; identities evaluated on cells whose two reads agree), with the template types' box strategy.

The first measurement, `results/templates/rediscovery.md` (dev split, seed 1001, before the previous row could be named), is kept as written; its drafts are judged again by the same matcher at the end.

Matching, changed after this measurement's card draft was seen: a drafted identity finds a known rule at the places where its equation is that rule, and the report says at how many of the places it applies. Before, it had to be that rule at every place, and an identity that is the running balance on every line and something else on one more row counted as missed. Both measurements are judged by the changed matcher.

Config: `{"drafter": {"backend": "meta", "model_id": "muse-spark-1.3-contributor"}, "extractor": {"backend": "meta", "model_id": "muse-spark-1.3-contributor"}, "rereader": {"backend": "meta", "model_id": "muse-spark-1.3-contributor"}}`

## Ledger cards: `rediscovery_cards`

Drafted from val/card-01-1, val/card-01-3, val/card-02-3: "Line Date Particulars Debit Credit Balance", 20 rows (fixed) x 6 columns, 1 identities kept at drafting. Files: `results/templates/rediscovery_v2/rediscovery_cards.yaml`, `results/templates/rediscovery_v2/rediscovery_cards.evidence.json`. Boxes: S0+ocr.


| Page | Classified as the draft | Read | Needed cells read twice | Agree |
|---|---|---|--:|--:|
| val/card-01-1 | yes | ok | 58 | 49 |
| val/card-01-3 | yes | ok | 58 | 51 |
| val/card-02-3 | yes | ok | 57 | 21 |

Known rules:

| Known rule | Expressible as a template identity | Found by |
|---|---|---|
| `running_balance`: each line's balance is the one before (the brought forward on line 1), less its debit, plus its credit | yes: for each row, with the balance of the previous row | `running_balance` (at 18 of 19 places) |
| `carried_forward`: the carried forward is the last line's balance | only for a full card: the last line used changes from card to card | missed |
| `one_side`: a line has a debit or a credit, not both or neither | no: not an equation | missed |
| `dates_ascend`: dates never go backwards down the card | no: an order, not an equation | missed |
| `cheques_ascend`: cheque numbers never go backwards down the card | no: an order, not an equation | missed |
| `carry_across_sheets`: the next sheet of the account brings forward what this one carried forward | no: across pages of one account, not tables of one issue | missed |
| `sequences_across_sheets`: dates and cheque numbers don't go backwards from one sheet to the next | no: an order across pages | missed |
| `account_and_holder`: an account's sheets share its number and holder, in sheet order | no: text across pages | missed |

Extra identities proposed (0):


How the identities that found a known rule fared in the test:

| Identity | Known rule | Test outcome | Held / evaluated | Not evaluated |
|---|---|---|--:|---|
| `running_balance` | `running_balance` (at 18 of 19 places) | sometimes fails | 22 / 23 | the two reads of a cell disagree (33); a cell was not read twice (1) |

## Payment memos: `rediscovery_memos`

Drafted from val/memo-0010, val/memo-0011, val/memo-0013: "Thistledown County Bank Payment Memorandum", 1 rows (read) x 8 columns, 0 identities kept at drafting. Files: `results/templates/rediscovery_v2/rediscovery_memos.yaml`, `results/templates/rediscovery_v2/rediscovery_memos.evidence.json`. Boxes: S0+ocr.


| Page | Classified as the draft | Read | Needed cells read twice | Agree |
|---|---|---|--:|--:|
| val/memo-0010 | yes | ok | 0 | 0 |
| val/memo-0011 | yes | ok | 0 | 0 |
| val/memo-0013 | yes | ok | 0 | 0 |

Known rules:

| Known rule | Expressible as a template identity | Found by |
|---|---|---|
| `words_figures`: the amount in words is the amount in figures | no: words are text, and only figures enter an identity | missed |
| `memo_amount_posted`: the ledger line the memo cites debits the memo's amount | no: across pages, found by the reference's sheet and line | missed |
| `memo_date_before_posting`: the memo is dated no later than its posting and at most 30 days before it | no: an order across pages | missed |
| `memo_account`: the memo's account is the cited card's account | no: text across pages | missed |

Extra identities proposed (0):


## Both measurements, judged by the same matcher

| Kind | Measurement | Identities kept | Known rules found | Extras |
|---|---|--:|---|--:|
| ledger card | first (dev, 1001) | 1 | none | 1 |
| ledger card | second (val, 2002) | 1 | `running_balance` | 0 |
| payment memo | first (dev, 1001) | 0 | none | 0 |
| payment memo | second (val, 2002) | 0 | none | 0 |
