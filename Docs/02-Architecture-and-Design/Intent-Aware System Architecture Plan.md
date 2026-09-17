# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Intent-Aware System Architecture Plan
### Dual-Gate Semantic Cache + Intent Propagation Across the Full Pipeline

---

## The Core Idea: Two Dimensions of Intent

The current system has **one** intent dimension:

```
query_type = {aggregation, comparison, direct_lookup, open_ended}   ← operational intent
```

What we're proposing adds a **second** dimension:

```
domain_intent = {regulatory, esg_sustainability, financial_performance,
                 fund_comparison, corporate_governance, market_data}  ← domain intent
```

**Together, these two form a 2D intent fingerprint** that gates the cache, routes NER labels, controls graph depth, selects prompt templates, and sets output format — making the entire pipeline intent-aware end to end.

```
Query: "What are key ESG initiatives for climate change adaptation?"
  └─► query_type   = "open_ended"
  └─► domain_intent = "esg_sustainability"
  └─► intent_key   = "open_ended::esg_sustainability"
```

---

## Architecture: Intent-Aware Dual-Gate Cache

### The Cache Data Structure

```python
@dataclass
class CacheEntry:
    query_embedding: np.ndarray     # 384-dim float32, normalized
    query_type: str                 # operational intent: aggregation|comparison|...
    domain_intent: str              # domain intent: esg_sustainability|regulatory|...
    query_canonical: str            # original query (for inspection)
    answer: str                     # the cached answer text
    provenance: list[dict]          # source docs + pages used
    confidence_label: str           # high/medium/low from retrieval
    total_tokens: int               # cost of the original query
    created_at: float               # time.time()
    ttl_seconds: int                # varies by domain_intent (see TTL policy)
    hit_count: int                  # how many times this was served from cache
```

### The Dual-Gate Lookup Logic (90% Threshold)

```
Incoming Query
     │
     ▼
 [A] Embed Query → query_vec (384-dim)         ← ~5ms (already warm)
     │
     ▼
 [B] Classify query_type + domain_intent       ← ~0ms (regex, no LLM)
     │
     ├─► intent_key = f"{query_type}::{domain_intent}"
     │
     ▼
 [C] Filter cache entries by intent_key        ← O(n_same_intent) only
     │                                            (not full cache scan)
     ├─► candidate pool = entries where intent_key MATCHES exactly
     │
     ▼
 [D] Cosine similarity vs. candidate pool
     │
     ├─► max_sim >= 0.90  AND  intent_key matches?
     │       YES → return cached answer (0ms LLM, 0ms retrieval)
     │       NO  → full pipeline → store new CacheEntry
```

**Why dual gate matters**: Two queries can have cosine similarity = 0.88 but different domain_intent:
- "What did Adani report in ESG?" → `open_ended::esg_sustainability`
- "What did Adani report on revenue?" → `open_ended::financial_performance`

These would score ~0.85 similarity — close but semantically different answers. The intent gate prevents the wrong answer from being served.

---

## New File: `intent_cache.py`

**New file**: `streamlit_app/intent_cache.py`

