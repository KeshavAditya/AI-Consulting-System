# Five hand-worked cases

All data is synthetic and authored for this repository. Review cutoff: **2026-09-30**, inclusive business date. Currency: USD. Data is declared complete for the five cases, with one deliberately later payment. There is no tax in these examples. Expected values are written independently of `scripts/validate_examples.py`; changing the implementation must not automatically change them.

These are public development fixtures, not evidence of model accuracy. The code verifies numerical expectations and evidence existence; it does **not** evaluate the semantic correctness of `must_say`/`must_not_say` statements.

| Project | Hours | Delivery cost | Pricing basis | Delivery margin | Eligible uninvoiced candidate | Outstanding at cutoff |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P01 healthy | 40 | 2200.00 | 4000.00 | 45.00% | 0.00 | 0.00 |
| P02 omitted work | 50 | 3000.00 | 6000.00 | 50.00% | 1200.00 | 0.00 |
| P03 external invoice | 30 | 2100.00 | 4500.00 | 53.33% | 0.00 | 0.00 |
| P04 fixed-fee overrun | 280 | 14000.00 | 20000.00 | 30.00% | Not applicable | 0.00 |
| P05 partial payment/credit | 50 | 4000.00 | 9000.00 | 55.56% | 0.00 | 5000.00 |

Pricing basis is defined in R04/R07/R13. It is neither recognized revenue nor cash. Delivery margin excludes overhead. The amounts in different columns cannot be summed as recoverable money.

## P01: correctly billed healthy hourly work

Five entries × 8 hours = 40. Labor: 40 × 50 = 2000. Direct infrastructure expense: 200. Total cost: 2200. Approved work: 40 × 100 = 4000. Margin: (4000 − 2200) / 4000 = 45%. Cost budget: 2200, so no cost variance. Invoice I01 is fully linked and paid. Correct result: no supported exception; do not manufacture a recommendation solely to fill a report.

## P02: approved hours omitted from billing

Five 8-hour entries plus two 5-hour entries = 50. Cost: 50 × 60 = 3000. Approved priced work: 50 × 120 = 6000. I02 covers only the first 40 hours: 4800. Remaining 10 × 120 = **1200 eligible uninvoiced candidate**. Existing I02 is already paid, so outstanding receivables are zero. Margin on approved pricing basis: (6000 − 3000) / 6000 = 50%, conditional on that pricing basis, not a claim of realized profit.

The agreement and review note explicitly rule out another invoice, cap, or write-off in this example. Ask the responsible manager to review the omitted entries before billing. Do not say 1200 has been collected or is already overdue. E02's later 90/hour cost rate starts October 1 and must not change September's cost.

## P03: external invoice with stale time flags

Five 6-hour entries = 30. Cost: 30 × 70 = 2100. Price: 30 × 150 = 4500. Every source invoiced flag is false, but the fictional bookkeeper explicitly links all entries to external invoice EXT-303/I03. It is paid. Candidate amount: zero. Margin: 2400 / 4500 = 53.33%. Correct action: reconcile the time system's flags; **do not invoice again**. Without those reviewed links/notes, the appropriate result would be an unresolved match question.

## P04: fixed-fee cost overrun, cause unresolved

Two people × 20 working days × 7 hours = 280 hours. Cost: 280 × 50 = 14000. Agreed budget: 200 hours / 10000. Overrun: 80 hours and 4000. Fee: 20000. Planned margin: (20000 − 10000) / 20000 = 50%; actual delivery margin: 6000 / 20000 = 30%, a **20 percentage-point** decline. Both fee installments are invoiced and paid.

Later task notes mention revisions, but no approved change order establishes extra fees or their cause. Correct action: examine whether revisions were corrections, included work, or new requests; use the result to improve future estimating/change approval. Do not label all 4000 as recoverable fees or assert scope creep as proven.

## P05: overdue residual after payment and price credit

Six 8-hour entries plus one 2-hour entry = 50. Cost: 50 × 80 = 4000. Original approved price/invoice: 50 × 200 = 10000. CR01 reduces the pre-tax pricing basis to 9000; margin: (9000 − 4000) / 9000 = 55.56%.

At September 30, balance = 10000 − 4000 received/applied September 20 − 1000 credited/applied September 25 = **5000**. Due date September 15 gives **15 days overdue**. October 2's 5000 payment is excluded. At October 2, with the same otherwise unchanged snapshot, balance becomes zero. Credit is not cash; cash allocated at September cutoff is only 4000.

## Review guide

Inspect `manifest.json` assumptions first, then CSVs and agreements, then the hand calculations above. `expected.json` holds the machine comparison values and qualitative review rubric. Validate reference existence independently from whether the passage actually supports the claim. All reviewer/model evaluation records must distinguish arithmetic correctness, evidence correctness, and action suitability.
