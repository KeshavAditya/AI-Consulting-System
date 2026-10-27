"""Conservative impact bounds for one error, not permission to calculate a subset."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationImpact:
    """Internal assessment; CLI issue v1 and its blocking_scope stay unchanged.

    Empty project_ids with scope='bundle' means impact is not safely bounded,
    not that no projects are affected. No unaffected/valid projects are claimed.
    """

    scope: str = "bundle"
    project_ids: tuple[str, ...] = ()
    reason: str = "unverified_structure"


# Opt in by BOTH rule and table. New rules remain bundle-wide until reviewed.
_RULE_TABLES = {
    "project_coverage": ("projects",),
    "billing_model_fee": ("projects",),
    "rate_interval": ("cost_rates",),
    "overlapping_rates": ("cost_rates",),
    "cost_rate_unavailable": ("time_entries",),
    "work_date_range": ("time_entries",),
    "positive_hours": ("time_entries",),
    "billing_hours_limit": ("time_entries",),
    "daily_hours_limit": ("time_entries",),
    "approval_status_date": ("time_entries",),
    "approval_before_work": ("time_entries",),
    "billing_rate_required": ("time_entries",),
    "fixed_fee_hourly_rate": ("time_entries",),
    "expense_date_range": ("expenses",),
    "multi_project_invoice": ("invoice_lines",),
    "invoice_due_date": ("invoices",),
    "invoice_total": ("invoices",),
    "invoice_line_total": ("invoices",),
    "billing_project_mismatch": ("billing_links",),
    "billing_link_eligibility": ("billing_links",),
    "positive_coverage": ("billing_links",),
    "billing_confirmation_date": ("billing_links",),
    "billing_hours_overallocated": ("time_entries",),
    "invoice_line_overallocated": ("invoice_lines",),
    "credit_total": ("credits",),
    "positive_allocation": ("payment_allocations", "credit_allocations"),
    "invoice_not_issued": ("payment_allocations", "credit_allocations"),
    "allocation_date": ("payment_allocations", "credit_allocations"),
    "credit_project_mismatch": ("credit_allocations",),
    "source_overallocated": ("payments", "credits"),
    "invoice_overallocated": ("invoices",),
}
_AMBIGUOUS_OWNERSHIP = {
    "invoice_lines_required", "invoice_client_mismatch", "credit_client_mismatch",
    "unknown_settlement_client", "settlement_client_mismatch",
}
_RATE_RULES = {"rate_interval", "overlapping_rates", "cost_rate_unavailable"}


class _Components:
    """Union by size with iterative path compression; no recursive graph walks."""

    def __init__(self, nodes):
        self.parent = {node: node for node in nodes}
        self.size = dict.fromkeys(self.parent, 1)

    def root(self, node):
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def join(self, left, right):
        left, right = self.root(left), self.root(right)
        if left == right:
            return
        if self.size[left] < self.size[right]:
            left, right = right, left
        self.parent[right] = left
        self.size[left] += self.size[right]


def _classify_domain_impact(bundle, issue) -> ValidationImpact:
    """Called only after complete parsing, uniqueness, FK and evidence checks.

    Use the captured tables, never reread files or trust issue.project_id. The
    graph includes all records, even draft/future ones, because validation does.
    This internal function does not validate arbitrary caller-created Bundles.
    """
    if issue.code in _AMBIGUOUS_OWNERSHIP:
        return ValidationImpact(reason="ambiguous_ownership")
    allowed = _RULE_TABLES.get(issue.code, ())
    table = next((name for name in allowed if issue.file == name + ".csv"), None)
    if table is None:
        return ValidationImpact(reason="unsupported_rule")
    rows = {(name, row["id"]): row for name, records in bundle.tables.items() for row in records}
    node = (table, issue.record_id)
    if node not in rows:
        return ValidationImpact(reason="unresolved_ownership")

    graph = _Components(rows)
    people = defaultdict(list)
    days = {}
    for entry in bundle.tables["time_entries"]:
        entry_node = ("time_entries", entry["id"])
        people[entry["person_id"]].append(entry_node)
        day = (entry["person_id"], entry["work_date"])
        if day in days:
            graph.join(entry_node, days[day])
        else:
            days[day] = entry_node

    # People and rates are shared reference data, not automatic connections
    # between every project that ever used the same employee. Rate failures seed
    # ALL of that person's work below; explicit CSV evidence is also followed.
    cited_people = set()
    for (name, record_id), row in rows.items():
        source = (name, record_id)
        for column in bundle.contract["tables"][name]["columns"]:
            value = row[column["name"]]
            target_table = column.get("references")
            if target_table and target_table != "people" and value is not None:
                graph.join(source, (target_table, value))
            if column["type"] == "evidence":
                filename, anchor = value.split("#")
                if filename.endswith(".csv"):
                    target = (filename[:-4], anchor)
                    graph.join(source, target)
                    if target[0] in {"people", "cost_rates"}:
                        person = anchor if target[0] == "people" else rows[target]["person_id"]
                        cited_people.add(person)
                        graph.join(target, ("people", person))
    # Each employee's entries are scanned once even if many evidence cells cite
    # their records. Shared Markdown documents have already passed validation;
    # their text is not interpreted as a financial dependency.
    for person in cited_people:
        for entry in people[person]:
            graph.join(("people", person), entry)

    seeds = people[rows[node]["person_id"]] if issue.code in _RATE_RULES else [node]
    roots = {graph.root(seed) for seed in seeds}
    projects = tuple(sorted(row["id"] for row in bundle.tables["projects"]
                            if graph.root(("projects", row["id"])) in roots))
    if not projects:
        return ValidationImpact(reason="unresolved_ownership")
    return ValidationImpact("projects", projects,
                            "person_cost_rates" if issue.code in _RATE_RULES else "record_dependencies")