```python
"""
intent_cache.py
================
Dual-gate semantic cache: cosine similarity >= THRESHOLD *and* exact
intent_key match before returning a cached answer.

Cache is in-process (no Redis needed for Streamlit). Eviction is LRU-based.
"""
from __future__ import annotations
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ── Intent taxonomy ───────────────────────────────────────────────────────────
DOMAIN_PATTERNS = {
    "esg_sustainability": [
        "esg", "climate", "sustainability", "carbon", "emission", "brsr",
        "green", "environment", "social", "governance", "net zero",
        "climate change", "renewable", "water", "biodiversity",
    ],
    "regulatory": [
        "sebi", "circular", "regulation", "compliance", "categorization",
        "master circular", "amendment", "guidelines", "framework",
        "aml", "pmla", "kyc", "disclosure", "nfo", "exit load",
    ],
    "financial_performance": [
        "revenue", "ebitda", "pat", "profit", "earnings", "fy24", "fy25",
        "quarterly", "annual", "q1", "q2", "q3", "q4", "growth", "margin",
        "debt", "credit", "balance sheet", "cash flow",
    ],
    "fund_comparison": [
        "nav", "aum", "benchmark", "alpha", "returns", "cagr", "sharpe",
        "fund house", "scheme", "category", "large cap", "mid cap", "small cap",
        "compare fund", "vs fund", "which fund",
    ],
    "corporate_governance": [
        "board", "director", "audit committee", "risk management",
        "dividend", "buyback", "promoter", "shareholding", "adani",
    ],
    "market_data": [
        "price", "market cap", "pe ratio", "index", "nifty", "sensex",
        "52 week", "volume", "amfi", "monthly data",
    ],
}

DOMAIN_INTENT_DEFAULT = "general"

# Cache TTL seconds by domain — regulatory changes rarely, market data often
DOMAIN_TTL = {
    "regulatory":            86400 * 7,   # 7 days — SEBI circulars stable
    "esg_sustainability":    86400 * 3,   # 3 days — reports quarterly
    "financial_performance": 86400 * 1,   # 1 day  — earnings can update
    "fund_comparison":       3600 * 6,    # 6 hours — NAVs change daily
    "corporate_governance":  86400 * 3,   # 3 days  — governance stable
    "market_data":           3600 * 1,    # 1 hour  — prices change constantly
    "general":               86400 * 1,   # 1 day   — default
}

# Confidence threshold for cache hit
CACHE_SIMILARITY_THRESHOLD = 0.90

# Max cache entries per intent_key before LRU eviction
CACHE_MAX_PER_INTENT = 200
CACHE_MAX_TOTAL = 2000


@dataclass
class CacheEntry:
    query_embedding: np.ndarray
    query_type: str
    domain_intent: str
    query_canonical: str
    answer: str
    provenance: list[dict]
    confidence_label: str
    total_tokens: int
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 86400
    hit_count: int = 0
    last_hit_at: float = field(default_factory=time.time)

    @property
    def intent_key(self) -> str:
        return f"{self.query_type}::{self.domain_intent}"

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


class IntentAwareCache:
    """
    In-process semantic cache gated by cosine similarity >= threshold
    AND exact intent_key match.
    """

    def __init__(
        self,
        similarity_threshold: float = CACHE_SIMILARITY_THRESHOLD,
        max_total: int = CACHE_MAX_TOTAL,
    ):
        self.threshold = similarity_threshold
        self.max_total = max_total
        # Partitioned by intent_key for fast filtering
        self._store: dict[str, list[CacheEntry]] = {}
        self._stats = {"hits": 0, "misses": 0, "expirations": 0, "evictions": 0}

    # ── Domain intent classification (zero LLM calls) ─────────────────────
    @staticmethod
    def classify_domain_intent(query: str) -> str:
        q = query.lower()
        scores: dict[str, int] = {}
        for domain, keywords in DOMAIN_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in q)
            if score > 0:
                scores[domain] = score
        if not scores:
            return DOMAIN_INTENT_DEFAULT
        # Return domain with most keyword matches
        return max(scores, key=scores.get)

    # ── Cache lookup ───────────────────────────────────────────────────────
    def lookup(
        self,
        query_vec: np.ndarray,       # shape (1, 384), normalized
        query_type: str,
        domain_intent: str,
    ) -> Optional[CacheEntry]:
        intent_key = f"{query_type}::{domain_intent}"
        candidates = self._store.get(intent_key, [])

        if not candidates:
            self._stats["misses"] += 1
            return None

        # Remove expired entries
        active = [e for e in candidates if not e.is_expired]
        if len(active) != len(candidates):
            self._stats["expirations"] += len(candidates) - len(active)
            self._store[intent_key] = active

        if not active:
            self._stats["misses"] += 1
            return None

        # Batch cosine similarity (vectorized)
        cache_vecs = np.vstack([e.query_embedding for e in active])  # (N, 384)
        sims = cache_vecs @ query_vec[0]                              # (N,)
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])

        if best_sim >= self.threshold:
            entry = active[best_idx]
            entry.hit_count += 1
            entry.last_hit_at = time.time()
            self._stats["hits"] += 1
            return entry

        self._stats["misses"] += 1
        return None

    # ── Cache store ───────────────────────────────────────────────────────
    def store(
        self,
        query_vec: np.ndarray,
        query_type: str,
        domain_intent: str,
        query_text: str,
        answer: str,
        provenance: list[dict],
        confidence_label: str,
        total_tokens: int,
    ) -> None:
        intent_key = f"{query_type}::{domain_intent}"
        ttl = DOMAIN_TTL.get(domain_intent, DOMAIN_TTL["general"])

        entry = CacheEntry(
            query_embedding=query_vec[0].copy(),
            query_type=query_type,
            domain_intent=domain_intent,
            query_canonical=query_text,
            answer=answer,
            provenance=provenance,
            confidence_label=confidence_label,
            total_tokens=total_tokens,
            ttl_seconds=ttl,
        )

        if intent_key not in self._store:
            self._store[intent_key] = []

        bucket = self._store[intent_key]
        bucket.append(entry)

        # LRU eviction within bucket
        if len(bucket) > CACHE_MAX_PER_INTENT:
            # Evict least recently hit entry
            bucket.sort(key=lambda e: e.last_hit_at)
            self._stats["evictions"] += len(bucket) - CACHE_MAX_PER_INTENT
            self._store[intent_key] = bucket[-CACHE_MAX_PER_INTENT:]

        # Global eviction if total exceeds max
        total = sum(len(v) for v in self._store.values())
        if total > self.max_total:
            self._evict_global()

    def _evict_global(self) -> None:
        """Evict oldest 10% of entries across all intent buckets."""
        all_entries = [
            (ik, e) for ik, bucket in self._store.items() for e in bucket
        ]
        all_entries.sort(key=lambda x: x[1].last_hit_at)
        to_evict = set(id(e) for _, e in all_entries[: len(all_entries) // 10])
        for ik in self._store:
            self._store[ik] = [e for e in self._store[ik] if id(e) not in to_evict]
        self._stats["evictions"] += len(to_evict)

    # ── Stats ──────────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        total = self._stats["hits"] + self._stats["misses"]
        return {
            **self._stats,
            "hit_rate": round(self._stats["hits"] / max(total, 1), 3),
            "total_entries": sum(len(v) for v in self._store.values()),
            "intent_buckets": len(self._store),
            "bucket_sizes": {k: len(v) for k, v in self._store.items()},
        }


# ── Module-level singleton ────────────────────────────────────────────────────
_cache = IntentAwareCache()

def get_cache() -> IntentAwareCache:
    return _cache
```

