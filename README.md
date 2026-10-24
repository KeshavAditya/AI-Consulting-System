# AI Consulting System

A planned local, open-source assistant for reviewing agency project costs and billing records. It will connect recorded work, agreements, invoices, and payments to explain discrepancies with traceable evidence.

**Current status: research and executable example-data foundation.** This repository does not yet contain a consulting application, dashboard, model integration, or production importer. The existing root `main.py` is an unrelated WikiBacon prototype and is not the entry point for this project.

## Start here

1. [Scope and acceptance criteria](docs/scope.md)
2. [Research and evidence register](docs/research.md)
3. [Business rules and formulas](docs/business-rules.md)
4. [Data contract and field dictionary](docs/data-contract.md)
5. [Five worked examples](docs/example-cases.md)
6. [Architecture and implementation sequence](docs/architecture.md)
7. [Evaluation and limitations](docs/evaluation.md)
8. [Contribution workflow](CONTRIBUTING.md)

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
