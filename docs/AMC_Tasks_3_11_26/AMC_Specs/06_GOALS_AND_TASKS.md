# 06 — Engineering Goals and 196 Executable Tasks

**Each goal has exactly 14 tasks.** Tasks are proposed; none is recorded as executed. Goal IDs and task IDs are stable for issue tracking. Each task has an action and independently verifiable acceptance evidence. Dependencies are suggested logical sequencing, not exhaustive change dependencies.

## Priority legend
- **P0**: urgent security/truth safety, baseline correctness or release gate prerequisite.
- **P1**: required hardening before broad production rollout.
- **P2**: optional optimization after correctness (covered in P1 goal workstreams but may be scheduled later).

## Goal index

| Goal | Title | Priority | Dependencies | Tasks |
|---|---|---|---|---:|
| G01 | Reproducible baseline and CSV incident diagnosis | P0 | — | 14 |
| G02 | Access control, identity and immediate safety controls | P0 | G01 | 14 |
| G03 | Canonical financial data model, identity and metric dictionary | P0 | G01 | 14 |
| G04 | Completeness-safe CSV/XLSX ingestion and version publication | P0 | G02, G03 | 14 |
| G05 | Typed deterministic financial query engine | P0 | G03, G04 | 14 |
| G06 | Intent routing, hybrid retrieval and context engineering | P1 | G04, G05 | 14 |
| G07 | Claim-level grounding, citations and confidence integrity | P1 | G05, G06 | 14 |
| G08 | AMC Core boundaries, data stewardship and API compatibility | P1 | G03, G05 | 14 |
| G09 | Feedback intake, issue intelligence and adjudication | P1 | G02, G07, G08 | 14 |
| G10 | Repair governance, patch isolation, safe publication and rollback | P0 | G02, G05, G07 | 14 |
| G11 | Cross-module messages, idempotency and failure recovery | P1 | G08, G09, G10 | 14 |
| G12 | Regulatory currency, source lineage and domain governance | P1 | G03, G04, G07, G10 | 14 |
| G13 | Independent benchmark, assurance harness and fail-closed gates | P0 | G01, G03, G05, G07, G10 | 14 |
| G14 | CI/CD, deployment reproducibility, operations and sustainable scaling | P1 | G02, G04, G08, G11, G13 | 14 |


## G01 — Reproducible baseline and CSV incident diagnosis

**Priority:** P0  
**Depends on:** None  
**Code areas:** `backend/app/retrieval, backend/app/services/scheme_aggregation_service.py, backend/scripts, mf-context-engine`  
**Goal acceptance:** Frozen failing examples, execution-path evidence and classification of exact CSV correctness defects.

1. **G01-T01 — Pin branch SHA and all runtime data/model/config versions.** Acceptance: Manifest lists exact SHA, providers, active corpus and dataset hash.
2. **G01-T02 — Export current OpenAPI schema and all mounted routes.** Acceptance: Route inventory includes methods, auth and response contracts.
3. **G01-T03 — Record active graph/vector/SQL/index manifests without secrets.** Acceptance: Read-only inventory shows counts and version for each plane.
4. **G01-T04 — Collect 30 observed incorrect CSV user questions.** Acceptance: Each incident contains actual response, expected interpretation and timestamp.
5. **G01-T05 — Collect 15 good PDF/TXT control questions.** Acceptance: Control set is fixed before CSV remediation.
6. **G01-T06 — Tag each CSV error by root-cause taxonomy.** Acceptance: Every incident assigned primary and secondary fault category.
7. **G01-T07 — Capture route-level query traces under instrumented mode.** Acceptance: Each trace shows chosen fast path, SQL, graph, vector and patch calls.
8. **G01-T08 — Build source-row and chunk reconciliation probe.** Acceptance: Reports raw row count, sum of 22 chunk counts and gaps/overlaps.
9. **G01-T09 — Profile Scheme_Code/ISIN/name/AMC collisions and nulls.** Acceptance: Duplicate and ambiguous-key report available for steward review.
10. **G01-T10 — Profile AAUM quarters, NAV dates and closure-date conventions.** Acceptance: Report shows date distributions and questionable status inference.
11. **G01-T11 — Compute independently reviewed exact-answer pilot gold.** Acceptance: Gold includes source_row_id and approved metric interpretation.
12. **G01-T12 — Re-run current pipeline without changes against fixed probes.** Acceptance: Baseline result hashes and pass/fail table frozen.
13. **G01-T13 — Create sanitized reproducibility bundles for top failures.** Acceptance: Each bundle reproduces without production secret or PII leakage.
14. **G01-T14 — Publish prioritized fault ledger with trace/evidence links.** Acceptance: P0/P1 issue owners, fix scope and regression tests assigned.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G02 — Access control, identity and immediate safety controls

