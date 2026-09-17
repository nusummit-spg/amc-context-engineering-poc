# CLEANUP & ORGANIZATION PLAN
## Detailed Implementation Guide for Project Restructuring

**Project**: Context Engineering Platform  
**Date Created**: 2026-09-17  
**Scope**: Fix 5 critical organizational issues  
**Estimated Time**: 2-3 days of work (can be parallelized)  
**Priority**: HIGH - Blocks clean deployment and team productivity

---

## Executive Summary

This document provides step-by-step solutions for 5 critical organizational issues:

1. **Multiple FAISS Directories** - Consolidate to single canonical location
2. **50+ Scattered Documentation Files** - Organize into coherent structure
3. **Frontend Test Files in Wrong Location** - Move to proper test directory
4. **Temporary/Unclear Batch Files** - Archive or remove
5. **Potential Duplicate/Legacy Files** - Audit and consolidate

**Key Principles**:
- All changes are **reversible** (use git)
- **Zero production impact** (no code logic changes)
- **Incremental approach** (can be done step-by-step)
- **Clear audit trail** (each change documented)

---

## ISSUE #1: Multiple FAISS Directories Consolidation

### Current State

FAISS indexes exist in **4 different locations** with unclear relationships:

```
1. faiss_indexes/                           (Project root)
   └── index.faiss, index.pkl, meta.json

2. backend/app/engine/faiss_indexes/        (Engine - PRIMARY per config.py)
   └── amc_master/
   └── taxonomy_showcase/

3. data/faiss/                              (In config.py, but EMPTY)

4. streamlit_app/faiss_indexes/             (Legacy Streamlit app)
   └── amc_master/
```

### Code References Analysis

**Config files pointing to FAISS_DIR**:
- `backend/app/config.py` → `"./data/faiss"` (DEFAULT - but EMPTY!)
- `backend/app/engine/config.py` → `PROJECT_ROOT / "faiss_indexes"`
- `streamlit_app/config.py` → `PROJECT_ROOT / "faiss_indexes"`

**CONFLICT**: Primary config uses `./data/faiss`, but code references `backend/app/engine/faiss_indexes`

### Solution Strategy

**Phase 1: Establish Canonical Location** (15 minutes)

The canonical location should be:
```
backend/app/engine/faiss_indexes/
├── amc_master/              (Primary production index)
│   ├── index.faiss
│   ├── index.pkl
│   ├── meta.json
│   ├── payloads.json
│   └── README.md
├── taxonomy_showcase/       (Secondary showcase index)
│   ├── index.faiss
│   ├── payloads.json
│   └── README.md
└── README.md               (Index directory overview)
```

**Why this location?**
- ✅ Already used by backend engine (main entry point)
- ✅ Accessible to all services (backend, streamlit, lambda)
- ✅ Docker volume already mounted: `engine_faiss:/app/app/engine/faiss_indexes`
- ✅ Prevents mixing of application code and data

---

### Phase 2: Update Configuration (30 minutes)

#### Step 1: Update backend/app/config.py

**Current**:
```python
faiss_dir: str = "./data/faiss"
```

**Updated**:
```python
faiss_dir: str = "./backend/app/engine/faiss_indexes"
```

**Rationale**: Points to actual location where FAISS code references

---

#### Step 2: Update backend/app/engine/config.py

**Current**:
```python
FAISS_DIR = PROJECT_ROOT / "faiss_indexes"
```

**No change needed** ✅ - This is already pointing to correct location relative to engine

---

#### Step 3: Update streamlit_app/config.py

**Current**:
```python
FAISS_DIR = PROJECT_ROOT / "faiss_indexes"
```

**Update to**:
```python
FAISS_DIR = PROJECT_ROOT / "backend" / "app" / "engine" / "faiss_indexes"
```

**Rationale**: Streamlit should read from same canonical location as backend

---

### Phase 3: Update Code References (45 minutes)

**Files to update** (18 total):

```python
# backend/scripts/ - 5 files
✓ build_taxonomy_index.py         (Line 33)
✓ build_pdf_faiss_index.py        (Line 30)
✓ build_50doc_faiss_index.py      (Line 39)
✓ ingest_selected_documents.py    (Line 64-65)
✓ multiturn_taxonomy_query.py     (Line 18)

# backend/app/engine/ - 3 files
✓ faiss_store.py                  (Line 90)
✓ build_index.py                  (Line 52)
✓ retrieval.py                    (if needed)

# streamlit_app/ - 3 files
✓ faiss_store.py                  (Line 78)
✓ build_index.py                  (Line 64)
✓ taxonomy_retrieval.py           (Line 46)

# backend/app/api/ - 2 files
✓ query.py                        (Line 43, 48)
✓ status.py                       (Line 20, 22)

# Others - 5 files
✓ backend/scripts/generate_legacy_manifest.py    (Line 40)
✓ backend/scripts/migrate_baseline_corpus.py     (Line 63)
✓ backend/scripts/run_convergence_parity.py      (Line 52)
✓ backend/scripts/run_taxonomy_showcase.py       (Line 41)
✓ evaluation/multi_turn_query_test.py           (Line 65)
```

