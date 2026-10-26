# Migration Guide

**From**: `amc-context-engineering-poc-frontend-react` (Original)  
**To**: `amc-context-engineering-clean` (Refactored)

---

## What Changed?

### ✅ What Was Preserved
- ✅ All backend application code (`backend/app/`)
- ✅ All frontend application code (`mf-context-engine/src/`)
- ✅ Core functionality and features
- ✅ Configuration files (requirements.txt, package.json)
- ✅ Business logic and algorithms

### 🔄 What Was Reorganized
- 📁 **Documentation**: Consolidated from 10+ root-level docs → single `docs/` directory
- 📁 **Scripts**: All scripts moved to `scripts/` directory
- 📁 **Data**: Separated into `data/` directory
- 📄 **Root README**: Simplified to <300 lines with quick start focus

### ❌ What Was NOT Copied
- ❌ Data dumps (`.cypher`, `.json` dumps) - keep in original dir
- ❌ HTML visualization files - archived in original dir
- ❌ Deprecated Streamlit app - no longer needed
- ❌ Duplicate/redundant documentation
- ❌ Build artifacts (`__pycache__`, `node_modules`, `dist/`)
- ❌ Log files
- ❌ Nested `backend/backend/` redundancy

---

## Directory Structure Comparison

### Before (Original)
```
amc-context-engineering-poc-frontend-react/
├── backend/
│   ├── app/
│   ├── backend/              ← Nested redundancy
│   ├── requirements.txt
│   └── ...
├── mf-context-engine/
├── streamlit_app/            ← Deprecated
├── Docs/                     ← Comprehensive but heavy
├── PROJECT_OVERVIEW.md       ← 3000+ lines
├── README.md
├── REPAIR_ENGINE_*.md        ← 6 separate files
├── amc_master_full_dump.*    ← Data dumps at root
├── end_to_end_query_flow.html
├── run_project.bat
├── mock_run.bat
├── temp_test.bat             ← Multiple scripts
└── ... (50+ root-level items)
```

### After (Clean)
```
amc-context-engineering-clean/
├── backend/
│   ├── app/                  ← All core code
│   ├── scripts/              ← Backend scripts
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── mf-context-engine/
│   ├── src/                  ← All frontend code
│   ├── package.json
│   └── vite.config.js
├── docs/                     ← Single doc location
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── DEVELOPER_GUIDE.md
│   ├── API_REFERENCE.md
│   └── ... (organized by role)
├── scripts/                  ← Unified scripts
│   ├── start.bat             ← Single start script
│   └── setup.bat
├── data/                     ← Data files
├── tests/                    ← Integration tests
├── config/                   ← Configuration
├── README.md                 ← Simplified (<300 lines)
├── .env.example
├── .gitignore
└── MIGRATION_GUIDE.md        ← This file
```

---

## Step-by-Step Migration

### Phase 1: Verification (Do This First)

1. **Backup Original Directory**
   ```bash
   # Already done - original directory is untouched
   ```

2. **Verify Clean Directory Structure**
   ```bash
   cd "C:\Users\HemantMore\OneDrive - NuSummit Technologies Pvt Ltd\Desktop\amc-context-engineering-clean"
   dir
   ```

3. **Check Core Files Copied**
   ```bash
   # Verify backend
   dir backend\app
   
   # Verify frontend
   dir mf-context-engine\src
   ```

### Phase 2: Configuration

1. **Copy Environment Variables**
   ```bash
   # Copy and edit root .env
   copy .env.example .env
   
   # Copy and edit backend .env
   copy backend\.env.example backend\.env
   ```

2. **Transfer Custom Settings**
   - Open original `amc-context-engineering-poc-frontend-react\.env`
   - Copy your actual values to new `.env`
   - **Important**: Copy credentials, API keys, database URLs

3. **Verify Configuration**
   - Neo4j connection string
   - Groq API key
   - OpenAI API key (if used)
   - Any custom feature flags

### Phase 3: Setup

1. **Run Initial Setup**
   ```bash
   scripts\setup.bat
   ```

   This will:
   - Create Python virtual environment
   - Install Python dependencies
   - Install Node.js dependencies
   - Create necessary directories

