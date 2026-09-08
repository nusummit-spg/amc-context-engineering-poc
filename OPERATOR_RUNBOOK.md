# 📋 Operator Runbook: Backend Efficiency Features

**For:** Operations & SRE teams  
**Updated:** September 8, 2026  
**Scope:** Managing and troubleshooting efficiency features in production

---

## Quick Reference

### Health Check
```bash
# Is the service up?
curl http://localhost:8000/health

# Are efficiency features working?
curl http://localhost:8000/metrics/summary | jq '.features_enabled'

# What's the current performance?
curl http://localhost:8000/metrics/summary
```

### Emergency Rollback
```bash
# Disable all efficiency features
export ENABLE_HYDE_CACHE=false
export ENABLE_GLINER_SKIP=false
export ENABLE_CYPHER_AUTO_CORRECTION=false
export ENABLE_SMART_VECTOR_PRUNING=false
export ENABLE_SEMANTIC_CACHE_WARMUP=false
export ENABLE_PARALLELIZATION=false
export ENABLE_QUERY_DECOMPOSITION=false

# Restart service
systemctl restart backend-service
```

### Reset Metrics (for testing)
```bash
curl -X POST http://localhost:8000/metrics/reset
```

---

## 1. Deployment & Startup

### Prerequisites
- Python 3.10+
- All dependencies installed: `pip install -r requirements.txt`
- Environment variables set (see Configuration)

### Starting the Service
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Configuration via Environment Variables
```bash
# Feature Flags (default: all true)
export ENABLE_HYDE_CACHE=true
export ENABLE_HYDE_IN_ORCHESTRATOR=true
export ENABLE_GLINER_SKIP=true
export ENABLE_CYPHER_AUTO_CORRECTION=true
export ENABLE_SMART_VECTOR_PRUNING=true
export ENABLE_SEMANTIC_CACHE_WARMUP=true
export ENABLE_PARALLELIZATION=true
export ENABLE_QUERY_DECOMPOSITION=true

# API Configuration
export API_HOST=0.0.0.0
export API_PORT=8000
export LOG_LEVEL=INFO

# Optional: Metrics storage
export METRICS_TTL_HOURS=24
export METRICS_RETENTION_COUNT=10000
```

### Verification After Startup
```bash
# Wait 10 seconds for service to initialize
sleep 10

# Check health
curl http://localhost:8000/health
# Expected response: {"status": "ok"}

# Check metrics API
curl http://localhost:8000/metrics/summary
# Expected response: JSON with query_count, latency, cache_hit_rates, etc.
```

---

## 2. Monitoring & Metrics

### Available Metrics Endpoints

#### GET /metrics/summary
Returns current aggregated metrics across all queries.

```bash
curl http://localhost:8000/metrics/summary | jq .
```

**Response:**
```json
{
  "query_count": 1234,
  "avg_latency_ms": 1856,
  "p50_latency_ms": 1650,
  "p95_latency_ms": 2341,
  "p99_latency_ms": 3156,
  "cache_hit_rates": {
    "hyde": 0.62,
    "semantic": 0.48,
    "intent": 0.55,
    "cypher": 0.52
  },
  "token_usage": {
    "input_tokens": 45000,
    "output_tokens": 12000,
    "total_cost_usd": 0.57
  },
  "features_enabled": {
    "hyde_cache": true,
    "hyde_in_orchestrator": true,
    "gliner_skip": true,
    "cypher_auto_correction": true,
    "smart_vector_pruning": true,
    "semantic_cache_warmup": true,
    "parallelization": true,
    "query_decomposition": true
  },
  "cache_sizes": {
    "hyde_cache_entries": 2456,
    "semantic_cache_entries": 1234,
    "intent_cache_entries": 5000,
    "cypher_cache_entries": 432
  }
}
```

---

#### GET /metrics/recent?count=N
Returns detailed metrics for the last N queries (default: 100, max: 1000).

```bash
# Get last 50 queries
curl "http://localhost:8000/metrics/recent?count=50" | jq .

# Get last 500 queries
curl "http://localhost:8000/metrics/recent?count=500" | jq .
```

**Response:**
```json
{
  "queries": [
    {
      "query_id": "q_abc123",
      "query_text": "Find all compliance violations for ACME Corp",
      "latency_ms": 1923,
      "tokens_used": 342,
      "cache_hits": {
        "hyde": true,
        "semantic": false,
        "intent": true,
        "cypher": false
      },
      "features_used": {
        "decomposition": true,
        "parallelization": true,
        "auto_correction": false
      },
      "timestamp": "2026-09-08T14:32:15Z"
    },
    ...
  ]
}
```

