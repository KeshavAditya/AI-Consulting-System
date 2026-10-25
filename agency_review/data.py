"""Canonical bundle loading and validation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "examples" / "synthetic_agency"
CENT = Decimal("0.01")
ZERO = Decimal("0")
ASSERTIONS = (
    "complete_project_costs", "complete_billing_and_settlements",
    "reviewed_billing_links", "snapshot_at_cutoff", "supported_transactions_only",
)


class ValidationError(ValueError):
    """An input violates the documented contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def display(value: Decimal) -> str:
    return format(money(value), ".2f")


def parse_day(value: str) -> date:
    require(isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), "date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"invalid date: {value}") from exc


def parse_cell(raw: str, column: dict, location: str):
    require(isinstance(raw, str), f"{location}: missing CSV cell")
    if raw == "":
        require(column["nullable"], f"{location}: required value is blank")
        return None
    kind = column["type"]
    if kind in ("money", "decimal"):
        pattern = r"\d{1,12}\.\d{2}" if kind == "money" else r"\d{1,12}(?:\.\d{1,4})?"
        require(len(raw) <= 24 and bool(re.fullmatch(pattern, raw)), f"{location}: invalid {kind}")
        return Decimal(raw)
    if kind == "date":
        try:
            return parse_day(raw)
        except ValidationError as exc:
            raise ValidationError(f"{location}: {exc}") from exc
    if kind == "boolean":
        require(raw in ("true", "false"), f"{location}: invalid boolean")
        return raw == "true"
    if kind == "enum":
        require(raw in column["enum"], f"{location}: unsupported value {raw!r}")
    if kind == "id":
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]+", raw)), f"{location}: invalid ID")
    require(raw.strip() != "", f"{location}: whitespace-only value")
    require(len(raw) <= 4096 and not any(ord(c) < 32 and c not in "\n\r\t" for c in raw),
            f"{location}: text exceeds limit or contains control characters")
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

    def index(self, table: str) -> dict[str, dict]:
        if table not in self._indexes:
            self._indexes[table] = {row["id"]: row for row in self.tables[table]}
        return self._indexes[table]


def local_file(root: Path, name: str) -> Path:
    require(isinstance(name, str) and bool(name) and name not in (".", "..")
            and not any(c in name for c in '/\\:#\x00') and Path(name).name == name,
            "bundle files must be local basenames")
    require(not (root / name).is_symlink(), f"symlink bundle file unsupported: {name}")
    path = (root / name).resolve()
    require(path.parent == root.resolve() and path.is_file(), f"missing or unsafe bundle file: {name}")
    require(path.stat().st_size <= 2_000_000, f"bundle file too large: {name}")
    return path


def read_bytes(root: Path, name: str) -> bytes:
    # Bound actual reads as well as stat size; no unbounded read if a file grows.
    with local_file(root, name).open("rb") as stream:
        data = stream.read(2_000_001)
    require(len(data) <= 2_000_000, f"bundle file too large: {name}")
    return data


def parse_json(data: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique)


def resolve_evidence(bundle: Bundle, ref: str) -> None:
    require(isinstance(ref, str) and ref.count("#") == 1, f"invalid evidence reference: {ref}")
    filename, anchor = ref.split("#")
    if filename.endswith(".csv"):
        table = filename[:-4]
        require(table in bundle.tables and anchor in bundle.index(table), f"unresolved row evidence: {ref}")
    else:
        require(filename in bundle.manifest["documents"], f"unlisted document evidence: {ref}")
        text = bundle.documents[filename]
        require(bool(re.search(r"(?m)^#{1,6} " + re.escape(anchor) + r"\s*$", text)), f"unresolved document evidence: {ref}")


