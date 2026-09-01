# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

Excellent. I have all the context I need. Let me create a comprehensive implementation plan.---

## **Implementation Plan: Python + Rust Hybrid Architecture**

### **Problem Statement**
Your compliance & regulatory system currently runs all deterministic operations (rules evaluation, input/output validation, drift detection, data processing) in Python. This creates bottlenecks in three areas:
- **Performance**: Repetitive validation and rule checks run under Python's GIL, limiting concurrency.
- **Resource efficiency**: Large-scale drift checks and index operations consume significant memory due to Python runtime overhead.
- **Auditability**: Deterministic logic lives in dynamic code; Rust's compiler guarantees make rule execution verifiable and bulletproof.

### **Requirements Summary**
From your answers:
1. **Multi-faceted ROI**: Performance gains (10x on critical paths), cost efficiency (fewer machines needed), higher throughput, and audit-grade determinism.
2. **Move everything deterministic**: Compliance guardrails, drift detection, rules evaluation, and supporting operations.
3. **Local-first POC strategy**: Prove value in single-module before committing to full refactor.
4. **Minimal deployment friction**: PyO3 bindings for seamless Python ↔ Rust interaction, local testing on laptop, no microservice overhead yet.

### **Background: Architecture Decisions**

**Why PyO3 over other approaches?**
- PyO3 provides native Python bindings. Rust code compiles to `.pyd` (Windows) or `.so` (Linux), imported as standard Python modules.
- Zero-copy performance for simple data types; structured serialization (serde_json) for complex types.
- Async support via PyO3's coroutine integration.
- Simpler local development than subprocess/HTTP service; easier deployment to production later.

**Module Priority Order:**
1. **Compliance Guardrails** (smallest, highest-frequency): Input/output validation logic. Quick win to validate the pattern.
2. **Staleness Drift Detection** (medium, IO-bound but CPU-parallel): Hash comparisons, HTTP HEAD calls. Demonstrates async capabilities.
3. **Compliance Rules Engine** (largest, CPU-intensive): Rule parsing and evaluation. Biggest performance gain.

**Fallback Strategy:**
- Python implementations remain. Rust modules are loaded optionally. If compilation fails, system falls back to pure Python.
- Tests verify parity between Python and Rust implementations before switching.

---

### **Proposed Solution Architecture**

```
┌─────────────────────────────────────────────────────────┐
│         Python Orchestration Layer                       │
│  (FastAPI, Streamlit, pipeline_scheduler)               │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │Guardrails│   │ Drift   │   │ Rules   │
   │PyO3      │   │Detector │   │ Engine  │
   │Module    │   │PyO3     │   │PyO3     │
   │(Rust)    │   │Module   │   │Module   │
   │          │   │(Rust)   │   │(Rust)   │
   └────▲────┘   └────▲────┘   └────▲────┘
        │              │              │
   ┌────┴──────────────┴──────────────┴──────┐
   │        Rust Core Library                 │
   │  (amc_compliance_rs Cargo workspace)     │
   │                                          │
   │  - GuardrailValidator                    │
   │  - DriftChecker                          │
   │  - RulesEvaluator                        │
   │  - SharedTypes & Serialization           │
   └──────────────────────────────────────────┘
```

---

### **Task Breakdown: Test-Driven Development with Early Integration**

---

#### **Task 1: Phase 0 – Project Setup & Rust Toolchain Configuration**

**Objective:** Establish local Rust workspace, configure PyO3, and set up build pipeline for compilation on Windows laptop.

**Implementation Guidance:**
- Create `rust/` directory at project root (parallel to `backend/`, `streamlit_app/`).
- Initialize Cargo workspace with workspace members: `guardrails`, `drift_detector`, `rules_engine`, `shared`.
- Configure `Cargo.toml` with dependencies: `pyo3` (with `"abi3"` feature), `serde`/`serde_json`, `regex`, `sha2`, `tokio` (async).
- Add `pyproject.toml` to compile Rust bindings into `backend/` as native Python modules.
- Set up GitHub Actions or local script to verify both Python and Rust build on Windows.

**Test Requirements:**
- Verify `cargo build --release` succeeds on Windows.
- Verify `pip install -e .` (editable install of Rust bindings) creates `.pyd` files in site-packages.
- Run `python -c "import amc_compliance_rs; print(amc_compliance_rs.__version__)"` to confirm import.

