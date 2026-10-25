"""Evidence-backed deterministic findings and escaped Markdown output."""
from __future__ import annotations

import hashlib
import html
import json
import re
from decimal import Decimal

from .calculations import RULE_VERSION, calculate_details
from .data import ZERO, Bundle, display, parse_day, resolve_evidence

REPORT_VERSION = "0.1"
LIMITATIONS = [
    "This is a deterministic management review, not an AI-generated audit or an accounting opinion.",
    "Delivery margin uses the stated pricing basis and direct costs; it excludes overhead and is not net profit or recognized revenue.",
    "Input completeness, agreement terms, and reviewed billing links are supplied assertions, not independently verified facts.",
    "A billing candidate is a reconciliation question, not permission to invoice. Confirm external invoices, credits, caps, discounts, acceptance, and disputes first.",
    "Cost overruns do not establish scope creep or a right to charge more on fixed-fee work.",
    "Current invoice status cannot reconstruct past status changes. Only the manifest cutoff is supported by the CLI.",
    "Amounts across findings must not be summed as money recovered or savings. Credits are not cash.",
    "Document headings are checked for existence; agreement meaning and document effective dates are not interpreted.",
    "USD and completed projects only. Vendor export mapping, refunds, reversals, retainers, multi-project invoices, and tax calculation are unsupported.",
]
FORMULAS = {
    "hours": "Sum recorded work hours through cutoff; summary rounded to 2 decimals; exact hours in work details.",
    "labor_cost": "Sum ROUND_HALF_UP(recorded hours × effective hourly cost, 2) per entry.",
    "direct_expenses": "Sum dated direct expense amounts through cutoff.",
    "delivery_cost": "Labor cost + direct expenses.",
    "approved_hourly_value": "Sum ROUND_HALF_UP(billing hours × rate, 2) for approved billable hourly entries through cutoff.",
    "pricing_basis": "Approved hourly value or agreed fixed fee, less project-attributed pre-tax credits issued through cutoff.",
    "delivery_margin_pct": "100 × (pricing basis − delivery cost) / pricing basis; null for zero basis or incomplete project.",
    "uninvoiced_hourly_candidate": "For each eligible entry: rounded full value − rounded confirmed covered value; sum. Null for fixed fee.",
    "billed_ex_tax": "Sum pre-tax subtotals of issued invoices through cutoff, before credits.",
    "allocated_cash": "Sum payment amounts allocated to issued invoices by cutoff, received by cutoff.",
    "balance": "Sum issued invoice gross totals − eligible cash allocations − eligible credit allocations.",
    "overdue_balance": "Sum positive invoice balances where due date is before cutoff.",
    "max_days_overdue": "Maximum days past due among issued invoices with positive balances; otherwise zero.",
    "cost_variance": "Delivery cost − original direct cost budget; positive is over budget.",
}


def references(items, key="evidence"):
    return sorted({ref for item in items for ref in item[key]})


def metric_evidence(pid, detail):
    project = [f"projects.csv#{pid}"]
    work = references(detail["work"], "cost_evidence")
    billing = references(detail["work"], "billing_evidence")
    expenses = references(detail["expenses"])
    credits = references(detail["price_credits"])
    invoice = references(detail["invoices"])
    settlements = references([s for inv in detail["invoices"] for s in inv["settlements"]])
    costs = project + work + expenses
    basis = project + billing + credits
    balances = project + invoice + settlements
    return {
        "hours": project + work, "labor_cost": project + work, "direct_expenses": project + expenses,
        "delivery_cost": costs, "approved_hourly_value": project + billing,
        "pricing_basis": basis, "delivery_margin_pct": costs + basis,
        "uninvoiced_hourly_candidate": project + billing,
        "billed_ex_tax": project + invoice, "allocated_cash": balances,
        "balance": balances, "overdue_balance": balances,
        "max_days_overdue": balances, "cost_variance": costs,
    }


def finding(kind, identifier, project_id, title, fact, amount, evidence, metrics, uncertainty, owner, action):
    return {
        "id": identifier, "type": kind, "project_id": project_id,
        "status": "review_required", "title": title, "fact": fact,
        "amount": amount, "currency": "USD", "metric_ids": metrics,
        "evidence": sorted(set(evidence)), "uncertainty": uncertainty,
        "action": {"owner_role": owner, "next_step": action},
    }


