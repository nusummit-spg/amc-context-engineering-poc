# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# Phase 3 Plan: CPU-Bound Module Evaluation
## Rules Engine Optimization - Rust vs Python

**Date:** August 27, 2026  
**Status:** PLANNING  
**Target Module:** Compliance Rules Engine (Highest Priority)

---

## Executive Summary

### Phase 3 Objective
Evaluate Python vs Rust for **CPU-bound** compliance workload to demonstrate when Rust provides real advantage.

### Why Rules Engine?

**Performance Opportunity:**
- Current execution: 15-60ms per fund, 1.5-6 seconds for 100-fund batch
- **Expected Rust speedup: 5-10x**
- Real production impact: Compliance audits could run 5-10x faster

**Ideal for Rust:**
- ✅ Pure computation (no I/O)
- ✅ Deterministic operations
- ✅ High CPU intensity
- ✅ Clear speedup potential
- ✅ High invocation count (amortizes FFI overhead)

**Module:** `backend/app/compliance/rules_engine.py`

---

## What Rules Engine Does

### Core Functionality
1. **Loads compliance rules** (~30 default rules from SEBI, SEC, ESMA)
2. **For each fund:** Evaluates all rules against fund data
3. **Extracts metrics** using dotted path parsing ("holdings.max_sector_holding")
4. **Compares values** against thresholds using 6 operators (>, >=, <, <=, ==, !=)
5. **Generates violations** with evidence, severity, and confidence scores

### Example Rule
```python
{
    "id": "MAX_SECTOR_EXPOSURE",
    "condition": "holdings.max_sector_holding > 0.35",
    "description": "Single sector exposure exceeds 35%",
    "severity": "HIGH",
    "applicable_to": ["equity_fund", "balanced_fund"]
}
```

### Computational Pattern
```
For each fund in batch:
    For each rule in rules:
        1. Parse condition string ("holdings.max_sector_holding > 0.35")
           └─ Extract: metric_path, operator, threshold
        2. Check rule applicability (category matching)
        3. Extract metric value from fund (nested dict traversal)
        4. Compare value vs threshold
        5. If violated: Create violation object
```

**Performance Bottleneck:**
- **String parsing** repeated per rule evaluation (no pre-compilation)
- **Nested dict traversal** for metric extraction (Python slower than Rust)
- **Lambda-based comparators** (functional overhead in Python)
- **Batch processing** (1000s of funds × 30 rules = 30,000 evaluations)

---

## Proposed Architecture

### Python Version (Current - Baseline)

```python
# backend/app/compliance/rules_engine.py
class RulesEngine:
    def evaluate_fund(self, fund_id, fund_data):
        """Current implementation - pure Python"""
        violations = []
        for rule in self.rules:
            # 1. Parse condition
            parts = self._parse_condition(rule['condition'])
            
            # 2. Check applicability
            if not self._is_applicable(rule, fund_data):
                continue
            
            # 3. Extract metric
            value = self._get_metric_value(fund_data, parts['metric_path'])
            
            # 4. Compare
            operator_func = self.COMPARATORS[parts['operator']]
            violated = operator_func(value, parts['threshold'])
            
            if violated:
                violations.append(...)
        
        return violations
```

**Performance:** ~50ms per fund (30 rules × ~1.7ms per rule)

### Rust Version (New - Optimized)

```rust
// rust/compliance_rules_rs/src/lib.rs
#[derive(Deserialize)]
pub struct Rule {
    id: String,
    condition: String,  // Pre-compiled at startup
    ...
}

#[derive(Deserialize)]
pub struct Fund {
    id: String,
    data: Value,  // JSON value
}

pub struct RulesEngineRust {
    rules: Vec<CompiledRule>,  // Pre-compiled conditions
}

impl RulesEngineRust {
    pub fn evaluate_fund(&self, fund: &Fund) -> Vec<Violation> {
        // Optimized batch evaluation
        self.rules.par_iter()  // Parallel iteration
            .filter_map(|rule| {
                if !rule.is_applicable(&fund.data) { return None; }
                
                let value = self.extract_metric(&fund.data, &rule.metric_path)?;
                let threshold = rule.threshold;
                
                if rule.operator.compare(value, threshold) {
                    Some(Violation {
                        rule_id: rule.id.clone(),
                        ...
                    })
                } else {
                    None
                }
            })
            .collect()
    }
}
```