**Priority:** P0  
**Depends on:** G01  
**Code areas:** `backend/app/api, backend/app/compliance/security.py, backend/app/config.py, backend/app/auth, packages/*`  
**Goal acceptance:** No unauthenticated mutation, client-header privilege, cross-tenant leakage, or unapproved truth override.

1. **G02-T01 — Inventory public and protected routes with threat model.** Acceptance: Every route classified by principal, tenant, role and operation.
2. **G02-T02 — Enforce default-deny authentication at API boundary.** Acceptance: Sensitive anonymous requests yield 401 in automated matrix.
3. **G02-T03 — Replace X-User-Role and default ADMIN role resolver.** Acceptance: Role authorization comes only from verified server identity.
4. **G02-T04 — Bind tenant and scopes to authenticated principal.** Acceptance: Request-provided tenant/user/tier cannot elevate privileges.
5. **G02-T05 — Require admin permissions for user creation/deletion/listing.** Acceptance: Unauthorized requests return 403 without disclosure.
6. **G02-T06 — Require scoped ingestion and source-download permissions.** Acceptance: Anonymous upload/download and cross-tenant access denied.
7. **G02-T07 — Protect graph, compliance and governance routes.** Acceptance: Role matrix regression covers all methods.
8. **G02-T08 — Remove predictable new-user password and password reflection.** Acceptance: Password setup uses one-time expiring enrollment flow.
9. **G02-T09 — Validate prod configuration and rotate nonlocal default credentials.** Acceptance: Startup fails if insecure prod secrets are in use.
10. **G02-T10 — Bind quotas to verified principal and plan.** Acceptance: Spoofed X-User-ID/X-User-Tier has no effect on quota bucket.
11. **G02-T11 — Require authenticated service-to-service identity and scopes.** Acceptance: Untrusted internal HTTP request denied.
12. **G02-T12 — Disable automatic canonical repair promotion in config and code.** Acceptance: No feedback can change active facts without approval.
13. **G02-T13 — Exclude pending repairs from all serving paths and caches.** Acceptance: Adversarial pending patch cannot alter answer.
14. **G02-T14 — Automate SAST, secrets, access-negative and threat-model gates.** Acceptance: Security evidence saved with immutable CI run IDs.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G03 — Canonical financial data model, identity and metric dictionary

**Priority:** P0  
**Depends on:** G01  
**Code areas:** `backend/app/tabular/contracts.py, models/scheme_aggregation.py, data dictionary`  
**Goal acceptance:** Steward-signed semantics for 16 source fields, entity hierarchy, temporal definitions and permitted calculations.

1. **G03-T01 — Inventory CSV/XLSX fields and all observed aliases.** Acceptance: Published schema registry includes raw and normalized types.
2. **G03-T02 — Define AMC, scheme, plan and option identity hierarchy.** Acceptance: Diagram and unique/collision rules signed by data steward.
3. **G03-T03 — Separate Scheme_Code, ISIN, display name and source row identifiers.** Acceptance: Composite identity tests prevent name-only conflation.
4. **G03-T04 — Define immutable source_row_id and observation_id.** Acceptance: Stable row anchors across chunking; changed content creates new ID.
5. **G03-T05 — Specify AAUM grain, aggregation safety and data quarter.** Acceptance: Every SUM/AVG rule approved with examples and exclusions.
6. **G03-T06 — Specify NAV per-unit metric and as-of date policy.** Acceptance: No implicit mixed-date NAV ranking.
7. **G03-T07 — Define fund status semantics and Closure_Date interpretation.** Acceptance: Sample launch=closure case does not misclassify without proof.
8. **G03-T08 — Define category/type normalization tables and unknown handling.** Acceptance: Unrecognized variants are retained and flagged.
9. **G03-T09 — Define source unit conversion and Decimal precision.** Acceptance: Rounding, overflow and null policies tested.
10. **G03-T10 — Define missing, zero, placeholder and invalid values.** Acceptance: Dash or blank inputs never silently convert to zero.
11. **G03-T11 — Define duplicate record and cross-quarter aggregation policies.** Acceptance: Tests cover repeated plan and overlapping periods.
12. **G03-T12 — Version metric definitions separately from raw datasets.** Acceptance: Plan hash records metric_registry_version.
13. **G03-T13 — Implement entity alias registry and conflict review process.** Acceptance: Ambiguous canonical matches cannot silently merge.
14. **G03-T14 — Sign and freeze representative known-answer dataset.** Acceptance: Independent source-row gold approved by business owner.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G04 — Completeness-safe CSV/XLSX ingestion and version publication

