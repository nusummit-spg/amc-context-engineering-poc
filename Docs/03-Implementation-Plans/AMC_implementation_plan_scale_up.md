# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC Context Engineering: 50-Document Scale-Up & System Architecture Improvement Plan

> **Scope**: Extend from 14 selected documents → 50 strategically chosen documents.  
> **Goals**: Improve accuracy, token efficiency, latency, embedding quality, and knowledge graph fidelity.  
> **Constraint**: Plan only — no execution.

---

## Executive Assessment: What We Have vs. What We Need

### Current State Diagnosis

| Dimension | Current State | Root Cause | Impact |
|---|---|---|---|
| **Document Coverage** | 14 docs in `selected_source_documents` | Manual, ad hoc selection | Gaps in regulatory coverage; ESG, AML, ESG/BRSR, MF fund docs missing |
| **Embedding Model** | `all-MiniLM-L6-v2` (384-dim, CPU) | Default choice, local-only | Low-dimensional; poor cross-lingual recall on Hindi regulatory text |
| **Chunking Strategy** | Fixed-size sentence-boundary: Parent=1200 chars, Child=250 chars | Naive size-based splits | Tables, numbered clauses, and annexures are severed mid-structure |
| **Double Embedding Bug** | `_embed_texts([query])` called twice per query (lines 59 + 78 in `taxonomy_retrieval.py`) | Not caught in review | ~180ms wasted CPU per query |
| **Unpooled Graph Driver** | `GraphDatabase.driver()` created fresh per `retrieve_graph()` call | No singleton pattern | ~120ms TCP handshake overhead per query |
| **Vector Search** | `IndexFlatIP` (exact brute-force) | Default FAISS index | O(n) scan; will become slow at 50-doc scale |
| **Graph NER — Layer B** | GLiNER bypassed for short queries (`len < 300`) | Performance shortcut | Short but complex regulatory queries miss entity extraction |
| **Context Assembly** | Raw JSON / verbose text passed to LLM | No compression | 450+ tokens per graph context block; 2000+ total input tokens |
| **No RRF Fusion** | Vector and graph results passed independently as separate sections | Not implemented | LLM must mentally reconcile two unranked blocks; degrades precision |
| **No Similarity Floor** | Top-K=3 retrieved unconditionally | No threshold | Noisy, low-similarity chunks injected into every prompt |
| **No Semantic Cache** | Every query hits full retrieval + LLM | Not implemented | Identical/similar questions re-billed at full cost |
| **Graph Ontology Scope** | Only taxonomy (SchemeClass, MutualExclusion, Regime) | Limited initial design | Cannot answer ESG, AML, AIF, Portfolio Risk, Fund Performance questions |
| **Document Selection** | Only regulatory circulars + 1 ESG doc | Manual curation | Missing: Adani financial docs, fund performance, AIF master circular |
| **No Provenance Tracking** | Answers not traceable to source page + doc | Not implemented | Cannot cite sources; compliance risk |

---

## 🔍 Missing Concepts Not Covered in Production Roadmap

After deep evaluation, the following **critical architectural gaps** are absent from all 8 roadmap documents:

### Gap 1: Document-Level Routing Intelligence (Query → Document Namespace)
The system currently treats all 14 docs as a flat pool. With 50 documents from 4 distinct categories (SEBI Circulars, Master Circulars, Adani Corporate, ESG/Sustainability), there is **no routing logic** to direct a query to the right namespace before retrieval. A question about "ESG greenwashing in Adani's H1FY25 report" should not search through SEBI circular embeddings.

**Missing**: A lightweight query classifier that maps queries to document namespaces (taxonomies) before retrieval begins.

### Gap 2: Hierarchical Document Structure Preservation
The current chunking completely ignores document hierarchy:
- SEBI circulars have numbered clause trees: `2.6.3.16 > 2.6.3 > 2.6 > Section 2`
- Annual reports have section trees: `Directors' Report > ESG > Climate Adaptation > Water`
- These structural relationships define regulatory applicability (child clause overrides parent)

**Missing**: A `DocumentNode` → `SectionNode` → `ClauseNode` hierarchy in the knowledge graph, enabling path-based traversal for compliance queries.

### Gap 3: Cross-Document Entity Linking (Same Entity, Different Docs)
The NER pipeline creates isolated entity nodes per document. "Adani Enterprises Ltd" in `AEL_AR_FY24.pdf` and in `Adani_Portfolio_H1FY25_ESG.pdf` become separate, unlinked graph nodes.

