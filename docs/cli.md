# Local CSV review command

Status: experimental, deterministic command-line reporting. There is no LLM, server, database, vendor importer, or dashboard. This command uses the reviewed foundation rules and supports the same limited completed-project model.

## Run the demonstration

From the repository root, with Python 3.11 or newer:

```sh
python -m agency_review examples/synthetic_agency --output outputs/demo-review
```

On Windows, use `py -3.12` instead of `python` if needed. No package installation, API key, model, GPU, or network connection is required. Open `outputs/demo-review/report.md` in VS Code; use **Ctrl+Shift+V** to preview it. `report.json` contains structured metrics and calculation details.

The output folder must be new. To repeat a run, use a different folder such as `outputs/demo-review-2`. The command never overwrites an existing report directory and does not modify the inputs. The `outputs/` directory is excluded from Git.

The five fictional projects produce three review items:

| Project | Item | Recorded amount | Interpretation |
| --- | --- | ---: | --- |
| P02 | Billing candidate | USD 1,200.00 | Approved hourly value not matched to confirmed invoice links; reconcile before billing. |
| P04 | Cost overrun | USD 4,000.00 | Direct cost above budget; not additional fixed-fee revenue. |
| P05 | Overdue balance | USD 5,000.00 | Remaining invoice balance, 15 days overdue at cutoff; verify allocations and disputes. |

P01 and P03 trigger no exceptions under these rules. That does not establish that those businesses have no other issues. Do not sum the three amounts into a recovery or savings claim.

## Use a supported normalized bundle

This is a developer-facing format, not a drop-in Harvest or QuickBooks import. Prepare a separate folder containing:

- `manifest.json`, using [manifest.example.json](../templates/manifest.example.json) as a starting point.
- All twelve CSV files with the exact headers in [templates](../templates), even where a table has no rows.
- The Markdown files named in `documents`, containing the exact heading anchors used by agreement/evidence references.

Follow [data-contract.md](data-contract.md) and [field-dictionary.md](field-dictionary.md). `expected.json` is neither required nor read by the reporting command. Never copy fictional records into a real business review. Keep real inputs under `data/private/`, or outside the repository, and retain the original source exports separately.

Example command after preparing and reviewing your records:

```sh
python -m agency_review data/private/my-review --output outputs/my-review-001
```

For `synthetic: false`, the manifest must include these **user-supplied assertions**, all explicitly `true`:

| Assertion | What the person preparing the bundle must establish |
| --- | --- |
| `complete_project_costs` | Work and direct costs cover each included completed project from its start; historical cost rates are correct and contractor costs are not double counted. |
| `complete_billing_and_settlements` | Relevant invoice systems, cash receipts, credits, and allocations are included through cutoff, including external invoices. |
| `reviewed_billing_links` | Entry-to-invoice coverage was reviewed; confirmed rates and normalized terms support the supplied pricing basis. |
| `snapshot_at_cutoff` | Supplied status and terms represent the manifest cutoff, with no unmodeled later void/status/term changes used to reconstruct the past. |
| `supported_transactions_only` | There are no unsupported refunds, reversals, retainers, multi-project invoices, currency mixtures, caps, milestone rules, or unknown credit attribution requiring a different calculation model. |

Leave an assertion false if it is unknown; the command blocks instead of inventing a value. These assertions are not an independent audit or permission to ignore an unsupported transaction. They do not prove data completeness or legal entitlement. Terms in Markdown are checked only for referenced headings, not interpreted. The initial implementation fails the whole bundle on the first error; partial project results and interactive corrections remain future work.

The remaining manifest fields are `schema_version`, `dataset_id`, `synthetic`, `currency`, `as_of`, `coverage_start`, `coverage_end`, `tables`, `documents`, `source_coverage`, and `assumptions`. Dates must be ISO dates with `coverage_start <= as_of <= coverage_end`. Every project must be completed by `as_of` and start on/after `coverage_start`. Descriptive fields are assertions, not executable instructions. The code's rule version and documented formulas determine rounding; free-form source notes do not override them.

The CLI intentionally has no `--as-of` override. A historical review requires a separately prepared snapshot with appropriate status/terms and coverage, not simply a new cutoff over current records. The low-level calculation function still accepts dates for regression experiments; that is not a historical reconstruction feature.

## Output contract

`report.json` uses `report_version: "0.1"` and `rule_version: "0.2.0"`:

- Review metadata: dataset ID, synthetic label, cutoff, currency, coverage, assertions, assumptions, limitations, and snapshot ID.
- `projects`: project identity, pricing-basis label, original budget, metrics, and per-entry/per-invoice calculation details.
- Each metric includes a stable ID scoped to the snapshot (`P02.uninvoiced_hourly_candidate`), decimal-string value or `null`, unit, formula, and supporting record references. Days overdue is an integer; summary hours retain the original two-decimal convention, while work details preserve supplied decimal precision.
- `findings`: separate `billing_candidate`, `cost_overrun`, `overdue_balance`, and customer-level `reconciliation` items. Each includes a fact, amount, uncertainty, responsible role, next step, and evidence. No arbitrary urgency ranking or recovery total is assigned. Actions are fixed rule-based suggestions, not generated advice; they never send messages or change a ledger.
- `evidence`: CSV primary-key references with logical record numbers (header = 1), or named document headings, plus source SHA-256 hashes. Multiline CSV fields can span several physical lines; record number is not physical line number.
- `input_hashes`: hashes of every consumed input and the CSV contract. Expected answers and unrelated files are excluded. Documents are hashed in full, including any future notes, but their prose is not used to generate explanations. Only cutoff-eligible rows enter calculations and metric references.

