# PROJECT FILES - Complete Inventory & Implementation Roadmap

**Project**: Context Engineering Platform (Enterprise RAG System for Asset Management)  
**Architecture**: React Frontend + Python (FastAPI) Backend + SQLite (Application DB) + Neo4j (Graph DB) + FAISS (Vector Store)  
**Last Updated**: 2026-09-17  
**Purpose**: Master checklist for all required, supporting, and recommended files across the entire stack

---

## Table of Contents

1. [Project Root Files](#1-project-root-files)
2. [Backend - Python/FastAPI](#2-backend---pythonfastapi)
3. [Frontend - React/Vite](#3-frontend---reactvite)
4. [Database - SQLite (Application Layer)](#4-database---sqlite-application-layer)
5. [Database - Neo4j (Graph Layer)](#5-database---neo4j-graph-layer)
6. [Vector Store - FAISS](#6-vector-store---faiss)
7. [API Structure](#7-api-structure)
8. [Authentication & Security](#8-authentication--security)
9. [Shared Types & Utilities](#9-shared-types--utilities)
10. [Testing](#10-testing)
11. [Scripts & Automation](#11-scripts--automation)
12. [Documentation](#12-documentation)
13. [Docker & Containerization](#13-docker--containerization)
14. [CI/CD](#14-cicd)
15. [Deployment](#15-deployment)
16. [Development Tooling](#16-development-tooling)
17. [Data & Corpus](#17-data--corpus)
18. [Logs & Runtime](#18-logs--runtime)
19. [Missing/Recommended Files](#19-missingrecommended-files)
20. [Potentially Unnecessary Files](#20-potentially-unnecessary-files)

---

## Legend

- ✅ **EXISTS** - File currently exists in the repository
- ❌ **MISSING** - File is expected but not present
- 📝 **RECOMMENDED** - File should be created for completeness
- ⚠️ **REVIEW** - File exists but may need review/cleanup
- 🔄 **GENERATED** - Auto-generated file (build/runtime)

---

## 1. Project Root Files

### Core Configuration

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `README.md` | Main project documentation, setup instructions | ✅ Required | None |
| ✅ | `.gitignore` | Git exclusion rules (secrets, caches, artifacts) | ✅ Required | None |
| ✅ | `.env.example` | Template for environment variables | ✅ Required | Used by backend setup |
| ❌ | `.env` | Actual environment variables (not committed) | ✅ Required | Backend runtime |
| ✅ | `docker-compose.yml` | Multi-service orchestration (Neo4j, Redis, API, Streamlit) | ✅ Required | All services |
| ✅ | `.dockerignore` | Excludes files from Docker build context | ✅ Required | Docker builds |
| ❌ | `Makefile` | Common tasks automation (start, test, deploy) | 📝 Recommended | Developer workflow |
| ❌ | `LICENSE` | Software license (proprietary/MIT/Apache) | 📝 Recommended | Legal compliance |
| ❌ | `CHANGELOG.md` | Version history and release notes | 📝 Recommended | Release tracking |
| ❌ | `CONTRIBUTING.md` | Contribution guidelines | 📝 Recommended | Open source/team |
| ❌ | `.editorconfig` | Consistent editor settings | 📝 Recommended | Team consistency |

### Package Management

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `package-lock.json` | Root npm lockfile (monorepo/scripts) | ⚠️ Review | Unclear if needed |
| ❌ | `package.json` | Root package.json (if monorepo or scripts) | ⚠️ Review | Only if npm used at root |

**Notes**: 
- `package-lock.json` exists at root but no corresponding `package.json` - **review if needed**
- Consider if root-level npm is intentional or artifact

---

## 2. Backend - Python/FastAPI

### 2.1 Core Application Structure

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/main.py` | FastAPI app initialization, lifespan, routing | ✅ Required | All modules |
| ✅ | `backend/app/__init__.py` | Package marker | ✅ Required | None |
| ✅ | `backend/app/config.py` | Pydantic settings (env vars, secrets) | ✅ Required | .env file |
| ❌ | `backend/app/version.py` | Version tracking | 📝 Recommended | Deployment |

### 2.2 API Layer

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/api/__init__.py` | API package marker | ✅ Required | None |
| ✅ | `backend/app/api/deps.py` | Dependency injection container | ✅ Required | All services |
| ✅ | `backend/app/api/middleware.py` | Rate limiting, validation middleware | ✅ Required | FastAPI app |
| ✅ | `backend/app/api/routes/query.py` | Query endpoints (traditional/contextgraph) | ✅ Required | Retrieval engine |
| ✅ | `backend/app/api/routes/chat.py` | Multi-turn chat endpoints | ✅ Required | Query, session management |
| ✅ | `backend/app/api/routes/compliance.py` | Compliance audit, scorecard APIs | ✅ Required | Rules engine |
| ✅ | `backend/app/api/routes/status.py` | Health checks, system status | ✅ Required | All data planes |
| ✅ | `backend/app/api/routes/files.py` | Document download, file serving | ✅ Required | Corpus storage |
| ✅ | `backend/app/api/routes/ingest.py` | Document ingestion endpoints | ✅ Required | Ingestion pipeline |
| ✅ | `backend/app/api/routes/auth.py` | Authentication (login, session) | ✅ Required | Auth service |
| ✅ | `backend/app/api/routes/feedback.py` | Human feedback collection | ✅ Required | SQLite feedback store |
| ✅ | `backend/app/api/routes/sessions.py` | Chat session management | ✅ Required | Session storage |
| ✅ | `backend/app/api/routes/admin.py` | Admin operations | ✅ Required | RBAC |
| ✅ | `backend/app/api/routes/graph.py` | Graph exploration endpoints | ✅ Required | Neo4j |
| ✅ | `backend/app/api/routes/taxonomy.py` | Taxonomy management | ✅ Required | Graph schema |
| ✅ | `backend/app/api/routes/metrics.py` | Metrics/analytics endpoints | ✅ Required | Metrics store |
| ✅ | `backend/app/api/routes/docs.py` | Documentation serving | ✅ Required | Frontend |
| ✅ | `backend/app/api/routes/governance.py` | Governance/audit trail | ✅ Required | Compliance |
| ✅ | `backend/app/api/routes/review_queue.py` | Review queue for feedback | ✅ Required | Feedback system |

### 2.3 Core Services

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/core/llm.py` | LLM client wrapper (Groq/OpenAI/Gemini) | ✅ Required | API keys |
| ✅ | `backend/app/core/logging.py` | Structured logging setup | ✅ Required | All modules |
| ✅ | `backend/app/core/errors.py` | Custom exceptions, error handlers | ✅ Required | FastAPI app |
| ✅ | `backend/app/core/metrics.py` | Application metrics collection | ✅ Required | Monitoring |
| ✅ | `backend/app/core/rate_limiter.py` | Rate limiting logic | ✅ Required | API middleware |
| ✅ | `backend/app/core/tracing.py` | Distributed tracing (optional) | ⚠️ Optional | Observability |

### 2.4 Database - SQLite Layer

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/db/__init__.py` | DB package marker | ✅ Required | None |
| ✅ | `backend/app/db/feedback.py` | Feedback store (SQLite) | ✅ Required | sqlite3 |
| ✅ | `backend/app/db/review_queue_repository.py` | Review queue persistence | ✅ Required | sqlite3 |
| ❌ | `backend/app/db/session_repository.py` | Chat session SQLite store | 📝 Recommended | Currently file-based |
| ❌ | `backend/app/db/migrations/` | Database migration scripts | 📝 Recommended | Alembic/manual |
| ❌ | `backend/app/db/schema.sql` | SQLite schema definitions | 📝 Recommended | Documentation |

**Current SQLite Databases**:
- `logs/feedback.db` - Feedback submissions
- Chat sessions - Currently stored as JSON files in `logs/chat_sessions/` (consider migrating to SQLite)

### 2.5 Graph Database - Neo4j Layer

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/graph/__init__.py` | Graph package marker | ✅ Required | None |
| ✅ | `backend/app/graph/schema.py` | Neo4j schema constraints, indexes | ✅ Required | Neo4j driver |
| ✅ | `backend/app/graph/compliance_schema.py` | AMC compliance graph schema | ✅ Required | Neo4j |
| ⚠️ | `backend/app/graph/*.py` | Various graph operations (needs inventory) | ✅ Required | Neo4j |

### 2.6 Vector Store - FAISS

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/vector/__init__.py` | Vector package marker | ✅ Required | None |
| ⚠️ | `backend/app/vector/*.py` | FAISS operations (needs inventory) | ✅ Required | faiss-cpu |

### 2.7 Retrieval Engine

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/engine/__init__.py` | Engine package marker | ✅ Required | None |
| ✅ | `backend/app/engine/config.py` | Engine-specific configuration | ✅ Required | Settings |
| ⚠️ | `backend/app/engine/*.py` | Core retrieval logic (needs full inventory) | ✅ Required | Graph, vector, LLM |

### 2.8 Ingestion Pipeline

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/ingestion/__init__.py` | Ingestion package marker | ✅ Required | None |
| ✅ | `backend/app/ingestion/compliance_rules_ingester.py` | Seed compliance rules | ✅ Required | Neo4j |
| ⚠️ | `backend/app/ingestion/*.py` | Document parsing, chunking (needs inventory) | ✅ Required | PyMuPDF, python-docx |

### 2.9 Compliance System

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/compliance/__init__.py` | Compliance package marker | ✅ Required | None |
| ✅ | `backend/app/compliance/rules_engine.py` | Rule evaluation engine | ✅ Required | Neo4j |
| ✅ | `backend/app/compliance/violation_detector.py` | Violation detection | ✅ Required | Rules engine |
| ✅ | `backend/app/compliance/alerting_service.py` | Alert dispatching | ✅ Required | Rules engine |
| ✅ | `backend/app/compliance/escalation_engine.py` | Escalation logic | ✅ Required | Rules engine |
| ✅ | `backend/app/compliance/failure_taxonomy.py` | Failure categorization | ✅ Required | Feedback system |
| ✅ | `backend/app/compliance/metrics_store.py` | Compliance metrics storage | ✅ Required | Rules engine |
| ✅ | `backend/app/compliance/audit_integration.py` | Audit trail integration | ✅ Required | Compliance APIs |
| ✅ | `backend/app/compliance/security.py` | Security controls | ✅ Required | Auth |
| ⚠️ | `backend/app/compliance/agents/` | Autonomous compliance agents | ⚠️ Review | Needs inventory |

**Rust Integration** (Performance-critical paths):
| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/compliance/amc_compliance_rs.dll` | Rust-compiled compliance rules | ⚠️ Optional | Rust toolchain |
| ✅ | `backend/app/compliance/rules_engine_rust.py` | Python FFI wrapper for Rust | ⚠️ Optional | .dll file |
| ✅ | `backend/app/compliance/compliance_guardrails_rust.py` | Rust guardrails wrapper | ⚠️ Optional | .dll file |

### 2.10 Authentication System

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/auth/__init__.py` | Auth package marker | ✅ Required | None |
| ✅ | `backend/app/auth/security.py` | Password hashing, token generation | ✅ Required | HMAC, bcrypt |
| ✅ | `backend/app/auth/service.py` | Auth business logic | ✅ Required | Repository |
| ✅ | `backend/app/auth/repository.py` | User data access | ✅ Required | JSON store |
| ✅ | `backend/app/auth/data/users.json` | User credentials store | ✅ Required | Auth service |
| ❌ | `backend/app/auth/models.py` | Auth domain models | 📝 Recommended | Service layer |

### 2.11 Schemas & Models

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/schemas/__init__.py` | Schemas package marker | ✅ Required | None |
| ⚠️ | `backend/app/schemas/*.py` | Pydantic models for API contracts | ✅ Required | All routes |

### 2.12 Contracts (Shared Interfaces)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/contracts/__init__.py` | Contracts package marker | ✅ Required | None |
| ✅ | `backend/app/contracts/identity.py` | Identity contracts | ✅ Required | Auth |

### 2.13 Tasks & Background Jobs

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/tasks/__init__.py` | Tasks package marker | ✅ Required | None |
| ✅ | `backend/app/tasks/queue.py` | Async task queue (ingestion) | ✅ Required | Ingestion pipeline |
| ✅ | `backend/app/tasks/scheduler.py` | Background scheduler (APScheduler) | ✅ Required | Cron jobs |

### 2.14 Prompts

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/prompts/__init__.py` | Prompts package marker | ✅ Required | None |
| ⚠️ | `backend/app/prompts/*.py` | LLM prompt templates | ✅ Required | Query engine |

### 2.15 Evaluation & Benchmarking

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/evaluation/__init__.py` | Evaluation package marker | ✅ Required | None |
| ⚠️ | `backend/app/evaluation/*.py` | RAG evaluation harness | ⚠️ Optional | Testing/research |

### 2.16 Feedback System

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/feedback/__init__.py` | Feedback package marker | ✅ Required | None |
| ⚠️ | `backend/app/feedback/*.py` | Feedback processing logic | ✅ Required | SQLite store |

### 2.17 Extraction & Parsing

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/extraction/__init__.py` | Extraction package marker | ✅ Required | None |
| ⚠️ | `backend/app/extraction/*.py` | Document parsing (PDF, DOCX, etc.) | ✅ Required | PyMuPDF, python-docx |

### 2.18 Data Directory

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/data/__init__.py` | Data package marker | ✅ Required | None |
| ⚠️ | `backend/app/data/*.py` | Data access layer | ⚠️ Review | Various modules |

### 2.19 Backend Configuration Files

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/requirements.txt` | Python dependencies | ✅ Required | pip install |
| ✅ | `backend/.env.example` | Backend environment template | ✅ Required | Configuration |
| ❌ | `backend/.env` | Backend environment variables | ✅ Required | Runtime (not committed) |
| ✅ | `backend/.gitignore` | Backend-specific git ignores | ✅ Required | Git |
| ✅ | `backend/Dockerfile` | Backend container definition | ✅ Required | Docker |
| ❌ | `backend/pyproject.toml` | Modern Python project config | 📝 Recommended | Build tools |
| ❌ | `backend/setup.py` | Package installation script | 📝 Recommended | Distribution |
| ❌ | `backend/pytest.ini` | Pytest configuration | 📝 Recommended | Testing |
| ❌ | `backend/.python-version` | Python version pinning | 📝 Recommended | pyenv |
| ❌ | `backend/mypy.ini` | Type checking config | 📝 Recommended | Type safety |
| ❌ | `backend/ruff.toml` | Ruff linter config | 📝 Recommended | Code quality |

### 2.20 Backend Scripts

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ⚠️ | `backend/scripts/` | Utility scripts directory | ⚠️ Review | Needs inventory |
| ❌ | `backend/scripts/seed_neo4j.py` | Initialize Neo4j schema/data | ✅ Required | Neo4j |
| ❌ | `backend/scripts/reindex_faiss.py` | Rebuild FAISS indexes | 📝 Recommended | FAISS |
| ❌ | `backend/scripts/import_corpus.py` | Bulk document import | 📝 Recommended | Ingestion |
| ❌ | `backend/scripts/backup_sqlite.py` | SQLite backup utility | 📝 Recommended | Ops |
| ❌ | `backend/scripts/health_check.py` | Pre-deployment health check | 📝 Recommended | CI/CD |

---

## 3. Frontend - React/Vite

### 3.1 Core Structure

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `mf-context-engine/package.json` | Frontend dependencies | ✅ Required | npm install |
| ✅ | `mf-context-engine/package-lock.json` | Dependency lockfile | ✅ Required | Reproducible builds |
| ✅ | `mf-context-engine/vite.config.js` | Vite build configuration | ✅ Required | Dev server |
| ✅ | `mf-context-engine/index.html` | Entry HTML file | ✅ Required | Vite |
| ✅ | `mf-context-engine/.gitignore` | Frontend git ignores | ✅ Required | Git |
| ✅ | `mf-context-engine/README.md` | Frontend documentation | ✅ Required | Developers |
| ✅ | `mf-context-engine/.oxlintrc.json` | Oxlint configuration | ✅ Required | Linting |
| ❌ | `mf-context-engine/.env.example` | Frontend env template | 📝 Recommended | Configuration |
| ❌ | `mf-context-engine/.env` | Frontend env variables | ⚠️ Optional | Production builds |
| ❌ | `mf-context-engine/tsconfig.json` | TypeScript configuration | 📝 Recommended | Type checking |
| ❌ | `mf-context-engine/tsconfig.node.json` | Node TypeScript config | 📝 Recommended | Vite tooling |
| ❌ | `mf-context-engine/.prettierrc` | Code formatting | 📝 Recommended | Code quality |
| ❌ | `mf-context-engine/.eslintrc.js` | ESLint config (if used) | ⚠️ Optional | Currently using oxlint |

### 3.2 Source Code

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `mf-context-engine/src/main.jsx` | React entry point | ✅ Required | ReactDOM |
| ✅ | `mf-context-engine/src/App.jsx` | Root component | ✅ Required | Router |
| ✅ | `mf-context-engine/src/components/` | Reusable React components | ✅ Required | Views |
| ✅ | `mf-context-engine/src/views/` | Page-level components | ✅ Required | Router |
| ✅ | `mf-context-engine/src/services/` | API client, services | ✅ Required | Backend API |
| ✅ | `mf-context-engine/src/state/` | State management | ✅ Required | Components |
| ✅ | `mf-context-engine/src/utils/` | Utility functions | ✅ Required | Various |
| ✅ | `mf-context-engine/src/styles/` | CSS/styling | ✅ Required | Components |
| ✅ | `mf-context-engine/src/constants/` | Constants, enums | ✅ Required | App logic |
| ✅ | `mf-context-engine/src/data/` | Static data, fixtures | ⚠️ Review | Purpose unclear |

### 3.3 Components (Expected)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `mf-context-engine/src/components/QueryForm.jsx` | Search input component | ✅ Required | API service |
| ❌ | `mf-context-engine/src/components/ResultCard.jsx` | Answer display | ✅ Required | Query response |
| ❌ | `mf-context-engine/src/components/ChatWindow.jsx` | Multi-turn chat UI | ✅ Required | Chat API |
| ❌ | `mf-context-engine/src/components/ComplianceCard.jsx` | Compliance scorecard | ✅ Required | Compliance API |
| ❌ | `mf-context-engine/src/components/CitationList.jsx` | Citations/provenance | ✅ Required | Result card |
| ❌ | `mf-context-engine/src/components/GraphVisualization.jsx` | Graph explorer | ⚠️ Optional | Neo4j API |
| ❌ | `mf-context-engine/src/components/FeedbackForm.jsx` | Human feedback UI | ✅ Required | Feedback API |
| ❌ | `mf-context-engine/src/components/LoginForm.jsx` | Authentication UI | ✅ Required | Auth API |
| ❌ | `mf-context-engine/src/components/Header.jsx` | Navigation header | ✅ Required | Layout |
| ❌ | `mf-context-engine/src/components/Sidebar.jsx` | Navigation sidebar | ⚠️ Optional | Layout |

### 3.4 Services/API Layer

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `mf-context-engine/src/services/api.js` | Base API client (axios/fetch) | ✅ Required | Backend |
| ❌ | `mf-context-engine/src/services/queryService.js` | Query API calls | ✅ Required | API client |
| ❌ | `mf-context-engine/src/services/chatService.js` | Chat API calls | ✅ Required | API client |
| ❌ | `mf-context-engine/src/services/authService.js` | Auth API calls | ✅ Required | API client |
| ❌ | `mf-context-engine/src/services/feedbackService.js` | Feedback API calls | ✅ Required | API client |

### 3.5 Build Artifacts (Generated)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| 🔄 | `mf-context-engine/dist/` | Production build output | 🔄 Generated | `npm run build` |
| 🔄 | `mf-context-engine/node_modules/` | Installed npm packages | 🔄 Generated | `npm install` |

### 3.6 Test Files (Present but Unusual)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ⚠️ | `mf-context-engine/test_auth_logic.js` | Auth testing | ⚠️ Review | Not in tests/ dir |
| ⚠️ | `mf-context-engine/test_auth_validation.js` | Auth validation | ⚠️ Review | Not in tests/ dir |
| ⚠️ | `mf-context-engine/test_build.html` | Build testing | ⚠️ Review | Unusual location |
| ⚠️ | `mf-context-engine/test_components.js` | Component tests | ⚠️ Review | Should be .test.js |
| ⚠️ | `mf-context-engine/test_state_management.js` | State tests | ⚠️ Review | Should be .test.js |

**Recommendation**: Move to proper `tests/` or `__tests__/` directory with `.test.js` naming

### 3.7 Public Assets

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `mf-context-engine/public/` | Static assets directory | ✅ Required | Vite |
| ❌ | `mf-context-engine/public/favicon.ico` | Browser icon | 📝 Recommended | UX |
| ❌ | `mf-context-engine/public/logo.svg` | Application logo | 📝 Recommended | Branding |
| ❌ | `mf-context-engine/public/robots.txt` | SEO crawler control | 📝 Recommended | SEO |

---

## 4. Database - SQLite (Application Layer)

### 4.1 Current SQLite Databases

| Status | Path | Purpose | Required? | Schema Defined? |
|--------|------|---------|-----------|-----------------|
| 🔄 | `logs/feedback.db` | Human feedback submissions | ✅ Required | ✅ Yes (feedback.py) |
| ❌ | `logs/review_queue.db` | Review queue items | 📝 Recommended | ✅ Yes (review_queue_repository.py) |
| ❌ | `logs/sessions.db` | Chat session metadata | 📝 Recommended | ❌ No (currently JSON files) |
| ❌ | `logs/audit.db` | Audit trail | 📝 Recommended | ❌ No |
| ❌ | `logs/metrics.db` | Application metrics | 📝 Recommended | ❌ No |

### 4.2 Schema Files (Recommended)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `backend/app/db/schema/feedback.sql` | Feedback schema DDL | 📝 Recommended | Documentation |
| ❌ | `backend/app/db/schema/review_queue.sql` | Review queue schema | 📝 Recommended | Documentation |
| ❌ | `backend/app/db/schema/sessions.sql` | Sessions schema | 📝 Recommended | If migrating from JSON |
| ❌ | `backend/app/db/migrations/` | Migration scripts | 📝 Recommended | Schema evolution |

### 4.3 SQLite Management Scripts

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `scripts/sqlite_backup.sh` | Backup SQLite databases | 📝 Recommended | Operations |
| ❌ | `scripts/sqlite_vacuum.sh` | Optimize database files | 📝 Recommended | Maintenance |
| ❌ | `scripts/sqlite_export_csv.py` | Export data to CSV | 📝 Recommended | Analysis |

**Current Schema Locations**:
- Feedback: Defined in `backend/app/db/feedback.py` (Python code, not SQL file)
- Review Queue: Defined in `backend/app/db/review_queue_repository.py`

**Recommendation**: Extract SQL schema to separate `.sql` files for:
- Documentation clarity
- Version control of schema changes
- Easier database inspection/setup

---

## 5. Database - Neo4j (Graph Layer)

### 5.1 Schema & Setup

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/graph/schema.py` | Core graph schema | ✅ Required | Neo4j driver |
| ✅ | `backend/app/graph/compliance_schema.py` | Compliance graph schema | ✅ Required | Neo4j |
| ✅ | `amc_master_full_dump.cypher` | Neo4j database dump (Cypher) | ✅ Required | Data import |
| ✅ | `amc_master_full_dump.json` | Graph data (JSON format) | ✅ Required | Alternative import |
| ✅ | `import_neo4j_dump.py` | Import script for dumps | ✅ Required | Setup |

### 5.2 Cypher Queries (Recommended)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `backend/app/graph/queries/` | Directory for Cypher queries | 📝 Recommended | Query organization |
| ❌ | `backend/app/graph/queries/compliance_rules.cypher` | Compliance rule queries | 📝 Recommended | Rules engine |
| ❌ | `backend/app/graph/queries/fund_relationships.cypher` | Fund graph queries | 📝 Recommended | Retrieval |
| ❌ | `backend/app/graph/queries/taxonomy_traversal.cypher` | Taxonomy queries | 📝 Recommended | Retrieval |

### 5.3 Neo4j Management

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `scripts/backup_compliance_graph.sh` | Backup Neo4j (Unix) | ✅ Required | Operations |
| ✅ | `scripts/backup_compliance_graph.ps1` | Backup Neo4j (Windows) | ✅ Required | Operations |
| ✅ | `scripts/restore_compliance_graph.sh` | Restore Neo4j (Unix) | ✅ Required | Operations |
| ✅ | `scripts/restore_compliance_graph.ps1` | Restore Neo4j (Windows) | ✅ Required | Operations |
| ✅ | `deploy/export.cypher` | Export script for deployment | ✅ Required | Deployment |
| ❌ | `scripts/neo4j_health_check.sh` | Neo4j connectivity test | 📝 Recommended | CI/CD |

### 5.4 Graph Data Ingestion

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/ingestion/compliance_rules_ingester.py` | Seed compliance rules | ✅ Required | Schema |
| ❌ | `backend/app/ingestion/fund_data_ingester.py` | Import fund data | 📝 Recommended | Data pipeline |
| ❌ | `backend/app/ingestion/taxonomy_ingester.py` | Import taxonomy | 📝 Recommended | Data pipeline |

---

## 6. Vector Store - FAISS

### 6.1 FAISS Indexes

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| 🔄 | `backend/app/engine/faiss_indexes/` | FAISS index storage | ✅ Required | Retrieval engine |
| 🔄 | `faiss_indexes/` | Alternative FAISS location | ⚠️ Review | May be duplicate |
| 🔄 | `data/faiss/` | Yet another FAISS location | ⚠️ Review | May be duplicate |

**Issue**: Multiple FAISS index directories - needs consolidation

**Expected FAISS Files**:
- `index.faiss` - FAISS index file
- `payloads.json` - Metadata for vectors
- `config.json` - Index configuration

### 6.2 FAISS Management Scripts

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `backend/scripts/rebuild_faiss.py` | Rebuild FAISS from corpus | 📝 Recommended | Maintenance |
| ❌ | `backend/scripts/validate_faiss_index.py` | Verify index integrity | 📝 Recommended | Debugging |
| ❌ | `backend/scripts/faiss_stats.py` | Index statistics | 📝 Recommended | Monitoring |

### 6.3 Embedding Model Cache

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| 🔄 | `~/.cache/huggingface/` | Downloaded embedding models | 🔄 Generated | sentence-transformers |
| 🔄 | Docker volume: `hf_cache` | Model cache in containers | ✅ Required | Docker |

---

## 7. API Structure

### 7.1 API Documentation

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `backend/docs/api/` | API documentation directory | 📝 Recommended | Developers |
| ❌ | `backend/docs/api/query.md` | Query API documentation | 📝 Recommended | OpenAPI |
| ❌ | `backend/docs/api/chat.md` | Chat API documentation | 📝 Recommended | OpenAPI |
| ❌ | `backend/docs/api/compliance.md` | Compliance API docs | 📝 Recommended | OpenAPI |
| ❌ | `backend/docs/openapi.yaml` | OpenAPI 3.0 spec | 📝 Recommended | Auto-generated |

**Note**: FastAPI auto-generates docs at `/docs` and `/redoc`, but static documentation is useful for:
- Version control
- Non-developers
- External partners

### 7.2 API Request/Response Examples

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `backend/docs/api/examples/` | Example requests/responses | 📝 Recommended | Testing |
| ❌ | `backend/tests/fixtures/api_responses.json` | Test fixtures | 📝 Recommended | Testing |

---

## 8. Authentication & Security

### 8.1 Auth Configuration

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/auth/data/users.json` | User credentials store | ✅ Required | Auth service |
| ❌ | `backend/app/auth/data/roles.json` | RBAC role definitions | 📝 Recommended | Authorization |
| ❌ | `backend/app/auth/data/permissions.json` | Permission mappings | 📝 Recommended | Authorization |

### 8.2 Security Policies

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `SECURITY.md` | Security policy & reporting | 📝 Recommended | Compliance |
| ❌ | `backend/app/auth/policies/` | Authorization policies | 📝 Recommended | RBAC |
| ❌ | `.github/dependabot.yml` | Automated dependency updates | 📝 Recommended | Security |

### 8.3 Secrets Management

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `.env` (gitignored) | Local development secrets | ✅ Required | All services |
| ✅ | AWS Secrets Manager | Production secrets | ✅ Required | Deployment |
| ❌ | `secrets.example.yml` | Secrets template (K8s) | 📝 Recommended | Kubernetes |

---

## 9. Shared Types & Utilities

### 9.1 Python Shared Code

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/contracts/` | Shared interfaces | ✅ Required | Multiple modules |
| ✅ | `backend/app/schemas/` | Pydantic models | ✅ Required | API contracts |
| ❌ | `backend/app/common/` | Common utilities | 📝 Recommended | DRY principle |
| ❌ | `backend/app/types.py` | Type aliases | 📝 Recommended | Type hints |

### 9.2 Frontend Shared Code

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `mf-context-engine/src/utils/` | Utility functions | ✅ Required | Components |
| ✅ | `mf-context-engine/src/constants/` | Constants | ✅ Required | App logic |
| ❌ | `mf-context-engine/src/types/` | TypeScript types | 📝 Recommended | Type safety |
| ❌ | `mf-context-engine/src/hooks/` | Custom React hooks | 📝 Recommended | Components |

---

## 10. Testing

### 10.1 Backend Tests

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `backend/tests/` | Test root directory | ✅ Required | pytest |
| ❌ | `backend/tests/__init__.py` | Test package marker | ✅ Required | pytest |
| ❌ | `backend/tests/conftest.py` | Pytest fixtures | ✅ Required | All tests |
| ❌ | `backend/tests/test_api.py` | API endpoint tests | ✅ Required | FastAPI |
| ❌ | `backend/tests/test_engine.py` | Retrieval engine tests | ✅ Required | Engine |
| ❌ | `backend/tests/test_compliance.py` | Compliance rules tests | ✅ Required | Rules engine |
| ❌ | `backend/tests/test_integration.py` | End-to-end tests | 📝 Recommended | Full stack |
| ❌ | `backend/tests/test_graph.py` | Neo4j operations tests | ✅ Required | Graph |
| ❌ | `backend/tests/test_auth.py` | Authentication tests | ✅ Required | Auth |
| ❌ | `backend/tests/test_feedback.py` | Feedback store tests | ✅ Required | SQLite |
| ❌ | `backend/tests/fixtures/` | Test data fixtures | 📝 Recommended | All tests |
| ❌ | `backend/pytest.ini` | Pytest configuration | 📝 Recommended | Test setup |
| ❌ | `backend/.coveragerc` | Coverage configuration | 📝 Recommended | Test coverage |

### 10.2 Frontend Tests

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `mf-context-engine/tests/` | Test directory | ✅ Required | Vitest/Jest |
| ❌ | `mf-context-engine/tests/setup.js` | Test setup | 📝 Recommended | Test config |
| ❌ | `mf-context-engine/src/components/__tests__/` | Component tests | ✅ Required | Components |
| ❌ | `mf-context-engine/src/services/__tests__/` | Service tests | ✅ Required | API layer |
| ❌ | `mf-context-engine/vitest.config.js` | Vitest config | 📝 Recommended | Testing |
| ❌ | `mf-context-engine/jest.config.js` | Jest config (if used) | ⚠️ Optional | Alternative |

### 10.3 E2E Tests

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `e2e/` | End-to-end test directory | 📝 Recommended | Playwright/Cypress |
| ❌ | `e2e/tests/query_flow.spec.js` | Query workflow tests | 📝 Recommended | E2E |
| ❌ | `e2e/tests/chat_flow.spec.js` | Chat workflow tests | 📝 Recommended | E2E |
| ❌ | `playwright.config.js` | Playwright config | 📝 Recommended | If using Playwright |
| ❌ | `cypress.config.js` | Cypress config | 📝 Recommended | If using Cypress |

### 10.4 Test Data & Fixtures

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `tests/fixtures/sample_queries.json` | Test queries | 📝 Recommended | Testing |
| ❌ | `tests/fixtures/expected_responses.json` | Expected outputs | 📝 Recommended | Assertions |
| ❌ | `tests/fixtures/mock_neo4j_data.json` | Graph test data | 📝 Recommended | Graph tests |

---

## 11. Scripts & Automation

### 11.1 Operational Scripts

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `scripts/backup_compliance_graph.sh` | Backup Neo4j (Unix) | ✅ Required | Neo4j |
| ✅ | `scripts/backup_compliance_graph.ps1` | Backup Neo4j (Windows) | ✅ Required | Neo4j |
| ✅ | `scripts/restore_compliance_graph.sh` | Restore Neo4j (Unix) | ✅ Required | Neo4j |
| ✅ | `scripts/restore_compliance_graph.ps1` | Restore Neo4j (Windows) | ✅ Required | Neo4j |
| ❌ | `scripts/seed_database.sh` | Initialize all databases | 📝 Recommended | Setup |
| ❌ | `scripts/reset_development.sh` | Reset dev environment | 📝 Recommended | Development |
| ❌ | `scripts/update_dependencies.sh` | Update all dependencies | 📝 Recommended | Maintenance |

### 11.2 Batch Files (Windows)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `run_project.bat` | Start full stack (Windows) | ✅ Required | Windows dev |
| ✅ | `mock_run.bat` | Mock/test runner | ⚠️ Review | Purpose unclear |
| ✅ | `temp_test.bat` | Temporary test script | ⚠️ Review | Remove if not needed |
| ✅ | `test_no_pause.bat` | Test without pause | ⚠️ Review | Purpose unclear |
| ✅ | `run_compliance_dashboard.ps1` | Start compliance UI | ✅ Required | Streamlit |

### 11.3 Shell Scripts (Unix)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `run_compliance_dashboard.sh` | Start compliance UI (Unix) | ✅ Required | Streamlit |
| ❌ | `scripts/start_backend.sh` | Start backend | 📝 Recommended | Development |
| ❌ | `scripts/start_frontend.sh` | Start frontend | 📝 Recommended | Development |
| ❌ | `scripts/run_tests.sh` | Run all tests | 📝 Recommended | CI/CD |

---

## 12. Documentation

### 12.1 Core Documentation

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `README.md` | Main project README | ✅ Required | None |
| ✅ | `00_START_HERE.md` | Entry point for developers | ✅ Required | None |
| ✅ | `00_CHIEF_ARCHITECT_START_HERE.md` | Architecture overview | ✅ Required | Architects |
| ✅ | `START_HERE.md` | Alternative entry point | ⚠️ Review | Duplicate? |
| ❌ | `CONTRIBUTING.md` | Contribution guidelines | 📝 Recommended | Contributors |
| ❌ | `CODE_OF_CONDUCT.md` | Community guidelines | 📝 Recommended | Open source |
| ❌ | `CHANGELOG.md` | Version history | 📝 Recommended | Releases |
| ❌ | `LICENSE` | Software license | 📝 Recommended | Legal |

### 12.2 Architecture Documentation

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `ARCHITECTURE_AND_INTEGRATION.md` | System architecture | ✅ Required | Developers |
| ✅ | `Docs/SCHEMA_AND_AUDIT_STRUCTURE.md` | Database schemas | ✅ Required | Database work |
| ✅ | `system_architecture_flowchart.html` | Visual architecture | ✅ Required | Understanding |
| ✅ | `comprehensive_query_pipeline_flowchart.html` | Query pipeline | ✅ Required | Understanding |
| ✅ | `query_pipeline_metrics_flowchart.html` | Metrics flow | ✅ Required | Monitoring |
| ❌ | `docs/architecture/data_flow.md` | Data flow diagrams | 📝 Recommended | Developers |
| ❌ | `docs/architecture/security_model.md` | Security architecture | 📝 Recommended | Security review |

### 12.3 Implementation Documentation

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `IMPLEMENTATION_ROADMAP_COMPLETE.md` | Implementation roadmap | ✅ Required | Planning |
| ✅ | `IMPLEMENTATION_SUMMARY.md` | Implementation summary | ✅ Required | Status tracking |
| ✅ | `DETAILED_IMPLEMENTATION_PLAN.md` | Detailed plan | ✅ Required | Planning |
| ✅ | `DESIGN_IMPLEMENTATION_GAP_ANALYSIS.md` | Gap analysis | ✅ Required | Planning |
| ✅ | `IMPLEMENTATION_CODE_SNIPPETS.md` | Code examples | ✅ Required | Reference |
| ❌ | `docs/implementation/phase_tracking.md` | Phase status | 📝 Recommended | Project mgmt |

### 12.4 Audit & Compliance Documentation

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `AUDIT_MANIFEST.md` | Audit manifest | ✅ Required | Compliance |
| ✅ | `AUDIT_COMPLETION_SUMMARY.txt` | Audit summary | ✅ Required | Compliance |
| ✅ | `AGENTIC_SOLUTION_AUDIT.md` | Solution audit | ✅ Required | Quality |
| ✅ | `AMC_PERSPECTIVE_AUDIT.md` | AMC perspective | ✅ Required | Domain |
| ✅ | `COMPLIANCE_CHECKLIST.md` | Compliance checklist | ✅ Required | Compliance |
| ✅ | `PHASE_0_AUDIT_REPORT.md` | Phase 0 audit | ✅ Required | Historical |

### 12.5 Operational Documentation

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `OPERATOR_RUNBOOK.md` | Operations manual | ✅ Required | Production ops |
| ✅ | `DEPLOYMENT_GUIDE.md` | Deployment procedures | ✅ Required | Deployment |
| ✅ | `PRODUCTION_ROLLOUT.md` | Rollout plan | ✅ Required | Production |
| ✅ | `PRE_DEPLOYMENT_VERIFICATION.md` | Pre-deploy checks | ✅ Required | Deployment |
| ❌ | `docs/operations/troubleshooting.md` | Troubleshooting guide | 📝 Recommended | Support |
| ❌ | `docs/operations/monitoring.md` | Monitoring setup | 📝 Recommended | Observability |

### 12.6 Phase & Evaluation Documentation

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `PHASE_0_ANALYSIS.md` through `PHASE_4_SUMMARY.md` | Phase documentation | ✅ Required | Historical |
| ✅ | `EVALUATION_DOCUMENTATION_INDEX.md` | Evaluation index | ✅ Required | Quality |
| ✅ | `LATENCY_TOKEN_EVALUATION.md` | Performance eval | ✅ Required | Benchmarking |
| ✅ | `BENCHMARK_SUMMARY.md` | Benchmark results | ✅ Required | Performance |

### 12.7 Docs Directory

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `Docs/` | Documentation directory | ✅ Required | Organization |
| ✅ | `Docs/SCHEMA_AND_AUDIT_STRUCTURE.md` | Schema documentation | ✅ Required | Database |
| ❌ | `Docs/api/` | API documentation | 📝 Recommended | Developers |
| ❌ | `Docs/architecture/` | Architecture docs | 📝 Recommended | System design |
| ❌ | `Docs/guides/` | User guides | 📝 Recommended | End users |

**Issue**: Many documentation files are scattered in root directory - consider organizing into `Docs/` subdirectories

---

## 13. Docker & Containerization

### 13.1 Docker Configuration

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `docker-compose.yml` | Multi-service orchestration | ✅ Required | Docker |
| ✅ | `.dockerignore` | Docker build exclusions | ✅ Required | Docker |
| ✅ | `backend/Dockerfile` | Backend container | ✅ Required | Docker build |
| ❌ | `mf-context-engine/Dockerfile` | Frontend container | 📝 Recommended | Production |
| ✅ | `streamlit_app/Dockerfile` | Streamlit UI container | ✅ Required | Docker |
| ❌ | `docker-compose.dev.yml` | Development overrides | 📝 Recommended | Dev environment |
| ❌ | `docker-compose.prod.yml` | Production overrides | 📝 Recommended | Production |

### 13.2 Docker Volumes

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| 🔄 | Volume: `neo4j_data` | Neo4j persistence | ✅ Required | Neo4j service |
| 🔄 | Volume: `hf_cache` | Hugging Face models | ✅ Required | ML models |
| 🔄 | Volume: `engine_data` | Engine data | ✅ Required | Backend |
| 🔄 | Volume: `engine_faiss` | FAISS indexes | ✅ Required | Vector search |
| 🔄 | Volume: `faiss_data` | Alternative FAISS | ⚠️ Review | Duplicate? |
| 🔄 | Volume: `chat_sessions` | Chat session files | ✅ Required | Streamlit |

### 13.3 Container Health Checks

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | Neo4j healthcheck (in compose) | Neo4j readiness | ✅ Required | docker-compose |
| ❌ | `backend/healthcheck.py` | Backend health script | 📝 Recommended | Monitoring |
| ❌ | `deploy/healthcheck.sh` | Universal health check | 📝 Recommended | CI/CD |

---

## 14. CI/CD

### 14.1 GitHub Actions (Recommended)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `.github/workflows/` | Workflow directory | 📝 Recommended | GitHub Actions |
| ❌ | `.github/workflows/test.yml` | Run tests on PR | 📝 Recommended | CI |
| ❌ | `.github/workflows/lint.yml` | Code quality checks | 📝 Recommended | CI |
| ❌ | `.github/workflows/deploy.yml` | Deployment automation | 📝 Recommended | CD |
| ❌ | `.github/workflows/docker-build.yml` | Build containers | 📝 Recommended | CI |
| ❌ | `.github/dependabot.yml` | Dependency updates | 📝 Recommended | Security |

### 14.2 GitLab CI (Alternative)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `.gitlab-ci.yml` | GitLab CI configuration | ⚠️ Optional | If using GitLab |

### 14.3 Jenkins (Alternative)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `Jenkinsfile` | Jenkins pipeline | ⚠️ Optional | If using Jenkins |

### 14.4 CI Scripts

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `scripts/ci/run_tests.sh` | CI test runner | 📝 Recommended | CI pipeline |
| ❌ | `scripts/ci/lint_check.sh` | Linting script | 📝 Recommended | CI pipeline |
| ❌ | `scripts/ci/build_docker.sh` | Docker build script | 📝 Recommended | CI pipeline |
| ❌ | `scripts/ci/deploy_staging.sh` | Staging deployment | 📝 Recommended | CD pipeline |

---

## 15. Deployment

### 15.1 AWS Deployment

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `deploy/deploy.sh` | AWS deployment script | ✅ Required | AWS CLI |
| ✅ | `deploy/ec2-bootstrap.sh` | EC2 instance setup | ✅ Required | EC2 deployment |
| ✅ | `deploy/ec2-user-data.sh` | EC2 user data script | ✅ Required | EC2 initialization |
| ✅ | `deploy/README.md` | Deployment documentation | ✅ Required | Ops team |
| ✅ | `deploy/.gitignore` | Deployment artifacts ignore | ✅ Required | Git |
| ✅ | `deploy/db_transport.json` | Database transfer config | ⚠️ Review | May contain sensitive data |

### 15.2 Kubernetes Deployment

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `deploy/k8s/` | Kubernetes manifests directory | ⚠️ Optional | If using K8s |
| ❌ | `deploy/k8s/namespace.yaml` | K8s namespace | 📝 Recommended | K8s |
| ❌ | `deploy/k8s/backend-deployment.yaml` | Backend deployment | 📝 Recommended | K8s |
| ❌ | `deploy/k8s/backend-service.yaml` | Backend service | 📝 Recommended | K8s |
| ❌ | `deploy/k8s/neo4j-statefulset.yaml` | Neo4j StatefulSet | 📝 Recommended | K8s |
| ❌ | `deploy/k8s/configmap.yaml` | Configuration | 📝 Recommended | K8s |
| ❌ | `deploy/k8s/secrets.yaml` | Secrets (template) | 📝 Recommended | K8s |
| ❌ | `deploy/k8s/ingress.yaml` | Ingress rules | 📝 Recommended | K8s |
| ❌ | `deploy/k8s/hpa.yaml` | Horizontal autoscaling | 📝 Recommended | K8s |

### 15.3 Lambda Functions

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `deploy/lambda/` | Lambda functions directory | ⚠️ Optional | If using Lambda |
| ❌ | `deploy/lambda/requirements.txt` | Lambda dependencies | 📝 Recommended | Lambda |
| ❌ | `deploy/lambda/handler.py` | Lambda function code | 📝 Recommended | Lambda |

### 15.4 Monitoring Setup

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `deploy/monitoring/` | Monitoring configs | ⚠️ Optional | Observability |
| ❌ | `deploy/monitoring/prometheus.yml` | Prometheus config | 📝 Recommended | Prometheus |
| ❌ | `deploy/monitoring/grafana-dashboards/` | Grafana dashboards | 📝 Recommended | Grafana |
| ❌ | `deploy/monitoring/alerting-rules.yml` | Alert rules | 📝 Recommended | Prometheus |

### 15.5 Production Roadmap

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `production_roadmap/` | Production planning docs | ✅ Required | Planning |
| ⚠️ | `production_roadmap/*.md` | Various roadmap docs | ✅ Required | Needs inventory |

---

## 16. Development Tooling

### 16.1 IDE Configuration

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `.vscode/` | VS Code workspace settings | 📝 Recommended | VS Code |
| ❌ | `.vscode/settings.json` | Editor settings | 📝 Recommended | Team consistency |
| ❌ | `.vscode/extensions.json` | Recommended extensions | 📝 Recommended | Developer setup |
| ❌ | `.vscode/launch.json` | Debug configurations | 📝 Recommended | Debugging |
| ❌ | `.idea/` | PyCharm/IntelliJ settings | ⚠️ Optional | If using JetBrains |
| ❌ | `.editorconfig` | Cross-editor settings | 📝 Recommended | Team consistency |

### 16.2 Linting & Formatting

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `mf-context-engine/.oxlintrc.json` | Oxlint config | ✅ Required | Frontend linting |
| ❌ | `backend/ruff.toml` | Ruff linter config | 📝 Recommended | Backend linting |
| ❌ | `backend/mypy.ini` | Type checking config | 📝 Recommended | Type safety |
| ❌ | `backend/.flake8` | Flake8 config (if used) | ⚠️ Optional | Alternative linter |
| ❌ | `backend/pyproject.toml` | Black/isort config | 📝 Recommended | Code formatting |
| ❌ | `.prettierrc` | Prettier config | 📝 Recommended | Frontend formatting |
| ❌ | `.eslintrc.js` | ESLint config | ⚠️ Optional | If not using oxlint |

### 16.3 Git Hooks (Pre-commit)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `.pre-commit-config.yaml` | Pre-commit hooks | 📝 Recommended | Code quality |
| ❌ | `.husky/` | Husky git hooks | ⚠️ Optional | Alternative to pre-commit |

### 16.4 Development Scripts

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ❌ | `scripts/dev/setup.sh` | Development setup | 📝 Recommended | Onboarding |
| ❌ | `scripts/dev/reset.sh` | Reset dev environment | 📝 Recommended | Development |
| ❌ | `scripts/dev/seed_data.sh` | Seed test data | 📝 Recommended | Development |

---

## 17. Data & Corpus

### 17.1 Data Directories

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `data/` | Data root directory | ✅ Required | All data operations |
| ✅ | `data/corpora/` | Document corpus | ✅ Required | Ingestion |
| ✅ | `data/compliance/` | Compliance data | ✅ Required | Rules engine |
| ✅ | `data/faiss/` | FAISS indexes | ✅ Required | Vector search |
| ❌ | `data/uploads/` | Temporary uploads | ✅ Required | Ingestion |
| ❌ | `data/processed/` | Processed documents | 📝 Recommended | Pipeline |
| ❌ | `data/backups/` | Data backups | 📝 Recommended | Disaster recovery |

### 17.2 Corpus Files

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `amc_master_full_dump.cypher` | Graph database dump | ✅ Required | Neo4j import |
| ✅ | `amc_master_full_dump.json` | Alternative data format | ✅ Required | Import script |
| ❌ | `data/corpora/README.md` | Corpus documentation | 📝 Recommended | Data understanding |

### 17.3 FAISS Indexes (Multiple Locations - Needs Consolidation)

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| 🔄 | `faiss_indexes/` | FAISS indexes (root) | ⚠️ Review | May be legacy |
| 🔄 | `data/faiss/` | FAISS indexes (data) | ⚠️ Review | May be legacy |
| 🔄 | `backend/app/engine/faiss_indexes/` | FAISS indexes (engine) | ✅ Required | Current location |

**Recommendation**: Consolidate to single location (`backend/app/engine/faiss_indexes/`)

---

## 18. Logs & Runtime

### 18.1 Log Directories

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `logs/` | Application logs | ✅ Required | Logging |
| 🔄 | `logs/feedback.db` | Feedback database | ✅ Required | Feedback system |
| 🔄 | `logs/chat_sessions/` | Chat session files | ✅ Required | Session management |
| ❌ | `logs/api/` | API request logs | 📝 Recommended | Debugging |
| ❌ | `logs/errors/` | Error logs | 📝 Recommended | Troubleshooting |
| ❌ | `logs/audit/` | Audit trail logs | 📝 Recommended | Compliance |

### 18.2 Benchmark & Profiling Output

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `backend/app/compliance/benchmark_output.log` | Benchmark logs | ⚠️ Review | Should be in logs/ |
| ✅ | `backend/app/compliance/profiling_output.log` | Profiling logs | ⚠️ Review | Should be in logs/ |
| ✅ | `backend/app/compliance/benchmark_report_detailed.json` | Benchmark report | ⚠️ Review | Should be in logs/ |
| ✅ | `backend/app/compliance/phase3_profiling_results/` | Profiling results | ⚠️ Review | Should be in logs/ |

**Recommendation**: Move output/logs to dedicated `logs/` directory

### 18.3 Evaluation Output

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `evaluation/` | Evaluation results directory | ✅ Required | Quality assessment |
| ✅ | `multi_turn_report.html` | Multi-turn eval report | ✅ Required | Quality metrics |
| ✅ | `system_valuation_performance_report.html` | Performance report | ✅ Required | Benchmarking |

---

## 19. Missing/Recommended Files

### 19.1 High Priority Missing Files

| Path | Purpose | Why Missing? | Impact |
|------|---------|-------------|--------|
| `backend/tests/` | Backend test suite | Not created yet | Cannot verify code quality |
| `mf-context-engine/tests/` | Frontend test suite | Not created yet | Cannot verify UI behavior |
| `backend/.env` | Backend environment | Not committed (correct) | Required for local dev |
| `Makefile` | Task automation | Not created | Harder developer workflow |
| `LICENSE` | Legal license | Not specified | Legal ambiguity |
| `CHANGELOG.md` | Version history | Not tracked | No release notes |
| `backend/pytest.ini` | Test configuration | Not created | Test setup unclear |
| `backend/pyproject.toml` | Modern Python config | Not created | Missing build metadata |

### 19.2 Database Schema Files

| Path | Purpose | Why Missing? | Impact |
|------|---------|-------------|--------|
| `backend/app/db/schema/feedback.sql` | Feedback schema DDL | Schema in Python only | Hard to review schema |
| `backend/app/db/schema/review_queue.sql` | Review queue schema | Schema in Python only | Hard to review schema |
| `backend/app/db/migrations/` | Schema migrations | Not implemented | Schema evolution unclear |

### 19.3 API Documentation Files

| Path | Purpose | Why Missing? | Impact |
|------|---------|-------------|--------|
| `backend/docs/api/` | API documentation | Relying on auto-gen | No static reference |
| `backend/docs/openapi.yaml` | OpenAPI spec | Not exported | External integration harder |

### 19.4 CI/CD Files

| Path | Purpose | Why Missing? | Impact |
|------|---------|-------------|--------|
| `.github/workflows/test.yml` | CI test pipeline | Not implemented | Manual testing only |
| `.github/workflows/deploy.yml` | CD deployment | Manual deployment | Slower releases |

### 19.5 Frontend Missing Files

| Path | Purpose | Why Missing? | Impact |
|------|---------|-------------|--------|
| `mf-context-engine/tsconfig.json` | TypeScript config | Not created | Type checking disabled |
| `mf-context-engine/.env.example` | Frontend env template | Not documented | Config unclear |
| `mf-context-engine/Dockerfile` | Frontend container | Not created | Production deployment harder |

---

## 20. Potentially Unnecessary Files

### 20.1 Files to Review/Remove

| Status | Path | Reason | Recommendation |
|--------|------|--------|----------------|
| ⚠️ | `package-lock.json` (root) | No corresponding package.json | Remove if not needed |
| ⚠️ | `mock_run.bat` | Purpose unclear | Review and document or remove |
| ⚠️ | `temp_test.bat` | Temporary file | Remove if obsolete |
| ⚠️ | `test_no_pause.bat` | Purpose unclear | Review and document or remove |
| ⚠️ | `mf-context-engine/test_*.js` (root) | Tests not in tests/ dir | Move to proper location |
| ⚠️ | `mf-context-engine/test_build.html` | Test file in wrong location | Move or remove |
| ⚠️ | `backend/app/compliance/simple_test.py` | Ad-hoc test file | Move to tests/ or remove |
| ⚠️ | `backend/app/compliance/test_ffi.py` | Ad-hoc test file | Move to tests/ or remove |

### 20.2 Duplicate/Scattered Files

**Issue**: Multiple locations for similar data

| Issue | Files | Recommendation |
|-------|-------|----------------|
| Multiple FAISS directories | `faiss_indexes/`, `data/faiss/`, `backend/app/engine/faiss_indexes/` | Consolidate to one location |
| Scattered documentation | 50+ .md files in root | Organize into `Docs/` subdirectories |
| Multiple "START_HERE" files | `START_HERE.md`, `00_START_HERE.md`, `00_CHIEF_ARCHITECT_START_HERE.md` | Consolidate or clearly differentiate |
| Benchmark/profiling output in app/ | Various .log and .json files in `backend/app/compliance/` | Move to `logs/` directory |

### 20.3 Legacy/Obsolete Directories

| Path | Reason | Recommendation |
|------|--------|----------------|
| `scratch/` | Development scratch space | Review contents, keep in .gitignore |
| `backend/.pytest_cache/` | Test cache (should be gitignored) | Ensure in .gitignore |
| `backend/app/__pycache__/` | Python cache (should be gitignored) | Ensure in .gitignore |

---

## 21. Streamlit Application (Legacy UI)

### 21.1 Streamlit Files

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `streamlit_app/` | Legacy Streamlit UI directory | ⚠️ Optional | If maintaining Streamlit |
| ✅ | `streamlit_app/Dockerfile` | Streamlit container | ⚠️ Optional | Docker |
| ⚠️ | `streamlit_app/*.py` | Streamlit pages | ⚠️ Optional | Needs inventory if keeping |

**Note**: Project now has React frontend (`mf-context-engine/`) as primary UI. Streamlit may be legacy/compliance dashboard only.

---

## 22. Rust Integration

### 22.1 Rust Components

| Status | Path | Purpose | Required? | Dependencies |
|--------|------|---------|-----------|--------------|
| ✅ | `rust/` | Rust source code | ⚠️ Optional | Performance optimization |
| ✅ | `backend/app/compliance/amc_compliance_rs.dll` | Compiled Rust library | ⚠️ Optional | Rust code |
| ❌ | `rust/Cargo.toml` | Rust project manifest | ⚠️ Optional | If maintaining Rust |
| ❌ | `rust/src/` | Rust source code | ⚠️ Optional | If maintaining Rust |
| ❌ | `rust/build.sh` | Rust build script | ⚠️ Optional | If maintaining Rust |

**Recommendation**: Document Rust integration clearly - is it required or optional? How to build?

---

## Summary & Recommendations

### Critical Missing Files (Implement First)

1. **Testing Infrastructure**
   - `backend/tests/` - Complete test suite
   - `mf-context-engine/tests/` - Frontend tests
   - `backend/pytest.ini` - Test configuration

2. **Configuration**
   - `backend/.env` - Local environment (from .env.example)
   - `backend/pyproject.toml` - Modern Python project config
   - `mf-context-engine/tsconfig.json` - TypeScript config

3. **CI/CD**
   - `.github/workflows/test.yml` - Automated testing
   - `.github/workflows/deploy.yml` - Deployment automation

4. **Documentation**
   - `LICENSE` - Legal protection
   - `CHANGELOG.md` - Version tracking
   - `CONTRIBUTING.md` - Team guidelines

### Cleanup Recommendations

1. **Consolidate FAISS**: Single location for indexes
2. **Organize Documentation**: Move root .md files to `Docs/` subdirectories
3. **Review Test Files**: Move to proper directories with `.test.js` naming
4. **Remove Temporary Files**: Clean up `mock_run.bat`, `temp_test.bat`, etc.
5. **Document Purpose**: Add README files to key directories explaining their purpose

### Architecture Gaps

1. **SQLite Schema**: Extract to separate `.sql` files for clarity
2. **Database Migrations**: Implement migration system (Alembic)
3. **API Versioning**: Consider API version strategy (`/api/v1/`, `/api/v2/`)
4. **Secrets Management**: Document AWS Secrets Manager usage more clearly

### File Organization Score

- **Backend**: 7/10 - Well structured, missing tests
- **Frontend**: 6/10 - Good structure, needs TypeScript config and proper test organization
- **Database**: 7/10 - Working, but schema documentation needed
- **Documentation**: 5/10 - Lots of docs, but disorganized
- **Deployment**: 8/10 - Good Docker/AWS setup
- **CI/CD**: 3/10 - Missing automation
- **Testing**: 2/10 - Minimal test infrastructure

---

**Total Files Inventoried**: 200+ existing, 50+ recommended
**Completion Status**: ~75% of expected project files exist
**Priority**: Focus on testing, CI/CD, and documentation organization

---

*This document should be updated as the project evolves. Review quarterly or on major architectural changes.*