**Demo:**
- Rust toolchain installed and ready on local machine.
- Cargo workspace compiles cleanly.
- PyO3 module importable from Python REPL.

---

#### **Task 2: Phase 1a – Compliance Guardrails Core (Rust)**

**Objective:** Implement input validation and output safety logic in Rust, matching the behavior of `compliance_guardrails.py`.

**Implementation Guidance:**
- Port `validate_input_query()` logic:
  - Regex patterns for prompt injection detection (compile patterns at module init for zero-cost matching).
  - Return struct with `is_safe`, `risk_flag`, `sanitized_query`.
- Port `validate_llm_output()` logic:
  - Regex patterns for unauthorized financial advice.
  - SEBI disclaimer injection.
  - Return struct with `is_valid`, `modified_answer`, `advice_shield_triggered`.
- Use `regex` crate with precompiled patterns (lazy_static or once_cell).
- Serialize/deserialize via `serde_json` for complex returns.
- No external I/O; pure string processing.

**Test Requirements:**
- Unit tests for each regex pattern (prompt injection, unauthorized advice).
- Integration test: call Rust function directly with test cases (safe query, injection attempt, financial advice).
- Verify output structure matches Python version exactly.
- Benchmark: measure latency vs Python (expect 10–50x improvement).

**Demo:**
- Rust module compiles and passes all unit tests.
- Test harness shows parity with Python implementation on 20 test cases.

---

#### **Task 3: Phase 1b – PyO3 Bindings for Guardrails**

**Objective:** Expose Rust guardrails as a Python-callable module.

**Implementation Guidance:**
- Create `amc_compliance_rs::guardrails` submodule exporting `GuardrailValidator` class (PyClass).
- Implement PyO3 methods: `validate_input(query: str) -> dict`, `validate_output(answer: str, domain: str) -> dict`.
- Return Python dicts (PyO3 auto-converts from Rust structs via serde).
- Add module-level functions: `amc_compliance_rs.validate_input_query()`, `validate_llm_output()`.
- Use `pyo3-build-config` to auto-detect Python version and compile .pyd/.so.

**Test Requirements:**
- PyO3 binding tests: call Rust functions from Python, verify return types.
- FFI safety: no panics on malformed input; all Rust panics caught and converted to Python exceptions.
- Performance micro-benchmarks: 1000 calls with random payloads.

**Demo:**
- Python can import and call Rust guardrails: `from amc_compliance_rs import validate_input_query`.
- Return values are valid Python dicts with expected keys.

---

#### **Task 4: Phase 1c – Integration & Testing (Guardrails)**

**Objective:** Swap Python guardrails for Rust bindings in existing code; verify zero functional regression.

**Implementation Guidance:**
- Create wrapper module `backend/app/compliance/guardrails_rust.py` that imports from `amc_compliance_rs`.
- Add feature flag in `config.py`: `USE_RUST_GUARDRAILS = True` (env var `AMC_RUST_GUARDRAILS`).
- Update `taxonomy_retrieval.py`, `retrieval.py` to conditionally call Rust or Python versions.
- Run existing test suite against both implementations; measure latency/memory.
- Document API compatibility and fallback behavior.

**Test Requirements:**
- End-to-end test: run compliance_dashboard and taxonomy_retrieval queries with Rust guardrails enabled.
- Output parity: 50 real queries processed, Rust and Python outputs identical.
- Latency comparison: measure median/p95/p99 times, document % improvement.
- Memory profile: compare peak RSS before/after.
- Fallback: if Rust module not available, system gracefully reverts to Python.

**Demo:**
- Full compliance dashboard works with Rust guardrails.
- Performance telemetry shows improvement.
- Feature flag allows easy toggling between Python and Rust.

---

#### **Task 5: Phase 2a – Staleness Drift Detection (Rust)**

**Objective:** Implement SHA-256 hashing and HTTP HEAD validation logic in Rust.

**Implementation Guidance:**
- Port `staleness_monitor.run_drift_check()`:
  - Accept list of document metadata (filename, stored hash, stored url).
  - Compute SHA-256 on local files (zero-copy using memory mapping where possible).
  - Issue HTTP HEAD requests to stored URLs (using `reqwest` async client).
  - Compare hashes; track status codes (200 = active, 404/5xx = broken).
  - Return `DriftReport` struct: `checked_count`, `drifted_count`, `not_found_count`, timestamp.
