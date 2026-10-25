"""CLI for local saved reviews; the original report-only command is unchanged."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .data import ValidationError
from .storage import DEFAULT_STORE, StorageError, export_review, list_reviews, save_review, store_root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Save, list, and reopen local agency reviews.")
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("save", help="Preserve consumed inputs and the calculated reports")
    save.add_argument("bundle", type=Path)
    listing = commands.add_parser("list", help="List saved review metadata without recalculation")
    opening = commands.add_parser("open", help="Verify and export saved reports without recalculation")
    opening.add_argument("review_id", help="Full snapshot hash returned by save/list")
    opening.add_argument("--output", required=True, type=Path, help="New directory for copies of the stored reports")
    for command in (save, listing, opening):
        command.add_argument("--store", type=Path, default=DEFAULT_STORE,
                             help="Local review store (default: repository data/private/reviews)")
    args = parser.parse_args(argv)
    try:
        if args.command == "save":
            result = save_review(args.bundle, args.store)
            meta = result.review.metadata
            payload = {"status": "saved", "review_id": meta["review_id"], "reused": result.reused,
                       "created_at": meta["created_at"], "projects": meta["project_count"],
                       "findings": meta["finding_count"], "path": str(result.review.path)}
        elif args.command == "list":
            payload = {"status": "listed", "store": str(store_root(args.store)), **list_reviews(args.store)}
        else:
            result = export_review(args.store, args.review_id, args.output)
            payload = {"status": "opened", "review_id": result.metadata["review_id"],
                       "output": str(args.output.resolve()), "integrity": "verified", "recalculated": False}
    except (ValueError, OSError, csv.Error, RecursionError) as exc:
        if isinstance(exc, StorageError):
            code, message = "storage_error", str(exc)
        elif isinstance(exc, ValidationError):
            code, message = "validation_error", str(exc)
        elif isinstance(exc, (ValueError, csv.Error, RecursionError)):
            code, message = "parse_error", "Invalid UTF-8, CSV, or JSON input; see docs/cli.md."
        else:
            code, message = "file_error", "Unable to read or write local review files; check locations, permissions, and disk space."
        print(json.dumps({"status": "blocked", "code": code, "message": message}), file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False))
    return 0
