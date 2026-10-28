# Recount: an all-blank instance proves nothing (P26)

An identity instance whose cells are all blanks counted as zero reads 0 = 0, which holds whatever the table says. Until P26 the arithmetic test counted it as held; it is now not evaluated, "all blank". Every family's committed evidence (as at 2364d02, the approved ones included) is recounted here from its reads, replayed from the cache with both spend caps at zero, through the template it was tested on. No evidence file is rewritten: an approval is tied to its evidence file's sha256. Written by `python -m archivist.templates.recount`.

Each family is replayed twice. **The all-blank rule** reads figures as before P26, so the rule is the only change; its pages must replay exactly as committed, and a count is *explained* when the held count fell by exactly the instances now all blank and nothing else changed. **All of P26** also reads a space after a thousands comma ("29, 139") as one figure, so more first and second reads agree; *spaced reads* is how many first or second reads printed such a space. Counts are held / failed / evaluated.

## Families

| family | status | tested template | columns where a blank is zero | replayed as committed | instances now all blank | changed by the rule | spaced reads | changed further by reading them |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| occ_abstract_by_states | draft | the file at 2364d02 | 4 | all pages | 0 | 0 of 3 | 20 | 0 of 3 |
| occ_aggregate_resources_liabilities | draft | the file at 2364d02 | 6 | **not** 1905_p395 | 2 | 1 of 1 | 34 | 0 of 1 |
| occ_banks_in_charge_of_receivers | draft | the file at 2364d02 | 0 | all pages | 0 | 0 of 0 | 0 | 0 of 0 |
| occ_earnings_and_dividends | draft | the file at 2364d02 | 11 | all pages | 0 | 0 of 3 | 174 | 3 of 3 |
| outstanding_forward_exchange_contracts | approved | the file at 7af55d2, its approval undone | 13 | all pages | 0 | 0 of 4 | 36 | 3 of 4 |
| receipts_and_expenditures_under_railroad | approved | the file at 5fb55f2, its approval undone | 5 | all pages | 0 | 0 of 1 | 0 | 0 of 1 |
| security_transactions_as_reported_by | approved | the file at 06cf220 | 0 | all pages | 0 | 0 of 2 | 20 | 1 of 2 |
| short_term_foreign_liabilities_as | approved | the file at 06cf220 | 0 | all pages | 0 | 0 of 2 | 47 | 2 of 2 |
| total_claims_by_country | approved | the file at 06cf220 | 0 | a read is not in the cache: meta cap $0.00: $4.3029 spent + $0.0000 in flight + $0.0006 projected; no column counts a blank as zero, so no instance can be all blank | | | | |
| total_liabilities_by_type_payable_in | draft | the file at 342835e | 0 | all pages | 0 | 0 of 1 | 0 | 0 of 1 |

## The all-blank rule: every count that changed

| family | identity | accepted | applies | held / failed / evaluated | not evaluated | outcome | explained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| occ_aggregate_resources_liabilities | total_equals_sum | draft | 18 | 2 / 0 / 2 -> 0 / 0 / 0 | reads disagree 9 -> 8, not read twice 7 -> 8, all blank 0 -> 2 | holds -> untested | yes; the rest moved on 1905_p395, whose first reads are all blank |

Pages not replayed as committed under the all-blank rule:

- occ_aggregate_resources_liabilities, 1905_p395: 186 of its 186 re-read cells ask the very request another cell asks (the same crop with the same prompt). Before P26 identical requests made at once were each answered by the model while the cache kept one answer, so the committed reads of these cells need not be the cached ones; P26 answers them with one call (models/cache.py). Every first read on the page is blank.

## Accepted identities left with no genuine pass

None among the 9 accepted identities of the 4 approved families recounted: each still holds at least once under the all-blank rule, and under all of P26.

total_claims_by_country could not be recounted (a read is not in the cache: meta cap $0.00: $4.3029 spent + $0.0000 in flight + $0.0006 projected), but no column of the template it was tested on counts a blank as zero, so none of the passes of its 8 accepted identities can have been all blank.

## Reading spaced figures: every count that changed further

