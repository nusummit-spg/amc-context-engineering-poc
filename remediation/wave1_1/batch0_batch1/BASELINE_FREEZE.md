# Batch 0: Baseline Freeze

**Purpose**: Immutable snapshot for reproducible verification  
**Created**: 2026-11-04  
**Auditor**: Kiro AI Agent  

---

## Git State

**Branch**: `feature/wave1-canonical-data-and-typed-queries`  
**SHA**: `06cf9755f4b3dde3e9a24a430973f4bf86ed711d`  
**Commit Author**: Hemant More <hemantm.aids_ioe@bkc.met.edu>  
**Commit Date**: 2026-02-02 20:38:46 UTC  
**Commit Message**: feat(tabular): Wave 2 - tabular ingestion, NAV query interception, and patch governance

**Remote**: `origin/feature/wave1-canonical-data-and-typed-queries`  
**Parent Commits**:
- `6cf854b` - feat(data-model): Wave 1 foundation - canonical schema & typed repository
- `3eb8ac0` - feat(security): Wave 0 - P0 containment and baseline establishment
- `e3c74e0` - feat: enhance CSV retrieval, model provider configuration, and UI copy prompt capabilities (amc-dev)

---

## Dataset State

### Active Financial Database

**File**: `backend/data/financial.db`  
**SHA256**: `3EAEB4CAB5464D2CA279BC7A8D742C923ED3F310FAB1ACD46FD0462B4FCDCACB`  
**Active Version**: `v1_baseline`  
**Status**: `RECONCILED`

**Row Counts**:
- Source rows: 16,245
- NAV observations: 14,208
- AAUM observations: 8,178
- Quarantined rows: 0

**Schema Version**: `SOURCE_SCHEMA_V1`  
**Metric Registry**: `METRIC_REGISTRY_V1`

### Source Document Chunks

**Manifest**: `backend/data/source_docs/chunks/manifest.json`  
**Total Chunks**: 22  
**Expected Rows**: 16,245  
**Chunk Distribution**: 21 × 750 rows + 1 × 495 rows

**Sample Chunk Hashes** (for verification):
- `chunk_001.csv`: First 750 rows (row 1-750)
- `chunk_022.csv`: Final 495 rows (row 15751-16245)

---

## Code State

### Critical Files (SHA256 hashes)

**Security & Auth**:
- `backend/app/compliance/security.py`
- `backend/app/api/deps.py`
- `backend/app/auth/service.py`

**Repair & Governance**:
- `backend/app/services/repair_integration.py` - Contains auto-approval logic (P0 fix target)
- `backend/app/services/promotion_service.py` - Contains driver failure handling (P0 fix target)
- `backend/app/graph/correction_patch_layer.py` - Contains pending patch serving (P0 fix target)
- `backend/app/retrieval/orchestrator.py` - Contains patch application logic (P0 fix target)

**Typed Query Foundation**:
- `backend/app/tabular/contracts.py` - Canonical schema and metric registry
- `backend/app/tabular/planner.py` - Query plan compilation
- `backend/app/tabular/executor.py` - Deterministic SQL execution
- `backend/app/tabular/repository.py` - Financial data access layer

**API Routes**:
- `backend/app/api/routes/admin.py` - User management (auth enforcement target)
- `backend/app/api/routes/governance.py` - Repair governance (approval enforcement target)
- `backend/app/api/routes/ingest.py` - Data ingestion (auth enforcement target)

### Python Environment

**Python Version**: 3.11+ (required)  
**Key Dependencies**:
- fastapi
- sqlalchemy
- neo4j
- pydantic
- httpx

**Virtual Environment**: `.venv` (local development)

---

## Configuration State

### Environment Variables (sanitized)

**Database**:
- `DATABASE_URL`: SQLite financial.db
- `NEO4J_URI`: bolt://localhost:7687
- `NEO4J_DATABASE`: amc

**Services**:
- `REPAIR_SERVICE_URL`: http://localhost:8002
- `MICROSERVICES_MODE`: false (monolithic deployment)