---

#### POST /metrics/reset
Clears all metrics (use for testing or baseline resets).

```bash
curl -X POST http://localhost:8000/metrics/reset
# Expected response: {"status": "metrics_reset", "cleared_queries": 1234}
```

---

### Key Metrics to Monitor

| Metric | Healthy Range | Warning | Critical |
|--------|---|---|---|
| **Avg Latency** | 1500-2000ms | >2300ms | >3000ms |
| **p95 Latency** | 2000-2500ms | >2800ms | >3500ms |
| **p99 Latency** | 2500-3200ms | >3600ms | >4500ms |
| **HyDE Cache Hit Rate** | 50-70% | <40% | <20% |
| **Semantic Cache Hit Rate** | 40-60% | <30% | <10% |
| **Intent Cache Hit Rate** | 50-70% | <40% | <20% |
| **Cypher Cache Hit Rate** | 40-60% | <30% | <10% |
| **Error Rate** | <0.5% | 0.5-2% | >2% |
| **Token Usage/Query** | 300-400 | >450 | >500 |

---

## 3. Feature Flags: Toggle & Testing

### Overview
All efficiency features can be toggled independently via environment variables. This allows canary deployments and A/B testing.

### Individual Feature Control

#### Feature: HyDE Response Caching
**Flag:** `ENABLE_HYDE_CACHE`  
**Impact:** 15-25ms per cache hit  
**Default:** true  
**How to disable:**
```bash
export ENABLE_HYDE_CACHE=false
systemctl restart backend-service
```

**Expected behavior when disabled:**
- Latency increases 15-25ms on repeated queries
- HyDE cache hit rate in metrics drops to 0%

---

#### Feature: GLiNER Saturation Bypass
**Flag:** `ENABLE_GLINER_SKIP`  
**Impact:** 8-12ms when entities already confident  
**Default:** true  
**How to disable:**
```bash
export ENABLE_GLINER_SKIP=false
systemctl restart backend-service
```

**Expected behavior when disabled:**
- GLiNER runs on all queries (even if confidence already high)
- Latency increases 8-12ms on queries with high-confidence entities

---

#### Feature: Cypher Syntax Auto-Correction
**Flag:** `ENABLE_CYPHER_AUTO_CORRECTION`  
**Impact:** 20-50ms by avoiding LLM retries  
**Default:** true  
**How to disable:**
```bash
export ENABLE_CYPHER_AUTO_CORRECTION=false
systemctl restart backend-service
```

**Expected behavior when disabled:**
- Failed Cypher queries not retried
- Error rate may increase 2-5%
- Latency on failed queries increases (no fallback)

---

#### Feature: Semantic Cache Warmup
**Flag:** `ENABLE_SEMANTIC_CACHE_WARMUP`  
**Impact:** 10-15ms on warm queries  
**Default:** true  
**How to disable:**
```bash
export ENABLE_SEMANTIC_CACHE_WARMUP=false
systemctl restart backend-service
```

**Expected behavior when disabled:**
- Semantic cache hit rate drops 20-30%
- Latency on similar queries increases

---

#### Feature: Query Parallelization
**Flag:** `ENABLE_PARALLELIZATION`  
**Impact:** 30-60ms on complex queries (2+ sub-tasks)  
**Default:** true  
**How to disable:**
```bash
export ENABLE_PARALLELIZATION=false
systemctl restart backend-service
```

**Expected behavior when disabled:**
- Complex queries execute sequentially
- Latency increases 30-60ms for decomposed queries
- Simple queries (single sub-task) unaffected

---

#### Feature: Query Decomposition
**Flag:** `ENABLE_QUERY_DECOMPOSITION`  
**Impact:** Enables parallelization; 30-60ms on complex queries  
**Default:** true  
**How to disable:**
```bash
export ENABLE_QUERY_DECOMPOSITION=false
systemctl restart backend-service
```

**Expected behavior when disabled:**
- Complex queries execute as single pass
- Parallelization has no effect
- Latency increases 30-60ms on queries that would decompose

---

### A/B Testing: Compare Feature On vs. Off

**Procedure:**

1. **Establish baseline with feature enabled:**
```bash
export ENABLE_FEATURE_X=true
systemctl restart backend-service
sleep 60  # Let service stabilize
curl http://localhost:8000/metrics/reset  # Clear old metrics
# Run 100 test queries
curl -X POST http://localhost:8000/metrics/reset  # Clear
# Wait 10 minutes
curl http://localhost:8000/metrics/summary > baseline_on.json
```

