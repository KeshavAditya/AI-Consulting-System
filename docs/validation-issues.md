# Structured validation issues

This increment attaches machine-readable diagnostics to input validation failures. It still stops at the first error and blocks the entire review. It does not return partial calculations, collect every error, edit inputs, or resume an interrupted review.

## Python contract

`load_bundle` raises `ValidationError` for contract failures and located input parsing/read failures. Importing that class from `agency_review.data` remains supported; its implementation lives in `agency_review.issues`. `str(error)` is the human-readable message. `error.issue` is a frozen `ValidationIssue` dataclass; `error.issue.to_dict()` returns JSON-compatible values.

`error.category` retains the CLI categories `validation_error`, `parse_error`, or `file_error`. Callers that previously caught raw parser or input I/O exceptions from `load_bundle` should now catch `ValidationError` and inspect its category. Storage verification and output write errors keep their separate command behavior.

| Field | Meaning |
| --- | --- |
| `code` | Machine-readable rule identifier, such as `invalid_number`, `missing_reference`, or `invoice_total`. Do not parse message text to identify a rule. |
| `message` | Explanation for a person. Existing validation messages remain recognizable; wording is not the machine contract. It can contain supplied identifiers or values, so treat it as potentially sensitive. |
| `file` | Bundle filename, `manifest.json`, or the installation-relative `schemas/csv-contract.json`; null when unknown. Unsafe document paths point to the manifest's `documents` field. |
| `record` | Logical CSV record number, header = 1. Quoted multiline cells do not increase the record number. Null for non-CSV errors or when parsing failed before a complete record could be identified. |
| `field` | CSV column or manifest key (dotted for assertions); null for errors involving multiple fields or no specific field. |
| `record_id` | Syntactically valid source record ID, when known. A duplicate ID is located at its second occurrence. This is not proof of uniqueness or correctness. |
| `project_id` | Direct reference to a unique, known project ID, when available. This is diagnostic context, not a claim that only that project is affected. |
| `blocking_scope` | Always `bundle` in this version. No financial results are emitted for an invalid bundle. |

## Attribution and ordering

During CSV parsing, direct project attribution is available only after the projects table has been parsed and its IDs counted. A syntax error within `projects.csv` therefore may have a record ID but no project ID. Unknown or duplicate project IDs are never used for attribution. Relationship/business-rule checks run after all table IDs and source references have passed uniqueness checks.

Shared people/cost-rate rows, invoice rows with only indirect project links, settlement allocations, and billing links have a null project ID. Cross-project conflicts do not pick a side. A missing cost rate is located at the work entry that requires it. Aggregate errors identify the affected source or invoice row; the record location is a place to investigate, not necessarily the single record that should be edited.

Evidence errors point to the cell containing the bad reference, rather than pretending the referenced document or row was found. No project is inferred by parsing an error message, a name, or a customer ID.

The first error follows deterministic import/validation order for the same input bytes and validator version. All tables' uniqueness checks now precede foreign-key lookup, so ambiguous keys cannot be silently resolved through an overwritten index. A bundle with several errors may expose a different first error than older versions. Fix that error and run again. An empty diagnostics list is not a data-completeness certification.

## Rule identifiers

Rule identifiers are explicit in the validator. They cover cell types/required values, manifest structure/assertions/coverage, file safety and limits, duplicate IDs/source records, foreign keys/evidence, and the existing financial consistency rules. Representative identifiers:

- Import: `missing_cell`, `required_value`, `invalid_number`, `invalid_date`, `csv_headers`, `extra_csv_cells`, `malformed_input`, `json_value_limit`, `input_read_error`.
- Manifest/files: `manifest_shape`, `unsupported_schema`, `assertion_required`, `invalid_coverage`, `unsafe_filename`, `missing_or_unsafe_file`, `file_size_limit`.
- Relationships: `duplicate_id`, `duplicate_source`, `missing_reference`, `unresolved_evidence`, `billing_project_mismatch`.
- Business rules: `cost_rate_unavailable`, `rate_interval`, `daily_hours_limit`, `invoice_total`, `invoice_line_total`, `source_overallocated`, `invoice_overallocated`.

Consumers must handle unknown codes and null location fields. New rule identifiers may be added without changing existing identifiers. Diagnostic details do not change report version `0.1`, calculation rule version `0.2.0`, snapshot identities, or saved-review format. Valid inputs produce the same reports as before.