**Priority:** P0  
**Depends on:** G02, G03  
**Code areas:** `backend/app/ingestion, backend/app/engine/document_extractors.py, backend/app/tabular, backend/app/vector/client.py`  
**Goal acceptance:** All required rows parsed and validated, typed snapshot published atomically; no partial activation.

1. **G04-T01 — Implement streaming full-file CSV parser with explicit encoding.** Acceptance: Full source row count accounted for; no silent max_pages truncate.
2. **G04-T02 — Add XLSX sheet/formula/date handling policy and parser.** Acceptance: Golden workbook fixtures match approved Excel interpretation.
3. **G04-T03 — Validate input types, size, field names, schema version and malware policy.** Acceptance: Malformed/oversize inputs rejected safely.
4. **G04-T04 — Reconcile all 22 chunks with original source hash and offsets.** Acceptance: No duplicate, gap, missing chunk or conflicting header activates.
5. **G04-T05 — Create typed staging tables for source rows, NAV and AAUM.** Acceptance: Row anchors and decimal fidelity validated by round trip.
6. **G04-T06 — Canonicalize identity and retain raw values with normalization audit.** Acceptance: Every transformed value traces to original field.
7. **G04-T07 — Quarantine invalid rows with reason, severity and source location.** Acceptance: No discarded row without documented reason.
8. **G04-T08 — Implement idempotent ingest ledger and durable stage checkpoints.** Acceptance: Retries do not duplicate observations or vector IDs.
9. **G04-T09 — Generate graph facts from validated typed rows only.** Acceptance: Each graph fact links to row and dataset version.
10. **G04-T10 — Generate secondary semantic summaries for discovery only.** Acceptance: Text index cannot override canonical numeric result.
11. **G04-T11 — Verify graph/vector/typed-store presence for required artifacts.** Acceptance: Publication gate fails when any mandatory plane inconsistent.
12. **G04-T12 — Make version activation a single guarded pointer change.** Acceptance: Readers always see coherent prior or new snapshot.
13. **G04-T13 — Invalidate version-namespaced caches and emit activation event.** Acceptance: Old cached values cannot cross dataset boundary.
14. **G04-T14 — Test failure injection, backfill, diff and rollback of snapshot.** Acceptance: Old active version remains readable on every staged failure.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G05 — Typed deterministic financial query engine

**Priority:** P0  
**Depends on:** G03, G04  
**Code areas:** `backend/app/tabular/planner.py, executor.py, repository.py, backend/app/services/scheme_aggregation_service.py`  
**Goal acceptance:** Exact lookups and aggregations use validated typed plans, stable formulas and independently verifiable result proofs.

1. **G05-T01 — Specify enumerated intents, metrics and operations.** Acceptance: Unsupported metrics/operators fail validation.
2. **G05-T02 — Define typed QueryPlan schema and version.** Acceptance: JSON Schema/Pydantic tests reject unknown fields or unsafe SQL.
3. **G05-T03 — Parse exact key, date and period constraints.** Acceptance: NAV query requires plan identity and approved date rule.
4. **G05-T04 — Create explicit filter and grouping inference policy.** Acceptance: No silent equity/growth/open-ended filters.
5. **G05-T05 — Handle ambiguous scheme, option, date and average grain.** Acceptance: AMBIGUOUS_QUERY returns candidate choices instead of guessing.
6. **G05-T06 — Compile only whitelisted SQL templates with bound parameters.** Acceptance: Injection strings cannot alter SQL plan.
7. **G05-T07 — Enforce tenant and published dataset version inside repository.** Acceptance: Cross-tenant and stale-pointer queries rejected.
8. **G05-T08 — Implement Decimal/scaled-integer math and correct unit rendering.** Acceptance: Test extreme values, nulls, overflow and rounding.
9. **G05-T09 — Implement exact NAV/AAUM lookup and cross-date comparison policies.** Acceptance: Date comparability violations are explicit.
10. **G05-T10 — Implement scheme/AMC/type/category totals via signed metric registry.** Acceptance: All aggregate gold cases exact and independently checked.
11. **G05-T11 — Implement counts, percentages and stable tie-breaking.** Acceptance: Different row ordering yields identical ranked results.
12. **G05-T12 — Produce source-row proof, result hash and excluded-row counts.** Acceptance: Every number can be reconstructed via query-plan receipt.
13. **G05-T13 — Replace existing aggregation implementation with compatibility facade.** Acceptance: Old API contract preserved or versioned migration proven.
14. **G05-T14 — Fail closed on store/query error without generative numeric fallback.** Acceptance: SQL failure yields typed error and no fabricated result.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G06 — Intent routing, hybrid retrieval and context engineering

