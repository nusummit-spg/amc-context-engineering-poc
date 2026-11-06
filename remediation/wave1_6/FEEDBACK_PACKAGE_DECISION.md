# Feedback Loop Package Deletion Decision

**Date:** 6 November 2026  
**Delete commit:** eccc075 (Wave 1.4 Batch A)  
**Current branch:** amc-dev (4ede4338642949f0a32ee0672b4dc09616659193)

## Executive Summary

The `packages/amc-feedback-loop` source tree was removed in commit eccc075. This decision is **BLOCKED** for Wave 1.6 until explicit product-owner approval is obtained.

## What Was Deleted

| File | Purpose |
|------|---------|
| README.md | Package documentation |
| pyproject.toml | Package dependencies |
| src/feedback_loop/api.py | API endpoints |
| src/feedback_loop/audit.py | Audit logging |
| src/feedback_loop/config.py | Configuration |
| src/feedback_loop/ingest.py | Ingestion logic |
| src/feedback_loop/logging.py | Logging utilities |
| src/feedback_loop/loop.py | Feedback loop orchestration |
| src/feedback_loop/models.py | Data models |
| src/feedback_loop/server.py | Server entrypoint |
| tests/ | All test files (11 files) |

## Migration Path

If deletion is intentional, the following components must be migrated:

### Feedback Issue Lifecycle
- `Issue` model → `app/services/feedback_outcome_service.py`
- `Classification` service → New service required
- `Adjudication` service → New service required
- `Diagnosis` service → New service required

### Repair Linkage
- `FeedbackRepairLinkage` → `app/services/feedback_outcome_service.py`
- `RepairNotificationSystem` → `backend/app/services/repair_integration.py`

### Triggers and Events
- `FeedbackTrigger` → New service required
- `EventProcessor` → New service required

## Recommendations

1. **Restore** the original `packages/amc-feedback-loop` package (safest)
2. **Replace** with main-app modules (requires full compatibility mapping)
3. **Deprecate** Feedback package entirely (requires frontend changes)

## Required Actions

- [ ] Product owner signs off on deletion or restoration
- [ ] Update `backend/app/clients/repair_client.py` imports
- [ ] Update frontend Feedback UI to use new module structure
- [ ] Create migration scripts for existing FeedbackIssue records
- [ ] Run existing feedback_loop test suite (11 tests)

## References

- Deletion commit: eccc075
- Related PR: Wave 1.4 Batch A
- Handoff: R01 - Resolve Feedback-loop package deletion
