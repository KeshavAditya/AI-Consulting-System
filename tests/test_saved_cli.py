"""Real subprocess tests for save/list/open and legacy command compatibility."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agency_review.cli import main
from agency_review.data import DEFAULT_BUNDLE, ROOT


class SavedCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input with spaces"
        self.store = self.root / "saved reviews"
        shutil.copytree(DEFAULT_BUNDLE, self.source)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "agency_review", *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True, timeout=30)

    def save(self):
        result = self.run_cli("save", self.source, "--store", self.store)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_save_list_open_round_trip_after_source_removed(self):
        saved = self.save()
        self.assertEqual((saved["projects"], saved["findings"]), (5, 3))
        listing = self.run_cli("list", "--store", self.store)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        records = json.loads(listing.stdout)["reviews"]
        self.assertEqual(records[0]["review_id"], saved["review_id"])
        self.assertEqual(records[0]["integrity"], "not_checked")
        shutil.rmtree(self.source)
        output = self.root / "reopened"
        opened = self.run_cli("open", saved["review_id"], "--store", self.store, "--output", output)
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertEqual(json.loads(opened.stdout)["recalculated"], False)
        self.assertEqual(json.loads(opened.stdout)["integrity"], "verified")
        self.assertEqual((output / "report.md").read_bytes(), (self.store / saved["review_id"] / "report.md").read_bytes())
        self.assertEqual((output / "report.json").read_bytes(), (self.store / saved["review_id"] / "report.json").read_bytes())

    def test_default_store_is_used_without_creating_it_on_list(self):
        with patch("agency_review.saved_cli.DEFAULT_STORE", self.store), patch("sys.stdout") as stdout:
            self.assertEqual(main(["list"]), 0)
        text = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(json.loads(text)["store"], str(self.store.resolve()))
        self.assertFalse(self.store.exists())

    def test_repeated_save_reports_reuse(self):
        first = self.save()
        second = self.save()
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["review_id"], second["review_id"])
        self.assertEqual(first["created_at"], second["created_at"])

    def test_legacy_report_command_still_works(self):
        output = self.root / "ordinary"
        result = self.run_cli(self.source, "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "completed")
        self.assertTrue((output / "report.md").exists())
        self.assertFalse(self.store.exists())

    def test_open_refuses_overwriting_existing_export(self):
        saved = self.save()
        output = self.root / "existing"
        output.mkdir()
        (output / "report.md").write_text("KEEP", encoding="utf-8")
        result = self.run_cli("open", saved["review_id"], "--store", self.store, "--output", output)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["code"], "storage_error")
        self.assertEqual((output / "report.md").read_text(encoding="utf-8"), "KEEP")

    def test_corrupt_saved_record_returns_structured_error_without_output(self):
        saved = self.save()
        (self.store / saved["review_id"] / "report.json").write_bytes(b"broken")
        output = self.root / "reopen"
        result = self.run_cli("open", saved["review_id"], "--store", self.store, "--output", output)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["code"], "storage_error")
        self.assertIn("integrity mismatch", result.stderr)
        self.assertFalse(output.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_review_is_not_recalculated(self):
        result = self.run_cli("open", "0" * 64, "--store", self.store, "--output", self.root / "output")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "blocked")
        self.assertFalse(self.store.exists())

    def test_invalid_review_id_rejected(self):
        result = self.run_cli("open", "../private", "--store", self.store, "--output", self.root / "output")
        self.assertEqual(result.returncode, 1)
        self.assertIn("review ID", json.loads(result.stderr)["message"])

    def test_invalid_input_blocks_save_without_creating_store(self):
        (self.source / "manifest.json").write_text("not json", encoding="utf-8")
        result = self.run_cli("save", self.source, "--store", self.store)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["code"], "parse_error")
        self.assertFalse(self.store.exists())

    def test_list_reports_unavailable_and_pending_without_hiding_valid(self):
        self.save()
        incomplete = self.store / ("0" * 64)
        incomplete.mkdir()
        (self.store / ".pending-abandoned").mkdir()
        result = self.run_cli("list", "--store", self.store)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["reviews"]), 1)
        self.assertEqual(len(data["unavailable"]), 1)
        self.assertEqual(data["pending_count"], 1)

    def test_json_integer_parser_limit_returns_error_without_traceback(self):
        # CPython raises ValueError, not JSONDecodeError, at its integer limit.
        (self.source / "manifest.json").write_text('{"schema_version":' + "9" * 5000 + '}', encoding="utf-8")
        result = self.run_cli("save", self.source, "--store", self.store)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "blocked")
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.store.exists())

    def test_help_discovers_commands(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Saved reviews", result.stdout)
        for command in ["save", "list", "open"]:
            with self.subTest(command=command):
                result = self.run_cli(command, "--help")
                self.assertEqual(result.returncode, 0)
                self.assertIn("--store", result.stdout)

    def test_missing_open_output_is_usage_error(self):
        result = self.run_cli("open", "0" * 64)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--output", result.stderr)


if __name__ == "__main__":
    unittest.main()
