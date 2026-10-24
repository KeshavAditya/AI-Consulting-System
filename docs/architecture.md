# Architecture and implementation sequence

Status: design, except the standard-library fixture checker and tests. There is no deployed service, model runner, database, or UI in this PR.

## Components and ownership of decisions

| Component | Responsibility | Must not do |
| --- | --- | --- |
| Local browser UI | Uploads, mapping confirmation, questions, evidence display, user dispositions, export | Present unsupported suggestions as verified facts |
| Local Python API | Review lifecycle, validation, run isolation, persistence, cancellation | Execute code extracted from documents |
| Import adapters | Vendor-specific parsing into canonical records, provenance, coverage and ambiguity reporting | Treat similarly named columns as equivalent without checking semantics |
| Calculation engine | Decimal arithmetic, date filtering, reconciliation, validation, reproducible metric IDs | Delegate arithmetic or billing eligibility authority to free-form model text |
| Evidence store | Original files, hashes, normalized records, effective dates, passage/row references | Mix records across businesses or expose answer keys to inference |
| State-machine controller | Decide allowed next step, enforce tool limits, retry/timeouts, persist progress | Permit unlimited recursive model/tool calls |
| Local LLM adapter | Interpret selected text, propose questions, explain supplied facts in structured output | Write invoices, contact clients, browse the web, or run arbitrary SQL/shell commands |

Proposed stack: Python backend, SQLite local persistence, React interface, and a swappable local model endpoint. These are implementation choices to validate, not installed dependencies. Begin with one local user and one review at a time. Shared-server authentication, multi-tenant hosting, and concurrent account access are separate projects.

## State machine

`created → importing → validating → calculating → investigating → awaiting_input / reporting → completed`

Validation can enter `blocked` with actionable row errors; any active stage can enter `failed` or `cancelled`. A user answer resumes investigation from a saved checkpoint. Distinguish a timeout from a negative business finding. Initially cap investigation to three question rounds and ten tool calls per finding; these are adjustable engineering limits, not research-derived optimal values.

Persist: run ID, business namespace, input hashes, as-of date, schema/rule versions, model revision/settings, stage, completed tool calls, questions/answers, finding dispositions, and final artifact hash. Reopening a run must not duplicate input records or rerun completed external side effects; v1 has no external write actions. Changes to input/rule versions produce a new calculation snapshot rather than overwrite prior evidence.

The model can request a small allowlisted set of read-only operations: retrieve records by canonical ID, retrieve an effective agreement passage, inspect precomputed metrics, list unresolved mappings, and propose a structured question. The controller validates arguments and the scope of each request. A source sentence such as "ignore prior instructions" remains document content.

## Evidence and reporting

Deterministic facts receive stable metric IDs and source-row references. A model explanation must reference those facts and resolvable passages; arithmetic values are inserted from metrics, not copied from generated prose. Validate output fields/types and reject unknown references. Citation existence alone does not prove the source supports the claim: semantic evidence quality requires evaluation.

Retrieve only passages effective by the review cutoff. The future payment note in the examples is a deliberate leakage test. Do not pass `expected.json`, this repository's worked answers, or hidden benchmark rubrics into model context. Record uncertain document dates; historical claims stay blocked when versions cannot be established.

A finding should distinguish the recorded fact, possible explanation, remaining uncertainty, and proposed action. State estimated financial impact only when a reproducible scenario supplies it. The user remains responsible for confirming ambiguous invoice matches and contractual interpretation.

## Local privacy and input handling

At application implementation, bind to loopback by default; add request-origin/CSRF protection where applicable. Local files remain local after installation, with telemetry disabled by default. Model downloads are separate from review inference. Never fetch remote links embedded in uploaded content.

Use a dedicated workspace, allowlisted file formats, file/row/page limits, and non-executing parsers. Do not evaluate Excel formulas or macros. Escape spreadsheet formula prefixes when producing CSV exports for users. Do not render raw document HTML unsanitized. Keep model access scoped to the current run rather than the user's entire filesystem. Read-only tools and output validation reduce prompt-injection consequences but do not eliminate the risk (S15).

Do not log raw financial text by default. Define deletion behavior for original files, normalized records, generated reports, and logs; explain that operating-system backups or user-exported copies are outside app deletion. Do not claim database encryption at rest until implemented. An OS account with file access can access plaintext local records.

## Models and CHTC

Use an existing open-weight model as the first baseline. Exact model ID/revision, redistribution terms, compatible runtime, quantization, context length, and hardware measurements are required before selecting a default. A 32 GB laptop alone does not establish usable speed for a particular 27B-class model. A smaller model with reliable tools may be better; test rather than assume.

Use CHTC for research evaluation and approved training jobs, not a promised public inference host (S16). Keep this project's first experiments synthetic. Access through another job or lab does not by itself authorize unrelated workloads or confidential client data. No CHTC jobs or private-data transfers occur in this PR.

If baseline errors show a repeatable need, evaluate quantized adapter training (S17) against the same held-out cases. Learn tool selection, evidence use, and questions rather than memorizing company records. Training, retrieval, and larger model size do not establish financial expertise automatically. Distribute code and properly licensed model artifacts separately. Users provide inference hardware/electricity; the maintainer need not fund a shared inference API.

## Incremental PR sequence

| PR | Deliverable | Exit condition |
| --- | --- | --- |
| 1 — this foundation | Scope, research, rules, canonical CSVs/templates, worked answers, verifier, tests, CI | Reviewable assumptions and passing fixture checks |
| 2 — import/calculation library | Typed application models, immutable imports, structured errors, idempotency, metric provenance | Fixtures pass through application code; malformed/partial imports receive actionable results |
| 3 — review API and minimal UI | Create/reopen review, upload/mapping screens, deterministic findings, evidence links | Complete local workflow without an LLM |
| 4 — local LLM investigation | Model adapter, read-only tools, constrained state machine, questions, structured output | Evidence/cutoff tests and reproducible baseline results |
| 5 — vendor adapter and release | One tested export path, installation, cancellation/recovery, documentation, sample review | Reproducible fresh-machine installation and measured hardware report |
| 6 — optional research | Larger benchmark, model comparisons and possible adapter training | Measured improvement over the frozen baseline without regression |

Keep each PR independently runnable. The repository owner chooses reviewers and merges. No auto-merging or branch protection changes are part of this sequence.
