# Wave 1.3 Source Baseline

**Implementation Start:** 5 November 2026  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Branch:** `feature/wave1-3-truth-and-financial-correctness` (created from `amc-dev`)  
**Base SHA:** `c7aa9203819d21da20f2ad92223ccc4ff32778af`  
**Previous Baseline:** `af35d86b836884e6527f35b334e14848906e9f57`  
**Handoff Document:** `docs/AMC_Wave1_3_Next_Actions_Agent_Handoff_2026-11-04.md`

## Execution Environment

- **OS:** Windows (win32)
- **Shell:** PowerShell
- **Python:** 3.11+ (expected)
- **Backend:** FastAPI + SQLAlchemy + Neo4j
- **Microservice:** AMC Repair Engine (standalone FastAPI)
- **Frontend:** React (mf-context-engine)

## Verified Starting State

### Repository Status
- Working directory: Clean except for new handoff document
- Uncommitted files: `docs/AMC_Wave1_3_Next_Actions_Agent_Handoff_2026-11-04.md`
- Last commit: c7aa9203819d21da20f2ad92223ccc4ff32778af

### Key Code States Confirmed

#### 1. Repair Service Authentication (`packages/amc-repair-engine/src/amc_repair/auth.py`)
- Custom two-part HMAC tokens (payload.signature), not standard JWT
- Service secret: `REPAIR_SERVICE_SECRET` with development default
- `RepairUser.can_approve()`: **DEFECT** - allows any `is_service` to approve (C-04)
- Missing `exp` does not fail validation: **DEFECT** (C-05)
- Token verification: No issuer/audience/type enforcement: **DEFECT** (C-05)
- Four-eyes: Implemented in server approval endpoints with proposer checks ✓

#### 2. Repair Server Endpoints (`packages/amc-repair-engine/src/amc_repair/server.py`)
- `POST /api/patches`: Creates patches with forced `approved=False`, records proposer ✓
- `GET /api/patches/pending`: **Tenant filtering present** ✓
- `GET /api/patches/for-entities`: **DEFECT** - No authentication (C-03)
- `GET /api/patches/{patch_id}`: **DEFECT** - No authentication (C-03)
- `POST /api/patches/{patch_id}/approve`: Four-eyes check implemented ✓
- `POST /api/patches/batch-approve`: Four-eyes per-patch ✓
- Tenant isolation: Implemented for authenticated endpoints ✓

#### 3. Admin Routes (`backend/app/api/routes/admin.py`)
- All endpoints have `CurrentUser` dependency ✓
- Role-based authorization present ✓
- **Restored endpoints** from Wave 1.2:
  - `POST /admin/users/sync`: **Mock data** (C-01)
  - `GET /admin/ingestion/tasks`: **Mock example task** (C-01)
  - `GET /admin/ingestion/proposed-edges`: **Empty list** (C-01)
  - `POST /admin/ingestion/edges/{edge_id}/confirm`: **Four-eyes commented out** (C-02)
  - `POST /admin/cache/clear`: Partial implementation, may not invoke real cache
  - `POST /admin/intent-cache/clear`: **TODO implementation** (C-01)

#### 4. Invitation Tokens (`backend/app/schemas/invitation_token.py`, admin.py)
- `POST /admin/users`: Creates secure 32-byte token ✓
- **DEFECT**: Token stored/returned as **plaintext** (C-14)
- No atomic single-use enforcement documented
- No migration for invitation_token table found

### Critical Defects Confirmed (from Handoff)

| ID | Severity | Location | Issue |
|----|----------|----------|-------|
| C-01 | P0 | admin.py | Mock success responses without real effects |
| C-02 | P0 | admin.py:confirm_proposed_edge | Four-eyes check commented out |
| C-03 | P0 | server.py:get_patches_for_entities, get_patch_by_id | No auth dependencies |
| C-04 | P0 | auth.py:RepairUser.can_approve() | Service scope escalation - any is_service can approve |
| C-05 | P0 | auth.py:verify_token_signature | Missing exp OK, no iss/aud/type enforcement, dev secret |
| C-06 | P0 | Cross-system | Main/Repair token interoperability unclear |
| C-07 | P0 | governance.py | Main approval paths lack four-eyes (not reviewed in this file) |
| C-14 | P1 | admin.py, invitation schema | Plaintext invitation tokens |

### Tests Status
- `backend/tests/test_wave12_route_compatibility.py`: **Exists**
- `packages/amc-repair-engine/tests/test_repair_service_auth.py`: **Exists**
- Skip count: **36 skipped in backend tests** per handoff
- **No GitHub Actions runs** for current SHA
- **Tests not independently verified** by this implementer yet

## Batch A Execution Plan

Tasks to be executed in order:

1. **A01** - Replace mock Administrative success with real effects
2. **A02** - Close remaining Repair read access
3. **A03** - Correct token trust boundaries
4. **A04** - Enforce four-eyes across all approval paths
5. **A05** - Harden invitations
6. **A06** - Remove skipped tests, add real JWT fixtures

## Runtime Configuration

Expected environment variables:
- `REPAIR_SERVICE_SECRET`: **Must be strong in production**
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- `USE_REDIS`, `REDIS_HOST`, `REDIS_PORT`
- Main app: `JWT_SECRET`, database connection

## Implementation Constraints

- **No production deployments**
- **No live data mutation**
- **No forced branch rewrites**
- **Fresh clone must be reproducible**
- Tests must be **run and recorded**, not just written
- **Fail closed** on security and authorization
- **Explicit unavailable** responses better than mock success

## Next Steps

Execute Batch A (A01-A06) with runnable tests, evidence, and rollback documentation.

---
**Baseline recorded:** 5 November 2026  
**Implementation by:** Kiro AI Agent  
**Reviewed basis:** Read-only source code inspection + handoff audit
