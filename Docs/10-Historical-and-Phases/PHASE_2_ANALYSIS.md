# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# Phase 2 Analysis: Staleness Monitor
## Current Implementation & Optimization Design

**Date:** August 27, 2026  
**Module:** `staleness_monitor.py`  
**Goal:** Evaluate Python threading optimization (10-30x speedup expected)

---

## Current Implementation Analysis

### What It Does
1. Fetches all documents from provenance ledger with HTTP URLs
2. Samples first N documents (default 20)
3. **Sequentially** sends HTTP HEAD requests to each URL
4. Checks HTTP status codes and Last-Modified headers
5. Marks documents as drifted/not-found in ledger
6. Generates staleness alert report

### Performance Characteristics

**Current Sequential Approach:**
```python
for r in sample:
    try:
        resp = requests.head(r.source_url, headers=headers, timeout=10)
        # ... process response ...
    except Exception:
        pass
    time.sleep(0.2)  # Artificial delay between requests
```

**Per-Request Breakdown:**
- Network latency (HTTP HEAD): ~100-500ms (network-dependent)
- Sleep delay: 200ms (artificial courtesy delay)
- Processing: <5ms
- **Total per request:** ~300-700ms

**For 20 documents (default sample):**
- Sequential: 20 × 300-700ms = **6-14 seconds**
- With artificial sleep: Closer to **10-14 seconds**

**For 100 documents (evaluation target):**
- Sequential: 100 × 300-700ms = **30-70 seconds**

### Bottleneck Identification

**Primary bottleneck: Network I/O**
- HTTP request/response: 100-500ms (waiting on network)
- CPU is idle during request (~95% idle time)
- No parallelization = sequential wall-clock time

**Secondary issue: Artificial sleep(0.2)**
- Probably meant to avoid rate-limiting
- Adds 200ms per request unnecessarily
- In parallel mode, this becomes unnecessary (requests are naturally spaced by network latency)

---

## Optimization Strategy: Python Threading

### Design Approach

**Use `ThreadPoolExecutor` to parallelize HTTP requests:**

```
Sequential (current):
Request 1 [====100ms===]
Request 2         [====100ms===]
Request 3                 [====100ms===]
Total: 300ms (linear)

Parallel (optimized, 5 threads):
Request 1 [====100ms===]
Request 2 [====100ms===]
Request 3 [====100ms===]
Request 4 [====100ms===]
Request 5 [====100ms===]
Total: 100ms (5x speedup)
```

### Threading Configuration

**Thread pool size: Configurable, default 10 workers**

- Network-bound operation: Can safely use 10-50 threads
- Each thread waits on network I/O, not consuming CPU
- No GIL contention (threads blocked on I/O)
- Limit: OS socket limit (~1024 per process), practical limit ~50-100

**Expected speedup formula:**
```
Speedup = Sequential Time / Parallel Time
        = (20 × 300ms) / (300ms / workers + overhead)
        = (20 × 300ms) / (300ms / 10 + 10ms overhead)
        = 6000ms / 40ms
        ≈ 150x in ideal case (but network is still bottleneck)

More realistic (network is bottleneck):
Speedup = min(number_of_workers, number_of_documents)
        = min(10, 20)
        = 10x
```

### Implementation Details

**Key changes:**
1. Remove `time.sleep(0.2)` (no longer needed, requests naturally spaced)
2. Use `ThreadPoolExecutor(max_workers=10)`
3. Submit all requests immediately
4. Collect results as they complete with `as_completed()`
5. Mark ledger updates (still sequential to avoid race conditions)

**Memory considerations:**
- Each thread: ~8MB stack
- 10 threads: ~80MB overhead
- 20 requests object: ~1MB total
- Total overhead: ~100MB (acceptable)

---

## Expected Results

### Benchmark Expectations

**Test case: 100 documents, 300ms average latency per request**

