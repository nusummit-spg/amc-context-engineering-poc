# Phase 2 Modularization & Migration Runbook

## Overview
This runbook details how to operate and deploy the modularized AMC Context Engineering Platform. The platform has transitioned from a tightly-coupled monolith to clean, decoupled microservices and standalone pip packages.

---

## 1. Modular Components

| Component | Path | Responsibility | Standalone Server |
|---|---|---|---|
| **AMC Feedback Loop** | `packages/amc-feedback-loop` | Feedback capture, Entity Resolution, Dissatisfaction detection | Port `8001` (`uvicorn amc_feedback.server:app`) |
| **AMC Repair Engine** | `packages/amc-repair-engine` | Hot patch store, Tiered evaluation, Governance batch | Port `8002` (`uvicorn amc_repair.server:app`) |
| **Platform Orchestrator** | `backend/` | Query routing, Vector/Graph retrieval, Groq synthesis | Port `8000` (`uvicorn app.main:app`) |

---

## 2. Deployment Paths

### Path A: In-Process Library Mode (Development & Staging)
In library mode, the backend platform consumes `amc_feedback` and `amc_repair` directly as Python packages linked in editable mode:
```powershell
cd backend
pip install -e ..\packages\amc-feedback-loop
pip install -e ..\packages\amc-repair-engine
```
- Communication occurs in-process via `app.core.adapters` (`SQLiteAdapter`, `PlatformNeo4jGraphAdapter`, `MemoryCacheAdapter`).
- Zero network overhead, single container deployment.

### Path B: Distributed Microservices Mode (Production / Blue-Green)
In microservices mode, each service runs in an isolated container managed by Docker Compose or Kubernetes:
```bash
docker compose up -d
```
- **Service Mesh**:
  - `http://api:8000` - AMC Platform Gateway
  - `http://feedback-service:8001` - Feedback ingestion microservice
  - `http://repair-service:8002` - Repair & patch governance microservice
  - `neo4j:7687` - Knowledge Graph
  - `redis:6379` - Distributed Hot Patch Cache
- **Resilience**: The backend incorporates `CircuitBreaker` patterns (`app.clients.circuit_breaker`) to guarantee that if external services degrade or fail, query synthesis degrades gracefully without crashing.

---

## 3. ONNX GLiNER Acceleration
The NER layer has been optimized using ONNX INT8 Quantization:
- **Model Path**: `backend/models/gliner_quantized.onnx`
- **Latency**: Reduced from 9,000–30,000ms down to **~72ms–123ms** (over 95% speedup).
- **Fallback**: Automatic fallback to PyTorch GLiNER if ONNX model is missing or unsupported.
- **Verification**:
  ```powershell
  python backend/scripts/benchmark_onnx_ner.py
  ```

---

## 4. Verification Suite
Execute the integration and regression test suites:
```powershell
# 1. Package Unit Tests
cd packages/amc-feedback-loop && pytest tests -v
cd ../amc-repair-engine && pytest tests -v

# 2. Integration Health Validation
cd ../../backend
pytest tests/integration/test_background_jobs.py -v
pytest tests/integration/test_complete_feedback_loop.py -v
pytest tests/integration/test_phase2_modular_integration.py -v

# 3. Core Platform Regression
pytest tests/test_live_feedback_loop.py -v
```