2. **Test with feature disabled:**
```bash
export ENABLE_FEATURE_X=false
systemctl restart backend-service
sleep 60  # Let service stabilize
curl -X POST http://localhost:8000/metrics/reset  # Clear old metrics
# Run same 100 test queries
# Wait 10 minutes
curl http://localhost:8000/metrics/summary > baseline_off.json
```

3. **Compare results:**
```bash
jq '.avg_latency_ms' baseline_on.json    # Should be lower
jq '.cache_hit_rates' baseline_on.json   # Should be higher
jq '.avg_latency_ms' baseline_off.json   # Should be higher
```

---

### Canary Deployment: Staged Feature Rollout

**Scenario:** Deploy new features to 10% of traffic first.

**Using environment variables with blue-green deployment:**

1. **Blue instance (stable, all features):**
```bash
# Current production
export ENABLE_HYDE_CACHE=true
export ENABLE_QUERY_DECOMPOSITION=true
# ... other features ...
PORT=8000
```

2. **Green instance (canary, one feature disabled):**
```bash
# New canary
export ENABLE_QUERY_DECOMPOSITION=false  # Testing without decomposition
# ... other features same as blue ...
PORT=8001
```

3. **Load balancer configuration:**
```nginx
upstream backend_blue {
  server localhost:8000;
}

upstream backend_green {
  server localhost:8001;
}

upstream backend_pool {
  server localhost:8000 weight=9;  # 90% to stable
  server localhost:8001 weight=1;  # 10% to canary
}

server {
  location /api/ {
    proxy_pass http://backend_pool;
  }
}
```

4. **Monitor canary metrics:**
```bash
# Every 5 minutes, check green instance metrics
curl http://localhost:8001/metrics/summary | jq '.avg_latency_ms'

# If metrics look good, increase weight:
# server localhost:8001 weight=2;  # Now 20% to canary

# If issues detected, immediately revert:
# server localhost:8001 weight=0;  # 0% to canary (disable)
```

---

## 4. Troubleshooting

### Symptom: High Latency (>3000ms)

**Check 1: Are efficiency features enabled?**
```bash
curl http://localhost:8000/metrics/summary | jq '.features_enabled'
```
If any critical feature is false, enable it:
```bash
export ENABLE_HYDE_CACHE=true
export ENABLE_QUERY_DECOMPOSITION=true
export ENABLE_PARALLELIZATION=true
systemctl restart backend-service
```

**Check 2: Are cache hit rates low?**
```bash
curl http://localhost:8000/metrics/summary | jq '.cache_hit_rates'
```
If all cache hit rates are <20%, caches may not be warmed up:
```bash
# Give service time to warm caches (5-10 minutes)
# Then check again
```

**Check 3: Is system memory constrained?**
```bash
free -h  # Linux
wmic OS get TotalVisibleMemorySize,FreePhysicalMemory  # Windows (PowerShell)
```
If memory <10% free, caches may be evicting too aggressively:
```bash
# Restart service to clear caches
systemctl restart backend-service
# Or scale horizontally (add more instances)
```

---

### Symptom: Low Cache Hit Rates

**Check 1: Are warm-up patterns configured?**
```bash
grep -n "warm_cache_patterns\|warmup" backend/app/engine/intent_cache.py
```

**Check 2: Are TTLs too short?**
```bash
# Default TTLs (in seconds)
# HyDE: 3600 (1 hour)
# Semantic: 3600 (1 hour)
# Intent: 86400 (24 hours)
# Cypher: 604800 (7 days)

# If caches expiring too fast, increase TTL:
# Edit backend/app/core/metrics.py or use environment variables
```

**Check 3: Are caches hitting size limits?**
```bash
curl http://localhost:8000/metrics/summary | jq '.cache_sizes'

# Expected cache sizes:
# hyde_cache: up to 5000 entries
# semantic_cache: up to 10000 entries
# intent_cache: up to 5000 entries
# cypher_cache: up to 500 entries
```

If caches are at max size, increase limits or reduce TTL to encourage eviction.

---

### Symptom: Errors in Query Execution

**Check 1: Are auto-correction features enabled?**
```bash
curl http://localhost:8000/metrics/summary | jq '.features_enabled.cypher_auto_correction'
```

If false, enable it:
```bash
export ENABLE_CYPHER_AUTO_CORRECTION=true
systemctl restart backend-service
```

**Check 2: Check recent query errors:**
```bash
# Get last 100 queries
curl "http://localhost:8000/metrics/recent?count=100" | jq '.queries[] | select(.error != null)'

# Look for patterns:
# - Same query failing repeatedly? (check Cypher cache)
# - Specific entity type failing? (check GLiNER)
# - Graph connectivity issues? (check graph dump)
```