**Missing**: Post-ingestion entity resolution pass that merges canonical entity mentions across documents using embeddings + exact string matching.

### Gap 4: Temporal Graph Edges (Time-Aware Regulatory State)
The roadmap mentions "Graphiti temporal edges" but the current implementation has no time-aware graph edges. Queries like *"What was the mutual fund categorization rule in March 2024?"* return the current state, not the historical state.

**Missing**: `valid_from` / `valid_to` properties on all regulatory fact edges; query-time temporal filtering in Cypher.

### Gap 5: Document Freshness & Staleness Signals
With 50 documents spanning FY07 to FY26 (for Adani) and 2017–2025 SEBI circulars, the system has no mechanism to signal which information is superseded.

**Missing**: `superseded_by` edges between documents/nodes + UI freshness badges on retrieved content.

### Gap 6: Table-Aware Extraction & Table-as-Entity
The `_extract_tables()` function extracts tables as markdown, but the knowledge graph has no `TableFact` node type. Critical numeric data (AUM thresholds, investment limits, penalty schedules) is lost in the vector pool.

**Missing**: Table cells with numeric financial data → `FinancialFact` nodes in Neo4j with properties like `metric`, `value`, `unit`, `document`, `page_num`.

### Gap 7: Multi-Vector Indexing (Separate Indexes by Doc Type)
Currently all documents share a single `amc_master` FAISS index. This means ESG report embeddings compete with SEBI circular embeddings in the same similarity space.

**Missing**: Separate sub-indexes per document category, with a meta-router that decides which index(es) to query.

### Gap 8: Answer Provenance & Citation Chain
Answers are not linked back to specific page numbers and documents. For compliance use cases, every answer must be defensible with exact citations.

**Missing**: A `provenance` array in every response: `[{"doc": "...", "page": N, "clause": "2.6.3.16", "text_snippet": "..."}]`.

### Gap 9: Retrieval Quality Continuous Evaluation (per Query)
There is no per-query evaluation feedback loop. A bad answer is returned to the user with no mechanism to flag it, log it, or use it to improve the system.

**Missing**: Lightweight RAGAS-style inline faithfulness scoring on every production response, stored to a log for monitoring.

### Gap 10: Incremental Graph Update (Without Full Rebuild)
The `build_index.py` supports `--rebuild` but the graph store has no incremental document addition. Adding document #51 requires reasoning about whether to rebuild all NER-derived entity links.

**Missing**: A document-scoped graph merge strategy where adding a new doc only writes new/updated nodes without touching existing nodes from other docs.

---

## 📚 Document Selection Strategy: 14 → 50

### Current 14 Documents (selected_source_documents)
- AEL_AR_FY24.pdf, AEL_Annual_Return_FY_2024.pdf, AEL_Earnings_Call_Q1_FY19.pdf, AEL_Earnings_Call_Q4_FY24.pdf
- Adani_Portfolio_H1FY25_ESG.pdf
- April 2024.pdf, April 2025.pdf, May 2024.pdf (AMFI monthly reports)
- Borrowing by Mutual Funds.pdf
- Categorization and Rationalization of Mutual Fund Schemes.pdf
- Disclosure of Risk adjusted Return - Information Ratio (IR) for Mutual Fund Schemes.pdf
- Guidelines for Investment Advisers.pdf
- Safer participation of retail investors in Algorithmic trading.pdf
- mutual_fund_data.csv

### Proposed 50-Document Target Set (36 additions)

#### Tier 1: SEBI Master Circulars (Core Regulatory Foundation) — Add 8
Priority: These are the ground truth for all compliance answers.
1. `Master Circular for Mutual Funds.pdf` ← Most critical; 7.1 MB of complete MF regulation
2. `Master Circular for Investment Advisers.pdf` ← IA guidelines backbone
3. `Master Circular for Portfolio Managers.pdf` ← PM compliance
4. `Master Circular for Alternative Investment Funds (AIFs).pdf` ← AIF coverage
5. `Master Circular for ESG Rating Providers (ERPs).pdf` ← ESG regulation anchor
6. `Master Circular for Stock Brokers.pdf` ← Algo trading context
7. `Guidelines on Anti-Money Laundering (AML) Standards.pdf` ← AML/PMLA graph
8. `Master Circular for Research Analysts.pdf` ← RA regulatory baseline