def build_report(bundle: Bundle) -> dict:
    """No expected answers or source document prose enters generated explanations."""
    details = calculate_details(bundle)
    identity = {"report_version": REPORT_VERSION, "rule_version": RULE_VERSION,
                "as_of": bundle.manifest["as_of"], "input_hashes": bundle.file_hashes}
    snapshot = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    projects, findings = [], []
    for pid in sorted(details):
        p = bundle.index("projects")[pid]
        detail = details[pid]
        values = detail["metrics"]
        evidence = metric_evidence(pid, detail)
        metrics = {}
        for name, value in values.items():
            unit = "USD"
            if name == "hours":
                unit = "hours"
            elif name == "delivery_margin_pct":
                unit = "percent"
            elif name == "max_days_overdue":
                unit = "days"
            metrics[name] = {"id": f"{pid}.{name}", "value": value, "unit": unit,
                             "formula": FORMULAS[name], "evidence": sorted(set(evidence[name]))}
        if values["uninvoiced_hourly_candidate"] is not None and Decimal(values["uninvoiced_hourly_candidate"]) > 0:
            candidates = [w for w in detail["work"] if Decimal(w["candidate_value"]) > 0]
            findings.append(finding(
                "billing_candidate", f"{pid}.billing_candidate", pid, "Reconcile approved work against invoices",
                "Approved hourly work has value not covered by the supplied confirmed invoice links.",
                values["uninvoiced_hourly_candidate"], [f"projects.csv#{pid}", p["agreement_ref"], *references(candidates, "billing_evidence")],
                [f"{pid}.uninvoiced_hourly_candidate"],
                "Missing links, external invoices, credits, contractual caps, or acceptance conditions may explain the difference; this is not confirmed lost revenue.",
                "Bookkeeper", "Match the listed time entries to all invoice systems and review agreement terms before deciding whether to bill."))
        if Decimal(values["cost_variance"]) > 0:
            findings.append(finding(
                "cost_overrun", f"{pid}.cost_overrun", pid, "Review delivery cost above budget",
                "Recorded direct delivery cost exceeds the original project cost budget.",
                values["cost_variance"], evidence["cost_variance"] + [p["agreement_ref"]],
                [f"{pid}.delivery_cost", f"{pid}.cost_variance"],
                "The records do not establish whether estimation error, rework, scope changes, or another cause explains the overrun. Fixed-fee overrun is not automatically billable.",
                "Operations manager", "Review the listed work and expenses against the original estimate and approved changes; use verified causes to adjust future estimates."))
        for inv in detail["invoices"]:
            if inv["days_overdue"] > 0:
                findings.append(finding(
                    "overdue_balance", f"{pid}.overdue.{inv['invoice_id']}", pid, "Review an overdue invoice balance",
                    f"Invoice {inv['invoice_id']} has a recorded balance {inv['days_overdue']} days past its due date at cutoff.",
                    inv["balance"], inv["evidence"] + references(inv["settlements"]),
                    [f"{pid}.balance", f"{pid}.overdue_balance"],
                    "Unallocated funds, a dispute, changed terms, or missing settlement records may affect the next action.",
                    "Bookkeeper", "Confirm allocations and any dispute or revised terms; if the balance remains due and undisputed, prepare a follow-up for human approval."))
        projects.append({"id": pid, "name": p["name"], "billing_model": p["billing_model"],
                         "agreement_ref": p["agreement_ref"], "budget_cost": display(p["budget_cost"]),
                         "pricing_basis_label": "Approved hourly work less price credits" if p["billing_model"] == "hourly" else "Agreed fixed fee less price credits",
                         "metrics": metrics, "details": {k: v for k, v in detail.items() if k != "metrics"}})
    # Source balances stay customer-level. Do not guess a project for unallocated cash.
    cutoff = parse_day(bundle.manifest["as_of"])
    for sources, allocations, fk, event, amount_key in (
        ("payments", "payment_allocations", "payment_id", "received_on", "amount"),
        ("credits", "credit_allocations", "credit_id", "issued_on", "total"),
    ):
        for source in sorted(bundle.tables[sources], key=lambda r: r["id"]):
            if source[event] > cutoff:
                continue
            applied = [a for a in bundle.tables[allocations] if a[fk] == source["id"] and a["applied_on"] <= cutoff]
            remaining = source[amount_key] - sum((a["amount"] for a in applied), ZERO)
            if remaining > 0:
                f = finding("reconciliation", f"{sources}.{source['id']}.unallocated", None,
                            "Reconcile an unallocated settlement source",
                            f"{sources.capitalize()} record {source['id']} has an amount not allocated to invoices at cutoff.",
                            display(remaining), [f"{sources}.csv#{source['id']}", *[f"{allocations}.csv#{a['id']}" for a in applied]], [],
                            "This could explain an apparent receivable; it must not be counted as additional money recoverable.",
                            "Bookkeeper", "Match the source to the correct customer invoice before changing any balance or sending a follow-up.")
                f["client_id"] = source["client_id"]
                findings.append(f)
    refs = set()
    for p in projects:
        refs.add(p["agreement_ref"])
        for metric in p["metrics"].values():
            refs.update(metric["evidence"])
    for f in findings:
        refs.update(f["evidence"])
    catalog = {}
    for ref in sorted(refs):
        resolve_evidence(bundle, ref)
        filename, anchor = ref.split("#")
        loc = dict(bundle.row_locations.get(ref, {"file": filename, "heading": anchor}))
        loc["sha256"] = bundle.file_hashes[filename]
        catalog[ref] = loc
    return {
        "report_version": REPORT_VERSION, "rule_version": RULE_VERSION, "snapshot_id": snapshot,
        "dataset_id": bundle.manifest["dataset_id"], "synthetic": bundle.manifest["synthetic"],
        "as_of": bundle.manifest["as_of"], "currency": bundle.manifest["currency"],
        "coverage": {k: bundle.manifest[k] for k in ("coverage_start", "coverage_end", "source_coverage")},
        "review_assertions": bundle.manifest.get("review_assertions", {}),
        "assumptions": bundle.manifest["assumptions"], "limitations": LIMITATIONS,
        "input_hashes": dict(sorted(bundle.file_hashes.items())),
        "projects": projects, "findings": findings, "evidence": catalog,
    }