**Check 3: Validate graph connectivity:**
```bash
# Connect to Neo4j
cypher-shell -u neo4j -p [password]

# Check node count
MATCH (n) RETURN count(n);

# Check relationship count
MATCH ()-[r]->() RETURN count(r);

# If counts seem low, graph may need reloading
```

---

### Symptom: Memory Usage Growing Over Time

**Check 1: Are caches evicting stale entries?**
```bash
# Monitor cache sizes
watch -n 5 'curl http://localhost:8000/metrics/summary | jq ".cache_sizes"'

# If cache sizes grow unbounded, TTL not working:
# Restart service to clear caches
systemctl restart backend-service

# Or reduce cache size limits
```

**Check 2: Are there query result leaks?**
```bash
# Check process memory
ps aux | grep python  # Linux
Get-Process | Where-Object {$_.ProcessName -like '*python*'} | Select-Object Name, WorkingSet  # Windows PowerShell

# If memory keeps growing even with caches, there may be a leak
# Contact development team for investigation
```

---

### Symptom: Decomposition Not Working

**Check 1: Is decomposition enabled?**
```bash
curl http://localhost:8000/metrics/summary | jq '.features_enabled.query_decomposition'
```

**Check 2: Is parallelization enabled?**
```bash
curl http://localhost:8000/metrics/summary | jq '.features_enabled.parallelization'
```

Both must be true. If either false:
```bash
export ENABLE_QUERY_DECOMPOSITION=true
export ENABLE_PARALLELIZATION=true
systemctl restart backend-service
```

**Check 3: Check if queries are actually decomposing:**
```bash
# Get recent queries
curl "http://localhost:8000/metrics/recent?count=100" | jq '.queries[] | select(.features_used.decomposition == true)' | head -5

# If few or no queries decomposing, decomposition may not be triggering
# Check if queries are complex enough to warrant decomposition
```

---

## 5. Maintenance Tasks

### Daily
- ✅ Check `/metrics/summary` — verify latency within range
- ✅ Check cache hit rates — should be stable or improving
- ✅ Check error rate — should be <0.5%

### Weekly
- 🔄 Review query distribution — are certain queries dominating?
- 🔄 Check memory usage — is it stable?
- 🔄 Verify all feature flags — are they as expected?

### Monthly
- 🔄 Reset metrics and establish new baseline
- 🔄 Analyze performance trends
- 🔄 Review cache effectiveness
- 🔄 Optimize feature flag settings based on data

### Before Major Releases
- ✅ Run full benchmark suite: `python PHASE_4_EFFICIENCY_EVALUATION.py`
- ✅ Compare against baseline
- ✅ Verify all features working
- ✅ Test rollback procedures

---

## 6. Incident Response

### Incident: Service Crash

**Immediate Response (< 1 min):**
```bash
# 1. Check service status
systemctl status backend-service

# 2. Check logs
journalctl -u backend-service -n 50  # Linux
Get-EventLog -LogName System -Source backend-service -Newest 50  # Windows

# 3. Restart service
systemctl restart backend-service

# 4. Verify it comes back up
sleep 10
curl http://localhost:8000/health
```

**If service won't start:**
```bash
# Disable all features (revert to baseline)
export ENABLE_HYDE_CACHE=false
export ENABLE_QUERY_DECOMPOSITION=false
export ENABLE_PARALLELIZATION=false
export ENABLE_CYPHER_AUTO_CORRECTION=false
export ENABLE_GLINER_SKIP=false
export ENABLE_SEMANTIC_CACHE_WARMUP=false
export ENABLE_SMART_VECTOR_PRUNING=false

# Try restart
systemctl restart backend-service

# If still fails, contact development team
```

---

### Incident: High Error Rate (>2%)

**Immediate Response (< 5 min):**
```bash
# 1. Check what errors are happening
curl "http://localhost:8000/metrics/recent?count=100" | jq '.queries[] | select(.error != null)'

# 2. Check which feature might be causing it
# If Cypher errors: disable ENABLE_CYPHER_AUTO_CORRECTION
# If decomposition errors: disable ENABLE_QUERY_DECOMPOSITION
# If GLiNER errors: disable ENABLE_GLINER_SKIP

# Example: Disable Cypher auto-correction
export ENABLE_CYPHER_AUTO_CORRECTION=false
systemctl restart backend-service

# 3. Monitor error rate
watch -n 10 'curl http://localhost:8000/metrics/summary | jq ".query_count, .error_count"'

# 4. If error rate returns to <0.5%, problem identified
# Notify development team of which feature caused issues
```