**Performance:** ~5-10ms per fund (5-10x speedup due to):
- Pre-compiled rules (no string parsing)
- Compiled comparators (direct CPU instructions)
- Memory locality optimization
- Potential parallelization with rayon

---

## Phase 3 Execution Plan

### Phase 3a: Analyze & Design (Week 1)
- [x] Identify rules engine as best candidate ✅
- [ ] Read full rules_engine.py implementation
- [ ] Understand rule data structures and evaluation logic
- [ ] Profile current implementation (measure exact bottlenecks)
- [ ] Design Rust module architecture
- [ ] Create benchmark baseline

**Deliverables:**
- `PHASE_3A_ANALYSIS.md` - Design document
- Baseline benchmark data

### Phase 3b: Implement Rust Module (Week 2-3)
- [ ] Create `rust/compliance_rules_rs/Cargo.toml`
- [ ] Implement rule parsing and compilation
- [ ] Implement metric extraction (dotted path traversal)
- [ ] Implement comparison operators (all 6: >, >=, <, <=, ==, !=)
- [ ] Implement violation generation
- [ ] Create ctypes FFI bindings

**Deliverables:**
- `compliance_rules_rs` Rust crate
- FFI library (.dll on Windows)

### Phase 3c: Create Python Integration (Week 3)
- [ ] Create `backend/app/compliance/rules_engine_rust.py`
- [ ] Implement ctypes FFI wrapper
- [ ] Add fallback to Python version (graceful degradation)
- [ ] Test correctness (exact same violations as Python version)

**Deliverables:**
- `rules_engine_rust.py` wrapper

### Phase 3d: Comprehensive Benchmarking (Week 3-4)
- [ ] Create benchmark harness (like Phase 2)
- [ ] Generate test data (100-1000 funds with realistic complexity)
- [ ] Measure: Sequential, Parallel Rust, Python multiprocessing
- [ ] Capture: Latency, throughput, memory usage
- [ ] Compare results to expectations (5-10x)

**Deliverables:**
- `PHASE_3_BENCHMARK_RESULTS.md`
- `phase3_benchmark_results/`

### Phase 3e: Analysis & Documentation (Week 4)
- [ ] Analyze results vs predictions
- [ ] Document lessons learned
- [ ] Update knowledge base
- [ ] Create hybrid architecture recommendations
- [ ] Plan Phase 4 (full integration)

**Deliverables:**
- `PHASE_3_EVALUATION_REPORT.md`
- Updated knowledge base

---

## Success Criteria

### Correctness
- ✅ Rust version produces identical violations as Python
- ✅ All 6 comparison operators work correctly
- ✅ Rule applicability filtering matches Python behavior
- ✅ Edge cases handled (null values, missing fields, invalid data)

### Performance
- ✅ Speedup measured: **Target 5-10x, Acceptable 3-5x**
- ✅ Per-fund latency: Target <10ms (from current ~50ms)
- ✅ Batch processing: 100 funds should complete in <1 second

### Engineering
- ✅ FFI works without crashes
- ✅ Memory managed correctly (no leaks)
- ✅ Graceful fallback to Python if Rust library unavailable
- ✅ Code is maintainable and documented

### Enterprise
- ✅ Compiles successfully (or AppLocker exemption requested)
- ✅ Can be deployed to production
- ✅ Monitoring/logging integration planned

---

## Technical Details

### Rust Module Structure

