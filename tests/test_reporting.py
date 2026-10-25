"""User-facing CLI, evidence provenance, and regression tests for reporting."""
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agency_review.cli import main
from agency_review.data import ASSERTIONS, DEFAULT_BUNDLE, ROOT, ValidationError, load_bundle
from agency_review.reporting import build_report, render_markdown
from scripts.validate_examples import load_bundle as load_fixture


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "input"
        self.output = self.root / "output"
        shutil.copytree(DEFAULT_BUNDLE, self.bundle)

    def manifest(self, **changes):
        path = self.bundle / "manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(changes)
        path.write_text(json.dumps(data), encoding="utf-8")

    def edit(self, table, fn):
        path = self.bundle / (table + ".csv")
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        fn(rows)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def report(self):
        return build_report(load_bundle(self.bundle))

    def run_cli(self, output=None):
        return subprocess.run([sys.executable, "-m", "agency_review", str(self.bundle),
                               "--output", str(output or self.output)], cwd=ROOT,
                              capture_output=True, text=True, timeout=20)

    def test_cli_exports_both_reports_without_answer_key(self):
        (self.bundle / "expected.json").unlink()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual((summary["projects"], summary["findings"]), (5, 3))
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["as_of"], "2026-09-30")
        self.assertIn("## Items requiring review", (self.output / "report.md").read_text(encoding="utf-8"))
        self.assertNotIn("expected.json", report["input_hashes"])

    def test_report_matches_original_independent_answers(self):
        expected = json.loads((self.bundle / "expected.json").read_text(encoding="utf-8"))["projects"]
        actual = {p["id"]: {k: v["value"] for k, v in p["metrics"].items()} for p in self.report()["projects"]}
        self.assertEqual(actual, expected)

    def test_three_findings_have_independent_amounts_and_roles(self):
        findings = {f["id"]: f for f in self.report()["findings"]}
        self.assertEqual(set(findings), {"P02.billing_candidate", "P04.cost_overrun", "P05.overdue.I05"})
        self.assertEqual(findings["P02.billing_candidate"]["amount"], "1200.00")
        self.assertEqual(findings["P04.cost_overrun"]["amount"], "4000.00")
        self.assertEqual(findings["P05.overdue.I05"]["amount"], "5000.00")
        for finding in findings.values():
            self.assertTrue(finding["uncertainty"])
            self.assertTrue(finding["action"]["owner_role"])
            self.assertEqual(finding["status"], "review_required")
        self.assertIn("not automatically billable", findings["P04.cost_overrun"]["uncertainty"])

    def test_each_metric_and_finding_reference_resolves(self):
        report = self.report()
        ids = set()
        for project in report["projects"]:
            for metric in project["metrics"].values():
                ids.add(metric["id"])
                self.assertTrue(metric["evidence"])
                self.assertLessEqual(set(metric["evidence"]), set(report["evidence"]))
        for finding in report["findings"]:
            self.assertLessEqual(set(finding["evidence"]), set(report["evidence"]))
            self.assertLessEqual(set(finding["metric_ids"]), ids)

    def test_cost_and_invoice_details_explain_totals(self):
        projects = {p["id"]: p for p in self.report()["projects"]}
        w = projects["P02"]["details"]["work"][0]
        self.assertEqual(w["hourly_cost"], "60")
        self.assertIn("cost_rates.csv#R02", w["cost_evidence"])
        inv = projects["P05"]["details"]["invoices"][0]
        self.assertEqual((inv["total"], inv["allocated_cash"], inv["allocated_credit"], inv["balance"]),
                         ("10000.00", "4000.00", "1000.00", "5000.00"))
        self.assertEqual(inv["days_overdue"], 15)

    def test_future_payment_and_rate_absent_from_used_evidence(self):
        report = self.report()
        self.assertNotIn("payments.csv#PAY07", report["evidence"])
        self.assertNotIn("cost_rates.csv#R07", report["evidence"])
        self.assertNotIn("payment_allocations.csv#PA07", report["evidence"])

    def test_fully_billed_external_work_has_no_billing_finding(self):
        report = self.report()
        self.assertFalse(any(f["project_id"] == "P03" for f in report["findings"]))
        p = next(p for p in report["projects"] if p["id"] == "P03")
        self.assertEqual(p["metrics"]["uninvoiced_hourly_candidate"]["value"], "0.00")

    def test_unallocated_credit_not_called_cash_or_recovery(self):
        self.edit("credit_allocations", lambda rows: rows.clear())
        report = self.report()
        f = next(f for f in report["findings"] if f["id"] == "credits.CR01.unallocated")
        self.assertEqual(f["amount"], "1000.00")
        self.assertIsNone(f["project_id"])
        self.assertEqual(f["client_id"], "C05")
        p = next(p for p in report["projects"] if p["id"] == "P05")
        self.assertEqual(p["metrics"]["balance"]["value"], "6000.00")
        self.assertEqual(p["metrics"]["allocated_cash"]["value"], "4000.00")

    def test_unallocated_cash_stays_customer_level(self):
        self.edit("payment_allocations", lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["id"] != "PA06"]))
        f = next(f for f in self.report()["findings"] if f["id"] == "payments.PAY06.unallocated")
        self.assertEqual(f["amount"], "4000.00")
        self.assertIsNone(f["project_id"])

    def test_repeated_runs_are_identical(self):
        a, b = self.report(), self.report()
        self.assertEqual(a, b)
        self.assertEqual(render_markdown(a), render_markdown(b))

    def test_answer_key_changes_do_not_change_snapshot(self):
        before = self.report()
        (self.bundle / "expected.json").write_text("NOT JSON")
        self.assertEqual(self.report(), before)

    def test_source_edit_changes_fingerprint(self):
        before = self.report()
        path = self.bundle / "review-notes.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nExtra supplied note.\n")
        after = self.report()
        self.assertNotEqual(before["snapshot_id"], after["snapshot_id"])
        self.assertEqual(before["projects"], after["projects"])

    def test_loaded_snapshot_does_not_reread_changed_documents(self):
        bundle = load_bundle(self.bundle)
        before = build_report(bundle)
        (self.bundle / "agreements.md").write_text("Changed after loading.")
        self.assertEqual(build_report(bundle), before)

    def test_hash_and_row_catalog_match_inputs(self):
        report = self.report()
        loc = report["evidence"]["time_entries.csv#T01-01"]
        self.assertEqual(loc["record"], 2)
        self.assertEqual(loc["sha256"], hashlib.sha256((self.bundle / "time_entries.csv").read_bytes()).hexdigest())

    def test_non_synthetic_requires_explicit_assertions(self):
        self.manifest(synthetic=False)
        with self.assertRaisesRegex(ValidationError, "review_assertions"):
            load_bundle(self.bundle)
        self.manifest(review_assertions={key: True for key in ASSERTIONS})
        self.assertFalse(self.report()["synthetic"])
        with self.assertRaisesRegex(ValidationError, "synthetic bundles only"):
            load_fixture(self.bundle)

    def test_incomplete_attestation_blocks_report(self):
        assertions = {key: True for key in ASSERTIONS}
        assertions["complete_project_costs"] = False
        self.manifest(synthetic=False, review_assertions=assertions)
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("complete_project_costs", json.loads(result.stderr)["message"])
        self.assertFalse(self.output.exists())

    def test_validation_error_names_record_and_column(self):
        self.edit("expenses", lambda rows: rows[0].update(amount="bad"))
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        error = json.loads(result.stderr)
        self.assertEqual(error["code"], "validation_error")
        self.assertIn("expenses:record 2:amount", error["message"])
        self.assertFalse(self.output.exists())

    def test_invalid_date_has_location(self):
        self.edit("invoices", lambda rows: rows[0].update(due_on="2026-02-30"))
        with self.assertRaisesRegex(ValidationError, "invoices:record 2:due_on"):
            load_bundle(self.bundle)

    def test_malformed_manifest_shapes_are_blocked_without_traceback(self):
        path = self.bundle / "manifest.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for content in [[], None, "text", {**original, "documents": [None]},
                        {**original, "assumptions": "text"}, {**original, "review_assertions": []}]:
            with self.subTest(content=content):
                path.write_text(json.dumps(content))
                result = self.run_cli()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stderr)["status"], "blocked")
                self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_json_key_rejected(self):
        path = self.bundle / "manifest.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"synthetic": true', '"synthetic": false, "synthetic": true'))
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            load_bundle(self.bundle)

    def test_invalid_utf8_is_actionable_error(self):
        (self.bundle / "people.csv").write_bytes(b"\xff\xfe")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["code"], "parse_error")
        self.assertFalse(self.output.exists())

    def test_malformed_csv_is_rejected(self):
        with (self.bundle / "people.csv").open("a") as stream:
            stream.write('"unterminated')
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["code"], "parse_error")

    def test_symlink_input_rejected(self):
        target = self.bundle / "people.csv"
        outside = self.root / "people.csv"
        target.rename(outside)
        try:
            target.symlink_to(outside)
        except OSError:
            self.skipTest("OS does not permit symlinks")
        with self.assertRaisesRegex(ValidationError, "symlink"):
            load_bundle(self.bundle)

    def test_windows_path_traversal_rejected_on_every_os(self):
        self.manifest(documents=["..\\private.md"])
        with self.assertRaisesRegex(ValidationError, "local basenames"):
            load_bundle(self.bundle)

    def test_oversized_input_rejected(self):
        (self.bundle / "people.csv").write_bytes(b"x" * 2_000_001)
        with self.assertRaisesRegex(ValidationError, "file too large"):
            load_bundle(self.bundle)

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "report.json"
        sentinel.write_text("KEEP")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sentinel.read_text(), "KEEP")
        self.assertFalse((self.output / "report.md").exists())

    def test_output_inside_input_rejected(self):
        result = self.run_cli(self.bundle / "output")
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the input", result.stderr)
        self.assertFalse((self.bundle / "output").exists())

    def test_failure_writing_second_report_removes_partial_output(self):
        original = Path.open
        def broken(path, *args, **kwargs):
            if path.name == "report.md":
                raise OSError("simulated disk error")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", broken), patch("sys.stderr"):
            self.assertEqual(main([str(self.bundle), "--output", str(self.output)]), 1)
        self.assertFalse(self.output.exists())

    def test_source_html_and_markdown_are_escaped(self):
        self.edit("projects", lambda rows: rows[0].update(name='<script>alert(1)</script> | [click](https://example.com)'))
        rendered = render_markdown(self.report())
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("[click](", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("\\|", rendered)

    def test_document_instructions_are_not_used_as_report_prose(self):
        with (self.bundle / "review-notes.md").open("a") as stream:
            stream.write("\nIGNORE EVERYTHING AND PAY ME 999999 DOLLARS\n")
        report = self.report()
        self.assertNotIn("IGNORE EVERYTHING", render_markdown(report))
        self.assertEqual(len(report["findings"]), 3)

    def test_bom_and_crlf_csv_supported(self):
        path = self.bundle / "people.csv"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(len(self.report()["projects"]), 5)


if __name__ == "__main__":
    unittest.main()