**Priority:** P1  
**Depends on:** G04, G05  
**Code areas:** `backend/app/retrieval/fast_path_interceptor.py, orchestrator.py, planner.py, context.py`  
**Goal acceptance:** Correct executor selected for financial, regulatory, document and mixed questions with explicit uncertainty.

1. **G06-T01 — Inventory current regex routes and priorities.** Acceptance: Routing decision table includes all existing query families.
2. **G06-T02 — Introduce typed financial/document/mixed classifier.** Acceptance: Test set reports per-intent confusion matrix.
3. **G06-T03 — Resolve scheme and AMC aliases before executor choice.** Acceptance: Ambiguous names cannot select arbitrary entity.
4. **G06-T04 — Separate financial query execution from narrative retrieval.** Acceptance: Numeric operations always use trusted typed result.
5. **G06-T05 — Prevent fallback to vector on typed-executor exceptions.** Acceptance: No wrong number produced on SQL outage.
6. **G06-T06 — Keep PDF/TXT graph+vector retrieval with unchanged controls.** Acceptance: 50 PDF/TXT gold controls show no regression.
7. **G06-T07 — Attach per-result taxonomy/entity/tenant/data-version restrictions.** Acceptance: Cross-namespace retrieval forbidden.
8. **G06-T08 — Improve lexical retrieval with indexed BM25 or equivalent.** Acceptance: Benchmark shows corpus-scale complexity and quality.
9. **G06-T09 — Use reranker only after permission and source filters.** Acceptance: Reranked sources cannot expand authorized result set.
10. **G06-T10 — Join structured data and document evidence by canonical IDs.** Acceptance: Mixed query provenance retains both data versions.
11. **G06-T11 — Plan query decomposition with bounded concurrency and budgets.** Acceptance: A multi-hop query has deterministic max cost.
12. **G06-T12 — Clarify as-of terms and temporal perspective in answer context.** Acceptance: Latest is derived from active snapshot, not wall clock alone.
13. **G06-T13 — Make semantic cache keys include tenant/plan/versions/policy.** Acceptance: No outdated or cross-tenant cached answer reused.
14. **G06-T14 — Shadow-compare old and new routes before cutover.** Acceptance: Logged agreement, mismatches and reversible feature flags.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G07 — Claim-level grounding, citations and confidence integrity

**Priority:** P1  
**Depends on:** G05, G06  
**Code areas:** `backend/app/retrieval/synthesizer.py, context.py, evaluation/, schemas`  
**Goal acceptance:** Every material numeric/regulatory assertion has real evidence or is withheld and logged.

