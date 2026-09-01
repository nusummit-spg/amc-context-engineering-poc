# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

Ran command: `.venv\Scripts\python.exe ..\evaluation\cold_start_test.py`

Running — NER models loading cold. Will auto-notify when done. Watching the log:

Used tool: schedule

All results captured. Here's the complete cold-start analysis:

---

## Cold-Start Query Metrics Report

**Query**: *"Within those categories, what is the minimum equity allocation for a Large Cap Fund and how is Large Cap defined?"*
**Model**: `groq/llama-3.1-8b-instant` | **Cache**: ❌ Cleared | **Neo4j**: ✅ Online

---

### Side-by-Side Comparison

| Metric | Traditional RAG v2 | ContextGraph v2 | Delta |
|--------|:-----------------:|:---------------:|:-----:|
| **Tokens In** | 108 | 548 | -440 |
| **Tokens Out** | 108 | 74 | +34 |
| **Total Tokens** | **216** | **622** | -406 |
| **Wall Latency** | **849.5 ms** | 3,316.9 ms | -2,467 ms |
| **NER Latency** | N/A | 0.0 ms | — |
| **Graph DB (Neo4j)** | N/A | **2,655.5 ms** | — |
| **Vector DB (FAISS)** | N/A | 0.0 ms | — |
| **LLM Generation** | ~700 ms | **241.6 ms** | LLM 3x faster |
| **Graph Nodes** | 0 | **20** | — |
| **Graph Edges** | 0 | **15** | — |
| **Cache Hit** | No | No | — |
| **Docs/Candidates** | 5 chunks | 20 nodes | — |
| **Confidence** | — | High (Dual-Regime Graph + Vector) | — |
| **Answer Quality** | ❌ Refused | ✅ **Correct** (80%, top companies) | — |

---

### Key Findings

**1. Token usage: Graph uses more tokens in cold start (but answers correctly)**
Traditional uses 216 tokens to say *"I can't find it"*. ContextGraph uses 622 tokens to build a richer prompt (`548 in + 74 out`) — preamble + graph triplets + vector chunks — and **gives the correct answer: "minimum equity allocation is 80%"**.

**2. The 3,316ms latency is dominated by Neo4j (2,655ms)**
The actual LLM call was only **241.6ms** — 3x faster than Traditional's ~700ms — because ContextGraph's structured prompt is more focused. Neo4j graph traversal is the bottleneck.

**3. Cache vs Cold-Start comparison (same query)**

| Run | Cache | Total Tokens | Wall Latency | Answer |
|-----|-------|-------------|-------------|--------|
| Previous (cache hit) | ✅ Yes | **12 tokens** | 3,034ms | ✅ Correct |
| **This run (cold)** | ❌ No | **622 tokens** | 3,317ms | ✅ Correct |
| Traditional (both) | N/A | 216 tokens | ~850–962ms | ❌ Refused |

> The cache cuts tokens from 622 → **12 (98% reduction)** with the same latency profile (Neo4j re-traversal still runs in smart mode). On the **next query in this same session**, ContextGraph will serve this answer from cache at 12 tokens — that's the multi-turn advantage.

**4. FlashRank reranker had a download issue**
```
Could not load ranker: 404 Client Error (ms-marco-MiniLM-L-6-v2.zip not found)
```
This means reranking was skipped and chunks were served in raw FAISS score order. Fixing this would improve vector context quality further.

**5. Confidence: "High Confidence (Dual-Regime Graph + Vector)"**
Matched via `vector_similarity (db.index.vector.queryNodes)` — 20 nodes and 15 edges fetched from Neo4j via vector similarity on the query embedding against the graph's node embeddings.