#### Tier 2: High-Value SEBI Circulars (Targeted Coverage) — Add 10
9. `Categorization and Rationalization of Mutual Fund Schemes.pdf` ← Already indexed; confirm
10. `Regulatory framework for Specialized Investment Funds.pdf` ← SIF (new 2024 category)
11. `Framework for Environment, Social and Governance (ESG) Debt Securities.pdf` ← ESG debt
12. `Reclassification of Real Estate Investment Trusts (REITs) as equity.pdf`
13. `Timelines for rebalancing of portfolios of mutual fund schemes.pdf`
14. `Valuation of physical Gold and Silver held by mutual fund schemes.pdf`
15. `Timelines for deployment of funds collected by AMCs in NFO.pdf`
16. `Introduction of Voluntary Lock-in - Debit freeze facility to Mutual Fund folios.pdf`
17. `Clarification on Regulatory framework for Specialized Investment Funds.pdf`
18. `Transaction charges paid to Mutual Fund Distributors.pdf`

#### Tier 3: Adani Corporate Intelligence — Add 10
19. `Adani_Portfolio_H1FY25_ESG.pdf` ← Already indexed
20. `Adani_Portfolio_H1FY25_Credit_Summary.pdf` ← Credit analysis companion
21. `Adani_Portfolio_H1FY25_Results_Compendium.pdf` ← Financial results
22. `Adani_Portfolio_Equity_Note_H1_FY25.pdf` ← Equity analysis
23. `AEL_AR_FY25.pdf` ← Latest full annual report (FY25)
24. `AEL_AR_FY23.pdf` ← 3-year trend (FY23)
25. `AEL_Earnings_Call_Q4_FY25.pdf` ← Latest earnings call
26. `AEL_Earnings_Call_Q1_FY26.pdf` ← Newest available
27. `AEL_Investors_Presentation.pdf` ← Investor deck overview
28. `ESG_Deck_June_25.pdf` ← Latest ESG positioning

#### Tier 4: AMC Fund House Documents — Add 8
29-36: Select 1 representative document per fund house from the 11 available in `Docs/AMC Docs/AMC/MF/`:
   - HDFC Mutual Fund, SBI Mutual Fund, Axis, Tata, Groww, 360 ONE, Bajaj Finserv, Zerodha
   - Prefer: Latest SID (Scheme Information Document) or Annual Report for each

**Total: ~50 documents across 4 tiers**

> [!IMPORTANT]
> **Critical Exclusions**: Avoid adding bulk Adani historical financial statements (FY07–FY22) — they add volume without answering current compliance/ESG questions and bloat the vector index with outdated financial data.

---

## 🔧 System Architecture Improvements

### Module 1: Ingestion Pipeline Upgrades

#### 1.1 — Structural Chunking Strategy (Replaces Fixed-Size)
**Current Problem**: `build_parent_child_chunks()` uses fixed character sizes (Parent=1200, Child=250). SEBI clause `2.6.3.16` gets split mid-sentence.

**New Strategy — Hierarchical Clause-Aware Chunking**:
```
Step 1: Detect document type (Master Circular / Annual Report / ESG / Fund House)
Step 2: Apply type-specific chunking:
  - SEBI Circulars: Split on numbered clause headers (regex: r"^\d+\.\d+(\.\d+)*\s")
  - Annual Reports: Split on section headings (H1/H2 detected via font size from PyMuPDF)
  - ESG Reports: Split on metric blocks and framework sections
  - Tables: Each logical table = one parent chunk; rows = child chunks
Step 3: Preserve clause/section hierarchy metadata in every chunk:
  chunk["clause_path"] = "2.6.3.16"
  chunk["section"] = "Categorization of Equity Schemes"
  chunk["doc_type"] = "sebi_circular"
```

**Implementation**:
- New function: `build_structural_chunks(pages_data, doc_type)` in `faiss_store.py`
- Document type classifier: Simple rule-based on filename patterns (`Master Circular`, `AR_FY`, `ESG`, `Circular`)
- Fallback to existing sentence-boundary chunking for unrecognized types

#### 1.2 — Embedding Model Upgrade
**Current**: `all-MiniLM-L6-v2` (384-dim, 22M params, English-optimized)  
**Proposed**: `BAAI/bge-small-en-v1.5` (384-dim, same dim, but significantly better retrieval quality on finance/legal text) OR `all-mpnet-base-v2` (768-dim, 110M params, higher quality)