1. **G07-T01 — Define claim and source-attribution schema.** Acceptance: Source anchors include row/line, hash, effective date and access policy.
2. **G07-T02 — Emit row-based citations from typed engine.** Acceptance: Source links resolve to true protected source rows.
3. **G07-T03 — Emit clause/page citations from PDF/TXT evidence.** Acceptance: All regulatory claims have document-version and locator.
4. **G07-T04 — Remove automatic insertion of citation markers on absent support.** Acceptance: Unsupported claim fails citation validation.
5. **G07-T05 — Implement claim splitting and type classification.** Acceptance: Numbers, dates and obligations are separately verifiable claims.
6. **G07-T06 — Verify numeric claims against typed result rows.** Acceptance: Exactly matched values and units required.
7. **G07-T07 — Verify textual claims against authorized source excerpts.** Acceptance: NLI + human calibration distinguish entailment and contradiction.
8. **G07-T08 — Check date, jurisdiction and supersession before regulatory claim.** Acceptance: Outdated citations cannot imply current rule.
9. **G07-T09 — Replace hardcoded high confidence and 1.0 quality scores.** Acceptance: Confidence calibrated from real evaluation evidence.
10. **G07-T10 — Separate provenance, citation and confidence UI fields.** Acceptance: End-user can inspect why answer is supported.
11. **G07-T11 — Return explicit PARTIAL/ABSTAIN results when evidence insufficient.** Acceptance: No narrative fills unsupported numeric gaps.
12. **G07-T12 — Include excluded rows, filters, period and data completeness.** Acceptance: Metadata computed from source not fixed percentages.
13. **G07-T13 — Instrument real timing and token values.** Acceptance: No constant fabricated 2 ms trace or invented token savings.
14. **G07-T14 — Run adversarial unsupported-citation regression.** Acceptance: No citation laundering on unretrieved/irrelevant sources.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G08 — AMC Core boundaries, data stewardship and API compatibility

**Priority:** P1  
**Depends on:** G03, G05  
**Code areas:** `backend/app/api/routes, app/core, app/engine, app/models, frontend API client`  
**Goal acceptance:** AMC service owns approved data and execution contracts while legacy code migrates without regressions.

1. **G08-T01 — Define bounded context ownership for AMC Core, Feedback and Repair.** Acceptance: Architecture decision record assigns authoritative stores and permissions.
2. **G08-T02 — Create internal interface for typed query planning and execution.** Acceptance: AMC API uses injected services rather than global singleton state.
3. **G08-T03 — Remove duplicate graph/vector client behavior or route through facade.** Acceptance: One implementation owns each authoritative operation.
4. **G08-T04 — Split oversized retrieval orchestrator into tested stages.** Acceptance: Small modules have clear typed input/output contracts.
5. **G08-T05 — Unify central router registration and API versioning.** Acceptance: Aggregation routes discoverable and their citations resolve correctly.
6. **G08-T06 — Create source document and dataset catalogs with retention.** Acceptance: Every published source has owner, class and active version.
7. **G08-T07 — Add approved source refresh policy and ingestion scheduling.** Acceptance: Refresh cannot mutate live corpus without gated validation.
8. **G08-T08 — Make user/session/query evidence ownership consistent.** Acceptance: Cross-user and cross-tenant response access denied.
9. **G08-T09 — Implement domain glossary for plan, scheme, option, AMC, NAV and AAUM.** Acceptance: UI and backend use identical financially accurate labels.
10. **G08-T10 — Keep controlled legacy/v2/shadow/canary settings.** Acceptance: Routing choices tested and deprecated endpoints documented.
11. **G08-T11 — Move mutable global caches/jobs to injected lifecycle-managed services.** Acceptance: Multi-worker process starts do not create duplicate jobs.
12. **G08-T12 — Version OpenAPI and client response models with migration adapters.** Acceptance: React Chat/Compare preserve documented behavior.
13. **G08-T13 — Add change-impact inventory linking schema, query and UI consumers.** Acceptance: Every code change identifies affected API/tests.
14. **G08-T14 — Approve architecture ADR and deprecation timeline.** Acceptance: No unowned old path or unsupported endpoint remains.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G09 — Feedback intake, issue intelligence and adjudication

**Priority:** P1  
**Depends on:** G02, G07, G08  
**Code areas:** `backend/app/feedback, app/api/routes/feedback.py, packages/amc-feedback-loop, backend/app/evaluation`  
**Goal acceptance:** All feedback tied to verifiable response evidence, correctly triaged and separated from authority to change data.

