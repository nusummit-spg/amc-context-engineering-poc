# Wave 1.8 Source Baseline

**Date:** 6 November 2026  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Branch:** `amc-dev`  
**Pinned baseline SHA:** `763c1ec9e57517d97d6880ea79ff9c2ce5c42d36`  
**Previous Wave 1.7 SHA:** `bea1fbd4e52fdc93fa064c47ed1377347d3852f7`  
**Observed delta:** 1 commit ahead

## Wave 1.7 Completed
- A01-A10: CI workflow fixes, governance endpoints normalized
- B01-B02: Durable effects schema migrations 010_b07, 011_b08

## Wave 1.8 Critical Findings

| ID | Severity | Issue | Root Cause |
|----|----------|-------|------------|
| W18-01 | P0 | Fake verified activation | promote_patch_direct returns {"verified":True} without real effects |
| W18-02 | P0 | Broken internal graph lookup | _execute_graph_mutation_with_verification uses get_patch() |
| W18-03 | P0 | FAISS deletion inconsistent | delete_by_chunk_id doesn't remove from self._index |
| W18-04 | P0 | Preimage not exact | _capture_preimage uses similarity_search, not exact ID |
| W18-05 | P0 | Dual execution paths | PromotionService writes outbox AND invokes graph mutation |
| W18-06 | P0 | Process-memory staging | _staging/_preimages dictionaries not durable |
| W18-07 | P0 | Insufficient CAS | String fencing_token, no lease protocol, no uniqueness |
| W18-08 | P0 | Graph effects require proof | _update_node_or_edge reports success without readback |
| W18-09 | P0 | Governance serving auth | Still uses patch.approved, not ACTIVE + verified receipt |
| W18-10 | P0 | Assurance doesn't fail closed | Missing test dirs = skip, || exit 0 masks failures |

## Implemented Fixes (Wave 1.8 R0-01, R0-02)

| Task | Action | Status |
|------|--------|--------|
| R0-01 | Gitleaks action version | FIXED - v3 (was v8.22.0 which doesn't exist) |
| R0-02 | Test job failure detection | FIXED - Removed || exit 0, exit 1 on missing dirs |

## Pending Tasks (Wave 1.8)

### R0 Batch (R0-03 to R0-07)
- R0-03: Disable synthetic patch activation
- R0-04: Seal every answer path with is_serving_eligible
- R0-05: Stop dual execution (PromotionService)
- R0-06: Fix VectorStore deletion consistency
- R0-07: Evidence reconciliation

### D1 Batch (D1-01 to D1-07)
- D1-01: Migration history + constraints
- D1-02: Durable publication repository
- D1-03: Idempotent request envelope
- D1-04: Fenced worker claims
- D1-05: Durable preimage semantics
- D1-06: Immutable generation storage
- D1-07: Durable active pointer

### D2 Batch (D2-01 to D2-08)
- D2-01: Exact vector lookup
- D2-02: Generation builder
- D2-03: Vector verification and switch
- D2-04: Parameterized Neo4j graph write
- D2-05: Graph postcondition
- D2-06: One authoritative orchestration worker
- D2-07: Durable compensation/rollback
- D2-08: Terminal state and evidence

### Q Batch (Q-01 to Q-05)
### A Batch (A-01 to A-05)

## Next Steps
1. Execute R0-03 to R0-07
2. Execute D1-01 to D1-07
3. Execute D2-01 to D2-08
4. Execute Q and A batches
