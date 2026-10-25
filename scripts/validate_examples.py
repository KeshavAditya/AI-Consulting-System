"""Verify synthetic examples against independently authored answers."""
import argparse
import csv
import json
import sys
from pathlib import Path

# Support both direct execution and imports by the original regression suite.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agency_review.data import (
    DEFAULT_BUNDLE, Bundle, ValidationError, local_file, money, rate_for,
    require, resolve_evidence, load_bundle as load_review_bundle,
)
from agency_review.calculations import calculate


def load_bundle(root=DEFAULT_BUNDLE):
    return load_review_bundle(root, synthetic_only=True)


def verify_expected(bundle: Bundle, actual: dict) -> None:
    expected = json.loads(local_file(bundle.root, "expected.json").read_text(encoding="utf-8"))
    require(expected.get("as_of") == bundle.manifest["as_of"], "answer key cutoff mismatch")
    require(set(expected["projects"]) == set(actual), "answer key project set mismatch")
    for pid in actual:
        require(actual[pid] == expected["projects"][pid], f"expected metrics mismatch for {pid}: actual={actual[pid]}, expected={expected['projects'][pid]}")
    rubrics = expected.get("narrative_expectations", [])
    require(len(rubrics) == len(actual) and {r["project_id"] for r in rubrics} == set(actual), "narrative rubric project set mismatch")
    for rubric in rubrics:
        require(bool(rubric.get("must_say")) and bool(rubric.get("must_not_say")) and bool(rubric.get("evidence")), "incomplete narrative rubric")
        for ref in rubric["evidence"]:
            resolve_evidence(bundle, ref)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, nargs="?", default=DEFAULT_BUNDLE)
    args = parser.parse_args()
    try:
        bundle = load_bundle(args.bundle)
        actual = calculate(bundle)
        verify_expected(bundle, actual)
    except (ValidationError, OSError, csv.Error, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {len(bundle.tables)} tables, {sum(len(rows) for rows in bundle.tables.values())} rows, {len(actual)} projects; expected calculations and evidence references verified.")
    print("Narrative quality, model behavior, and real vendor import compatibility are not evaluated by this check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
