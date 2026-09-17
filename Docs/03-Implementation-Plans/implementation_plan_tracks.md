# Implementation Plan: Independent Feedback Loop & Correction Engine (Tracks 3–8)

This implementation plan covers the complete delivery of **Tracks 3 through 8** as specified in `Docs/track_3_4.md`, `Docs/track_4_5.md`, `Docs/track_6_7.md`, and `Docs/track_8.md`. 
Per instruction, implementation targets the **Python/FastAPI backend** and the **React frontend (`mf-context-engine`)** exclusively — avoiding Streamlit.

---

## User Review Required

> [!IMPORTANT]
> **Redis Availability & In-Memory Fallback**:
> Track 6 (Correction Patch Layer) uses Redis for fast key-value storage with 7-day TTLs. To ensure the application remains resilient and testable in environments where a live Redis server might not be running, `CorrectionPatchLayer` will feature an automatic in-memory fallback with timer-based TTL expiration while connecting to Redis when available (`REDIS_HOST:REDIS_PORT`).
>
> **Frontend Integration Surface**:
> In `mf-context-engine`, the Governance Review Queue will be added as a dedicated view accessible from the Sidebar navigation (`06_Governance` / "Governance Review Queue") and accessible to users with Compliance / Admin roles, with side-by-side correction inspection, single/batch approval and rejection, risk badges, and direct API synchronization.

---

## Current State & Gap Analysis

| Track | Target Component | Current State | Work Required |
|---|---|---|---|
| **Track 3** | Cypher Safety Layer | Core classes exist (`safe_cypher_builder.py`, `cypher_validators.py`, `cypher_audit_log.py`). 13 tests passing. | Verify whitelist completeness for AMC domain, verify audit log rotation/retention, ensure export in graph package `__init__.py`. |
| **Track 4** | Dissatisfaction Detection | `dissatisfaction_detector.py`, `correction_extractor.py` exist. | 1 test bug in positive sentiment handling (`-0.0 > 0`). Create FastAPI endpoint `POST /api/feedback/follow-up-detection`. Enhance extractor with currency/percentage heuristics. |
| **Track 5** | Deterministic Rules (Tier 1A) | `deterministic_rules.py` and `evaluation_router.py` exist. 8 tests passing. | Implement STOP-1 evaluation workflow integration, add tests for STOP-1 gate triggering, rule evaluation router wiring. |
| **Track 6** | Correction Patch Layer | Missing. | Create `backend/app/graph/correction_patch_layer.py` with Redis + fallback, TTL enforcement, context injection (`apply_patches_to_context`), and wire into `backend/app/retrieval/orchestrator.py`. |
| **Track 7** | Governance Review Queue (API + UI) | Missing governance routes and frontend view. | Create `backend/app/api/routes/governance.py` (`/pending-corrections`, `/approve/{id}`, `/reject/{id}`, `/batch-approve`). Create `mf-context-engine/src/views/pages/GovernancePage.jsx`, wire into `Sidebar.jsx`, `App.jsx`, and `api.js`. |
| **Track 8** | NER + Entity Resolution | Missing. | Create `backend/app/feedback/ner_pipeline.py`, `backend/app/feedback/fund_name_matcher.py`, fund master dataset `backend/app/data/fund_master.json`, and connect to feedback claim extraction. |

---

## Proposed Changes

### 1. Track 3: Cypher Query Safety Layer
Ensure production-grade Cypher security, audit trails, and strict whitelisting.

#### [MODIFY] [safe_cypher_builder.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/graph/safe_cypher_builder.py)
- Ensure all query builders validate entity IDs and attributes against whitelist.
- Add `get_correction_candidates(entity_id, attribute, feedback_value)` for evaluation against canonical values.
- Audit logging for every query execution via `CypherAuditLogger`.

#### [MODIFY] [backend/app/graph/__init__.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/graph/__init__.py)
- Export `SafeCypherBuilder`, `CypherSecurityError`, `CypherAuditLogger`.

---

### 2. Track 4: Dissatisfaction Detection Module
Automated detection of user dissatisfaction in follow-up queries and conversion into structured claims.

#### [MODIFY] [dissatisfaction_detector.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/feedback/dissatisfaction_detector.py)
- Fix sentiment analyzer fallback: properly score positive keywords (e.g. "great", "excellent", "thanks") so `score > 0`, avoiding `-0.0` comparison failures when VADER is not present.
- Support 3-stage detection: Frustration check + Same referent check + Correction language pattern match.
- Blend confidence score using sentiment, similarity, and pattern match count.