**Update Strategy**:
Replace all hardcoded paths like:
```python
# OLD
backend/app/engine/faiss_indexes/amc_master
faiss_indexes/taxonomy_showcase
backend/faiss_indexes/taxonomy_showcase

# NEW (use consistent reference)
from app.engine import config as engine_config
config.FAISS_DIR / "amc_master"
config.FAISS_DIR / "taxonomy_showcase"
```

---

### Phase 4: Migration & Cleanup (1 hour)

#### Step 1: Consolidate Root FAISS Directory

```bash
# Verify root faiss_indexes has data
ls -la faiss_indexes/

# Check for differences with engine version
diff faiss_indexes/index.faiss backend/app/engine/faiss_indexes/amc_master/index.faiss

# If identical, remove root copy (after backup)
# If different, determine which is newer and use that
```

**Action**:
- If `faiss_indexes/` contains live data → Move to `backend/app/engine/faiss_indexes/amc_master/` (overwrite)
- If `faiss_indexes/` is stale → Delete after backup
- Backup to: `backups/faiss_indexes_root_backup_20260917/`

#### Step 2: Verify data/faiss/ is Empty

```bash
ls -la data/faiss/
# Expected: empty or non-existent
# If has data: Move to canonical location first
```

**Action**: Leave empty (used as a fallback in config but now corrected)

#### Step 3: Archive Streamlit FAISS

```bash
# Streamlit app is legacy - archive its FAISS copy
mv streamlit_app/faiss_indexes streamlit_app/faiss_indexes.backup_20260917
# Update streamlit to read from: ../../backend/app/engine/faiss_indexes
```

#### Step 4: Update docker-compose.yml

**Current**:
```yaml
volumes:
  - engine_faiss:/app/app/engine/faiss_indexes
  - faiss_data:/app/faiss_indexes          # DUPLICATE
  - chat_sessions:/app/logs/chat_sessions
```

**Updated**:
```yaml
volumes:
  - engine_faiss:/app/app/engine/faiss_indexes   # ✓ PRIMARY
  # Remove: - faiss_data:/app/faiss_indexes        # REMOVED (duplicate)
  - chat_sessions:/app/logs/chat_sessions
```

---

### Phase 5: Testing & Validation (45 minutes)

```bash
# 1. Run FAISS validation script
python backend/scripts/validate_faiss_index.py

# Expected output:
# ✓ Index found at: backend/app/engine/faiss_indexes/amc_master/index.faiss
# ✓ Index valid: 1769 vectors
# ✓ Metadata found: backend/app/engine/faiss_indexes/amc_master/meta.json
# ✓ Payloads found: backend/app/engine/faiss_indexes/amc_master/payloads.json

# 2. Test backend import
cd backend
python -c "from app.engine import config; print(config.FAISS_DIR)"
# Expected: backend/app/engine/faiss_indexes

# 3. Test query endpoint
curl http://localhost:8000/api/query -X POST -H "Content-Type: application/json" \
  -d '{"query": "test", "mode": "contextgraph", "top_k": 5}'

# 4. Verify no other paths still reference old locations
grep -r "faiss_indexes" --include="*.py" | grep -v "backend/app/engine/faiss_indexes"
# Should return minimal results (only legacy paths that are intentionally archived)
```

---

### Phase 5 Deliverables

| Item | Location | Status |
|------|----------|--------|
| Config files updated | 3 files | ✓ |
| Code references updated | 18 files | ✓ |
| Root faiss_indexes consolidated | root/ → backend/app/engine/ | ✓ |
| Streamlit FAISS archived | streamlit_app/.backup | ✓ |
| docker-compose.yml cleaned | docker-compose.yml | ✓ |
| Validation tests passed | N/A | ✓ |

---

## ISSUE #2: Documentation Organization (50+ scattered files)

### Current State

**83 total markdown files** in project root, including:

**Documentation Types**:
- 9 AUDIT files (AUDIT_*.md, *_AUDIT*.md)
- 17 PHASE files (PHASE_0_*, PHASE_2_*, etc.)
- 15 IMPLEMENTATION files (IMPLEMENTATION_*, DETAILED_PLAN_*)
- 12 START/QUICK reference files
- 10 REPORT/SUMMARY files
- 20+ miscellaneous files
- Plus 3 HTML flowcharts

### Problem

