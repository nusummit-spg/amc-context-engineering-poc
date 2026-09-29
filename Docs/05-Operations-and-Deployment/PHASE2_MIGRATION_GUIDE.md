# Phase 2 Migration Guide: Monolithic to Microservices

**Document Version:** 1.0  
**Status:** ACTIVE  
**Audience:** Platform Engineers, DevOps, Site Reliability Engineers  
**Target Architecture:** AMC Context Engineering Modular Microservices Stack

---

## 1. Executive Overview

This guide provides the operational procedures for transitioning the AMC Context Engineering Platform from a monolithic, in-process architecture to a decoupled, multi-container microservices deployment.

- **Estimated Migration Timeline:** 1–2 weeks (Staging validation + Production deployment)
- **Target Downtime:** Zero downtime (via Blue-Green deployment with reverse proxy / load balancer)
- **Rollback Window:** < 5 minutes (via immediate feature flag revert or traffic redirect)

### Architectural Transformation

```
Monolithic Mode (Default):
┌────────────────────────────────────────────────────────┐
│  AMC Platform Orchestrator (Port 8000)                 │
│  - In-process amc-feedback-loop                        │
│  - In-process amc-repair-engine                        │
│  - Shared SQLite/PostgreSQL & Memory/Redis Cache       │
└────────────────────────────────────────────────────────┘

Microservices Mode (Distributed):
┌────────────────────────────────────────────────────────┐
│  AMC Platform Orchestrator (Port 8000)                 │
│  - ServiceClient / CircuitBreaker                      │
└──────────────┬─────────────────────────┬───────────────┘
               │ HTTP REST               │ HTTP REST
               ▼                         ▼
┌─────────────────────────┐    ┌─────────────────────────┐
│ Feedback Loop (Port 8001)│    │ Repair Engine (Port 8002)│
│ - NER / GLiNER Pipeline │    │ - Hot Patch Store       │
│ - Claim Extraction      │    │ - Governance Batch      │
│ - Dedicated DB Adapter  │    │ - Neo4j / Redis Adapter │
└─────────────────────────┘    └─────────────────────────┘
```

---

## 2. Pre-Migration Checklist

Before initiating migration in any environment, verify:

- [ ] **Infrastructure Prerequisites:**
  - Docker 24.0+ and Docker Compose v2.20+ installed.
  - Neo4j 5.24+ running and responding to Cypher health queries (`bolt://neo4j:7687`).
  - Redis 7+ operational for patch caching (`redis:6379`).
  - Persistent volume storage configured for `/data` and `/root/.cache`.
- [ ] **Code & Artifact Verification:**
  - `amc-feedback-loop` package wheels built or installed in editable mode.
  - `amc-repair-engine` package wheels built or installed in editable mode.
  - Container health check endpoints active:
    - Feedback: `curl -f http://localhost:8001/api/health`
    - Repair: `curl -f http://localhost:8002/api/health`
- [ ] **Backups & State Preservation:**
  - Full backup of relational database (`feedback.db` / PostgreSQL).
  - Snapshot / dump of Neo4j graph store (`neo4j-admin database dump`).
  - Redis RDB / AOF dump.

---

## 3. Migration Paths

### Path A: Development and Staging Environments (Direct Cut-Over)

Suitable for non-production environments where brief maintenance windows are acceptable:

1. Stop existing monolithic stack:
   ```bash
   docker-compose down
   ```
2. Set environment variables in `.env`:
   ```env
   MICROSERVICES_MODE=true
   FEEDBACK_SERVICE_URL=http://feedback-service:8001
   REPAIR_SERVICE_URL=http://repair-service:8002
   CIRCUIT_BREAKER_ENABLED=true
   ```
3. Build and launch all containers:
   ```bash
   docker-compose up -d --build
   ```
4. Verify health checks:
   ```bash
   curl -f http://localhost:8000/api/health
   curl -f http://localhost:8001/api/health
   curl -f http://localhost:8002/api/health
   ```

### Path B: Production Environment (Blue-Green Rollout)

Ensures continuous service availability with instant rollback capability:

1. **Phase 1: Pre-Migration Validation**
   - Deploy `feedback-service` and `repair-service` containers alongside the existing monolithic stack without routing public traffic.
   - Run integration smoke tests against ports 8001 and 8002.
2. **Phase 2: Deploy Green Orchestrator**
   - Launch Green orchestrator instances with `MICROSERVICES_MODE=true`.
   - Run automated validation suite against the Green cluster.
3. **Phase 3: Gradual Canary Traffic Shift**
   - Shift 10% traffic to Green.
   - Monitor circuit breaker metrics, latency, and error rates for 4 hours.
   - Incrementally increase to 50%, then 100%.
4. **Phase 4: Decommission Monolith**
   - Retain Blue (monolithic) instances in standby for 24 hours.
   - Safely shut down Blue cluster once stability criteria are met.

---

## 4. Step-by-Step Migration Execution

### Step 1: Package and Container Build
```bash
# Build standalone microservice images
docker-compose build feedback-service repair-service
```

### Step 2: Start Up Auxiliary Services
```bash
# Ensure Neo4j and Redis are healthy first
docker-compose up -d neo4j redis
docker-compose ps
```

### Step 3: Launch Microservices
```bash
docker-compose up -d feedback-service repair-service
```

### Step 4: Verify Service Health
```bash
# Check Feedback Service
curl -s http://localhost:8001/api/health | jq .
# Expected: {"status":"healthy","service":"feedback-loop",...}

# Check Repair Engine Service
curl -s http://localhost:8002/api/health | jq .
# Expected: {"status":"healthy","service":"repair-engine",...}
```

### Step 5: Enable Microservices Mode on Platform
Update `backend/.env`:
```env
MICROSERVICES_MODE=true
FEEDBACK_SERVICE_URL=http://feedback-service:8001
REPAIR_SERVICE_URL=http://repair-service:8002
SERVICE_TIMEOUT=30.0
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60.0
```
Restart API orchestrator:
```bash
docker-compose restart api
```

---

## 5. Rollback Procedures

### Emergency Rollback (< 5 minutes)

If catastrophic communication failures or latency spikes occur:

1. **Option 1: Hot Switch via Environment Variable**
   - In `backend/.env`, set:
     ```env
     MICROSERVICES_MODE=false
     ```
   - Restart the API container:
     ```bash
     docker-compose restart api
     ```
   - The platform will immediately revert to in-process package execution without container rebuilds.

2. **Option 2: Reverse Proxy / Load Balancer Switch**
   - If using Blue-Green routing, revert the target group rule to route 100% traffic back to Blue instances.

### Data Rollback Procedure
If data corruption occurred in the standalone feedback database:
1. Stop the feedback container: `docker-compose stop feedback-service`
2. Restore the pre-migration SQLite / PostgreSQL backup.
3. Restart the service: `docker-compose start feedback-service`

---

## 6. Troubleshooting & Diagnostics

| Symptom | Probable Cause | Corrective Action |
|---------|----------------|-------------------|
| Circuit breaker OPEN in orchestrator logs | Service down or network failure | Inspect `docker-compose logs feedback-service` or `repair-service`. Check container connectivity via `docker exec -it <api_id> curl http://feedback-service:8001/api/health`. |
| Container exits immediately with error | Missing environment variables or database write error | Verify `DATABASE_URL`, `REDIS_HOST`, and `NEO4J_URI` inside container environment. Ensure volumes have proper write permissions. |
| Patches not appearing in retrieval context | Confidence threshold or entity ID mismatch | Check `/api/patches/for-entities?entity_ids=<ID>` on port 8002. Ensure patch confidence >= 0.70. |

---

## 7. Post-Migration Verification

Verify the following end-to-end user journeys:
1. Submit query: `POST http://localhost:8000/api/query` -> verify response generated.
2. Submit feedback: `POST http://localhost:8001/api/feedback` -> verify correction detected.
3. Check hot patch: `GET http://localhost:8002/api/patches/pending` -> verify patch registered.
4. Execute governance batch: `POST http://localhost:8002/api/governance/run-batch` -> verify patch promoted.
5. Re-run query -> verify updated canonical value reflected in generated context.