1. **G09-T01 — Define feedback event schema and immutable attribution.** Acceptance: Each event links verified actor, response, tenant and timestamp.
2. **G09-T02 — Validate feedback ownership of target response and source access.** Acceptance: Unauthorized actor cannot raise/read another tenant issue.
3. **G09-T03 — Separate explicit feedback from passive inference.** Acceptance: No feedback timeout is labeled as confirmed satisfaction or error.
4. **G09-T04 — Provide claim-specific numeric correction UX.** Acceptance: User can identify exact row/value/date rather than free-text alone.
5. **G09-T05 — Build evidence-pack completeness validator.** Acceptance: Missing response or source prevents automatic repair work.
6. **G09-T06 — Deduplicate issues by entity, metric, intent, period, version and tenant.** Acceptance: Similar but distinct facts remain separate issues.
7. **G09-T07 — Use semantic matching only as triage candidate.** Acceptance: Entity/taxonomy mismatch rejects false merges.
8. **G09-T08 — Define root-cause taxonomy and priority matrix.** Acceptance: Routing error, data error, staleness, citation, auth separately labeled.
9. **G09-T09 — Reproduce reported failure against pinned source and plan.** Acceptance: Stored reproduction hash matches observed output.
10. **G09-T10 — Implement independent adjudication verdicts.** Acceptance: VALID, INVALID, INSUFFICIENT, CONFLICT and STALE outcomes tested.
11. **G09-T11 — Build authenticated reviewer assignment and SLA timeline.** Acceptance: Actor, comment and decision are audited.
12. **G09-T12 — Enforce guarded issue state transitions.** Acceptance: Illegal closure or reopening without evidence blocked.
13. **G09-T13 — Make duplicate feedback concurrent-safe with database unique key.** Acceptance: One logical issue despite multiple simultaneous submissions.
14. **G09-T14 — Render user-facing status without false correction claim.** Acceptance: UI distinguishes RECEIVED, REVIEW, CONFIRMED, FIX RELEASED.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G10 — Repair governance, patch isolation, safe publication and rollback

**Priority:** P0  
**Depends on:** G02, G05, G07  
**Code areas:** `backend/app/services/repair_integration.py, promotion_service.py, app/graph/correction_patch_layer.py, app/api/routes/governance.py, packages/amc-repair-engine`  
**Goal acceptance:** No unapproved patch affects answers; all canonical fact changes use independently verified staged releases.

1. **G10-T01 — Disable hands-free auto approval of finance/regulatory corrections.** Acceptance: Model confidence cannot cause active graph/vector mutation.
2. **G10-T02 — Remove pending-patch instruction text from retrieval context.** Acceptance: Unapproved feedback can never override numeric answers.
3. **G10-T03 — Require published ACTIVE status/version on every patch lookup.** Acceptance: Draft, conflicted and stale patches excluded from serving.
4. **G10-T04 — Define typed repair types and allowed mutation targets.** Acceptance: Generated arbitrary Cypher/SQL not accepted as default patch.
5. **G10-T05 — Bind repair proposal to immutable evidence pack and source base version.** Acceptance: Missing source proof blocks proposal validation.
6. **G10-T06 — Implement source/diff/precondition checks before staging.** Acceptance: Changed base value causes conflict, not overwrite.
7. **G10-T07 — Run deterministic and NLI/LLM assisted checks only as distinct signals.** Acceptance: High model score never substitutes for evidence.
8. **G10-T08 — Use staged isolated dataset/graph/index namespace for mutation.** Acceptance: Production source remains unchanged before approval.
9. **G10-T09 — Enforce least-privilege four-eyes approval for financial/regulatory facts.** Acceptance: Proposer cannot self-approve critical change.
10. **G10-T10 — Make missing graph driver an explicit apply failure.** Acceptance: No proposal marked APPLIED without mutation receipt.
11. **G10-T11 — Verify committed effect by read-back and hash proof.** Acceptance: After-apply postcondition must match expected value.
12. **G10-T12 — Implement atomic active-version switch plus cache-version bump.** Acceptance: Queries pin exactly one published repair-set version.
13. **G10-T13 — Implement durable compensating rollback, quarantine and audit.** Acceptance: Failed canary restores old version and records root cause.
14. **G10-T14 — Replay original bug and broad regression before resolving issue.** Acceptance: Issue close requires passing post-release evidence.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G11 — Cross-module messages, idempotency and failure recovery

**Priority:** P1  
**Depends on:** G08, G09, G10  
**Code areas:** `backend/app/clients, app/feedback/repair_linkage.py, app/services, packages/*, schema/event modules`  
**Goal acceptance:** Reliable AMC→Feedback→Repair choreography even during partial failures and retries.