**Trade-off Analysis**:

| Model | Dim | Size | Retrieval Quality (BEIR) | Load Time | FAISS Compat |
|---|---|---|---|---|---|
| `all-MiniLM-L6-v2` (current) | 384 | 22MB | ~58.9 | ~1s | ✅ IndexFlatIP |
| `BAAI/bge-small-en-v1.5` | 384 | 24MB | ~62.7 | ~1s | ✅ IndexFlatIP (same dim) |
| `all-mpnet-base-v2` | 768 | 420MB | ~69.6 | ~3s | Requires FAISS rebuild |

**Recommendation**: Start with `BAAI/bge-small-en-v1.5` — same 384-dim (no FAISS rebuild), significantly better quality, same load time. It explicitly optimizes for retrieval with query-document asymmetric embedding.

> [!WARNING]
> Changing embedding model requires **full FAISS index rebuild** (`--rebuild` flag). The graph remains intact since it doesn't store embeddings directly.

#### 1.3 — Smart FAISS Index Type (IndexIVFFlat vs IndexFlatIP)
**Current**: `IndexFlatIP` — exact brute-force search, O(n) per query.  
**At 50 docs**: Estimated ~150K–250K child chunks. IndexFlatIP at 250K × 384-dim = ~370MB memory; ~40–80ms search time.  
**Proposed**: Upgrade to `IndexIVFFlat` (Inverted File Index) when total vectors exceed 50K:
```python
# Approximate, fast, memory-efficient
nlist = 100  # 100 Voronoi cells
quantizer = faiss.IndexFlatIP(dim)
index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
index.train(all_vectors)   # one-time training pass
# Search: nprobe=10 (scan 10 of 100 cells) → ~10x speedup vs exact
index.nprobe = 10
```
**Impact**: ~8–12x search speedup at 50-doc scale; memory unchanged.

#### 1.4 — Per-Page Extraction Cache (Already Exists, Needs Scope Extension)
The `EXTRACTION_CACHE_DIR` is implemented but keys on `file_hash`. Extend to also cache:
- Structural metadata per page (tables detected, headers found, clause numbers)
- Document type classification result
This avoids re-classifying documents on incremental runs.

---

### Module 2: Query Pipeline Upgrades

#### 2.1 — Fix: Single-Pass Embedding (Eliminates Double Embedding)
**Location**: `taxonomy_retrieval.py`, lines 59 + 78  
**Problem**: `fs._embed_texts([query])` called once in `retrieve_vector()` and once in `retrieve_graph()`.  
**Fix**:
```python
def hybrid_graphrag_v2(query: str, history=None):
    # Embed ONCE, reuse everywhere
    query_vector_np = fs._embed_texts([query])   # shape: (1, 384)
    query_vector_list = query_vector_np[0].tolist()
    
    # Pass pre-computed vector to both retrievers
    graph_ctx = retrieve_graph_with_vector(query, query_vector_list)
    hyb_chunks = retrieve_vector_with_embedding(query_vector_np, index, chunks, top_k=3)
```
**Estimated Savings**: ~180ms CPU per query.

#### 2.2 — Fix: Graph Driver Connection Pool (Singleton)
**Location**: `taxonomy_retrieval.py`, lines 72–76  
**Problem**: `GraphDatabase.driver()` instantiated per `retrieve_graph()` call.  
**Fix**:
```python
_graph_driver = None  # module-level singleton

def _get_graph_driver():
    global _graph_driver
    if _graph_driver is None:
        _graph_driver = GraphDatabase.driver(
            TAXONOMY_NEO4J_URI,
            auth=(TAXONOMY_NEO4J_USER, TAXONOMY_NEO4J_PASSWORD),
            max_connection_lifetime=300,
            connection_timeout=3,
        )
    return _graph_driver
```
**Estimated Savings**: ~120ms per query.

#### 2.3 — Reciprocal Rank Fusion (RRF) with Similarity Floor
**Current**: Graph and vector results assembled separately as two blocks in the prompt.  
**New**: Merge both retrieval lists into a single ranked list before prompt assembly.