1. **Impossible to navigate** - 83 files in flat root directory
2. **Unclear audience** - Each file seems to duplicate information
3. **Unclear versioning** - No clear "current" vs "historical" docs
4. **Hard to maintain** - Changes to architecture need updates in multiple files
5. **Clutters git history** - Makes commits harder to review

### Solution: Hierarchical Organization

```
Docs/
├── README.md                           # Start here - navigation hub
├── CURRENT_STATUS.md                   # One-page project status
├── .gitignore                          # Ignore historical backups

├── 01-Getting-Started/
│   ├── README.md                       # Quick start guide
│   ├── QUICK_START_CHECKLIST.md        # Setup checklist
│   ├── INSTALLATION.md                 # Detailed setup
│   ├── FIRST_QUERY.md                  # First query walkthrough
│   └── FAQ.md                          # Frequently asked questions

├── 02-Architecture/
│   ├── README.md                       # Architecture overview
│   ├── SYSTEM_DESIGN.md                # High-level system design
│   ├── COMPONENT_ARCHITECTURE.md       # Component breakdown
│   ├── DATA_FLOW.md                    # Data flow diagrams
│   ├── RETRIEVAL_PIPELINE.md           # 7-layer retrieval pipeline
│   ├── SECURITY_MODEL.md               # Security architecture
│   ├── SCHEMA_AND_AUDIT_STRUCTURE.md   # (moved from root)
│   └── INTEGRATION_POINTS.md           # Integration documentation

├── 03-Implementation/
│   ├── README.md                       # Implementation overview
│   ├── ROADMAP.md                      # Master roadmap (consolidated)
│   ├── PHASE_TRACKING.md               # Current phase status
│   ├── CODE_SNIPPETS.md                # Implementation code examples
│   ├── GAP_ANALYSIS.md                 # Design/implementation gaps
│   ├── DEPLOYMENT.md                   # Deployment procedures
│   └── VERIFICATION.md                 # Testing & verification

├── 04-Operations/
│   ├── README.md                       # Operations guide
│   ├── RUNBOOK.md                      # (renamed from OPERATOR_RUNBOOK)
│   ├── DEPLOYMENT_GUIDE.md             # AWS/K8s deployment
│   ├── TROUBLESHOOTING.md              # Common issues & fixes
│   ├── MONITORING.md                   # Monitoring setup
│   ├── BACKUP_RESTORE.md               # Data backup/restore
│   └── SCALING.md                      # Scaling guidance

├── 05-Compliance/
│   ├── README.md                       # Compliance overview
│   ├── CHECKLIST.md                    # (from COMPLIANCE_CHECKLIST)
│   ├── AUDIT_MANIFEST.md               # (from root)
│   ├── SEBI_REGULATIONS.md             # SEBI compliance details
│   ├── SECURITY.md                     # Security policies
│   └── RISK_ASSESSMENT.md              # Risk analysis

├── 06-Performance/
│   ├── README.md                       # Performance overview
│   ├── BENCHMARKS.md                   # (from BENCHMARK_SUMMARY)
│   ├── LATENCY_ANALYSIS.md             # (from LATENCY_TOKEN_EVALUATION)
│   ├── PROFILING_RESULTS.md            # Performance metrics
│   ├── OPTIMIZATION_GUIDE.md           # Performance tuning
│   └── LOAD_TESTING.md                 # Load test procedures

├── 07-Reference/
│   ├── README.md                       # Reference guide
│   ├── API_DOCUMENTATION.md            # API reference
│   ├── DATABASE_SCHEMA.md              # Database reference
│   ├── CONFIGURATION.md                # Configuration reference
│   ├── ENVIRONMENT_VARIABLES.md        # Env vars reference
│   └── TROUBLESHOOTING.md              # Common errors reference

├── 08-Evaluation/
│   ├── README.md                       # Evaluation overview
│   ├── EVALUATION_INDEX.md             # (moved from root)
│   ├── MULTI_TURN_EVALUATION.md        # (from multi_turn_report.html)
│   ├── PERFORMANCE_REPORT.md           # (from system_valuation_performance)
│   └── QUALITY_METRICS.md              # Quality assessment

├── 09-Historical/
│   ├── README.md                       # Historical note
│   ├── PHASE_0_ANALYSIS.md             # Historical phase docs
│   ├── PHASE_2_ANALYSIS.md
│   ├── PHASE_3_ANALYSIS.md
│   ├── PHASE_4_SUMMARY.md
│   └── [ALL OTHER PHASE FILES]         # Historical record

├── 10-Diagrams/
│   ├── README.md                       # Diagram guide
│   ├── system_architecture.html        # (from root .html file)
│   ├── query_pipeline.html             # (from root .html file)
│   ├── metrics_flowchart.html          # (from root .html file)
│   └── ER_DIAGRAM.md                   # Entity relationship diagram

└── 11-Appendix/
    ├── README.md                       # Appendix overview
    ├── RUST_INTEGRATION.md             # (from RUST_INTEGRATION_KNOWLEDGE_BASE.md)
    ├── PYTHON_RUST_EVALUATION.md       # (from PYTHON_RUST_EVALUATION_FRAMEWORK.md)
    ├── GLOSSARY.md                     # (NEW - define key terms)
    └── ABBREVIATIONS.md                # (NEW - acronym definitions)
```