1. **G11-T01 — Define versioned events with correlation/causation IDs.** Acceptance: Schema registry validates all producers and consumers.
2. **G11-T02 — Bind tenant, actor scope and source version to every message.** Acceptance: Consumers reject missing/unauthorized identity.
3. **G11-T03 — Introduce transactional outbox in authoritative SQL database.** Acceptance: Local state commit and event enqueue cannot diverge.
4. **G11-T04 — Introduce idempotent consumer inbox and event dedupe keys.** Acceptance: At-least-once delivery produces exactly-one logical effect.
5. **G11-T05 — Unify feedback issue and repair task identity mapping.** Acceptance: Remote success/local crash reconciles without duplicate task.
6. **G11-T06 — Define retry policy, dead-letter, backoff and poison events.** Acceptance: Stuck operations visible and replayable by authorized operator.
7. **G11-T07 — Make state transitions optimistic-version-checked.** Acceptance: Concurrent reviewer decisions cannot silently overwrite.
8. **G11-T08 — Implement signed repair action receipts and linkage to issue.** Acceptance: Audit proves approval actor, hash and transaction outcome.
9. **G11-T09 — Use correlation propagation through HTTP and workers.** Acceptance: Single trace reconstructs all three modules.
10. **G11-T10 — Define tenant-aware service availability and circuit breaker behavior.** Acceptance: Outage degrades safely without patch fallback contamination.
11. **G11-T11 — Implement worker leadership or durable lease to prevent duplicates.** Acceptance: Multi-process deployment executes each scheduled job once logically.
12. **G11-T12 — Reconcile patch, proposal, status and active version read models.** Acceptance: Mismatches trigger quarantine not success banner.
13. **G11-T13 — Add end-to-end crash/timeout/duplicate-event chaos tests.** Acceptance: No phantom resolved issue or lost repair after restart.
14. **G11-T14 — Publish data ownership and inter-service dependency map.** Acceptance: Services do not write directly to each other’s authoritative stores.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G12 — Regulatory currency, source lineage and domain governance

**Priority:** P1  
**Depends on:** G03, G04, G07, G10  
**Code areas:** `backend/app/engine/regulatory_lifecycle_enricher.py, graph, ingestion, compliance, source registry`  
**Goal acceptance:** Regulatory answers are effective-date-aware, source-authoritative, and distinguish current rules from historical ones.

1. **G12-T01 — Inventory governing regulatory documents and jurisdiction scopes.** Acceptance: Each source has issuer, class, effective date and trust tier.
2. **G12-T02 — Define regulatory source precedence and supersession policy.** Acceptance: Circular/amendment relationship is deterministic and reviewed.
3. **G12-T03 — Attach original source hashes and exact clause/page locators.** Acceptance: All compliance evidence resolves to immutable document version.
4. **G12-T04 — Distinguish issue date, effective date, end date and retrieval date.** Acceptance: Historical queries select correct rule version.
5. **G12-T05 — Review existing SEBI domain taxonomy and alias coverage.** Acceptance: Unknown/risky classification is explicit rather than guessed.
6. **G12-T06 — Map signed regulatory rules to affected financial metrics.** Acceptance: Change-impact report lists queries and derived facts affected.
7. **G12-T07 — Validate source permissions/licensing and retention policy.** Acceptance: Only permitted documents enter published corpus.
8. **G12-T08 — Review proposed supersession edges before activation.** Acceptance: Unverified AI-discovered edges cannot hide authoritative sources.
9. **G12-T09 — Separate regulatory advice from factual lookup in answer schema.** Acceptance: High-impact interpretation labeled and appropriately reviewed.
10. **G12-T10 — Add staleness monitor and authoritative refresh workflow.** Acceptance: Source-age threshold triggers review not silent answer override.
11. **G12-T11 — Create multi-region rule boundaries rather than mixing jurisdictions.** Acceptance: SEBI, SEC and ESMA facts cannot cross without explicit query.
12. **G12-T12 — Record reasons for rejected/stale rules and document conflicts.** Acceptance: Audit supports regulator-facing reconstruction.
13. **G12-T13 — Build 30 temporal/supersession/mixed-data gold cases.** Acceptance: No obsolete obligation presented as current in critical cohort.
14. **G12-T14 — Require compliance owner signoff for rule updates.** Acceptance: Published rule registry contains approver and activation receipt.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G13 — Independent benchmark, assurance harness and fail-closed gates

**Priority:** P0  
**Depends on:** G01, G03, G05, G07, G10  
**Code areas:** `backend/app/evaluation, backend/scripts/run_phase5_evaluation_benchmark.py, backend/tests, assurance/`  
**Goal acceptance:** Measured release verdict from live execution, independent gold and negative tests; no simulated success claim.