```python
def rrf_merge(graph_facts: list, vector_chunks: list,
              w_graph: float = 0.75, w_vec: float = 0.25, k: int = 60) -> list:
    """
    RRF Score(d) = w_graph/(k + rank_graph(d)) + w_vec/(k + rank_vec(d))
    Drops vector chunks with cosine similarity < SIMILARITY_FLOOR
    """
    SIMILARITY_FLOOR = 0.65
    merged = {}
    
    for rank, fact in enumerate(graph_facts):
        key = fact.get("code") or fact.get("desc", "")[:30]
        merged[key] = merged.get(key, 0) + w_graph / (k + rank + 1)
    
    for rank, chunk in enumerate(vector_chunks):
        if chunk.get("score", 1.0) < SIMILARITY_FLOOR:
            continue  # Drop low-quality vector hits
        key = chunk["text"][:50]
        merged[key] = merged.get(key, 0) + w_vec / (k + rank + 1)
    
    return sorted(merged.items(), key=lambda x: x[1], reverse=True)
```

**Adaptive Weights by Query Type**:
- Temporal/Comparative queries: `w_graph=0.85, w_vec=0.15`
- Fact lookup queries: `w_graph=0.30, w_vec=0.70`
- ESG/Sustainability: `w_graph=0.50, w_vec=0.50`

#### 2.4 — Graph Context Micro-Notation (Token Compression)
**Current `_graph_context_to_text()` output** (verbose, ~450 tokens):
```
SchemeClass [CURRENT_2026] 'Index Fund': Open-ended scheme tracking a specific index.
MutualExclusion [CURRENT_2026]: 'Index Fund' cannot coexist with 'Large Cap Equity Scheme' in the same AMC.
Regime: CURRENT_2026 (active) — SEBI Mutual Fund Categorisation | Effective: 2026-02-26
```

**Proposed Micro-Notation** (~140 tokens, -68.8%):
```
[2026] SC:IndexFund(open,track_idx)
[2026] ME: IndexFund ≠ LargeCapEquity (same_amc)
[REG] CURRENT_2026(active, eff:2026-02-26)
```
**Implementation**: Rewrite `_graph_context_to_text()` with compact formatters per node type. Keep verbose mode as a `debug=True` option.

#### 2.5 — Cosine Similarity Floor for Vector Retrieval
**Current**: `retrieve_vector()` returns top-3 regardless of distance.  
**Fix**: After `index.search()`, check the distance scores (D values) and drop any hit below threshold:
```python
def retrieve_vector_with_floor(query_vec, index, chunks, top_k=5, floor=0.65):
    D, I = index.search(query_vec, top_k)
    results = []
    for score, idx in zip(D[0], I[0]):
        if score < floor or idx >= len(chunks):
            continue
        chunk = chunks[idx].copy()
        chunk["score"] = float(score)
        results.append(chunk)
    return results
```
**Impact**: Saves ~450 tokens when vector context is irrelevant; prevents hallucination from off-topic chunks.

#### 2.6 — Query Namespace Router
**New Component**: Lightweight classifier that routes the query to the correct document namespace before retrieval.
```python
NAMESPACE_KEYWORDS = {
    "sebi_regulation": ["sebi", "circular", "categorization", "regulation", "compliance", 
                        "mutual fund rules", "2026", "2017", "master circular"],
    "adani_corporate": ["adani", "ael", "aahl", "ebitda", "revenue", "pat", "fy25", "fy24"],
    "esg_sustainability": ["esg", "brsr", "climate", "carbon", "greenwashing", "sustainability",
                           "emissions", "green"],
    "fund_performance": ["nav", "returns", "aum", "benchmark", "alpha", "sharpe ratio",
                         "fund performance", "scheme performance"],
}

def route_query_namespace(query: str) -> list[str]:
    """Returns list of relevant namespaces (can be multiple for cross-domain queries)"""
    query_lower = query.lower()
    active = []
    for ns, keywords in NAMESPACE_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            active.append(ns)
    return active if active else ["all"]  # fallback: search everything
```

---

### Module 3: Knowledge Graph Schema Expansion

#### 3.1 — New Node Types Required

```cypher
// Document-level hierarchy nodes
(:Document {id, title, doc_type, source_path, effective_date, status})
(:Section {id, title, section_num, doc_id})
(:Clause {id, clause_num, clause_path, text_summary, doc_id, section_id})
(:TableFact {id, metric, value, unit, doc_id, page_num, row_context})

// Financial intelligence nodes
(:FinancialMetric {metric_name, value, unit, period, doc_id, entity_name})
(:AUMRecord {fund_house, scheme_name, aum_crore, period, doc_id})

// ESG-specific nodes  
(:ESGMetric {category, metric_name, value, unit, period, doc_id})
(:CarbonEmission {scope, value, unit, year, entity, doc_id})
(:GovernanceItem {topic, status, doc_id, page_num})

// AML/Compliance nodes
(:ComplianceRule {rule_id, rule_text, regulator, effective_date, doc_id})
(:Penalty {violation_type, penalty_amount, applicable_to, doc_id})
```

