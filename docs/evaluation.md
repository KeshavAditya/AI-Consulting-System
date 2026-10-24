# Evaluation, coverage, and limits

## What can be verified now

Run `python scripts/validate_examples.py` and `python -m unittest discover -s tests -v`. The fixture verifier checks schema/relationships, date/rate consistency, invoice and allocation arithmetic, evidence address existence, and exact equality with five hand-worked answers. Tests alter copied fixtures, not checked-in data.

The qualitative `must_say`/`must_not_say` rubric is for future model evaluation. No narrative evaluator, model benchmark, integration test against a vendor account, or business adoption study is implemented. Passing this suite is not a claim that recommendations are safe or correct on arbitrary real businesses.

## Separate evaluation layers

| Layer | Metric | Ground truth / proposed release gate |
| --- | --- | --- |
| Parsing and reconciliation | Correct field mapping, rejected invalid records, unresolved matches | Known source exports and independently labeled mapping cases; no silent dropped rows |
| Financial arithmetic | Exact cents, quantities and cutoff balances | Independent calculations; all supported test cases must match |
| Issue detection | Precision/recall by finding type, especially false billing alerts | Labeled positive/negative cases; all critical false-positive fixtures must pass |
| Evidence | Reference resolution and passage support | Report these separately; every reference resolves, and supporting claims are checked independently |
| Questions | Correct blocker identified, unnecessary questions, turns to resolve | Cases with deliberately hidden information and a scripted answer oracle |
| Recommendations | Action suitability, unsupported causal claims, invented amounts | Human review rubric where available; LLM-only grading explicitly labeled as a proxy |
| System | Latency p50/p95, peak RAM/VRAM, crash/cancellation recovery | Fixed hardware/model/context/input-size configuration; no performance result until measured |
| User value | Setup effort, review time, confirmed useful findings | Requires actual usage evidence; currently unknown |

Proposed numerical precision/recall thresholds should be set after an adequately sized pilot benchmark and error review; five easy public cases cannot justify a percentage claim. A zero-error result on development examples is necessary but insufficient.

## Research question and comparisons

Question: does a state machine that requests missing evidence reduce unsupported billing recommendations compared with ordinary document chat?

Compare (A) the same base model with documents and a simple prompt, (B) that model with calculation/retrieval tools, and (C) tools plus targeted questions and output validation. An optional (D) adds fine-tuning only after baseline results. Keep model revision, generation settings, evidence budget, and output rubric fixed. Give all variants comparable access to information; report the cost of extra questions/tool calls.

Run a second question experiment with information deliberately withheld, a fixed menu of allowable answers, and a bounded question budget. Measure whether the correct missing fact is requested and whether the final action changes appropriately. Do not feed the final expected action as a user answer.

## Dataset expansion and leakage control

The current five projects are public development cases. They cannot serve as held-out proof after being used to design prompts, tools, or training. Build separate scenario families varying rates, dates, project names, billing models, exception causes, document wording, and missing fields. Split by agency and scenario family; changing names alone is not an independent test case. Keep the final evaluation split frozen and separate from training/retrieval data.

Needed cases before application release include: healthy fixed-fee work; accepted/unaccepted milestones; partial entry billing; changed rates; rounded hours; deliberate write-offs; credits not applied to invoices; unrelated equal-value invoices; refunds and void histories if support is added; incomplete source exports; currency mismatch; duplicate imports; ambiguous names; contradictory agreements; malicious embedded instructions; and user answers of unknown/skip. Unsupported features should be explicitly rejected rather than included in accuracy denominators as successes.

FinQA (S18) can supplement numerical-reasoning research after its data terms are checked, but is not a substitute for this workflow benchmark. No external dataset is included in this PR. Synthetic ground truth is only as realistic as its assumptions, and human review by the builder is not independent expert validation.

## Integrity of reporting

Publish exact model/configuration, benchmark revision, sample size, split method, denominators, excluded cases, per-category errors, and uncertainty where appropriate. Keep all run outputs, including failures. Distinguish run variability from variation across cases. Never describe candidates as recovered money or estimated improvements as measured business outcomes.

With no customer outreach, this project can still publish transparent reproducible technical results and invite optional feedback. It cannot claim real-world consulting effectiveness, adoption, or willingness to pay. No such claims should appear in the README, demo, release notes, or future resume metrics until supported.

## Known foundation limitations

- The validator is intentionally strict and fixture-oriented; it is not a production ingestion/security boundary.
- Evidence checks verify addresses, not entailment, document authenticity, legal authority, or extraction accuracy.
- Complete source coverage and confirmed billing links are supplied assumptions in the examples.
- Snapshot invoice statuses cannot reconstruct historical state changes. Refunds/reversals need another representation.
- Dispute flags are recorded but there is no recommendation engine yet to enforce follow-up behavior.
- No runtime model, dashboard, database, adapter, performance benchmark, or encrypted local store is implemented.
- Existing unrelated `main.py` is not executed or tested by foundation CI.
