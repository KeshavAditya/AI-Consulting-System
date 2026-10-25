"""One calculation path for reports and independently checked fixture totals."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import localcontext

from .data import Bundle, ZERO, display, invoice_projects, money, parse_day, require

RULE_VERSION = "0.2.0"


def decimal_text(value):
    """Keep hours/rates at supplied precision; money uses display() instead."""
    return format(value, "f")


def calculate_details(bundle: Bundle, as_of: date | None = None) -> dict[str, dict]:
    with localcontext() as context:
        context.prec = 40
        return _calculate_details(bundle, as_of)


def _calculate_details(bundle, as_of):
    cutoff = as_of or parse_day(bundle.manifest["as_of"])
    t, results = bundle.tables, {}
    invoices, lines = bundle.index("invoices"), bundle.index("invoice_lines")
    ip = invoice_projects(bundle)
    active = {iid: inv for iid, inv in invoices.items()
              if inv["status"] == "issued" and inv["issued_on"] <= cutoff}
    cash, credited = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    settlements = defaultdict(list)
    for sources, allocations, fk, event_date, output in (
        ("payments", "payment_allocations", "payment_id", "received_on", cash),
        ("credits", "credit_allocations", "credit_id", "issued_on", credited),
    ):
        index = bundle.index(sources)
        for a in t[allocations]:
            if a["invoice_id"] in active and a["applied_on"] <= cutoff and index[a[fk]][event_date] <= cutoff:
                output[a["invoice_id"]] += a["amount"]
                settlements[a["invoice_id"]].append({
                    "kind": sources, "amount": display(a["amount"]),
                    "evidence": [f"{allocations}.csv#{a['id']}", f"{sources}.csv#{a[fk]}"],
                })
    coverage = defaultdict(lambda: ZERO)
    coverage_refs = defaultdict(list)
    for link in t["billing_links"]:
        line = lines[link["invoice_line_id"]]
        if link["confirmed_on"] <= cutoff and line["invoice_id"] in active:
            eid = link["time_entry_id"]
            coverage[eid] += link["covered_hours"]
            coverage_refs[eid].extend([
                f"billing_links.csv#{link['id']}", f"invoice_lines.csv#{line['id']}",
                f"invoices.csv#{line['invoice_id']}",
            ])
    for p in t["projects"]:
        pid = p["id"]
        hourly = p["billing_model"] == "hourly"
        entries = [e for e in t["time_entries"] if e["project_id"] == pid and e["work_date"] <= cutoff]
        work, labor, value, candidate = [], ZERO, ZERO, ZERO
        for e in entries:
            rates = [r for r in t["cost_rates"] if r["person_id"] == e["person_id"]
                     and r["valid_from"] <= e["work_date"]
                     and (r["valid_to"] is None or e["work_date"] < r["valid_to"])]
            require(len(rates) == 1, f"missing or ambiguous cost rate: {e['id']}")
            rate = rates[0]
            cost = money(e["hours"] * rate["hourly_cost"])
            labor += cost
            eligible = bool(hourly and e["billable"] and e["approval_status"] == "approved" and e["approved_on"] <= cutoff)
            priced = money(e["billing_hours"] * e["billing_rate"]) if eligible else ZERO
            covered_value = money(coverage[e["id"]] * e["billing_rate"]) if eligible else ZERO
            remaining = priced - covered_value
            value += priced
            candidate += remaining
            work.append({
                "entry_id": e["id"], "hours": decimal_text(e["hours"]),
                "hourly_cost": decimal_text(rate["hourly_cost"]), "labor_cost": display(cost),
                "cost_evidence": [f"time_entries.csv#{e['id']}", f"cost_rates.csv#{rate['id']}", f"people.csv#{e['person_id']}"],
                "eligible_hourly": eligible, "billing_hours": decimal_text(e["billing_hours"]),
                "billing_rate": decimal_text(e["billing_rate"]) if e["billing_rate"] is not None else None,
                "covered_hours": decimal_text(coverage[e["id"]]),
                "approved_value": display(priced) if hourly else None,
                "covered_value": display(covered_value) if hourly else None,
                "candidate_value": display(remaining) if hourly else None,
                "billing_evidence": [f"time_entries.csv#{e['id']}", *sorted(set(coverage_refs[e['id']]))],
            })
        hours = sum((e["hours"] for e in entries), ZERO)
        expense_rows = [x for x in t["expenses"] if x["project_id"] == pid and x["incurred_on"] <= cutoff]
        expenses = sum((x["amount"] for x in expense_rows), ZERO)
        cost = labor + expenses
        credits = [c for c in t["credits"] if c["project_id"] == pid and c["issued_on"] <= cutoff]
        price_credits = sum((c["subtotal"] for c in credits), ZERO)
        basis = (value if hourly else p["agreed_fee"]) - price_credits
        require(basis >= 0, f"credits exceed project pricing basis: {pid}")
        project_invoices = {iid: inv for iid, inv in active.items() if ip[iid] == pid}
        balances, balance, overdue, days = [], ZERO, ZERO, 0
        for iid, inv in project_invoices.items():
            remaining = inv["total"] - cash[iid] - credited[iid]
            require(remaining >= 0, f"negative invoice balance: {iid}")
            late = max(0, (cutoff - inv["due_on"]).days) if remaining > 0 else 0
            balance += remaining
            overdue += remaining if late else ZERO
            days = max(days, late)
            balances.append({
                "invoice_id": iid, "issued_on": inv["issued_on"].isoformat(), "due_on": inv["due_on"].isoformat(),
                "subtotal": display(inv["subtotal"]), "tax": display(inv["tax"]), "total": display(inv["total"]),
                "allocated_cash": display(cash[iid]), "allocated_credit": display(credited[iid]),
                "balance": display(remaining), "days_overdue": late,
                "settlements": settlements[iid],
                "evidence": [f"invoices.csv#{iid}", *sorted(f"invoice_lines.csv#{l['id']}" for l in lines.values() if l["invoice_id"] == iid)],
            })
        metrics = {
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
        results[pid] = {"metrics": metrics, "work": work, "invoices": balances,
                        "expenses": [{"amount": display(x["amount"]), "evidence": [f"expenses.csv#{x['id']}"]} for x in expense_rows],
                        "price_credits": [{"subtotal": display(c["subtotal"]), "evidence": [f"credits.csv#{c['id']}"]} for c in credits]}
    return results


def calculate(bundle: Bundle, as_of: date | None = None) -> dict[str, dict]:
    """Compatibility API: same summary values as the foundation verifier."""
    return {pid: result["metrics"] for pid, result in calculate_details(bundle, as_of).items()}
