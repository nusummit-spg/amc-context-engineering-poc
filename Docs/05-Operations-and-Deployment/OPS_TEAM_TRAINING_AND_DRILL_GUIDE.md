# Operations Team Training Manual & Simulation Drill Guide

**Document Version:** 1.0  
**Target Audience:** DevOps Engineers, Site Reliability Engineers (SRE), L1/L2 Operations Support  
**Target Systems:** `amc-platform` (port 8000), `amc-feedback-loop` (port 8001), `amc-repair-engine` (port 8002)  
**Related Runbook:** [`Docs/05-Operations-and-Deployment/MICROSERVICES_RUNBOOK.md`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/Docs/05-Operations-and-Deployment/MICROSERVICES_RUNBOOK.md)

---

## 1. Executive Summary & Architecture Overview

The AMC Context-Engineering Platform employs a **resilient hybrid microservices architecture** that balances decoupling with fault tolerance.

```
                              ┌───────────────────────────────────────────────┐
                              │            FastAPI Platform API               │
                              │                 (Port 8000)                   │
                              └───────┬───────────────────────────────┬───────┘
                                      │                               │
                      HTTP / Retries  │               HTTP / Retries  │
                      + Breaker Guard │               + Breaker Guard │
                                      ▼                               ▼
                 ┌───────────────────────────┐   ┌───────────────────────────┐
                 │    Feedback Service       │   │    Repair Engine Service  │
                 │       (Port 8001)         │   │       (Port 8002)         │
                 └─────────────┬─────────────┘   └─────────────┬─────────────┘
                               │                               │
                               ▼                               ▼
                        [ SQLite / PG ]                 [ Redis / Neo4j ]
                                ▲                               ▲
                                │                               │
                 Fallback:      └────── In-Process Fallback ────┘
                 (If Breaker OPEN or MICROSERVICES_MODE=false)
```

### Core Reliability Principles:
1. **Circuit Breakers on All Outbound Client Calls:**
   - Outbound requests to ports 8001 and 8002 are guarded by `CircuitBreaker`.
   - **Tripping Threshold:** 5 consecutive failures triggers state change from `CLOSED` to `OPEN`.
   - **Fail-Safe Behavior:** When `OPEN`, requests bypass network calls immediately and use local in-process fallback packages without crashing the user request.
   - **Self-Healing:** After 60 seconds (`recovery_timeout`), breaker enters `HALF_OPEN` and sends 2 canary probes. If both succeed, it recovers to `CLOSED`.
2. **Dual-Mode Operation:**
   - `MICROSERVICES_MODE=true` (Default Production): Microservices run in independent containers.
   - `MICROSERVICES_MODE=false` (Monolithic Recovery Mode): Single container fallback using installed Python packages in-process.

---

## 2. Walkthrough of the Operations Runbook

This section guides you through the day-to-day procedures detailed in the [`MICROSERVICES_RUNBOOK.md`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/Docs/05-Operations-and-Deployment/MICROSERVICES_RUNBOOK.md).

### 2.1 Daily Lifecycle Management

| Action | Command | Purpose |
|--------|---------|---------|
| **Start Stack** | `docker-compose up -d` | Launch all containers in detached mode |
| **Stop Stack** | `docker-compose down` | Gracefully shut down all containers |
| **Inspect Health** | `docker-compose ps` | Ensure all services report `Up (healthy)` |
| **Live Logs (All)** | `docker-compose logs -f --tail=100` | Stream aggregated logs |
| **Targeted Logs** | `docker-compose logs -f feedback-service` | Stream feedback service logs |
| **Resource Usage** | `docker stats` | Live CPU and RAM consumption across containers |

### 2.2 Health Check & Diagnostic Endpoints

All services expose a standard `/api/health` endpoint:

```bash
# 1. Platform API
curl -f http://localhost:8000/api/health
# Expected: {"status":"healthy", ...}

# 2. Feedback Service
curl -f http://localhost:8001/api/health
# Expected: {"status":"healthy","service":"feedback-loop","version":"0.1.0", ...}

# 3. Repair Engine Service
curl -f http://localhost:8002/api/health
# Expected: {"status":"healthy","service":"repair-engine","version":"0.1.0", ...}

# 4. Circuit Breaker Telemetry
curl -f http://localhost:8000/api/metrics/circuit-breakers
```

---

## 3. Hands-On Simulation Drills (Ops Team Training)

Execute these 4 operational drills in a staging environment to master incident triage.

---

### Drill 1: Circuit Breaker Trip & Self-Healing Recovery Drill

**Objective:** Observe the platform automatically isolate a failing downstream service and self-heal when restored.

#### Step 1: Simulate Service Failure
Stop the repair engine service:
```bash
docker-compose stop repair-service
```

#### Step 2: Trigger Service Traffic & Observe Circuit Breaker Trip
Send 5 requests that query repair patches:
```bash
for i in {1..6}; do
  curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost:8000/api/metrics/circuit-breakers
done
```

#### Step 3: Inspect Circuit Breaker Status & Alerts
Query the circuit breaker telemetry endpoint:
```bash
curl http://localhost:8000/api/metrics/circuit-breakers
```
**Expected Output:**
```json
{
  "timestamp": 1790597530.0,
  "circuit_breakers": {
    "repair-service": {
      "state": "open",
      "healthy": false,
      "metrics": {
        "failure_count": 5,
        "total_trips": 1,
        "state": "open"
      }
    }
  }
}
```

Notice that platform requests continue returning HTTP 200 because the platform seamlessly falls back to the local in-process fallback package.

#### Step 4: Restore the Downstream Service
Start the repair engine container:
```bash
docker-compose start repair-service
```

#### Step 5: Verify Automatic Canary Probe & Recovery
Wait 60 seconds (or configured `CIRCUIT_BREAKER_RECOVERY_TIMEOUT`). The breaker transitions to `HALF_OPEN`. After 2 successful probe calls, observe:
```bash
curl http://localhost:8000/api/metrics/circuit-breakers
```
**State returns to:** `"state": "closed"`, `"healthy": true`. An `INFO` recovery alert is emitted: `"RECOVERED_CLOSED"`.

---

### Drill 2: 5-Minute Emergency Monolithic Failover Drill

**Objective:** Restore 100% platform functionality within 5 minutes if Docker networking, DNS, or microservice containers catastrophically fail.

#### Incident Trigger:
A severe bridge network glitch prevents container-to-container communication.

#### Resolution Steps:
1. Open environment configuration:
   ```bash
   nano .env
   ```
2. Toggle the microservices mode flag:
   ```env
   MICROSERVICES_MODE=false
   ```
3. Restart the core API container:
   ```bash
   docker-compose restart api
   ```
4. Verify platform health:
   ```bash
   curl http://localhost:8000/api/health
   ```
5. **Outcome:** The platform now executes feedback and repair operations directly in-process using the pre-installed editable packages `amc-feedback-loop` and `amc-repair-engine`. Zero dependencies on ports 8001/8002.

---

### Drill 3: Weekly Governance Batch Inspection & Manual Trigger Drill

**Objective:** Audit, inspect, and trigger the scheduled Friday governance batch.

#### Step 1: Check Current Pending Patches
```bash
curl http://localhost:8002/api/patches/pending
```

#### Step 2: Trigger Governance Batch Manually
```bash
curl -X POST http://localhost:8002/api/governance/run-batch \
  -H "Content-Type: application/json" \
  -d '{"auto_approve_threshold": 0.95}'
```

#### Step 3: Inspect Execution Report
**Expected Output:**
```json
{
  "status": "completed",
  "evaluated_count": 12,
  "approved_count": 10,
  "promoted_to_graph": 10,
  "execution_time_ms": 42.5
}
```

---

### Drill 4: Prometheus Metrics & Alerting Drill

**Objective:** Confirm Prometheus scrapes circuit breaker metrics and triggers alerts when a service degrades.