#### [MODIFY] [correction_extractor.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/feedback/correction_extractor.py)
- Refine numeric extraction for Indian Rupee formats (`₹`, `Rs.`, decimals, `%`).
- Implement number role heuristics (asserted value vs. rejected value from original response).
- Attribute detection against AMC vocabulary (TER, NAV, RETURN, AUM, EXIT_LOAD, MIN_INVESTMENT).

#### [MODIFY] [feedback.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/api/routes/feedback.py)
- Add endpoint `POST /api/feedback/follow-up-detection`:
  - Receives `session_id`, `previous_response_id`, `follow_up_query`, optional `original_query`, `original_response`.
  - Runs `DissatisfactionDetector.is_correction_attempt()`.
  - On correction detection, auto-records feedback in `FeedbackStore` and returns structured claim payload.

#### [MODIFY] [test_dissatisfaction_detector.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/tests/test_dissatisfaction_detector.py)
- Verify that all 8 unit tests pass cleanly.

---

### 3. Track 5: Deterministic Rules Engine (Tier 1A)
Zero-LLM token rule verification for common failure modes (STOP-1 gate).

#### [MODIFY] [deterministic_rules.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/evaluation/deterministic_rules.py)
- Enhance C02 (Source Currency), C03 (Numeric Accuracy), and F06 (Citation Integrity) evaluation methods.
- Ensure `should_stop()` fires when any rule encounters a high-confidence FAIL (`confidence >= 0.9`).

#### [MODIFY] [evaluation_router.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/evaluation/evaluation_router.py)
- Integrate `DeterministicRuleEngine` into the evaluation pipeline with STOP-1 early return when rules decisively PASS or FAIL.

#### [NEW] [test_evaluation_router.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/tests/test_evaluation_router.py)
- Test STOP-1 short-circuit behavior (0 LLM tokens consumed on deterministic failures).

---

### 4. Track 6: Correction Patch Layer (Shadow Graph)
Fast, reversible correction layer that overrides canonical facts in the RAG retrieval context before LLM generation.

#### [NEW] [correction_patch_layer.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/graph/correction_patch_layer.py)
- Data model: `CorrectionPatch` (patch_id, entity_id, attribute, canonical_value, corrected_value, confidence, provenance, approved, created_at, expires_at).
- Redis store with thread-safe in-memory fallback.
- Unapproved patches get 7-day TTL; approved patches are permanent (no TTL).
- Method `add_correction(...)`.
- Method `get_correction(entity_id, attribute)`.
- Method `apply_patches_to_context(entities, retrieval_context)`: Injects `[CORRECTION - attribute]` priority blocks into retrieval context.
- Method `get_all_pending()` for governance queue.
- Method `promote_to_permanent(patch_id, neo4j_session)`: Updates canonical graph (Neo4j) and removes TTL.
- Method `delete_patch(patch_id)`: Removes patch on rejection.

#### [MODIFY] [orchestrator.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/retrieval/orchestrator.py)
- Integrate `CorrectionPatchLayer` in `RetrievalOrchestrator.answer()` after context assembly (Step 7) and before synthesizer execution (Step 8):
  - Extract entity IDs from `retrieval.resolved_entities` and `intent.entities_mentioned`.
  - Apply active patches to `context.context_text`.

#### [NEW] [test_correction_patch_layer.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/tests/test_correction_patch_layer.py)
- Unit tests: adding patches, TTL expiration, context injection, promotion, deletion, in-memory and Redis handling.

---

### 5. Track 7: Governance Review Queue (API + React UI)
Weekly batch approval workflow for compliance officers to inspect pending patches, verify evidence, and approve/reject changes.

#### [NEW] [governance.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/api/routes/governance.py)
- Router with prefix `/governance`:
  - `GET /api/governance/pending-corrections` (lists all pending `CorrectionProposal` objects with risk assessment: LOW, MEDIUM, HIGH).
  - `GET /api/governance/correction/{patch_id}` (retrieves single proposal with full provenance).
  - `POST /api/governance/approve/{patch_id}` (promotes patch to canonical Neo4j graph, removes TTL, logs audit).
  - `POST /api/governance/reject/{patch_id}` (deletes patch, logs audit).
  - `POST /api/governance/batch-approve` (approves or rejects multiple patch IDs).

#### [MODIFY] [main.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/main.py)
- Register `governance.router` under `/api`.

#### [MODIFY] [api.js](file:///c:/Users/Laptopadmin/Desktop/context-engineering/mf-context-engine/src/services/api.js)
- Add frontend API methods:
  - `fetchPendingCorrections()`
  - `approveCorrection(patchId, comment)`
  - `rejectCorrection(patchId, reason)`
  - `batchApproveCorrections(patchIds, action)`
  - `detectFollowUpCorrection(payload)`