#### 3.2 — New Relationship Types

```cypher
// Temporal regulatory chain
(c1:RegulatoryCircular)-[:SUPERSEDES {effective_date}]->(c2:RegulatoryCircular)
(clause:Clause)-[:AMENDS {change_type}]->(prev_clause:Clause)
(clause:Clause)-[:VALID_FROM {date}]->(regime:RegulatoryRegime)

// Cross-document entity links
(e1:Entity)-[:SAME_AS {confidence}]->(e2:Entity)  // Cross-doc entity resolution

// Document structure
(doc:Document)-[:HAS_SECTION]->(sec:Section)-[:HAS_CLAUSE]->(clause:Clause)
(clause:Clause)-[:CITES]->(other_clause:Clause)  // Cross-reference links

// Financial intelligence
(entity:Entity)-[:HAS_METRIC]->(metric:FinancialMetric)
(fund:Entity)-[:REPORTS_AUM]->(aum:AUMRecord)
(entity:Entity)-[:DISCLOSES_ESG]->(metric:ESGMetric)
```

#### 3.3 — Vector Index Expansion
Beyond the current `tax_scheme_vector` and `tax_change_vector`, add:
```cypher
CREATE VECTOR INDEX clause_vector FOR (c:Clause) ON c.embedding OPTIONS {indexConfig: {`vector.dimensions`: 384}}
CREATE VECTOR INDEX doc_summary_vector FOR (d:Document) ON d.embedding OPTIONS {indexConfig: {`vector.dimensions`: 384}}
CREATE VECTOR INDEX esg_metric_vector FOR (e:ESGMetric) ON e.embedding OPTIONS {indexConfig: {`vector.dimensions`: 384}}
```

---

### Module 4: NER Pipeline Upgrades

#### 4.1 — Expanded GLINER Labels for New Document Types
Current labels are MF-centric. Add:
```python
GLINER_LABELS = [
    # Existing
    "mutual fund scheme name", "fund house", "benchmark index",
    "fund manager", "asset class", "sector",
    # New — ESG/Corporate
    "ESG metric", "carbon emission value", "sustainability target",
    "BRSR indicator", "greenwashing claim",
    # New — Financial Intelligence
    "revenue figure", "EBITDA value", "AUM value", "PAT value",
    "market capitalization", "debt amount",
    # New — Regulatory
    "SEBI circular reference", "regulatory deadline", "penalty amount",
    "compliance requirement", "investment limit percentage",
]
```

#### 4.2 — Table-to-FinancialFact Extractor
New Layer D (post-NER): Dedicated table processor that converts detected table markdown into structured `FinancialFact` nodes:
```python
def extract_financial_facts_from_table(table_md: str, doc_id: str, page_num: int) -> list[dict]:
    """
    Detect patterns like:
    | Metric | FY24 | FY25 | YoY |
    | Revenue | ₹2,300 Cr | ₹2,890 Cr | +25.6% |
    
    → FinancialFact nodes: {metric: "Revenue", value: 2890, unit: "Cr", period: "FY25", ...}
    """
```

#### 4.3 — Entity Resolution Pass (Post-Ingestion)
After all documents are indexed, run a global entity resolution pass:
```python
def resolve_cross_document_entities():
    """
    1. Get all UNRESOLVED Entity nodes
    2. Embed their text
    3. Cluster using cosine similarity > 0.90
    4. Create SAME_AS edges between canonical variants
    5. Elect canonical entity per cluster (most mentioned)
    """
```

---

### Module 5: Provenance & Citation System

#### 5.1 — Chunk-Level Provenance Metadata
Every child chunk must carry:
```python
{
    "child_id": "C00123",
    "parent_id": "P00045",
    "source": "Master Circular for Mutual Funds.pdf",
    "page_num": 47,
    "clause_path": "2.6.3.16",
    "section": "Categorization - Equity Schemes",
    "doc_type": "sebi_master_circular",
    "effective_date": "2026-02-26",
    "score": 0.823  # cosine similarity at retrieval time
}
```