2. **Copy Data Files (If Needed)**
   ```bash
   # If you have important data files in original directory:
   copy "..\amc-context-engineering-poc-frontend-react\backend\data.db" ".\backend\"
   ```

3. **Copy FAISS Indexes (If Exists)**
   ```bash
   # Copy pre-built FAISS indexes
   robocopy "..\amc-context-engineering-poc-frontend-react\backend\app\engine\faiss_indexes" ".\backend\app\engine\faiss_indexes" /E
   ```

### Phase 4: Testing

1. **Start Services**
   ```bash
   scripts\start.bat
   ```

2. **Verify Services**
   - Frontend: http://localhost:5173
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health

3. **Test Core Functionality**
   - Submit a test query
   - Check chat interface
   - Verify document ingestion
   - Test admin panel

4. **Run Tests**
   ```bash
   # Backend tests
   cd backend
   .venv\Scripts\activate
   pytest
   
   # Frontend tests (if available)
   cd mf-context-engine
   npm test
   ```

### Phase 5: Data Migration (Optional)

If you have production data in the original directory:

1. **Database Migration**
   ```bash
   # Copy SQLite database
   copy "..\amc-context-engineering-poc-frontend-react\backend\data.db" ".\backend\"
   ```

2. **Neo4j Data**
   - No migration needed (same Neo4j instance)
   - Or export/import if separate instance

3. **Uploaded Documents**
   ```bash
   # Copy uploaded files
   robocopy "..\amc-context-engineering-poc-frontend-react\backend\uploads" ".\backend\uploads" /E
   ```

---

## Rollback Plan

If you need to rollback to the original directory:

1. **Original directory is unchanged** - simply switch back
2. **Use original scripts**: `run_project.bat` in original dir
3. **No data loss** - all data remains in original location

---

## Post-Migration Checklist

- [ ] Environment files configured (.env, backend/.env)
- [ ] Python dependencies installed (backend/.venv)
- [ ] Node dependencies installed (mf-context-engine/node_modules)
- [ ] Neo4j connection verified
- [ ] Backend starts successfully (http://localhost:8000)
- [ ] Frontend starts successfully (http://localhost:5173)
- [ ] Test query executes successfully
- [ ] API documentation accessible (/docs)
- [ ] Health check passes (/health)
- [ ] Data files copied (if needed)
- [ ] FAISS indexes copied (if needed)
- [ ] Tests pass (pytest, npm test)

---

## Benefits of Clean Structure

### For Developers
- ✅ **Clear entry point**: Single README with quick start
- ✅ **Organized docs**: Find what you need in `docs/`
- ✅ **No confusion**: One start script, clear structure
- ✅ **Better Git**: Smaller repo, faster clones

### For Operations
- ✅ **Simplified deployment**: Clear dependencies
- ✅ **Better CI/CD**: Standard structure
- ✅ **Easier troubleshooting**: Logs in one place
- ✅ **Configuration management**: Clear separation

### For Architecture
- ✅ **Maintainability**: Easier to navigate
- ✅ **Scalability**: Room to grow
- ✅ **Documentation**: Role-based docs
- ✅ **Onboarding**: Faster new developer ramp-up

---

## Important Data Locations

### Original Directory (Keep For Reference)
```
amc-context-engineering-poc-frontend-react/
├── amc_master_full_dump.cypher     ← Neo4j dump
├── amc_master_full_dump.json       ← JSON dump
├── backend/data.db                  ← SQLite database
├── backend/audit_results.json       ← Audit data
└── Docs/                            ← Comprehensive documentation archive
```

**Recommendation**: Keep original directory as an **archive** for:
- Historical documentation
- Data dumps
- Audit trails
- Reference

---

## Support & Questions

If you encounter issues during migration:

1. Verify environment configuration
2. Check logs in `backend/logs/`

---

## Timeline Estimate

| Phase | Time Estimate |
|-------|---------------|
| Verification | 15 minutes |
| Configuration | 30 minutes |
| Setup | 20 minutes |
| Testing | 30 minutes |
| Data Migration (optional) | 15 minutes |
| **Total** | **1.5-2 hours** |

---

**Migration Date**: October 19, 2026  
**Original Directory**: Preserved at `amc-context-engineering-poc-frontend-react/`  
**Clean Directory**: `amc-context-engineering-clean/`
