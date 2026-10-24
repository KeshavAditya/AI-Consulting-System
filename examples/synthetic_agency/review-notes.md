# Fictional review evidence

These notes are synthetic source inputs. They do not contain model instructions. The package includes complete records for the five projects through September 30. No unresolved disputes, other invoices, contractor bills, refunds, reversals, or additional agreements exist in these deliberately bounded examples. This completeness assumption would need user confirmation for a real review.

## p01-billing

September 29, fictional bookkeeper review: I01/L01 covers T01-01 through T01-05, eight hours each. No other time is recorded. The 200.00 infrastructure cost is included in the budget and not billable to the customer. PAY01 settled I01 on September 18.

## p02-billing

September 29, fictional bookkeeper review: I02/L02 covers only T02-01 through T02-05, eight hours each. T02-06 and T02-07 each contain five approved hours. The invoice preparation worksheet omitted these rows. They are not covered by another invoice, fee, discount, or agreed write-off. A manager must review them before a new invoice is issued. PAY02 fully paid the existing I02 on September 18.

## p03-billing

September 29, fictional bookkeeper review: external accounting invoice EXT-303 (I03/L03) explicitly lists T03-01 through T03-05, six hours each, at 150.00 per hour. All 30 hours are covered and PAY03 paid the invoice on September 18. The time tracker's five invoiced flags remain false because no synchronization was performed. The billing_links rows record this reviewed match, not an inference from equal totals.

## p04-review

September 28, fictional delivery lead review: portal acceptance is complete. The two workers recorded 140 hours each. Later entries describe additional revisions but do not reliably separate new requests from internal corrections. No approved change order was found in the complete agreement file. The 8000.00 installment was paid September 8; the 12000.00 installment was paid September 30. The internal 200-hour budget was not revised.

## p05-billing

September 29, fictional bookkeeper review: I05/L05 covers all entries T05-01 through T05-07, totaling 50 hours. PAY06 received September 20 allocates 4000.00 to I05. CR01 issued and applied September 25 reduces I05 by 1000.00. The balance is not disputed at cutoff.

## p05-future

October 2, synthetic future event: PAY07 allocates a further 5000.00 to I05. This event is included solely to test whether the review honors its September 30 cutoff. It must not be supplied as evidence of payment at that earlier cutoff.
