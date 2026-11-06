# AMC Context Engineering — Wave 1.6 CTO Re-Audit & Local-Agent Implementation Handoff

**Prepared:** 6 November 2026 (IST)  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Target branch:** `amc-dev`  
**Reviewed HEAD (pin source during reproduction):** `4ede4338642949f0a32ee0672b4dc09616659193`  
**Wave 1.5 comparison baseline:** `17fe11268f240359198f03bff1a1e9f9f2b8a3db`  
**Observed delta:** 12 commits ahead, 20 files changed, as reported by GitHub Compare.  
**Review method:** Repository source/commit/tree inspection using the connected GitHub account; *no application, database, FAISS, Neo4j, CI or runtime tests executed by this reviewer*.  
**Release decision:** **BLOCK** — do not deploy/merge as a production-ready financial answer or autonomous canonical Repair system.

> **Recipient:** Local Codex / engineering agent. This is an actionable implementation and verification contract, not a claim that the listed defects are already repaired. Code and tests must be implemented, executed and committed. Existing Wave 1.1–1.5 handoffs remain supporting references, but this document supersedes their *task priority* when overlapping.

**Pinned links:** [Source tree](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/4ede4338642949f0a32ee0672b4dc09616659193) · [Commits relative to Wave 1.5](https://github.com/nusummit-spg/amc-context-engineering-poc/compare/17fe11268f240359198f03bff1a1e9f9f2b8a3db...4ede4338642949f0a32ee0672b4dc09616659193) · [Current handoff predecessor](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/4ede4338642949f0a32ee0672b4dc09616659193/AMC_Wave1_5_Next_Implementation_Agent_Handoff_2026-11-06.md) · [Specifications](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/4ede4338642949f0a32ee0672b4dc09616659193/docs/AMC_Tasks_3_11_26/AMC_Specs).

---

## 1. Executive findings and action decision

### 1.1 What the latest push actually adds

- New `backend/app/services/financial_policy_service.py`, and edits to `backend/app/tabular/{planner,executor,contracts}.py` introducing a structured metric policy interface and result formatting.
- `backend/app/services/{vector_staging_service,graph_postconditions_service,feedback_outcome_service,operational_metrics_service}.py` and `backend/app/schemas/publication_intents_table.py`.
- Additional governance and feedback integration edits, one 420-line fault-injection test module, and new audit/migration scripts.
- A GitHub Actions YAML file `.github/workflows/amc-assurance.yml`.
- A recorded decision document acknowledging that deletion of `packages/amc-feedback-loop` remains unresolved.
- Improvements to preapproval vector insertion containment in `repair_integration.py` (the old synthetic insertion block is now commented out).

These are meaningful foundations, but **adding a service, schema or test file is not equivalent to closing its end-to-end control**.

### 1.2 Critical differences between implementation claims and inspected code

| ID | Severity | Source-grounded finding | Decision |
|---|---|---|---|
| V16-01 | **P0** | `FinancialPolicyService` hardcodes `aaum_crore.steward_approved=True`, `SUMMABLE` and `SUM/AVG/RANK`, although previous business-steward decision remains unresolved. `validate_metric_operation` also returns `(True, PENDING_STEWARD)` when not approved. | Block unapproved financial aggregation immediately. |
| V16-02 | **P0** | `QueryExecutor` supplies `"AGGREGATION"` for ranking/aggregation, while the policy registry allows `SUM`, `AVG`, `RANK`, not `AGGREGATION`; precise operation mapping is missing. | Typed numeric queries can be incorrectly blocked or misclassified; introduce strict, tested mapping. |
| V16-03 | **P0** | `planner.create_top_amcs_plan()` now selects unaggregated `aaum_crore` while grouping by AMC, and `create_top_schemes_plan()` groups by display name with raw NAV/AAUM/date columns. Merely formatting returned numbers with `Decimal` is **not exact aggregation**. | Replace invalid/nondeterministic SQL and establish approved canonical grains. |
| V16-04 | **P0** | `FeedbackOutcomeService._is_publication_published()` and `_is_verification_complete()` return `True` unconditionally; `resolve_issue()` can declare an issue resolved without real publication evidence. | Fail closed until persisted, tenant-scoped ACTIVE receipt is checked. |
| V16-05 | **P0** | `VectorStagingService` stores stage operations/preimages in process memory; its preimage finder uses similarity search for a `chunk_id`. Rollback operates on pending `_staging` but `apply_staged()` removes the staged records. | No durable or dependable post-application rollback; implement versioned FAISS generations with exact-ID proof. |
| V16-06 | **P0** | `GraphPostconditionsService._delete_node_or_edge()` only logs deletion. `_update_node_or_edge()` calls delete+create; `apply_staged()` clears staging even on partial failures. | No exact graph postcondition/rollback contract; forbid success until actual checked effects. |
| V16-07 | **P0** | `publication_intents_table.py` defines tables, but the inspected `backend/alembic/versions/` tree has only migrations `004`–`008`; no publication intents/receipts migration was found. | Add actual compatible Alembic migration, check all prior revisions and run isolated upgrade/downgrade. |
| V16-08 | **P0** | `.github/workflows/amc-assurance.yml` push branches exclude `amc-dev`; new workflow has no matching branch runs or commit status checks. Several jobs use `echo` statements for canary, SLO and release success, `|| echo` to suppress scan failures, and paths/options for test suites absent from tree. | Make CI real, mandatory, fail-closed, and runnable on `amc-dev`/PRs. |
| V16-09 | **P0** | `test_wave15_publication_fault_injection.py` contains assertions such as `assert result is False or result is True`; other tests model events/leases in local objects rather than exercising the actual worker. | Replace tautologies with executable, cross-store effect assertions. |
| V16-10 | **P0** | New graph/vector/feedback services are not shown to be driven by the existing approval, outbox, `PromotionService`, `RepairEngine`, cache and API serving paths. Pre-existing `_trigger_reindex()` and outbox placeholders should be rechecked. | Prove one orchestrated path, remove/disable conflicting legacy paths. |
| V16-11 | **P0** | Financial policy validates only shape/declared hash strings: manifest logic assumes 1,000 rows/chunk, checks hash lengths but does **not recompute bytes**, and dataset-state transition method is a validator, not persisted activation. | Implement actual source/hash reconciliation and durable version switch. |
| V16-12 | **P1** | `QueryExecutor` bounds `source_row_ids` at 50, even for aggregates; `FinancialPolicyService.create_aggregation_provenance()` sets `is_gold` based on policy category and uses placeholder timestamp `"now"`. | Real complete provenance/independent gold is absent. |
| V16-13 | **P1** | `OperationalMetricsService` holds event data in local lists; no observed durable telemetry, SLO calculation, or real canary health. | Instrument actual operations and prove monitored windows. |
| V16-14 | **P0** | `packages/amc-feedback-loop` remains absent; `remediation/wave1_5/FEEDBACK_PACKAGE_DECISION.md` states product-owner decision pending. | Preserve a block for Feedback parity/deletion until approved with executable coverage. |

### 1.3 Audit caveats

- This is a **source-level review** of the pinned commit. The GitHub workflow count and commit statuses were empty at review time; this does not prove there were never local test executions. The reported task completion table is **not accepted as independent verification**.
- Code and claims in `remediation/wave1_4/STATUS.md` conflict with `remediation/wave1_5/STATUS.md`: some items are marked COMPLETE even where the code is only scaffolded. Use `DONE / PARTIAL / BLOCKED / NOT_RUN` with run evidence; do not inherit optimistic scores.
- Do not infer that a CSV field is additive, that a financial number is authoritative, or that an approval was given. Any missing data-steward decision is a legitimate *release blocker*, not permission to choose a business rule.

---

## 2. Wave 1.6 execution plan — bulk work, not repeated planning cycles

**Implement in four coordinated PRs/commits plus a distinct release gate.** Keep each PR reviewable, preserving the user's existing `amc-dev` branch and historical changes. Use a new `wave1.6/...` feature branch based on pinned SHA; do not force-push and do not modify production datasets.

| Batch | Goal | Tasks | Prerequisite | Initial release impact |
|---|---|---|---|---|
| **G — Governance and immediate truth containment** | Prevent invented approvals, wrong financial numbers and false Feedback resolution | G01–G07 | None | P0 |
| **P — One durable publication/rollback plane** | Wire actual graph/FAISS effects, outbox, receipts and recovery | P01–P10 | G rules; data fixtures | P0 |
| **F — Financial deterministic correctness** | Canonical keys, approved exact arithmetic, manifests and provenance | F01–F10 | G01 policy | P0 |
| **Q — Serving, Feedback and operational parity** | All query modes and Feedback module contract | Q01–Q07 | P + F interfaces | P0/P1 |
| **A — Independent release assurance** | Real CI/migration/negative tests, safety and operational proof | A01–A08 | All batches | Required |

**Recommended bulk run:** Build G and P together, plus F's policy-gating and deterministic fixtures in parallel. Follow with the remaining F, Q and A. CI fixes (A01–A03) should start **immediately**, not at the very end, to expose regressions while the agent works.

**Non-negotiable:** Shipping in a blocked state is not allowed merely because a test suite passes. Stub success, unsupported operations, unreviewed AAUM or missing durable evidence all require deterministic errors.

---

## 3. Batch G — governance, trust and immediate safety (P0)

### G01 — Reverse the hardcoded AAUM business approval

**Inspect:** `backend/app/services/financial_policy_service.py`, `backend/app/tabular/metrics.py` or actual registry modules, `planner.py`, `executor.py`, `schemas` and financial config.

**Implement:**
1. Change AAUM additivity to **PENDING_APPROVAL** unless and until a named data steward signs off the metric's grain, period and aggregation rules. Do not set `steward_approved=True` in a default constructor.
2. Put policy in a **versioned persisted registry** including operation, canonical grain, source version, effective date, approver, approval receipt, and rationale. No user input or LLM can grant approval.
3. Return `METRIC_POLICY_BLOCKED` for SUM/AVG/RANK and derived metrics when policy is pending. Exact nonaggregate lookups may be allowed *only if their source validity and meaning are approved*.
4. Make `validate_metric_operation()` return `False` when pending; remove the `True` plus warning loophole.
5. Require an operator/analyst-facing explanation of **why** a result is blocked; never produce dataset-derived numeric output with a caution label.

**Acceptance:** 100% confidence/flag and policy text cannot override pending approval. An AAUM ranking returns an explicit blocked result. A signed, test-only approved policy with correct grain can proceed; no production approval is fabricated.

### G02 — Fix operator vocabulary and security of typed query plans

**Inspect:** `executor.py::execute()`, `planner.py`, `financial_policy_service.py`, `tabular/contracts.py`, FastPath/Query orchestration.

**Implement:** Define the actual allowed `MetricOperation` enum (`EXACT_LOOKUP`, `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `RANK`, `DISTRIBUTION`, etc.), map each `PlanIntent` and SQL template to its true operation, and validate the operation **at execution time** against canonical metric policy. Reject arbitrary compiled SQL unless produced by an allowlisted template/validated plan. Distinguish ranking by count from ranking by prohibited AAUM SUM. A dynamic query cannot bypass the policy by calling itself `EXACT_LOOKUP`.

**Acceptance:** No mismatch between `AGGREGATION` and `SUM`; no false passes for unknown operations; no fabricated approval. Test both approved and unapproved cases.

### G03 — Prohibit invalid numeric SQL and silently selected group values

**Inspect:** `planner.py::{create_top_amcs_plan,create_top_schemes_plan,create_top_nav_schemes_plan,create_exact_nav_plan}` and `executor.py`.

**Implement:** Remove `GROUP BY amc_id,amc_display_name` with a raw `aaum_crore` projection, `GROUP BY scheme_display_name`, raw NAV/date columns inside grouped queries, and `LIMIT 1` that hides multiple plan options. Use **approved row grain**, deterministic SQL and `Decimal` arithmetic before aggregation. Reject ambiguous source identities. Protect normalization for `NULL`, scientific notation, missing units, invalid floats, duplicate options and mixed quarters.

**Acceptance:** SQL is deterministic in strict-mode semantics; independent tests catch repeated display names, mixed plans, wrong quarter, and duped NAV observations. `Decimal` formatting after a wrong SQL result is **not** considered a correction.

### G04 — Feedback resolution must depend on actual ACTIVE evidence

**Inspect:** `backend/app/services/feedback_outcome_service.py` (`_is_publication_published`, `_is_verification_complete`, `resolve_issue`, `rollback_reopens_issue`), `feedback/repair_linkage.py`, `publication_intents_table.py`.

**Implement:** Query actual persisted records and validate `intent.tenant == issue.tenant`, approved source revision, receipt association, hash/checksum, observed postcondition, verified ACTIVE version and nonrevoked authority. Resolve the issue only after a transactional/causal update. Persist issue status; rollback must reopen or mark NEEDS_REVIEW across all dependent issues and invalidate stale answer evidence.

**Acceptance:** Unknown intent, absent receipt, stale version, wrong tenant, no ACTIVE patch, unverified graph/vector or revoked approval -> no RESOLVED. Remove all unconditional `True` helpers.

### G05 — Resolve Feedback package deletion as a governed product decision

**Inspect:** `remediation/wave1_5/FEEDBACK_PACKAGE_DECISION.md`, deletion diff, `backend/app/feedback`, `backend/tests/test_feedback*`, `packages/amc-repair-engine`, frontend and deployment manifests.

**Implement:** Produce a feature-level migration matrix for deleted `packages/amc-feedback-loop` (API contracts, classification, adjudication, orchestration, evidence, persistence, audit, triggers and telemetry). Recommend **restore the former package in a separate isolated branch** as the safest default if currently required by deployed or tested flows. If replacing it with main-app modules, implement interface adapters plus parity tests, and request explicit maintainer sign-off before deleting the legacy path. Do not reintroduce insecure auto-approval.

**Acceptance:** Zero unresolved imports/HTTP callers or missing behavior; old suite restored/adapted; explicit maintainer decision stored. If decision unavailable, keep R01 BLOCKED and continue unrelated safe development.

### G06 — Align patch and proposal lifecycle/approval vocabulary

**Inspect:** `backend/app/api/routes/governance.py`, `backend/app/graph/correction_patch_layer.py`, `packages/amc-repair-engine/src/amc_repair/{schemas,patch_layer,server}.py`, `backend/app/schemas/repair_proposals.py`.

**Implement:** Reconcile proposal status, approval state, review stage, publication intent and patch `ACTIVE` status; no undefined `reviewed_approved` or phantom applied state. Approval and promotion are separate actions; require proposer ≠ authorized reviewer, authoritative tenant, immutable evidence version, role scope, and explicit stage/revision. Derive current serving eligibility from persisted receipt, not a caller boolean or stale in-memory object. All legacy calls must route through the same transition service, or fail closed.

**Acceptance:** Approval cannot write canonical truth; neither a microservice token nor a confidence threshold self-approves; stale/no-receipt ACTIVE fails all serving paths.

### G07 — Fix contradictory reports and stop misleading success signals

**Inspect:** `remediation/wave1_4/STATUS.md`, `remediation/wave1_5/STATUS.md`, actual tests, workflow runs.

**Implement:** Regenerate a source-derived task status file with explicit state: `IMPLEMENTED_UNVERIFIED`, `VERIFIED_BY_TEST`, `BLOCKED`, `NOT_IMPLEMENTED`. Do not count unit-only checks as integration proof; avoid treating nonexistent CI as PASS. Record old and new SHA and exact evidence.

**Acceptance:** No “100% complete” assertion while P0 gates remain; every PASS references a real executed test or signed human decision.

---

## 4. Batch P — durable publication, cross-store invariants and rollback (P0)

### P01 — Publication-intent and receipt database migrations

**Inspect:** `backend/app/schemas/publication_intents_table.py`, `backend/alembic/versions/004*`–`008*`, Alembic configuration and startup models.

**Implement:** Add new migration(s) for publication_intents/receipts and any required fields/unique constraints. Ensure proper revisions and ancestor chain; confirm new tables register with SQLAlchemy metadata. Use a durable unique idempotency key on `(tenant, proposal_id, approved_revision, target_entity, source_version, publication_type)` (adjust after actual model audit), with optimistic version fencing, foreign keys and cross-tenant isolation. Immutable receipts have write-once semantics, actual preimage/postimage hashes and verification timestamp.

**Acceptance:** Fresh PostgreSQL upgrade creates tables; upgrade of old schema succeeds; downgrade is rehearsed on a disposable DB only; duplicate intent key cannot create duplicate effects.

### P02 — One real lifecycle orchestrator, not unrelated new service objects

**Inspect:** governance promotion routes, `PromotionService`, `OutboxProcessor`, `GraphPostconditionsService`, `VectorStagingService`, `FeedbackOutcomeService`, both patch stores.

**Implement:** Wire approval to a **single** persisted `PublicationIntent`, enqueue one durable outbox event **inside the approval transaction**, asynchronously acquire lease, execute external effect, read back, persist verified receipt, atomically switch active pointer and emit Feedback resolution event. Remove/guard `PromotionService.apply_approved_proposals` synchronous external mutation pattern and legacy `promote_to_permanent` bypass. One logical proposal must not be applied twice if both old and new paths fire.

**Acceptance:** End-to-end test starts with human-approved PENDING correction and ends with verified ACTIVE only when all required graph/vector writes succeed. Incomplete step -> FAIL/PENDING_RETRY, previous active version preserved.

### P03 — Persist staged vector generations and prove exact vector effects

**Inspect:** `VectorStagingService`, `backend/app/vector/*`, FAISS client, vector payloads, activation/cache code.

**Implement:** Stage in an **isolated, versioned index generation** on disk/object storage (not the serving index). Capture preimage via **exact chunk ID lookup** and persist it keyed by tenant + intent + source revision, never via similarity search. Verify payload count, vector count, document hashes, metadata, tombstones and deterministic query probes. Activate via atomic generation pointer after verified receipt and staged persistence. Rollback atomically switches to previous verified generation. Avoid editing `_payloads` and FAISS IDs ad hoc without index consistency.

**Acceptance:** Pending correction absent from normal retrieval. Crash/restart preserves staging and preimage; failed add/delete does not disappear from retry; rollback truly restores prior index and query behavior. No false `verified=True` receipt.

### P04 — Real graph mutation, readback and rollback preimages

**Inspect:** `GraphPostconditionsService`, `PromotionService._execute_graph_mutation`, GraphStore adapter.

**Implement:** Capture exact preimage using identity/typed property under a transaction; parameterize values and allowlist node labels/attributes. Replace `_delete_node_or_edge` logging with real authorized mutation; do not model update as unsafe delete+create unless domain rules explicitly require it. Record mutation counter/version and same-entity readback. Compare typed value using `Decimal` exact numeric semantics where needed; no float-epsilon tolerance for canonical financial amounts. On rollback, compare current version with recorded expected postimage and restore prior value/edge, verify readback.

**Acceptance:** Wrong value, zero affected nodes, missing driver, concurrent version conflict, partial delete/create and rollback mismatch -> failure + durable recovery instructions; no state marked ACTIVE.

### P05 — Repair outbox, lease, idempotence and crash recovery

**Inspect:** `OutboxProcessor`, `PublicationIntent`, `outbox_events_table.py`, transaction boundaries in `PromotionService`.

**Implement:** Remove `NotImplementedError` handlers by wiring actual verified graph/vector and state transitions (or block release if adapter unavailable). Add atomic lease claim, expiry, heartbeat, worker fencing, idempotency token, bounded retry/backoff, dead-letter queue, metrics and operator replay. Never mark event completed merely because a method returned `None`, a log emitted or one of two external systems succeeded. Stop `db.rollback()` from reversing earlier SQL flags after independent Neo4j commits; use one intent per transaction, compensation and reconciliation.

**Acceptance:** Two workers contend for one intent -> one logical effect; crash after Neo4j commit/before SQL ACK -> eventual consistent VERIFIED or compensated failure; replay no duplicate mutation.

### P06 — Rollback after actual publication, not only while staged

**Inspect:** `VectorStagingService.rollback_staged`, `GraphPostconditionsService.rollback_staged`, `RollbackService`, receipts and active-version pointers.

**Implement:** Preserve preimages and operation journal **after apply_staged** until rollback window elapses and resolution is final. A failure after graph commit/vector activation must be reversible to prior version. If preimage missing, fail safe and signal manual recovery; never treat `restored=False` as successfully rolled back. Audit who initiated rollback, reason and observed postcondition.

**Acceptance:** Deploy v2 and actually roll back to v1; queries, graph and hash match v1. Survive process restart. Reject rollback when a legitimate newer version superseded the target.

### P07 — Wire receipt-backed eligibility across all serving paths

**Inspect:** `FastPathInterceptor`, `retrieval/orchestrator.py`, `backend/app/graph/correction_patch_layer.py`, Repair microservice `server.py`, chat/query/stream/follow-up and caches.

**Implement:** Single `is_serving_eligible(patch, tenant, active_dataset_version, active_index_generation)` function. ACTIVE alone insufficient: require actual receipt, verified external postconditions, source version, tenant, unexpired approval and correct active pointer. `approved=True` and confidence are never enough. Read from persisted cache-safe adapter; stale cache versions are invalidated on activation/rollback. Every fallback path shares the rule.

**Acceptance:** One pending/approved/staged patch never appears in any answer context, direct response, stream, cache or provenance. A rolled-back value disappears immediately upon version switch.

### P08 — Feedback causal lifecycle and source of truth

**Inspect:** `FeedbackOutcomeService`, `feedback/repair_linkage.py`, `app/services/repair_integration.py` and issue tables.

**Implement:** Record issue→evidence→proposal→approver→intent→receipt→ACTIVE version as persisted causal chain. On failure, status remains IN_REPAIR/NEEDS_REVIEW with diagnostic reason. On rollback, reopen dependent issues and invalidate correction citations. No unverified local-memory list can override DB truth.

**Acceptance:** True resolution only after verified active fact, rollback always reopens and evidence is inspectable; human audit trace is complete.

### P09 — Operational telemetry bound to real events

**Inspect:** `OperationalMetricsService`, existing `publication_metrics.py`, Prometheus/observability endpoints.

**Implement:** Emit monotonic counters/histograms with appropriate low-cardinality labels, durable event IDs/correlation, outcome-specific failures; track queue age, retries, lease recovery, activation error budget, rollbacks, latency, token/API/vector/graph cost. Explicit `UNKNOWN` for missing uptime evidence, not 100% availability. Build structured operational review dashboard based on actual captured evidence, not simulated samples.

**Acceptance:** Induced failures cause expected counters, red SLO alerts and traceable attempts; missing telemetry never yields PASS.

### P10 — Ensure old/new APIs and service tokens cannot bypass the orchestrator

**Inspect:** `governance.py`, `repair_client.py`, repair microservice auth/server, background scheduler.

**Implement:** Single trust boundary for end-user, service and tenant. Direct approve/promote/batch endpoints call common service. Role, service scope, separation of duties and tenant authorization are checked against verified identity before any mutation. Reject unknown/legacy status, duplicate messages and absent approval record.

**Acceptance:** Fuzz all approval and mutation endpoint variants, including caller `approved=true`, user-role headers, forged service token, self-approval, cross-tenant, expired evidence and background batch.

---

## 5. Batch F — financial accuracy, deterministic queries and data governance (P0)

### F01 — Independent data-steward decisions and source policy

Record explicit **decision-required** fields: AAUM period/additivity/grain, AMC/scheme/plan identity, NAV date-as-of semantics, closure-date meaning, currency/unit/scale, data completeness and allowed aggregations. If no signature, block affected calculations. Technical agent may implement gates and tests, **not choose** business meanings.

### F02 — Canonical identity model and deterministic aggregation

Stop grouping by `scheme_display_name` alone. Adopt validated canonical `amc_id + scheme_id + plan_option_id + period` or the actual approved source grain. Dedup row identity and distinguish plan-level AAUM from scheme-level AAUM. Group by IDs, not display labels. Use independent gold cases with duplicate scheme names across AMCs.

### F03 — Decimal from source through result

Store/parse exact scaled decimal values at ingest; do arithmetic in exact Decimal/scaled integer with explicit rounding policy (on **final** values, not on each input unless defined); no IEEE float SQL aggregate followed by Decimal string formatting. Test `0.1+0.2`, large values, zeros, nulls, negative/invalid cases and cross-period unit mismatch.

### F04 — NAV observation identity/date correctness

Make NAV date, value, scheme, plan and source record come from one observation; no `LIMIT 1` hiding multiple valid plan choices. Return `AMBIGUOUS_QUERY` with candidates and prompt for plan/date where necessary. Implement exact and as-of rules under approved policy.

### F05 — Real manifest and row-level integrity

Validate actual ingestion manifest schema, original rows, parsed rows, chunk count and *actual bytes* for SHA-256, per-row provenance, duplicate/incomplete/quarantined counts and invalid NAV/AAUM independently. Do not assume `row_count / 1000` chunks. Reject hash mismatch, 0-row accidental publication and partial failed batch. Preserve PDF/TXT behavior.

### F06 — Durable atomic dataset version activation

Create lifecycle `DISCOVERED→STAGED→RECONCILED→REVIEWED→ACTIVE` in SQL with versioned source hashes, audit events, isolation and rollback. Maintain one active pointer per tenant/dataset; serving queries must use the active version consistently. Test cold clone and failure during activation.

### F07 — Aggregate provenance and independent gold

Provenance must include **all contributing source row IDs**, source version, filters, metric operation, grain, effective date, intermediate calculations and final hash (do not trim proof to 50 rows). Store full proof internally; API can paginate proof safely. `is_gold` means checked against independently authored expected results, not a metric safety category.

### F08 — Numeric fail-closed routing without LLM escape

If typed planner returns blocked/ambiguous/unavailable/invalid, all `/query`, `/query/v2`, `/query/stream`, `/chat`, streaming and follow-up modes show that structured response. Do not silently fall back to Pandas, graph language overlays or LLM-generated numbers. Non-numeric PDF/TXT retrieval stays operational.

### F09 — 30→50 independent CSV controls and PDF/TXT regression

Seed ≥30 observed real CSV failure prompts, grow to ≥50 independent numeric tests; include AMC top-X, scheme rank, quarter, source identity, NAV pairing, aggregation, rounding and unapproved AAUM cases. Include ≥15, then ≥50 PDF/TXT control questions. Gold answers must be independently calculated, not produced by the same SQL/planner under test.

### F10 — Control generated SQL, filters, and planner ambiguity

Explicitly bind tenant, dataset version, quarter/as-of, AMC, plan/scheme filters. No incomplete group-by, implicit quarter default for an otherwise unscoped financial question, interpolated unsafe field name or ambiguous name. Run queries against real SQLite/PostgreSQL fixture as relevant to actual repository; compare engine outputs and column types.

---

## 6. Batch Q — answer surfaces, Feedback parity and user experience

**Q01 — Route parity:** Typed numeric decision, error codes, active version and citations identical across query/chat/stream and fast path; build one runtime endpoint inventory and integration matrix.

**Q02 — Frontend/API:** Restore real Admin ingestion tasks, proposed edges, audit tenant filter and metrics or return honest documented `503`, not mock success. Frontend needs meaningful states, not infinite spinners or silent success. Verify auth, 401/403, multipart upload, status schema and deprecation path.

**Q03 — Feedback compatibility:** Resolve R01 maintainer choice (restore prior package vs versioned replacement); run old and new contract tests. No silent missing HTTP handlers or lost adjudication flows.

**Q04 — Versioned citation receipt:** Each corrected answer links to original source rows/document offsets, approval, mutation receipt, active version and rollback status, subject to authorization; correct value without a source is not authoritative.

**Q05 — Deterministic error UX:** Show blocked metric, ambiguous NAV plan, unavailable data, pending correction and stale deployment as distinct user-understandable structured errors. Frontend never renders false totals or unverified repair facts.

**Q06 — Privacy/security:** Tenant isolation across Graph/FAISS/SQL/Feedback; verify service scopes, PII minimization, no raw credentials, secure invite lifecycle and audit redaction. No sensitive error internals in client responses.

**Q07 — Performance and resilience:** Compare before/after latency, cache hit/miss, token cost, vector reads, index build cost and recovery duration; enforce clear SLO windows under load with abort/rollback on violations.

---

## 7. Batch A — executable assurance, migrations and release gates

### A01 — Fix GitHub Actions trigger coverage and failing-open validation

**Observed:** `.github/workflows/amc-assurance.yml` triggers push on `main, develop, feature/*`; it **does not cover `amc-dev`**. PR target only `main`. GitHub Actions returned zero runs for `amc-dev` at reviewed SHA.

**Implement:** Include `amc-dev` in push/PR target coverage. Gate release on real actions status and branch protection (where permissions allow); add concurrency protection. Use deterministic lock files and pinned action versions/permissions. Prefer isolated service containers and minimal secret exposure.

**Remove:** `gitleaks ... || echo`, `pip-audit || echo`, fake `echo P95 latency`, fake `echo canary complete`, fake `echo RELEASE APPROVED`. Ensure dependencies/tools actually install, and fail if unavailable. Use a real secrets scanner and Python dependency audit with actionable findings.

**Acceptance:** A seeded secret, vulnerable requirement and deliberate failing pytest each fail its proper job and block release; `amc-dev` push triggers real run.

### A02 — Repair CI test file paths and pytest invocation

**Observed:** Workflow references `tests/regression/`, `tests/fault_injection/` which are absent from inspected Git tree, and uses `pytest --deterministic` without verified plugin. Test jobs may not install all dependencies. `py_compile app/**/*.py` is not a runtime import test.

**Implement:** Use real test paths (`test_wave15_publication_fault_injection.py` etc.), `pytest -q --junitxml=...`, explicit required extras, Python package imports, startup smoke tests and artifact retention. Add proper test suites as files rather than echoing test plans. Separate fixtures for Postgres, Neo4j, FAISS and any Redis use; do not call production.

**Acceptance:** Clean checkout executes every claimed suite; no skips silently counted as gates; test results contain pass/fail/skip and reproducible revision hash.

### A03 — Real migrations and safe rehearsal

**Observed:** `backend/scripts/migrate_rehearse.py` yields an existing `DATABASE_URL`, has a downgrade step that **does not execute**, and prints “Schema validation passed” without checking. Schema models for publication intents lack visible Alembic migration.

**Implement:** Provision disposable PostgreSQL database in CI; run upgrade head, verify tables/indexes/check constraints, inspect revision chain, downgrade only on **disposable** DB, re-upgrade, then run models/contract tests. Never connect to user production DB for destructive steps. Fail on data/schema mismatch or broken revision graph.

**Acceptance:** Fresh install and existing-version migration both work. Deliberately missing migration fails CI. Evidence includes revision list and schema diff/checks.

### A04 — Rewrite false-positive test assertions

**Observed:** `backend/tests/test_wave15_publication_fault_injection.py` includes `assert result is False or result is True`, simulated lease/restart tests and mocked constructors. These are not reliable cross-store integration proof. Older Wave 1.4 suite includes no-op tests and `assert True` patterns.

**Implement:** Replace with assertions against *persisted* SQL state, GraphStore state, FAISS generation pointers and output contexts. Verify failure injection with real adapters or contract-faithful fakes and add live disposable-service tests. Classify unit vs integration vs E2E accurately. Remove `pass`-only tests, tautological assertions and unreasonably broad skip markers.

**Acceptance:** Deliberately sabotage an external effect and see test FAIL; tests require exact values/outcomes, not “either result accepted.”

### A05 — Security and business policy negative matrix

Verify anonymous/scope/tenant/role headers/self-approval/forged service token, replay, duplicate approval, wrong identity, mismatched signed policy, cross-tenant reading, stale publisher, revoked approval and cached pending fact. Confirm distinct human approver and independent data-steward authorization.

### A06 — Recoverability, SLO and monitored canary

Exercise restart after external write, failure before SQL commit, two workers claiming one event, data corruption, wrong graph readback, FAISS build failure, partial dataset migration, rollback concurrency and missing monitoring. Store trace/correlation IDs, real p95/error windows and no-traffic UNKNOWN. Canary is a **staging-only rehearsal** unless an authorized operator approves live deployment.

### A07 — Source/recipe/credential hygiene

Audit historical tracked `backend/app/auth/data/users.json` and `backend/config/users_rbac.json` for safe sample/production content and ensure no real credentials leaked. Audit vector payload file changes and dependency lockfile for scope/intent. Do not commit test tokens, private source data or environment files.

### A08 — Formal evidence and final CTO release decision

Commit under `remediation/wave1_6/`:

- `SOURCE_BASELINE.md` (HEAD SHA, compared base, environment and input hashes)
- `CRITICAL_FINDINGS.md` (each V16 finding and code change)
- `TASK_STATUS.md` + `TASK_MATRIX.csv` (all 42 tasks G01–G07, P01–P10, F01–F10, Q01–Q07, A01–A08; actual count 42)
- `POLICY_DECISIONS.md` (human-only pending decisions and approved sources)
- `PUBLICATION_STATE_CONTRACT.md` + `RECOVERY_RUNBOOK.md`
- `FINANCIAL_GOLD_CASES.csv` + `SOURCE_PROVENANCE_MANIFEST.json` (synthetic fixtures only)
- `ROUTE_PARITY_MATRIX.csv` + `FEEDBACK_COMPATIBILITY.md`
- `MIGRATION_EVIDENCE.md`, `TEST_RESULTS.md`, `CI_RUNS.md`, `FAILURE_INJECTION.md`, `RELEASE_GATE.md`

**Documentation must point to real commands, actual exit codes, commit SHA, CI run URLs, test counts including skips, test environment, evidence artifacts and residual risk owner.** No synthetic “all tests passed” prose.

---

## 8. Mandatory adversarial tests (minimum)

### Identity / lifecycle

1. Anonymous approval or mutation endpoint => 401.
2. Forged `X-User-Role: admin` => no privilege elevation.
3. Wrong tenant, including caller-supplied tenant ID => no leakage/mutation.
4. Proposer attempts own approval => deny.
5. Invalid/stale/revoked approval => reject publication.
6. Caller sends `approved=true` or `status=ACTIVE` => cannot publish.
7. Valid APPROVED without external receipt => not served.
8. `PENDING`, `STAGED`, `VERIFIED` and `ROLLED_BACK` patches absent from all answer paths.
9. Legacy `promote_to_permanent` / batch endpoint cannot bypass canonical state machine.
10. Missing or invalid `PublicationIntent` schema/migration => cold start fails explicitly.

### Graph / FAISS / outbox

11. Graph driver unavailable => no APPLIED, ACTIVE or phantom success.
12. Graph matches no node => no verified receipt.
13. Graph returns wrong field/value => reject and preserve old version.
14. Graph numeric value drift beyond approved Decimal precision => reject.
15. Graph update/delete actually mutates and readback matches; no log-only effect.
16. Two workers claim same intent => one logical mutation.
17. Crash after graph commit, before SQL ACK => reconcile without duplicate.
18. FAISS staging corrupt or query probe wrong => no activation.
19. Vector preimage exact-ID retrieval, not nearest-neighbor search.
20. Restart between stage and apply => staged intent recovered.
21. FAISS failure after graph change => old active index remains; compensation recorded.
22. Successful activation v2 then rollback restores v1 exact payload/index hash.
23. Partial apply followed by rollback after staging map cleared still restores v1.
24. Wrong active generation or stale source version => no corrected answer.

### Feedback

25. Nonexistent publication intent => issue remains IN_REPAIR.
26. Present intent with missing receipt => issue remains IN_REPAIR.
27. Receipt belongs to different tenant/version => reject resolution.
28. Verified but not ACTIVE => cannot RESOLVE.
29. ACTIVE + correct signed receipt => RESOLVED and causal chain persisted.
30. Rollback => affected issues NEEDS_REVIEW and stale citations invalid.
31. Deleted Feedback package use case => feature restored or explicit blocked contract.

### Financial

32. AAUM without steward approval => `METRIC_POLICY_BLOCKED` for SUM/AVG/RANK.
33. Approved exact NAV lookup with multiple valid plan options => `AMBIGUOUS_QUERY`.
34. AMC name collision and scheme display-name collision => no merged funds.
35. Quarter mismatch or hidden period default => blocked/clarified.
36. `Decimal('0.1') + Decimal('0.2')` exact expected result.
37. Large/noninteger AAUM, nulls and duplicated options => independent gold.
38. Invalid manifest hashes/row counts/chunk checks => quarantine.
39. Failed activation after staged source => old active dataset remains.
40. Unavailable typed numeric source => no LLM/Pandas numeric fallback.
41. Aggregate full contributor-row lineage reconstructs sum and hash.
42. ≥30 observed CSV failures and ≥15 PDF/TXT control questions independently pass; expand to ≥50 each.

### Assurance

43. CI runs on `amc-dev`; `gitleaks`/dependency scan deliberate fail blocks merge.
44. Real migration upgrade/downgrade/re-upgrade on disposable database; missing revision fails.
45. Test with `assert True`/tautology removed; sabotaged external step fails relevant test.
46. Canary health/SLO evidence is actual, not `echo`, and absence of evidence is UNKNOWN/BLOCK.

**Do not claim all 46 tests already exist.** These are acceptance scenarios to implement and run, with full evidence.

---

## 9. Required implementation sequence and pull request boundaries

**PR-1 — Safety and verification foundations (G01–G07 + A01–A03):** Disable unapproved AAUM computations, fail-closed Feedback outcome, fix op mapping, correct CI trigger/suppression, add migration and negative tests. Make this the first reviewable milestone. Resolve missing business approvals by blocking, not fabricating.

**PR-2 — Durable publication (P01–P10):** Wire authoritative intent/outbox/graph/FAISS with real receipts, idempotence and persisted rollback; eliminate old bypasses. Include crash/dual-worker tests. PR must remain non-deployable until verified.

**PR-3 — Deterministic financial engine (F01–F10):** Canonical identities, exact arithmetic, source manifest reconciliation, stable dataset activation, full provenance and numeric routing. Gate unknown AAUM semantics behind steward decision.

**PR-4 — Answer and Feedback parity (Q01–Q07):** query/chat/stream/frontend parity, issue lifecycle, compatibility of removed Feedback package, security, PDF/TXT and performance controls.

**PR-5 — Assurance/release package (A04–A08):** Real E2E evidence, CI runs, isolation/canary rehearsal, accountable sign-off and release gate. Do **not** deploy automatically or change GitHub branch-protection/security settings without owner approval.

**Agent output contract at the end of each PR:** base/head SHA, changed files, task-by-task DONE/PARTIAL/BLOCKED, exact tests/commands and outcomes, CI run URLs, rollback notes, unresolved dependencies, and a short recommendation. A high-level progress paragraph is insufficient.

---

## 10. Suggested verification commands — run from clean, isolated workspace

These are **commands to adapt and actually execute**; they are not a report of passing results. Never run destructive migration/downgrade against production, staging shared with others, or the user's real database.

```bash
# From cloned repository root, after environment setup
python -m compileall -q backend/app

cd backend
python -m pytest -q tests/test_wave14_p0_containment.py
python -m pytest -q tests/test_wave15_publication_fault_injection.py
python -m pytest -q tests/test_tabular_queries.py tests/test_wave0_verification.py
python -m pytest -q tests/test_e2e_user_journey_feedback_repair.py tests/test_repair_linkage.py
python scripts/audit_clean_checkout.py
# WARNING: migrate_rehearse.py is currently NOT verified as disposable.
# First fix it to create and use a dedicated throwaway DB; never run it
# until that guard is proven by tests.
```

Add new, appropriately named modules for Wave 1.6:

- `backend/tests/test_wave16_policy_approval_and_exact_math.py`
- `backend/tests/test_wave16_financial_gold.py`
- `backend/tests/test_wave16_feedback_publication_causality.py`
- `backend/tests/test_wave16_graph_vector_effects.py`
- `backend/tests/test_wave16_outbox_recovery_and_rollback.py`
- `backend/tests/test_wave16_serving_parity.py`
- `backend/tests/test_wave16_migrations.py`
- `backend/tests/test_wave16_adversarial_access.py`
- `backend/tests/test_wave16_ci_assurance_contract.py`

Add disposable PostgreSQL, Neo4j, FAISS and Redis (if used) service fixtures. Tests should not depend on production databases, actual customer financial documents, third-party API calls or live secrets.

---

## 11. Copy/paste into Codex (single bulk assignment)

```text
ROLE: Act as principal engineer, data architect, AI Governance lead, security
reviewer and independent release-assurance engineer for the AMC Context
Engineering POC. Execute code and tests, not a design-only workstream.

REPOSITORY: nusummit-spg/amc-context-engineering-poc
BRANCH: amc-dev
PIN BASELINE SHA: 4ede4338642949f0a32ee0672b4dc09616659193
HANDOFF: AMC_Wave1_6_Next_Implementation_Agent_Handoff_2026-11-06.md

READ (in order):
1. THIS handoff, Sections 1-10.
2. remediation/wave1_5/STATUS.md and FEEDBACK_PACKAGE_DECISION.md.
3. docs/AMC_Tasks_3_11_26/AMC_Specs/03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md.
4. .../04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md.
5. .../05_ASSURANCE_SECURITY_RELEASE_GATES.md.
6. Current code in planner, executor, financial policy, Feedback outcome,
   publication intent, vector staging, graph postconditions, governance,
   outbox, legacy patches, repair integration and GitHub Actions.

BULK EXECUTION:
- Create a new feature branch from pinned SHA. Do not force-push.
- First implement G01-G07 and A01-A03 as PR-1, using real negative tests.
- Then implement P01-P10 (durable effects/recovery); F01-F10 (financial
  correctness) can proceed in parallel after shared policy agreement.
- Integrate Q01-Q07 and A04-A08 in reviewable PRs.
- Work on as many related tasks as practical per run, but keep commits
  scoped for independent audit.

CRITICAL POLICIES:
- AAUM SUM/AVG/RANK is PENDING human steward signoff; BLOCK, do not invent.
- A successful Decimal conversion cannot fix an incorrect GROUP BY.
- No pending patch, approved-only patch, fake receipt or stale version serves.
- Feedback RESOLVED requires actual, tenant-bound verified ACTIVE evidence.
- No in-memory preimage-only design qualifies as durable rollback.
- Outbox completion requires real observed effects, not logs or stub returns.
- No arbitrary confidence threshold or service token self-approves facts.
- CI must run on amc-dev, fail on scan/test errors and use real SLO/canary.
- Do NOT run Alembic downgrade on existing user databases.
- Preserve PDF/TXT behavior and prior source provenance.
- Do not deploy to production or silently change owner security settings.

ACCEPTANCE:
- Run every case in Section 8 and record actual passes/fails/skips.
- Separate unit, integration and E2E results; tests with tautologies do not count.
- Deliver code, migrations, fixtures, complete receipts, verified readbacks,
  full provenance and explicit release gates.
- Provide exact PR/commit SHAs and clean-checkout CI run URLs.
- Maintain BLOCK while any P0 scenario lacks passing evidence or a required
  human stewardship/product decision is missing.

DELIVERABLES:
- PR-1..PR-5 (or equivalent atomic commits on dedicated branch)
- remediation/wave1_6/ evidence bundle per Section 7 A08
- Short source-derived summary: DONE / PARTIAL / BLOCKED + next blockers.

DO NOT:
- Mark a service DONE because a source file was created.
- Count docs/echo lines/synthetic tests as observed release evidence.
- Claim 100% passed from a selectively executed or skipped suite.
- Choose AAUM business rules without actual steward approval.
- Treat a non-existent CI run as a passed CI job.
```

---

## 12. CTO review rubric for the next push

On the next `amc-dev` or Wave 1.6 feature push, inspect changed files against this checklist:

1. AAUM approval source and operation mapping; no hardcoded silent business approval.
2. Real exact numeric SQL, canonical identity and source-row proof; no arbitrary group value.
3. Real persisted Feedback publication checks and rollback reopen.
4. Versioned durable vector staging/activation and exact payload lookup.
5. Neo4j mutation/rollback readback, no log-only delete/update.
6. SQL Alembic migrations for every new table and revision chain coherence.
7. One authoritative outbox processor with replay, fencing and transactional boundaries.
8. No alternate approval or serving bypass in fast path, monolith, microservice or streaming mode.
9. Feedback package deleted behavior explicitly restored/replaced or blocked by maintainer.
10. Actual runnable tests validate failed operations; zero tautological/no-op tests accepted as evidence.
11. `amc-dev` workflow runs exist and pass, fail-closed scans, real migration rehearsal and observed SLO/canary.
12. All seven gates below have code + independent evidence.

| Release gate | Required evidence | At reviewed HEAD |
|---|---|---|
| `GOV` | Approved policy registry, four-eyes, tenant and source authority | **BLOCK** |
| `PUB` | Durable, verified graph/vector + retry/rollback | **BLOCK** |
| `NUM` | Exact AAUM/NAV with approved grain and independent gold | **BLOCK** |
| `ING` | Real source manifest/hash and versioned activation | **BLOCK** |
| `FB` | Feedback service parity and no fake RESOLVED | **BLOCK** |
| `E2E` | Query/stream/citations/PDF-TXT parity | **BLOCK** |
| `OPS` | Clean CI, migration, security, SLO, canary and rollback evidence | **BLOCK** |

**Overall at SHA `4ede4338642949f0a32ee0672b4dc09616659193`: BLOCK.** The next agent may ship additional *safe code to a review branch*, but must not imply production readiness until an independent re-audit of the resulting SHA and actual run evidence supports it.