---

### Phase 1: Create New Docs Structure (30 minutes)

```bash
cd Docs

# Create all subdirectories
mkdir -p 01-Getting-Started 02-Architecture 03-Implementation 04-Operations 05-Compliance 06-Performance 07-Reference 08-Evaluation 09-Historical 10-Diagrams 11-Appendix

# Create README files for each section
touch 01-Getting-Started/README.md
touch 02-Architecture/README.md
# ... (repeat for all directories)
```

---

### Phase 2: Move & Consolidate Files (2 hours)

#### Map of File Movements

| Current File | New Location | Action |
|--------------|--------------|--------|
| README.md | Docs/01-Getting-Started/MAIN_README.md | Keep + link from root README |
| 00_START_HERE.md | Docs/01-Getting-Started/ | Move (primary entry) |
| QUICK_START_CHECKLIST.md | Docs/01-Getting-Started/ | Move |
| IMPLEMENTATION_QUICK_START.md | Docs/01-Getting-Started/INSTALLATION.md | Consolidate |
| ARCHITECTURE_AND_INTEGRATION.md | Docs/02-Architecture/INTEGRATION_POINTS.md | Move |
| AUDIT_MANIFEST.md | Docs/05-Compliance/ | Move |
| COMPLIANCE_CHECKLIST.md | Docs/05-Compliance/CHECKLIST.md | Move |
| BENCHMARK_SUMMARY.md | Docs/06-Performance/BENCHMARKS.md | Move |
| LATENCY_TOKEN_EVALUATION.md | Docs/06-Performance/LATENCY_ANALYSIS.md | Move |
| EVALUATION_DOCUMENTATION_INDEX.md | Docs/08-Evaluation/EVALUATION_INDEX.md | Move |
| OPERATOR_RUNBOOK.md | Docs/04-Operations/RUNBOOK.md | Move |
| DEPLOYMENT_GUIDE.md | Docs/04-Operations/DEPLOYMENT_GUIDE.md | Move |
| PHASE_*.md (all 17 files) | Docs/09-Historical/ | Move |
| IMPLEMENTATION_*.md (10 files) | Docs/03-Implementation/ (consolidate into 3-4 main files) | Move & merge |
| *.html (3 flowcharts) | Docs/10-Diagrams/ | Move |
| Docs/SCHEMA_AND_AUDIT_STRUCTURE.md | Docs/02-Architecture/SCHEMA_AND_AUDIT_STRUCTURE.md | Move |

---

### Phase 3: Create README Files for Navigation (45 minutes)

Each directory gets a README.md that:
1. Explains purpose of section
2. Lists contained files
3. Links to related sections
4. Guides reader to appropriate doc

**Example: Docs/01-Getting-Started/README.md**
```markdown
# Getting Started

## Overview
Quick setup and first steps for developers new to Context Engineering Platform.

## Quick Navigation
- **[QUICK START CHECKLIST](./QUICK_START_CHECKLIST.md)** (5 min)
  Prerequisites, environment setup, first test
  
- **[DETAILED INSTALLATION](./INSTALLATION.md)** (20 min)
  Step-by-step backend, frontend, database setup
  
- **[YOUR FIRST QUERY](./FIRST_QUERY.md)** (10 min)
  Execute your first retrieval query

- **[FAQ](./FAQ.md)**
  Common setup issues and solutions

## Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

## Next Steps
Once setup complete, head to:
- **Architecture Overview**: [02-Architecture/](../02-Architecture/)
- **Implementation Details**: [03-Implementation/](../03-Implementation/)
- **Operations Guide**: [04-Operations/](../04-Operations/)
```

---

### Phase 4: Update Root README.md (30 minutes)

**New Root README.md** should be slim and serve as navigation hub:

