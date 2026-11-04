# Wave 1.2 Implementation Baseline and Decisions

**Date:** 2026-11-04  
**Repository:** nusummit-spg/amc-context-engineering-poc  
**Branch:** amc-dev  
**Pinned HEAD:** af35d86b836884e6527f35b334e14848906e9f57  
**Comparison Baseline:** 910bae72030cbf641badbdb6e2c6fe82b78a9f57 (Wave 1.1)  
**Status:** IMPLEMENTATION IN PROGRESS

## Executive Summary

Wave 1.2 addresses critical gaps identified in CTO re-audit:
- **COMP-01:** 18 missing admin routes causing frontend regression
- **REP-10 through REP-13:** Repair microservice auth, four-eyes, state machine
- **PUB-10 through PUB-11:** Publication verification and saga
- **FIN-10 through FIN-12:** Financial correctness and policy enforcement
- **SEC-10, ING-10, OPS-10:** Security hardening, ingestion integrity, CI/evidence

## Git Baseline

```
Current HEAD: af35d86b836884e6527f35b334e14848906e9f57
Author: Kiro AI Agent
Message: feat(security): SEC-01, SEC-02, SEC-03 wave 1.1 P0 route enforcement
Date: 2026-11-04

Commits since Wave 1.1 audit (910bae7):
- af35d86: SEC-01, SEC-02, SEC-03 route enforcement
- (1 prior commit)
Total: 2 commits, 37 changed files
```

## Component Versions

### Backend Stack
- Python: 3.9+
- FastAPI: Latest
- SQLAlchemy: Latest with SQLite backend
- Neo4j: Graph database
- FAISS: Vector store
- Groq: LLM synthesis

### Data Assets
- Database: `backend/data.db` (SQLite)
- Graph: Neo4j (connection required)
- Vector Store: FAISS index files
- Financial DB: Canonical typed queries table (if exists)
- Source Data: CSV/XLSX manifests (version tracking required)

### Authentication
- JWT-based with bearer tokens
- User repository: SQL (`auth_users` table)
- Invitation tokens: `invitation_tokens` table
- Token revocation: `revoked_tokens` table

## Critical Findings from Re-Audit

### COMP-01: Admin Route Regression

**18 Missing Routes from Previous Implementation:**

1. `POST /api/admin/users/sync` - User synchronization
2. `GET /api/admin/rbac` - RBAC configuration
3. `GET /api/admin/audit` - Audit logs
4. `POST /api/admin/ingestion/staleness` - Staleness checks
5. `GET /api/admin/ingestion/tasks` - Task listing
6. `GET /api/admin/ingestion/tasks/active` - Active tasks
7. `GET /api/admin/ingestion/notifications` - Notifications
8. `POST /api/admin/ingestion/notifications/{task_id}/read` - Mark read
9. `POST /api/admin/ingestion/notifications/read-all` - Mark all read
10. `GET /api/admin/ingestion/proposed-edges` - Proposed graph edges
11. `POST /api/admin/ingestion/edges/{edge_id}/confirm` - Confirm edge
12. `POST /api/admin/ingestion/edges/{edge_id}/reject` - Reject edge
13. `GET /api/admin/ingestion/compliance-report` - Compliance reporting
14. `GET /api/admin/intent-cache/stats` - Intent cache statistics
15. `GET /api/admin/cache/stats` - Cache statistics
16. `POST /api/admin/intent-cache/invalidate-domain` - Invalidate domain
17. `POST /api/admin/intent-cache/clear` - Clear intent cache
18. `GET /api/admin/feedback/issues` - Feedback issues

**Frontend Dependencies:**
- `mf-context-engine/src/services/api.js` references multiple endpoints
- Admin dashboard UI likely broken
- Ingestion management UI affected
- Cache management UI affected

**Resolution Strategy:**
- R1-09: Restore each with proper authentication
- Document intentional deprecations
- Update frontend or provide compatibility layer

### Security Gaps

**REP-10:** Repair microservice endpoints lack authentication
- Service: `packages/amc-repair-engine/src/amc_repair/server.py`
- Endpoints: create, approve, batch-approve, promote
- Risk: Direct unauthenticated mutations if service reachable

**REP-11:** Four-eyes enforcement unproven
- No proposer != approver checks in code
- Approval may lead to immediate promotion
- Missing staged → verified → active flow

**SEC-10:** Invitation token security
- Tokens stored plaintext (not hashed)
- Token replay risk
- Tenant assignment needs audit

### Financial Correctness

**FIN-10:** Metric policy not enforced in executor
- AAUM marked pending but sums still execute
- Need `METRIC_POLICY_BLOCKED` error

**FIN-11:** Float arithmetic in financial calculations
- `CAST(aaum_crore AS REAL)` in planner
- Python float() usage
- Precision loss risk

**FIN-12:** Legacy CSV/Pandas fallback active
- SchemeAggregationService has fallback path
- Can return hallucinated numbers
- Must fail closed

### Publication Safety

**PUB-10:** No verification of actual effects
- `_trigger_reindex()` only logs
- Graph postcondition checks existence, not value
- Vector proposal marked APPLIED without work

**PUB-11:** Transaction saga broken
- Multiple proposals in one SQL session
- External commits can be orphaned
- Rollback risk