---

### Incident: Latency Spike (>50% above baseline)

**Immediate Response (< 5 min):**
```bash
# 1. Check which queries are slow
curl "http://localhost:8000/metrics/recent?count=50" | jq '.queries | sort_by(-.latency_ms) | .[0:5]'

# 2. Check if specific feature is causing slowdown
# Try disabling features one by one:

# Disable decomposition
export ENABLE_QUERY_DECOMPOSITION=false
systemctl restart backend-service
sleep 60
LATENCY_1=$(curl http://localhost:8000/metrics/summary | jq '.avg_latency_ms')

# If latency improved, decomposition is the problem
# Otherwise, re-enable and try next feature
export ENABLE_QUERY_DECOMPOSITION=true
export ENABLE_PARALLELIZATION=false
systemctl restart backend-service
sleep 60
LATENCY_2=$(curl http://localhost:8000/metrics/summary | jq '.avg_latency_ms')

# Continue until culprit found
```

---

## 7. Performance Optimization

### Cache Size Tuning

**If memory pressure is high:**
```bash
# Reduce cache sizes in backend/app/core/metrics.py
# HyDE: reduce from 5000 to 2500
# Semantic: reduce from 10000 to 5000
# Intent: reduce from 5000 to 2500

# Then restart
systemctl restart backend-service
```

**If cache hit rates are low:**
```bash
# Increase cache sizes or TTLs
# HyDE: increase from 5000 to 10000
# Semantic: increase TTL from 3600 to 7200

# Then restart
systemctl restart backend-service
```

---

### Query Decomposition Tuning

**If decomposition is breaking queries:**
```bash
# Reduce decomposition threshold
# Currently: decompose queries with >2 entities
# Try: decompose queries with >5 entities (more conservative)

# Edit backend/app/retrieval/planner.py
# Modify MIN_ENTITIES_FOR_DECOMPOSITION constant
```

---

### Feature Flag Optimization

**After 1 week of production data:**
```bash
# Analyze feature effectiveness
curl http://localhost:8000/metrics/recent?count=1000 | jq '
.queries[] | 
{
  feature: .features_used,
  latency: .latency_ms,
  cache_hits: .cache_hits
}' | 
sort_by(.latency) | 
group_by(.feature)
```

**Disable features with low impact:**
```bash
# If a feature shows <2% latency improvement:
export FEATURE_NAME=false
systemctl restart backend-service

# Monitor for 1 hour to confirm no regression
```

---

## 8. Contact & Escalation

### Support Contacts
- **On-Call Engineer:** [phone/slack]
- **Development Team:** #backend-dev (Slack)
- **DevOps Lead:** [contact info]

### Escalation Path
1. On-call engineer handles first response
2. If issue persists >15 min or service down: Page development lead
3. If data integrity concern: Page VP Engineering

### When to Escalate
- ✅ Service down >5 minutes
- ✅ Data loss or corruption suspected
- ✅ Error rate >5%
- ✅ P99 latency >4000ms (sustained)
- ✅ Inability to rollback a feature

---

## Appendix: Quick Commands

```bash
# Health check
curl http://localhost:8000/health

# Get metrics summary
curl http://localhost:8000/metrics/summary | jq .

# Get last 50 queries
curl "http://localhost:8000/metrics/recent?count=50" | jq .

# Reset metrics
curl -X POST http://localhost:8000/metrics/reset

# Check feature flags
curl http://localhost:8000/metrics/summary | jq '.features_enabled'

# Disable all features
export ENABLE_HYDE_CACHE=false; \
export ENABLE_GLINER_SKIP=false; \
export ENABLE_CYPHER_AUTO_CORRECTION=false; \
export ENABLE_SMART_VECTOR_PRUNING=false; \
export ENABLE_SEMANTIC_CACHE_WARMUP=false; \
export ENABLE_PARALLELIZATION=false; \
export ENABLE_QUERY_DECOMPOSITION=false; \
systemctl restart backend-service

# Enable all features
export ENABLE_HYDE_CACHE=true; \
export ENABLE_GLINER_SKIP=true; \
export ENABLE_CYPHER_AUTO_CORRECTION=true; \
export ENABLE_SMART_VECTOR_PRUNING=true; \
export ENABLE_SEMANTIC_CACHE_WARMUP=true; \
export ENABLE_PARALLELIZATION=true; \
export ENABLE_QUERY_DECOMPOSITION=true; \
systemctl restart backend-service
```

---

**Last Updated:** September 8, 2026  
**Next Review:** Post-production (1 week)
