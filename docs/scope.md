# Scope: agency project and billing review

Status: proposed product specification, supported by desk research. The accompanying example validator is implemented; the application is not. Research checked 2026-10-23. This is management decision support, not a financial-statement audit or an assertion of legal collection rights.

## User and job

Start with software/web agencies that maintain time records, written billing agreements, project budgets, and invoice/payment exports. The suggested 5–30-person segment is a recruitment hypothesis, not a validated market boundary. The owner, operations manager, or bookkeeper is the primary user. Agencies without time records can eventually receive limited billing checks but cannot receive reliable labor-cost analysis from this version.

Job: before finalizing a billing run or reviewing completed projects, identify discrepancies, verify what the records support, and decide the next operational action.

Public examples support recurring project reviews and fragmented data [S01–S05 in research.md]. They also show exceptions: some firms bill per person-week without timesheets. We explicitly exclude those firms from the first cost-analysis workflow.

## Included in version one

| Capability | Required evidence | User-visible result |
| --- | --- | --- |
| Completed-project cost review | Complete time/expense coverage, dated cost rates, agreed fee or approved hourly rates | Delivery cost and margin on a named pricing basis; budget variance |
| Hourly billing review | Approved billable entries, agreed rates, billing cutoff, invoice lines, confirmed entry-to-line links | Eligible uninvoiced amount or unresolved reconciliation candidate |
| Fixed-fee billing review | Agreement, invoiced milestones, acceptance/change evidence | Human-review checklist; no conversion of extra hours into automatic fees |
| Receivables review | Issued invoices, payment and credit allocations, dates, disputes | Remaining balance and days overdue at a named cutoff |
| Evidence-based explanation | Above records plus relevant agreement/task passages | Facts, possible causes, missing evidence, next action, and assumptions |

The first data examples implement completed-project cost arithmetic, hourly billing reconciliation, and invoice balances. They do not implement general milestone detection or legal contract interpretation. Those require additional fixtures before application code is released.

## Workflow and output

1. Choose an as-of date and confirm the coverage of each uploaded source.
2. Import files into staging; inspect mappings, duplicates, currencies, missing rates, and unmatched records.
3. Calculate supported metrics and retain source-row references. Block only affected conclusions where possible.
4. Investigate exceptions using the relevant agreement version and task notes.
5. Ask at most three high-value questions per review round (initial UX choice). Allow skip/unknown and save progress.
6. Present a review queue with amount, evidence state, reason, proposed next action, and remaining uncertainty.
7. Let the user mark a finding confirmed, intentional, incorrect, or unresolved; preserve the explanation and audit history.

Each future finding includes: stable finding ID, project ID, rule ID, finding type, factual statement, amount/currency/basis when justified, source references, evidence state (`supported`, `needs_confirmation`, `blocked`), questions, proposed action, and user disposition. Evidence state is not a statistical probability. A final report must identify its cutoff, coverage, rule/model versions, and incomplete checks.

## Explicit boundaries

- USD only initially; reject mixed currencies rather than assume conversion.
- Historical project delivery margin, not company net profit, GAAP/IFRS revenue recognition, tax calculation, or cash forecasting.
- Preserve supplied tax amounts for receivables arithmetic. No determination of tax liability or tax-adjusted project margin where credit attribution is unclear.
- No automatic invoicing, collections messages, bookkeeping writes, bank access, staffing decisions, or web browsing by the runtime model.
- No retainer rollover, subscription billing, person-week billing, refunds, reversed allocations, or cross-project invoice allocation in the executable fixtures. Represent unsupported cases explicitly during import; never silently discard them.
- No promised ROI or causal claim that an overrun was caused by scope creep merely because hours exceeded budget.
- Initial documents are plain text/searchable PDFs with human-confirmed extraction; scanned documents/OCR remain deferred.

## Acceptance criteria for a usable first application

- Imports a canonical example bundle with an actionable validation report and no paid API.
- Reproduces all fixture numbers exactly to cents and identifies no false billing opportunity on healthy/externally billed examples.
- Every displayed financial amount comes from the calculation engine; every substantive explanation has resolvable evidence or is labeled a hypothesis.
- Missing costs do not become zero; omitted invoice data does not prove work was unbilled.
- A selected cutoff excludes later payments/credits and later work. Current snapshot limitations are disclosed.
- Runs locally with a documented model revision, license, quantization, hardware, context limit, peak memory, and measured latency.
- Supports repeat imports without duplicate counting and preserves user-confirmed mappings. This is a future importer requirement, not provided by the fixture checker.
- A reviewer can reconstruct a finding from its evidence without trusting the model's prose.

## Priorities and unresolved product questions

First release priority: canonical imports and accurate review queue; next, one verified Harvest export adapter and an accounting invoice/payment adapter; then model investigation and a local UI. Avoid a large integration matrix initially.

Desk research cannot establish adoption, willingness to pay, acceptable setup effort, or real recommendation quality. Interviews are not a development prerequisite for this project. Public releases should invite optional issue reports and redacted examples, without making claims of customer validation. Monetization is deferred; optional support or integrations could be explored after usage evidence exists.