---

## Integration: Where the Cache Slots into `retrieval.py`

**Modify**: `retrieval.py` — `hybrid_graphrag()` entry and exit:

```python
import intent_cache as ic
import faiss_store as fs

def hybrid_graphrag(query: str, store) -> dict:
    t_start = time.perf_counter()

    # ── STEP 0: Intent-aware cache lookup (runs before ANYTHING else) ────
    cache = ic.get_cache()
    query_vec = fs._embed_texts([query])           # shape (1, 384), 5ms
    query_type_fast = query_classifier.classify_query(query)  # regex, 0ms
    domain_intent  = ic.IntentAwareCache.classify_domain_intent(query)

    cached = cache.lookup(query_vec, query_type_fast, domain_intent)
    if cached is not None:
        # Serve from cache — 0ms NER, 0ms graph, 0ms LLM
        return _build_cached_response(cached, query, time.perf_counter() - t_start)

    # ── Proceed with full pipeline ────────────────────────────────────────
    # ... (existing NER, graph, vector, LLM code) ...

    # ── STEP LAST: Store in cache ─────────────────────────────────────────
    if answer:   # only cache successful answers
        provenance = [
            {"doc": h["source"], "page": h["page_num"], "score": h["score"]}
            for h in effective_hits
        ]
        cache.store(
            query_vec=query_vec,
            query_type=query_type_fast,
            domain_intent=domain_intent,
            query_text=query,
            answer=answer,
            provenance=provenance,
            confidence_label=confidence_label,
            total_tokens=total_tokens,
        )

    return { ... }  # existing return dict

def _build_cached_response(entry: ic.CacheEntry, query: str, elapsed: float) -> dict:
    """Build a retrieval result dict from a cache hit."""
    return {
        "mode": "hybrid",
        "query": query,
        "query_type": entry.query_type,
        "answer": entry.answer,
        "confidence_label": f"{entry.confidence_label} (cached)",
        "docs": [{"name": p["doc"], "page": p["page"], "score": p["score"],
                  "snippet": "", "full_text": ""} for p in entry.provenance],
        "total_tokens": 0,   # ← cached response costs 0 tokens
        "total_time": elapsed,
        "cache_hit": True,
        "cache_similarity": entry.hit_count,
        "telemetry_breakdown": {
            "pipeline_mode": "IntentCache HIT",
            "latency_total_pipeline_ms": round(elapsed * 1000, 1),
            "tokens_total": 0,
            "ui_badges": [
                {"label": f"⚡ Intent Cache HIT ({entry.domain_intent})",
                 "type": "success",
                 "desc": f"Served from {entry.query_type}::{entry.domain_intent} cache. "
                         f"Hit #{entry.hit_count}. Saved ~{entry.total_tokens} tokens."}
            ],
        },
    }
```

