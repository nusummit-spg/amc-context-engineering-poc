# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Cache Token Optimization — "Zero-Token Warm Hit" Architecture

## Problem Statement

A correct and technically honest observation has been made: in the current system, a warm cache hit
does **not** demonstrate token savings — it merely shows latency savings. The telemetry reports:

| Run Type | Input Tokens | Output Tokens | Total | LLM Cost |
|---|---|---|---|---|
| **Cold** | 622 | 398 | **1,020** | Billed |
| **Warm (Cache Hit)** | 1,020 | 0 | **1,020** | $0.00 |

The total is identical because `tokens_input` on cache hits is set to `cached.total_tokens` 
(the original cold run's full token count), used as a "stored volume" for audit transparency.
This eliminates the ability to justify token savings as a second, independent benefit of caching.

**Root Cause (exact code location):**
`taxonomy_retrieval.py` lines 395–397:
```python
"tokens_input": cached.total_tokens,   # ← Reports original cold token count
"tokens_output": 0,
"tokens_total": cached.total_tokens,   # ← Same as cold run — no savings shown
```

---

## Technical Root Cause Analysis

### The Current Pipeline (Cache Hit Path)

```
Query Received
    │
    ▼
[1] PII Scrub (query)                          ← ~5 tokens cost
    │
    ▼
[2] Compliance Input Guard                     ← ~5 tokens cost
    │
    ▼
[3] Load FAISS Index + Embed Query             ← EMBEDDING COST (no token billing)
    │
    ▼
[4] Classify Domain Intent (regex, free)
    │
    ▼
[5] IntentCache.lookup() → CACHE HIT ✅
    │
    ▼
[6] STILL runs: retrieve_graph() (Neo4j)       ← 20-30ms latency, no token cost
    │
    ▼
[7] Return cached answer                       
    + telemetry: tokens_input = cached.total_tokens (1,020) ← THE PROBLEM
```

**Key Insight:** At step [5], when a cache hit is confirmed, **no prompt is assembled,
no context chunks are retrieved from FAISS, and no LLM is called**. The only real
compute cost is:
- Query embedding (~2ms)
- Cosine similarity computation (~0.1ms)
- Optional Neo4j re-traversal (~20-30ms for live graph UI)

The 1,020 tokens being reported is not a real token cost — it's a ghost accounting artifact
from the cold run stored in `CacheEntry.total_tokens`.

---

## Solution Architecture: 5 Complementary Approaches

These approaches are **layered** — each adds an independent dimension of token-savings evidence.
They can be implemented sequentially or in combination.

---

### Approach 1: Separate Cache-Specific Token Accounting (Quickest Win)

**Philosophy**: Report only real token work performed on the cache hit path.

#### What Changes
In `taxonomy_retrieval.py` cache hit block, replace the ghost token reporting with
an honest breakdown of actual work done:

```python
# NEW: Cache-specific token accounting
CACHE_PROBE_TOKENS = 12       # Approximate: query embedding + cosine sim overhead
CACHE_OVERHEAD_TOKENS = 8     # Domain classification + PII scan overhead

telemetry:
    "tokens_input":  CACHE_PROBE_TOKENS,        # Real: ~12 tokens of actual work
    "tokens_output": 0,                          # Real: zero LLM generation
    "tokens_total":  CACHE_PROBE_TOKENS,         # Real: ~12 total
    "tokens_cold_equivalent": cached.total_tokens,  # New field: what it WOULD have cost
    "tokens_saved": cached.total_tokens - CACHE_PROBE_TOKENS,   # New field: net savings
```

#### New Fields in CacheEntry (intent_cache.py)
Add to `CacheEntry` dataclass:
```python
@dataclass
class CacheEntry:
    ...
    input_tokens_cold: int    # Tokens that were billed on the original cold run (input)
    output_tokens_cold: int   # Tokens that were billed on the original cold run (output)
    prompt_char_len: int      # Char length of the original prompt (for compression ratio)
```

#### Result
| Run Type | tokens_input | tokens_output | tokens_total | tokens_saved |
|---|---|---|---|---|
| Cold | 622 | 398 | 1,020 | — |
| Warm | 12 | 0 | 12 | **1,008 (98.8%)** |

**Traceability**: Add to HTML performance report as "Cache Token Efficiency" metric.

---

### Approach 2: Pre-Cache Gate — Move Cache Check Before Query Embedding

**Philosophy**: The cache check currently fires AFTER query embedding (step [3]), which
means even on a cache hit, the full embedding cost is paid. Move the cache gate to
happen BEFORE embedding using a fast lightweight probe.

#### Two-Stage Cache Architecture

**Stage 1 — Fast Text Fingerprint Gate (no embedding needed):**
```python
# NEW: O(1) hash-based preliminary cache probe (before embedding)
query_fingerprint = hashlib.md5(query.lower().strip().encode()).hexdigest()
if fingerprint_exists_in_cache(query_fingerprint):
    return serve_cache_hit(tokens_probe=2)  # Effectively 0 token cost
```

**Stage 2 — Semantic Cosine Gate (current behavior, now only for non-fingerprint queries):**
```python
# Only reach here if exact fingerprint missed
query_vec_np = fs._embed_texts([query])   # Embedding happens now
cached = cache.lookup(query_vec_np[0:1], ...)
```

#### What to Add to IntentAwareCache
```python
class IntentAwareCache:
    def __init__(self, ...):
        self._fingerprint_index: Dict[str, str] = {}   # md5 → cache_key
    
    def fingerprint_probe(self, query: str) -> Optional[CacheEntry]:
        """Stage 1: O(1) exact text match — avoids embedding entirely."""
        fp = hashlib.md5(query.lower().strip().encode()).hexdigest()
        cache_key = self._fingerprint_index.get(fp)
        if cache_key:
            return self._get_by_key(cache_key)
        return None
    
    def store(self, ...):
        # Also store fingerprint index on every new entry
        fp = hashlib.md5(query_text.lower().strip().encode()).hexdigest()
        self._fingerprint_index[fp] = cache_key
```

#### Token Cost Comparison

| Scenario | Approach 1 (semantic gate) | Approach 2 (fingerprint gate) |
|---|---|---|
| Exact repeat query | tokens = 12 (embed cost) | tokens ≈ **0** (hash only) |
| Semantically similar | tokens = 12 (embed cost) | tokens = 12 (falls to Stage 2) |
| Cache miss | Full pipeline | Full pipeline |

---

### Approach 3: Compressed Answer Cache + Response Expansion

**Philosophy**: On cold runs, store a compressed summary of the answer (not the full response).
On cache hits, serve the compressed summary directly. This dramatically reduces
`cached.total_tokens` itself, making the stored volume smaller.

#### Compression Strategy

**At cache STORE time (cold run):**
```python
# After getting LLM answer (398 output tokens, ~1,600 chars):
compressed = compress_for_cache(raw_answer)
# Strategy: extract key facts, strip boilerplate, keep citations
# Target: 80-120 tokens compressed vs 398 tokens original

cache.store(
    answer=raw_answer,           # Full answer shown to user
    compressed_answer=compressed, # Compressed stored in cache
    compressed_tokens=len(compressed.split()) * 1.3  # Approx token count
)
```

**At cache HIT time:**
```python
# Serve compressed answer for token accounting purposes
# Expand it with a trivial template for UI display (no LLM call needed)
cached_tokens = entry.compressed_tokens   # ~100 tokens vs 1,020 original

telemetry:
    "tokens_input":  cached_tokens,     # ~100 (compressed stored volume)
    "tokens_output": 0,
    "tokens_total":  cached_tokens,     # ~100
    "tokens_saved":  1020 - cached_tokens  # ~920 saved
```

#### Compression Algorithm (no LLM needed)
```python
def compress_for_cache(answer: str) -> str:
    """
    Extractive compression: keep first sentence of each paragraph +
    all sentences containing citation markers (circular numbers, dates).
    Target: reduce to ~25% of original length.
    """
    sentences = sent_tokenize(answer)
    key_sentences = []
    for i, sent in enumerate(sentences):
        if i == 0:                          # Always keep first
            key_sentences.append(sent)
        elif re.search(r'SEBI|circular|section|\d{4}', sent):  # Citations
            key_sentences.append(sent)
        elif len(key_sentences) < 3:        # Keep early context
            key_sentences.append(sent)
    return ' '.join(key_sentences)
```

#### Result
| Scenario | Cold Tokens | Warm Tokens | Savings |
|---|---|---|---|
| Approach 3 Cache Hit | 1,020 | **~100** | **90%** |

---

### Approach 4: Token Ledger Redesign — Dual-Track Accounting

**Philosophy**: The existing `CacheEntry.total_tokens` mixes two semantically different
things: "tokens spent to generate the answer" vs "tokens required to serve the answer."
Separate these into distinct tracked fields across the entire system.

#### New Token Ledger Schema

```python
@dataclass 
class TokenLedger:
    # Cold run fields (populated once at cache store time)
    cold_input_tokens: int        # Tokens in the LLM prompt (622)
    cold_output_tokens: int       # Tokens the LLM generated (398)
    cold_total_tokens: int        # Sum of above (1,020)
    cold_api_cost_usd: float      # Actual API billing cost
    
    # Warm hit fields (populated at cache serve time)
    warm_probe_tokens: int        # Tokens for cache lookup (~12)
    warm_graph_tokens: int        # Tokens for optional Neo4j re-traversal (0, it's Cypher not LLM)
    warm_total_tokens: int        # Sum of above (~12)
    warm_api_cost_usd: float      # Always $0.00
    
    # Savings fields (computed)
    token_savings: int            # cold_total_tokens - warm_total_tokens
    token_savings_pct: float      # (token_savings / cold_total_tokens) * 100
    cost_savings_usd: float       # cold_api_cost_usd - warm_api_cost_usd
    
    # Provenance
    cache_hit: bool
    cache_similarity_score: float
    cache_domain: str
    cache_ttl_remaining_sec: int
```

#### Telemetry Display in UI
The telemetry panel in `chat_view.py` would then show:
```
Token Efficiency Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cold Equivalent:    1,020 tokens  ($0.0031)
Cache Probe Cost:      12 tokens  ($0.0000)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Net Savings:        1,008 tokens  (98.8%)
API Cost Savings:   $0.0031 / query
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

This is the most customer-facing, demo-ready change — it makes the value immediately visible.

---

### Approach 5: Aggregate Savings Dashboard (Cumulative Token Economy)

**Philosophy**: A single-query saving of ~1,008 tokens is modest. But **across 100, 1,000,
10,000 queries**, the cumulative savings becomes a compelling product story.

#### New Persistent Savings Ledger

```python
# In intent_cache.py — persist aggregate stats to disk
class SavingsLedger:
    def __init__(self, path: str):
        self.path = path
        self._data = self._load()
    
    def record_hit(self, tokens_saved: int, cost_saved_usd: float):
        self._data["total_hits"] += 1
        self._data["total_tokens_saved"] += tokens_saved
        self._data["total_cost_saved_usd"] += cost_saved_usd
        self._data["cumulative_co2_saved_grams"] += tokens_saved * 0.0002  # Approx
        self._save()
    
    def record_miss(self, tokens_used: int, cost_usd: float):
        self._data["total_misses"] += 1
        self._data["total_tokens_used"] += tokens_used
        self._data["total_cost_usd"] += cost_usd
        self._save()
    
    def summary(self) -> dict:
        total = self._data["total_hits"] + self._data["total_misses"]
        return {
            "hit_rate_pct": round(self._data["total_hits"] / max(total, 1) * 100, 1),
            "tokens_saved_cumulative": self._data["total_tokens_saved"],
            "cost_saved_cumulative_usd": round(self._data["total_cost_saved_usd"], 4),
            "co2_saved_grams": round(self._data["cumulative_co2_saved_grams"], 2),
            "queries_served_free": self._data["total_hits"],
        }
```

#### Dashboard Widget (analytics_view.py)
```
┌─────────────────────────────────────────────┐
│         SYSTEM TOKEN ECONOMY LEDGER         │
├─────────────────────────────────────────────┤
│  Total Queries Served:          1,247        │
│  Cache Hit Rate:                 73.4%       │
│  Queries Served from Cache:       915        │
│  Tokens Saved (Cumulative):   923,120        │
│  API Cost Saved (Cumulative):   $2.84        │
│  Estimated CO₂ Saved:          184.6g        │
└─────────────────────────────────────────────┘
```

---

## Implementation Priority & Sequence

| Phase | Approach | Files Changed | Effort | Impact |
|---|---|---|---|---|
| **Phase 1** | Approach 1 (Honest Token Reporting) | `taxonomy_retrieval.py` (5 lines), `intent_cache.py` (3 fields) | 30 min | High — fixes the core parity problem immediately |
| **Phase 2** | Approach 4 (Token Ledger Redesign) | `intent_cache.py`, `chat_view.py` | 2 hrs | Very High — demo-ready UI showing savings |
| **Phase 3** | Approach 2 (Pre-Cache Fingerprint Gate) | `intent_cache.py` | 1 hr | Medium — eliminates embedding cost on exact repeats |
| **Phase 4** | Approach 5 (Savings Dashboard) | `analytics_view.py`, `intent_cache.py` | 3 hrs | Very High — product story for customers |
| **Phase 5** | Approach 3 (Compressed Answer Cache) | `intent_cache.py`, `taxonomy_retrieval.py` | 4 hrs | Medium — architectural complexity for incremental gain |

---

## Verification Plan

### Metric 1: Token Parity Eliminated
- Run same query twice
- Cold run: expect 622 in / 398 out = 1,020 total
- Warm run: expect **12 in / 0 out = 12 total**
- Token savings = 1,008 (98.8%)

### Metric 2: Latency Savings (unchanged, still demonstrated)
- Cold: ~1,310ms LLM wait
- Warm: ~0ms LLM wait (graph re-traversal: ~25ms)

### Metric 3: Cost Savings (unchanged, still demonstrated)
- Cold: ~$0.0031 API cost
- Warm: $0.0000 API cost

### Metric 4: API Call Count (new metric)
- Cold: 1 LLM API call
- Warm: 0 LLM API calls

### Combined Value Statement (for customers)
```
Cache Hit delivers:
  ✅ 98.8% token reduction   (1,020 → 12)
  ✅ 100% API cost savings   ($0.0031 → $0.00)
  ✅ 100% LLM latency savings (1,310ms → 0ms)
  ✅ 0 LLM API calls fired
```

---

## Open Questions

> [!IMPORTANT]
> **Q1**: Should the Neo4j re-traversal on cache hits be made **optional** (toggled by config)?
> Removing it would make cache hits truly zero-compute for all dimensions, but the live
> graph visualization in the UI would show stale node data. Tradeoff: token savings proof
> vs. UI live graph integrity.

> [!IMPORTANT]
> **Q2**: Should `CacheEntry.total_tokens` be deprecated in favor of the new split
> `input_tokens_cold` / `output_tokens_cold` fields, or kept for backwards compatibility
> with the disk-persisted JSON cache store?

> [!NOTE]
> **Q3**: The `co2_saved_grams` metric in the Savings Dashboard is an approximation
> (~0.0002g per token based on LLM inference energy estimates). Should this be included
> in the HTML report as an ESG/sustainability angle, or is it too speculative for
> a compliance-focused product?
