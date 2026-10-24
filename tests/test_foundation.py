"""Behavioral tests for the fixture contract and hand-worked arithmetic."""
import csv
import json
import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.validate_examples import (
    DEFAULT_BUNDLE, ROOT, ValidationError, calculate, load_bundle,
    money, rate_for, resolve_evidence, verify_expected,
)


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "bundle"
        shutil.copytree(DEFAULT_BUNDLE, self.path)

    def edit(self, table, change):
        path = self.path / f"{table}.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def field(self, table, row_id, field, value):
        self.edit(table, lambda rows: next(r for r in rows if r['id'] == row_id).__setitem__(field, value))

    def rejects(self, text):
        with self.assertRaisesRegex(ValidationError, text):
            load_bundle(self.path)

    def test_complete_bundle_matches_independent_answers(self):
        bundle = load_bundle(self.path)
        verify_expected(bundle, calculate(bundle))

    def test_expected_file_cannot_drive_calculations(self):
        bundle = load_bundle(self.path)
        expected_path = self.path / 'expected.json'
        expected = json.loads(expected_path.read_text())
        expected['projects']['P02']['uninvoiced_hourly_candidate'] = '9999.00'
        expected_path.write_text(json.dumps(expected))
        actual = calculate(bundle)
        self.assertEqual(actual['P02']['uninvoiced_hourly_candidate'], '1200.00')
        with self.assertRaisesRegex(ValidationError, 'metrics mismatch'):
            verify_expected(bundle, actual)

    def test_false_billed_flags_do_not_trigger_duplicate_billing(self):
        result = calculate(load_bundle(self.path))['P03']
        self.assertEqual(result['uninvoiced_hourly_candidate'], '0.00')
        self.assertEqual(result['allocated_cash'], '4500.00')

    def test_fixed_fee_overrun_is_not_hourly_revenue(self):
        result = calculate(load_bundle(self.path))['P04']
        self.assertIsNone(result['uninvoiced_hourly_candidate'])
        self.assertEqual(result['cost_variance'], '4000.00')
        self.assertEqual(result['delivery_margin_pct'], '30.00')

    def test_future_payment_excluded_then_included(self):
        bundle = load_bundle(self.path)
        self.assertEqual(calculate(bundle)['P05']['balance'], '5000.00')
        later = calculate(bundle, date(2026, 10, 2))['P05']
        self.assertEqual(later['balance'], '0.00')
        self.assertEqual(later['max_days_overdue'], 0)
        self.assertEqual(later['allocated_cash'], '9000.00')

    def test_credit_affects_price_and_balance_but_not_cash(self):
        result = calculate(load_bundle(self.path))['P05']
        self.assertEqual(result['pricing_basis'], '9000.00')
        self.assertEqual(result['allocated_cash'], '4000.00')
        self.assertEqual(result['balance'], '5000.00')

    def test_due_today_is_not_overdue(self):
        result = calculate(load_bundle(self.path), date(2026, 9, 15))['P05']
        self.assertEqual(result['balance'], '10000.00')
        self.assertEqual(result['overdue_balance'], '0.00')
        self.assertEqual(result['max_days_overdue'], 0)

    def test_credit_does_not_apply_before_issue_date(self):
        result = calculate(load_bundle(self.path), date(2026, 9, 24))['P05']
        self.assertEqual(result['balance'], '6000.00')
        self.assertEqual(result['pricing_basis'], '10000.00')

    def test_unallocated_credit_not_guessed_onto_invoice(self):
        self.edit('credit_allocations', lambda rows: rows.clear())
        self.edit('payment_allocations', lambda rows: rows.pop())
        result = calculate(load_bundle(self.path))['P05']
        self.assertEqual(result['balance'], '6000.00')
        self.assertEqual(result['pricing_basis'], '9000.00')

    def test_historical_rate_not_overwritten_by_future_rate(self):
        bundle = load_bundle(self.path)
        self.assertEqual(rate_for(bundle, 'E02', date(2026,9,30)), Decimal('60'))
        self.assertEqual(rate_for(bundle, 'E02', date(2026,10,1)), Decimal('90'))
        self.assertEqual(calculate(bundle)['P02']['labor_cost'], '3000.00')

    def test_nonbillable_work_still_costs_money(self):
        self.field('time_entries','T02-06','billable','false')
        result = calculate(load_bundle(self.path))['P02']
        self.assertEqual(result['labor_cost'], '3000.00')
        self.assertEqual(result['uninvoiced_hourly_candidate'], '600.00')

    def test_pending_work_not_priced_but_still_costed(self):
        self.field('time_entries','T02-06','approval_status','pending')
        self.field('time_entries','T02-06','approved_on','')
        result = calculate(load_bundle(self.path))['P02']
        self.assertEqual(result['labor_cost'], '3000.00')
        self.assertEqual(result['approved_hourly_value'], '5400.00')

    def test_future_approval_excluded(self):
        self.field('time_entries','T02-06','approved_on','2026-10-01')
        result = calculate(load_bundle(self.path))['P02']
        self.assertEqual(result['uninvoiced_hourly_candidate'], '600.00')

    def test_zero_pricing_basis_has_no_percentage(self):
        for entry_id in ['T02-06','T02-07']:
            self.field('time_entries',entry_id,'billable','false')
        # Remove confirmed links before marking the remaining work nonbillable.
        self.edit('billing_links', lambda rows: rows.__setitem__(slice(None), [r for r in rows if not r['time_entry_id'].startswith('T02')]))
        self.edit('time_entries', lambda rows: [r.update(billable='false') for r in rows if r['project_id']=='P02'])
        self.assertIsNone(calculate(load_bundle(self.path))['P02']['delivery_margin_pct'])

    def test_completed_margin_suppressed_before_completion(self):
        self.assertIsNone(calculate(load_bundle(self.path),date(2026,9,15))['P04']['delivery_margin_pct'])

    def test_decimal_rounding_policy(self):
        self.assertEqual(money(Decimal('0.105')), Decimal('0.11'))
        self.assertEqual(money(Decimal('1.005')), Decimal('1.01'))

    def test_partial_coverage_does_not_invent_a_cent(self):
        self.field('time_entries','T02-06','billing_hours','0.02')
        self.field('time_entries','T02-06','billing_rate','0.5')
        self.edit('billing_links',lambda rows: rows.append(dict(
            id='B-PARTIAL',time_entry_id='T02-06',invoice_line_id='L02',
            covered_hours='0.01',confirmed_on='2026-09-29',
            evidence_ref='review-notes.md#p02-billing')))
        for table,field in [('invoices','subtotal'),('invoices','total'),('invoice_lines','amount')]:
            self.field(table,'L02' if table=='invoice_lines' else 'I02',field,'4800.01')
        # 0.02 * 0.5 rounds to 0.01; covered 0.01 * 0.5 also rounds to 0.01.
        # Thus this entry contributes zero, and only the other 5h * 120 remain.
        result=calculate(load_bundle(self.path))['P02']
        self.assertEqual(result['uninvoiced_hourly_candidate'],'600.00')

    def test_delayed_allocation_is_not_applied_early(self):
        self.field('payment_allocations','PA06','applied_on','2026-10-01')
        result=calculate(load_bundle(self.path))['P05']
        self.assertEqual(result['balance'],'9000.00')
        self.assertEqual(result['allocated_cash'],'0.00')

    def test_billing_hours_are_distinct_from_cost_hours(self):
        self.field('time_entries','T02-06','billing_hours','4.5')
        result=calculate(load_bundle(self.path))['P02']
        self.assertEqual(result['labor_cost'],'3000.00')
        self.assertEqual(result['uninvoiced_hourly_candidate'],'1140.00')

    def test_duplicate_id_rejected(self):
        self.edit('time_entries',lambda rows: rows.append(rows[0].copy()))
        self.rejects('duplicate ID')

    def test_duplicate_source_record_rejected(self):
        self.field('time_entries','T01-02','source_ref','fictional-time:T01-01')
        self.rejects('duplicate source record')

    def test_missing_reference_rejected(self):
        self.field('time_entries','T01-01','project_id','NO_PROJECT')
        self.rejects('dangling foreign key')

    def test_missing_rate_rejected(self):
        self.edit('cost_rates',lambda rows: rows.pop(0))
        self.rejects('missing or ambiguous cost rate')

    def test_overlapping_rates_rejected(self):
        self.field('cost_rates','R07','valid_from','2026-09-30')
        self.rejects('overlapping cost rates')

    def test_mixed_currency_rejected(self):
        self.field('invoices','I01','currency','EUR')
        self.rejects('unsupported value')

    def test_bad_numbers_rejected(self):
        for bad in ['NaN','Infinity','1e4','-1.00','1,000.00','0.001','']:
            with self.subTest(value=bad):
                self.field('expenses','X01','amount',bad)
                self.rejects('invalid money|required value')

    def test_invalid_date_rejected(self):
        self.field('invoices','I01','due_on','2026-02-30')
        self.rejects('invalid date')

    def test_unknown_header_rejected(self):
        path=self.path/'people.csv'
        path.write_text(path.read_text().replace('id,role','id,job',1))
        self.rejects('headers differ')

    def test_missing_required_file_rejected(self):
        (self.path/'payments.csv').unlink()
        self.rejects('missing or unsafe')

    def test_bad_evidence_rejected(self):
        self.field('projects','P01','agreement_ref','agreements.md#nonexistent')
        self.rejects('unresolved document evidence')

    def test_outside_document_not_read(self):
        bundle=load_bundle(self.path)
        with self.assertRaisesRegex(ValidationError,'unlisted document'):
            resolve_evidence(bundle,'../../private.md#secret')

    def test_manifest_path_traversal_rejected(self):
        path=self.path/'manifest.json'
        manifest=json.loads(path.read_text())
        manifest['documents']=['../private.md']
        path.write_text(json.dumps(manifest))
        self.rejects('local basenames')

    def test_invoice_arithmetic_rejected(self):
        self.field('invoices','I01','total','4001.00')
        self.rejects('invoice total mismatch')

    def test_line_sum_mismatch_rejected(self):
        self.field('invoice_lines','L01','amount','3999.00')
        self.rejects('lines do not sum')

    def test_credit_arithmetic_rejected(self):
        self.field('credits','CR01','total','1001.00')
        self.rejects('credit total mismatch')

    def test_cross_client_allocation_rejected(self):
        self.field('payments','PAY01','client_id','C02')
        self.rejects('settlement client mismatch')

    def test_cross_project_billing_link_rejected(self):
        self.field('billing_links','B-T01-01','invoice_line_id','L02')
        self.rejects('cross-project billing link')

    def test_excess_hours_covered_rejected(self):
        self.field('billing_links','B-T01-01','covered_hours','9')
        self.rejects('covered hours exceed')

    def test_allocation_before_receipt_rejected(self):
        self.field('payment_allocations','PA01','applied_on','2026-09-17')
        self.rejects('allocation precedes')

    def test_source_overallocation_rejected(self):
        self.field('payment_allocations','PA01','amount','4001.00')
        self.rejects('allocations exceed source')

    def test_combined_credit_and_cash_overallocation_rejected(self):
        self.field('payments','PAY06','amount','4001.00')
        self.field('payment_allocations','PA06','amount','4001.00')
        self.rejects('combined settlements exceed')

    def test_draft_invoice_does_not_establish_coverage(self):
        self.edit('payment_allocations',lambda rows: rows.__setitem__(slice(None),[r for r in rows if r['invoice_id']!='I03']))
        self.field('invoices','I03','status','draft')
        result=calculate(load_bundle(self.path))['P03']
        self.assertEqual(result['billed_ex_tax'],'0.00')
        self.assertEqual(result['balance'],'0.00')
        self.assertEqual(result['uninvoiced_hourly_candidate'],'4500.00')

    def test_allocation_to_void_invoice_rejected(self):
        self.field('invoices','I01','status','void')
        self.rejects('allocation to non-issued')

    def test_24_hour_limit_rejected(self):
        self.field('time_entries','T01-01','hours','25')
        self.rejects('more than 24 hours')

    def test_templates_match_contract(self):
        bundle=load_bundle(self.path)
        for table,spec in bundle.contract['tables'].items():
            with (ROOT/'templates'/f'{table}.csv').open(newline='') as stream:
                rows=list(csv.reader(stream))
            self.assertEqual(rows,[[c['name'] for c in spec['columns']]])


if __name__ == '__main__':
    unittest.main()