---

## 9 Other Places Intent Can Be Applied in the Pipeline

### Hook 1 — Intent-Routed GLiNER Label Sets (NER)
**File**: `ner_pipeline.py` + `config.py`  
**Current**: One global `GLINER_LABELS` list used for all queries.  
**Proposed**: Domain-specific label subsets loaded based on `domain_intent`.

```python
# config.py — domain-specific label sets
GLINER_LABELS_BY_DOMAIN = {
    "esg_sustainability": [
        "ESG metric", "sustainability initiative", "climate change adaptation",
        "carbon emission", "BRSR indicator", "renewable energy target",
        "water consumption", "biodiversity commitment",
    ],
    "regulatory": [
        "mutual fund scheme name", "SEBI circular reference",
        "regulatory deadline", "penalty amount", "compliance requirement",
        "investment limit percentage", "fund house",
    ],
    "financial_performance": [
        "revenue figure", "EBITDA value", "PAT value", "AUM value",
        "market capitalization", "debt amount", "growth percentage",
    ],
    "fund_comparison": [
        "mutual fund scheme name", "benchmark index", "fund manager",
        "NAV value", "expense ratio", "exit load", "asset class",
    ],
    # ... other domains
}

def get_gliner_labels(domain_intent: str) -> list[str]:
    return GLINER_LABELS_BY_DOMAIN.get(domain_intent, GLINER_LABELS)
```

```python
# ner_pipeline.py — in layer_b_gliner():
def layer_b_gliner(text: str, domain_intent: str = "general") -> list:
    model = _get_gliner()
    labels = config.get_gliner_labels(domain_intent)  # ← domain-routed labels
    raw = model.predict_entities(text, labels, threshold=config.GLINER_THRESHOLD)
    ...
```

**Impact**: ~30% fewer false-positive entities extracted (reduces graph traversal noise). GLiNER also runs slightly faster with fewer labels.

---

### Hook 2 — Intent-Controlled Graph Traversal Depth
**File**: `retrieval.py` → `graph_store.get_subgraph_for_query()`  
**Current**: `hops=1` hardcoded for all query types.  
**Proposed**:

```python
# In hybrid_graphrag(), before graph traversal:
GRAPH_HOPS_BY_INTENT = {
    "aggregation":    2,   # needs 2-hop to count distinct related entities
    "comparison":     2,   # needs 2-hop to find shared attributes between entities
    "direct_lookup":  1,   # 1-hop is enough for a single attribute
    "open_ended":     1,   # prose synthesis doesn't benefit from deep graph
}
GRAPH_LIMIT_BY_INTENT = {
    "aggregation":  25,    # needs more edges for accurate counts
    "comparison":   20,    # one set per entity being compared
    "direct_lookup": 8,    # lean — we just need the direct fact
    "open_ended":   12,    # moderate
}

hops  = GRAPH_HOPS_BY_INTENT.get(query_type, 1)
limit = GRAPH_LIMIT_BY_INTENT.get(query_type, 15)

graph_result = graph_store.get_subgraph_for_query(
    query, product_names=None, hops=hops, limit=limit,
    query_entities=query_entities
)
```

**Impact**: `aggregation` queries get richer graph context (+accuracy). `direct_lookup` queries waste fewer tokens on unnecessary edges (-cost).

---

### Hook 3 — Intent-Driven Vector `top_k` Selection
**File**: `retrieval.py:211`  
**Current**: `store.retrieve(query, top_k_children=5)` — same for all intents.  
**Proposed**:

```python
VECTOR_TOPK_BY_INTENT = {
    "aggregation":    3,   # graph does the heavy lifting; less vector noise
    "comparison":     4,   # need examples from both entities' docs
    "direct_lookup":  2,   # single fact — top-2 is enough
    "open_ended":     6,   # prose synthesis needs broad context
}

top_k = VECTOR_TOPK_BY_INTENT.get(query_type, 5)
hits = store.retrieve(query, top_k_children=top_k)
```

**Impact**: `direct_lookup` cuts from 5 chunks (450 tokens) to 2 chunks (180 tokens). `open_ended` ESG queries get 6 chunks for richer prose context.

---

### Hook 4 — Intent-Aware Prompt Template Selection
**File**: `context_engineering.py`  
**Current**: Single generic `RANKING_PREAMBLE` for all query types.  
**Proposed**: Intent-specific system instructions that shape LLM output format.

```python
PROMPT_TEMPLATES = {
    "aggregation": """
You are an expert analyst. A verified aggregate computation has been run against the knowledge graph.
Present the results as: (1) a one-line direct answer with the number, (2) a breakdown by document.
Never make up numbers. If the graph aggregate is present, cite it as [graph]. Be concise.
""",
    "comparison": """
You are comparing entities. Present your answer as a structured side-by-side markdown table
with columns: | Dimension | Entity A | Entity B |. Only compare dimensions where data exists.
Never blend facts from different entities in the same cell.
""",
    "direct_lookup": """
You are answering a specific factual question. Give the answer in ONE sentence.
Cite the source document as [1]. If the fact is not in context, say exactly: "Not found in indexed documents."
""",
    "open_ended::esg_sustainability": """
You are an ESG analyst. Structure your answer as: (1) Key initiatives listed, (2) Benefits and outcomes,
(3) Metrics/targets if mentioned. Cite document + page as [Doc, p.N].
""",
    "open_ended::regulatory": """
You are a regulatory compliance expert. Answer with: (1) The rule/requirement, (2) Applicable circular/date,
(3) Scope (who it applies to). Use exact regulatory language where quoted.
""",
    "open_ended": """
Synthesize the context into a clear, grounded answer in 3-5 sentences.
Cite document sources as [1], [2]. If context is insufficient, identify the specific gap.
""",
}

def get_prompt_template(query_type: str, domain_intent: str) -> str:
    # Try specific template first (e.g., "open_ended::esg_sustainability")
    key = f"{query_type}::{domain_intent}"
    return PROMPT_TEMPLATES.get(key, PROMPT_TEMPLATES.get(query_type, PROMPT_TEMPLATES["open_ended"]))
```

**Impact**: ESG queries now get structured "initiatives + benefits" output by default. Comparison queries get markdown tables. Dramatically improves answer usability.

---

### Hook 5 — Intent-Driven Cache TTL Policy
**Already designed in `intent_cache.py` above.**

The key insight is that regulatory answers age differently from market data:

| Domain | TTL | Rationale |
|---|---|---|
| `regulatory` | 7 days | SEBI circulars change quarterly at most |
| `esg_sustainability` | 3 days | ESG reports are quarterly |
| `financial_performance` | 1 day | Earnings data can be updated |
| `fund_comparison` | 6 hours | NAVs change daily at EOD |
| `market_data` | 1 hour | Prices change intraday |

---

### Hook 6 — Intent-Aware Confidence Thresholds for Cache Hit
**File**: `intent_cache.py`

Not all intents should use the same 0.90 threshold. A `direct_lookup` query is very precise — "What is the NAV of HDFC Large Cap Fund?" vs "What is the NAV of HDFC Mid Cap Fund?" — these are very similar text but need different answers.

```python
CACHE_THRESHOLD_BY_INTENT = {
    "direct_lookup":  0.96,   # Very strict — tiny wording changes matter
    "aggregation":    0.93,   # Strict — different scope = different number
    "comparison":     0.91,   # Slightly relaxed — structural comparisons generalise
    "open_ended":     0.88,   # Relaxed — prose about same topic is often reusable
}

# In IntentAwareCache.lookup():
threshold = CACHE_THRESHOLD_BY_INTENT.get(query_type, CACHE_SIMILARITY_THRESHOLD)
if best_sim >= threshold:   # uses per-intent threshold instead of global
```

