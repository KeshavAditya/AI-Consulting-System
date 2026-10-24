# Contributing

Work on feature branches and submit small pull requests to `main`. The repository owner selects reviewers and performs merges. Do not push implementation work directly to `main`, auto-merge PRs, or change branch protection as part of a feature. These are project conventions; branch protection must be configured separately by the owner to enforce them.

For this foundation PR, review scope and definitions before implementation details. In particular, check the distinction between priced work, invoiced amounts, cash collected, and delivery margin.

Run from the repository root:

```sh
python scripts/validate_examples.py
python -m unittest discover -s tests -v
```

When changing a business rule, update its assumptions, source references, expected examples, and relevant negative tests. Expected values must be worked out separately; do not regenerate expected answers from the calculation function under test. Record why the expected result changes.

Research references belong in `docs/research.md`, including publisher, URL, date checked, evidence strength, and limitations. Distinguish a vendor's documented behavior from a universal accounting rule or a proposed product decision. Do not copy full articles into this repository.

Keep real client records and credentials outside version control. Synthetic examples should clearly identify their provenance. Do not upload business files to CHTC or an external model service merely because a developer has access to that service. Do not include datasets in training unless rights and scope of use are established.

The existing `main.py` predates this foundation and is unrelated. Any removal or relocation should be a separate, explicit change so its author can review it.
