"""Canonical bundle loading and validation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .issues import ValidationError, issue_context
from .impact import _classify_domain_impact

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "examples" / "synthetic_agency"
CENT = Decimal("0.01")
ZERO = Decimal("0")
ASSERTIONS = (
    "complete_project_costs", "complete_billing_and_settlements",
    "reviewed_billing_links", "snapshot_at_cutoff", "supported_transactions_only",
)


def require(condition: bool, message: str, *, code="invalid_input", **location) -> None:
    if not condition:
        raise ValidationError(message, code=code, **location)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def display(value: Decimal) -> str:
    return format(money(value), ".2f")


def parse_day(value: str) -> date:
    require(isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), "date must be YYYY-MM-DD", code="invalid_date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"invalid date: {value}", code="invalid_date") from exc


def parse_cell(raw: str, column: dict, location: str):
    require(isinstance(raw, str), f"{location}: missing CSV cell", code="missing_cell")
    if raw == "":
        require(column["nullable"], f"{location}: required value is blank", code="required_value")
        return None
    kind = column["type"]
    if kind in ("money", "decimal"):
        pattern = r"\d{1,12}\.\d{2}" if kind == "money" else r"\d{1,12}(?:\.\d{1,4})?"
        require(len(raw) <= 24 and bool(re.fullmatch(pattern, raw)), f"{location}: invalid {kind}", code="invalid_number")
        return Decimal(raw)
    if kind == "date":
        try:
            return parse_day(raw)
        except ValidationError as exc:
            raise ValidationError(f"{location}: {exc}", code=exc.issue.code) from exc
    if kind == "boolean":
        require(raw in ("true", "false"), f"{location}: invalid boolean", code="invalid_boolean")
        return raw == "true"
    if kind == "enum":
        require(raw in column["enum"], f"{location}: unsupported value {raw!r}", code="unsupported_value")
    if kind == "id":
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]+", raw)), f"{location}: invalid ID", code="invalid_id")
    require(raw.strip() != "", f"{location}: whitespace-only value", code="required_value")
    require(len(raw) <= 4096 and not any(ord(c) < 32 and c not in "\n\r\t" for c in raw),
            f"{location}: text exceeds limit or contains control characters", code="invalid_text")
    return raw


@dataclass
class Bundle:
    root: Path
    manifest: dict
    tables: dict[str, list[dict]]
    contract: dict
    file_hashes: dict[str, str] = field(default_factory=dict)
    row_locations: dict[str, dict] = field(default_factory=dict)
    documents: dict[str, str] = field(default_factory=dict)
    _indexes: dict[str, dict] = field(default_factory=dict, repr=False)
    raw_inputs: dict[str, bytes] = field(default_factory=dict, repr=False)

    def index(self, table: str) -> dict[str, dict]:
        if table not in self._indexes:
            self._indexes[table] = {row["id"]: row for row in self.tables[table]}
        return self._indexes[table]


def local_file(root: Path, name: str) -> Path:
    require(isinstance(name, str) and bool(name) and name not in (".", "..")
            and not any(c in name for c in '/\\:#\x00') and Path(name).name == name,
            "bundle files must be local basenames", code="unsafe_filename")
    require(not (root / name).is_symlink(), f"symlink bundle file unsupported: {name}", code="unsafe_file")
    path = (root / name).resolve()
    require(path.parent == root.resolve() and path.is_file(), f"missing or unsafe bundle file: {name}", code="missing_or_unsafe_file")
    require(path.stat().st_size <= 2_000_000, f"bundle file too large: {name}", code="file_size_limit")
    return path


def read_bytes(root: Path, name: str) -> bytes:
    # Bound actual reads as well as stat size; no unbounded read if a file grows.
    with local_file(root, name).open("rb") as stream:
        data = stream.read(2_000_001)
    require(len(data) <= 2_000_000, f"bundle file too large: {name}", code="file_size_limit")
    return data


def parse_json(data: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key", code="duplicate_json_key")
            result[key] = value
        return result
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique)
    except (ValidationError, UnicodeError, json.JSONDecodeError):
        raise
    except ValueError as exc:
        # Includes Python's bounded integer parser; do not echo the input value.
        raise ValidationError("JSON value exceeds parser limits", code="json_value_limit",
                              category="parse_error") from exc


def resolve_evidence(bundle: Bundle, ref: str) -> None:
    require(isinstance(ref, str) and ref.count("#") == 1, f"invalid evidence reference: {ref}", code='invalid_evidence')
    filename, anchor = ref.split("#")
    if filename.endswith(".csv"):
        table = filename[:-4]
        require(table in bundle.tables and anchor in bundle.index(table), f"unresolved row evidence: {ref}", code='unresolved_evidence')
    else:
        require(filename in bundle.manifest["documents"], f"unlisted document evidence: {ref}", code='unresolved_evidence')
        text = bundle.documents[filename]
        require(bool(re.search(r"(?m)^#{1,6} " + re.escape(anchor) + r"\s*$", text)), f"unresolved document evidence: {ref}", code='unresolved_evidence')


def known_id(value):
    """Only expose syntactically valid identifiers in diagnostic locations."""
    return value if isinstance(value, str) and len(value) <= 4096 and re.fullmatch(r"[A-Za-z0-9_-]+", value) else None


def project_location(table, row, project_ids):
    # Attribution is deliberately conservative: direct references to unique
    # project IDs only. Shared records and indirect relationships remain null.
    candidate = row.get("id") if table == "projects" else row.get("project_id")
    candidate = known_id(candidate)
    if candidate is None:
        return None
    return candidate if candidate in project_ids else None


def record_context(bundle, table, row, **extra):
    location = bundle.row_locations.get(f"{table}.csv#{row['id']}", {})
    return issue_context(file=table + ".csv", record=location.get("record"),
                         record_id=row["id"], project_id=project_location(table, row, bundle.index("projects")),
                         **extra)


def validate_manifest(manifest, contract, synthetic_only):
    require(isinstance(manifest, dict), "manifest must be a JSON object", code="manifest_shape")
    require(manifest.get("schema_version") == contract["version"], "unsupported schema version",
            code="unsupported_schema", field="schema_version")
    require(type(manifest.get("synthetic")) is bool, "synthetic must be a boolean",
            code="invalid_boolean", field="synthetic")
    if synthetic_only:
        require(manifest["synthetic"], "fixture verifier accepts explicitly synthetic bundles only",
                code="synthetic_required", field="synthetic")
    for key in ("dataset_id", "source_coverage"):
        require(isinstance(manifest.get(key), str) and 0 < len(manifest[key].strip()) <= 4096,
                f"manifest {key} must be nonempty text (up to 4096 characters)", code="invalid_text", field=key)
    assumptions = manifest.get("assumptions")
    require(isinstance(assumptions, list) and len(assumptions) <= 50
            and all(isinstance(x, str) and 0 < len(x.strip()) <= 4096 for x in assumptions),
            "manifest assumptions must be a list of at most 50 nonempty strings",
            code="invalid_assumptions", field="assumptions")
    if "review_assertions" in manifest:
        assertions = manifest["review_assertions"]
        require(isinstance(assertions, dict) and set(assertions) <= set(ASSERTIONS)
                and all(type(v) is bool for v in assertions.values()),
                "review_assertions must contain only documented boolean fields",
                code="invalid_assertions", field="review_assertions")
    if not manifest["synthetic"]:
        assertions = manifest.get("review_assertions")
        require(isinstance(assertions, dict), "non-synthetic bundle requires review_assertions; see docs/cli.md",
                code="assertion_required", field="review_assertions")
        for key in ASSERTIONS:
            require(assertions.get(key) is True, f"review_assertions.{key} must be true; incomplete/unsupported review is blocked",
                    code="assertion_required", field="review_assertions." + key)
    require(manifest.get("currency") == "USD", "unsupported manifest currency", code="unsupported_currency", field="currency")
    require(manifest.get("tables") == list(contract["tables"]), "manifest table list differs from contract",
            code="invalid_table_list", field="tables")
    require(isinstance(manifest.get("documents"), list) and manifest["documents"], "documents must be listed",
            code="invalid_document_list", field="documents")
    require(len(manifest["documents"]) <= 20 and all(isinstance(x, str) for x in manifest["documents"]),
            "documents must contain at most 20 filenames", code="invalid_document_list", field="documents")
    require(len(set(manifest["documents"])) == len(manifest["documents"]), "duplicate document filename",
            code="duplicate_document", field="documents")
    dates = {}
    for key in ("coverage_start", "as_of", "coverage_end"):
        with issue_context(field=key):
            dates[key] = parse_day(manifest.get(key))
    require(dates["coverage_start"] <= dates["as_of"] <= dates["coverage_end"], "review cutoff outside declared coverage",
            code="invalid_coverage", field="as_of")


def load_bundle(root: Path = DEFAULT_BUNDLE, *, synthetic_only: bool = False) -> Bundle:
    root = root.resolve()
    with issue_context(file="schemas/csv-contract.json"):
        contract_data = (ROOT / "schemas/csv-contract.json").read_bytes()
        contract = parse_json(contract_data)
    captured, raw_inputs = {}, {}

    def capture(name):
        with issue_context(file=name):
            data = read_bytes(root, name)
        captured[name] = hashlib.sha256(data).hexdigest()
        raw_inputs[name] = data
        return data

    with issue_context(file="manifest.json"):
        manifest = parse_json(capture("manifest.json"))
        validate_manifest(manifest, contract, synthetic_only)
    documents = {}
    for name in manifest["documents"]:
        with issue_context(file="manifest.json", field="documents"):
            require(name.endswith(".md"), "fixture documents must be Markdown", code="unsupported_document")
            # Check unsafe names before assigning them to a diagnostic file field.
            require(name not in (".", "..") and not any(c in name for c in '/\\:#\x00')
                    and Path(name).name == name, "bundle files must be local basenames", code="unsafe_filename")
        with issue_context(file=name):
            documents[name] = capture(name).decode("utf-8-sig")
    tables, locations = {}, {}
    project_ids = set()
    for name, spec in contract["tables"].items():
        columns = spec["columns"]
        with issue_context(file=name + ".csv"):
            with io.StringIO(capture(name + ".csv").decode("utf-8-sig"), newline="") as stream:
                reader = csv.DictReader(stream, strict=True)
                require(reader.fieldnames == [c["name"] for c in columns], f"{name}: CSV headers differ from contract",
                        code="csv_headers", record=1)
                rows = []
                for line, raw in enumerate(reader, 2):
                    with issue_context(record=line, record_id=known_id(raw.get("id")),
                                       project_id=project_location(name, raw, project_ids)):
                        require(None not in raw, f"{name}:{line}: extra CSV cells", code="extra_csv_cells")
                        require(len(rows) < 10000, "fixture row limit exceeded", code="row_limit")
                        row = {}
                        for column in columns:
                            with issue_context(field=column["name"]):
                                row[column["name"]] = parse_cell(raw[column["name"]], column,
                                                               f"{name}:record {line}:{column['name']}")
                        rows.append(row)
                        locations[f"{name}.csv#{row['id']}"] = {"file": name + ".csv", "record": line, "id": row["id"]}
                tables[name] = rows
                if name == "projects":
                    project_ids = {key for key, count in Counter(r["id"] for r in rows).items() if count == 1}
    captured["schema:csv-contract.json"] = hashlib.sha256(contract_data).hexdigest()
    raw_inputs["schema:csv-contract.json"] = contract_data
    bundle = Bundle(root, manifest, tables, contract, captured, locations, documents,
                    raw_inputs=raw_inputs)
    validate(bundle)
    return bundle


def rate_for(bundle: Bundle, person: str, worked: date) -> Decimal:
    candidates = [r for r in bundle.tables["cost_rates"] if r["person_id"] == person and r["valid_from"] <= worked and (r["valid_to"] is None or worked < r["valid_to"])]
    require(len(candidates) == 1, f"missing or ambiguous cost rate: {person} on {worked}", code='cost_rate_unavailable')
    return candidates[0]["hourly_cost"]


def invoice_projects(bundle: Bundle) -> dict[str, str]:
    result = {}
    for line in bundle.tables["invoice_lines"]:
        with record_context(bundle, "invoice_lines", line):
            iid = line["invoice_id"]
            require(iid not in result or result[iid] == line["project_id"], f"multi-project invoice unsupported: {iid}", code='multi_project_invoice', field='project_id')
            result[iid] = line["project_id"]
    return result


def validate(bundle: Bundle) -> None:
    """Structural checks precede arithmetic; reject ambiguity instead of guessing."""
    bundle._indexes.clear()
    t = bundle.tables
    # Establish unique IDs in every table before building any reference index.
    for table, rows in t.items():
        seen_ids, seen_refs = set(), set()
        for record, row in enumerate(rows, 2):
            with issue_context(file=table + ".csv", record=record, record_id=row["id"]):
                require(row["id"] not in seen_ids, f"duplicate ID in {table}", code="duplicate_id", field="id")
                seen_ids.add(row["id"])
                if "source_ref" in row:
                    require(row["source_ref"] not in seen_refs, f"duplicate source record in {table}",
                            code="duplicate_source", field="source_ref")
                    seen_refs.add(row["source_ref"])
    for table, rows in t.items():
        for row in rows:
            with record_context(bundle, table, row):
                for column in bundle.contract["tables"][table]["columns"]:
                    with issue_context(field=column["name"]):
                        value = row[column["name"]]
                        if column.get("references") and value is not None:
                            require(value in bundle.index(column["references"]), f"dangling foreign key: {table}.{column['name']}={value}", code="missing_reference")
                        if column["type"] == "evidence":
                            resolve_evidence(bundle, value)
    # A row's diagnostic project_id is not a safe impact bound. Classify only
    # after ALL identities, relationships and evidence references are trusted.
    # Every error still blocks load/report/save; no rows are filtered here.
    try:
        _validate_business_rules(bundle)
    except ValidationError as exc:
        exc.impact = _classify_domain_impact(bundle, exc.issue)
        raise


def _validate_business_rules(bundle: Bundle) -> None:
    t = bundle.tables
    projects, entries, invoices, lines = (bundle.index(n) for n in ("projects", "time_entries", "invoices", "invoice_lines"))
    require(bool(projects), "at least one project is required", code='projects_required', file="projects.csv")
    cutoff = parse_day(bundle.manifest["as_of"])
    coverage_start = parse_day(bundle.manifest["coverage_start"])
    for p in projects.values():
        with record_context(bundle, "projects", p):
            require(coverage_start <= p["start_date"] <= p["completed_date"] <= cutoff, f"incomplete completed-project coverage: {p['id']}", code='project_coverage')
            require((p["agreed_fee"] is not None) == (p["billing_model"] == "fixed_fee"), f"fee inconsistent with billing model: {p['id']}", code='billing_model_fee', field='agreed_fee')
    for person in bundle.index("people"):
        rates = sorted((r for r in t["cost_rates"] if r["person_id"] == person), key=lambda r:r["valid_from"])
        for i, r in enumerate(rates):
            with record_context(bundle, "cost_rates", r):
                require(r["valid_to"] is None or r["valid_to"] > r["valid_from"], "invalid rate interval", code='rate_interval', field='valid_to')
                if i:
                    prev = rates[i-1]
                    require(prev["valid_to"] is not None and prev["valid_to"] <= r["valid_from"], f"overlapping cost rates: {person}", code='overlapping_rates')
    daily = defaultdict(lambda: ZERO)
    for e in entries.values():
        with record_context(bundle, "time_entries", e):
            p = projects[e["project_id"]]
            require(p["start_date"] <= e["work_date"] <= p["completed_date"], f"time outside project dates: {e['id']}", code='work_date_range', field='work_date')
            require(e["hours"] > 0, "recorded hours must be positive", code='positive_hours', field='hours')
            require(e["billing_hours"] <= 24, "billing hours exceed 24 per entry", code='billing_hours_limit', field='billing_hours')
            daily[e["person_id"], e["work_date"]] += e["hours"]
            require(daily[e["person_id"], e["work_date"]] <= 24, "more than 24 hours per person/date", code='daily_hours_limit', field='hours')
            rate_for(bundle, e["person_id"], e["work_date"])
            require((e["approved_on"] is not None) == (e["approval_status"] == "approved"), f"approval date/status mismatch: {e['id']}", code='approval_status_date', field='approved_on')
            require(e["approved_on"] is None or e["approved_on"] >= e["work_date"], f"approval precedes work: {e['id']}", code='approval_before_work', field='approved_on')
            if p["billing_model"] == "hourly" and e["billable"]:
                require(e["billing_rate"] is not None, "billable hourly entry missing rate", code='billing_rate_required', field='billing_rate')
            if p["billing_model"] == "fixed_fee":
                require(e["billing_rate"] is None, "fixed-fee fixture must not imply hourly billing", code='fixed_fee_hourly_rate', field='billing_rate')
    for x in t["expenses"]:
        with record_context(bundle, "expenses", x):
            p = projects[x["project_id"]]
            require(p["start_date"] <= x["incurred_on"] <= p["completed_date"], f"expense outside project dates: {x['id']}", code='expense_date_range', field='incurred_on')
    ip = invoice_projects(bundle)
    for iid, inv in invoices.items():
        with record_context(bundle, "invoices", inv):
            require(iid in ip, f"invoice has no lines: {iid}", code='invoice_lines_required')
            require(inv["client_id"] == projects[ip[iid]]["client_id"], f"invoice/project client mismatch: {iid}", code='invoice_client_mismatch', field='client_id')
            require(inv["due_on"] >= inv["issued_on"], f"due date before invoice issue: {iid}", code='invoice_due_date', field='due_on')
            require(inv["subtotal"] + inv["tax"] == inv["total"], f"invoice total mismatch: {iid}", code='invoice_total', field='total')
            require(sum((l["amount"] for l in lines.values() if l["invoice_id"] == iid), ZERO) == inv["subtotal"], f"invoice lines do not sum to subtotal: {iid}", code='invoice_line_total', field='subtotal')
    covered = defaultdict(lambda: ZERO)
    line_values = defaultdict(lambda: ZERO)
    for link in t["billing_links"]:
        with record_context(bundle, "billing_links", link):
            entry, line = entries[link["time_entry_id"]], lines[link["invoice_line_id"]]
            inv = invoices[line["invoice_id"]]
            require(entry["project_id"] == line["project_id"], f"cross-project billing link: {link['id']}", code='billing_project_mismatch')
            require(projects[entry["project_id"]]["billing_model"] == "hourly" and entry["billable"] and entry["billing_rate"] is not None, "billing link must cover billable hourly work", code='billing_link_eligibility', field='time_entry_id')
            require(link["covered_hours"] > 0, "covered hours must be positive", code='positive_coverage', field='covered_hours')
            require(link["confirmed_on"] >= max(entry["work_date"], inv["issued_on"]), "billing link confirmation precedes evidence", code='billing_confirmation_date', field='confirmed_on')
            if inv["status"] == "issued":
                covered[entry["id"]] += link["covered_hours"]
                line_values[line["id"]] += money(link["covered_hours"] * entry["billing_rate"])
    for eid, hours in covered.items():
        with record_context(bundle, "time_entries", entries[eid]):
            require(hours <= entries[eid]["billing_hours"], f"covered hours exceed billing hours: {eid}", code='billing_hours_overallocated', field='billing_hours')
    for lid, amount in line_values.items():
        with record_context(bundle, "invoice_lines", lines[lid]):
            require(amount <= lines[lid]["amount"], f"covered work exceeds invoice line amount: {lid}", code='invoice_line_overallocated', field='amount')
    for c in t["credits"]:
        with record_context(bundle, "credits", c):
            require(c["subtotal"] + c["tax"] == c["total"], f"credit total mismatch: {c['id']}", code='credit_total', field='total')
            require(c["client_id"] == projects[c["project_id"]]["client_id"], f"credit/project client mismatch: {c['id']}", code='credit_client_mismatch', field='client_id')
    invoice_applied = defaultdict(lambda: ZERO)
    clients = {p["client_id"] for p in projects.values()}
    for sources, allocations, fk, event_date in (("payments", "payment_allocations", "payment_id", "received_on"), ("credits", "credit_allocations", "credit_id", "issued_on")):
        source_index = bundle.index(sources)
        totals = defaultdict(lambda: ZERO)
        for s in source_index.values():
            with record_context(bundle, sources, s):
                require(s["client_id"] in clients, "unknown customer on settlement source", code='unknown_settlement_client', field='client_id')
        for a in t[allocations]:
            with record_context(bundle, allocations, a):
                source, inv = source_index[a[fk]], invoices[a["invoice_id"]]
                require(a["amount"] > 0, "allocation amount must be positive", code='positive_allocation', field='amount')
                require(inv["status"] == "issued", f"allocation to non-issued invoice: {allocations}#{a['id']}", code='invoice_not_issued', field='invoice_id')
                require(source["client_id"] == inv["client_id"], f"settlement client mismatch: {allocations}#{a['id']}", code='settlement_client_mismatch')
                require(a["applied_on"] >= max(source[event_date], inv["issued_on"]), f"allocation precedes receipt/issue: {allocations}#{a['id']}", code='allocation_date', field='applied_on')
                if sources == "credits":
                    require(source["project_id"] == ip[inv["id"]], "credit price attribution differs from invoice project", code='credit_project_mismatch')
                totals[source["id"]] += a["amount"]
                invoice_applied[inv["id"]] += a["amount"]
        for sid, amount in totals.items():
            with record_context(bundle, sources, source_index[sid]):
                require(amount <= source_index[sid]["amount" if sources == "payments" else "total"], f"allocations exceed source amount: {sources}#{sid}", code='source_overallocated')
    for iid, amount in invoice_applied.items():
        with record_context(bundle, "invoices", invoices[iid]):
            require(amount <= invoices[iid]["total"], f"combined settlements exceed invoice total: {iid}", code='invoice_overallocated', field='total')
