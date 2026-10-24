"""Validate canonical synthetic fixtures; not a production importer or AI audit.

Only Python's standard library is used. The expected answer key is loaded AFTER
calculations and never participates in them. See docs/business-rules.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "examples" / "synthetic_agency"
CENT = Decimal("0.01")
ZERO = Decimal("0")


class ValidationError(ValueError):
    """A fixture violates the documented contract."""


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
        return parse_day(raw)
    if kind == "boolean":
        require(raw in ("true", "false"), f"{location}: invalid boolean")
        return raw == "true"
    if kind == "enum":
        require(raw in column["enum"], f"{location}: unsupported value {raw!r}")
    if kind == "id":
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]+", raw)), f"{location}: invalid ID")
    require(raw.strip() != "", f"{location}: whitespace-only value")
    return raw


@dataclass
class Bundle:
    root: Path
    manifest: dict
    tables: dict[str, list[dict]]
    contract: dict

    def index(self, table: str) -> dict[str, dict]:
        return {row["id"]: row for row in self.tables[table]}


def local_file(root: Path, name: str) -> Path:
    require(isinstance(name, str) and Path(name).name == name, "bundle files must be local basenames")
    path = (root / name).resolve()
    require(path.parent == root.resolve() and path.is_file(), f"missing or unsafe bundle file: {name}")
    require(path.stat().st_size <= 2_000_000, f"fixture file too large: {name}")
    return path


def resolve_evidence(bundle: Bundle, ref: str) -> None:
    require(isinstance(ref, str) and ref.count("#") == 1, f"invalid evidence reference: {ref}")
    filename, anchor = ref.split("#")
    if filename.endswith(".csv"):
        table = filename[:-4]
        require(table in bundle.tables and anchor in bundle.index(table), f"unresolved row evidence: {ref}")
    else:
        require(filename in bundle.manifest["documents"], f"unlisted document evidence: {ref}")
        text = local_file(bundle.root, filename).read_text(encoding="utf-8")
        require(bool(re.search(r"(?m)^#{1,6} " + re.escape(anchor) + r"\s*$", text)), f"unresolved document evidence: {ref}")


def load_bundle(root: Path = DEFAULT_BUNDLE) -> Bundle:
    root = root.resolve()
    contract = json.loads((ROOT / "schemas/csv-contract.json").read_text(encoding="utf-8"))
    manifest = json.loads(local_file(root, "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema_version") == contract["version"], "unsupported schema version")
    require(manifest.get("synthetic") is True, "fixture verifier accepts explicitly synthetic bundles only")
    require(manifest.get("currency") == "USD", "unsupported manifest currency")
    require(manifest.get("tables") == list(contract["tables"]), "manifest table list differs from contract")
    require(isinstance(manifest.get("documents"), list) and manifest["documents"], "documents must be listed")
    start, cutoff, end = (parse_day(manifest.get(key)) for key in ("coverage_start", "as_of", "coverage_end"))
    require(start <= cutoff <= end, "review cutoff outside declared coverage")
    for name in manifest["documents"]:
        require(name.endswith(".md"), "fixture documents must be Markdown")
        local_file(root, name)
    tables = {}
    for name, spec in contract["tables"].items():
        columns = spec["columns"]
        with local_file(root, name + ".csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == [c["name"] for c in columns], f"{name}: CSV headers differ from contract")
            rows = []
            for line, raw in enumerate(reader, 2):
                require(None not in raw, f"{name}:{line}: extra CSV cells")
                require(len(rows) < 10000, "fixture row limit exceeded")
                rows.append({c["name"]: parse_cell(raw[c["name"]], c, f"{name}:{line}:{c['name']}") for c in columns})
            tables[name] = rows
    bundle = Bundle(root, manifest, tables, contract)
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
        require((e["approved_on"] is not None) == (e["approval_status"] == "approved"), "approval date/status mismatch")
        require(e["approved_on"] is None or e["approved_on"] >= e["work_date"], "approval precedes work")
        if p["billing_model"] == "hourly" and e["billable"]:
            require(e["billing_rate"] is not None, "billable hourly entry missing rate")
        if p["billing_model"] == "fixed_fee":
            require(e["billing_rate"] is None, "fixed-fee fixture must not imply hourly billing")
    for x in t["expenses"]:
        p = projects[x["project_id"]]
        require(p["start_date"] <= x["incurred_on"] <= p["completed_date"], "expense outside project dates")
    ip = invoice_projects(bundle)
    for iid, inv in invoices.items():
        require(iid in ip, f"invoice has no lines: {iid}")
        require(inv["client_id"] == projects[ip[iid]]["client_id"], "invoice/project client mismatch")
        require(inv["due_on"] >= inv["issued_on"], "due date before invoice issue")
        require(inv["subtotal"] + inv["tax"] == inv["total"], "invoice total mismatch")
        require(sum((l["amount"] for l in lines.values() if l["invoice_id"] == iid), ZERO) == inv["subtotal"], "invoice lines do not sum to subtotal")
    covered = defaultdict(lambda: ZERO)
    line_values = defaultdict(lambda: ZERO)
    for link in t["billing_links"]:
        entry, line = entries[link["time_entry_id"]], lines[link["invoice_line_id"]]
        inv = invoices[line["invoice_id"]]
        require(entry["project_id"] == line["project_id"], "cross-project billing link")
        require(projects[entry["project_id"]]["billing_model"] == "hourly" and entry["billable"] and entry["billing_rate"] is not None, "billing link must cover billable hourly work")
        require(link["covered_hours"] > 0, "covered hours must be positive")
        require(link["confirmed_on"] >= max(entry["work_date"], inv["issued_on"]), "billing link confirmation precedes evidence")
        if inv["status"] == "issued":
            covered[entry["id"]] += link["covered_hours"]
            line_values[line["id"]] += money(link["covered_hours"] * entry["billing_rate"])
    for eid, hours in covered.items():
        require(hours <= entries[eid]["billing_hours"], "covered hours exceed billing hours")
    for lid, amount in line_values.items():
        require(amount <= lines[lid]["amount"], "covered work exceeds invoice line amount")
    for c in t["credits"]:
        require(c["subtotal"] + c["tax"] == c["total"], "credit total mismatch")
        require(c["client_id"] == projects[c["project_id"]]["client_id"], "credit/project client mismatch")
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
            require(inv["status"] == "issued", "allocation to non-issued invoice")
            require(source["client_id"] == inv["client_id"], "settlement client mismatch")
            require(a["applied_on"] >= max(source[event_date], inv["issued_on"]), "allocation precedes receipt/issue")
            if sources == "credits":
                require(source["project_id"] == ip[inv["id"]], "credit price attribution differs from invoice project")
            totals[source["id"]] += a["amount"]
            invoice_applied[inv["id"]] += a["amount"]
        for sid, amount in totals.items():
            require(amount <= source_index[sid]["amount" if sources == "payments" else "total"], "allocations exceed source amount")
    for iid, amount in invoice_applied.items():
        require(amount <= invoices[iid]["total"], "combined settlements exceed invoice total")


def calculate(bundle: Bundle, as_of: date | None = None) -> dict[str, dict]:
    """Deterministic reference arithmetic, assuming validate() has succeeded."""
    cutoff = as_of or parse_day(bundle.manifest["as_of"])
    t, results = bundle.tables, {}
    invoices, lines = bundle.index("invoices"), bundle.index("invoice_lines")
    ip = invoice_projects(bundle)
    active = {iid: inv for iid, inv in invoices.items() if inv["status"] == "issued" and inv["issued_on"] <= cutoff}
    cash, credited = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for sources, allocations, fk, event_date, output in (("payments", "payment_allocations", "payment_id", "received_on", cash), ("credits", "credit_allocations", "credit_id", "issued_on", credited)):
        index = bundle.index(sources)
        for a in t[allocations]:
            if a["invoice_id"] in active and a["applied_on"] <= cutoff and index[a[fk]][event_date] <= cutoff:
                output[a["invoice_id"]] += a["amount"]
    coverage = defaultdict(lambda: ZERO)
    for link in t["billing_links"]:
        if link["confirmed_on"] <= cutoff and lines[link["invoice_line_id"]]["invoice_id"] in active:
            coverage[link["time_entry_id"]] += link["covered_hours"]
    for p in t["projects"]:
        pid = p["id"]
        entries = [e for e in t["time_entries"] if e["project_id"] == pid and e["work_date"] <= cutoff]
        hours = sum((e["hours"] for e in entries), ZERO)
        labor = sum((money(e["hours"] * rate_for(bundle, e["person_id"], e["work_date"])) for e in entries), ZERO)
        expenses = sum((x["amount"] for x in t["expenses"] if x["project_id"] == pid and x["incurred_on"] <= cutoff), ZERO)
        cost = labor + expenses
        hourly = p["billing_model"] == "hourly"
        eligible = [e for e in entries if e["billable"] and e["approval_status"] == "approved" and e["approved_on"] <= cutoff]
        value = sum((money(e["billing_hours"] * e["billing_rate"]) for e in eligible), ZERO) if hourly else None
        # Subtract rounded covered value from the rounded full entry value.
        # Rounding the remainder independently can invent a cent on split work.
        candidate = sum((money(e["billing_hours"] * e["billing_rate"]) - money(coverage[e["id"]] * e["billing_rate"]) for e in eligible), ZERO) if hourly else None
        price_credits = sum((c["subtotal"] for c in t["credits"] if c["project_id"] == pid and c["issued_on"] <= cutoff), ZERO)
        basis = (value if hourly else p["agreed_fee"]) - price_credits
        require(basis >= 0, "credits exceed project pricing basis")
        project_invoices = {iid:inv for iid, inv in active.items() if ip[iid] == pid}
        balance, overdue, days = ZERO, ZERO, 0
        for iid, inv in project_invoices.items():
            remaining = inv["total"] - cash[iid] - credited[iid]
            require(remaining >= 0, "negative invoice balance")
            late = max(0, (cutoff - inv["due_on"]).days) if remaining > 0 else 0
            balance += remaining
            overdue += remaining if late else ZERO
            days = max(days, late)
        results[pid] = {
            "hours": display(hours), "labor_cost": display(labor), "direct_expenses": display(expenses),
            "delivery_cost": display(cost), "approved_hourly_value": display(value) if hourly else None,
            "pricing_basis": display(basis),
            "delivery_margin_pct": display((basis-cost)/basis*100) if basis > 0 and p["completed_date"] <= cutoff else None,
            "uninvoiced_hourly_candidate": display(candidate) if hourly else None,
            "billed_ex_tax": display(sum((inv["subtotal"] for inv in project_invoices.values()), ZERO)),
            "allocated_cash": display(sum((cash[iid] for iid in project_invoices), ZERO)),
            "balance": display(balance), "overdue_balance": display(overdue), "max_days_overdue": days,
            "cost_variance": display(cost - p["budget_cost"]),
        }
    return results


def verify_expected(bundle: Bundle, actual: dict) -> None:
    expected = json.loads(local_file(bundle.root, "expected.json").read_text(encoding="utf-8"))
    require(expected.get("as_of") == bundle.manifest["as_of"], "answer key cutoff mismatch")
    require(set(expected["projects"]) == set(actual), "answer key project set mismatch")
    for pid in actual:
        require(actual[pid] == expected["projects"][pid], f"expected metrics mismatch for {pid}: actual={actual[pid]}, expected={expected['projects'][pid]}")
    rubrics = expected.get("narrative_expectations", [])
    require(len(rubrics) == len(actual) and {r["project_id"] for r in rubrics} == set(actual), "narrative rubric project set mismatch")
    for rubric in rubrics:
        require(bool(rubric.get("must_say")) and bool(rubric.get("must_not_say")) and bool(rubric.get("evidence")), "incomplete narrative rubric")
        for ref in rubric["evidence"]:
            resolve_evidence(bundle, ref)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, nargs="?", default=DEFAULT_BUNDLE)
    args = parser.parse_args()
    try:
        bundle = load_bundle(args.bundle)
        actual = calculate(bundle)
        verify_expected(bundle, actual)
    except (ValidationError, OSError, csv.Error, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {len(bundle.tables)} tables, {sum(len(rows) for rows in bundle.tables.values())} rows, {len(actual)} projects; expected calculations and evidence references verified.")
    print("Narrative quality, model behavior, and real vendor import compatibility are not evaluated by this check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