- Use `sha2` crate for hashing.
- Use `tokio` + `reqwest` for concurrent HTTP requests (parallel checks).
- Implement as `pub async fn run_drift_check(docs: Vec<DocMetadata>, sample_size: usize) -> DriftReport`.

**Test Requirements:**
- Unit tests for SHA-256 computation (verify against known hashes).
- Mock HTTP server tests: simulate HEAD requests (200, 404, 5xx).
- Concurrency test: 100 URLs, verify all checked in <1s (vs Python sequential ~10s).
- Output structure matches Python `DriftReport` dataclass.

**Demo:**
- Rust drift checker compiles and passes integration tests.
- Performance test shows 5–10x faster drift detection vs Python.

---

#### **Task 6: Phase 2b – PyO3 Bindings for Drift Detection**

**Objective:** Expose Rust drift checker as async-capable Python module.

**Implementation Guidance:**
- Create `amc_compliance_rs::drift_detector` submodule.
- Implement `DriftChecker` PyClass with async method `check_docs(docs: list[dict]) -> dict`.
- Use PyO3's coroutine integration to await Rust async code from Python's event loop.
- Return Python dict matching structure of `DriftReport`.
- Handle serialization of document lists via serde.

**Test Requirements:**
- Async Python integration: `asyncio.run(drift_checker.check_docs(...))`.
- Return type validation: `DriftReport` Python dict has expected fields.
- Concurrency: call multiple drift checks simultaneously from Python, verify no GIL blocking.

**Demo:**
- Python can call Rust drift checker asynchronously.
- Multiple checks run concurrently without blocking.

---

#### **Task 7: Phase 2c – Integration & Benchmarking (Drift Detection)**

**Objective:** Wire Rust drift detector into `pipeline_scheduler.py`; measure and document improvements.

**Implementation Guidance:**
- Create wrapper `backend/app/engine/drift_detector_rust.py` importing from `amc_compliance_rs`.
- Update `pipeline_scheduler.run_production_pipeline()` to use Rust drift checker.
- Add feature flag: `USE_RUST_DRIFT_DETECTOR = True`.
- Collect telemetry: execution time, memory, documents checked, detection accuracy.
- Create before/after comparison report.

**Test Requirements:**
- Full pipeline runs with Rust drift detector enabled.
- Accuracy: drift detection matches Python baseline (same files flagged as drifted/broken).
- Performance: benchmark on realistic dataset (100–1000 documents).
- Memory: compare peak RSS during drift check.

**Demo:**
- Full pipeline uses Rust drift detector.
- Performance telemetry dashboard shows improvements.
- Report documents 5–10x latency gain and 20–30% memory reduction.

---

#### **Task 8: Phase 3a – Compliance Rules Engine (Rust)**

**Objective:** Port rule evaluation logic from `rules_engine.py` to Rust.

**Implementation Guidance:**
- Port key data structures:
  - `Rule`: id, rule_type, title, condition, severity, confidence_threshold, applicability, region.
  - `ComplianceViolation`: fund_id, rule_id, severity, confidence, actual_value, threshold_value.
- Implement `RulesEvaluator`:
  - `load_rules(rules_json: str) -> Result<(), Error>` – parse rule set into memory.
  - `evaluate(fund_data: FundRecord) -> Vec<ComplianceViolation>` – test fund against all rules.
  - Condition evaluation: implement safe parser for expressions like `holdings.max_single_holding > 0.15`.
- Use `regex` for condition parsing; avoid eval-like constructs.
- Handle rule applicability filters (e.g., "only for equity funds").
- Return violations with confidence scores.

**Test Requirements:**
- Unit tests: verify rule parsing (valid/invalid conditions).
- Integration: evaluate sample fund record against 10 rules, verify all violations detected.
- Accuracy: results match Python engine on test dataset.
- Stress test: evaluate 1000 funds against 50 rules; measure throughput (expect 10–100x faster).

**Demo:**
- Rust rules engine compiles and passes integration tests.
- Throughput benchmark shows 50+ rule evaluations/second per fund.

---

#### **Task 9: Phase 3b – PyO3 Bindings for Rules Engine**

