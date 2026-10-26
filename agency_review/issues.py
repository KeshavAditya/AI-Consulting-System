"""Machine-readable input diagnostics; all issues still block the whole review."""
from __future__ import annotations

import csv
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace

ISSUE_VERSION = "1"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    file: str | None = None
    record: int | None = None
    field: str | None = None
    record_id: str | None = None
    project_id: str | None = None
    blocking_scope: str = "bundle"

    def to_dict(self) -> dict:
        return asdict(self)


class ValidationError(ValueError):
    """An input violates the contract; str(error) remains the human message."""

    def __init__(self, message: str, *, code: str = "invalid_input",
                 category: str = "validation_error", **location):
        super().__init__(message)
        self.issue = ValidationIssue(code=code, message=message, **location)
        self.category = category


@contextmanager
def issue_context(**location):
    """Fill missing locations while preserving the innermost, precise location.

    Context lives on the exception, not global mutable state. Parser and input
    I/O errors are translated only at the boundaries that opt into this context.
    """
    try:
        yield
    except ValidationError as exc:
        exc.issue = replace(exc.issue, **{
            key: value for key, value in location.items()
            if getattr(exc.issue, key) is None
        })
        raise
    except (UnicodeError, csv.Error, json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError(
            "Invalid UTF-8, CSV, or JSON input; check the canonical format in docs/cli.md.",
            code="malformed_input", category="parse_error", **location,
        ) from exc
    except OSError as exc:
        raise ValidationError(
            "Unable to read input file; check its location and permissions.",
            code="input_read_error", category="file_error", **location,
        ) from exc


def error_payload(exc, code: str, message: str) -> dict:
    """Add diagnostics without changing existing top-level error fields."""
    result = {"status": "blocked", "code": code, "message": message}
    if isinstance(exc, ValidationError) and code != "storage_error":
        result.update(issue_version=ISSUE_VERSION, issues=[exc.issue.to_dict()])
    return result