### Ingestion Integrity

**ING-10:** Manifest validation weak
- Hardcoded expectations (16,245 rows, 22 chunks)
- Missing hash verification
- No field-level validity tracking

## Business Decisions Required

### Data Steward Sign-Offs Needed

1. **AAUM Additivity:**
   - Can AAUM be summed across schemes?
   - Can AAUM be summed across plan variants (growth/IDCW)?
   - Can AAUM be summed across quarters?
   - **Status:** BLOCKED - calculations disabled until approved

2. **Fund Identity:**
   - Official hierarchy: AMC → Scheme → Plan → Option
   - How to handle name collisions across AMCs
   - Display name vs canonical ID usage
   - **Status:** PENDING

3. **NAV Semantics:**
   - NAV date binding rules
   - Multiple plans on same date handling
   - Latest NAV selection policy
   - **Status:** PENDING

4. **Closure Date:**
   - What does Closure_Date mean?
   - Are closed funds excluded from totals?
   - Status inference rules
   - **Status:** PENDING

5. **Count Metrics:**
   - What is "16,245" - source rows or folios?
   - Do we have actual investor folio IDs?
   - Fund count vs scheme count vs plan count
   - **Status:** PENDING

### Technical Decisions

1. **Admin Route Restoration:**
   - Which 18 routes to restore vs deprecate
   - Frontend migration timeline
   - Compatibility layer approach
   - **Owner:** Product + Frontend team

2. **Service Authentication:**
   - Workload identity method (JWT, mTLS, API key)
   - Service-to-service vs user-on-behalf-of
   - Token refresh and rotation
   - **Owner:** Security team

3. **Publication Saga:**
   - Outbox table schema
   - Retry policy and dead letter queue
   - Compensation transaction design
   - **Owner:** Backend architecture

## Implementation Phases

### R0: Baseline Freeze (CURRENT)
- [x] Directory structure
- [x] Baseline document
- [ ] Route compatibility matrix
- [ ] Frontend contract analysis
- [ ] Financial gold baseline

### R1: Security & Repair P0
- [ ] Admin route restoration
- [ ] Repair service authentication
- [ ] Four-eyes approval enforcement
- [ ] Patch state machine
- [ ] Vector isolation
- [ ] Publication saga
- [ ] Security hardening

### F1: Financial Policy
- [ ] Metric dictionary enforcement
- [ ] Exact decimal arithmetic
- [ ] Canonical identities
- [ ] NAV/date semantics
- [ ] Independent gold tests

### F2: Ingestion Integrity
- [ ] Manifest validation
- [ ] Field-level validity
- [ ] Immutable staging
- [ ] Atomic activation

### F3: Query Routing
- [ ] Structured numeric gateway
- [ ] Fail-closed errors
- [ ] Stream/query parity
- [ ] PDF/TXT preservation

### Q1: Operational Assurance
- [ ] Evidence-based feedback
- [ ] CI/CD pipeline
- [ ] Release gates

## Risk Register

| Risk ID | Description | Severity | Mitigation |
|---------|-------------|----------|------------|
| RISK-01 | Frontend broken by missing routes | P0 | Restore with auth or provide compatibility |
| RISK-02 | Unauthenticated Repair service | P0 | Add service auth in R1 |
| RISK-03 | Self-approval possible | P0 | Implement four-eyes in R1 |
| RISK-04 | Pending patches served | P0 | Vector isolation in R1 |
| RISK-05 | Float precision loss | P0 | Decimal arithmetic in F1 |
| RISK-06 | Unapproved AAUM sums | P0 | Policy enforcement in F1 |
| RISK-07 | LLM number hallucination | P0 | Fail-closed routing in F3 |
| RISK-08 | Publication without verification | P0 | Saga pattern in R1 |
| RISK-09 | No rollback capability | P1 | Immutable versions in F2 |
| RISK-10 | No CI evidence | P1 | GitHub Actions in Q1 |

## Success Criteria

### Release Gates (Must Pass)

- **COMP:** All frontend admin functions work or intentionally migrated
- **SEC:** No unauthenticated/unauthorized access to sensitive operations
- **REP:** Four-eyes enforced, pending isolated, state machine complete
- **PUB:** Verified effects, idempotent saga, safe rollback
- **NUM:** Approved metrics only, exact arithmetic, complete evidence
- **ING:** Manifest validated, field-level tracked, atomic activation
- **E2E:** Query/stream parity, PDF/TXT preserved, fail-closed errors
- **OPS:** CI passes, reproducible deployment, rollback tested

### Evidence Requirements

Each gate requires:
1. Actual code implementation
2. Passing test execution (not just test creation)
3. CI run ID or manual execution log
4. Git commit SHA
5. Review sign-off

## References

- Original handoff: `docs/AMC_Wave1_2_Next_Implementation_Agent_Handoff_2026-11-04.md`
- CTO specifications: `docs/AMC_Tasks_3_11_26/AMC_Specs/`
- Wave 1.1 artifacts: `remediation/wave1_1/p0_closure/`

## Change Log

- 2026-11-04: Baseline document created
- 2026-11-04: R0 directory structure established
- Next: R0-02 Route compatibility matrix
