# Microservices Operations Runbook

**Document Version:** 1.0  
**Target Services:** `amc-platform` (API), `amc-feedback-loop`, `amc-repair-engine`  
**Classification:** Internal Operations & SRE Runbook

---

## 1. Daily Operations & Service Control

### 1.1 Managing All Services
```bash
# Start all microservices in detached mode
docker-compose up -d

# Stop all microservices gracefully
docker-compose down

# Restart a single service
docker-compose restart feedback-service
docker-compose restart repair-service
docker-compose restart api
```

### 1.2 Inspecting Live Logs
```bash
# Follow logs across all microservices
docker-compose logs -f --tail=100

# Follow logs for specific services
docker-compose logs -f feedback-service
docker-compose logs -f repair-service
docker-compose logs -f api
```

### 1.3 Container Health Status
```bash
docker-compose ps
```
All containers should report `Up (healthy)`.

---

## 2. Health Check & Diagnostics API Matrix

| Service | Port | Health Endpoint | Healthy Response Schema |
|---------|------|-----------------|-------------------------|
| Platform Orchestrator | 8000 | `/api/health` | `{"status":"ok",...}` |
| Feedback Loop Service | 8001 | `/api/health` | `{"status":"healthy","service":"feedback-loop","version":"0.1.0",...}` |
| Repair Engine Service | 8002 | `/api/health` | `{"status":"healthy","service":"repair-engine","version":"0.1.0",...}` |

### Quick Diagnostic Curl Command
```bash
curl -f http://localhost:8000/api/health && echo " API: OK"
curl -f http://localhost:8001/api/health && echo " Feedback: OK"
curl -f http://localhost:8002/api/health && echo " Repair: OK"
```

---

## 3. Common Incidents & Rapid Resolution

### Incident A: Circuit Breaker Tripped to OPEN State
- **Symptoms:** Logs contain `Circuit OPEN -> reject calls` or `Repair service circuit breaker OPEN, falling back to local`. Platform queries remain operational but without dynamic hot-patching.
- **Root Cause:** 5 consecutive connection timeouts or 5xx errors from port 8002 or 8001.
- **Resolution Steps:**
  1. Check repair service status: `docker-compose ps repair-service`.
  2. Check container memory and resource exhaustion: `docker stats repair-service`.
  3. Inspect logs: `docker-compose logs --tail=100 repair-service`.
  4. Test raw connectivity: `curl -v http://localhost:8002/api/health`.
  5. Restart the failing microservice: `docker-compose restart repair-service`.
  6. The circuit breaker will automatically transition from `OPEN` to `HALF_OPEN` after 60 seconds (or configured `CIRCUIT_BREAKER_RECOVERY_TIMEOUT`), and to `CLOSED` after 2 successful probe calls.

### Incident B: Service Fails to Start (Healthcheck Failing)
- **Symptoms:** Container status shows `unhealthy` or restarts continuously.
- **Root Cause:**
  - Missing dependent containers (Redis or Neo4j).
  - Port conflict on 8001 or 8002.
  - Corrupt local SQLite database file in volume mount.
- **Resolution Steps:**
  1. Inspect startup stack trace: `docker-compose logs --tail=200 feedback-service`.
  2. Check port allocation: `netstat -ano | findstr "8001"` (Windows) or `ss -tulpn | grep 8001` (Linux).
  3. Verify volume write permissions: Ensure the user running docker has read/write privileges on `feedback_data` volume.

### Incident C: High Latency in Query Synthesis
- **Symptoms:** Orchestrator response time exceeds 3000ms.
- **Diagnostics:**
  1. Check inter-service roundtrip times: Look for `[repair-engine] GET /api/patches/for-entities` timings in logs.
  2. If network latency between containers is high, check Docker bridge network configuration.
  3. Ensure persistent HTTP/2 connection pooling is working as designed.

---

## 4. Scheduled Maintenance Procedures

### Weekly Maintenance (Every Friday)
- **Governance Feedback Batch Review:**
  The background scheduler runs `_process_governance_batch` every Friday at 09:00 UTC.
  - Manual trigger via API:
    ```bash
    curl -X POST http://localhost:8002/api/governance/run-batch -H "Content-Type: application/json" -d '{"auto_approve_threshold": 0.95}'
    ```
  - Verify result report: Review `total_evaluated`, `approved`, `promoted_to_graph` counters.

### Monthly Maintenance
- **Prune Inactive Docker Images & Volumes:**
  ```bash
  docker image prune -f
  ```
- **Backup Knowledge Stores:**
  - Backup SQLite / PostgreSQL feedback database:
    ```bash
    docker run --rm -v feedback_data:/data -v $(pwd)/backups:/backup alpine cp /data/feedback.db /backup/feedback_$(date +%Y%m%d).db
    ```

---

## 5. Emergency Procedures & Failover

### Total System Failover to Monolithic Mode
In the event that the microservice networking layer fails entirely or multiple containers crash under load:

1. Edit `.env` or set environment variable:
   ```env
   MICROSERVICES_MODE=false
   ```
2. Restart API platform:
   ```bash
   docker-compose restart api
   ```
3. The platform will operate autonomously in single-container mode using in-process packages without relying on ports 8001/8002.

---

## 6. Scaling & Resource Allocation

### Recommended Container Resources

| Container | Min CPU | Min RAM | Recommended CPU | Recommended RAM |
|-----------|---------|---------|-----------------|-----------------|
| `api` | 1.0 core | 1.5 GB | 2.0 cores | 4.0 GB |
| `feedback-service` | 0.5 core | 1.0 GB | 1.0 core | 2.0 GB |
| `repair-service` | 0.5 core | 512 MB | 1.0 core | 1.0 GB |
| `redis` | 0.2 core | 256 MB | 0.5 core | 512 MB |
| `neo4j` | 1.0 core | 1.0 GB | 2.0 cores | 2.0 GB |

---

## 7. Escalation Contacts & On-Call Matrix

- **Primary SRE:** DevOps Team (`#ops-channel`)
- **Backend Architecture Lead:** Platform Engineering (`#phase2-backend`)
- **Escalation SLA:**
  - P0 (Platform down): < 15 minutes acknowledgment, < 1 hour resolution
  - P1 (Microservice circuit open / degraded): < 30 minutes acknowledgment, < 2 hours resolution
  - P2 (Governance batch warning): Next business day
