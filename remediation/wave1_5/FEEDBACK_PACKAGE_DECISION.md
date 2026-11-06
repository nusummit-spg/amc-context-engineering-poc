# Feedback Loop Package Decision - Wave 1.5

**Date:** 6 November 2026  
**Branch:** amc-dev  
**SHA:** 17fe112 (current HEAD)

## Executive Summary

**Decision:** BLOCKED - Requires maintainer/product-owner approval before proceeding.

## Background

The `packages/amc-feedback-loop/` directory was deleted in commit eccc075 (Wave 1.4 Batch A).

**Files deleted (37 files, ~8,000 lines):**
- `src/feedback_loop/server.py` - Microservice entrypoint
- `src/feedback_loop/orchestrator.py` - Main orchestration logic
- `src/feedback_loop/api.py` - HTTP API endpoints
- `src/feedback_loop/models.py` - Domain models
- `src/feedback_loop/domain_models.py` - Additional models
- `src/feedback_loop/database.py` - Database layer
- `src/feedback_loop/loop.py` - Main feedback loop
- `src/feedback_loop/ingest.py` - Ingestion handlers
- `src/feedback_loop/services/{adjudication,classification,diagnosis,enrichment,repair_analyzer,router}.py`
- `src/feedback_loop/adapters/db.py` - Database adapter
- `src/feedback_loop/adapters/evidence.py` - Evidence adapter
- `src/feedback_loop/adapters/sqlite/{db_adapter,evidence_adapter}.py`
- `src/feedback_loop/logging.py` - Logging configuration
- `src/feedback_loop/config.py` - Configuration
- `src/feedback_loop/audit.py` - Audit logging
- `tests/test_*.py` - Test suite
- `README.md`, `pyproject.toml`

## Current State

### Backend/app/feedback/ (partial replacement)
The backend has `backend/app/feedback/` module with:
- `correction_extractor.py` - Extracts corrections from user feedback
- `dissatisfaction_detector.py` - Detects user dissatisfaction
- `feedback_cache.py` - Caching layer
- `feedback_timer.py` - Timeout handling
- `fund_name_matcher.py` - Fund name resolution
- `intent_matcher.py` - Intent matching
- `issue_matcher.py` - Issue matching
- `issue_store.py` - Issue storage
- `metrics_enrichment.py` - Metrics enrichment
- `ner_pipeline.py` - NER processing
- `repair_linkage.py` - Repair linkage
- `session_manager.py` - Session management
- `timeout_processor.py` - Timeout processing

**Gap Analysis:**

| Deleted Package Module | Backend Replacement | Status |
|------------------------|---------------------|--------|
| server.py | None | MISSING - No microservice entrypoint |
| orchestrator.py | None | MISSING - No orchestration logic |
| api.py | backend/app/api/routes/ | PARTIAL - Some routes exist but incomplete |
| models.py | app/schemas/*.py | PARTIAL - Schemas exist but not all fields |
| database.py | app/core/database.py | PARTIAL - General DB but not Feedback-specific |
| loop.py | None | MISSING - No main feedback loop |
| ingest.py | backend/scripts/ingest_corpus.py | PARTIAL - Ingestion exists but not Feedback-specific |
| services/adjudication.py | None | MISSING |
| services/classification.py | None | MISSING |
| services/diagnosis.py | None | MISSING |
| services/enrichment.py | None | MISSING |
| services/repair_analyzer.py | None | MISSING |
| services/router.py | None | MISSING |
| adapters/db.py | app/core/database.py | PARTIAL |
| adapters/evidence.py | None | MISSING |
| triggers/feedback_trigger.py | None | MISSING |

## Dependencies

| Component | Uses Feedback | Impact of Deletion |
|-----------|--------------|-------------------|
| backend/app/api/routes/governance.py | None (direct to repair engine) | No impact |
| backend/app/services/repair_integration.py | None (direct to repair engine) | No impact |
| packages/amc-repair-engine | None (independent package) | No impact |
| mf-context-engine/frontend | Unknown - needs audit | Potential API breakage |
| Docker/compose files | Unknown - needs audit | Potential startup failure |
| CI/CD workflows | Unknown - needs audit | Potential test failures |

## Required Actions

### Option A: Restore Feedback Package
1. Restore `packages/amc-feedback-loop/` from git history
2. Update imports throughout codebase
3. Run full test suite
4. Update deployment manifests

### Option B: Implement Replacement
1. Implement missing modules in backend/app/feedback/
2. Create HTTP API endpoints for microservice compatibility
3. Migrate database schema and data
4. Implement orchestration logic
5. Run full test suite

### Option C: Accept Deletion
1. Document all impacted features
2. Add explicit error messages where Feedback was used
3. Update documentation
4. Add maintainer approval in release gate

## Recommendation

**BLOCKED** pending maintainer decision.

The Feedback package was a complete microservice with its own server, orchestrator, and services. The backend/app/feedback/ module appears to be a partial replacement focused on patch extraction, not a full replacement.

Before proceeding with Wave 1.5 implementation:
1. Determine if Feedback package deletion was intentional or accidental
2. If intentional, approve the replacement strategy
3. Update deployment and CI/CD configurations
4. Run integration tests to verify no regression

## Next Steps

Once maintainer decision is made, update this document and proceed with:
1. R02-R08: Regression containment fixes (P0)
2. P01-P10: Publication/rollback pipeline (P0)
3. F01-F08: Financial correctness (P0)
4. Q01-Q06: Query/Feedback/UI parity (P0/P1)
5. A01-A07: CI, migrations, release assurance (required)