**Objective:** Expose Rust rules evaluator as Python module.

**Implementation Guidance:**
- Create `amc_compliance_rs::rules_engine` submodule.
- Implement `RulesEvaluator` PyClass with methods:
  - `load_rules(rules_json: str)` – load rule set.
  - `evaluate(fund_data: dict) -> list[dict]` – return list of violation dicts.
  - `get_rule_count() -> int` – introspection.
- Serialize violations to Python dicts.
- Error handling: Python exceptions for invalid rules, fund data.

**Test Requirements:**
- PyO3 binding tests: load rules, evaluate fund, get violations.
- Type safety: violations are valid Python dicts with expected keys.
- Error cases: invalid JSON rules, missing fund fields (proper exceptions).

**Demo:**
- Python can import and use Rust rules engine.
- `from amc_compliance_rs import RulesEvaluator` works.

---

#### **Task 10: Phase 3c – Integration & Validation (Rules Engine)**

**Objective:** Wire Rust rules engine into compliance API; validate correctness at scale.

**Implementation Guidance:**
- Update `backend/app/api/routes/compliance.py` (or create new endpoint).
- Create wrapper `backend/app/compliance/rules_engine_rust.py`.
- Add feature flag: `USE_RUST_RULES_ENGINE = True`.
- For each fund scorecard request, call Rust engine to evaluate rules.
- Compare results with Python baseline on test dataset.
- Validate violations match production expectations.

**Test Requirements:**
- End-to-end: compliance dashboard queries use Rust rules engine.
- Correctness: 100 fund records evaluated, all violations match Python baseline.
- API response structure: unchanged; violations returned in expected format.
- Load test: 50 concurrent fund evaluations; measure latency, throughput.

**Demo:**
- Compliance dashboard displays scorecard with Rust-computed violations.
- API responses identical to Python version.
- Load test shows 10–100x improvement in throughput.

---

#### **Task 11: Phase 4 – Documentation & Handoff**

**Objective:** Document the hybrid architecture, performance gains, and rollout strategy.

**Implementation Guidance:**
- Create `RUST_ARCHITECTURE.md`:
  - Architecture diagram (Python orchestration + Rust core).
  - Module breakdown: what moved to Rust, why.
  - PyO3 bindings: how to compile, deploy, troubleshoot.
  - Feature flags and fallback behavior.
- Create `PERFORMANCE_REPORT.md`:
  - Before/after benchmarks: latency, memory, throughput per module.
  - Hardware spec (your laptop).
  - Test dataset size and real-world applicability.
- Create `DEPLOYMENT_GUIDE.md`:
  - Local development setup: install Rust, compile bindings, run tests.
  - CI/CD integration: GitHub Actions for Windows/Linux builds.
  - Production deployment: Rust modules in Docker, pip wheel distribution.
- Create `ROLLOUT_PLAN.md`:
  - Phase 2 roadmap: testing in staging, migration to production.
  - Rollback procedure: feature flags allow instant revert to Python.
  - Monitoring: telemetry to track Rust module performance in production.

**Test Requirements:**
- Documentation completeness: all setup steps are reproducible on a fresh machine.
- Code examples: sample usage of each Rust module from Python.
- Troubleshooting guide: common issues and solutions.

**Demo:**
- Complete documentation package.
- New developer can set up local Rust environment in <1 hour.
- Clear roadmap for next phases (data processing, index building).

---

## **Summary: Why This Plan Works**

1. **POC-first de-risks the approach**: Phase 1 (guardrails) is small, fastest to validate. If ROI is proven, expand to phases 2–3.
2. **Incremental integration**: Each phase ends with working, tested functionality. No "big bang" risky refactor.
3. **Local-first testing**: PyO3 bindings compile and run on your laptop. No containerization overhead yet.
4. **Graceful fallback**: Feature flags allow instant revert to Python if issues arise.
5. **Performance transparency**: Each phase includes benchmarks and comparisons, so you have clear visibility into ROI.
6. **Foundation for production**: Documentation and build pipeline set up for easy deployment later.

---

## **Does this plan look good, or would you like me to adjust anything?**

I can refine scope (e.g., add index building to Phase 3), adjust module order, add more detail to specific tasks, or discuss deployment/CI concerns. What resonates, and what needs tweaking?