**Impact**: Prevents wrong answers on very similar direct-lookup queries while allowing ESG/open-ended answers to be served more aggressively from cache.

---

### Hook 7 — Intent-Aware Multi-Turn History Compression
**File**: `taxonomy_retrieval.py:hybrid_graphrag_v2()` and `retrieval.py`  
**Current**: Last 4 turns of history included verbatim for all query types.  
**Proposed**: Compress history differently by domain intent.

```python
HISTORY_TURNS_BY_INTENT = {
    "regulatory":           6,   # regulatory conversations reference earlier clauses
    "esg_sustainability":   4,   # ESG discussions build on prior initiative mentions
    "financial_performance": 3,  # financial Q&A is usually standalone
    "fund_comparison":      2,   # comparison queries rarely chain
    "direct_lookup":        1,   # direct lookups are almost always standalone
    "general":              4,
}

# Compress earlier turns for non-regulatory intents
def compress_history_for_intent(history: list[dict], domain_intent: str) -> str:
    n_turns = HISTORY_TURNS_BY_INTENT.get(domain_intent, 4)
    recent = history[-n_turns * 2:]   # last N turns (user + assistant)
    lines = []
    for m in recent:
        role = m["role"].upper()
        content = m["content"]
        # Compress older turns to just key entities
        if m is not recent[-2] and m is not recent[-1]:
            content = content[:100] + "…" if len(content) > 100 else content
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
```

**Impact**: `direct_lookup` queries stop paying for 4 turns of irrelevant history. `regulatory` queries retain more context for clause cross-references.

---

### Hook 8 — Intent Metadata in Audit Log + Streamlit Telemetry Badge
**File**: `retrieval.py:log_query_audit()`

Add intent fields to every audit log entry and surface them as a UI badge:

```python
# In audit_record dict:
audit_record["domain_intent"]      = domain_intent
audit_record["intent_key"]         = f"{query_type}::{domain_intent}"
audit_record["cache_hit"]          = False
audit_record["cache_similarity"]   = None
audit_record["ner_labels_used"]    = config.get_gliner_labels(domain_intent)

# Cache hit path:
audit_record["cache_hit"]          = True
audit_record["cache_similarity"]   = best_sim
audit_record["tokens_saved"]       = cached_entry.total_tokens

# UI badge:
ui_badges.append({
    "label": f"🎯 Domain: {domain_intent.replace('_', ' ').title()}",
    "type": "info",
    "desc": f"Intent routing: {intent_key} | Cache threshold: {threshold:.0%}"
})
```

**Impact**: Full observability on intent routing. You can see in the Streamlit telemetry panel exactly which domain was detected, what threshold was applied, and whether the cache saved tokens.

---

### Hook 9 — Intent-Aware Answer Confidence Score Calibration
**File**: `retrieval.py:337–344`  
**Current**: Confidence label is based on graph signal strength alone.  
**Proposed**: Modulate confidence by domain intent coverage in the graph.

```python
# Intent-coverage confidence modifier
DOMAIN_GRAPH_COVERAGE = {
    # How well the current graph schema covers this domain (0.0 = no nodes, 1.0 = full)
    "regulatory":           0.85,   # Good — SchemeClass, RegulatoryRegime nodes exist
    "fund_comparison":      0.70,   # Moderate — Entity nodes but limited attributes
    "financial_performance": 0.50,  # Partial — revenue entities but no FinancialFact nodes yet
    "esg_sustainability":   0.15,   # Poor — no ESGMetric nodes in schema yet
    "general":              0.50,
}

def calibrate_confidence(raw_confidence: str, domain_intent: str) -> str:
    """Downgrade confidence if the domain is poorly covered in the graph."""
    coverage = DOMAIN_GRAPH_COVERAGE.get(domain_intent, 0.5)
    if coverage < 0.3 and "high" in raw_confidence:
        return raw_confidence.replace("high", "medium") + " (limited graph coverage)"
    return raw_confidence
```

**Impact**: Users and compliance teams see an honest confidence signal — ESG answers are correctly labelled "medium confidence" until the ESG graph schema is expanded.

---

## Full Pipeline View with All Intent Hooks

