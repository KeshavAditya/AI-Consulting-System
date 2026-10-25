"""Local report command. No network calls, model downloads, or paid services."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .data import ValidationError, load_bundle
from .reporting import build_report, render_markdown


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a local agency review from canonical CSVs.")
    parser.add_argument("bundle", type=Path, help="Folder containing manifest.json and the 12 canonical CSVs")
    parser.add_argument("--output", required=True, type=Path, help="New folder for report.json and report.md; existing folders are never overwritten")
    args = parser.parse_args(argv)
    created = False
    files_written = []
    output = args.output.resolve()
    try:
        source = args.bundle.resolve()
        if output == source or source in output.parents:
            raise ValidationError("output must be outside the input bundle")
        if args.output.is_symlink() or output.exists():
            raise ValidationError("output already exists; choose a new folder to preserve previous reports")
        bundle = load_bundle(source)
        report = build_report(bundle)
        # Finish parsing, validation and rendering before creating output files.
        payloads = {
            "report.json": json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
            "report.md": render_markdown(report),
        }
        output.mkdir(parents=True, exist_ok=False)
        created = True
        for filename, text in payloads.items():
            path = output / filename
            # Exclusive creation protects against overwriting even during races.
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                files_written.append(path)
                stream.write(text)
    except (ValidationError, OSError, UnicodeError, csv.Error, json.JSONDecodeError, RecursionError) as exc:
        if created:
            for path in files_written:
                try:
                    path.unlink()
                except OSError:
                    pass
            try:
                output.rmdir()
            except OSError:
                pass
        if isinstance(exc, ValidationError):
            code, message = "validation_error", str(exc)
        elif isinstance(exc, (UnicodeError, csv.Error, json.JSONDecodeError, RecursionError)):
            code, message = "parse_error", "Invalid UTF-8, CSV, or JSON input; check the canonical format in docs/cli.md."
        else:
            code, message = "file_error", "Unable to read inputs or write reports; check file locations, permissions, and whether the output already exists."
        print(json.dumps({"status": "blocked", "code": code, "message": message}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", "snapshot_id": report["snapshot_id"],
                      "projects": len(report["projects"]), "findings": len(report["findings"]),
                      "output": str(output)}))
    return 0