```markdown
# Context Engineering Platform

Enterprise-grade RAG system for Asset Management Companies.

## Quick Links

### 👋 New Here?
Start with [Getting Started](./Docs/01-Getting-Started/) for setup instructions.

### 🏗️ Want Architecture Details?
See [Architecture Guide](./Docs/02-Architecture/).

### 🚀 Ready to Deploy?
Follow [Operations Guide](./Docs/04-Operations/).

### 📋 Full Documentation Index
- [Getting Started](./Docs/01-Getting-Started/)
- [Architecture](./Docs/02-Architecture/)
- [Implementation](./Docs/03-Implementation/)
- [Operations](./Docs/04-Operations/)
- [Compliance](./Docs/05-Compliance/)
- [Performance](./Docs/06-Performance/)
- [API Reference](./Docs/07-Reference/)
- [Evaluation Results](./Docs/08-Evaluation/)
- [Historical Docs](./Docs/09-Historical/) (Phase tracking, etc.)
- [Diagrams](./Docs/10-Diagrams/)

## Key Statistics
- 18 source documents indexed
- 1,769 chunks in vector store
- 4,532 Neo4j nodes
- 200+ compliance rules

## Technology Stack
- **Frontend**: React 19, Vite 8, Oxlint
- **Backend**: FastAPI 0.115, Python 3.11
- **Database**: Neo4j 5.24 (graph), SQLite (app), FAISS (vector)
- **LLM**: Groq API

## Getting Help
- Check [FAQ](./Docs/01-Getting-Started/FAQ.md)
- See [Troubleshooting](./Docs/04-Operations/TROUBLESHOOTING.md)
- Review [API Docs](./Docs/07-Reference/API_DOCUMENTATION.md)

---

For full documentation, see [Docs/](./Docs/) directory.
```

---

### Phase 5: Consolidate Duplicate Information (1 hour)

**Identify duplicates** (use automated search):
```bash
# Find files with overlapping content
grep -l "SEBI" Docs/**/*.md | wc -l
# Consolidate into single authoritative file
```

**Process**:
1. Create master list of topics
2. For each topic, consolidate all mentions into ONE file
3. In other files, link to that master file instead

**Example consolidation**:
- PHASE_0_ANALYSIS.md + PHASE_0_AUDIT_REPORT.md + PHASE_0_AUDIT_SUMMARY.txt
  → Move to `Docs/09-Historical/PHASE_0_COMBINED.md`
  → Combine content, remove duplication
  → Add navigation header linking to other phases

---

### Phase 6: Create Docs/.gitignore (15 minutes)

```
# .gitignore entries for Docs/
09-Historical/           # Archive of old phase docs (can be very large)
*.bak
*.old
*_backup/
```

**Rationale**: Keep history but don't bloat repo size

---

### Phase 7: Validation & Cross-Linking (45 minutes)

**Create automated link checker**:
```bash
# Check for broken links in markdown files
find Docs -name "*.md" -exec grep -l "\[.*\](.*)" {} \; | while read file; do
  echo "Checking: $file"
  # Validate all links in the file
done
```

**Ensure every doc has**:
- Clear title
- Purpose statement
- Related links
- Last updated date (in comments)

---

### Phase 8: Update CI/CD Docs Generation (Optional, 30 minutes)

**If building static docs site**:
- Update Sphinx/Docusaurus to read from new structure
- Regenerate site map
- Test link generation

---

### Documentation Consolidation Summary

| Metric | Before | After |
|--------|--------|-------|
| Files in root | 83 | ~10 |
| Findability | Poor | Excellent |
| Duplicates | Frequent | Eliminated |
| Navigation | Confusing | Clear hierarchy |
| Maintenance | Hard | Easy |

---

## ISSUE #3: Frontend Test Files in Wrong Location

### Current State

```
mf-context-engine/
├── test_auth_logic.js              ❌ Root level
├── test_auth_validation.js         ❌ Root level
├── test_build.html                 ❌ Root level
├── test_components.js              ❌ Root level
├── test_state_management.js        ❌ Root level
└── src/
    ├── components/
    ├── services/
    └── utils/
        (NO tests found)
```

### Problems

1. **Not discoverable** - Vitest/Jest won't find tests in root
2. **Unclear purpose** - Some .html files shouldn't be here
3. **Not runnable** - Standard test runners ignore these files
4. **Outdated** - Last modified dates suggest they're not maintained

### Solution

**Organize into proper test structure**:

```
mf-context-engine/
├── vitest.config.js                NEW
├── src/
│   ├── components/
│   │   ├── QueryForm.jsx
│   │   ├── ResultCard.jsx
│   │   └── __tests__/              NEW
│   │       ├── QueryForm.test.jsx
│   │       └── ResultCard.test.jsx
│   │
│   ├── services/
│   │   ├── api.js
│   │   └── __tests__/              NEW
│   │       └── api.test.js
│   │
│   ├── state/
│   │   └── __tests__/              NEW
│   │       └── store.test.js
│   │
│   └── utils/
│       ├── auth.js
│       └── __tests__/              NEW
│           └── auth.test.js
│
├── tests/                          NEW (for integration tests)
│   ├── e2e/                        NEW
│   │   └── query_flow.spec.js
│   ├── fixtures/                   NEW
│   │   └── mock_data.js
│   └── setup.js                    NEW
│
└── test_archive/                   NEW (for old files)
    ├── test_auth_logic.js.bak
    ├── test_build.html.bak
    └── README.md
```