| Approach | Workers | Total Time | Throughput | Speedup |
|----------|---------|-----------|------------|---------|
| Sequential | 1 | 30,000ms (30s) | 3.3 docs/sec | 1.0x |
| Threading | 5 | 6,000ms (6s) | 16.7 docs/sec | 5.0x |
| Threading | 10 | 3,000ms (3s) | 33.3 docs/sec | 10.0x |
| Threading | 20 | 1,500ms (1.5s) | 66.7 docs/sec | 20.0x |

**Conservative estimate (including overhead):**
- With 10 workers: **8-15x speedup** (accounting for network variance and overhead)

### Success Criteria

✅ **Phase 2 evaluation passes if:**
1. Parallel version runs successfully without errors
2. Latency reduction: >5x speedup (conservative)
3. Throughput increase: >5x more docs/sec
4. No race conditions in ledger updates
5. Results match sequential baseline (same documents marked same)

❌ **Blockers:**
- Speedup <2x (indicates threading not working)
- Race conditions in ledger (parallel writes causing corruption)
- Memory issues (thread pool exhaustion)

---

## Implementation Phases

### Phase 2a: Analyze (CURRENT) ✅
- [x] Understand sequential implementation
- [x] Identify network I/O bottleneck
- [x] Design threading approach
- [x] Calculate expected speedup

### Phase 2b: Implement (NEXT)
- [ ] Create `staleness_monitor_optimized.py`
- [ ] ThreadPoolExecutor version
- [ ] Remove artificial delays
- [ ] Add timing/metrics capture

### Phase 2c: Benchmark (THEN)
- [ ] Create benchmark harness
- [ ] Sequential baseline measurement
- [ ] Parallel measurement (5, 10, 20 workers)
- [ ] Document timing results

### Phase 2d: Analyze Results (THEN)
- [ ] Calculate actual speedup
- [ ] Identify any issues
- [ ] Compare vs Rust expectations
- [ ] Document findings

### Phase 2e: Document (FINAL)
- [ ] Create Phase 2 Evaluation Report
- [ ] Add findings to knowledge base
- [ ] Recommendations for other I/O-bound modules
- [ ] Decision: Proceed with Phase 3 or iterate?

---

## Questions Before Implementation

1. **Test data:** Should I use real provenance ledger or mock data with simulated URLs?
   - **Recommendation:** Mock data (100 test URLs with known latencies) to ensure reproducible results

2. **Error handling:** How strict should error handling be?
   - **Current:** Silently ignores exceptions
   - **Recommendation:** Log errors but continue, don't fail entire batch

3. **Ledger updates:** Sequence matters?
   - **Current:** Marks status in ledger during request loop
   - **Recommendation:** Collect results, then update ledger sequentially after all requests complete (avoid race conditions)

4. **Rate limiting:** Should we implement exponential backoff?
   - **Current:** 200ms sleep between requests
   - **Recommendation:** No (parallel requests naturally space out); use timeout handling instead

5. **Worker count tuning:** Start with 10, or test multiple?
   - **Recommendation:** Test 5, 10, 20 workers to show scalability curve

---

## Key Metrics to Capture

### For Each Run:
```python
{
    'approach': 'sequential' | 'parallel_5' | 'parallel_10' | 'parallel_20',
    'sample_size': int,
    'total_time_seconds': float,
    'throughput_docs_per_sec': float,
    'success_count': int,
    'error_count': int,
    'latency_p50_ms': float,
    'latency_p95_ms': float,
    'latency_p99_ms': float,
}
```

### Comparison:
```python
{
    'speedup': parallel_time / sequential_time,
    'throughput_improvement': parallel_throughput / sequential_throughput,
    'resource_usage': {
        'memory_mb': float,
        'thread_count': int,
    }
}
```

---

## Next Steps

Ready to proceed with Phase 2b: Implementation

Will create:
1. `staleness_monitor_optimized.py` - ThreadPoolExecutor version
2. `benchmark_harness.py` - Test framework
3. Mock test data - 100 documents with simulated URLs
4. Run benchmarks and capture metrics
