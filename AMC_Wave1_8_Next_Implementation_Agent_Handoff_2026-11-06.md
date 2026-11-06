# AMC Context Engineering POC — Wave 1.8 Implementation Handoff

**Document type:** CTO-grade source audit, implementation specification, adversarial assurance plan, and local Codex execution prompt  
**Prepared:** 6 November 2026  
**Repository:** [`nusummit-spg/amc-context-engineering-poc`](https://github.com/nusummit-spg/amc-context-engineering-poc)  
**Branch:** [`amc-dev`](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/amc-dev)  
**Pinned audited HEAD:** [`763c1ec9e57517d97d6880ea79ff9c2ce5c42d36`](https://github.com/nusummit-spg/amc-context-engineering-poc/commit/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36)  
**Comparison baseline (Wave 1.7):** `bea1fbd4e52fdc93fa064c47ed1377347d3852f7`  
**Observed change:** 1 new commit, 11 changed files.  
**Release recommendation:** **BLOCK**. Schema additions and code-level containment are not equivalent to an executable, crash-safe publication pipeline.

> **Execution instruction:** Work from the pinned HEAD above, first verify the branch has not advanced, and produce reviewable commits. **Do not claim DONE, VERIFIED, PASS, or RELEASE READY without tests against the code path and persistence layer specified in each acceptance criterion.** If the branch has moved, rebase the implementation plan on the new HEAD and capture the difference.

---

## 1. Executive assessment and what actually changed

### 1.1 New, source-confirmed work

| Area | Source evidence | Assessment |
|---|---|---|
| CI secret scanning | `.github/workflows/amc-assurance.yml` now references `gitleaks/gitleaks-action@v8.22.0` | **Attempted fix, but new CI run fails in setup: unresolved action version** |
| Compile/test job discovery | CI uses `compileall` and conditional test directories | **Implemented, not sufficient**: some missing directories and failed tests can be skipped/masked |
| Governance API normalization | `backend/app/api/routes/governance.py` changes | **Partial**: wrong `get_patch` call fixed in public promote handler, but related helper still uses it; synthetic `ACTIVE` receipt remains |
| Persistent effect schema | `backend/alembic/versions/010_b07_publication_effects.py` | **Schema added, not runtime-verified** |
| FAISS active-version schema | `backend/alembic/versions/011_b08_active_versions.py` | **Schema added, no atomic generation switch demonstrated** |
| Exact-ID vector deletion API | `backend/app/vector/client.py::delete_by_chunk_id` | **Partial, with index/payload divergence bug** |
| Vector preimage | `backend/app/services/vector_staging_service.py::_capture_preimage` | **Still not exact-ID**: uses a semantic similarity search on the string `chunk_id:...` |
| Remediation evidence | `remediation/wave1_7/{00_SOURCE_BASELINE.md,01_FINDINGS_AND_ROOT_CAUSES.md,02_TASK_MATRIX.csv,04_SCHEMA_MIGRATION_EVIDENCE.md}` | Useful audit scaffolding; many tasks correctly labeled `IMPLEMENTED_UNVERIFIED` or `BLOCKED` |

### 1.2 CI evidence — real result, not a prediction

GitHub Actions run [`42209601755`](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42209601755), on the pinned HEAD, concluded **failure**. The first job failed in **Set up job** with:

```text
Unable to resolve action `gitleaks/gitleaks-action@v8.22.0`, unable to find version `v8.22.0`
```

All subsequent jobs were **skipped**. The earlier run `42202423962` failed because `pip install gitleaks` could not find a Python distribution. Thus the `amc-dev` trigger works, but end-to-end CI has never been demonstrated green in this audit. Do not suppress scanner failures; choose a verified published action revision or install the official scanner executable from a pinned checksum-verified release.

### 1.3 Highest-risk newly confirmed defects

**W18-01 — Fake verified activation (P0):** `governance.py::promote_patch_direct` executes graph handling, then constructs `{"type":"patch_activation","verified":True,...}` and calls `activate_patch` **even though vector activation is commented out / deferred**. The route can say `promoted` without a proven vector generation. **Change to 202 Accepted / publication intent only, or return a fail-closed non-success until the worker verifies every required effect.**

**W18-02 — Broken internal graph lookup (P0):** In the same module, `_execute_graph_mutation_with_verification` still executes `await patch_layer.get_patch(patch_id)`; the local correction layer exposes `get_patch_by_id` and not `get_patch`. The public handler's fix does not repair the helper. The graph mutation itself is also outside the proposed durable outbox execution path.

**W18-03 — FAISS deletion is inconsistent (P0):** `VectorStore.delete_by_chunk_id` deletes an entry from `self._payloads` and persists it, but **never removes the matching ID from `self._index`**. `count()` reports `index.ntotal`, which can then disagree with `len(payloads)`; stale search IDs can persist. The staging service also has its own private index manipulation. Replace with a single tested exact-ID store API, and ideally immutable generation rebuild/pointer flip rather than destructive live mutation.

**W18-04 — Preimage not exact (P0):** `VectorStagingService._capture_preimage` calls `similarity_search(query='chunk_id:"..."', limit=1)`. `VectorStore.similarity_search` embeds the supplied text and runs nearest-neighbor search, so **it does not guarantee an exact `chunk_id` match**. A wrong document can be captured and later restored. A missing snapshot must be distinguishable from a genuine absent document and from an I/O failure.

**W18-05 — Outbox still has two execution paths (P0):** `PromotionService.apply_approved_proposals` writes an outbox event and immediately invokes graph mutation or `_trigger_reindex`; the outbox worker also processes events. `_execute_graph_mutation` and `_execute_state_transition` in `OutboxProcessor` still raise `NotImplementedError`, and vector reindex can produce a fabricated verified receipt. Implement **one authoritative asynchronous worker** with durable effects; no direct canonical write in request handling.

**W18-06 — Process-memory staging and rollback (P0):** `VectorStagingService` and `GraphPostconditionsService` use `_staging`/`_preimages` dictionaries. `apply_staged()` clears staged records even after partial failures; `rollback_staged()` works only on surviving in-memory staged operations, not immutable *applied* receipts. Service restart loses recoverability.

**W18-07 — Insufficient CAS and state constraints (P0):** `010`/`011` migrations add string fencing-token columns but no observed lease protocol, monotonic generation comparison, uniqueness for one ACTIVE `(tenant, namespace)`, idempotency uniqueness, or DB constraints binding effects to intents. Schema presence does not prove correctness. The ORM and migrations also require compatibility verification against actual PostgreSQL.

**W18-08 — Graph effects require real postcondition proofs (P0):** Graph service now attempts `_execute_cypher` for deletions rather than logging *only*, but interpolates graph labels/relationship types into Cypher and returns success without readback. `_update_node_or_edge` can report success after delete/create without verifying the stored postcondition. Use validated allowlisted identifiers, parameterized values, scoped tenant/entity match, and exact readback.

**W18-09 — Governance serving authorization (P0):** `CorrectionPatchLayer.apply_patches_to_context` and `get_active_patches` still use `patch.approved`, not an authoritative `ACTIVE + verified receipt + active version + tenant + not revoked` predicate. Existing fast-path code also checks `approved` on patch dictionaries. These are potential publication bypasses until all retrieval paths are rewired.

**W18-10 — Assurance does not fail closed (P0):** CI's missing regression folder becomes a skip, its fault-test fallback appends `|| exit 0`, SLO checks are echo placeholders, and canary reports a skip without a real deployment. A truly required gate must be executable and fail when absent or inconclusive; unsupported canary should be marked `NOT_RUN` and prohibit release, not emit a misleading success.

### 1.4 Scope control

Wave 1.8 **does not** attempt to rebuild every historical AMC feature. Complete the *publication integrity vertical slice* first. Keep unapproved AAUM aggregation blocked, do not restore or delete the Feedback microservice without a product-owner decision, and defer cosmetic/Admin enhancements. Prior financial and UI recommendations remain tracked, not certified complete.

---

## 2. Non-negotiable architecture and contracts

### 2.1 One publication write authority

```text
Authenticated API / Human Review
   -> validate tenant, proposer != approver, revision, source evidence
   -> PostgreSQL TRANSACTION:
        immutable approval proof
        publication_intent (PENDING)
        publication_effect records (STAGED)
        outbox event with unique idempotency key
      COMMIT
   -> return 202 + intent_id (NEVER ACTIVE)

Leased Publication Worker (the ONLY external writer)
   -> claim outbox/intent via transaction + monotonic fencing token
   -> load durable staged effects and preimages
   -> graph change with CAS/preimage + exact readback
   -> build isolated FAISS generation + verify count/ID membership/checksum/probes
   -> durably persist receipts, snapshots and worker progress
   -> atomically CAS active generation pointer and guarded state to ACTIVE
   -> mark outbox completed after all required proofs
   -> expose only ACTIVE + valid, tenant-matching authoritative evidence

Crash / expiry / duplicate
   -> recover existing intent + effect state from PostgreSQL
   -> reconcile observed graph/index postconditions before deciding replay
   -> retry idempotently or mark CONFLICTED/FAILED/DEAD_LETTER
   -> rollback only with persisted preimages + postimage compare-and-swap
```

**Important:** PostgreSQL, Neo4j and FAISS do not share an ACID transaction. Implement a **durable saga with verified steps and compensation**, not claims of global atomicity. No code path may mark `ACTIVE`, `PUBLISHED`, `RESOLVED`, `VERIFIED`, or `COMPLETED` from a fabricated receipt, a nonzero staging count, or the mere presence of an indexer.

### 2.2 Durable record contracts

Use existing migrations `009`, `010`, `011` as a starting point; modify by **additive follow-up migrations** if any database has applied these revisions. Do not rewrite already-deployed migrations in place.

**`publication_intents`:** `intent_id`, `tenant_id`, `proposal_id`, `approved_revision`, `source_version/hash`, immutable actor/evidence reference, scope, expected effect count, state, created/updated timestamps, idempotency key, policy version. Unique `(tenant, proposal, approved_revision, source_version, publication_scope)` or explicit canonical idempotency digest.

**`publication_effects`:** `effect_id`, `intent_id` FK, tenant, ordinal, effect type/target, immutable desired payload digest, preimage snapshot/hash, expected pre-version, expected postimage, observed postimage/hash, status, fencing epoch, lease reference, attempts, verified timestamp, error. Unique `(intent_id, ordinal)` and `(intent_id, effect_kind, logical_target, revision)` as appropriate. Large FAISS snapshots may live on persistent volume/object store behind content-addressed immutable references; DB holds hashes and locations.

**`active_versions`:** separate immutable *generations* from one authoritative *active pointer*. Enforce exactly one active generation **at most** for each `(tenant, namespace)` via a unique active-pointer row or partial unique index, plus monotonically increasing pointer version; carry generation hash, document count, embedding model/dimension, source and tenant. Forbid cross-tenant and cross-namespace pointer switches.

**`outbox_events`:** `idempotency_key` unique, `lease_owner`, `lease_expires_at`, `fencing_epoch` monotonic (integer), `next_attempt_at`, `attempts`, max attempts, last result/error, dead-letter status and timestamps. Claims should use safe row locking (`FOR UPDATE SKIP LOCKED` in PostgreSQL) or equivalent CAS; do not hold a DB transaction open over long Neo4j/FAISS calls.

**Receipt:** immutable effect list with observed postconditions, pre/post hashes, graph revision, active FAISS generation ID, active-pointer CAS outcome, worker fencing epoch, actor, tenant, source version, timestamps, canonical evidence digest. A receipt is *evidence*, not self-declared verification.

### 2.3 State invariants

1. `PENDING -> APPROVED` changes **only** approval state; it cannot mutate canonical graph or FAISS.
2. `APPROVED -> STAGED` requires a durable intent/effect/outbox transaction.
3. `STAGED -> VERIFIED` requires all mandatory effects to have exact readback and persisted receipts.
4. `VERIFIED -> ACTIVE` requires successful active-version pointer CAS and no superseding approval/revocation.
5. Failed/partial effects must remain **non-serving**. Rollback/compensation is separately observable.
6. A retry must never produce duplicate graph relationships, duplicate FAISS chunks, double activation or duplicate Feedback resolution.
7. Concurrent conflicting updates cannot both become ACTIVE; stale workers lose their fenced authority.
8. Source identity, tenant and approval revision are fixed at approval time and re-validated at publish time.

---

## 3. Execution batches — 32 actionable tasks

### Batch R0 — Immediate integrity containment and trustworthy CI (7 tasks, P0)

**R0-01 — CI action resolution.** Replace `gitleaks/gitleaks-action@v8.22.0` with a **verified existing** official release/tag or full commit SHA (or checksum-pinned scanner binary). Validate from GitHub before committing; retain actual secret-detection failure. No `pip install gitleaks` substitution. **Pass:** first CI job installs the scanner and runs successfully or fails on a *real* detection.

**R0-02 — Required test jobs must never silently pass.** Remove `|| exit 0` and success-on-missing-directory behavior. Install the test dependencies in each isolated GitHub Actions job. Target existing `backend/tests/test_wave15_publication_fault_injection.py` while replacing tautologies. Ensure `pytest --collect-only` finds nonzero tests. **Pass:** deliberately failing test fails CI; absent mandatory tests fail CI.

**R0-03 — Disable synthetic patch activation.** Remove unconditional `{"verified": true}` from `/governance/promote/{patch_id}`. Until the worker exists, submit durable intent (202) or return an explicit blocked error with no state mutation. Correct `_execute_graph_mutation_with_verification` call to supported lookup or retire helper when worker takes over. **Pass:** no graph/vector effect -> no ACTIVE state; no fake receipt.

**R0-04 — Seal every answer path.** Create one shared, version-aware `is_serving_eligible(patch, authoritative_receipts, active_pointer, tenant)` and use it in fast path, local fallback, overlay, stream, cached response, graph retrieval, microservice adapters. Do **not** trust request-supplied `can_serve` or `approved` booleans. **Pass:** PENDING/APPROVED/STAGED/VERIFIED/ROLLED_BACK/revoked/cross-tenant patches are absent from every response path.

**R0-05 — Stop dual execution now.** Change `PromotionService` and governance APIs to create intents and outbox records only; disable direct external calls. Keep a feature flag default OFF for *publication* until verified worker is deployed, never default ON. **Pass:** approving/submitting a promotion results in exactly one durable event, zero canonical writes by the request handler.

**R0-06 — Vector deletion consistency containment.** Fix `VectorStore.delete_by_chunk_id` so payload and underlying FAISS IndexIDMap2 delete the same `int64` ID under the store lock, check the removal count and readback, and persist safely; ensure `count == payload cardinality`. But do not use mutable live-index operations for rollout after generations ship. **Pass:** add/search/delete/restart shows no stale FAISS hit and counts match.

**R0-07 — Evidence reconciliation.** Update `remediation/wave1_7/02_TASK_MATRIX.csv` and create `remediation/wave1_8/STATUS.md`: statuses only `NOT_STARTED`, `IMPLEMENTED_UNVERIFIED`, `VERIFIED`, `BLOCKED`, `NOT_RUN`, `FAILED`. Distinguish `011 schema exists` from `FAISS generation ready`. **Pass:** each VERIFIED task references real CI URL, test name and data evidence.

### Batch D1 — Durable journal, leases and CAS foundation (7 tasks, P0)

**D1-01 — Check migration history and add constraints.** Validate 009→010→011 on disposable PostgreSQL; ensure ORM mappings match. Add new migration(s) for missing FK/uniqueness/idempotency/lease/pointer constraints and transaction timestamps without rewriting applied revisions. **Pass:** fresh upgrade, downgrade where supported, re-upgrade, and filled-data upgrade preserve evidence.

**D1-02 — Durable publication repository.** Create `PublicationRepository` using SQLAlchemy with `create_intent_and_outbox`, `record_preimage`, `record_effect_observation`, `verify_effect`, `transition_intent`, `claim_work`, `release_work` and `record_compensation`. All methods tenant-scoped, testable and transactional. **Pass:** records survive service restart and are reconstructible by intent ID.

**D1-03 — Idempotent request envelope.** Build deterministic idempotency key from tenant + proposal + approved revision + source version + effect specification digest. Enforce DB uniqueness; repeated HTTP request returns existing intent. **Pass:** 100 duplicate submissions create one intent and one logical event.

**D1-04 — Fenced worker claims.** Implement PostgreSQL-backed claims with `SKIP LOCKED`, short lease, incrementing `fencing_epoch`, heartbeat and expiry; record claims before external effects. Stale epochs fail CAS. **Pass:** two workers race; at most one current owner; old owner cannot flip active pointer.

**D1-05 — Durable preimage semantics.** Distinguish `PRESENT(snapshot)`, `ABSENT`, and `LOOKUP_ERROR`; never return `None` on a graph/vector outage and treat it as absent. Record tenant, target ID, original version/hash and acquisition proof. **Pass:** injected lookup errors block publication; exact preimage survives crash.

**D1-06 — Immutable generation storage.** Store candidate FAISS index and payload manifest in a versioned, tenant-isolated durable directory/object store; fsync/checksum and atomic rename/publish. Define reader behavior on generation change and restart; maintain prior generations for rollback. **Pass:** crash/reload finds prior active generation and detects tampered candidate files.

**D1-07 — Durable active pointer.** Introduce one database-authoritative active-pointer row keyed by `(tenant, namespace)` with CAS expected version + fencing epoch. Readers resolve from pointer (not arbitrary directory mtime). **Pass:** stale pointer update fails; one active generation per key.

### Batch D2 — Real external effects and publication (8 tasks, P0)

**D2-01 — Exact vector lookup.** Implement `get_by_chunk_id(chunk_id, tenant_id, generation_id)` using payload metadata/ID map, NOT semantic search. Guarantee zero-or-one or explicit ambiguity error, plus exact FAISS `int64` ID. **Pass:** near-similar texts do not cause wrong preimage capture.

**D2-02 — Generation builder.** Apply durable adds/deletes against an isolated copy of the active FAISS generation; preserve embedding model/dimension and stable IDs; recalculate exact count and every requested ID. **Pass:** staged changes do not appear in live searches before activation.

**D2-03 — Vector verification and switch.** Reload the built FAISS generation from durable storage; verify index count, payload cardinality, content hashes, exact membership/deletion, tenant scope and deterministically selected probe queries; only then CAS active pointer. **Pass:** missing vector, checksum mismatch, wrong model or wrong count blocks ACTIVE.

**D2-04 — Parameterized Neo4j graph write.** Replace interpolation of unsanitized label/relationship/property names. Use strict schema allowlists for identifiers, bound parameter values, explicit tenant and entity constraints, expected graph revision/preimage conditions. **Pass:** injected identifiers rejected; wrong tenant/old revision produces `CONFLICTED`.

**D2-05 — Graph postcondition.** Execute mutation, then read back **exact** node/edge identity, property values and revision; persist observed postimage and a hash-matched receipt. Treat 0 matched or >1 ambiguous nodes as failure. **Pass:** no-op or wrong readback never VERIFIED.

**D2-06 — One authoritative orchestration worker.** Replace `NotImplementedError` handlers with implementations that call `PublicationRepository`, `GraphEffectExecutor`, `VectorGenerationManager` and CAS activation. Do not call old direct execution routes. **Pass:** one intent drives all effects, and completion is recorded only after verified readback.

**D2-07 — Durable compensation / rollback.** On partial application, use persisted preimages and observed postimages to safely compensate graph mutations; revert active pointer to verified prior vector generation with CAS; reject rollback over intervening third-party updates. **Pass:** rollback after process restart; conflicts never overwrite newer truth.

**D2-08 — Terminal state and evidence.** Enforce committed `PUBLISHED` / `ACTIVE` only when all required effect receipts and active-pointer proof exist. `FAILED`/`CONFLICTED`/`DEAD_LETTER` require non-serving finality and reason codes; support operator-reviewed requeue. **Pass:** missing any receipt, mismatched source or revoked approval is a hard block.

### Batch Q — Feedback, user experience, financial guardrails and operations (5 tasks)

**Q-01 — Feedback causality.** `FeedbackOutcomeService` must query real `PublicationIntent` and `PublicationReceipt` records by tenant/issue/intent/receipt; do not inspect `_staging` counts. Mark issue RESOLVED only if matching ACTIVE, verified, nonrevoked publication and persisted source evidence. Rollback reopens affected issues. **P0.**

**Q-02 — Operational telemetry.** Replace process-memory lists with durable audit events and Prometheus counters/histograms; use tenant-safe labels, protect against high cardinality, and record lease/retry/verification/activation/rollback/latency/cost. **P1.**

**Q-03 — Financial containment.** Preserve `aaum_crore` unapproved policy and block any SQL/LLM/Pandas fallback that fabricates AAUM amounts, including mismatched AMC ranking/COUNT semantics; use exact Decimal math and canonical scheme identity. **P0.**

**Q-04 — Data integrity/provenance.** Recompute SHA-256 from actual CSV bytes and chunk bytes; quarantine mismatches. Do not truncate contributor evidence at 50 without exposing a complete paginated/hash-linked provenance ledger. Test NAV date/value pairing and source row identity. **P0.**

**Q-05 — Feedback package disposition.** The previous `packages/amc-feedback-loop` source was removed. Record explicit maintainer decision: restore on compatible branch (preferred interim), replace with proven feature parity, or deprecate with signed customer/API impact. Do not silently treat partial backend modules as equivalent. **P0 decision gate.**

### Batch A — Executable assurance and controlled release (5 tasks)

**A-01 — CI repaired and matrix executed.** Make `amc-dev` push and PR jobs run unit, integration, migration, security and adversarial suites. Only use existing pinned action references; no echo-only success and no `|| exit 0` on critical test failures. Upload JUnit/artifacts. **P0.**

**A-02 — Disposable external services.** Use CI containers for PostgreSQL/Neo4j, a temporary FAISS directory and deterministic embedding fixture. Never require production secrets for test suite. Verify migrations and integration tests on clean database. **P0.**

**A-03 — Failure injection.** Test crash after DB commit, graph write before receipt, vector build before pointer CAS, pointer switch before ack, expired lease, stale worker, duplicate event, wrong readback, partial rollback and tenant crossover. All assertions must observe *real state*. **P0.**

**A-04 — Release evidence.** Store pinned SHA, executable command, test counts, JUnit XML, migration receipt, durable-state digest, fault scenarios, SLO-window results, canary/rollback rehearsal and signed gate decision under `remediation/wave1_8/evidence/`. **P0.**

**A-05 — Canary hard gate.** A canary job that only prints 'skipping' is not a passed deployment. If no environment exists, set `CANARY=NOT_RUN`, release remains BLOCK. For eventual rollout use read-only/shadow first, then low-risk tenant with guarded rollback and human review. **P0.**

**Total: 32 tasks across R0 (7), D1 (7), D2 (8), Q (5), A (5).** For execution efficiency, R0 and D1 can run as one bulk cycle with individually reviewable commits; D2 depends on D1. Q and A can progress in parallel, subject to no bypass of the P0 gates.

---

## 4. File-by-file changes and expected owner

| Path | Required action |
|---|---|
| `.github/workflows/amc-assurance.yml` | Verified scanner ref, dependencies per job, no silent skips, actionable gates |
| `backend/alembic/versions/009_b06_publication_intents_receipts.py` | Validate existing revision, **do not overwrite if applied** |
| `backend/alembic/versions/010_b07_publication_effects.py` | Validate DDL, follow-up migration for IDs/FKs/constraints |
| `backend/alembic/versions/011_b08_active_versions.py` | Validate DDL, follow-up migration for unique active pointer |
| `backend/app/schemas/publication_intents_table.py` | ORM compatibility, immutable receipt and pointer relationships |
| `backend/app/schemas/outbox_events_table.py` | Lease/fencing/idempotency schema and state machine |
| `backend/app/services/outbox_processor.py` | Sole leased, idempotent effect executor, stale-worker protection |
| `backend/app/services/promotion_service.py` | Remove direct canonical mutations; only durable enqueue and status observation |
| `backend/app/services/vector_staging_service.py` | Replace `_staging` and `_preimages` as source of truth with durable repository |
| `backend/app/vector/client.py` | Correct FAISS `remove_ids`, exact-ID lookup, generation APIs, checksum, atomic persistence |
| `backend/app/services/graph_postconditions_service.py` | Tenant-safe graph CAS + exact readback and persisted effect receipts |
| `backend/app/api/routes/governance.py` | Disable fake `ACTIVE`, remove broken helper, 202 async intent request |
| `backend/app/graph/correction_patch_layer.py` | One transition API; remove shadow approval-based serving and duplicate method alias |
| `backend/app/retrieval/fast_path_interceptor.py` | Authoritative `can_serve` check and version-aware retrieval |
| `backend/app/retrieval/orchestrator.py` | Gate all overlays, fallback and streaming on persisted verified ACTIVE |
| `backend/app/services/feedback_outcome_service.py` | Real DB-backed publication/receipt + issue causality |
| `backend/app/services/financial_policy_service.py` | Preserve AAUM block, exact manifest recomputation |
| `backend/app/tabular/planner.py` + `executor.py` | No financial fallback, correct COUNT vs AAUM semantics, full contributor ledger |
| `backend/tests/test_wave15_publication_fault_injection.py` | Replace tautologies and self-assigned mock outcomes with real assertions |

Follow established project structure; do not create an entirely new microservice unless a real isolation requirement is demonstrated. Prefer additive interfaces with a single ownership boundary.

---

## 5. Mandatory adversarial test matrix (48 tests)

**CI / schema (1–8):**

1. CI checkout resolves every referenced action release/SHA.
2. Scanner finds seeded dummy secret and fails pipeline.
3. Scanner passes clean fixture.
4. Deliberately failing unit test fails required CI job.
5. Missing mandatory test target fails the build rather than skipping.
6. Fresh 009→010→011→latest migration upgrade and required constraints verified.
7. Compatible downgrade/re-upgrade preserves migration validity; explicit data-loss risks documented.
8. Existing dataset migration retains rows and old approval/evidence metadata.

**Governance and versioning (9–16):**

9. Proposal creator cannot approve their own patch or proposal.
10. Approval is a durable PENDING→APPROVED transition only; graph and FAISS remain unchanged.
11. Promotion submission returns durable intent and `202`, not synthetic ACTIVE.
12. Proposed patch cannot serve without verified receipt even with `approved=True`.
13. Wrong tenant/user cannot see another tenant's patch or version.
14. Revoked/superseded receipt is rejected by every fast/slow/stream/cache path.
15. Two concurrent approvals of same revision generate only one intent/event.
16. Altered source version after approval fails publication CAS.

**Vector exactness and durability (17–26):**

17. Similar-text chunk IDs resolve their exact preimages, not nearest neighbor.
18. Missing chunk is ABSENT; vector outage is LOOKUP_ERROR; never conflated.
19. Exact delete removes both FAISS `int64` ID and payload, including after restart.
20. Staged candidate is invisible to live retrieval until active pointer flip.
21. Rebuilt generation has matching document count, exact IDs and SHA-256 content digest.
22. Corrupted candidate index/payload checksum fails verification.
23. Unexpected embedding dimension/model fails generation activation.
24. Crash after generation write but before pointer CAS leaves old generation active.
25. Crash after pointer CAS but before outbox ack recovers exactly once.
26. Rollback after restart returns previous verified generation, no stale chunk.

**Graph and compensation (27–35):**

27. Parameterized property values cannot alter graph query syntax.
28. Disallowed graph labels, relationships or attribute identifiers fail validation.
29. Wrong tenant/entity/version cannot mutate target graph.
30. Graph no-match or multiple-match results fail expected-postcondition verification.
31. Wrong graph readback produces no VERIFIED receipt.
32. Graph outage after intent creation is recoverable from durable journal.
33. Crash after graph commit before receipt reconciles via readback; no double write.
34. Graph rollback after restart restores preimage if current postimage matches.
35. Rollback on third-party intervening update returns CONFLICTED, does not overwrite.

**Workers / saga (36–42):**

36. Two workers race: only one valid fenced lease owns an intent.
37. Expired worker's old fencing epoch cannot commit receipt or active pointer.
38. Duplicate event delivery produces exactly one logical external effect.
39. Failed handler retries with bounded exponential backoff, then dead-letter evidence.
40. Partial graph success + vector failure cannot activate or resolve Feedback.
41. No publication receipt until *all* required effects have verified readbacks.
42. Reconciliation works after full worker/process restart with zero in-memory staging.

**Feedback / financial / release (43–48):**

43. Feedback issue stays open when intent/receipt missing, mismatched tenant or non-ACTIVE.
44. Published issue becomes NEEDS_REVIEW after rollback with retained causality.
45. AAUM SUM/AVG/RANK are blocked without steward approval in every route/fallback.
46. Corrupt CSV byte stream or chunk hash causes quarantine despite syntactically valid manifest.
47. Citation/provenance paging returns all contributing row IDs with verifiable digest.
48. Release decision remains BLOCK when CI red, test skipped, missing SLO, or no canary evidence.

**Assertion policy:** Forbid `assert True`, `assert x is True or x is False`, self-assigned mock outcomes, mere in-memory counts, status strings returned by test doubles, and mocks of the entire component under test. Mocks may isolate only external dependencies where independently verified integration tests exercise the real boundary.

---

## 6. Reference test fixtures and execution commands

**Minimal fixture:** one tenant `t_alpha`, another `t_beta`; 3 graph entities, 2 approved candidate corrections, 1 obsolete correction, 7 vector chunks including near-identical text and same-prefix IDs; one Feedback issue linked to the proposed correction; fixed deterministic embeddings and immutable source hashes.

**PostgreSQL:** start isolated disposable DB (Docker service or container), set `DATABASE_URL` only to that DB, run Alembic upgrade to latest and schema SQL probes. Do not run a downgrade against any real dataset.

**Neo4j:** disposable server with tenant-scoped seeded nodes/edges; verify transaction commit and readback. Production graph must never be touched by tests.

**FAISS:** temporary durable directory with two generations and independently computed payload/index digests; run add/delete/build/switch/crash/reload/rollback in separate processes to expose loss of memory-state assumptions.

Suggested commands, **to be adapted to actual repository dependencies and only marked PASS after execution**:

```bash
# From a clean clone, pinned at the audited HEAD
python -m compileall -q backend/app backend/tests
cd backend
python -m pytest --collect-only -q tests/
python -m pytest -q tests/test_wave14_p0_containment.py \
  tests/test_wave15_publication_fault_injection.py

# Once new suites exist (do not silently skip missing files):
python -m pytest -q tests/test_wave18_governance_and_cas.py
python -m pytest -q tests/test_wave18_vector_generations.py
python -m pytest -q tests/test_wave18_graph_effects.py
python -m pytest -q tests/test_wave18_outbox_recovery.py
python -m pytest -q tests/test_wave18_feedback_and_policy.py

# Fresh disposable PostgreSQL (database URL must be confirmed disposable)
alembic current
alembic heads
alembic upgrade head
```

**CI minimum:** `compile`, `test discovery`, `unit`, `database migration`, `graph/vector integration`, `fault injection`, `security`, `release decision`; separate green quality check from environment-dependent staging canary and never turn unexecuted canary into RELEASE READY.

---

## 7. Implementation order and limited-resource strategy

| Cycle | Bulk tasks | Required evidence | Gate |
|---|---|---|---|
| 1 | R0-01…07 + D1-01…03 | CI scanner resolves; no fake ACTIVE; deduplicated durable intent | No production activation |
| 2 | D1-04…07 + D2-01…03 | Fenced claims; immutable FAISS generations; exact-ID proofs | Real vector durability |
| 3 | D2-04…08 + Q-01 | Verified graph + vector publication; durable outbox + restart rollback; Feedback DB causality | One publication path |
| 4 | Q-02…05 + A-01…05 | Source provenance, monitoring, CI, migration and release evidence | Independent release decision |

**Resource choices:** PostgreSQL + SQLAlchemy/Alembic as coordination store, Neo4j existing graph adapter, local FAISS immutable generations on a persistent filesystem (or existing approved object storage), `pytest` integration tests and GitHub Actions. Avoid introducing Kafka, Kubernetes, Redis queues, Temporal or another database solely to solve a small POC's publication workflow. Redis may cache but **must not be the authoritative approval/effect journal**. A single worker process is acceptable if leases and recovery make it safe to restart; multi-worker scenarios must still be tested.

**Breakpoints and stop criteria:** At any phase, if a test cannot be run, a dependency is unavailable, a real approval is missing, or the effect semantics are ambiguous, mark `BLOCKED` and retain the existing fail-closed path. Do not add placeholder `verified=True`, `status='completed'`, `pass`, or `except: return True` branches.

---

## 8. Evidence artifacts required from Codex

Produce, in `remediation/wave1_8/`:

```text
00_SOURCE_BASELINE.md            # reviewed SHA, date, diff, root findings
01_ARCHITECTURE_AND_DECISIONS.md  # one authority; saga and generation contracts
02_TASK_MATRIX.csv                # task -> state -> changed files -> tests -> commit
03_SCHEMA_REHEARSAL.md           # DB commands, schema fingerprints, results
04_PUBLICATION_RECOVERY.md       # actual restart, readback and rollback traces
05_FINANCIAL_FEEDBACK_GATES.md   # remaining separate blockers, evidence
06_CI_AND_TEST_EVIDENCE.md       # links to real runs, exact pass/fail/skip
07_RELEASE_GATE.md               # SEC, REP, PUB, NUM, ING, E2E, OPS, decision
08_CLEAN_DIFF_AUDIT.md           # no fake success, deleted-code review
README.md                        # execution summary, residual risks
```

Store JUnit and deterministic fixture manifests as referenced evidence. Record run IDs and the HEAD SHA they exercised. If there is no clean green CI at the final commit, **release gate = BLOCK**. Do not call syntax compilation a runtime or migration verification test.

---

## 9. Final release criteria (all required)

| Gate | PASS requires | Current audited result |
|---|---|---|
| `SEC` | JWT/service authorization, tenant scoping, four-eyes, revocation and fenced ownership tested | BLOCK |
| `REP` | One patch/proposal lifecycle; no `approved`-only retrieval, no synthetic ACTIVE | BLOCK |
| `PUB` | Single outbox writer, durable effects, exact Neo4j/FAISS readback, CAS pointer and restart-safe rollback | BLOCK |
| `NUM` | AAUM steward policy consistently blocked where unapproved; Decimal/canonical grain gold tested | BLOCK |
| `ING` | Actual file-byte/chunk hash validation, reconciled source counts and immutable version activation | BLOCK |
| `E2E` | Feedback, query, streaming, citations and existing PDF/TXT behavior regressions pass | BLOCK |
| `OPS` | Resolved GitHub Action, successful migration & fault CI, SLO and canary evidence or explicit approved risk exception | BLOCK |

**Explicit verdict:** **NO-GO / BLOCK.** Even if schema migrations compile and a new CI action resolves, the publication engine cannot be considered complete until the mandatory runtime and recovery tests pass.

---

## 10. Ready-to-paste Codex execution prompt

> You are the senior implementation agent for `nusummit-spg/amc-context-engineering-poc`, branch `amc-dev`. The architectural handoff is `AMC_Wave1_8_Next_Implementation_Agent_Handoff_2026-11-06.md`. Audit HEAD versus pinned SHA `763c1ec9e57517d97d6880ea79ff9c2ce5c42d36` and update the source baseline if moved. Execute **bulk Cycles 1 and 2** without requesting micro-approvals, in separate reviewable commits; continue with Cycles 3–4 when prerequisite tests are green. The single governing rule is **no fabricated publication or verification success**. Implement a DB-backed publication-intent/effect/outbox/active-pointer saga with atomic request enqueue, leased and fenced worker claims, immutable FAISS generations, exact-ID preimages, tenant-safe Neo4j CAS mutations and readback, verified graph/vector receipts, guarded ACTIVE transitions and persisted rollback after restart. Remove direct execution from API/PromotionService. Fix the Gitleaks action reference to an actually published version, eliminate CI silent skips and tautological assertions, and verify each gate using actual fixtures. Preserve AAUM fail-closed policy and existing PDF/TXT retrieval. Do not silently restore or permanently remove Feedback components without product-owner decision. Deliver all `remediation/wave1_8/` evidence files, test output, source commit hashes, residual blockers and a truthful release decision. **No tests run = NOT_RUN; test with mocks only = IMPLEMENTED_UNVERIFIED; actual passing integration/CI evidence = VERIFIED.** Never modify production data or promote to ACTIVE until proof is present.

---

## 11. Audit source links (pinned to commit)

- [GitHub branch and pinned SHA](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36)
- [Actions run 42209601755 — failed during setup](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42209601755)
- [CI workflow](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/.github/workflows/amc-assurance.yml)
- [Wave 1.7 task matrix](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/remediation/wave1_7/02_TASK_MATRIX.csv)
- [Publication effect migration 010](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/alembic/versions/010_b07_publication_effects.py)
- [Active versions migration 011](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/alembic/versions/011_b08_active_versions.py)
- [Promotion and synthetic ACTIVE path](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/app/api/routes/governance.py)
- [Outbox worker](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/app/services/outbox_processor.py)
- [Vector client exact deletion](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/app/vector/client.py)
- [Vector staging](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/app/services/vector_staging_service.py)
- [Graph postconditions](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/app/services/graph_postconditions_service.py)
- [Promotion service direct execution](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/763c1ec9e57517d97d6880ea79ff9c2ce5c42d36/backend/app/services/promotion_service.py)

*Provenance note: this is a source-level GitHub audit plus GitHub Actions job-log verification. It is not a claim that the backend, Neo4j, PostgreSQL, FAISS, migrations or integration tests were executed by this assistant. The 48 scenarios above are proposed mandatory tests, not tests already passed.*