```
rust/compliance_rules_rs/
├── Cargo.toml                    # Dependencies: serde, serde_json, rayon
├── src/
│   ├── lib.rs                    # Main FFI interface
│   ├── rule_engine.rs            # Core evaluation logic
│   ├── metric_extractor.rs       # Dotted path traversal
│   └── comparators.rs            # Comparison operators
└── tests/
    ├── test_evaluation.rs        # Correctness tests
    └── test_performance.rs       # Benchmarks
```

### FFI Interface

**Rust export (ffi.rs):**
```rust
#[no_mangle]
pub extern "C" fn evaluate_fund(
    fund_json: *const c_char,
    rules_json: *const c_char,
) -> *mut c_char {
    // Evaluate and return violations as JSON
    // Caller responsible for freeing memory
}
```

**Python wrapper (rules_engine_rust.py):**
```python
from ctypes import CDLL, c_char_p

def evaluate_fund_rust(fund_id, fund_data, rules):
    """Wrapper around Rust FFI"""
    lib = CDLL('./compliance_rules_rs.dll')
    fund_json = json.dumps(fund_data).encode()
    rules_json = json.dumps(rules).encode()
    
    result_ptr = lib.evaluate_fund(fund_json, rules_json)
    result_json = ctypes.string_at(result_ptr).decode()
    
    return json.loads(result_json)
```

### Testing Strategy

**Correctness Testing:**
1. Load 10 sample funds from production database
2. Run Python version → get violations
3. Run Rust version → get violations
4. Assert violations are identical
5. Test edge cases: null values, missing fields, large numbers

**Performance Testing:**
1. Generate 1000 realistic fund records
2. Measure sequential Python
3. Measure sequential Rust
4. Measure parallel Rust (rayon)
5. Measure Python multiprocessing
6. Calculate speedup factors
7. Profile memory usage

---

## AppLocker Handling

**Current Status:** Rust compilation blocked by AppLocker

**Phase 3 Options:**

### Option A: Request IT Exemption (Parallel with Development)
- Submit formal exemption request now
- Start Rust development in WSL2 or local machine
- When exemption approved: test on Windows

**Template:**
```
Subject: Request AppLocker Exemption for Rust Development

We are evaluating Rust for compliance rule evaluation as part of 
performance optimization initiative. Phase 2 evaluation showed Python 
threading limited by CPU computation.

Please exempt these paths from AppLocker:
- C:\Users\[username]\.cargo\bin\*
- C:\Users\[username]\.cargo\registry\*
- C:\Users\[username]\AppData\Local\Temp\cargo-*

Project: AMC Compliance Rules Engine (Phase 3 evaluation)
Duration: 2-3 weeks (evaluation phase)
Impact: Development workstations only; production binary pre-compiled
```

### Option B: Build in Unrestricted Environment (Immediate)
- Use WSL2 if available
- Or: Build in CI/CD Linux environment
- Result: `.dll` binary for Windows testing
- No AppLocker issues (only binary, no compilation on Windows)

### Option C: Pure Python Optimization (Fallback)
- If Rust compilation blocked and WSL2 unavailable
- Optimize Python rules engine (caching, JIT, etc.)
- Expected improvement: 2-3x (not 5-10x, but acceptable)

---

## Expected Outcomes

### If Rust Compilation Works
- **Speedup: 5-10x**
- **Business impact: Compliance audits run 5-10x faster**
- **Validates:** Rust is worth using for CPU-bound compliance operations
- **Architecture decision:** Use Rust for deterministic rules in production

### If AppLocker Blocks Temporarily
- **Continue in parallel:** Build in WSL2 or CI/CD
- **Timeline: +1 week**
- **Still achieves:** Same Rust speedup + knowledge base entry on AppLocker workarounds

### If Rust Shows <3x Speedup
- **Root cause analysis:** Profile where time is spent
- **Decision point:** May indicate FFI overhead dominates (like Phase 0 guardrails)
- **Action:** Optimize Python version, batch multiple evaluations per FFI call, or redesign

---

## Knowledge Base Considerations

### Expected Learning: CPU-Bound Scenario