| family | identity | accepted | held / failed / evaluated | not evaluated | outcome |
| --- | --- | --- | --- | --- | --- |
| occ_earnings_and_dividends | total_net_earnings | draft | 2 / 0 / 2 -> 3 / 0 / 3 | reads disagree 27 -> 26 | holds |
| occ_earnings_and_dividends | total_losses | draft | 0 / 0 / 0 -> 1 / 0 / 1 | reads disagree 29 -> 28 | untested -> holds |
| occ_earnings_and_dividends | net_addition | draft | 2 / 0 / 2 -> 6 / 0 / 6 | reads disagree 25 -> 23, blank 2 -> 0 | holds |
| outstanding_forward_exchange_contracts | grand_total | yes | 1 / 0 / 1 -> 2 / 0 / 2 | reads disagree 77 -> 76 | holds |
| outstanding_forward_exchange_contracts | total_purchase_breakdown | yes | 30 / 0 / 30 -> 34 / 0 / 34 | reads disagree 138 -> 134 | holds |
| outstanding_forward_exchange_contracts | total_sale_breakdown | yes | 32 / 0 / 32 -> 33 / 0 / 33 | reads disagree 137 -> 136 | holds |
| security_transactions_as_reported_by | grand_total | yes | 16 / 0 / 16 -> 20 / 0 / 20 | reads disagree 148 -> 144 | holds |
| short_term_foreign_liabilities_as | total_europe | yes | 6 / 0 / 6 -> 10 / 0 / 10 | reads disagree 125 -> 121 | holds |
| short_term_foreign_liabilities_as | grand_total | yes | 19 / 0 / 19 -> 24 / 0 / 24 | reads disagree 113 -> 108 | holds |

## Every identity

| family | identity | committed | the all-blank rule | all blank | all of P26 |
| --- | --- | --- | --- | --- | --- |
| occ_abstract_by_states | resources_total | 0 / 0 / 0, untested | 0 / 0 / 0, untested | 0 | 0 / 0 / 0, untested |
| occ_abstract_by_states | liabilities_total | 0 / 0 / 0, untested | 0 / 0 / 0, untested | 0 | 0 / 0 / 0, untested |
| occ_abstract_by_states | total_balance | 0 / 0 / 0, untested | 0 / 0 / 0, untested | 0 | 0 / 0 / 0, untested |
| occ_aggregate_resources_liabilities | total_equals_sum | 2 / 0 / 2, holds | 0 / 0 / 0, untested | 2 | 0 / 0 / 0, untested |
| occ_earnings_and_dividends | total_net_earnings | 2 / 0 / 2, holds | 2 / 0 / 2, holds | 0 | 3 / 0 / 3, holds |
| occ_earnings_and_dividends | total_losses | 0 / 0 / 0, untested | 0 / 0 / 0, untested | 0 | 1 / 0 / 1, holds |
| occ_earnings_and_dividends | net_addition | 2 / 0 / 2, holds | 2 / 0 / 2, holds | 0 | 6 / 0 / 6, holds |
| outstanding_forward_exchange_contracts | total_europe | 1 / 0 / 1, holds | 1 / 0 / 1, holds | 0 | 1 / 0 / 1, holds |
| outstanding_forward_exchange_contracts | grand_total | 1 / 0 / 1, holds | 1 / 0 / 1, holds | 0 | 2 / 0 / 2, holds |
| outstanding_forward_exchange_contracts | total_purchase_breakdown | 30 / 0 / 30, holds | 30 / 0 / 30, holds | 0 | 34 / 0 / 34, holds |
| outstanding_forward_exchange_contracts | total_sale_breakdown | 32 / 0 / 32, holds | 32 / 0 / 32, holds | 0 | 33 / 0 / 33, holds |
| receipts_and_expenditures_under_railroad | total_expenditures | 2 / 0 / 2, holds | 2 / 0 / 2, holds | 0 | 2 / 0 / 2, holds |
| security_transactions_as_reported_by | total_europe | 18 / 0 / 18, holds | 18 / 0 / 18, holds | 0 | 18 / 0 / 18, holds |
| security_transactions_as_reported_by | grand_total | 16 / 0 / 16, holds | 16 / 0 / 16, holds | 0 | 20 / 0 / 20, holds |
| short_term_foreign_liabilities_as | total_europe | 6 / 0 / 6, holds | 6 / 0 / 6, holds | 0 | 10 / 0 / 10, holds |
| short_term_foreign_liabilities_as | grand_total | 19 / 0 / 19, holds | 19 / 0 / 19, holds | 0 | 24 / 0 / 24, holds |
| total_liabilities_by_type_payable_in | total_equals_components | 0 / 0 / 0, untested | 0 / 0 / 0, untested | 0 | 0 / 0 / 0, untested |