def escaped(value) -> str:
    # Render source strings as literal text, not HTML/links/headings/table syntax.
    text = " ".join(str(value).split())
    text = "".join(c for c in text if ord(c) >= 32 and not 127 <= ord(c) <= 159)
    text = html.escape(text, quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~>\-])", r"\\\1", text)


def render_markdown(report: dict) -> str:
    out = ["# Agency project review", "",
           f"Dataset: {escaped(report['dataset_id'])} · As of: {report['as_of']} · Currency: {report['currency']}",
           f"Snapshot: `{report['snapshot_id']}`", "",
           "**Synthetic demonstration data.**" if report["synthetic"] else "**User-supplied records; completeness and terms are user assertions.**",
           "", "## Coverage and assumptions", "",
           f"Declared coverage: {report['coverage']['coverage_start']} through {report['coverage']['coverage_end']}.",
           escaped(report["coverage"]["source_coverage"]), ""]
    out.extend(f"- {escaped(x)}" for x in report["assumptions"])
    if report["review_assertions"]:
        out.extend(["", "Review assertions (user supplied):", ""])
        out.extend(f"- {escaped(k)}: {escaped(v)}" for k, v in report["review_assertions"].items())
    out.extend(["", "## Project summary", "",
                "| Project | Pricing basis (USD) | Delivery cost (USD) | Margin (%) | Cost variance (USD) | Billing candidate (USD) | Balance (USD) |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for p in report["projects"]:
        m = p["metrics"]
        values = [m[k]["value"] for k in ("pricing_basis", "delivery_cost", "delivery_margin_pct", "cost_variance", "uninvoiced_hourly_candidate", "balance")]
        out.append("| " + escaped(p["id"] + " — " + p["name"]) + " | " + " | ".join("N/A" if v is None else str(v) for v in values) + " |")
    out.extend(["", "Margins exclude overhead. Positive cost variance means over budget. Findings are not additive recoveries.",
                "", "## Items requiring review", ""])
    if not report["findings"]:
        out.append("No exceptions triggered by the implemented rules. This does not establish that the business has no issues.")
    for f in report["findings"]:
        out.extend([f"### {escaped(f['id'])}: {escaped(f['title'])}", "",
                    f"Recorded amount: **USD {f['amount']}** — review required.", "", escaped(f["fact"]), "",
                    f"Uncertainty: {escaped(f['uncertainty'])}", "",
                    f"Next step ({escaped(f['action']['owner_role'])}): {escaped(f['action']['next_step'])}", "",
                    "Evidence: " + ", ".join(escaped(r) for r in f["evidence"]), ""])
    out.extend(["## Metric calculations and references", ""])
    for p in report["projects"]:
        out.extend([f"### {escaped(p['id'])}: {escaped(p['name'])}", "",
                    f"Pricing basis: {escaped(p['pricing_basis_label'])}. Budget cost: USD {p['budget_cost']}.", ""])
        for m in p["metrics"].values():
            out.extend([f"- **{escaped(m['id'])}**: {m['value'] if m['value'] is not None else 'N/A'} {m['unit']}. {escaped(m['formula'])}",
                        "  Evidence: " + ", ".join(escaped(ref) for ref in m["evidence"])])
        out.append("")
    out.extend(["## Limitations", "", *[f"- {escaped(x)}" for x in report["limitations"]], "",
                "## Source file fingerprints", "", "| File | SHA-256 |", "| --- | --- |"])
    out.extend(f"| {escaped(name)} | `{digest}` |" for name, digest in report["input_hashes"].items())
    out.extend(["", "See report.json for per-entry cost and billing calculations, invoice settlement breakdowns, and the evidence catalog. CSV record numbers count the header as record 1; quoted multiline records can span physical lines.", ""])
    return "\n".join(out)