#### [NEW] [GovernancePage.jsx](file:///c:/Users/Laptopadmin/Desktop/context-engineering/mf-context-engine/src/views/pages/GovernancePage.jsx)
- React view for the Governance Review Queue:
  - Header with summary metrics (Total Pending, High Risk, Expiring Soon).
  - Batch action toolbar (Select All, Approve Selected, Reject Selected).
  - Data table of pending corrections:
    - Entity Name & Canonical ID
    - Attribute (e.g. TER, NAV)
    - Current Canonical Value vs. Proposed Corrected Value
    - Confidence score with visual badge
    - Risk Level tag (LOW / MEDIUM / HIGH)
    - Expiration countdown (7-day TTL)
    - Action buttons: Approve, Reject, Inspect Evidence Modal.
  - Evidence & Provenance inspection modal showing raw feedback text, user ID, timestamp, and evaluation tier.

#### [MODIFY] [Sidebar.jsx](file:///c:/Users/Laptopadmin/Desktop/context-engineering/mf-context-engine/src/components/Sidebar.jsx) & [App.jsx](file:///c:/Users/Laptopadmin/Desktop/context-engineering/mf-context-engine/src/App.jsx)
- Register page `06_Governance` with `ClipboardCheck` icon in `PAGES` list and render `GovernancePage` in `App.jsx`.

---

### 6. Track 8: NER + Entity Resolution for Feedback
Extract structured claims from free-text feedback and resolve ambiguous fund names to canonical ISINs.

#### [NEW] [fund_master.json](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/data/fund_master.json)
- Canonical AMC fund catalog containing major Indian mutual funds with ISIN, fund name, AMC, category, plan (Direct/Regular), option (Growth/IDCW).

#### [NEW] [fund_name_matcher.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/feedback/fund_name_matcher.py)
- Fallback resolution chain:
  1. Exact match lookup against canonical names and ISINs.
  2. Fuzzy string matching (Levenshtein distance via `difflib`/`rapidfuzz`).
  3. Semantic embedding similarity using `all-MiniLM-L6-v2` against precomputed fund embeddings.
  4. Disambiguation using user context / query history (Direct vs. Regular preference).
- Returns resolved ISIN, canonical fund name, confidence score, and candidate list if ambiguous.

#### [NEW] [ner_pipeline.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/feedback/ner_pipeline.py)
- `FeedbackNERPipeline`: extracts entity candidates, financial attributes, and asserted/rejected values from user feedback.
- Combines with `FundNameMatcher` to resolve canonical entity IDs.

#### [MODIFY] [feedback.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/api/routes/feedback.py)
- Integrate `FeedbackNERPipeline` and `FundNameMatcher` into `POST /api/feedback` so that feedback submissions automatically extract structured claims and resolve canonical ISINs.

#### [NEW] [test_ner_pipeline.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/tests/test_ner_pipeline.py) & [test_fund_name_matcher.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/tests/test_fund_name_matcher.py)
- Unit tests verifying exact match, fuzzy matching, abbreviation expansion, and ambiguous resolution.

---

## Verification Plan

### Automated Tests
Execute backend pytest suite covering all tracks:
```powershell
cd backend
pytest tests/test_safe_cypher.py `
       tests/test_dissatisfaction_detector.py `
       tests/test_deterministic_rules.py `
       tests/test_correction_patch_layer.py `
       tests/test_governance_api.py `
       tests/test_ner_pipeline.py `
       tests/test_fund_name_matcher.py -v
```

### Frontend Build Verification
Verify `mf-context-engine` compiles with zero build errors:
```powershell
cd mf-context-engine
npm run build
```

### End-to-End Flow Verification
1. **Dissatisfaction Detection**: Call `POST /api/feedback/follow-up-detection` with "No, that's wrong! TER is 0.82% not 0.79%". Verify extraction of `{ attribute: "TER", asserted_value: "0.82", rejected_value: "0.79" }` and auto-created feedback record.
2. **Patch Layer & Context Injection**: Add patch for `INF846K01DP5:TER = 0.82`. Call context assembly / orchestrator query. Verify `[CORRECTION - TER]` block is injected into the synthesized context.
3. **Governance Review UI**: Open `mf-context-engine`, navigate to Governance Review Queue, see the pending correction, inspect evidence, click "Approve" (or "Reject"), and verify backend status updates.
4. **NER & Entity Resolution**: Test resolution of "axis bluechip" -> `INF846K01DP5`. Verify structured claim resolution.
