"""Public error protocol and fail-closed behavior for report/save commands."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agency_review.data import DEFAULT_BUNDLE, ROOT


class IssueCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input"
        self.output = self.root / "output"
        self.store = self.root / "store"
        shutil.copytree(DEFAULT_BUNDLE, self.source)

    def run_command(self, *args):
        return subprocess.run([sys.executable, "-m", "agency_review", *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, timeout=20)

    def blocked(self, result, category):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        payload = json.loads(result.stderr)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["code"], category)
        self.assertEqual(payload["issue_version"], "1")
        self.assertEqual(len(payload["issues"]), 1)
        self.assertEqual(payload["message"], payload["issues"][0]["message"])
        self.assertEqual(payload["issues"][0]["blocking_scope"], "bundle")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.store.exists())
        return payload

    def test_report_and_save_publish_same_issue_without_creating_outputs(self):
        path = self.source / "expenses.csv"
        path.write_bytes(path.read_bytes().replace(b"200.00", b"bad"))
        report = self.blocked(self.run_command(self.source, "--output", self.output), "validation_error")
        saved = self.blocked(self.run_command("save", self.source, "--store", self.store), "validation_error")
        self.assertEqual(report, saved)
        issue = report["issues"][0]
        self.assertEqual((issue["file"], issue["record"], issue["field"], issue["project_id"]),
                         ("expenses.csv", 2, "amount", "P01"))

    def test_missing_input_file_is_located(self):
        (self.source / "people.csv").unlink()
        payload = self.blocked(self.run_command(self.source, "--output", self.output), "validation_error")
        self.assertEqual(payload["issues"][0]["file"], "people.csv")

    def test_json_syntax_error_keeps_parse_category(self):
        (self.source / "manifest.json").write_text("{bad json", encoding="utf-8")
        payload = self.blocked(self.run_command("save", self.source, "--store", self.store), "parse_error")
        self.assertEqual(payload["issues"][0]["file"], "manifest.json")

    def test_integer_parser_limit_is_structured_in_both_commands(self):
        (self.source / "manifest.json").write_text('{"huge":' + '9' * 5000 + '}')
        for args in [(self.source, "--output", self.output), ("save", self.source, "--store", self.store)]:
            with self.subTest(command=str(args[0])):
                payload = self.blocked(self.run_command(*args), "parse_error")
                self.assertEqual(payload["issues"][0]["code"], "json_value_limit")

    def test_first_error_only_is_deterministic(self):
        (self.source / "people.csv").write_bytes(b"\xff")
        (self.source / "expenses.csv").write_bytes(b"also bad")
        first = self.blocked(self.run_command(self.source, "--output", self.output), "parse_error")
        second = self.blocked(self.run_command(self.source, "--output", self.output), "parse_error")
        self.assertEqual(first, second)
        self.assertEqual(first["issues"][0]["file"], "people.csv")

    def test_storage_errors_are_not_mislabeled_as_input_issues(self):
        result = self.run_command("open", "bad-id", "--store", self.store, "--output", self.output)
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stderr)
        self.assertEqual(payload["code"], "storage_error")
        self.assertNotIn("issues", payload)
        self.assertNotIn("issue_version", payload)

    def test_success_protocol_and_report_remain_unchanged(self):
        result = self.run_command(self.source, "--output", self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(set(payload), {"status", "snapshot_id", "projects", "findings", "output"})
        self.assertEqual((payload["projects"], payload["findings"]), (5, 3))
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual((report["report_version"], report["rule_version"]), ("0.1", "0.2.0"))
        self.assertNotIn("issues", report)

    def test_usage_error_stays_exit_two(self):
        result = self.run_command("save")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)
        self.assertFalse(self.store.exists())


if __name__ == "__main__":
    unittest.main()