**Scenario:** Compliance rules engine - deterministic computation, high invocation count  
**Expected:** Rust 5-10x faster (no I/O, pure CPU)  
**Actual:** TBD after Phase 3 benchmarking  

**Key variables:**
- FFI overhead vs computation time ratio
- Effective memory utilization
- Parallelization opportunities (rayon)
- Pre-compilation benefits (rules compiled at startup)

### Contrast with Phase 2
| Aspect | Phase 2 (Staleness) | Phase 3 (Rules) |
|--------|-------------------|-----------------|
| **Bottleneck** | Network I/O | CPU computation |
| **Python advantage** | Simple threading | Multiprocessing overhead |
| **Rust advantage** | Marginal (I/O-bound) | Significant (CPU-bound) |
| **Expected speedup** | 8-15x (same as Rust) | 5-10x (Rust only) |
| **Decision** | Python sufficient | Rust worthwhile |

---

## Timeline & Milestones

**Week 1 (This week):**
- [ ] Finalize Phase 3a design
- [ ] Request IT AppLocker exemption
- [ ] Create baseline benchmarks

**Week 2-3:**
- [ ] Implement Rust module
- [ ] Create FFI bindings
- [ ] Implement Python wrapper

**Week 4:**
- [ ] Run comprehensive benchmarks
- [ ] Analyze results
- [ ] Document findings
- [ ] Decision: Ready for Phase 4 (full integration)

**Target completion:** 4 weeks from start of Phase 3a

---

## Resource Requirements

### Tools
- Rust toolchain (rustup)
- VS Code with Rust Analyzer
- Python ctypes (standard library)

### Knowledge
- Rust fundamentals (already established from Phase 0)
- FFI concepts (similar to Phase 0)
- Compliance rules understanding (from rules_engine.py)

### External
- Realistic test data (100-1000 fund records with actual complexity)
- Potential IT AppLocker exemption (1-5 business days)

---

## Success Definition

**Phase 3 is successful if:**

1. ✅ Rust rules engine compiles and runs without crashes
2. ✅ Produces identical violations to Python baseline
3. ✅ Shows ≥3x speedup (ambitious target 5-10x)
4. ✅ FFI overhead is acceptable (<20% of total time)
5. ✅ Memory usage is reasonable
6. ✅ Results are thoroughly documented
7. ✅ Knowledge base updated with CPU-bound scenario learnings

**Phase 3 enables Phase 4 if:**
- Rust speedup is ≥3x (justifies production deployment)
- FFI integration is solid (no crashes, memory leaks)
- Can be integrated into existing pipeline

---

## Next Decision Point

After Phase 3 benchmarking:

**If speedup ≥3x:**
→ Proceed to **Phase 4: Full Hybrid Integration** (production deployment)

**If speedup <3x:**
→ Analyze root cause: Is it FFI overhead? Complex data structures? Pre-compile rules?  
→ Decide: Optimize further, or accept Python for this module?

**If AppLocker blocks compilation:**
→ Use WSL2/CI/CD to build binary (same evaluation, different toolchain)  
→ Add AppLocker constraint to knowledge base for future reference

---

## Questions to Address

**Q: Will AppLocker block Rust compilation for Phase 3?**
A: Likely, but we have proven workarounds (WSL2, CI/CD, IT exemption request).

**Q: What if FFI overhead is too high?**
A: Batch multiple fund evaluations per FFI call, or accept 2-3x speedup from optimized Python.

**Q: How does Phase 3 differ from Phase 0 (Guardrails)?**
A: Phase 0 had tiny operations (0.003ms) where FFI overhead (0.2ms) dominated. Phase 3 has large operations (50ms) where FFI is <1% overhead.

**Q: Is rules engine the only option?**
A: No, but it's the best candidate (clear CPU-bound, high opportunity). NER pipeline (Layer A) is second priority.

**Q: What about existing Rust compliance_guardrails module?**
A: Already shows no speedup (FFI overhead dominates). Phase 3 will demonstrate proper batching/design.

