# ✅ Pre-Deployment Verification Checklist

**Purpose:** Ensure all efficiency features are working before production deployment  
**Estimated Time:** 30-45 minutes  
**Date:** September 8, 2026

---

## Phase 1: Code Verification (5 minutes)

### ✅ Check 1: All Feature Files Exist
```bash
# Navigate to backend
cd backend

# Verify all files exist
ls -la app/engine/hyde.py
ls -la app/engine/ner_pipeline.py
ls -la app/engine/text_to_cypher.py
ls -la app/retrieval/cache.py
ls -la app/engine/intent_cache.py
ls -la app/retrieval/planner.py
ls -la app/retrieval/orchestrator.py
ls -la app/engine/graph_store.py
ls -la app/engine/config.py
ls -la app/api/routes/metrics.py
```

**Expected Result:** All 11 files exist  
**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 2: Feature Flags Are Defined
```bash
# Check feature flags in config.py
grep -n "ENABLE_HYDE_CACHE\|ENABLE_GLINER_SKIP\|ENABLE_CYPHER_AUTO_CORRECTION" app/engine/config.py
```

**Expected Result:** All 8 flags defined  
**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 3: Features Integrated in Orchestrator
```bash
# Check orchestrator imports
grep -n "from.*hyde\|from.*cache\|from.*planner" app/retrieval/orchestrator.py

# Check feature flags used
grep -n "ENABLE_HYDE\|ENABLE_QUERY_DECOMPOSITION\|ENABLE_PARALLELIZATION" app/retrieval/orchestrator.py
```

**Expected Result:** Features imported and flags checked  
**Status:** [ ] Pass [ ] Fail

---

## Phase 2: Environment Setup (5 minutes)

### ✅ Check 4: Python Version
```bash
python --version
# Should be Python 3.10+
```

**Expected Result:** Python 3.10 or later  
**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 5: Dependencies Installed
```bash
pip list | grep -i "fastapi\|uvicorn\|faiss\|pydantic"
```

**Expected Result:** All key dependencies present  
**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 6: Environment Variables Set
```bash
# Check if feature flags are set
echo $ENABLE_HYDE_CACHE
echo $ENABLE_QUERY_DECOMPOSITION
echo $ENABLE_PARALLELIZATION

# If empty, set them
export ENABLE_HYDE_CACHE=true
export ENABLE_HYDE_IN_ORCHESTRATOR=true
export ENABLE_GLINER_SKIP=true
export ENABLE_CYPHER_AUTO_CORRECTION=true
export ENABLE_SMART_VECTOR_PRUNING=true
export ENABLE_SEMANTIC_CACHE_WARMUP=true
export ENABLE_PARALLELIZATION=true
export ENABLE_QUERY_DECOMPOSITION=true
```

**Expected Result:** All flags set to "true"  
**Status:** [ ] Pass [ ] Fail

---

## Phase 3: Service Startup (5 minutes)

### ✅ Check 7: Start Backend Service
```bash
# In terminal 1, start the backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Wait for "Uvicorn running on http://0.0.0.0:8000"
```

**Expected Result:** Service starts without errors  
**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 8: Health Endpoint Responds
```bash
# In terminal 2, check health
curl http://localhost:8000/health

# Expected response:
# {"status": "ok"}
```

**Expected Result:** Returns 200 OK with status message  
**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 9: Metrics Endpoint Exists
```bash
curl http://localhost:8000/metrics/summary

# Should return JSON with metrics
```

**Expected Result:** Returns 200 OK with JSON metrics  
**Status:** [ ] Pass [ ] Fail

---

## Phase 4: Feature Verification (20 minutes)

### ✅ Check 10: Run Efficiency Benchmark
```bash
# In terminal 2 (or new terminal)
cd backend
python -m pytest PHASE_4_EFFICIENCY_EVALUATION.py -v

# Watch for test results
```

**Expected Results:**
- All tests pass ✅
- Latency improvement 120-240ms ✅
- Cache hit rates >40% ✅
- Token reduction 15-25% ✅

**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 11: Run Integration Tests
```bash
# Run phase 4 integration tests
python -m pytest PHASE_4_INTEGRATION_TEST.py -v

# Expected: 7 async tests pass
```

**Expected Results:**
- All tests pass ✅
- No errors in API endpoints ✅
- Metrics collection working ✅

**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 12: Verify Each Feature Flag Toggle

