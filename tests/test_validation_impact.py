"""Impact bounds use complete relationships; reporting remains fail-closed."""
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from agency_review.data import DEFAULT_BUNDLE, ROOT, ValidationError, load_bundle
from agency_review.impact import ValidationImpact, _classify_domain_impact
from agency_review.issues import ValidationIssue, error_payload
from agency_review.reporting import build_report, render_markdown


class ValidationImpactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "input"
        shutil.copytree(DEFAULT_BUNDLE, self.root)

    def edit(self, table, change):
        path = self.root / (table + ".csv")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def update(self, table, record_id, **changes):
        self.edit(table, lambda rows: next(r for r in rows if r["id"] == record_id).update(changes))

    def failure(self, code, projects=None, reason=None):
        with self.assertRaises(ValidationError) as caught:
            load_bundle(self.root)
        error = caught.exception
        self.assertEqual(error.issue.code, code)
        self.assertEqual(error.issue.blocking_scope, "bundle")
        self.assertEqual(error.impact.scope, "bundle" if projects is None else "projects")
        self.assertEqual(error.impact.project_ids, tuple(projects or ()))
        if reason:
            self.assertEqual(error.impact.reason, reason)
        return error

    def same_client(self):
        # P01 and P02 legitimately share a customer, but not necessarily cash.
        self.update("projects", "P02", client_id="C01")
        self.update("invoices", "I02", client_id="C01")
        self.update("payments", "PAY02", client_id="C01")

    def shared_payment(self):
        self.same_client()
        self.update("payment_allocations", "PA02", payment_id="PAY01")
        self.update("payments", "PAY01", amount="8800.00")

    def test_expense_error_is_bounded_to_its_project(self):
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01"], "record_dependencies")

    def test_project_rule_does_not_connect_shared_markdown_documents(self):
        self.update("projects", "P02", agreed_fee="1.00")
        self.failure("billing_model_fee", ["P02"])

    def test_invoice_error_resolves_through_lines_despite_null_diagnostic_project(self):
        self.update("invoices", "I01", total="1.00")
        error = self.failure("invoice_total", ["P01"])
        self.assertIsNone(error.issue.project_id)

    def test_cross_project_billing_link_includes_both_ends(self):
        self.update("billing_links", "B-T01-01", invoice_line_id="L02")
        self.failure("billing_project_mismatch", ["P01", "P02"])

    def test_multi_project_invoice_includes_all_line_projects(self):
        self.edit("invoice_lines", lambda rows: rows.append({
            "id": "LX", "invoice_id": "I01", "project_id": "P03",
            "description": "Conflicting project", "amount": "1.00",
        }))
        self.failure("multi_project_invoice", ["P01", "P03"])

    def test_payment_overallocation_includes_every_allocated_project(self):
        self.shared_payment()
        self.update("payments", "PAY01", amount="8799.00")
        self.failure("source_overallocated", ["P01", "P02"])

    def test_same_customer_alone_does_not_connect_projects(self):
        self.same_client()
        self.update("invoices", "I01", total="1.00")
        self.failure("invoice_total", ["P01"])

    def test_transitive_dependencies_extend_beyond_direct_ownership(self):
        self.shared_payment()
        # P01 -> shared payment -> P02 -> billing link -> P03.
        self.update("billing_links", "B-T02-01", invoice_line_id="L03")
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01", "P02", "P03"])

    def test_future_allocation_still_participates_in_validation_impact(self):
        self.shared_payment()
        self.update("payment_allocations", "PA02", applied_on="2026-10-02")
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01", "P02"])

    def test_draft_invoice_dependencies_are_not_discarded(self):
        self.shared_payment()
        self.update("invoices", "I02", status="draft")
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01", "P02"])

    def test_daily_hours_include_later_records_and_other_projects(self):
        # The first record alone exceeds the limit; later records still matter.
        self.update("time_entries", "T01-01", hours="25")
        self.update("time_entries", "T02-01", person_id="E01")
        error = self.failure("daily_hours_limit", ["P01", "P02"])
        self.assertEqual(error.issue.project_id, "P01")

    def test_shared_person_on_different_days_does_not_couple_local_errors(self):
        self.update("time_entries", "T02-06", person_id="E01")  # September 8; no P01 work.
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01"])

    def test_invalid_rate_interval_covers_all_projects_using_person(self):
        self.update("time_entries", "T02-06", person_id="E01")
        self.update("cost_rates", "R01", valid_to="2026-09-01")
        self.failure("rate_interval", ["P01", "P02"], "person_cost_rates")

    def test_overlapping_rates_are_not_scoped_to_only_first_period(self):
        self.update("time_entries", "T03-01", person_id="E02")
        self.update("cost_rates", "R07", valid_from="2026-09-15")
        self.failure("overlapping_rates", ["P02", "P03"], "person_cost_rates")

    def test_missing_rate_includes_other_dates_for_the_same_person(self):
        self.update("time_entries", "T02-06", person_id="E01")
        self.edit("cost_rates", lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["id"] != "R01"]))
        self.failure("cost_rate_unavailable", ["P01", "P02"], "person_cost_rates")

    def test_unused_bad_rate_does_not_mean_zero_impact(self):
        self.edit("people", lambda rows: rows.append({"id": "UNUSED", "role": "Developer"}))
        self.edit("cost_rates", lambda rows: rows.append({
            "id": "RX", "person_id": "UNUSED", "valid_from": "2026-09-01",
            "valid_to": "2026-09-01", "hourly_cost": "10", "currency": "USD",
        }))
        self.failure("rate_interval", reason="unresolved_ownership")

    def test_csv_evidence_connects_cited_project(self):
        self.update("projects", "P02", agreement_ref="expenses.csv#X01")
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01", "P02"])

    def test_evidence_cycles_are_finite_and_include_both_projects(self):
        self.update("projects", "P01", agreement_ref="projects.csv#P02")
        self.update("projects", "P02", agreement_ref="projects.csv#P01")
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01", "P02"])

    def test_cited_cost_rate_includes_its_work_consumers(self):
        self.update("projects", "P03", agreement_ref="cost_rates.csv#R01")
        self.update("time_entries", "T02-06", person_id="E01")
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.failure("expense_date_range", ["P01", "P02", "P03"])

    def test_credit_conflict_includes_price_project_and_invoice_project(self):
        self.update("projects", "P01", client_id="C05")
        self.update("invoices", "I01", client_id="C05")
        self.update("payments", "PAY01", client_id="C05")
        self.update("credit_allocations", "CA01", invoice_id="I01")
        self.failure("credit_project_mismatch", ["P01", "P05"])

    def test_combined_cash_and_credit_excess_has_invoice_impact(self):
        self.update("payment_allocations", "PA07", amount="5001.00")
        self.update("payments", "PAY07", amount="5001.00")
        self.failure("invoice_overallocated", ["P05"])

    def test_conflicting_customer_ownership_stays_bundle_wide(self):
        self.update("invoices", "I01", client_id="C02")
        self.failure("invoice_client_mismatch", reason="ambiguous_ownership")

    def test_cross_customer_payment_is_not_assumed_to_belong_to_one_side(self):
        self.update("payment_allocations", "PA02", payment_id="PAY01")
        self.failure("settlement_client_mismatch", reason="ambiguous_ownership")

    def test_long_evidence_chain_is_iterative_and_complete(self):
        count = 1100
        def chain(rows):
            template = rows[0].copy()
            template["agreed_fee"] = "1.00"
            rows[0]["agreement_ref"] = "projects.csv#CHAIN0000"
            for i in range(count):
                rows.append(dict(template, id=f"CHAIN{i:04d}",
                                 agreement_ref=f"projects.csv#CHAIN{i+1:04d}" if i+1 < count else "projects.csv#P01"))
        self.edit("projects", chain)
        self.failure("billing_model_fee", [*(f"CHAIN{i:04d}" for i in range(count)), "P01"])

    def test_unallocated_payment_with_unknown_customer_stays_bundle_wide(self):
        self.update("payments", "PAY07", client_id="UNKNOWN")
        self.edit("payment_allocations", lambda rows: rows.pop())
        self.failure("unknown_settlement_client", reason="ambiguous_ownership")

    def test_invoice_without_lines_does_not_guess_from_customer_or_payment(self):
        self.edit("invoice_lines", lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["id"] != "L04A"]))
        self.failure("invoice_lines_required", reason="ambiguous_ownership")

    def test_parse_failure_with_project_label_still_has_unverified_structure(self):
        self.update("expenses", "X01", amount="bad")
        error = self.failure("invalid_number", reason="unverified_structure")
        self.assertEqual(error.issue.project_id, "P01")

    def test_later_broken_reference_prevents_earlier_business_rule_scoping(self):
        self.update("projects", "P01", agreed_fee="1.00")
        self.update("payment_allocations", "PA07", payment_id="MISSING")
        self.failure("missing_reference", reason="unverified_structure")

    def test_duplicate_ids_are_never_used_to_build_impact_graph(self):
        self.update("time_entries", "T01-02", id="T01-01")
        with patch("agency_review.data._classify_domain_impact", side_effect=AssertionError("must not classify")):
            self.failure("duplicate_id", reason="unverified_structure")

    def test_invalid_evidence_stays_bundle_wide(self):
        self.update("projects", "P01", agreement_ref="agreements.md#missing")
        self.failure("unresolved_evidence", reason="unverified_structure")

    def test_unknown_rule_or_wrong_location_cannot_claim_project_scope(self):
        bundle = load_bundle(self.root)
        issue = ValidationIssue("new_rule", "example", file="expenses.csv", record_id="X01", project_id="P01")
        for changed in [issue, replace(issue, code="invoice_total"),
                        replace(issue, code="expense_date_range", record_id="UNKNOWN")]:
            with self.subTest(issue=changed):
                self.assertEqual(_classify_domain_impact(bundle, changed).scope, "bundle")

    def test_project_label_is_not_used_as_dependency_evidence(self):
        bundle = load_bundle(self.root)
        issue = ValidationIssue("expense_date_range", "example", file="expenses.csv",
                                record_id="X01", project_id="P05")
        self.assertEqual(_classify_domain_impact(bundle, issue).project_ids, ("P01",))

    def test_one_bounded_failure_does_not_claim_other_projects_are_valid(self):
        self.update("expenses", "X01", incurred_on="2026-09-30")
        self.update("invoices", "I05", total="1.00")
        self.failure("expense_date_range", ["P01"])
        self.update("expenses", "X01", incurred_on="2026-09-04")
        self.failure("invoice_total", ["P05"])

    def test_row_order_does_not_change_shared_impact_set(self):
        self.shared_payment()
        self.update("payments", "PAY01", amount="8799.00")
        first = self.failure("source_overallocated", ["P01", "P02"]).impact
        self.edit("payment_allocations", lambda rows: rows.reverse())
        self.edit("projects", lambda rows: rows.reverse())
        self.assertEqual(self.failure("source_overallocated", ["P01", "P02"]).impact, first)

    def test_impact_is_immutable_and_existing_error_payload_is_unchanged(self):
        self.update("expenses", "X01", incurred_on="2026-09-30")
        error = self.failure("expense_date_range", ["P01"])
        with self.assertRaises(FrozenInstanceError):
            error.impact.scope = "bundle"
        self.assertEqual(error_payload(error, error.category, str(error)), {
            "status": "blocked", "code": "validation_error", "message": str(error),
            "issue_version": "1", "issues": [error.issue.to_dict()],
        })

    def test_report_and_save_still_block_without_creating_outputs(self):
        self.update("expenses", "X01", incurred_on="2026-09-30")
        for verb, option in [(None, "--output"), ("save", "--store")]:
            destination = self.root.parent / (verb or "report")
            args = ([verb] if verb else []) + [str(self.root), option, str(destination)]
            result = subprocess.run([sys.executable, "-m", "agency_review", *args],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(result.stderr)
            self.assertEqual(payload["issues"][0]["code"], "expense_date_range")
            self.assertEqual(payload["issues"][0]["blocking_scope"], "bundle")
            self.assertNotIn("impact", payload)
            self.assertFalse(destination.exists())

    def test_valid_inputs_do_not_build_graph_or_change_reports(self):
        before = build_report(load_bundle(self.root))
        with patch("agency_review.data._classify_domain_impact", side_effect=AssertionError("unnecessary graph")):
            after = build_report(load_bundle(self.root))
        self.assertEqual(before, after)
        self.assertEqual(render_markdown(before), render_markdown(after))

    def test_concurrent_failures_and_later_success_do_not_share_impact_state(self):
        other = self.root.parent / "other"
        shutil.copytree(self.root, other)
        self.update("expenses", "X01", incurred_on="2026-09-30")
        (other / "people.csv").unlink()
        def assess(root):
            try:
                load_bundle(root)
            except ValidationError as error:
                return error.impact
            self.fail("expected failure")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(assess, [self.root, other]))
        self.assertEqual(results[0].project_ids, ("P01",))
        self.assertEqual(results[1], ValidationImpact())
        self.update("expenses", "X01", incurred_on="2026-09-04")
        self.assertEqual(len(load_bundle(self.root).tables["projects"]), 5)


if __name__ == "__main__":
    unittest.main()
