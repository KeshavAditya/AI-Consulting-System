# Data contract v0.1

The canonical bundle is a **developer-facing normalized format**. Users should eventually upload their existing exports and confirm mappings in a UI; they should not be expected to maintain twelve linked spreadsheets manually. No vendor adapter is implemented yet.

The [CLI](cli.md) now accepts this format for experimental reports. Non-synthetic bundles require the explicit review assertions described there. The synthetic verifier retains its separate answer-key checks.

## Files

`schemas/csv-contract.json` defines column names/order, primitive types, nullability, enums, and foreign keys. It is a small project-specific CSV contract, **not JSON Schema**. [field-dictionary.md](field-dictionary.md) lists every column. `templates/` holds header-only CSVs; `examples/synthetic_agency/` contains populated originals.

| Table | Row meaning |
| --- | --- |
| projects | Agreed billing model, budget, customer, completed project, agreement reference |
| people | Pseudonymous worker and role |
| cost_rates | Effective-dated cost rate for a worker |
| time_entries | Dated work with separate recorded/billing hours and approval/billed hints |
| expenses | Direct project cost, not an automatic reimbursable item |
| invoices | Header, customer, dates, status, supplied pre-tax/tax/gross amounts |
| invoice_lines | Pre-tax line allocated to a project |
| billing_links | Explicitly confirmed quantity of a time entry covered by an invoice line |
| payments | Customer receipt, independent of allocation |
| payment_allocations | Portion of a receipt applied to an invoice on a date |
| credits | Issued price reduction with explicit project attribution |
| credit_allocations | Portion of a credit applied to an invoice on a date |

`manifest.json` names the schema version, dataset ID, synthetic provenance, currency, review cutoff, source coverage, table files, document files, and assumptions. Future payment records can be present but are excluded at earlier cutoffs. `expected.json` is a separate answer key, never model input. Agreement and review-note Markdown files provide named evidence passages.

## Parsing and identity

- UTF-8 CSV (BOM accepted on input), standard comma/quote escaping, header required. The fixture verifier requires exact header order and rejects extra/missing columns and blank required cells. Production mapping happens before this boundary.
- Blank nullable cells mean unknown/not applicable, not zero. Literal `0.00` means known zero. Boolean values are exactly `true` or `false`; dates are ISO `YYYY-MM-DD` business dates.
- All financial values are decimal strings with at most twelve integer digits. Monetary amounts require two decimal places; hours and rates allow up to four. Negative numbers, NaN/Infinity, exponent notation, and currency symbols are invalid in this unsigned fixture format. Billing hours cannot exceed 24 per entry.
- IDs are unique within a table, stable across imports, and separate from display names. Foreign keys refer to canonical IDs. `client_id` is a shared canonical customer key in this compact format; no customer contact or identity table is required.
- Preserve raw system/record provenance (`source_ref`) where supplied. A future importer must retain raw file hash, source row, import ID, mapping version, and snapshot timestamp for every normalized record. This metadata is not fully modeled in the fixture tables.
- Every invoice belongs to one project in v0.1 (several lines permitted). Customer IDs on invoices, project, receipts, and credits must agree. Multi-project invoices require explicit allocation semantics before support is enabled.

## Relationships and invariants

Time belongs to a project and worker; exactly one nonoverlapping rate period must cover each worked date. Invoice lines belong to an invoice and project, and sum to the invoice's pre-tax subtotal. Header subtotal plus supplied tax equals total. Each confirmed billing link joins a time entry to a line for the same hourly project. Sum of active covered hours cannot exceed billing hours; sum of covered hourly amounts cannot exceed the line amount. Additional non-time line content is permitted but not automatically classified.

Payment and credit allocations cannot exceed their source amounts or the invoice gross total in aggregate. Allocation dates cannot precede source receipt/issue or invoice issue. Credits also carry a separate, explicit price attribution; a delayed/unallocated credit must not be guessed into an invoice. A positive unsupported overpayment is a reconciliation issue, not silently clamped to zero.

Cost rates are inclusive at `valid_from` and exclusive at `valid_to`. Rate periods cannot overlap. Recorded hours per person per date cannot exceed 24. Time/expenses must fall within the completed project's coverage. The original budgets remain fixed for comparison; budget revisions require a future versioned table.

Invoice status is a snapshot, not a full event history. The arithmetic can exclude later dated events, but cannot recover a prior invoice state after a later void without source history. A production historical review must obtain an as-of snapshot or a versioned event feed. Do not claim historical reconstruction from a current export alone.

## Evidence addresses

Examples: `time_entries.csv#T02-06`, `invoices.csv#I05`, `agreements.md#p04`. Row addresses resolve by primary key; document addresses resolve by explicit heading. Only bundle-local files declared in the manifest are permitted. Do not fetch URLs or follow filesystem paths found in an uploaded document. Proposed semantic matches require user confirmation; equal totals/names are insufficient.

Future extracted passages must preserve document hash, page/section or line span, version/effective date, and extraction confidence separately from any business conclusion. An instruction embedded in a source file must not alter execution policy.

## Mapping plan (not implemented)

1. Start with one exact Harvest detailed-time export flavor. Verify included IDs/columns, permissions, rounding and currency before mapping. Time export alone may not contain complete budgets or historical rates (S06, S09, S11).
2. Add one accounting export path for invoice headers/lines, receipts, credits, and allocations. A summary balance or bank deposit alone may not establish invoice-level linkage.
3. Map client/project identities explicitly and retain ambiguous/unmatched candidates. Never merge by similar names automatically.
4. Confirm coverage across source systems, including externally billed work, archived projects, and missing periods. Completeness is a user assertion to record, not something the LLM can infer from a CSV.
5. Store original files unchanged; normalize into a new versioned snapshot. Detect repeat file/row imports and revised records before recomputing.

## Failure handling

The fixture checker and initial reporting CLI intentionally fail the entire bundle on structural or semantic inconsistency. The future interactive application should instead distinguish fatal import errors from project-level blockers and warnings, display affected records, and allow correction. A skipped file must be prominently disclosed. Unsupported billing models or tax/credit cases must not be coerced into the nearest supported type.
