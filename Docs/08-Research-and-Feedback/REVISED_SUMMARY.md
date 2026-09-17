# Human Feedback Loop — Revised Summary

**Date:** 2026-09-03  
**Status:** Corrected based on actual architectural context

---

## Architecture Correction

The `human-feedback-loop` module is a **focused, single-purpose library**, not a monolithic pipeline:

```
┌─────────────────────────────────────────┐
│ AMC (host application)                  │
│ • Owns: session, response, feedback UI  │
│ • Writes to: response_feedback,         │
│            query_evidence, violations   │
│            (audit schema)               │
└─────────────┬───────────────────────────┘
              │
              │ start_feedback_loop(...)
              ▼
┌─────────────────────────────────────────┐
│ human-feedback-loop (this module)       │
│ • Steps 1–4: NER, enrichment, rules,    │
│            root cause classification    │
│ • Responsibility: Build                 │
│   UnifiedEvaluationRecord               │
│ • Output: Record struct (no DB writes)  │
└─────────────┬───────────────────────────┘
              │
              │ UnifiedEvaluationRecord
              ▼
┌─────────────────────────────────────────┐
│ AMC (consumer)                          │
│ • Receives: UnifiedEvaluationRecord     │
│ • Persists to: audit schema tables      │
│ • Invokes: Evaluation Layer (if repair) │
└─────────────────────────────────────────┘
              │
              │ (if repair=true)
              ▼
┌─────────────────────────────────────────┐
│ Evaluation Layer (external)             │
│ • Tier 2–3: NLI, LLM evaluation         │
│ • Returns: Enriched record              │
└─────────────────────────────────────────┘
```

---

## Revised Findings

### ✅ What the Module Does Correctly

1. **Steps 1–4 Pipeline** — Correctly implements classification, enrichment, routing, adjudication
2. **Concurrency Model** — Steps 1+2 parallel, Steps 3+4 sequential ✅
3. **Type Safety** — Full Pydantic models for all inputs/outputs ✅
4. **Adapter Pattern** — Database and evidence adapters properly decoupled ✅
5. **Error Handling** — Graceful degradation, retry sweep working ✅
6. **No Side Effects** — Module doesn't write to DB (that's AMC's job) ✅

### ⚠️ Remaining Gaps (Not Schema-Related)

#### Gap 1: Missing Step 6 (Repair Analysis)

**Current:** Steps 1–4 produce root_cause + severity, then... nothing  
**Expected:** Step 6 should compute `repair` flag and `repair_target`

**Why it matters:**
- AMC needs to know: "Should we invoke Evaluation Layer?"
- Evaluation Layer needs to know: "Target graph or vector space?"

**Add to UnifiedEvaluationRecord:**
```python
class UnifiedEvaluationRecord(BaseModel):
    # ... existing fields ...
    repair: bool = False                          # NEW
    repair_target: Literal["vector", "graph", None] = None  # NEW
```

**Implement Step 6:**
```python
class RepairAnalysisService:
    def run(self, adjudication_result) -> RepairAnalysisResult:
        root_cause = adjudication_result.root_cause
        
        # Routing logic
        if root_cause in {KNOWLEDGE, RETRIEVAL, GRAPH}:
            return RepairAnalysisResult(repair=True, repair_target="graph")
        elif root_cause == MODEL:
            return RepairAnalysisResult(repair=True, repair_target="vector")
        else:  # PRESENTATION, FEEDBACK_INVALID, etc.
            return RepairAnalysisResult(repair=False, repair_target=None)
```

**Effort:** 4–6 hours

---

#### Gap 2: Incomplete EvidencePack Model

**Current:** `EvidenceSnapshot` is minimal:
```python
class EvidenceSnapshot(BaseModel):
    response_id: str
    original_query: str
    response_text: str
    entity_name: Optional[str] = None
    evidence_selected: list[EvidenceChunk] = []
```

