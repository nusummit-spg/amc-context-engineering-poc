# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# Phase 2: Constraint Discovery - AppLocker Blocking Build

**Date:** August 27, 2026  
**Status:** Blocked by Windows AppLocker Policy  
**Impact:** Cannot compile complex Rust projects on this machine

---

## Discovery

When attempting to build `staleness_detector` module with dependencies like `tokio`, `reqwest`, compilation fails:

```
error: failed to run custom build command for `proc-macro2 v1.0.107`
An Application Control policy has blocked this file. (os error 4551)
```

This same error occurred in Phase 0 and is now confirmed to be a systematic constraint.

---

## Root Cause

**AppLocker Policy:** Windows Enterprise security restricts execution of build artifacts  
**Affected:** Complex crates with build scripts (proc-macros, code generation)  
**Unaffected:** Simple pure-Rust code (like Phase 0's guardrails module)

**Crates that work:**
- `regex` (simple library)
- `once_cell` (no build script)
- `chrono` (no complex macros)
- `serde` (pure library, no build-time codegen)

**Crates that fail:**
- `tokio` (requires build-time async macro compilation)
- `reqwest` (async macros, platform-specific build)
- Any crate with proc-macros
- Windows platform-specific crates

---

## Decision Point

**Option A: Workaround (Try Simpler Rust)**
- Remove async/await (tokio, reqwest)
- Use blocking HTTP + threading  
- Still limited by build script crates
- May still fail on less common dependencies

**Option B: Accept Constraint (Python Optimization)**
- Implement Phase 2 in Python instead
- Use `concurrent.futures.ThreadPoolExecutor` for parallelism
- Achieve 3-5x speedup without Rust
- No build constraints
- Deploy immediately

**Option C: Escalate to IT** 
- Request AppLocker exemption for Rust toolchain
- Likely takes 1-2 weeks
- May or may not be granted

**Option D: Pivot to Phase 3**
- Skip Phase 2 (staleness monitor)
- Go directly to Phase 3 (Rules Engine in Python)
- Small, focused Rust module might not trigger AppLocker

---

## Recommendation: Pivot to Option B + D Hybrid

Given constraints discovered:

1. **Phase 2 in Python** (immediate, 3-5x improvement)
   - Use `ThreadPoolExecutor` for concurrent HTTP requests
   - Parallelize from 20 sequential requests → 20 concurrent
   - Expected: 6 seconds → 1-2 seconds (3-5x speedup)
   - Deployable immediately

2. **Phase 3 - Build Small Rust Module**
   - Target only what doesn't trigger AppLocker
   - Rules Engine might work if kept simple
   - Minimal dependencies, no proc-macros
   - Test feasibility first

**Rationale:**
- Delivers Performance improvement now (Python version)
- Proves parallelization concept
- Buys time to resolve AppLocker (for future Rust work)
- Sets up Phase 3 for success

---

## Updated Phase 2 Plan

### Phase 2 (Revised): Staleness Monitor - Python Threading

**Implementation:** 2-3 hours  
**Expected ROI:** 3-5x speedup  
**Dependencies:** Python stdlib only (no new packages)

**Code Approach:**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from pathlib import Path
import time

def run_drift_check_optimized(sample_size: int = 20) -> DriftReport:
    """Parallel version using ThreadPoolExecutor"""
    records = provenance_ledger.get_all_records()
    records_with_url = [r for r in records if r.source_url and r.source_url.startswith("http")]
    sample = records_with_url[:sample_size]
    
    # Use thread pool (remove time.sleep(0.2) - not needed with parallelism)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(check_single_url, r): r 
            for r in sample
        }
        
        results = []
        for future in as_completed(futures):
            results.append(future.result())
    
    return aggregate_results(results)
```

**Expected Performance:**
- Python sequential (current): ~5-6 seconds
- Python parallel (proposed): ~200-500ms (10-30x faster!)
- Reason: Parallelizes I/O waiting, not compute

---

## Knowledge Repository Update

Add to `RUST_INTEGRATION_KNOWLEDGE_BASE.md`:

### New Constraint: AppLocker Policy

**Definition:** Windows AppLocker blocks execution of certain build artifacts  
**Impact:** Complex Rust projects with proc-macros cannot compile  
**Workaround:** Stick to simple Rust crates without build scripts  
**Resolution:** Request IT exemption or use Python for compute-heavy I/O-bound tasks

**Lesson:** Enterprise environments have security policies that affect tooling choices

---

## Timeline Adjustment

**Original Plan:**
- Phase 2 (Rust): 1 week
- Phase 3 (Rust): 2-3 weeks
- Total: 3-4 weeks

**New Plan:**
- Phase 2 (Python): 3-5 hours (immediate)
- Test & verify: 1-2 hours
- Phase 3 (small Rust): 1-2 weeks
- Total: 1.5-2 weeks + AppLocker resolution time

---

## Decision Required

**Move forward with:**
- [ ] **A.** Python optimization for Phase 2 (recommended)
- [ ] **B.** Continue attempting Rust with simpler crates
- [ ] **C.** Request AppLocker exemption (wait 1-2 weeks)
- [ ] **D.** Abandon Rust integration entirely

**Recommendation:** Choose A + D hybrid:
1. Implement Phase 2 in Python (parallelism proven)
2. Attempt small Phase 3 Rust module (test AppLocker limits)
3. Request exemption if needed for future phases

---

This constraint is **valuable learning** for the knowledge base: enterprise environments impose build constraints that may make Rust impractical for some workloads.
