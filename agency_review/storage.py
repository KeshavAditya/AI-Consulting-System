"""Versioned local review snapshots. No database, network, or background jobs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .data import ROOT, ValidationError, load_bundle, parse_json
from .reporting import build_report, render_markdown

DEFAULT_STORE = ROOT / "data" / "private" / "reviews"
STORAGE_VERSION = 1
MAX_REPORT_BYTES = 32_000_000
MAX_METADATA_BYTES = 64_000
ID_PATTERN = re.compile(r"[a-f0-9]{64}")
METADATA_KEYS = {
    "storage_version", "review_id", "created_at", "dataset_id", "as_of", "currency",
    "synthetic", "report_version", "rule_version", "project_count", "finding_count", "files",
}


class StorageError(ValidationError):
    """A saved review is unsupported, unsafe, incomplete, or inconsistent."""


def check(condition, message):
    if not condition:
        raise StorageError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def store_root(path: Path) -> Path:
    path = Path(path)
    check(not path.is_symlink(), "store must not be a symlink")
    path = path.resolve()
    check(not path.exists() or path.is_dir(), "store must be a directory")
    return path


def valid_id(review_id):
    check(isinstance(review_id, str) and bool(ID_PATTERN.fullmatch(review_id)),
          "review ID must be the full 64-character lowercase snapshot hash")


def input_path(name: str) -> str:
    if name == "schema:csv-contract.json":
        return "schema/csv-contract.json"
    check(isinstance(name, str) and name not in ("", ".", "..")
          and not any(c in name for c in '/\\:#\x00') and Path(name).name == name,
          "invalid retained input filename")
    return "inputs/" + name


def file_limit(relative: str) -> int:
    if relative in ("report.json", "report.md"):
        return MAX_REPORT_BYTES
    if relative == "schema/csv-contract.json":
        return 2_000_000
    parts = PurePosixPath(relative).parts
    check(len(parts) == 2 and parts[0] == "inputs" and input_path(parts[1]) == relative,
          "invalid stored file path")
    return 2_000_000


def read_local(root: Path, relative: str, limit: int) -> bytes:
    # Names are validated before joining; reject symlinks for every component.
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        check(not path.is_symlink(), f"symlink in saved review: {relative}")
    check(path.is_file(), f"missing saved file: {relative}")
    check(path.stat().st_size <= limit, f"saved file exceeds size limit: {relative}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    check(len(data) <= limit, f"saved file exceeds size limit: {relative}")
    return data


def read_metadata(root: Path, review_id: str) -> dict:
    valid_id(review_id)
    check(not root.is_symlink() and root.is_dir(), "saved review directory is missing or unsafe")
    try:
        meta = parse_json(read_local(root, "metadata.json", MAX_METADATA_BYTES))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StorageError("invalid saved review metadata") from exc
    check(isinstance(meta, dict) and set(meta) == METADATA_KEYS, "unsupported metadata structure")
    check(type(meta["storage_version"]) is int and meta["storage_version"] == STORAGE_VERSION,
          "unsupported storage version")
    check(meta["review_id"] == review_id, "review ID does not match its directory")
    for key in ("dataset_id", "as_of", "currency", "report_version", "rule_version", "created_at"):
        check(isinstance(meta[key], str) and 0 < len(meta[key]) <= 4096, f"invalid metadata field: {key}")
    check(meta["report_version"] == "0.1", "unsupported stored report version")
    check(type(meta["synthetic"]) is bool, "invalid synthetic label")
    for key in ("project_count", "finding_count"):
        check(type(meta[key]) is int and meta[key] >= 0, f"invalid metadata field: {key}")
    check(isinstance(meta["files"], dict) and 4 <= len(meta["files"]) <= 36, "invalid saved file inventory")
    check({"inputs/manifest.json", "schema/csv-contract.json", "report.json", "report.md"} <= set(meta["files"]),
          "missing required files in inventory")
    for name, spec in meta["files"].items():
        limit = file_limit(name)
        check(isinstance(spec, dict) and set(spec) == {"sha256", "size"}, "invalid saved file descriptor")
        check(isinstance(spec["sha256"], str) and bool(ID_PATTERN.fullmatch(spec["sha256"])), "invalid saved file hash")
        check(type(spec["size"]) is int and 0 <= spec["size"] <= limit, "invalid saved file size")
    return meta


@dataclass(frozen=True)
class SavedReview:
    path: Path
    metadata: dict
    report_json: bytes
    report_markdown: bytes


@dataclass(frozen=True)
class SaveResult:
    review: SavedReview
    reused: bool


def open_review(store: Path, review_id: str) -> SavedReview:
    """Verify stored bytes and relationships; never import or recalculate inputs."""
    valid_id(review_id)
    root = store_root(store) / review_id
    meta = read_metadata(root, review_id)
    reports = {}
    for name, spec in meta["files"].items():
        data = read_local(root, name, file_limit(name))
        check(len(data) == spec["size"] and digest(data) == spec["sha256"], f"saved file integrity mismatch: {name}")
        if name in ("report.json", "report.md"):
            reports[name] = data
    try:
        report = parse_json(reports["report.json"])
        reports["report.md"].decode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StorageError("invalid stored report encoding or JSON") from exc
    check(isinstance(report, dict), "stored report must be an object")
    for key in ("dataset_id", "as_of", "currency", "synthetic", "report_version", "rule_version"):
        check(key in report and report[key] == meta[key], f"report/metadata mismatch: {key}")
    check(isinstance(report.get("projects"), list) and len(report["projects"]) == meta["project_count"], "project count mismatch")
    check(isinstance(report.get("findings"), list) and len(report["findings"]) == meta["finding_count"], "finding count mismatch")
    hashes = report.get("input_hashes")
    check(isinstance(hashes, dict) and 2 <= len(hashes) <= 34, "invalid report input inventory")
    paths = {input_path(name): value for name, value in hashes.items()}
    check(set(paths) | {"report.json", "report.md"} == set(meta["files"]), "report input inventory mismatch")
    for path, expected_hash in paths.items():
        check(expected_hash == meta["files"][path]["sha256"], f"report input hash mismatch: {path}")
    identity = {"report_version": report["report_version"], "rule_version": report["rule_version"],
                "as_of": report["as_of"], "input_hashes": hashes}
    snapshot = digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    check(snapshot == review_id and report.get("snapshot_id") == review_id, "stored snapshot identity mismatch")
    return SavedReview(root, meta, reports["report.json"], reports["report.md"])


def list_reviews(store: Path = DEFAULT_STORE) -> dict:
    """Metadata-only listing; full file integrity is checked when reopening."""
    root = store_root(store)
    result = {"reviews": [], "unavailable": [], "pending_count": 0}
    if not root.exists():
        return result
    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if path.name.startswith(".pending-"):
            result["pending_count"] += 1
            continue
        if not ID_PATTERN.fullmatch(path.name):
            continue
        try:
            meta = read_metadata(path, path.name)
            result["reviews"].append({k: v for k, v in meta.items() if k != "files"} | {"integrity": "not_checked"})
        except (StorageError, OSError) as exc:
            result["unavailable"].append({"review_id": path.name, "status": "unavailable",
                                          "message": str(exc) if isinstance(exc, StorageError) else "Unable to read saved metadata."})
    result["reviews"].sort(key=lambda r: (r["created_at"], r["review_id"]))
    return result


def write_file(path: Path, data: bytes):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def save_review(source: Path, store: Path = DEFAULT_STORE) -> SaveResult:
    root = store_root(store)
    source = Path(source).resolve()
    check(root != source and source not in root.parents and root not in source.parents,
          "store and input bundle must be separate, non-nested directories")
    bundle = load_bundle(source)
    report = build_report(bundle)
    review_id = report["snapshot_id"]
    valid_id(review_id)
    target = root / review_id
    if target.exists() or target.is_symlink():
        return SaveResult(open_review(root, review_id), reused=True)
    check(set(bundle.raw_inputs) == set(report["input_hashes"]), "captured input inventory differs from report")
    payloads = {}
    for name, data in bundle.raw_inputs.items():
        check(digest(data) == report["input_hashes"][name], "captured input bytes differ from report hash")
        payloads[input_path(name)] = data
    payloads["report.json"] = encoded(report)
    payloads["report.md"] = render_markdown(report).encode("utf-8")
    for name, data in payloads.items():
        check(len(data) <= file_limit(name), f"saved report exceeds size limit: {name}")
    meta = {
        "storage_version": STORAGE_VERSION, "review_id": review_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        **{k: report[k] for k in ("dataset_id", "as_of", "currency", "synthetic", "report_version", "rule_version")},
        "project_count": len(report["projects"]), "finding_count": len(report["findings"]),
        "files": {name: {"sha256": digest(data), "size": len(data)} for name, data in sorted(payloads.items())},
    }
    metadata_bytes = encoded(meta)
    check(len(metadata_bytes) <= MAX_METADATA_BYTES, "saved metadata exceeds size limit")
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
    try:
        for name, data in payloads.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            write_file(path, data)
        write_file(staging / "metadata.json", metadata_bytes)
        # Other readers see only fully written reviews. Concurrent identical saves
        # converge on one existing, verified non-empty directory.
        if target.exists() or target.is_symlink():
            return SaveResult(open_review(root, review_id), reused=True)
        try:
            staging.rename(target)
        except OSError:
            if target.exists() or target.is_symlink():
                return SaveResult(open_review(root, review_id), reused=True)
            raise
        return SaveResult(open_review(root, review_id), reused=False)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def export_review(store: Path, review_id: str, output: Path) -> SavedReview:
    """Copy original report bytes to a new folder after full integrity checking."""
    root = store_root(store)
    output = Path(output)
    check(not output.is_symlink(), "output must not be a symlink")
    output = output.resolve()
    check(output != root and root not in output.parents and output not in root.parents,
          "output and store must be separate, non-nested directories")
    check(not output.exists(), "output already exists; choose a new folder")
    review = open_review(root, review_id)
    output.mkdir(parents=True, exist_ok=False)
    written = []
    try:
        for name, data in (("report.json", review.report_json), ("report.md", review.report_markdown)):
            path = output / name
            # Track only files this invocation creates, including partial writes.
            with path.open("xb") as stream:
                written.append(path)
                stream.write(data)
    except OSError:
        for path in written:
            path.unlink(missing_ok=True)
        output.rmdir()
        raise
    return review
