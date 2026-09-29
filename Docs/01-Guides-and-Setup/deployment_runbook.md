# 📖 AMC Platform — Operations & Deployment Runbook
**Target Audience:** DevOps Engineers, Platform Operators, and System Administrators  
**Platform Version:** 1.0 (Phase 1 Production Hardening)  
**Date:** September 2026  

---

## 1. System Overview & Architecture

The AMC ContextGraph Platform is an institutional-grade knowledge retrieval and compliance system built with FastAPI, Neo4j graph traversal, FAISS vector indexing, Groq LLM synthesis, and an autonomous human-feedback self-healing loop.

```
                    ┌────────────────────────────────────────┐
                    │          FastAPI App Engine            │
                    │  (Port 8000 / Reverse Proxy NGINX)     │
                    └────┬──────────────┬──────────────┬─────┘
                         │              │              │
        ┌────────────────▼───┐  ┌───────▼──────┐  ┌────▼─────────────────┐
        │  FAISS Vector DB   │  │ Neo4j Graph  │  │   SQLite data.db     │
        │  (./data/faiss)    │  │ (Port 7687)  │  │ (Evidence/Feedback)  │
        └────────────────────┘  └──────────────┘  └──────────────────────┘
                         │              │              │
                    ┌────▼──────────────▼──────────────▼─────┐
                    │     Self-Healing Correction Layer      │
                    │   (TTL-backed in-memory / Redis cache) │
                    └────────────────────────────────────────┘
```

### Key Operational Characteristics (Phase 1)
- **Single-Instance Deployment**: Optimized for 10–50 concurrent AMC analysts.
- **Resilient Fallbacks**: Runs seamlessly even if Neo4j is offline by gracefully switching to vector/FAISS retrieval.
- **Zero-External Cache Dependency**: Correction Patch Layer operates with thread-safe in-memory cache and automatic TTL expiration.

---

## 2. Environment Configuration

All operational configuration is managed via `.env` in the `backend/` directory:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `local` | `local`, `staging`, or `production` |
| `LOG_LEVEL` | `INFO` | Logging severity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FORMAT` | `text` | Set to `json` for machine-readable structured JSON logs |
| `LOG_FILE` | `logs/app.log` | Destination path for rotating log files |
| `ENABLE_FILE_LOGGING` | `true` | Enables JSON structured log persistence to disk |
| `ENABLE_STREAMING` | `true` | Server-Sent Events (SSE) streaming responses |
| `ENABLE_TIER2_NLI_EVALUATION` | `false` | Tier 2 NLI semantic alignment evaluator |
| `ENABLE_TIER3_LLM_JUDGE` | `false` | Tier 3 LLM Judge arbitration |
| `TIER2_NLI_CONFIDENCE_THRESHOLD` | `0.85` | STOP-2 gate confidence threshold |
| `NEO4J_URI` | `bolt://localhost:7687` | Knowledge graph connection URI |
| `NEO4J_USER` | `neo4j` | Knowledge graph username |
| `NEO4J_PASSWORD` | `contextgraph` | Knowledge graph password |
| `FAISS_DIR` | `./data/faiss` | Path containing vector index files |
| `AUTH_SECRET_KEY` | *(Set strong key)* | HMAC signing key for session authentication |

---

## 3. Service Startup & Verification

### Step 3.1: Python Virtual Environment Activation
Always execute commands using the dedicated project virtualenv:
```powershell
# Windows PowerShell
.\backend\.venv\Scripts\Activate.ps1
```

