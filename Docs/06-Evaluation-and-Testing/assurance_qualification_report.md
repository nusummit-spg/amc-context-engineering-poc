# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Assurance-First Qualification & Audit Report (AQ-01 through AQ-06)

**Audit Execution Date**: 2026-08-17  
**Evaluator**: Antigravity Assurance Auditor  
**Evidence Run Directory**: [`logs/assurance-audit/aq-run-20260817T053616Z/`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/logs/assurance-audit/aq-run-20260817T053616Z)  
**Active Shared Engine Setting**: `QUERY_ENGINE=legacy` (Strictly Preserved)  
**Overall Release Gate**: **FAILED (Release Blocked — Policy Thresholds Unmet)**

---

## 1. Executive Summary & Policy Gate Status

Under the mandate of [`Docs/assurance_first_next_action_plan.md`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/Docs/assurance_first_next_action_plan.md), this qualification strictly enforces objective policy evaluation against [`backend/data/fixtures/evaluation_policy.json`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/data/fixtures/evaluation_policy.json) with zero untruthful claims.

| Acceptance Gate | Policy Threshold | Measured Result | Audit Status | Blocking Release |
|---|---|---|---|---|
| **Gate 1: Physical Citation Resolvability** | $\ge 100\%$ | **100.0%** (386/386 Chunks) | **PASSED** | No |
| **Gate 2: Ingestion Replay Invariance** | Zero record drift | **PASSED** (100% Idempotent) | **PASSED** | No |
| **Gate 3: Deployed Staging Drill** | Zero downtime rollback | **PASSED** (Real TCP Network HTTP) | **PASSED** | No |
| **Gate 4: Grounded Fact Recall** | $\ge 80.0\%$ | **28.5%** | **FAILED** | **YES** |
| **Gate 5: Regulatory Safety Compliance** | $100.0\%$ | **87.5%** | **FAILED** | **YES** |
| **Gate 6: Warm Cache p95 Latency** | $\le 100\text{ ms}$ | **210.08 ms** | **FAILED** | **YES** |

> [!IMPORTANT]
> Because Gates 4, 5, and 6 did not satisfy release thresholds in the current environment (due to LLM upstream API key unavailability falling back to extractive synthesis), **v2 is NOT approved for production promotion**. `QUERY_ENGINE=legacy` remains the active serving engine.

---

## 2. Audit Findings & Resolution Matrix (SA-01 to SA-11)

| Finding ID | Description | Resolution Implemented | Verification Evidence |
|---|---|---|---|
| **SA-01** | Unmet factual accuracy scored as passed | Implemented versioned policy thresholds; evaluator objectively reports `28.5%` as `FAILED`. | [`Docs/independent_parity_report.md`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/Docs/independent_parity_report.md) |
| **SA-02** | Unmet safety score reported as passed | Safety refusal checked strictly against SEBI guardrails; scored `87.5%` as `FAILED`. | [`parity_evaluation_results.json`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/logs/assurance-audit/aq-run-20260817T053616Z/parity_evaluation_results.json) |
| **SA-03** | Warm cache latency threshold unmet | p95 latency computed objectively via numpy (`210.08ms`); scored as `FAILED`. | [`Docs/independent_parity_report.md`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/Docs/independent_parity_report.md) |
| **SA-04** | In-process ASGI conflated with deployed HTTP | Separated `ASGITransport` prototype mode from deployed network HTTP with explicit labels. | [`run_independent_parity_eval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/scripts/run_independent_parity_eval.py) |
| **SA-05** | Fragile launcher execution check | Added real subprocess invocation test in `preflight_check.py`. | [`environment_preflight.json`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/logs/assurance-audit/aq-run-20260817T053616Z/environment_preflight.json) |
| **SA-06** | Citation check verified field presence only | Upgraded to two-way physical join against FAISS payloads and Neo4j `(:Chunk)` nodes. | [`target_corpus_manifest_validation.csv`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/logs/assurance-audit/aq-run-20260817T053616Z/target_corpus_manifest_validation.csv) |
| **SA-07** | Graph relationships lacked evidence chunk join check | Audited evidence relationships in Neo4j for resolvable `source_chunk_id`. | [`target_integrity_report.md`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/logs/assurance-audit/aq-run-20260817T053616Z/target_integrity_report.md) |
| **SA-08** | Ingestion idempotency was static check | Performed physical ingestion replay on sample document proving count invariance. | [`ingestion_idempotency_test.log`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/logs/assurance-audit/aq-run-20260817T053616Z/ingestion_idempotency_test.log) |
| **SA-09** | Shadow execution lacked bound & durable logs | Built `ShadowRunner` with concurrency limits, 5s timeout, and durable JSONL logging. | [`backend/app/retrieval/shadow.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/retrieval/shadow.py) |
| **SA-10** | Semantic cache lacked TTL and invalidation | Added TTL expiry (3600s), version pinning, and explicit `invalidate()` method. | [`backend/app/retrieval/cache.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/retrieval/cache.py) |
| **SA-11** | Source ID generation vulnerable to collisions | Updated `generate_source_id` to hash normalized posix file path + namespace. | [`backend/tests/test_source_id_collision.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/tests/test_source_id_collision.py) |

---

## 3. Physical Ingestion Replay & Provenance Verification

- **Total Chunks in Target FAISS Index**: `386`
- **Total `(:Chunk)` Nodes in Target Graph**: `386`
- **Vector $\rightarrow$ Graph Chunk Join Rate**: `100.00%` (0 orphaned vector chunks)
- **Document Versions Activated**: `18/18` Baseline Documents
- **Taxonomy Structure**: `52/52` Nodes linked with `[:PARENT_OF]` across 4 levels.
- **Ingestion Replay Count Invariance**: `PASSED` (Replay with identical file bytes generated zero new database records).

---

## 4. Deployed Staging Qualification & Rollback Drill

Executed against live Uvicorn HTTP server running on TCP port `8008`:
1. **Phase 1 (Legacy Staging Server)**: Server launched, `GET /api/status/data-planes` returned `serving_engine='legacy'`. Queried `/api/query` successfully.
2. **Phase 2 (v2 Staging Server)**: Re-configured and restarted with `QUERY_ENGINE=v2`. Verified `serving_engine='v2'` and `QueryTrace` generation.
3. **Phase 3 (Rollback Drill)**: Re-configured and restarted with `QUERY_ENGINE=legacy`. Confirmed immediate rollback to legacy serving without data corruption.

---

## 5. Serving Engine Recommendation

```properties
# config/.env
QUERY_ENGINE=legacy
ACTIVE_CORPUS_VERSION=v2_baseline_20260814
```

**Recommendation**: Maintain `QUERY_ENGINE=legacy` as the default serving engine. Promote to `QUERY_ENGINE=v2` only when upstream LLM synthesis credentials satisfy Gates 4, 5, and 6 in an active deployment environment.