1. **G13-T01 — Stop labeling simulated 25-case benchmark as live production proof.** Acceptance: Report names methodology and cannot grant release PASS.
2. **G13-T02 — Replace heuristic context length recall with evidence-grounded retrieval metrics.** Acceptance: Recall@k uses annotated relevant row IDs/doc clauses.
3. **G13-T03 — Freeze 200-case finance gold with separate holdout split.** Acceptance: Labels independent of generated context/answer and reviewed.
4. **G13-T04 — Freeze 50-case PDF/TXT controls.** Acceptance: Any material regression blocks CSV fix release.
5. **G13-T05 — Add 40 AMC→Feedback→Repair end-to-end scenarios.** Acceptance: Includes false feedback, concurrency, recovery and rollback.
6. **G13-T06 — Implement deterministic financial exact-match scorer.** Acceptance: Comparison uses canonical values, dates, units, filters and tolerances.
7. **G13-T07 — Implement claim-level citation support scorer.** Acceptance: Unsupported claim and citation-laundering cases fail.
8. **G13-T08 — Implement secure authorization negative-test inventory.** Acceptance: Every sensitive route and tenant path covered.
9. **G13-T09 — Separate offline unit, mocked, integration and live benchmark labels.** Acceptance: Dashboards never collapse methodologies.
10. **G13-T10 — Capture precise observed timings, token usage and provider costs.** Acceptance: No static or fabricated trace metrics in reports.
11. **G13-T11 — Support regression by commit, dataset version and model ID.** Acceptance: Reports reproducible and diffs traceable.
12. **G13-T12 — Run chaos and fault injection against persistence/publish pipeline.** Acceptance: Any missing receipt prevents release PASS.
13. **G13-T13 — Emit signed machine-readable PASS/REVIEW/BLOCK gate result.** Acceptance: Gate includes failing cases and source-run hashes.
14. **G13-T14 — Validate harness itself with intentionally incorrect answers.** Acceptance: Known-bad answers must be detected before gate trusted.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.

## G14 — CI/CD, deployment reproducibility, operations and sustainable scaling

**Priority:** P1  
**Depends on:** G02, G04, G08, G11, G13  
**Code areas:** `.github/workflows, docker-compose.yml, backend/app/main.py, backend/app/monitoring, frontend, docs`  
**Goal acceptance:** Fresh-checkout deployment, bounded runtime, measured SLOs, safe rollouts and maintainable delivery.

1. **G14-T01 — Fix missing Dockerfiles/Streamlit references in Compose.** Acceptance: docker compose config and clean image build succeed.
2. **G14-T02 — Provide supported local dev stack with seed and fake secrets.** Acceptance: New developer can run independent smoke suite.
3. **G14-T03 — Implement CI build/lint/typecheck/security/license/SBOM jobs.** Acceptance: No critical finding silently bypassed.
4. **G14-T04 — Run unit, contract, integration and holdout E2E CI stages.** Acceptance: Release failures block merge and deployment.
5. **G14-T05 — Pin dependency versions, model IDs and runtime matrix.** Acceptance: Build manifest reproducible across test and prod.
6. **G14-T06 — Add migration governance with forward/backward and backup drill.** Acceptance: Schema upgrade failure safely rolls back.
7. **G14-T07 — Gate startup readiness on essential data plane health.** Acceptance: API not ready when FAISS/SQL/Neo4j mandatory dependency unusable.
8. **G14-T08 — Make schedulers single-leader and jobs idempotent.** Acceptance: Multiworker load test shows no duplicate mutation.
9. **G14-T09 — Instrument measured p50/p95/p99, error, cache and correctness SLO.** Acceptance: Dashboard uses real request spans and evaluation labels.
10. **G14-T10 — Profile vector lexical scan and memory at growing corpus sizes.** Acceptance: Benchmarked scale threshold and upgrade decision recorded.
11. **G14-T11 — Test load/concurrency/failover at representative AMC workloads.** Acceptance: Target SLO defined and evidence reported.
12. **G14-T12 — Deploy shadow→canary→full with automatic rollback trigger.** Acceptance: Comparative quality, access and latency gates attached.
13. **G14-T13 — Document operational runbooks, incident severity and restore steps.** Acceptance: Operators can reproduce source and repair rollback.
14. **G14-T14 — Conduct final architecture and security re-audit against exact release.** Acceptance: Critical findings closed, residual risks accepted and signed.

**Goal gate:** All 14 tasks have test commands, logs, code references, and an approved risk/rollback note. No task is marked DONE solely on code existence.
