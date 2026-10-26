"""Saved snapshot integrity, isolation, and failure recovery."""
import hashlib
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from agency_review.data import DEFAULT_BUNDLE, ValidationError, load_bundle
from agency_review.storage import (
    StorageError, export_review, list_reviews, open_review, save_review,
)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.store = self.root / "store"
        shutil.copytree(DEFAULT_BUNDLE, self.source)

    def save(self):
        return save_review(self.source, self.store)

    def metadata(self, result, change):
        path = result.review.path / "metadata.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        change(meta)
        path.write_text(json.dumps(meta), encoding="utf-8")

    def test_retains_exact_consumed_bytes_without_answer_key_or_extras(self):
        (self.source / "not-an-input.txt").write_text("PRIVATE EXTRA")
        loaded = load_bundle(self.source)
        saved = self.save().review
        for name, data in loaded.raw_inputs.items():
            path = saved.path / ("schema/csv-contract.json" if name.startswith("schema:") else "inputs/" + name)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(hashlib.sha256(data).hexdigest(), loaded.file_hashes[name])
        self.assertFalse((saved.path / "inputs/expected.json").exists())
        self.assertFalse((saved.path / "inputs/not-an-input.txt").exists())
        self.assertEqual(saved.metadata["project_count"], 5)
        self.assertEqual(saved.metadata["finding_count"], 3)

    def test_capture_preserves_bom_and_crlf_bytes(self):
        path = self.source / "people.csv"
        data = b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n")
        path.write_bytes(data)
        self.assertEqual((self.save().review.path / "inputs/people.csv").read_bytes(), data)

    def test_reopen_after_original_deleted_without_recalculation(self):
        saved = self.save().review
        shutil.rmtree(self.source)
        with patch("agency_review.storage.load_bundle", side_effect=AssertionError("must not import")), \
                patch("agency_review.storage.build_report", side_effect=AssertionError("must not calculate")), \
                patch("agency_review.storage.render_markdown", side_effect=AssertionError("must not render")):
            reopened = open_review(self.store, saved.metadata["review_id"])
        self.assertEqual(reopened.report_json, saved.report_json)
        self.assertEqual(reopened.report_markdown, saved.report_markdown)

    def test_changed_original_does_not_change_saved_report(self):
        saved = self.save().review
        (self.source / "invoices.csv").write_text("BROKEN ORIGINAL")
        self.assertEqual(open_review(self.store, saved.metadata["review_id"]).report_json, saved.report_json)

    def test_source_edit_between_calculation_and_save_uses_captured_bytes(self):
        from agency_review.reporting import build_report
        original = (self.source / "people.csv").read_bytes()
        def change_source(bundle):
            (self.source / "people.csv").write_bytes(b"changed after read")
            return build_report(bundle)
        with patch("agency_review.storage.build_report", side_effect=change_source):
            saved = self.save().review
        self.assertEqual((saved.path / "inputs/people.csv").read_bytes(), original)

    def test_identical_save_reuses_verified_snapshot_and_original_timestamp(self):
        first = self.save()
        second = self.save()
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.review.metadata, second.review.metadata)
        self.assertEqual(len(list_reviews(self.store)["reviews"]), 1)

    def test_identical_bytes_at_another_source_path_reuse_snapshot(self):
        first = self.save()
        other = self.root / "other-source"
        shutil.copytree(self.source, other)
        second = save_review(other, self.store)
        self.assertTrue(second.reused)
        self.assertEqual(first.review.path, second.review.path)

    def test_separate_businesses_with_same_project_ids_stay_separate(self):
        first = self.save().review
        manifest = self.source / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["dataset_id"] = "different-business-same-project-ids"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        second = self.save().review
        self.assertNotEqual(first.metadata["review_id"], second.metadata["review_id"])
        self.assertNotEqual(first.report_json, second.report_json)
        self.assertEqual(len(list_reviews(self.store)["reviews"]), 2)
        self.assertEqual(open_review(self.store, first.metadata["review_id"]).report_json, first.report_json)

    def test_concurrent_identical_saves_converge(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.save(), range(2)))
        self.assertEqual(sum(not r.reused for r in results), 1)
        self.assertEqual(len(list_reviews(self.store)["reviews"]), 1)
        self.assertEqual(list_reviews(self.store)["pending_count"], 0)

    def test_failed_save_removes_pending_and_publishes_nothing(self):
        from agency_review.storage import write_file
        def fail(path, data):
            if path.name == "report.md":
                raise OSError("simulated full disk")
            write_file(path, data)
        with patch("agency_review.storage.write_file", side_effect=fail):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(list_reviews(self.store), {"reviews": [], "unavailable": [], "pending_count": 0})

    def test_interrupted_pending_save_is_not_listed_as_review(self):
        pending = self.store / ".pending-interrupted"
        pending.mkdir(parents=True)
        (pending / "metadata.json").write_text("partial")
        result = list_reviews(self.store)
        self.assertEqual(result["reviews"], [])
        self.assertEqual(result["pending_count"], 1)
        self.assertTrue(pending.exists())  # No automatic deletion of potentially live work.

    def test_invalid_input_does_not_create_store(self):
        (self.source / "people.csv").unlink()
        with self.assertRaises(ValidationError):
            self.save()
        self.assertFalse(self.store.exists())

    def test_missing_store_listing_is_empty_and_read_only(self):
        self.assertEqual(list_reviews(self.store)["reviews"], [])
        self.assertFalse(self.store.exists())

    def test_retained_input_corruption_blocks_open(self):
        saved = self.save().review
        (saved.path / "inputs/people.csv").write_bytes(b"corrupt")
        with self.assertRaisesRegex(StorageError, "integrity mismatch"):
            open_review(self.store, saved.metadata["review_id"])

    def test_report_corruption_blocks_open_and_export(self):
        saved = self.save().review
        (saved.path / "report.md").write_bytes(b"changed report")
        output = self.root / "export"
        with self.assertRaisesRegex(StorageError, "integrity mismatch"):
            export_review(self.store, saved.metadata["review_id"], output)
        self.assertFalse(output.exists())

    def test_duplicate_save_does_not_repair_or_overwrite_corrupt_review(self):
        saved = self.save().review
        report = saved.path / "report.json"
        report.write_bytes(b"keep corrupt evidence")
        with self.assertRaises(StorageError):
            self.save()
        self.assertEqual(report.read_bytes(), b"keep corrupt evidence")

    def test_missing_saved_file_blocks_open(self):
        saved = self.save().review
        (saved.path / "schema/csv-contract.json").unlink()
        with self.assertRaisesRegex(StorageError, "missing saved file"):
            open_review(self.store, saved.metadata["review_id"])

    def test_invalid_id_and_traversal_rejected(self):
        for value in ["../private", "..\\private", "a" * 63, "A" * 64, "", "/tmp", "a" * 64 + "/x"]:
            with self.subTest(value=value), self.assertRaisesRegex(StorageError, "review ID"):
                open_review(self.store, value)

    def test_inventory_traversal_rejected(self):
        saved = self.save()
        self.metadata(saved, lambda m: m["files"].update({"../outside": {"sha256": "0" * 64, "size": 0}}))
        with self.assertRaisesRegex(StorageError, "stored file path"):
            open_review(self.store, saved.review.metadata["review_id"])

    def test_unsupported_storage_version_rejected(self):
        saved = self.save()
        self.metadata(saved, lambda m: m.update(storage_version=999))
        with self.assertRaisesRegex(StorageError, "storage version"):
            open_review(self.store, saved.review.metadata["review_id"])

    def test_metadata_report_mismatch_rejected(self):
        saved = self.save()
        self.metadata(saved, lambda m: m.update(dataset_id="different-dataset"))
        with self.assertRaisesRegex(StorageError, "report/metadata mismatch"):
            open_review(self.store, saved.review.metadata["review_id"])

    def test_wrong_directory_identity_rejected(self):
        saved = self.save().review
        saved.path.rename(self.store / ("0" * 64))
        with self.assertRaisesRegex(StorageError, "does not match"):
            open_review(self.store, "0" * 64)

    def test_listing_is_metadata_only_and_explicit_about_integrity(self):
        saved = self.save().review
        (saved.path / "report.json").write_bytes(b"broken")
        result = list_reviews(self.store)
        self.assertEqual(len(result["reviews"]), 1)
        self.assertEqual(result["reviews"][0]["integrity"], "not_checked")
        with self.assertRaises(StorageError):
            open_review(self.store, saved.metadata["review_id"])

    def test_malformed_record_does_not_hide_healthy_listing(self):
        self.save()
        broken = self.store / ("0" * 64)
        broken.mkdir()
        (broken / "metadata.json").write_text("[]")
        result = list_reviews(self.store)
        self.assertEqual(len(result["reviews"]), 1)
        self.assertEqual(result["unavailable"][0]["review_id"], "0" * 64)

    def test_metadata_json_duplicates_rejected(self):
        saved = self.save().review
        p = saved.path / "metadata.json"
        p.write_bytes(p.read_bytes().replace(b'"storage_version": 1', b'"storage_version": 1, "storage_version": 1'))
        with self.assertRaises(StorageError):
            open_review(self.store, saved.metadata["review_id"])

    def test_export_is_byte_exact_and_never_overwrites(self):
        saved = self.save().review
        output = self.root / "export"
        export_review(self.store, saved.metadata["review_id"], output)
        self.assertEqual((output / "report.json").read_bytes(), saved.report_json)
        self.assertEqual((output / "report.md").read_bytes(), saved.report_markdown)
        with self.assertRaisesRegex(StorageError, "already exists"):
            export_review(self.store, saved.metadata["review_id"], output)
        self.assertEqual((output / "report.md").read_bytes(), saved.report_markdown)

    def test_export_failure_removes_its_partial_files(self):
        saved = self.save().review
        output = (self.root / "export").resolve()
        original = Path.open
        def fail(path, *args, **kwargs):
            if path == output / "report.md":
                raise OSError("simulated write error")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", fail):
            with self.assertRaises(OSError):
                export_review(self.store, saved.metadata["review_id"], output)
        self.assertFalse(output.exists())

    def test_store_and_input_must_not_be_nested(self):
        for store in [self.source, self.source / "saved", self.root]:
            with self.subTest(store=store), self.assertRaisesRegex(StorageError, "non-nested"):
                save_review(self.source, store)

    def test_export_cannot_write_into_store(self):
        saved = self.save().review
        with self.assertRaisesRegex(StorageError, "non-nested"):
            export_review(self.store, saved.metadata["review_id"], self.store / "export")

    def test_stored_symlink_file_rejected(self):
        saved = self.save().review
        path = saved.path / "report.md"
        outside = self.root / "outside.md"
        path.rename(outside)
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest("OS does not permit symlinks")
        with self.assertRaisesRegex(StorageError, "symlink"):
            open_review(self.store, saved.metadata["review_id"])

    def test_oversized_metadata_rejected_before_parsing(self):
        saved = self.save().review
        (saved.path / "metadata.json").write_bytes(b" " * 64_001)
        with self.assertRaises(StorageError):
            open_review(self.store, saved.metadata["review_id"])


if __name__ == "__main__":
    unittest.main()