#### 5.2 — Response Provenance Object
Every API/LLM response must include:
```json
{
  "answer": "...",
  "provenance": [
    {
      "doc": "Master Circular for Mutual Funds.pdf",
      "page": 47,
      "clause": "2.6.3.16",
      "snippet": "An AMC shall not operate more than one scheme...",
      "score": 0.87,
      "effective_date": "2026-02-26"
    }
  ],
  "confidence": "high",
  "graph_facts_used": 4,
  "vector_chunks_used": 2
}
```

---

### Module 6: Semantic Cache Layer

#### 6.1 — In-Memory Semantic Cache
Implement a lightweight semantic cache using FAISS in-memory for the **query embedding**, not the query string:
```python
class SemanticQueryCache:
    """
    Cache lookup: embed query → find nearest cached query (cosine sim > 0.96)
    → return cached answer without hitting Neo4j/LLM
    Expected latency: < 30ms vs. 2000-10000ms full pipeline
    """
    def __init__(self, max_entries=200, sim_threshold=0.96):
        self.index = faiss.IndexFlatIP(384)
        self.answers = []
        self.threshold = sim_threshold
    
    def lookup(self, query_vec: np.ndarray) -> dict | None:
        if self.index.ntotal == 0:
            return None
        D, I = self.index.search(query_vec, 1)
        if D[0][0] >= self.threshold:
            return self.answers[I[0][0]]
        return None
    
    def store(self, query_vec: np.ndarray, answer: dict):
        self.index.add(query_vec)
        self.answers.append(answer)
```

**Expected Cache Hit Rate**: 20–30% on a production compliance Q&A system (users re-ask similar questions about common regulatory topics).

---

## 📋 Implementation Phases

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                        50-Document Scale-Up Roadmap                                │
├────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 0: Quick Wins — Code Fixes (Day 1-2)                                         │
│   ├── [P0] Fix double embedding bug (taxonomy_retrieval.py lines 59+78)             │
│   ├── [P0] Fix graph driver singleton (eliminate TCP handshake per query)           │
│   ├── [P0] Add cosine similarity floor (0.65) to vector retrieval                  │
│   └── [P0] Add RRF merger for graph + vector results                               │
│                                                                                    │
│ PHASE 1: Embedding & Index Upgrade (Day 3-5)                                       │
│   ├── [P1] Upgrade embedding model: all-MiniLM → BAAI/bge-small-en-v1.5           │
│   ├── [P1] Switch FAISS index type: IndexFlatIP → IndexIVFFlat (at 50K+ vectors)  │
│   ├── [P1] Implement context micro-notation in _graph_context_to_text()            │
│   └── [P1] Add semantic query cache (SemanticQueryCache class)                     │
│                                                                                    │
│ PHASE 2: Document Selection & Structural Chunking (Day 6-10)                       │
│   ├── [P2] Select 36 additional documents from the 4 tiers defined above           │
│   ├── [P2] Implement doc-type classifier (filename pattern matching)               │
│   ├── [P2] Implement structural/clause-aware chunking strategy                     │
│   ├── [P2] Add clause_path, section, doc_type metadata to all chunks              │
│   └── [P2] Run build_index.py on full 50-document set (--rebuild)                 │
│                                                                                    │
│ PHASE 3: Graph Schema & NER Expansion (Day 11-15)                                  │
│   ├── [P3] Extend graph schema: Document, Section, Clause, TableFact nodes         │
│   ├── [P3] Expand GLiNER labels (ESG, financial metrics, regulatory)               │
│   ├── [P3] Implement Table-to-FinancialFact extractor (Layer D NER)               │
│   ├── [P3] Add temporal validity edges (valid_from / valid_to)                     │
│   └── [P3] Run cross-document entity resolution pass                              │
│                                                                                    │
│ PHASE 4: Query Routing & Provenance (Day 16-20)                                    │
│   ├── [P4] Implement query namespace router                                        │
│   ├── [P4] Add provenance metadata to every response                              │
│   ├── [P4] Build per-namespace FAISS sub-indexes                                  │
│   └── [P4] Extend Streamlit UI with citation/provenance panel                     │
│                                                                                    │
│ PHASE 5: Evaluation & Monitoring (Day 21-25)                                       │
│   ├── [P5] Integrate RAGAS faithfulness scorer (inline, per response)             │
│   ├── [P5] Build evaluation dataset: 25 ground-truth Q&A pairs                    │
│   ├── [P5] Add latency + token telemetry to logs                                  │
│   └── [P5] A/B compare: old 14-doc system vs. new 50-doc system                  │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📈 Expected Impact Matrix