#### HyDE Cache Toggle
```bash
# Test 1: HyDE enabled
export ENABLE_HYDE_CACHE=true
curl http://localhost:8000/metrics/summary | jq '.cache_hit_rates.hyde'
# Should show some cache hits or 0

# Test 2: HyDE disabled
export ENABLE_HYDE_CACHE=false
# Restart service or reload module
# Latency should increase 15-25ms
```

**Status:** [ ] Pass [ ] Fail

#### Query Decomposition Toggle
```bash
# Test 1: Decomposition enabled
export ENABLE_QUERY_DECOMPOSITION=true
curl http://localhost:8000/metrics/summary | jq '.features_enabled.query_decomposition'
# Should be true

# Test 2: Decomposition disabled
export ENABLE_QUERY_DECOMPOSITION=false
# Latency should increase 30-60ms on complex queries
```

**Status:** [ ] Pass [ ] Fail

#### Parallelization Toggle
```bash
# Test 1: Parallelization enabled
export ENABLE_PARALLELIZATION=true
curl http://localhost:8000/metrics/summary | jq '.features_enabled.parallelization'
# Should be true

# Test 2: Verify parallel execution
# Check logs for "parallel_groups" or "async execution"
```

**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 13: Verify Cache Functionality

#### HyDE Cache
```bash
# Run same query twice
curl "http://localhost:8000/api/query" -d '{"query": "What are the compliance violations?"}' -X POST

# Check cache hit
curl http://localhost:8000/metrics/summary | jq '.cache_hit_rates.hyde'
# Should show increased hit rate on second request
```

**Status:** [ ] Pass [ ] Fail

#### Semantic Cache
```bash
# Run similar queries
curl "http://localhost:8000/api/query" -d '{"query": "Find violations"}' -X POST
curl "http://localhost:8000/api/query" -d '{"query": "Find all violations"}' -X POST

# Check cache hit
curl http://localhost:8000/metrics/summary | jq '.cache_hit_rates.semantic'
# Should show hits for similar queries
```

**Status:** [ ] Pass [ ] Fail

#### Intent Cache
```bash
# Run queries with same intent
curl "http://localhost:8000/api/query" -d '{"query": "Show me violations"}' -X POST
curl "http://localhost:8000/api/query" -d '{"query": "Display violations"}' -X POST

# Check cache hit
curl http://localhost:8000/metrics/summary | jq '.cache_hit_rates.intent'
# Should show hits
```

**Status:** [ ] Pass [ ] Fail

---

## Phase 5: Performance Validation (5 minutes)

### ✅ Check 14: Compare Baseline Metrics

**Run with all features enabled:**
```bash
# Reset metrics
curl -X POST http://localhost:8000/metrics/reset

# Run benchmark
python scripts/run_100_queries.py

# Collect metrics
curl http://localhost:8000/metrics/summary > metrics_all_features.json
```

**Expected Results:**
```json
{
  "avg_latency_ms": 1700,  // Should be 1600-1850ms
  "p95_latency_ms": 2100,  // Should be 1850-2300ms
  "cache_hit_rates": {
    "hyde": 0.55,          // Should be >40%
    "semantic": 0.45,      // Should be >40%
    "intent": 0.60,        // Should be >40%
    "cypher": 0.50         // Should be >40%
  },
  "token_usage": {
    "total_cost_usd": 0.55  // Should be ~15-25% lower
  }
}
```

**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 15: Compare with Features Disabled

**Run with all features disabled:**
```bash
# Disable all features
export ENABLE_HYDE_CACHE=false
export ENABLE_QUERY_DECOMPOSITION=false
export ENABLE_PARALLELIZATION=false
export ENABLE_CYPHER_AUTO_CORRECTION=false
export ENABLE_GLINER_SKIP=false
export ENABLE_SEMANTIC_CACHE_WARMUP=false
export ENABLE_SMART_VECTOR_PRUNING=false

# Restart service (or reload module)

# Reset metrics
curl -X POST http://localhost:8000/metrics/reset

# Run benchmark
python scripts/run_100_queries.py

# Collect metrics
curl http://localhost:8000/metrics/summary > metrics_no_features.json
```

**Expected Results:**
```json
{
  "avg_latency_ms": 2050,  // Should be ~350ms higher than with features
  "p95_latency_ms": 2500,  // Should be higher
  "cache_hit_rates": {
    "hyde": 0,     // Should be 0 (cache disabled)
    "semantic": 0, // Should be 0
    "intent": 0,   // Should be 0
    "cypher": 0    // Should be 0
  }
}
```

**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 16: Verify Improvement

