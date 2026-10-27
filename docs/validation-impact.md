# Validation impact analysis

Status: internal Python support for bounding the impact of the **first observed
business-rule error**. This is the first step toward partial project reviews.
It does not produce partial reports, collect all errors, or permit calculations
on an invalid bundle. Report and save commands still block on every error.

## Location is different from impact

The issue's `project_id` locates a record when its direct ownership is known.
It does not describe every project affected by the error. For example, the
record that pushes a person's daily hours above 24 can belong to P01, while
other entries on that date belong to P02. Both projects must be considered.

Every `ValidationError` now carries a frozen `impact` assessment:

| Field | Meaning |
| --- | --- |
| `scope` | `projects` when a conservative project set can be established; otherwise `bundle`. |
| `project_ids` | Sorted, unique tuple for `projects`. Empty for `bundle`, which means unknown/unbounded impact, **not zero impact**. |
| `reason` | Internal decision category, listed below. |

This assessment is separate from the existing version-1 `ValidationIssue`.
Its `blocking_scope` remains `bundle`. CLI JSON, exit codes, report versions,
and saved-review formats do not change. Impact is not serialized or persisted.
The internal Python interface can evolve with partial reporting.

```python
from pathlib import Path
from agency_review.data import ValidationError, load_bundle

try:
    bundle = load_bundle(Path("path/to/canonical-input"))
except ValidationError as error:
    print(error.issue.code, error.impact)
    # Repair the inputs. Do not calculate a filtered subset from this result.
```

## Trust boundary and dependency rules

All files must parse, all IDs and source references must be unique, and all
foreign keys and evidence references must resolve before business-rule impact
can be classified. A malformed amount still blocks the whole bundle, even if
its diagnostic location names one project. Structural failures can hide later
records or make dependency resolution ambiguous.

For an explicitly supported business-rule code and source table, classification
uses the complete captured tables, not a second disk read or `issue.project_id`.
It builds connected groups of records using:

- Project references, invoices and their lines, billing links, payments and
  credits with **all** their allocations. A payment shared across projects joins
  those projects; a conflicting billing link includes both ends.
- All time entries for the same person on the same work date. Later entries are
  included even when an earlier entry already triggers the hours-limit error.
- Explicit CSV evidence references, including references across projects and
  cycles. References to people or cost rates include that person's work consumers.

Connections are followed transitively. A local expense error can therefore
have a wider impact if its project shares a payment with another project.
All records participate, including future allocations and draft invoices:
validation checks those records even when a cutoff calculation would omit them.

Rate-interval, overlapping-rate, and unavailable-rate errors start from **all
work for the affected person**, then follow the connected groups. Date narrowing
is intentionally avoided when rate-period validity is in question. Merely using
the same employee on different dates does not connect projects for other errors.
Sharing a client ID alone does not establish shared money. Valid Markdown
documents are checked for references but their prose is not interpreted as a
financial dependency.

The graph uses iterative union/find with union by size and path compression.
Records and references are scanned without constructing every pair in a shared
group. It is built only for a supported failure; successful reviews incur no
graph-construction cost. It has no cross-request mutable state.

## Conservative fallbacks

| Reason | Decision |
| --- | --- |
| `unverified_structure` | Default for parsing, manifest, file, uniqueness, relationship and evidence failures, or errors outside the classified business-rule stage. Whole bundle. |
| `unsupported_rule` | Rule/table pair has not explicitly opted into classification. Whole bundle. |
| `ambiguous_ownership` | Missing invoice lines, customer mismatches, or unknown settlement customers. Whole bundle. |
| `unresolved_ownership` | Located record or a nonempty project set cannot be established, including an invalid unused cost rate. Whole bundle. |
| `record_dependencies` | Conservative project set from the located record and its connected dependencies. |
| `person_cost_rates` | Conservative project set from the person's work and its connected dependencies. |

The classifier is internal and is called only after the loader's structural
checks. It is not a validator for arbitrary manually constructed `Bundle` objects.
Future rule codes default to whole-bundle impact until their dependencies have
been reviewed and tested.

## What remains before partial reporting

An impact set describes only the observed error. It does **not** prove projects
outside that set are valid. Validation still stops at the first error: P01 can
have an expense-date problem while P05 has a separate invoice-total problem.
Correcting P01 then reveals P05. Some remaining errors are detected during
calculation, which this classification stage does not cover.

The next implementation must account for further validation and calculation
failures, preserve shared records and source evidence, and explicitly identify
excluded projects. Global/unallocated settlement findings and any totals need
their own partial-report policy. Simply removing the affected rows and rerunning
the current report is not supported. This change does not add an editable review
lifecycle, automatic input correction, or resumable execution.