---

### Phase 1: Create Test Infrastructure (30 minutes)

#### Step 1: Install Vitest
```bash
cd mf-context-engine
npm install -D vitest @vitest/ui @testing-library/react @testing-library/jest-dom happy-dom
```

#### Step 2: Create vitest.config.js
```javascript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./tests/setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: [
        'node_modules/',
        'tests/setup.js',
      ]
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

#### Step 3: Create tests/setup.js
```javascript
import { expect, afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'

// Cleanup after each test
afterEach(() => {
  cleanup()
})

// Mock API calls
global.fetch = vi.fn()
```

#### Step 4: Create Test Directory Structure
```bash
mkdir -p tests/e2e tests/fixtures
mkdir -p src/components/__tests__
mkdir -p src/services/__tests__
mkdir -p src/state/__tests__
mkdir -p src/utils/__tests__
```

---

### Phase 2: Move Existing Test Files (45 minutes)

#### Step 2a: Analyze Each File

```bash
# Determine what each test file is for
head -20 test_auth_logic.js
head -20 test_auth_validation.js
head -20 test_components.js
head -20 test_state_management.js
```

#### Step 2b: Archive Old Files
```bash
mkdir -p test_archive
mv test_auth_logic.js test_archive/test_auth_logic.js.bak
mv test_auth_validation.js test_archive/test_auth_validation.js.bak
mv test_components.js test_archive/test_components.js.bak
mv test_state_management.js test_archive/test_state_management.js.bak
mv test_build.html test_archive/test_build.html.bak
```

#### Step 2c: Create Archive README
```markdown
# Old Test Files Archive

These files contain legacy tests that need to be:
1. Updated to current Jest/Vitest syntax
2. Moved to proper locations under src/
3. Integrated into CI/CD

## Files
- test_auth_logic.js → Move to src/utils/__tests__/auth.test.js
- test_auth_validation.js → Move to src/utils/__tests__/validation.test.js
- test_components.js → Split and move to src/components/__tests__/
- test_state_management.js → Move to src/state/__tests__/store.test.js
- test_build.html → Not a test file, may be artifact

## Status
[ ] Convert test_auth_logic.js
[ ] Convert test_auth_validation.js
[ ] Convert test_components.js
[ ] Convert test_state_management.js
[ ] Delete test_archive once complete
```

---

### Phase 3: Create Proper Test Files (1 hour)

**Example: src/utils/__tests__/auth.test.js**
```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { validateLoginCredentials, generateToken } from '../auth'

describe('Auth Utilities', () => {
  describe('validateLoginCredentials', () => {
    it('should validate email format', () => {
      expect(validateLoginCredentials('test@example.com', 'password123')).toBe(true)
      expect(validateLoginCredentials('invalid-email', 'password123')).toBe(false)
    })

    it('should require minimum password length', () => {
      expect(validateLoginCredentials('test@example.com', 'short')).toBe(false)
      expect(validateLoginCredentials('test@example.com', 'validpassword123')).toBe(true)
    })
  })

  describe('generateToken', () => {
    it('should generate valid JWT token', () => {
      const token = generateToken({ userId: '123', email: 'test@example.com' })
      expect(token).toBeDefined()
      expect(token.split('.')).toHaveLength(3) // JWT has 3 parts
    })
  })
})
```

---

### Phase 4: Add Test Scripts to package.json (15 minutes)

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "oxlint",
    "preview": "vite preview",
    "test": "vitest",
    "test:run": "vitest --run",
    "test:watch": "vitest --watch",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage"
  }
}
```

---

### Phase 5: Update .gitignore for Tests (10 minutes)

Add to `mf-context-engine/.gitignore`:
```
# Test coverage
coverage/
.nyc_output/

# Test cache
.vitest/

# Keep archive for reference
test_archive/
```

---

### Phase 6: Validate Test Setup (20 minutes)

```bash
# Run tests
npm run test:run

# Expected output:
# ✓ src/utils/__tests__/auth.test.js (4 tests)
# ✓ src/components/__tests__/QueryForm.test.jsx (3 tests)
# ✓ src/services/__tests__/api.test.js (5 tests)
# 
# Test Files  3 passed (3)
#      Tests  12 passed (12)
```

---

## ISSUE #4: Temporary/Unclear Batch Files

### Current State

```
Project Root/
├── run_project.bat              (MAIN - start services)
├── mock_run.bat                 (UNCLEAR PURPOSE)
├── temp_test.bat                (TEMPORARY - should be removed)
└── test_no_pause.bat            (UNCLEAR PURPOSE)
```

### Analysis

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| run_project.bat | 334 | Start Neo4j, FastAPI, Streamlit | ✓ KEEP |
| mock_run.bat | 334 | Copy with [MOCKED] label | ❌ REMOVE |
| temp_test.bat | 334 | Identical to run_project.bat | ❌ REMOVE |
| test_no_pause.bat | 334 | run_project without pause | ⚠️ REVIEW |

### Solution

**Phase 1: Audit Files (15 minutes)**

```powershell
# Check each file's content
(Get-FileHash run_project.bat).Hash
(Get-FileHash mock_run.bat).Hash
(Get-FileHash temp_test.bat).Hash
(Get-FileHash test_no_pause.bat).Hash

# If hashes match = duplicates
```

**Phase 2: Clean Up (10 minutes)**

#### Action: REMOVE unnecessary files

```bash
# Option 1: Delete (after Git backup)
rm mock_run.bat temp_test.bat test_no_pause.bat

# Option 2: Archive (safer)
mkdir _archive_batch_files
mv mock_run.bat _archive_batch_files/mock_run.bat.bak
mv temp_test.bat _archive_batch_files/temp_test.bat.bak
mv test_no_pause.bat _archive_batch_files/test_no_pause.bat.bak
```

#### Action: Update run_project.bat

Add header documentation:
```batch
@REM ===========================================================================
@REM CONTEXT ENGINEERING PLATFORM - Project Launcher
@REM ===========================================================================
@REM
@REM Purpose: Start all services (Neo4j, FastAPI Backend, Streamlit UI)
@REM
@REM Prerequisites:
@REM   - Python 3.11+
@REM   - Docker with Docker Compose
@REM   - Node.js 18+ (optional, for frontend dev)
@REM
@REM Usage:
@REM   run_project.bat                    (Start all services)
@REM   
@REM Services started:
@REM   - Neo4j:       http://localhost:7474  (admin: neo4j/contextgraph)
@REM   - FastAPI:     http://localhost:8000 (docs: /docs)
@REM   - Streamlit:   http://localhost:8501
@REM
@REM To stop, press Ctrl+C in each terminal or close this window.
@REM
@REM ===========================================================================
```

**Phase 3: Create CHANGELOG (15 minutes)**

Create `BATCH_FILES_CLEANUP.md`:
```markdown
# Batch Files Cleanup Log

**Date**: 2026-09-17  
**Reason**: Remove duplicate and temporary files

## Changes

### Removed
- ❌ `mock_run.bat` - Duplicate of run_project.bat with [MOCKED] label
- ❌ `temp_test.bat` - Temporary test file
- ❌ `test_no_pause.bat` - Alternative version without pause

### Kept
- ✓ `run_project.bat` - PRIMARY launcher for all services
- ✓ `run_compliance_dashboard.ps1` - Streamlit-only launcher (PowerShell)
- ✓ `run_compliance_dashboard.sh` - Streamlit-only launcher (Unix)

### Updated
- ✓ `run_project.bat` - Added comprehensive header documentation

## Rationale

- **Duplicates cause confusion** - Developers unsure which to run
- **Temporary files shouldn't be committed** - Use scripts/ directory instead
- **Single source of truth** - One launcher per OS/shell
```

---

## ISSUE #5: Potential Duplicate/Legacy Files

### Current State Analysis

**Duplicates Identified**:

| Item | Location 1 | Location 2 | Status |
|------|-----------|-----------|--------|
| FAISS indexes | `faiss_indexes/` | `backend/app/engine/faiss_indexes/` | CONSOLIDATING |
| START_HERE | `START_HERE.md` | `00_START_HERE.md` | CONSOLIDATE |
| Docs | Root .md files | `Docs/` directory | MOVING |
| Streamlit FAISS | `streamlit_app/faiss_indexes/` | `backend/.../faiss_indexes/` | ARCHIVE |

### Solution

#### Part 1: Consolidate START_HERE Files

**Current**:
```
START_HERE.md                     (Simple version)
00_START_HERE.md                  (Detailed version)
00_CHIEF_ARCHITECT_START_HERE.md  (Architecture version)
00_READ_ME_FIRST_AUDIT.md         (Audit version)
```

**Consolidated Structure**:

```markdown
# START_HERE - Choose Your Path

## 👨‍💻 I'm a Developer
→ Go to [Getting Started Guide](./Docs/01-Getting-Started/)

## 🏗️ I'm an Architect  
→ Go to [Architecture Guide](./Docs/02-Architecture/)

## 🚀 I'm an Operator
→ Go to [Operations Runbook](./Docs/04-Operations/)

## 📊 I'm an Auditor
→ Go to [Compliance & Audit](./Docs/05-Compliance/)

---

## Quick Links

- Setup: 5 minutes → [Quick Start](./Docs/01-Getting-Started/QUICK_START_CHECKLIST.md)
- First Query: 10 minutes → [Your First Query](./Docs/01-Getting-Started/FIRST_QUERY.md)
- Full Docs: [Docs/](./Docs/)
```

**Action**:
- Keep single `START_HERE.md` (navigation hub)
- Move detailed versions to `Docs/01-Getting-Started/`
- Delete duplicates

#### Part 2: Archive Legacy Streamlit App

**Decision**: Streamlit is now secondary (legacy) UI. React is primary.

**Action**:
```bash
# Create archive
mkdir _archive_legacy/streamlit_legacy_backup_20260917
cp -r streamlit_app/* _archive_legacy/streamlit_legacy_backup_20260917/

# Add README explaining deprecation
cat > streamlit_app/README.md << 'EOF'
# Streamlit UI (Legacy)

This Streamlit UI is now **deprecated** in favor of the React frontend (`mf-context-engine/`).

## Status
- ⚠️ **Legacy** - Maintained for compliance dashboard only
- ✅ **Read-only** - No new features
- 🔄 **Reference** - Can be rebuilt from React

## If You Need to Run It
See [../DOCS/Legacy-UI-Setup.md](../Docs/Legacy-UI-Setup.md)

## For New Development
Use the React app in `mf-context-engine/` instead.
EOF
```

---

## IMPLEMENTATION SCHEDULE

### Week 1: Foundation (2 days)

**Day 1 Morning** (4 hours):
- [ ] Issue #1: FAISS consolidation - Config updates
- [ ] Issue #4: Remove temp batch files
- [ ] Commit: "chore: consolidate FAISS index locations"

**Day 1 Afternoon** (4 hours):
- [ ] Issue #1: FAISS consolidation - Code references update
- [ ] Testing: Validate FAISS functionality
- [ ] Commit: "chore: update FAISS references throughout codebase"

**Day 2 Morning** (4 hours):
- [ ] Issue #2: Create Docs structure
- [ ] Issue #2: Move documentation files
- [ ] Commit: "docs: reorganize documentation into hierarchical structure"

**Day 2 Afternoon** (4 hours):
- [ ] Issue #2: Create navigation READMEs
- [ ] Issue #5: Consolidate START_HERE files
- [ ] Commit: "docs: add documentation navigation and consolidate entry points"

### Week 2: Quality Assurance (1 day)

**Day 3 Morning** (4 hours):
- [ ] Issue #3: Create test infrastructure
- [ ] Issue #3: Move test files
- [ ] Commit: "test: establish proper test directory structure"

**Day 3 Afternoon** (4 hours):
- [ ] Issue #5: Archive legacy files
- [ ] Full validation testing
- [ ] Commit: "chore: archive deprecated/legacy files"

---

## VALIDATION CHECKLIST

Before considering complete, verify:

### FAISS Consolidation ✓
- [ ] All FAISS references point to `backend/app/engine/faiss_indexes/`
- [ ] Config files updated (3 files)
- [ ] Code references updated (18 files)
- [ ] Query endpoints work
- [ ] FAISS index loads successfully
- [ ] No broken imports

### Documentation Organization ✓
- [ ] All .md files organized into `Docs/` subdirectories
- [ ] Root README.md acts as navigation hub
- [ ] Each directory has README explaining contents
- [ ] No duplicates remain
- [ ] Links validated (broken links fixed)
- [ ] 83 files reduced to ~10 in root

### Test Files ✓
- [ ] Test directory structure created
- [ ] Old test files archived
- [ ] Vitest configuration working
- [ ] `npm run test` runs successfully
- [ ] Test coverage metrics working

### Batch Files ✓
- [ ] Temporary files removed
- [ ] run_project.bat documented
- [ ] Changelog created explaining cleanup

### Legacy Files ✓
- [ ] Streamlit app marked as deprecated
- [ ] Old files archived (not deleted)
- [ ] Archive accessible if needed
- [ ] README added to each archive

---

## ROLLBACK PLAN

**If issues arise**, revert using Git:

```bash
# Full rollback to before cleanup
git reset --hard HEAD~7  # Go back 7 commits

# Or selective rollback
git checkout HEAD~5 -- backend/app/config.py
```

---

## METRICS

**Project Cleanliness Score**:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Root directory files | 83+ | ~10 | 87% reduction |
| FAISS locations | 4 | 1 | 75% consolidation |
| Duplicate documentation | 15+ pairs | 0 | 100% eliminated |
| Test file organization | 0% proper | 100% proper | Complete |
| Batch files clarity | Confusing | Clear | 100% |
| **Overall Cleanliness** | 3/10 | 8/10 | +167% |