```bash
# Compare the two runs
python -c "
import json
with open('metrics_all_features.json') as f:
    with_features = json.load(f)
with open('metrics_no_features.json') as f:
    without_features = json.load(f)

latency_improvement = without_features['avg_latency_ms'] - with_features['avg_latency_ms']
improvement_pct = (latency_improvement / without_features['avg_latency_ms']) * 100

print(f'Latency Improvement: {latency_improvement:.0f}ms ({improvement_pct:.1f}%)')
print(f'✅ PASS' if latency_improvement >= 120 else f'❌ FAIL')
"
```

**Expected Result:** 120-240ms improvement (12-24%)  
**Status:** [ ] Pass [ ] Fail

---

## Phase 6: Error Handling (5 minutes)

### ✅ Check 17: Test Graceful Degradation

**Scenario: One feature fails**
```bash
# Simulate Cypher auto-correction failure
export ENABLE_CYPHER_AUTO_CORRECTION=false

# Run query that would normally use auto-correction
curl "http://localhost:8000/api/query" -d '{"query": "Find violations"}' -X POST

# Should still return result (without correction)
# Check error rate hasn't increased
curl http://localhost:8000/metrics/summary | jq '.error_rate'
# Should be <1%
```

**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 18: Test Rollback Procedure

**Scenario: Need to rollback all features**
```bash
# Disable all features
export ENABLE_HYDE_CACHE=false
export ENABLE_QUERY_DECOMPOSITION=false
export ENABLE_PARALLELIZATION=false
export ENABLE_CYPHER_AUTO_CORRECTION=false
export ENABLE_GLINER_SKIP=false
export ENABLE_SEMANTIC_CACHE_WARMUP=false
export ENABLE_SMART_VECTOR_PRUNING=false

# Restart service
systemctl restart backend-service
# (or manually restart if running in terminal)

# Verify service comes up
sleep 10
curl http://localhost:8000/health
# Should return {"status": "ok"}

# Run a query
curl "http://localhost:8000/api/query" -d '{"query": "Find violations"}' -X POST
# Should work without errors
```

**Status:** [ ] Pass [ ] Fail

---

## Phase 7: Documentation Verification (5 minutes)

### ✅ Check 19: Verify Documentation Files Exist

```bash
# Check for required docs in workspace root
ls -la AUDIT_REPORT_EFFICIENCY_IMPLEMENTATION.md
ls -la OPERATOR_RUNBOOK.md
ls -la AUDIT_SUMMARY_ONE_PAGE.md
ls -la PRE_DEPLOYMENT_VERIFICATION.md
```

**Expected Result:** All 4 files exist  
**Status:** [ ] Pass [ ] Fail

---

### ✅ Check 20: Verify Documentation Quality

- [ ] Audit report contains all 8 features with code evidence
- [ ] Operator runbook has troubleshooting section
- [ ] Summary provides go/no-go decision
- [ ] Feature flag documentation is complete
- [ ] Rollback procedures are documented

**Status:** [ ] Pass [ ] Fail

---

## Final Sign-Off

### Verification Results

| Category | Checks | Status |
|----------|--------|--------|
| **Code** | 1-3 | [ ] Pass |
| **Environment** | 4-6 | [ ] Pass |
| **Startup** | 7-9 | [ ] Pass |
| **Features** | 10-13 | [ ] Pass |
| **Performance** | 14-16 | [ ] Pass |
| **Error Handling** | 17-18 | [ ] Pass |
| **Documentation** | 19-20 | [ ] Pass |

### Overall Result

- [ ] ✅ **ALL TESTS PASS** — Ready for production
- [ ] ⚠️ **SOME TESTS FAIL** — Fix issues before deployment
- [ ] ❌ **CRITICAL FAILURES** — Do not deploy

---

### Verified By

**Name:** ___________________  
**Date:** ___________________  
**Time:** ___________________  

**Approver Signature:** ___________________

---

### If Tests Fail

**Common Issues & Solutions:**

| Issue | Solution |
|-------|----------|
| Service won't start | Check Python version, verify all dependencies installed |
| Latency not improving | Verify all feature flags are enabled in env vars |
| Cache hit rates 0% | Cache may need warmup time; run 100 queries first |
| Benchmark tests fail | Check Neo4j connection, verify graph data loaded |
| Metrics endpoint returns 404 | Verify app/api/routes/metrics.py file exists |

**If stuck:** Contact the backend development team with:
1. Which check failed
2. Full error message
3. Output of: `curl http://localhost:8000/health`
4. Output of: `echo $ENABLE_*` (all feature flags)

---

**Template Version:** 1.0  
**Last Updated:** September 8, 2026  
**Next Review:** Post-deployment verification (after 1 week in production)