| Metric | Current Baseline | After Phase 0-1 | After Phase 2-3 | After Phase 4-5 |
|---|---|---|---|---|
| **Query Latency (p95)** | ~9.9s (Haiku) | ~9.5s | ~8.0s | ~4.0s (with cache) |
| **Input Tokens per Query** | ~2,000+ | ~1,200 (-40%) | ~900 (-55%) | ~700 (-65%) |
| **Answer Accuracy (on ESG queries)** | Poor (doc not in index) | Moderate | Good | High |
| **Graph Coverage (node types)** | 5 types | 5 types | 11 types | 11 types + provenance |
| **Document Coverage** | 14 docs | 14 docs | 50 docs | 50 docs |
| **Cache Hit Rate** | 0% | 0% | 5% | 20-30% |
| **Hallucination Risk** | Medium | Medium-Low | Low | Very Low (with floor) |

---

## 🚨 Critical Risks & Mitigations

> [!CAUTION]
> **Risk 1: FAISS Index Rebuild Required on Model Change**
> Changing from `all-MiniLM-L6-v2` to `bge-small-en-v1.5` requires a full rebuild of all FAISS indexes. Estimated rebuild time at 50 docs: 2–4 hours (including Claude vision extraction for image-heavy pages).
> **Mitigation**: Run rebuild during off-hours; keep old index as backup until new one is validated.

> [!CAUTION]
> **Risk 2: Neo4j Schema Migration**
> Adding new node types and constraints to Neo4j requires careful migration since we cannot `DROP` constraints without losing existing data.
> **Mitigation**: Use `CREATE CONSTRAINT IF NOT EXISTS` for all new schema elements; new nodes coexist with old ones without conflict.

> [!WARNING]
> **Risk 3: Large PDF Ingestion (Master Circular for Mutual Funds = 7.1MB)**
> The Master Circular for Mutual Funds is 7.1 MB (~400+ pages). At current Claude vision escalation rates, this could generate 400+ API calls.
> **Mitigation**: Enable `SMART_EXTRACTION=true` (already the default); most prose pages won't escalate. Set `LOCAL_TEXT_SUFFICIENCY_THRESHOLD=600` (stricter) for regulatory docs.

> [!WARNING]
> **Risk 4: GLiNER Memory Pressure at 50 Docs**
> GLiNER (`urchade/gliner_medium-v2.1`) loads ~400MB into CPU RAM. Running it on 50 documents' worth of chunks could OOM on machines with <8GB RAM.
> **Mitigation**: Process in document-level batches; explicitly call `gc.collect()` between batches; consider `gliner_small` for very large docs.

> [!NOTE]
> **Note on AUM/Financial Data CSV**
> The `mutual_fund_data.csv` (4.7MB) is already in the index. It provides rich tabular data but uses fixed-width rows that get corrupted by naive CSV chunking. The Table-to-FinancialFact extractor (Phase 3) will retroactively improve how this data is represented in the graph.

---

## User Review Decisions (RESOLVED)

1. **Embedding Model**: **UPGRADED** → Selected `BAAI/bge-small-en-v1.5` (384-dim, fastembed). Provides superior legal/regulatory precision.
2. **Document Tier Priority**: **COMBINATION OF BOTH** → Include both Tier 3 (10 Adani Corporate docs) and Tier 4 (8 AMC Fund House SIDs) alongside Tier 1 & 2 SEBI Regulatory baseline.
3. **Structural Chunking Scope**: **COMBINE BOTH** → Apply Clause-Aware / Structural Chunking to SEBI Circulars and Annual Reports; fallback to sentence-boundary parent-child splits for generic documents.
4. **GraphDB Port**: **DECIDED BEST → UNIFIED INSTANCE (`bolt://localhost:7687`)** → Single Neo4j instance with label-based namespaces (`:TaxonomyNode`, `:SchemeClass`, `:Entity`, `:Issuer`). Retain env override `TAXONOMY_NEO4J_URI`.
5. **Fund House Documents**: **DECIDED BEST → SCHEME INFORMATION DOCUMENTS (SIDs & KIMs)** → Select 8 representative SIDs from HDFC, SBI, Axis, Tata, Groww, 360 ONE, Bajaj Finserv, Zerodha to support scheme comparison queries.
