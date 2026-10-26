"""Input diagnostics locate failures without relaxing validation or guessing scope."""
import csv
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from agency_review.data import DEFAULT_BUNDLE, ValidationError, load_bundle
from agency_review.reporting import build_report, render_markdown


class ValidationIssueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "input"
        shutil.copytree(DEFAULT_BUNDLE, self.root)

    def edit(self, table, change):
        path = self.root / (table + ".csv")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def manifest(self, **changes):
        path = self.root / "manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(changes)
        path.write_text(json.dumps(data), encoding="utf-8")

    def issue(self):
        with self.assertRaises(ValidationError) as caught:
            load_bundle(self.root)
        error = caught.exception
        self.assertEqual(error.issue.message, str(error))
        self.assertEqual(error.issue.blocking_scope, "bundle")
        return error.issue.to_dict()

    def test_invalid_cell_has_exact_location_and_direct_project(self):
        self.edit("expenses", lambda rows: rows[0].update(amount="bad"))
        self.assertEqual(self.issue(), {
            "code": "invalid_number", "message": "expenses:record 2:amount: invalid money",
            "file": "expenses.csv", "record": 2, "field": "amount", "record_id": "X01",
            "project_id": "P01", "blocking_scope": "bundle",
        })

    def test_missing_and_blank_cells_have_distinct_codes(self):
        path = self.root / "expenses.csv"
        original = path.read_bytes()
        for record, code, field in [
            (b"X01,P01,2026-09-04\n", "missing_cell", "amount"),
            (b"X01,P01,2026-09-04,,USD,description\n", "required_value", "amount"),
            (b"X01,P01,2026-09-04,200.00,USD,description,extra\n", "extra_csv_cells", None),
        ]:
            with self.subTest(code=code):
                path.write_bytes(original.splitlines()[0] + b"\n" + record)
                issue = self.issue()
                self.assertEqual((issue["code"], issue["field"], issue["record"]), (code, field, 2))

    def test_invalid_date_identifies_cell(self):
        self.edit("invoices", lambda rows: rows[0].update(due_on="2026-02-30"))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["field"]),
                         ("invalid_date", "invoices.csv", "due_on"))
        self.assertIsNone(issue["project_id"])  # No indirect attribution from invoice lines.

    def test_manifest_date_identifies_key(self):
        self.manifest(as_of="bad")
        issue = self.issue()
        self.assertEqual((issue["file"], issue["field"], issue["record"]),
                         ("manifest.json", "as_of", None))

    def test_missing_assertions_identifies_manifest_field(self):
        self.manifest(synthetic=False, review_assertions={})
        issue = self.issue()
        self.assertEqual(issue["code"], "assertion_required")
        self.assertEqual(issue["field"], "review_assertions.complete_project_costs")
        self.assertIsNone(issue["project_id"])

    def test_missing_file_names_expected_file(self):
        (self.root / "people.csv").unlink()
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"]), ("missing_or_unsafe_file", "people.csv"))
        self.assertIsNone(issue["record"])

    def test_unsafe_document_name_points_to_manifest_not_external_path(self):
        self.manifest(documents=["../private.md"])
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["field"]),
                         ("unsafe_filename", "manifest.json", "documents"))

    def test_malformed_input_keeps_parser_category_and_file(self):
        path = self.root / "people.csv"
        original = path.read_bytes()
        for content in [b"\xff", original + b'"unterminated']:
            with self.subTest(content=content[:10]):
                path.write_bytes(content)
                with self.assertRaises(ValidationError) as caught:
                    load_bundle(self.root)
                self.assertEqual(caught.exception.category, "parse_error")
                self.assertEqual(caught.exception.issue.file, "people.csv")
                self.assertIsNone(caught.exception.issue.record)

    def test_json_limit_is_located_without_echoing_value(self):
        (self.root / "manifest.json").write_text('{"value":' + '9' * 5000 + '}')
        with self.assertRaises(ValidationError) as caught:
            load_bundle(self.root)
        self.assertEqual(caught.exception.category, "parse_error")
        self.assertEqual(caught.exception.issue.file, "manifest.json")
        self.assertEqual(caught.exception.issue.code, "json_value_limit")
        self.assertNotIn('9' * 20, str(caught.exception))

    def test_permission_error_is_located_and_does_not_leak_absolute_path(self):
        original = Path.open
        def denied(path, *args, **kwargs):
            if path.name == "people.csv":
                raise PermissionError("PRIVATE ABSOLUTE PATH")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", denied), self.assertRaises(ValidationError) as caught:
            load_bundle(self.root)
        self.assertEqual(caught.exception.category, "file_error")
        self.assertEqual(caught.exception.issue.file, "people.csv")
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_headers_located_at_record_one(self):
        path = self.root / "expenses.csv"
        path.write_bytes(path.read_bytes().replace(b"amount", b"unknown", 1))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["record"], issue["field"]), ("csv_headers", 1, None))

    def test_multiline_csv_uses_logical_record_numbers(self):
        def change(rows):
            rows[0]["task"] = "first line\nsecond line"
            rows[1]["hours"] = "bad"
        self.edit("time_entries", change)
        issue = self.issue()
        self.assertEqual((issue["record"], issue["record_id"]), (3, "T01-02"))

    def test_duplicate_id_identifies_second_occurrence_not_overwritten_index(self):
        self.edit("time_entries", lambda rows: rows[1].update(id=rows[0]["id"]))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["record"], issue["field"]), ("duplicate_id", 3, "id"))
        self.assertIsNone(issue["project_id"])

    def test_duplicate_source_identifies_second_occurrence(self):
        self.edit("time_entries", lambda rows: rows[1].update(source_ref=rows[0]["source_ref"]))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["record"], issue["field"]),
                         ("duplicate_source", 3, "source_ref"))

    def test_missing_project_reference_does_not_claim_project(self):
        self.edit("expenses", lambda rows: rows[0].update(project_id="UNKNOWN"))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["field"]), ("missing_reference", "project_id"))
        self.assertIsNone(issue["project_id"])

    def test_duplicate_project_ids_do_not_establish_parse_attribution(self):
        self.edit("projects", lambda rows: rows[1].update(id=rows[0]["id"]))
        self.edit("expenses", lambda rows: rows[0].update(amount="bad"))
        issue = self.issue()
        self.assertEqual(issue["code"], "invalid_number")
        self.assertIsNone(issue["project_id"])

    def test_invalid_record_id_is_not_a_location_identifier(self):
        self.edit("expenses", lambda rows: rows[0].update(id="not/an/id"))
        issue = self.issue()
        self.assertEqual(issue["code"], "invalid_id")
        self.assertIsNone(issue["record_id"])

    def test_business_rule_identifies_record_and_field(self):
        self.edit("time_entries", lambda rows: rows[0].update(hours="0"))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["record"], issue["field"], issue["project_id"]),
                         ("positive_hours", "time_entries.csv", 2, "hours", "P01"))

    def test_shared_cost_rate_error_does_not_guess_project(self):
        self.edit("cost_rates", lambda rows: rows[0].update(valid_to=rows[0]["valid_from"]))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["field"]),
                         ("rate_interval", "cost_rates.csv", "valid_to"))
        self.assertIsNone(issue["project_id"])

    def test_unavailable_rate_points_to_work_requiring_it(self):
        self.edit("cost_rates", lambda rows: rows.clear())
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["record_id"], issue["project_id"]),
                         ("cost_rate_unavailable", "time_entries.csv", "T01-01", "P01"))
        self.assertIsNone(issue["field"])

    def test_cross_project_billing_conflict_does_not_pick_one_project(self):
        self.edit("billing_links", lambda rows: rows[0].update(invoice_line_id="L02"))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["record"]),
                         ("billing_project_mismatch", "billing_links.csv", 2))
        self.assertIsNone(issue["project_id"])

    def test_invoice_arithmetic_identifies_invoice_not_a_guessed_cell_source(self):
        self.edit("invoices", lambda rows: rows[0].update(total="1.00"))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["field"]),
                         ("invoice_total", "invoices.csv", "total"))

    def test_evidence_location_is_referring_cell(self):
        self.edit("billing_links", lambda rows: rows[0].update(evidence_ref="review-notes.md#missing"))
        issue = self.issue()
        self.assertEqual((issue["code"], issue["file"], issue["field"]),
                         ("unresolved_evidence", "billing_links.csv", "evidence_ref"))

    def test_success_after_failure_does_not_leak_diagnostic_state(self):
        before = build_report(load_bundle(self.root))
        path = self.root / "expenses.csv"
        original = path.read_bytes()
        self.edit("expenses", lambda rows: rows[0].update(amount="bad"))
        self.issue()
        path.write_bytes(original)
        after = build_report(load_bundle(self.root))
        self.assertEqual(before, after)
        self.assertEqual(render_markdown(before), render_markdown(after))

    def test_concurrent_loads_keep_issue_locations_separate(self):
        other = self.root.parent / "other"
        shutil.copytree(self.root, other)
        self.edit("expenses", lambda rows: rows[0].update(amount="bad"))
        (other / "people.csv").unlink()
        def locate(root):
            try:
                load_bundle(root)
            except ValidationError as exc:
                return exc.issue
            self.fail("expected invalid input")
        with ThreadPoolExecutor(max_workers=2) as pool:
            issues = list(pool.map(locate, [self.root, other]))
        self.assertEqual([i.file for i in issues], ["expenses.csv", "people.csv"])
        self.assertEqual([i.record for i in issues], [2, None])


if __name__ == "__main__":
    unittest.main()