#### Step 1: Inspect Raw Prometheus Exposition
```bash
curl http://localhost:8000/metrics
```
Filter for circuit breaker metrics:
```bash
curl -s http://localhost:8000/metrics | grep "amc_circuit_breaker"
```
**Expected Output:**
```prometheus
# HELP amc_circuit_breaker_state Current state: 0=CLOSED, 1=OPEN, 2=HALF_OPEN
# TYPE amc_circuit_breaker_state gauge
amc_circuit_breaker_state{service="feedback-service"} 0
amc_circuit_breaker_state{service="repair-service"} 0

# HELP amc_circuit_breaker_trips_total Total times circuit breaker tripped to OPEN
# TYPE amc_circuit_breaker_trips_total counter
amc_circuit_breaker_trips_total{service="feedback-service"} 0
amc_circuit_breaker_trips_total{service="repair-service"} 0
```

#### Step 2: Prometheus Alert Rule Mapping
Verify [`prometheus_alerts.yml`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/Docs/05-Operations-and-Deployment/prometheus_alerts.yml) is mounted in your Prometheus configuration:
- `CircuitBreakerTrippedOpen`: Fires after 10s if `amc_circuit_breaker_state == 1` (`severity: critical`).
- `CircuitBreakerProbingHalfOpen`: Fires if `amc_circuit_breaker_state == 2` (`severity: warning`).
- `CircuitBreakerRapidTripRate`: Fires if `increase(amc_circuit_breaker_trips_total[5m]) > 2`.

---

## 4. Concurrency & Load Capacity Reference

The platform has been benchmarked and validated under heavy concurrent load:

| Concurrency Level | Throughput | P50 Latency | P95 Latency (SLA < 500ms) | Error Rate | Status |
|-------------------|------------|-------------|----------------------------|------------|--------|
| **50 Users**      | 2,802 req/s| 0.32 ms     | 0.57 ms                    | 0.0%       | PASS   |
| **100 Users**     | 2,791 req/s| 0.32 ms     | 0.57 ms                    | 0.0%       | PASS   |

### Running the Load Test on Staging / Production:
```bash
# In-process ASGI benchmark
python scripts/run_load_test.py --users 50,100 --reqs-per-user 5

# Live target benchmark
python scripts/run_load_test.py --base-url http://localhost:8000 --users 50,100
```
Benchmark reports are automatically archived to:  
[`backend/evaluation/results/load_testing_microservices_50_100.json`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/evaluation/results/load_testing_microservices_50_100.json)

---

## 5. Incident Triage Decision Tree

```
                      Incident Alert Received
                                │
               Is /api/health responding on 8000?
                      ├── NO ──► Check Container/Docker Host Logs
                      │          Check Port 8000 Conflicts
                      │          Fallback: Run in-process
                      │
                      └── YES
                                │
               Check /api/metrics/circuit-breakers
                      ├── All "closed" ──► Inspect Neo4j / LLM APIs
                      │
                      └── Breaker is "open" on Port 8001 or 8002
                                │
                      Can you reach service directly?
                      (curl http://localhost:8001/api/health)
                      ├── YES ──► Breaker will recover in 60s
                      │           Observe HALF_OPEN -> CLOSED
                      │
                      └── NO ──► Check specific service logs:
                                 docker-compose logs repair-service
                                 Restart container:
                                 docker-compose restart repair-service
                                 If persists > 5 min:
                                 Set MICROSERVICES_MODE=false
```

---

## 6. SRE Shift Handover & Weekly Checklist

- [ ] **Daily (08:00 UTC):** Review `/api/metrics/circuit-breakers` for any trip events in the last 24h.
- [ ] **Daily (12:00 UTC):** Check `docker stats` memory usage across `feedback-service` and `repair-service`.
- [ ] **Friday (09:00 UTC):** Verify weekly governance batch completion via `/api/patches/pending`.
- [ ] **Monthly:** Backup SQLite / PostgreSQL feedback stores and test disaster recovery failover drill.