def load_bundle(root: Path = DEFAULT_BUNDLE, *, synthetic_only: bool = False) -> Bundle:
    root = root.resolve()
    contract_data = (ROOT / "schemas/csv-contract.json").read_bytes()
    contract = parse_json(contract_data)
    captured = {}

    def capture(name):
        data = read_bytes(root, name)
        captured[name] = hashlib.sha256(data).hexdigest()
        return data

    manifest = parse_json(capture("manifest.json"))
    require(isinstance(manifest, dict), "manifest must be a JSON object")
    require(manifest.get("schema_version") == contract["version"], "unsupported schema version")
    require(type(manifest.get("synthetic")) is bool, "synthetic must be a boolean")
    if synthetic_only:
        require(manifest["synthetic"], "fixture verifier accepts explicitly synthetic bundles only")
    for key in ("dataset_id", "source_coverage"):
        require(isinstance(manifest.get(key), str) and 0 < len(manifest[key].strip()) <= 4096,
                f"manifest {key} must be nonempty text (up to 4096 characters)")
    assumptions = manifest.get("assumptions")
    require(isinstance(assumptions, list) and len(assumptions) <= 50
            and all(isinstance(x, str) and 0 < len(x.strip()) <= 4096 for x in assumptions),
            "manifest assumptions must be a list of at most 50 nonempty strings")
    if "review_assertions" in manifest:
        assertions = manifest["review_assertions"]
        require(isinstance(assertions, dict) and set(assertions) <= set(ASSERTIONS)
                and all(type(v) is bool for v in assertions.values()),
                "review_assertions must contain only documented boolean fields")
    if not manifest["synthetic"]:
        assertions = manifest.get("review_assertions")
        require(isinstance(assertions, dict), "non-synthetic bundle requires review_assertions; see docs/cli.md")
        for key in ASSERTIONS:
            require(assertions.get(key) is True, f"review_assertions.{key} must be true; incomplete/unsupported review is blocked")
    require(manifest.get("currency") == "USD", "unsupported manifest currency")
    require(manifest.get("tables") == list(contract["tables"]), "manifest table list differs from contract")
    require(isinstance(manifest.get("documents"), list) and manifest["documents"], "documents must be listed")
    require(len(manifest["documents"]) <= 20 and all(isinstance(x, str) for x in manifest["documents"]),
            "documents must contain at most 20 filenames")
    require(len(set(manifest["documents"])) == len(manifest["documents"]), "duplicate document filename")
    start, cutoff, end = (parse_day(manifest.get(key)) for key in ("coverage_start", "as_of", "coverage_end"))
    require(start <= cutoff <= end, "review cutoff outside declared coverage")
    documents = {}
    for name in manifest["documents"]:
        require(name.endswith(".md"), "fixture documents must be Markdown")
        documents[name] = capture(name).decode("utf-8-sig")
    tables, locations = {}, {}
    for name, spec in contract["tables"].items():
        columns = spec["columns"]
        with io.StringIO(capture(name + ".csv").decode("utf-8-sig"), newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            require(reader.fieldnames == [c["name"] for c in columns], f"{name}: CSV headers differ from contract")
            rows = []
            for line, raw in enumerate(reader, 2):
                require(None not in raw, f"{name}:{line}: extra CSV cells")
                require(len(rows) < 10000, "fixture row limit exceeded")
                row = {c["name"]: parse_cell(raw[c["name"]], c, f"{name}:record {line}:{c['name']}") for c in columns}
                rows.append(row)
                locations[f"{name}.csv#{row['id']}"] = {"file": name + ".csv", "record": line, "id": row["id"]}
            tables[name] = rows
    captured["schema:csv-contract.json"] = hashlib.sha256(contract_data).hexdigest()
    bundle = Bundle(root, manifest, tables, contract, captured, locations, documents)
    validate(bundle)
    return bundle


def rate_for(bundle: Bundle, person: str, worked: date) -> Decimal:
    candidates = [r for r in bundle.tables["cost_rates"] if r["person_id"] == person and r["valid_from"] <= worked and (r["valid_to"] is None or worked < r["valid_to"])]
    require(len(candidates) == 1, f"missing or ambiguous cost rate: {person} on {worked}")
    return candidates[0]["hourly_cost"]


def invoice_projects(bundle: Bundle) -> dict[str, str]:
    result = {}
    for line in bundle.tables["invoice_lines"]:
        iid = line["invoice_id"]
        require(iid not in result or result[iid] == line["project_id"], f"multi-project invoice unsupported: {iid}")
        result[iid] = line["project_id"]
    return result


def validate(bundle: Bundle) -> None:
    """Structural checks precede arithmetic; reject ambiguity instead of guessing."""
    bundle._indexes.clear()
    t = bundle.tables
    for table, rows in t.items():
        ids = [row["id"] for row in rows]
        require(len(ids) == len(set(ids)), f"duplicate ID in {table}")
        refs = [r["source_ref"] for r in rows if "source_ref" in r]
        require(len(refs) == len(set(refs)), f"duplicate source record in {table}")
        for row in rows:
            for column in bundle.contract["tables"][table]["columns"]:
                value = row[column["name"]]
                if column.get("references") and value is not None:
                    require(value in bundle.index(column["references"]), f"dangling foreign key: {table}.{column['name']}={value}")
                if column["type"] == "evidence":
                    resolve_evidence(bundle, value)
    projects, entries, invoices, lines = (bundle.index(n) for n in ("projects", "time_entries", "invoices", "invoice_lines"))
    require(bool(projects), "at least one project is required")
    cutoff = parse_day(bundle.manifest["as_of"])
    coverage_start = parse_day(bundle.manifest["coverage_start"])
    for p in projects.values():
        require(coverage_start <= p["start_date"] <= p["completed_date"] <= cutoff, f"incomplete completed-project coverage: {p['id']}")
        require((p["agreed_fee"] is not None) == (p["billing_model"] == "fixed_fee"), f"fee inconsistent with billing model: {p['id']}")
    for person in bundle.index("people"):
        rates = sorted((r for r in t["cost_rates"] if r["person_id"] == person), key=lambda r:r["valid_from"])
        for i, r in enumerate(rates):
            require(r["valid_to"] is None or r["valid_to"] > r["valid_from"], "invalid rate interval")
            if i:
                prev = rates[i-1]
                require(prev["valid_to"] is not None and prev["valid_to"] <= r["valid_from"], f"overlapping cost rates: {person}")
    daily = defaultdict(lambda: ZERO)
    for e in entries.values():
        p = projects[e["project_id"]]
        require(p["start_date"] <= e["work_date"] <= p["completed_date"], f"time outside project dates: {e['id']}")
        require(e["hours"] > 0, "recorded hours must be positive")
        require(e["billing_hours"] <= 24, "billing hours exceed 24 per entry")
        daily[e["person_id"], e["work_date"]] += e["hours"]
        require(daily[e["person_id"], e["work_date"]] <= 24, "more than 24 hours per person/date")
        rate_for(bundle, e["person_id"], e["work_date"])
        require((e["approved_on"] is not None) == (e["approval_status"] == "approved"), f"approval date/status mismatch: {e['id']}")
        require(e["approved_on"] is None or e["approved_on"] >= e["work_date"], f"approval precedes work: {e['id']}")
        if p["billing_model"] == "hourly" and e["billable"]:
            require(e["billing_rate"] is not None, "billable hourly entry missing rate")
        if p["billing_model"] == "fixed_fee":
            require(e["billing_rate"] is None, "fixed-fee fixture must not imply hourly billing")
    for x in t["expenses"]:
        p = projects[x["project_id"]]
        require(p["start_date"] <= x["incurred_on"] <= p["completed_date"], f"expense outside project dates: {x['id']}")
    ip = invoice_projects(bundle)
    for iid, inv in invoices.items():
        require(iid in ip, f"invoice has no lines: {iid}")
        require(inv["client_id"] == projects[ip[iid]]["client_id"], f"invoice/project client mismatch: {iid}")
        require(inv["due_on"] >= inv["issued_on"], f"due date before invoice issue: {iid}")
        require(inv["subtotal"] + inv["tax"] == inv["total"], f"invoice total mismatch: {iid}")
        require(sum((l["amount"] for l in lines.values() if l["invoice_id"] == iid), ZERO) == inv["subtotal"], f"invoice lines do not sum to subtotal: {iid}")
    covered = defaultdict(lambda: ZERO)
    line_values = defaultdict(lambda: ZERO)
    for link in t["billing_links"]:
        entry, line = entries[link["time_entry_id"]], lines[link["invoice_line_id"]]
        inv = invoices[line["invoice_id"]]
        require(entry["project_id"] == line["project_id"], f"cross-project billing link: {link['id']}")
        require(projects[entry["project_id"]]["billing_model"] == "hourly" and entry["billable"] and entry["billing_rate"] is not None, "billing link must cover billable hourly work")
        require(link["covered_hours"] > 0, "covered hours must be positive")
        require(link["confirmed_on"] >= max(entry["work_date"], inv["issued_on"]), "billing link confirmation precedes evidence")
        if inv["status"] == "issued":
            covered[entry["id"]] += link["covered_hours"]
            line_values[line["id"]] += money(link["covered_hours"] * entry["billing_rate"])
    for eid, hours in covered.items():
        require(hours <= entries[eid]["billing_hours"], f"covered hours exceed billing hours: {eid}")
    for lid, amount in line_values.items():
        require(amount <= lines[lid]["amount"], f"covered work exceeds invoice line amount: {lid}")
    for c in t["credits"]:
        require(c["subtotal"] + c["tax"] == c["total"], f"credit total mismatch: {c['id']}")
        require(c["client_id"] == projects[c["project_id"]]["client_id"], f"credit/project client mismatch: {c['id']}")
    invoice_applied = defaultdict(lambda: ZERO)
    clients = {p["client_id"] for p in projects.values()}
    for sources, allocations, fk, event_date in (("payments", "payment_allocations", "payment_id", "received_on"), ("credits", "credit_allocations", "credit_id", "issued_on")):
        source_index = bundle.index(sources)
        totals = defaultdict(lambda: ZERO)
        for s in source_index.values():
            require(s["client_id"] in clients, "unknown customer on settlement source")
        for a in t[allocations]:
            source, inv = source_index[a[fk]], invoices[a["invoice_id"]]
            require(a["amount"] > 0, "allocation amount must be positive")
            require(inv["status"] == "issued", f"allocation to non-issued invoice: {allocations}#{a['id']}")
            require(source["client_id"] == inv["client_id"], f"settlement client mismatch: {allocations}#{a['id']}")
            require(a["applied_on"] >= max(source[event_date], inv["issued_on"]), f"allocation precedes receipt/issue: {allocations}#{a['id']}")
            if sources == "credits":
                require(source["project_id"] == ip[inv["id"]], "credit price attribution differs from invoice project")
            totals[source["id"]] += a["amount"]
            invoice_applied[inv["id"]] += a["amount"]
        for sid, amount in totals.items():
            require(amount <= source_index[sid]["amount" if sources == "payments" else "total"], f"allocations exceed source amount: {sources}#{sid}")
    for iid, amount in invoice_applied.items():
        require(amount <= invoices[iid]["total"], f"combined settlements exceed invoice total: {iid}")
