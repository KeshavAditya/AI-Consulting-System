# AI Consulting System

A local, open-source project for reviewing agency project costs and billing records. It will connect recorded work, agreements, invoices, and payments to explain discrepancies with traceable evidence.

**Current status: experimental CSV-to-report command plus the researched foundation.** It validates canonical records, calculates project metrics, exports evidence-backed Markdown and JSON reports, and can save reviews with their source inputs for later reopening. There is no dashboard, model integration, or vendor importer yet. The existing root `main.py` is an unrelated WikiBacon prototype and is not the entry point for this project.

## Start here

1. [Scope and acceptance criteria](docs/scope.md)
2. [Research and evidence register](docs/research.md)
3. [Business rules and formulas](docs/business-rules.md)
4. [Data contract and field dictionary](docs/data-contract.md)
5. [Five worked examples](docs/example-cases.md)
6. [Architecture and implementation sequence](docs/architecture.md)
7. [Evaluation and limitations](docs/evaluation.md)
8. [Contribution workflow](CONTRIBUTING.md)

## Generate a local report

Requires Python 3.11 or newer, with no additional packages, GPU, API key, or network access:

```sh
python -m agency_review examples/synthetic_agency --output outputs/demo-review
```

Open `outputs/demo-review/report.md` in VS Code and press **Ctrl+Shift+V** to preview it. `report.json` includes structured facts, per-entry calculations, invoice balances, and source references. Choose a new output folder for each run; existing folders are never overwritten.

The demonstration flags a USD 1,200 billing candidate, a USD 4,000 cost overrun, and a USD 5,000 overdue balance. These are different review categories, **not additive recoveries**. Explanations and next steps are deterministic rules; no LLM is running.

See [CLI usage, input requirements, and output contract](docs/cli.md) before preparing your own records. Non-synthetic inputs require explicit completeness and supported-transaction assertions. This is an experimental developer-facing workflow, not a verified accounting integration.

## Save and reopen a review

```sh
python -m agency_review save examples/synthetic_agency
python -m agency_review list
```

Copy the full `review_id` from the output, then replace `REVIEW_ID` below:

```sh
python -m agency_review open REVIEW_ID --output outputs/reopened-review
```

Saved inputs and reports live under the Git-ignored `data/private/reviews/` folder by default. Reopening verifies the retained files and exports the original report without recalculation. Identical saves reuse the same review. Use a fresh output folder for each export. See [the CLI guide](docs/cli.md#save-and-reopen-reviews) for PowerShell commands and [storage behavior](docs/storage.md) for integrity checks and limitations.

## Verify the foundation

Requires Python 3.11 or newer. These checks use only the standard library: no package installation, GPU, model download, network access, or API key is needed.

```sh
python scripts/validate_examples.py
python -m unittest discover -s tests -v
```

The first command validates the synthetic CSV records and compares independently written expected totals against calculations. The second deliberately corrupts copies of those records to check important rejection paths and cutoff behavior. These commands validate the foundation; they do not run an AI audit or prove real-world advisory accuracy.

## Intended first workflow

An agency owner, operations manager, or bookkeeper imports a review period, confirms data mappings, inspects project cost and billing exceptions, answers targeted questions, and exports a prioritized review report. The application will run on the user's own machine with a local model; hardware requirements remain to be benchmarked.

Initial scope: one currency (USD), completed fixed-fee project cost reviews, approved hourly work billing reviews, and invoice balances as of a selected date. Financial arithmetic belongs in deterministic code. The model interprets text and explains evidence; it does not decide what a client legally owes.

## Example data

All records under [examples/synthetic_agency](examples/synthetic_agency) are fictional, authored for this project, and contain no customer records. [templates](templates) contains empty canonical CSV headers, not drop-in exports from any vendor. The machine-readable column contract is [schemas/csv-contract.json](schemas/csv-contract.json).

Expected answers are development fixtures, not a held-out benchmark. Do not use them to claim model accuracy, money recovered, or time saved. Real business documents, model weights, credentials, and local analysis results must stay out of the public repository.

## License

The repository's existing [MIT license](LICENSE) applies to project code, documentation, and original synthetic examples. Linked third-party documents retain their own terms. Future model weights/adapters will have their own license and redistribution review; this repository does not grant rights to them.