`report.md` displays the summary, actions, formulas, references, and limitations. Source text is escaped to prevent it becoming raw HTML or Markdown instructions. JSON details supply the full per-entry cost/coverage and invoice settlement breakdown; Markdown does not reproduce every source row.

The snapshot ID hashes the consumed file hashes, cutoff, report version, and rule version. Identical bytes and versions produce identical reports; changing input bytes (including line endings) creates a different snapshot even if numeric values remain the same. This is reproducibility metadata, not an authenticity signature. Bump the rule/report version when behavior changes. There is no saved-run database or deduplication service yet.

## Errors and file handling

Success prints a JSON summary to stdout and exits 0. A blocked run prints one JSON error to stderr and exits 1. Argument usage errors exit 2. Example:

```json
{"status": "blocked", "code": "validation_error", "message": "expenses:record 2:amount: invalid money"}
```

The command blocks missing files/values, inconsistent totals, invalid relationships, malformed input, unsupported assertions, and existing output directories. Files are limited to 2 MB each, tables to 10,000 records each, documents to 20 files, text cells to 4,096 characters, and assumptions to 50 entries. Files must be local basenames; symlink inputs and Windows/POSIX path traversal are rejected. The parser is non-executing and does not fetch links or evaluate spreadsheet formulas.

Inputs are read into an in-memory snapshot and hashed from the same bytes used for parsing. Correctness assumes the caller does not mutate the loaded `Bundle` or concurrently edit inputs during import. This is not a sandbox against another process with filesystem access. The report does not retain a copy of each original source file; retain the reviewed inputs alongside the report for later evidence checks.

All validation and rendering finish before the output directory is created. Writes use exclusive file creation; on a normal caught I/O failure the command attempts to remove its partial report files. A process kill, power loss, or failed cleanup can leave a partial directory: absence of a successful completion message means the run is incomplete. Use a fresh output directory after inspecting it.

Reports contain potentially sensitive business information and local files are not encrypted by this application. Nothing is uploaded. To remove a review, delete its input and output folders yourself; backups and copies are outside application control.

## Checks

```sh
python scripts/validate_examples.py
python -m unittest discover -s tests -v
```

The original fixture checker remains synthetic-only and compares against hand-worked answers. It now calls the shared library used by reports, preventing two independent calculation implementations from drifting apart. The CLI tests exercise real subprocess execution, evidence/amounts, error handling, Windows-style paths, output collisions, and source-text escaping. CI includes Linux on Python 3.11–3.13 and Windows on Python 3.12; local testing alone does not establish CI success or production readiness.

## Save and reopen reviews

The new commands preserve the completed report and its consumed inputs under the Git-ignored `data/private/reviews/` directory by default. They do not change the original report-only command above.

### Windows PowerShell example

From the repository root:

```powershell
$savedReview = python -m agency_review save examples/synthetic_agency | ConvertFrom-Json
$savedReview
python -m agency_review list
python -m agency_review open $savedReview.review_id --output outputs/reopened-demo
```

After `save`, confirm `status` is `saved` before running `open`. The save response includes the full review ID, saved location, original UTC creation time, project/finding counts, and `reused`. An identical save returns `reused: true` and does not create a duplicate review. Use a new output directory when reopening again; reports are never overwritten.

If you reopen VS Code and lose the `$savedReview` variable, run `python -m agency_review list`, copy a full `review_id`, then use it in place of the variable. For example, the general syntax is:

```sh
python -m agency_review save PATH_TO_BUNDLE --store PATH_TO_STORE
python -m agency_review list --store PATH_TO_STORE
python -m agency_review open FULL_REVIEW_ID --store PATH_TO_STORE --output NEW_OUTPUT_FOLDER
```

`open` does not launch a browser or editor. It verifies retained files and exports the original `report.json` and `report.md` into the new folder. Open the Markdown file in VS Code and press **Ctrl+Shift+V** to preview it. No financial recalculation, input import, or Markdown regeneration occurs on reopening, even if the original input folder no longer exists.

`list` returns JSON with `reviews`, `unavailable`, and `pending_count`. Listed metadata has `integrity: "not_checked"`; full hash verification happens on `open` or reuse. A corrupted record can appear in a metadata listing but will be blocked on reopening. Invalid metadata is listed separately rather than hiding valid reviews. Pending directories are never presented as completed reviews or automatically removed.

All three commands accept `--store`; the default is relative to the repository installation, not the current working directory. Keep custom stores outside public version control. Input, store, and export directories must satisfy the separation rules in [storage.md](storage.md). Saved reviews remain plaintext local files; no records are uploaded or encrypted by this application.

Command successes exit 0 with a JSON summary. Storage/input/I/O failures exit 1 with a structured error, and argument errors exit 2. A listing can succeed with unavailable entries: inspect that field. Use each command's `--help` for its arguments. If a legacy input folder is literally named `save`, `list`, or `open`, prefix it with `./` to distinguish it from a subcommand.

Storage format/versioning, exact retained contents, interrupted writes, duplicate handling, file limits, and manual deletion are documented in [storage.md](storage.md). This increment does not add a review database, model, dashboard, automatic migrations, partial project recovery, or multi-user service.
