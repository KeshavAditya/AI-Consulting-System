# Canonical CSV field dictionary

Generated from `schemas/csv-contract.json`; schema and this file must change together. All tables use `id` as a unique primary key. Empty cells are permitted only where marked nullable. References target the other table's `id`.

## projects.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Canonical project ID. |
| `client_id` | id | no | Canonical customer ID; repeated across projects only for the same customer. |
| `name` | text | no | Display name, never a matching key. |
| `billing_model` | enum: hourly, fixed_fee | no | Determines pricing and billing semantics. |
| `status` | enum: completed | no | Only completed-project margin fixtures in this version. |
| `start_date` | date | no | Beginning of complete project coverage. |
| `completed_date` | date | no | Confirmed completion date. |
| `currency` | enum: USD | no | Currency of all amounts on this row; USD only in v0.1. |
| `agreed_fee` | money | yes | Agreed pre-tax fixed fee; blank for hourly. |
| `budget_hours` | decimal | no | Approved original total hours budget. |
| `budget_cost` | money | no | Approved direct delivery cost budget, including expenses. |
| `agreement_ref` | evidence | no | Confirmed agreement passage; relative Markdown path and anchor. |

## people.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Pseudonymous worker ID. |
| `role` | text | no | Delivery role; no salary or personal contact information. |

## cost_rates.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Rate period ID. |
| `person_id` | id → people.id | no | Worker. |
| `valid_from` | date | no | Inclusive effective date. |
| `valid_to` | date | yes | Exclusive effective date; blank is open-ended. |
| `hourly_cost` | decimal | no | Loaded direct labor cost rate; not selling rate. |
| `currency` | enum: USD | no | Currency of all amounts on this row; USD only in v0.1. |

## time_entries.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Stable canonical time-entry ID. |
| `project_id` | id → projects.id | no | Project. |
| `person_id` | id → people.id | no | Worker. |
| `work_date` | date | no | Business date worked. |
| `task` | text | no | Work description; untrusted document content in future runtime. |
| `hours` | decimal | no | Recorded hours used for cost. |
| `billing_hours` | decimal | no | Hours after agreed billing rounding; used for priced work. |
| `billable` | boolean | no | Whether work is marked billable. |
| `approval_status` | enum: approved, pending, rejected | no | Agency billing review status. |
| `approved_on` | date | yes | Date approved; required only for approved entries. |
| `billing_rate` | decimal | yes | Confirmed historical hourly selling rate; blank for fixed-fee work. |
| `invoiced_flag` | boolean | no | Source-system hint; not authoritative invoice coverage. |
| `source_ref` | text | no | Synthetic source namespace and record ID; replace with immutable import provenance later. |

## expenses.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Direct expense ID. |
| `project_id` | id → projects.id | no | Project. |
| `incurred_on` | date | no | Date cost incurred. |
| `amount` | money | no | Direct cost excluding recoverable taxes; no markup. |
| `currency` | enum: USD | no | Currency of all amounts on this row; USD only in v0.1. |
| `description` | text | no | Cost description; no automatic rebilling of expenses in v0.1. |

## invoices.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Canonical invoice ID. |
| `client_id` | id | no | Customer matching the invoice line project. |
| `issued_on` | date | no | Invoice date; status history outside this fixture contract. |
| `due_on` | date | no | Agreed payment due date. |
| `status` | enum: issued, draft, void | no | Only issued invoices establish balances/coverage. |
| `currency` | enum: USD | no | Currency of all amounts on this row; USD only in v0.1. |
| `subtotal` | money | no | Total before supplied tax; sum of invoice lines. |
| `tax` | money | no | Supplied tax, not computed by this tool. |
| `total` | money | no | Subtotal plus supplied tax. |
| `disputed` | boolean | no | Requires review before collection action. |
| `source_ref` | text | no | Original invoice system and immutable identifier. |

## invoice_lines.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Invoice line ID. |
| `invoice_id` | id → invoices.id | no | Invoice. |
| `project_id` | id → projects.id | no | Project; one project per invoice in v0.1. |
| `description` | text | no | Line description. |
| `amount` | money | no | Pre-tax net line amount after any source discount. |

## billing_links.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Confirmed invoice-coverage link ID. |
| `time_entry_id` | id → time_entries.id | no | Covered time entry. |
| `invoice_line_id` | id → invoice_lines.id | no | Covering line. |
| `covered_hours` | decimal | no | Covered billing hours, not necessarily recorded hours. |
| `confirmed_on` | date | no | When a human/source confirmed the link. |
| `evidence_ref` | evidence | no | Specific support for this link; never inferred from an amount alone. |

## payments.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Customer cash receipt ID. |
| `client_id` | id | no | Customer. |
| `received_on` | date | no | Date funds were received. |
| `amount` | money | no | Gross customer payment; processing fees not netted. |
| `currency` | enum: USD | no | Currency of all amounts on this row; USD only in v0.1. |

## payment_allocations.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Allocation event ID. |
| `payment_id` | id → payments.id | no | Payment. |
| `invoice_id` | id → invoices.id | no | Invoice. |
| `applied_on` | date | no | Allocation date, on/after payment receipt and invoice issue. |
| `amount` | money | no | Amount of the payment applied to this invoice. |

## credits.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Issued credit memo ID; no delayed credits. |
| `client_id` | id | no | Customer. |
| `project_id` | id → projects.id | no | Confirmed project whose pricing basis is reduced. |
| `issued_on` | date | no | Credit issue date. |
| `subtotal` | money | no | Pre-tax price reduction attributed to the project. |
| `tax` | money | no | Tax component supplied by source. |
| `total` | money | no | Subtotal plus tax. |
| `currency` | enum: USD | no | Currency of all amounts on this row; USD only in v0.1. |
| `reason` | text | no | Reason for credit; does not imply payment. |

## credit_allocations.csv

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `id` | id | no | Credit application ID. |
| `credit_id` | id → credits.id | no | Credit memo. |
| `invoice_id` | id → invoices.id | no | Invoice. |
| `applied_on` | date | no | Application date, on/after credit and invoice issue. |
| `amount` | money | no | Gross credit applied to the invoice. |