**Security** (P0 AUDIT TARGET):
- `REPAIR_AUTO_APPROVE_ENABLED`: **NOT SET** (defaults permissive in code)
- `DEFAULT_PASSWORD`: "Welcome@2026" (P0 removal target)

**Models**:
- Provider: OpenAI / Anthropic
- Embedding Model: text-embedding-3-small

---

## Known P0 Vulnerabilities (Pre-Fix)

### GOV-01: Header-Based Role Trust
**Status**: ✅ PARTIAL FIX (Wave 0 containment)  
**Current**: `get_client_role()` rejects missing header (401) instead of defaulting to ADMIN  
**Remaining**: Full JWT enforcement via `CurrentUser` not universally applied

### GOV-03: Confidence-Based Auto-Approval
**Status**: 🚨 VULNERABLE  
**Location**: `repair_integration.py` line ~200-335  
**Risk**: confidence≥0.95 + LOW risk → automatic canonical graph mutation

### GOV-04: Pending Patch Serving
**Status**: 🚨 VULNERABLE  
**Location**: `orchestrator.py` line ~370-431  
**Risk**: Unapproved corrections (confidence≥0.70) contaminate user answers

### GOV-05: Imperative Instruction Injection
**Status**: 🚨 VULNERABLE  
**Location**: `correction_patch_layer.py` `apply_patches_to_context()`  
**Risk**: Pending patches converted to LLM instructions

### GOV-06: Phantom APPLIED Status
**Status**: 🚨 VULNERABLE  
**Location**: `promotion_service.py` line ~127-131  
**Risk**: Graph driver failure does not prevent proposal.status="applied"

---

## Test Baseline

### Existing Test Suites

**Wave 1 Financial Tests**:
- `backend/tests/test_tabular_queries.py`: 17/17 PASSING
- Golden cases E01-E07: VERIFIED
- SQL injection safety: VERIFIED
- Version isolation: VERIFIED

**Wave 0 Security Tests**:
- `backend/tests/test_wave0_verification.py`: 5/5 PASSING
- Auth rejection on missing header: VERIFIED

**Regression Tests**:
- Scheme type distribution: 14/14 PASSING

**Total Passing**: 36/36 tests

### Missing Test Coverage (Batch 1 Targets)

- [ ] Negative auth tests on admin routes
- [ ] Four-eyes approval enforcement
- [ ] Pending patch exclusion from serving
- [ ] Graph driver failure handling
- [ ] Cross-tenant isolation

---

## Reproducibility Commands

### Restore Exact State

```bash
# Clone and checkout
git clone <repo-url> amc-clean
cd amc-clean
git checkout 06cf9755f4b3dde3e9a24a430973f4bf86ed711d

# Verify database
sha256sum backend/data/financial.db
# Expected: 3EAEB4CAB5464D2CA279BC7A8D742C923ED3F310FAB1ACD46FD0462B4FCDCACB

# Setup environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r backend/requirements.txt

# Run baseline tests
cd backend
pytest tests/test_tabular_queries.py -v
pytest tests/test_wave0_verification.py -v
```

### Verify Ingestion State

```bash
cd backend
python -c "
from app.tabular.repository import FinancialDataRepository
repo = FinancialDataRepository('data/financial.db')
print(f'Active version: {repo.get_active_version()}')
print(f'Source rows: {repo._count_rows(\"source_rows\")}')
print(f'NAV observations: {repo._count_rows(\"nav_observations\")}')
print(f'AAUM observations: {repo._count_rows(\"aaum_observations\")}')
"
```

**Expected Output**:
```
Active version: v1_baseline
Source rows: 16245
NAV observations: 14208
AAUM observations: 8178
```

---

## Audit Trail

**Freeze Performed By**: Kiro AI Agent  
**Freeze Date**: 2026-11-04  
**Purpose**: Wave 1.1 Batch 0+1 P0 Security Containment  
**Next Actions**: Implement W1.1-10, W1.1-11, W1.1-12 fixes
