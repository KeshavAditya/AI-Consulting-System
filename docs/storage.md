# Saved review storage v1

This module retains a completed deterministic review and the exact input bytes used to produce it. It is a local filesystem store for one OS user, not a shared service or database. Storage has no model or network dependency. The original report-only command remains usable without saving a review.

## Library API

`agency_review.storage` provides:

| Function | Result |
| --- | --- |
| `save_review(source, store)` | Validate and calculate a bundle, retain consumed inputs and reports, and return `SaveResult(review, reused)`. |
| `list_reviews(store)` | Read metadata for completed review directories; separately report unavailable metadata and pending entries. Does not verify all retained file hashes. |
| `open_review(store, review_id)` | Verify stored file sizes, hashes, inventory, snapshot ID and report/metadata consistency; return the original report bytes without recalculation. |
| `export_review(store, review_id, output)` | Verify and copy the original Markdown/JSON report bytes into a new output directory. |

The default store is `data/private/reviews/` under the repository root, covered by the existing `.gitignore`. A custom store must stay out of public version control. Source and store must be separate directories, with neither nested inside the other. The same separation applies to an export directory and the store.

## Retained record

Each completed review occupies a directory named by the report's full 64-character snapshot hash. It contains `metadata.json`, `report.json`, `report.md`, `inputs/` with the consumed canonical files, and `schema/csv-contract.json` with the exact contract used. The schema is retained for inspection; reopening does not parse the inputs again with that schema or the currently installed schema.

`Bundle.raw_inputs` captures the same bytes that the loader hashes and parses, including the manifest, twelve CSVs, listed Markdown documents, and contract. Saving does not recopy live originals after calculation. No answer key, unrelated files, arbitrary adjacent directories, model weights, or absolute original source path are retained. All declared documents are retained in full, including any later notes; report calculations still use the existing cutoff rules. Files can change between their individual reads: this is not a simultaneous filesystem snapshot, so users should finish preparing inputs before saving.

Metadata includes storage format version, review ID, UTC creation time, dataset/cutoff/currency, synthetic label, report and rule versions, project/finding counts, and each retained file's SHA-256 and byte size. The report ID is derived from the consumed byte hashes, cutoff, report version, and rule version. Original file location and save time do not affect identity.

Identical inputs and versions in the same store reuse the existing verified review and original creation timestamp. Re-saving still validates/calculates the source to determine its snapshot ID; this is not a computation cache. Changed inputs, dataset IDs, or applicable report/rule versions produce a different review. Use a distinct, meaningful dataset ID for each business/review scope. Shared project IDs do not join separate snapshots. An existing corrupted or unsupported record is blocked, never silently repaired or overwritten.

## Reopening and compatibility

Opening verifies all inventoried file bytes and compares report identity and metadata. It then returns the saved report, even if the original source folder has moved, changed, or been deleted. It does not invoke the input loader, calculation engine, or Markdown renderer. Previously generated rule versions remain visible in the report; they are not silently upgraded to current calculations.

Storage format 1 currently reads report format `0.1`. Unknown storage or report formats are rejected with an actionable error rather than guessed. No migrations are implemented. The `SavedReview` wrapper is frozen, but its metadata dictionary is an ordinary in-memory object; callers should treat it as read-only. There is no API to edit a completed stored snapshot.

Listings are deliberately metadata-only, with `integrity: "not_checked"`. A listed record can still fail full verification when opened. Malformed/missing metadata is returned under `unavailable`; it does not hide healthy reviews. Hash checks detect accidental modification, but are not authenticity signatures or protection against a person who can rewrite both stored data and metadata. These checks do not establish financial correctness or validate agreement meaning.

## Publication and interruption

The writer creates a private `.pending-...` staging directory inside the store, writes and flushes every payload and its metadata, then renames it to the final snapshot directory on the same filesystem. Cooperating writers never expose a partially written directory as a completed review. Concurrent identical saves converge on the same completed record and verify it before reuse. There is no global index to update or lock file to recover.

Ordinary caught failures remove the writer's staging directory when the filesystem permits cleanup. A killed process or power loss can leave a pending directory. Listings count pending entries but do not present them as completed, delete them automatically, or resume their work. After confirming that no save is running, users can inspect and remove an abandoned pending directory manually. Files are flushed, but filesystem/directory power-loss durability is not guaranteed. Use local disk; network filesystem consistency and adversarial concurrent filesystem changes are outside this implementation's guarantees.

Export uses exclusive creation of a new output directory and files. It refuses to overwrite any existing output directory and attempts to remove its own partial files after an I/O failure. A process kill or failed cleanup may still leave an incomplete export; use a fresh output directory after inspecting it. Exported report bytes are identical to the saved files, not regenerated Markdown or JSON.

## Bounds and privacy

The existing input limits apply: 2 MB per consumed file, at most twenty Markdown documents and twelve CSV tables. Saved metadata is limited to 64 KB, each report to 32 MB, and the inventory to 36 files. Reads are bounded. Saved IDs must be full lowercase hexadecimal hashes; inventory names cannot traverse directories, and symlink records/files are rejected. Unlisted files in the store are not imported or exported.

Saved inputs may contain sensitive business data. They remain plaintext on local disk with OS account permissions; this implementation does not encrypt them or upload them. There is no multi-user authorization boundary or automatic retention policy. To remove a saved review, delete its exact hash-named directory when no command is using it. Removing the original input folder does not remove the retained copy. Exported copies and OS backups must be handled separately. No delete command is provided in this increment.

## Validation

The storage tests cover exact-byte retention, answer-key exclusion, source changes/deletion, byte-identical reopening/export, duplicate and concurrent saves, dataset isolation, corruption, path traversal, unsupported versions, missing files, pending saves, and write failures. They run alongside the unchanged foundation/report tests. Tests do not establish production filesystem durability or validate real-business accounting exports.