**Needed:** Full `EvidencePack` with all D0–D3 fields (from design §2.7):
```python
class EvidencePack(BaseModel):
    response_id: str
    original_query: str
    response_text: str
    entity_name: Optional[str] = None
    
    # Retrieval artifact
    source_ids: list[str] = []
    source_versions: list[str] = []
    chunk_ids: list[str] = []
    vector_scores: list[float] = []
    
    # Graph & taxonomy
    graph_paths: list[dict] = []
    taxonomy_nodes: list[dict] = []
    
    # Evidence selection
    selected_context: list[dict] = []
    rejected_context: list[dict] = []
    
    # Citations & metadata
    citations: list[dict] = []
    source_authority: list[str] = []
    effective_dates: list[datetime] = []
    content_hashes: list[str] = []
```

**Why it matters:**
- Evaluation Layer needs full context for deep evaluation
- AMC needs complete data for audit trail
- Enables proper citation tracking

**Effort:** 6–8 hours (coordinate with AMC's evidence adapter)

---

#### Gap 3: No Evaluation Layer Trigger Mechanism

**Current:** UnifiedEvaluationRecord is returned, but:
- How does Evaluation Layer know to pick it up?
- What's the contract/interface?

**Expected:** Either:

Option A: **Callback mechanism**
```python
config = FeedbackLoopConfig(
    evaluation_layer_callback=invoke_evaluation_layer  # Optional
)

# In IngestService
if record.repair and config.evaluation_layer_callback:
    config.evaluation_layer_callback(record)
```

Option B: **Return value signals downstream**
```python
# AMC checks: if record.repair, invoke Evaluation Layer
def on_ingest(...) -> bool:
    record = builder.build(row)
    if record.repair:
        # AMC responsibility: invoke Evaluation Layer
        evaluation_layer.process(record)
    return True
```

**Recommendation:** Option B (simpler, no module dependencies)  
**Effort:** 0 hours (just document the contract)

---

## Revised Priority List

Now that we understand the actual architecture:

### 🔴 Blocking Production (Must Fix)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| **1** | Implement Step 6 (RepairAnalysisService) | 4–6h | AMC needs `repair` flag to decide whether to invoke Eval Layer |
| **2** | Extend to full EvidencePack model | 6–8h | Eval Layer needs complete D0–D3 context |
| **3** | Document Evaluation Layer contract | 1–2h | Make clear how AMC triggers Eval Layer (if repair=true) |

### 🟡 High Priority (Should Fix)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| **4** | Add response existence validation | 1–2h | Fail-fast on invalid responses |
| **5** | Add trace IDs for observability | 2–3h | End-to-end latency tracking |
| **6** | Improve dependency logging | 1h | Distinguish missing deps from failures |

### 🟢 Polish (Nice to Have)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| **7** | Add metrics/counters | 2–3h | Production monitoring |
| **8** | Batch logging correlation | 1–2h | Better debugging |

---

## Corrected Schema Integration Analysis

**Previous claim:** "Module doesn't write to audit schema" ❌  
**Correction:** This is **by design**. AMC handles it ✅

### What This Module Owns
- ✅ `UnifiedEvaluationRecord` data structure
- ✅ Population of fields: root_cause, severity, entry_route, dissatisfaction_evidence
- ✅ Audit-quality classification logic (Steps 1–4)

### What AMC Owns
- ✅ Persistence to response_feedback table
- ✅ Persistence to query_evidence table
- ✅ Persistence to violations table (after Eval Layer confirms)
- ✅ Invocation of Evaluation Layer

### What Evaluation Layer Owns
- ✅ Tier 2–3 evaluation (NLI, LLM)
- ✅ Updating: deterministic_results, gnn_plausibility_score, semantic_results, llm_evaluation
- ✅ Final adjudication_verdict + confidence
- ✅ Writing violations to audit schema (confirmed verdicts only)

**Result:** Clean separation of concerns ✅

---

## Corrected Recommendations

### Remove from scope:
- ❌ Write response_feedback (AMC does this)
- ❌ Write query_evidence (AMC does this)
- ❌ Write violations (Evaluation Layer does this)
- ❌ Full audit metadata tracking (AMC does this)

### Keep in scope:
- ✅ Implement Step 6 (repair analysis)
- ✅ Extend to full EvidencePack
- ✅ Document Eval Layer trigger contract
- ✅ Add observability (trace IDs, metrics)
- ✅ Improve error handling

---

## Updated Effort Estimate

**Previous:** ~26–32 hours (incorrect, included schema writes)  
**Corrected:** ~14–20 hours

### Breakdown
- Step 6 (RepairAnalysisService): 4–6h
- Full EvidencePack model: 6–8h
- Eval Layer contract docs: 1–2h
- Response validation + observability: 3–5h

**Total: 14–21 hours** ✅

---

## Code Quality Verdict

**Overall: 8.5/10** ✅

### Strengths (unchanged)
- Correct pipeline architecture
- Proper concurrency model
- Good type safety
- Graceful degradation
- Clean adapter pattern
- Realistic scenario tests

### Weaknesses (corrected interpretation)
- Missing Step 6 (repair analysis)
- Incomplete EvidencePack model
- No Eval Layer invocation mechanism
- Limited observability (trace IDs, metrics)

### Not issues (were incorrectly flagged)
- ✅ No schema writes — correct by design
- ✅ No violations table — Eval Layer responsibility
- ✅ No audit metadata writes — AMC responsibility

---

## Production Readiness Checklist

| Item | Status | Notes |
|------|--------|-------|
| Core pipeline (Steps 1–4) | ✅ Ready | Tested with realistic scenarios |
| Concurrency model | ✅ Ready | Steps 1+2 parallel enforced |
| Type safety | ✅ Ready | Full Pydantic models |
| Error handling | ✅ Ready | Retry sweep, graceful degradation |
| Tests | ✅ Good | Scenario-based coverage; Step 6 tests to add |
| **Step 6 (repair analysis)** | ❌ Missing | Blocking; 4–6h to implement |
| **EvidencePack model** | ⚠️ Incomplete | High priority; 6–8h to extend |
| **Eval Layer contract** | ⚠️ Undocumented | 1–2h to clarify |
| Observability (trace IDs) | ⚠️ Minimal | 2–3h to add |
| Metrics | ⚠️ None | 2–3h to add |

---

## Next Steps

### Week 1: Core Implementation
1. Implement Step 6 (RepairAnalysisService)
   - Add `repair` and `repair_target` fields
   - Implement priority-based routing logic
   - Add unit tests

2. Extend EvidencePack model
   - Add all D0–D3 fields from design
   - Update EvidenceAdapter interface
   - Update tests

3. Document Eval Layer contract
   - Write: "When repair=true, invoke Evaluation Layer with UnifiedEvaluationRecord"
   - Clarify: Field ownership and lifecycle

### Week 2: Polish & Testing
4. Add response existence validation
5. Add trace IDs for observability
6. Add metrics/counters
7. Integration tests with Step 6

### Week 3: QA & Documentation
8. End-to-end testing (Steps 1–6)
9. Review with AMC team (data flow)
10. Review with Eval Layer team (contract)

---

## Conclusion

The `human-feedback-loop` module is a **well-designed, focused component** that correctly implements Steps 1–4 of the feedback pipeline. It has the right architecture, proper abstractions, and good test coverage.

**To achieve production readiness:**
- ✅ Implement Step 6 (repair analysis) — **unblocks Eval Layer invocation**
- ✅ Extend EvidencePack model — **provides full context to Eval Layer**
- ✅ Document Eval Layer contract — **clarifies data flow**
- ⚠️ Add observability — **enables production monitoring**

**Estimated effort: 2–3 weeks** of focused development.

---

**Revised Status:** ✅ **Ready for production with 14–20 hours of targeted work**

(Previous estimate of 26–32h was based on misunderstanding of architectural responsibilities.)
