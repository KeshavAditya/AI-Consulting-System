# Business rules v0.1

These rules define management review semantics for the proposed product. They are not universal accounting standards. Source IDs refer to [research.md](research.md). `Implemented` below refers to the shared calculation library exercised by the synthetic verifier and experimental local reporting CLI, not a deployed service.

## Arithmetic and eligibility

| Rule | Definition | Source or rationale | Foundation coverage |
| --- | --- | --- | --- |
| R01 | A review has a currency, as-of date, and source coverage. Apply event dates before aggregation. | Project decision: reproducible snapshots. | Cutoff arithmetic implemented; importer completeness attestation deferred. |
| R02 | Labor cost = sum of each entry's recorded hours × effective hourly cost, rounded to cents per entry. All recorded work costs money, including nonbillable work. | S09, S14; our rounding choice. | Implemented; missing/overlapping rates reject the fixture. |
| R03 | Delivery cost = labor cost + direct project expenses, without counting contractor labor both ways. | Project cost model. | Sum implemented; detecting a real duplicate contractor bill is deferred. |
| R04 | Hourly priced work = approved billable billing-hours × confirmed rates. Unapproved/nonbillable work is excluded from priced work, not from cost. | S06, S08; confirmed terms requirement is our policy. | Implemented on normalized records. |
| R05 | Confirmed invoice links override a stale billed flag. Link coverage is quantitative; a flag alone never proves which work was billed. | S06–S07. | Implemented; links in examples are supplied as reviewed evidence. |
| R06 | Eligible uninvoiced hourly work = eligible priced work minus confirmed covered work. Unknown coverage is a reconciliation question, not an instruction to invoice. | Project decision from S06–S07. | Candidate arithmetic and conservative report actions implemented; source completeness remains a supplied assertion. |
| R07 | Extra hours on fixed-fee work indicate cost variance, not automatically extra billable revenue. Changes need agreement/approval evidence. | S01, S08. | Fixed fee used as pricing basis; text interpretation deferred. |
| R08 | Invoice balance = issued invoice total minus valid payment allocations minus valid credit allocations at cutoff. | S10 and allocation model. | Implemented; overallocations reject the bundle. |
| R09 | Days overdue = max(0, cutoff − due date), only for a positive balance on an issued invoice. Due today = 0. | Project date convention. | Implemented. |
| R10 | Draft/void invoices do not establish billed coverage or receivables. Disputed balances may exist but must not receive an unconditional collection recommendation. | Project review policy. | Draft/void excluded; dispute branch specified, not exercised in five fixtures. |
| R11 | Cash received is not revenue or profit. Applying a credit is not collecting cash. Unallocated customer funds cannot be automatically assigned to a project. | S10; conservative allocation policy. | Separate invoice balances and allocated cash implemented. |
| R12 | Project delivery margin = (named pricing basis − direct delivery cost) / pricing basis. Excludes overhead; zero basis means undefined percentage. | Project management metric, not reported net profit. | Implemented; zero basis returns null. |
| R13 | Known credits reducing this project's price reduce its net pricing basis. Settlement allocation is separate from price attribution. | Project decision informed by S10. | Explicit credit project ID and pre-tax amount used. Unknown price attribution deferred. |
| R14 | Blank/unknown is not zero. Mixed currencies, bad links, duplicates, malformed numbers, and inconsistent totals block affected calculations. | S11, S14; data integrity. | Strict fixture checks implemented; partial production results deferred. |
| R15 | An overrun is a fact; scope creep, estimation error, and rework are possible causes requiring evidence. | Evidence discipline. | Report actions ask for evidence; no causal inference engine. |
| R16 | Keep immutable facts/calculations separate from model proposals and user dispositions. External document text is data, never tool authority. | S15. | Architectural requirement; no model/tool execution in this PR. |

## Exact conventions for the fixtures

- Decimal strings only; money has two fractional digits, hours/rates have up to four. Finite, unsigned, plain decimal notation; never binary floats or exponent notation.
- `ROUND_HALF_UP` at each money calculation. Preserve supplied invoice totals; a future importer must report a rounding-policy mismatch, not silently rewrite records to match our formula.
- For partially covered hourly entries, candidate value is rounded full entry value minus rounded total covered value. Do not round the remainder independently and create an extra cent. Any source allocation/rounding discrepancy needs reconciliation rather than automatic correction.
- Recorded hours drive cost; `billing_hours` drive hourly pricing and invoice coverage. They can differ because of a documented billing rounding policy. Fixtures happen to use equal values. An adapter may need distinct vendor cost-rounding semantics.
- Rate intervals use `[valid_from, valid_to)`; blank end date is open-ended. Exactly one rate must cover a worked date. Historic records do not use today's rate.
- Approved hourly work requires an approval date no later than cutoff, a billable flag, and a rate. Approval means the agency's billing review accepted it; it does not by itself prove client contractual approval.
- The fixed-fee pricing basis is the agreed fee, less explicitly project-attributed pre-tax credits; the hourly basis is approved priced work, less such credits. Label both as **delivery margin on pricing basis**, never recognized revenue or cash profit.
- Invoice totals and settlement allocations include supplied tax. Price/margin uses pre-tax values. Tax is not computed. Unsupported credit attribution or tax decomposition blocks margin while a known gross balance can still be shown.
- Payment contribution requires receipt and allocation dates on/before cutoff. Credit contribution requires issue and allocation dates. Reversals/refunds require a future signed-event ledger; positive-only fixture tables must reject, not approximate, those events.
- Unallocated amounts remain customer-level balances. A credit is subtracted once for price impact and once in its separate receivable calculation; do not sum these as two recoveries.
- Source as-of snapshots cannot reconstruct earlier draft/void status or text revisions without history. The examples explicitly assume no such revisions. Temporal tests cover event dates, not a complete bitemporal ledger.

## Findings and actions

Use distinct finding types: `billing_candidate`, `reconciliation`, `cost_overrun`, `overdue_balance`, `data_quality`. Confirming an amount does not confirm a cause. Amounts in these categories must not be added into a single "money recovered" total.

Every proposed action names an owner role and evidence needed: operations manager confirms scope/acceptance; bookkeeper reconciles invoice links and allocations; owner reviews future estimating/pricing. Drafts remain suggestions; no outbound messages or ledger writes.

Examples of appropriate actions: reconcile an existing invoice before rebilling; review omitted approved work at the next billing run; inspect task-level causes before revising future estimates; confirm an outstanding balance/dispute before following up. Do not recommend a particular price increase or guaranteed saving without scenario assumptions.

## Cases requiring additional implementation fixtures

Milestone acceptance/deposits; approved change orders; price caps and discounts; retainer rollover; draft→issued→void transitions; reversed or refunded payments; unallocated credits; invoice lines covering multiple projects; repeated partial billing; effective rate changes mid-project; late time entry edits; ambiguous project names; indirect expenses/overhead; archived projects; missing invoice exports; source timezone boundaries; multi-currency; malicious document instructions; and equivalent records from different vendors.

The negative tests exercise some of these structural/date boundaries. They do not substitute for full end-to-end scenario coverage.
