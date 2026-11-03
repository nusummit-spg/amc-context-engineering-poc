# AMC Context Engineering — CTO Remediation Blueprint

**Baseline**: `nusummit-spg/amc-context-engineering-poc`, `amc-dev`, SHA `e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0` (observed 2026-11-03).

**Assessment type**: remote static source review and specification. No test suites, infrastructure deployment, security exploitation, or production workload benchmarking have been executed. A proposed action is not a verified defect unless explicitly identified as observed in code.

## Outcome
Preserve **AMC Core → Feedback → Repair** as logical products/services, but establish one controlled source of truth and evidence contract across them. Execute CSV financial questions against an authoritative typed dataset, not an embedding-only approximation. Retire unapproved corrections from the serving path, eliminate implicit privileged roles, replace simulated benchmarks with measured end-to-end tests, and introduce guarded releases.

## Documents
1. `01_SOURCE_REVIEW_AND_ROOT_CAUSES.md`: observed code issues, failure hypotheses, severity, quick containment.
2. `02_TARGET_ARCHITECTURE_AND_CONTRACTS.md`: target design, dependencies, models, API/event contracts, state models, storage decisions.
3. `03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md`: CSV/Excel schema, canonical identity, ingestion, deterministic query planner, proof objects, tests.
4. `04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md`: end-to-end source/evidence/feedback/repair trust model, governance state machines and failure handling.
5. `05_ASSURANCE_SECURITY_RELEASE_GATES.md`: test strategy, production gates, SLOs, security requirements, rollback and audit design.
6. `06_GOALS_AND_TASKS.md`: **14 goals, 14 tasks per goal, 196 actionable tasks**, with acceptance evidence and dependencies.
7. `07_CODEX_EXECUTION_PLAYBOOK.md`: local Codex execution order, batch prompts, deliverables, review checklist, rollback.
8. `08_OPEN_DECISIONS.md`: bounded unresolved business semantics and environment decisions; conservative defaults provided.
9. `tasks.csv`, `goals.json`: machine-readable backlog.
10. `golden_test_case_template.csv`: 31 suggested validation scenarios, with independent gold-answer fields left blank; none executed.

## Immediate order of operations
**Freeze:** block externally reachable `/api/admin`, `/api/ingest`, graph, document-download and compliance-mutation routes until authentication is enforced; disable automatic repair promotion and prevent pending patches from influencing trusted answers. These are configuration/code changes to make in a controlled branch, not changes applied by this review.

**Reproduce:** record wrong and correct CSV examples as golden tests with query, active corpus version, expected normalized result, source row IDs, chosen retrieval path, and actual outputs.

**Replace:** publish a versioned canonical tabular snapshot and typed query execution API; route numeric requests there; forbid generative fallback after deterministic execution failure.

**Prove:** complete cross-system P0 security, numeric correctness, evidence consistency, and promotion rollback gates before canary rollout.

## Notable scope limits
- This plan does not change the target repository or its data, secrets, or production systems.
- `mutual_fund_data.csv` is described by its committed manifest as 16,245 rows in 22 chunks; the full CSV was not downloaded into the review environment.
- Industry formulas and financial labels (AUM granularity, folio vs plan vs option, fund identity, historical dates, closures) **must be signed off by an AMC data steward** before release.
- The committed README's production-ready claims and performance numbers are not relied upon as operational evidence.

## Engineering non-negotiables
1. No trust elevation from caller-provided headers or generated text.
2. No financial number without typed computation and traceable data provenance.
3. No source citation unless it supports the relevant claim.
4. No index activation after partial mandatory write failures.
5. No feedback-derived correction becomes serving truth without required authorization, validation and activation.
6. No passing benchmark constructed from the same ground truth used to compose the answer.
7. Every behavioral change has baseline, golden test, canary rule and rollback strategy.
10. `golden_test_case_template.csv`: 31 suggested validation scenarios with placeholders for independently approved expected answers; **none is marked executed**.