### Step 3.2: Launch FastAPI Server
```powershell
# From the backend directory:
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### Step 3.3: Health Check Verification
Immediately verify that all subsystems report healthy status:
```powershell
curl http://localhost:8000/health
```
**Expected Response (HTTP 200):**
```json
{
  "status": "ok",
  "components": {
    "database": {"status": "ok"},
    "neo4j": {"status": "ok", "mode": "graph"},
    "vector_store": {"status": "ok", "type": "faiss"},
    "llm": {"status": "ok", "provider": "groq"},
    "scheduler": {"status": "ok", "running": true}
  }
}
```

---

## 4. Monitoring & Telemetry

### 4.1 Real-Time Metrics Dashboard
The platform serves a built-in, lightweight operational dashboard:
- **URL**: `http://localhost:8000/metrics/dashboard` (or `http://localhost:8000/api/metrics/dashboard`)
- **Key Metrics Displayed**:
  - Total Queries served
  - Latency: p50 (target < 1,800ms) and p99 tail latency
  - Cache Hit Rate (%)
  - HTTP 4xx/5xx Error Rates
  - Average token usage and hallucination rate
  - Live query activity log

### 4.2 Prometheus Scraping
- **Scrape Target**: `http://localhost:8000/api/metrics/prometheus`
- **Sample Configuration (`prometheus.yml`)**:
  ```yaml
  scrape_configs:
    - job_name: "amc_platform"
      scrape_interval: 15s
      metrics_path: "/api/metrics/prometheus"
      static_configs:
        - targets: ["localhost:8000"]
  ```

### 4.3 Structured Logging & Request Tracing
When `LOG_FORMAT=json` is configured, logs are written in structured JSON:
```json
{
  "timestamp": "2026-09-25T07:25:00.123456+00:00",
  "level": "INFO",
  "logger": "api",
  "message": "rid=a1b2c3d4 POST /api/query -> 200 (1540ms)",
  "request_id": "a1b2c3d4",
  "session_id": "sess_9876",
  "module": "logging",
  "line": 154
}
```
- Request correlation is propagated via the `X-Request-ID` and `X-Session-ID` headers.
- Slow requests exceeding 1,000ms automatically log a `[SLOW_REQUEST]` warning.

---

## 5. Database Backup & Restore Procedures

### 5.1 SQLite `data.db` Backup
The operational feedback, evidence packs, and evaluation records reside in `data.db`:
```powershell
# Create an online SQLite backup snapshot
sqlite3 backend/data.db ".backup 'backend/backups/data_backup_$(Get-Date -Format yyyyMMdd_HHmmss).db'"
```

### 5.2 Restore SQLite Database
1. Stop the FastAPI process.
2. Replace `backend/data.db` with the backup snapshot.
3. Restart the FastAPI service and verify `/health`.

---

## 6. Troubleshooting Common Incidents

| Symptom | Probable Cause | Corrective Action |
| :--- | :--- | :--- |
| `/health` reports `neo4j: degraded` | Neo4j service stopped or credentials incorrect. | App runs in vector fallback mode. Verify Neo4j status with `bolt://localhost:7687` and restart Neo4j service. |
| Slow query response (> 3,000ms) | Model cold start or un-cached complex query. | First request warms up FAISS/Embedder models. Subsequent queries hit cache or warm models. Check `[SLOW_REQUEST]` logs. |
| 429 Rate Limit Errors | IP or user query quota exceeded. | Check client rate limit headers (`X-RateLimit-Remaining`). Increase client throttle or whitelist internal IP in `middleware.py`. |
| In-memory patches reset after restart | In-memory fallback was used instead of Redis. | Expected behavior for in-memory mode. Approved patches promoted to Neo4j remain permanent. |

---

## 7. Rollback Plan

If a release introduces unexpected regressions:
1. Revert Git repository to the last tagged stable commit:
   ```bash
   git checkout <stable-tag-or-commit>
   ```
2. Restore SQLite database snapshot from the pre-deployment backup.
3. Restart FastAPI service:
   ```powershell
   python -m uvicorn app.main:app --port 8000
   ```
4. Run the automated regression test suite:
   ```powershell
   pytest tests/test_health_endpoint.py tests/test_e2e_user_journey_feedback_repair.py
   ```
