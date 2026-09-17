# Context Engineering Platform

> Enterprise-grade RAG and Graph Knowledge Platform for Asset Management Companies (AMCs) and SEBI Compliance.

---

## 🌟 Quick Links

- **New Developer?** Start with [**00_START_HERE**](./Docs/01-Guides-and-Setup/00_START_HERE.md) and the [**Quick Start Checklist**](./Docs/01-Guides-and-Setup/QUICK_START_CHECKLIST.md).
- **Chief Architect?** Review [**00_CHIEF_ARCHITECT_START_HERE**](./Docs/01-Guides-and-Setup/00_CHIEF_ARCHITECT_START_HERE.md) and the [**Chief Architect Review**](./Docs/04-Audits-and-Compliance/CHIEF_ARCHITECT_REVIEW.md).
- **Operations & Deployment?** Check the [**Deployment Guide**](./Docs/05-Operations-and-Deployment/DEPLOYMENT_GUIDE.md) and [**Operator Runbook**](./Docs/05-Operations-and-Deployment/OPERATOR_RUNBOOK.md).
- **Looking for Full Documentation?** Visit the central [**Documentation Hub (`Docs/`)**](./Docs/README.md).

---

## 📂 Documentation Directory Overview

All project documentation is organized under the [`Docs/`](./Docs/README.md) folder into 10 structured categories:

| Category | Contents |
| :--- | :--- |
| [**`01-Guides-and-Setup/`**](./Docs/01-Guides-and-Setup/) | Developer onboarding, user manual, video walkthrough, and troubleshooting guides |
| [**`02-Architecture-and-Design/`**](./Docs/02-Architecture-and-Design/) | System architecture, zero-token warm cache, Neo4j graph models, and DDL schemas |
| [**`03-Implementation-Plans/`**](./Docs/03-Implementation-Plans/) | Feature tracks 3–8, master engineering plans, and convergence roadmaps |
| [**`04-Audits-and-Compliance/`**](./Docs/04-Audits-and-Compliance/) | Codebase audit reports, SEBI compliance audits, 45-pillar IP defense, and defect logs |
| [**`05-Operations-and-Deployment/`**](./Docs/05-Operations-and-Deployment/) | Production deployment guides, compliance runbooks, and incident response SOPs |
| [**`06-Evaluation-and-Testing/`**](./Docs/06-Evaluation-and-Testing/) | Retrieval latency profiling, multi-turn test suites, and benchmark comparisons |
| [**`07-Frontend-and-UI/`**](./Docs/07-Frontend-and-UI/) | React app design, design system tokens, Streamlit migration diff, and wireframes |
| [**`08-Research-and-Feedback/`**](./Docs/08-Research-and-Feedback/) | Website crawl manifests, human feedback loop designs, and meeting notes |
| [**`09-Diagrams-and-Presentations/`**](./Docs/09-Diagrams-and-Presentations/) | Interactive HTML flowcharts, visual architecture maps, and presentation decks |
| [**`10-Historical-and-Phases/`**](./Docs/10-Historical-and-Phases/) | Historical phase documentation (Phases 0 through 4), legacy reports, and audit archives |

---

## 🏗️ Architecture & Technology Stack

- **Frontend**: React 19, Vite 8, Tailwind CSS, Oxlint (`mf-context-engine/`)
- **Backend API**: FastAPI 0.115, Python 3.10+ (`backend/`)
- **Knowledge Graph**: Neo4j 5.24 (CYPHER queries, schema constraints)
- **Vector Store**: FAISS (`backend/app/engine/faiss_indexes/`)
- **Application DB**: SQLite (query evidence, audit trails, user authentication)
- **Containerization**: Docker Compose (`docker-compose.yml`)

---

## 🚀 Running the Platform

### Local Development (Windows)
```cmd
run_project.bat
```

### Backend Tests
```cmd
cd backend
pytest
```

For detailed setup instructions, please see the [**Installation Guide**](./Docs/01-Guides-and-Setup/IMPLEMENTATION_QUICK_START.md).
