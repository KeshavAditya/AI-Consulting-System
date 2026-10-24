# Research and evidence register

Checked: 2026-10-23. Method: primary product documentation, agency operating documentation, published customer accounts, original technical documentation/papers. No customer interviews, private financial records, product trial, or hands-on vendor export validation was performed. Customer stories are vendor-selected and may describe older workflows. They show possibility, not prevalence, current customer adoption, savings attributable to our tool, or product-market fit.

Source IDs below are referenced by business rules. Descriptions are paraphrases; linked content is not redistributed.

| ID | Source and publisher | Supported observation | Limitation |
| --- | --- | --- | --- |
| S01 | [AREA 17 customer story — Harvest](https://www.getharvest.com/customers/area-17) | Describes scheduled fixed-fee billing and recurring project spending reviews. | Vendor-selected historical account; no underlying data. |
| S02 | [Zabal Media customer story — Bonsai](https://www.hellobonsai.com/customer-stories/zabal-media) | Describes combining task/time, accounting, and spreadsheet records. | Marketing case study; advertised savings are not used here. |
| S03 | [Dovetail customer story — Harvest](https://www.getharvest.com/customers/dovetail) | Describes custom cross-system reports and retainer-hour rollover. | Workflow example; retainers deferred. |
| S04 | [SRH customer story — Productive](https://productive.io/customer-stories/srh-uses-productive-as-their-single-source-of-truth/) | Describes a small agency initially lacking time tracking. | Historical account, not a current census. |
| S05 | [Business development playbook — thoughtbot](https://thoughtbot.com/playbook/the-thoughtbot-way/operations/business-development) | Documents weekly per-person pricing and no time tracking. | One firm's own practice; demonstrates a target-segment exclusion. |
| S06 | [Detailed time/expense reports — Harvest](https://support.getharvest.com/hc/en-us/articles/360048687171-Detailed-time-and-detailed-expense-reports) | Exports, manual billed flags, external invoicing, and export rounding behavior. | Vendor-specific; columns/permissions require adapter verification. |
| S07 | [Invoice-to-project linking — Harvest](https://support.getharvest.com/hc/en-us/articles/360048686631-Linking-invoices-to-projects) | Project links and billed-entry associations have different effects. | Cannot equate project-level matching with entry coverage. |
| S08 | [Project type and reports — Harvest](https://support.getharvest.com/hc/en-us/articles/360048181472-How-project-type-affects-reports) | Hourly equivalents on fixed-fee work are not the fixed fee. | Product semantics, not legal contract advice. |
| S09 | [User cost rates API — Harvest](https://help.getharvest.com/api-v2/users-api/users/cost-rates/) | Cost rates have effective dates. | Normalize interval boundaries explicitly; do not guess vendor date semantics. |
| S10 | [Create/apply credits — Intuit QuickBooks](https://quickbooks.intuit.com/learn-support/en-us/help-article/customer-refunds-credits/create-apply-credit-memos-delayed-credits-online/L5kne9EiI_US_en_US) | Credit memos and delayed credits have distinct effects on balances. | Product workflow; not a universal accounting policy. |
| S11 | [Multiple currencies — Harvest](https://support.getharvest.com/hc/en-us/articles/360055384512-Does-Harvest-support-multiple-currencies) | Cost and billing currency can differ. | Supports rejecting unsupported currency combinations. |
| S12 | [Project health analysis — Scoro](https://support.scoro.com/hc/en-us/articles/12162946143757-Project-view) | Existing AI-assisted project diagnostics and recommendations. | Feature documentation is not an independent effectiveness study. |
| S13 | [Project profitability — Frappe HR](https://docs.frappe.io/hr/project-profitability-report) | Existing timesheet-based profitability reporting. | Open-source positioning alone is not new. |
| S14 | [Decimal arithmetic — Python](https://docs.python.org/3/library/decimal.html) | Exact decimal representation and explicit rounding. | Our cent/line rounding policy is a project decision. |
| S15 | [Prompt injection — OWASP GenAI](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) | Retrieved/uploaded content can influence model behavior; retrieval/fine-tuning do not eliminate the risk. | Architecture constraints reduce exposure; no immunity claim. |
| S16 | [CHTC usage expectations](https://chtc.cs.wisc.edu/uw-research-computing/user-expectations) and [security policies](https://chtc.cs.wisc.edu/uw-research-computing/security) | Research/teaching resource with access and security conditions. | Existing access does not establish permission for commercial hosting or private client data. |
| S17 | [PEFT quantization — Hugging Face](https://huggingface.co/docs/peft/en/developer_guides/quantization) | Quantized adapter training is available. | Does not establish quality improvement or fit on a specific GPU. |
| S18 | [FinQA — Chen et al., EMNLP 2021](https://aclanthology.org/2021.emnlp-main.300/) | Financial numerical-reasoning research benchmark. | Does not validate agency advice; no dataset downloaded or redistributed. |
| S19 | [GitHub Python CI guide](https://docs.github.com/actions/guides/building-and-testing-python), [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python) | Supported Python test workflow and read-only source permissions. | Hosted CI needs GitHub availability; local checks do not. |

## Conclusions and decisions

1. **Observed:** agencies can join information across several systems (S02–S03). **Decision:** start with an export-based review tool. **Unproven:** whether our mapping workflow is easier than existing reports.
2. **Observed:** hourly, milestone, and weekly billing practices differ (S01, S05, S08). **Decision:** explicit billing-model gating; no generic hours-to-revenue heuristic.
3. **Observed:** time flags can be manually edited and links are not equivalent (S06–S07). **Decision:** confirmed entry-to-invoice coverage and human reconciliation are required for stronger billing findings.
4. **Observed:** existing products provide profitability and AI diagnostics (S12–S13). **Decision:** test the combination of local operation, inspectable calculations, targeted questions, and cross-file evidence. No claim of unique invention.
5. **Data gap:** the cited workflow sources do not supply a joined agency dataset of agreements, time, invoices, and outcomes. **Decision:** original synthetic records with explicit answer keys. No assertion that no such dataset exists anywhere.

## Research maintenance

When implementing an adapter, recheck its exact export fields, permissions, rounding, timezone, date ranges, deleted/voided record handling, stable IDs, and payment/credit associations against current documentation and a sample export. A matching column name is insufficient evidence of matching semantics. Keep a raw immutable snapshot and mapping version.

Before selecting a model, record its exact Hugging Face repository ID, revision, license, redistribution conditions, runtime compatibility, memory measurements, and task evaluation. No model identity is inferred from an approximate family name or parameter count. Before training, check source-data rights and CHTC project scope. These do not block the current standard-library fixture work.