```
Query: "What are key ESG initiatives for climate change adaptation?"
  │
  ├─ [Hook 0] Intent Classification
  │     query_type   = "open_ended"
  │     domain_intent = "esg_sustainability"
  │     intent_key   = "open_ended::esg_sustainability"
  │
  ├─ [Hook Cache] Dual-Gate Cache Lookup (threshold=0.88 for open_ended)
  │     → MISS (first time) → proceed
  │
  ├─ [Hook 1] NER Layer B (GLiNER)
  │     labels = ESG label set (8 labels vs. 13 generic)
  │     → "climate change adaptation", "ESG metric" extracted
  │
  ├─ [Hook 2] Graph Traversal
  │     hops=1, limit=12 (open_ended parameters)
  │     → entity_texts = ["climate change adaptation", "ESG metric"]
  │     → (no ESG nodes yet → empty, clean fallback to vector)
  │
  ├─ [Hook 3] Vector Retrieval
  │     top_k=6 (open_ended gets more chunks)
  │     → 6 chunks from Adani_Portfolio_H1FY25_ESG.pdf
  │
  ├─ [Hook 4] Prompt Assembly
  │     template = PROMPT_TEMPLATES["open_ended::esg_sustainability"]
  │     → structured: "1. Initiatives, 2. Benefits, 3. Metrics"
  │
  ├─ [Hook 7] History
  │     n_turns=4 for esg_sustainability
  │
  ├─ [Hook 9] Answer + Confidence Calibration
  │     raw = "high confidence" (strong vector hits, score=0.81)
  │     calibrated = "medium confidence (limited graph coverage)"
  │     (ESG graph coverage = 0.15, so downgraded)
  │
  ├─ [Hook 8] Audit Log
  │     domain_intent="esg_sustainability", intent_key="open_ended::esg_sustainability"
  │     cache_hit=False, tokens_saved=0
  │
  └─ [Hook Cache STORE]
        key = (query_embedding, "open_ended::esg_sustainability")
        ttl = 3 days (esg_sustainability TTL)
        → stored for future similar queries

Second identical query 10 minutes later:
  ├─ [Hook Cache] lookup → similarity=1.00 >= 0.88 → CACHE HIT
  └─ Returns in ~8ms. 0 tokens consumed. 0 LLM calls.
```

---

## Implementation Sequence

```
Phase 1 (Today, 2 hours):
  ✅ Create intent_cache.py (new file — no impact on existing code)
  ✅ Add domain_intent classifier to query_classifier.py (pure addition)
  ✅ Wire cache lookup/store into retrieval.py hybrid_graphrag()
  ✅ Add domain_intent to audit log

Phase 2 (This Week, 1–2 days):
  ✅ Add GLINER_LABELS_BY_DOMAIN to config.py
  ✅ Pass domain_intent to layer_b_gliner()
  ✅ Add PROMPT_TEMPLATES dict to context_engineering.py
  ✅ Add VECTOR_TOPK_BY_INTENT and GRAPH_HOPS_BY_INTENT
  ✅ Add per-intent cache thresholds

Phase 3 (Next Week):
  ✅ Intent-aware history compression
  ✅ Confidence calibration by domain coverage
  ✅ Streamlit intent badge in telemetry panel
  ✅ Cache hit-rate dashboard in Analytics tab
```

---

## Open Questions for User Review

1. **Cache persistence**: Should the cache survive Streamlit restarts (write to disk as `.pkl`) or be ephemeral (in-memory, reset on restart)? Disk persistence means ESG queries from yesterday serve from cache today — valuable for a compliance team.

2. **Domain intent coverage for "corporate_governance"**: Should Adani corporate governance queries (board composition, promoter holding) be treated as a separate domain or merged with `financial_performance`? This affects both cache partitioning and GLiNER label routing.

3. **Cache invalidation on reindex**: When new documents are added (the 50-doc expansion), should the cache be cleared? Or should individual domain buckets be selectively expired (e.g., adding a new SEBI circular only clears the `regulatory` bucket)?

4. **Threshold for `direct_lookup` at 0.96**: Is this too strict? "What is the NAV of HDFC Large Cap Fund on 15 July?" vs "What is the NAV of HDFC Large Cap Fund on 16 July?" would score ~0.97 similarity but have different answers. Should we also gate on detected date entities?
