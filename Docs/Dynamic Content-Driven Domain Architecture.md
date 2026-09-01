# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Dynamic Content-Driven Domain Architecture
### Replacing All Hardcoded Domain Constants with a Self-Building Registry

---

## The Fundamental Problem

The previous plan had this pattern throughout the codebase:

```python
# BAD — hardcoded, breaks when you add a credit rating report
DOMAIN_PATTERNS = {
    "esg_sustainability": ["esg", "climate", "carbon", ...],
    "regulatory":         ["sebi", "circular", ...],
    "financial_performance": ["revenue", "ebitda", ...],
}

GLINER_LABELS_BY_DOMAIN = {
    "esg_sustainability": ["ESG metric", "climate change adaptation", ...],
}

DOMAIN_GRAPH_COVERAGE = {
    "esg_sustainability": 0.15,   # ← who updates this when the graph schema changes?
}
```

**Every time you add a new document type, someone has to edit Python files.**  
At 50 documents spanning ESG reports, SEBI circulars, AMC factsheets, credit reports, annual reports, and investor presentations — that's 6+ domain types no one anticipated in code.

---

## The Core Shift: Documents Profile Themselves

```
OLD FLOW (static):
  Code defines domains → Domains shape how documents are processed

NEW FLOW (dynamic):
  Documents are indexed → Documents declare their own domains
                        → Registry aggregates across all documents
                        → System adapts to whatever documents exist
```

**The key insight**: The document already contains everything needed to understand its domain. You just need to ask it once — at index time — and store the answer permanently in `meta.json`.

---

## Architecture: Three Layers

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: DOCUMENT PROFILING (at index-build time, once per document)    │
│                                                                         │
│  PDF → extract_pdf_text_full() → sample 3 pages                        │
│       → DomainProfiler.profile_document()                              │
│       → {document_type, themes, key_entities, key_metrics,             │
│           ner_labels, ttl_class, sample_questions}                      │
│       → saved in meta.json["domain_profile"]                           │
└─────────────────────────────────────────────────────────────────────────┘
                              │  (persisted)
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: DOMAIN REGISTRY (at Streamlit startup, reads all meta.json)   │
│                                                                         │
│  DomainRegistry.build_from_corpus()                                    │
│    reads all faiss_indexes/*/meta.json                                 │
│    aggregates domain_profiles across all documents                     │
│    builds:                                                             │
│      - keyword_patterns[domain]  → for fast regex matching             │
│      - anchor_embeddings[domain] → for semantic classification         │
│      - gliner_labels[domain]     → domain-specific NER labels          │
│      - ttl_seconds[domain]       → cache expiry policy                 │
│      - prompt_preamble[domain]   → adaptive prompt template            │
│      - graph_coverage[domain]    → actual Neo4j node counts            │
└─────────────────────────────────────────────────────────────────────────┘
                              │  (in-memory singleton)
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: QUERY SERVING (per query, all dynamic)                        │
│                                                                         │
│  query → classify_domain(registry)  → intent_key                      │
│        → get_gliner_labels(domain)  → domain-specific NER             │
│        → cache.lookup(intent_key)   → 0ms if hit                      │
│        → get_prompt(domain)         → adaptive template                │
│        → build_response(coverage)  → calibrated confidence            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component 1: `domain_profiler.py` (New File — Build Time)

**When it runs**: Once per document, during `build_faiss_index_for_pdf()`.  
**Input**: Sample text from the document (~3,000 chars from first 3 representative pages).  
**Output**: A `DomainProfile` stored in `meta.json`.

```python
"""
domain_profiler.py
==================
Extracts a self-describing domain profile from a document at index time.
Called once per document during FAISS build. Output is stored in meta.json
and never recomputed unless force_rebuild=True.

The profile is the source of truth for all domain-specific behaviour:
  - intent classification
  - GLiNER label routing
  - cache TTL
  - prompt template selection
  - graph coverage calibration
"""
from __future__ import annotations
import json
from typing import Optional
import config
import llm_text_client

# ── Document type taxonomy (open — new types are added by documents) ─────────
# This is a VOCABULARY of possible types, NOT an exhaustive list.
# Documents can declare new types not listed here.
KNOWN_DOC_TYPES = [
    "esg_sustainability_report",
    "annual_report",
    "quarterly_results",
    "sebi_regulatory_circular",
    "amc_factsheet",
    "mutual_fund_categorization",
    "credit_rating_report",
    "investor_presentation",
    "research_report",
    "risk_disclosure_document",
    "portfolio_disclosure",
    "corporate_governance_report",
]

# ── TTL mapping by document type ─────────────────────────────────────────────
# Documents declare their own TTL class; registry maps it to seconds.
TTL_CLASS_TO_SECONDS = {
    "static":    86400 * 30,   # annual reports, circulars — change rarely
    "quarterly": 86400 * 7,    # quarterly reports — change every 3 months
    "monthly":   86400 * 1,    # factsheets — change every month
    "daily":     3600 * 6,     # NAV, fund performance — updated daily
    "realtime":  3600 * 1,     # market prices — change intraday
}

_PROFILE_PROMPT = """You are analyzing a document to understand its content and domain.
Read the document sample below and extract a structured profile.

DOCUMENT SAMPLE:
{sample_text}

Return ONLY a valid JSON object with exactly these fields:
{{
  "document_type": "<one of the types below or a new type if none fit>",
  "primary_domain": "<single most important domain keyword, e.g. 'ESG', 'mutual funds', 'credit rating'>",
  "secondary_domains": ["<domain2>", "<domain3>"],
  "key_themes": ["<theme1>", "<theme2>", "<theme3>", "<theme4>", "<theme5>"],
  "key_entities": ["<entity1>", "<entity2>", ...],
  "key_metrics": ["<metric1>", "<metric2>", ...],
  "ner_labels": ["<label suitable for GLiNER zero-shot extraction>", ...],
  "ttl_class": "<static|quarterly|monthly|daily|realtime>",
  "typical_queries": ["<example query a user would ask>", "<example2>", "<example3>"],
  "language": "english",
  "time_sensitivity": "<high|medium|low>"
}}

Known document types (you may use others if none fit):
{doc_types}

Be specific with ner_labels — use descriptive phrases that GLiNER understands,
like "carbon emission target", "fund AUM value", "SEBI circular reference",
"board director name", "credit rating score".
"""


def profile_document(
    pages_data: list[dict],
    product_name: str,
    verbose: bool = True,
) -> dict:
    """
    Extract a domain profile from a document's pages.
    Uses a representative sample (first page + one from middle + last page).
    """
    # ── Sample strategy: first + middle + last page ───────────────────────
    n = len(pages_data)
    sample_indices = sorted({0, n // 2, max(0, n - 1)})
    sample_parts = []
    for i in sample_indices:
        page = pages_data[i]
        text = page.get("text", "").strip()
        if text:
            sample_parts.append(f"[Page {page['page_num']}]\n{text[:1200]}")

    sample_text = "\n\n---\n\n".join(sample_parts)[:4000]  # cap at 4K chars

    if not sample_text.strip():
        if verbose:
            print(f"  [profiler] No text sample available for '{product_name}' — using defaults", flush=True)
        return _default_profile(product_name)

    # ── LLM profile extraction ────────────────────────────────────────────
    prompt = _PROFILE_PROMPT.format(
        sample_text=sample_text,
        doc_types="\n".join(f"  - {t}" for t in KNOWN_DOC_TYPES),
    )

    if verbose:
        print(f"  [profiler] Profiling '{product_name}'…", flush=True)

    result = llm_text_client.call_llm_json(
        prompt, model_id=config.CLAUDE_MODEL_LIGHT
    )

    if not isinstance(result, dict):
        if verbose:
            print(f"  [profiler] Profile extraction failed — using defaults", flush=True)
        return _default_profile(product_name)

    # ── Validate + fill missing fields ───────────────────────────────────
    profile = {
        "document_type":    result.get("document_type", "unknown"),
        "primary_domain":   result.get("primary_domain", product_name),
        "secondary_domains": result.get("secondary_domains", []),
        "key_themes":       result.get("key_themes", []),
        "key_entities":     result.get("key_entities", []),
        "key_metrics":      result.get("key_metrics", []),
        "ner_labels":       result.get("ner_labels", []),
        "ttl_class":        result.get("ttl_class", "quarterly"),
        "typical_queries":  result.get("typical_queries", []),
        "language":         result.get("language", "english"),
        "time_sensitivity": result.get("time_sensitivity", "medium"),
        "product_name":     product_name,
    }

    if verbose:
        print(f"  [profiler] '{product_name}' → type='{profile['document_type']}' "
              f"domain='{profile['primary_domain']}' "
              f"ttl={profile['ttl_class']}", flush=True)

    return profile


def _default_profile(product_name: str) -> dict:
    """Fallback when LLM profiling is unavailable."""
    return {
        "document_type":    "unknown",
        "primary_domain":   product_name,
        "secondary_domains": [],
        "key_themes":       [],
        "key_entities":     [],
        "key_metrics":      [],
        "ner_labels":       list(config.GLINER_LABELS),   # use global defaults
        "ttl_class":        "quarterly",
        "typical_queries":  [],
        "language":         "english",
        "time_sensitivity": "medium",
        "product_name":     product_name,
    }
```

---

## Component 2: `domain_registry.py` (New File — Startup)

**When it runs**: Once at Streamlit startup, after `@st.cache_resource`.  
**Input**: All `faiss_indexes/*/meta.json` files.  
**Output**: An in-memory `DomainRegistry` singleton used by all query-time modules.

```python
"""
domain_registry.py
==================
Aggregates domain_profile data from all indexed documents at startup.
Builds a live, corpus-driven registry that replaces all hardcoded domain
constants. As documents are added/removed, re-calling build_from_corpus()
refreshes the registry automatically.

Key outputs:
  - classify_domain(query, query_vec) → (domain_name, confidence)
  - get_gliner_labels(domain) → list of NER labels specific to that domain
  - get_ttl(domain) → cache TTL in seconds
  - get_prompt_preamble(domain, query_type) → LLM prompt prefix
  - get_cache_threshold(domain, query_type) → cosine similarity threshold
  - get_graph_coverage(domain) → actual Neo4j node count fraction
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from collections import defaultdict
from typing import Optional
import numpy as np

import config

# ── Universal labels always included regardless of domain ────────────────────
UNIVERSAL_NER_LABELS = [
    "organization name", "person name", "date", "monetary value",
    "percentage", "regulatory reference",
]

# ── Base cache thresholds by query type (starting point, tuned per domain) ───
BASE_CACHE_THRESHOLDS = {
    "direct_lookup": 0.96,
    "aggregation":   0.93,
    "comparison":    0.91,
    "open_ended":    0.88,
}

# ── Time sensitivity → cache threshold modifier ───────────────────────────────
# High time-sensitivity docs need stricter thresholds (stale answers are bad)
SENSITIVITY_THRESHOLD_MODIFIER = {
    "high":   +0.03,   # tighten — market data, daily NAV
    "medium": +0.00,   # no change
    "low":    -0.02,   # relax — static regulatory docs, old reports
}


class DomainEntry:
    """One domain derived from one or more documents."""
    def __init__(self, name: str):
        self.name = name
        self.document_types: set[str] = set()
        self.key_themes: list[str] = []
        self.key_entities: list[str] = []
        self.key_metrics: list[str] = []
        self.ner_labels: set[str] = set()
        self.ttl_class: str = "quarterly"
        self.time_sensitivity: str = "medium"
        self.typical_queries: list[str] = []
        self.contributing_docs: list[str] = []
        # Set at registry build time:
        self.anchor_embedding: Optional[np.ndarray] = None
        self.keyword_set: set[str] = set()


class DomainRegistry:
    """
    Content-driven registry. Call build_from_corpus() to populate.
    Thread-safe for reads after build is complete.
    """

    def __init__(self):
        self._domains: dict[str, DomainEntry] = {}
        self._built_at: float = 0.0
        self._corpus_size: int = 0

    # ── Build ────────────────────────────────────────────────────────────
    def build_from_corpus(
        self,
        indexes_dir: Path,
        measure_graph_coverage: bool = False,
    ) -> None:
        """
        Scan all meta.json files and aggregate domain profiles.
        Call once at startup (wrapped in @st.cache_resource).
        """
        from domain_profiler import TTL_CLASS_TO_SECONDS
        import faiss_store as fs

        self._domains.clear()
        meta_files = list(indexes_dir.glob("*/meta.json"))
        self._corpus_size = len(meta_files)

        print(f"  [registry] Building from {len(meta_files)} documents…", flush=True)

        for meta_path in meta_files:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            profile = meta.get("domain_profile")
            if not profile:
                continue   # document indexed before profiling was added

            primary = profile.get("primary_domain", "general")
            secondary = profile.get("secondary_domains", [])
            product_name = meta.get("product_name", "unknown")

            # Register primary domain
            self._merge_into_domain(primary, profile, product_name)

            # Also register secondary domains (lighter merge)
            for sec in secondary:
                self._merge_into_domain(sec, profile, product_name, is_secondary=True)

        # Build keyword sets and anchor embeddings for fast classification
        self._build_keyword_sets()
        self._build_anchor_embeddings()

        # Optionally measure actual graph coverage
        if measure_graph_coverage:
            self._measure_graph_coverage()

        self._built_at = time.time()
        print(f"  [registry] Built {len(self._domains)} domains from "
              f"{self._corpus_size} documents.", flush=True)
        for name, entry in self._domains.items():
            print(f"    → {name}: {len(entry.contributing_docs)} docs, "
                  f"{len(entry.ner_labels)} NER labels, ttl={entry.ttl_class}", flush=True)

    def _merge_into_domain(
        self,
        domain_name: str,
        profile: dict,
        product_name: str,
        is_secondary: bool = False,
    ) -> None:
        if domain_name not in self._domains:
            self._domains[domain_name] = DomainEntry(domain_name)
        entry = self._domains[domain_name]

        entry.contributing_docs.append(product_name)
        entry.document_types.add(profile.get("document_type", "unknown"))
        entry.key_themes.extend(profile.get("key_themes", []))
        entry.key_entities.extend(profile.get("key_entities", []))
        entry.key_metrics.extend(profile.get("key_metrics", []))
        entry.typical_queries.extend(profile.get("typical_queries", []))

        if not is_secondary:
            entry.ner_labels.update(profile.get("ner_labels", []))
            entry.time_sensitivity = profile.get("time_sensitivity", "medium")
            ttl_from_doc = profile.get("ttl_class", "quarterly")
            # Take the more conservative TTL when multiple docs contribute
            if TTL_CLASS_TO_SECONDS.get(ttl_from_doc, 0) < \
               TTL_CLASS_TO_SECONDS.get(entry.ttl_class, 0):
                entry.ttl_class = ttl_from_doc

    def _build_keyword_sets(self) -> None:
        """Build a flat keyword set for each domain from themes + entities + metrics."""
        for entry in self._domains.values():
            words: set[str] = set()
            for item in entry.key_themes + entry.key_entities + entry.key_metrics:
                # Split multi-word items and add both the full phrase and individual words
                words.add(item.lower())
                words.update(w for w in item.lower().split() if len(w) > 3)
            entry.keyword_set = words

    def _build_anchor_embeddings(self) -> None:
        """Embed the domain's typical queries as an anchor for semantic classification."""
        try:
            import faiss_store as fs
            for entry in self._domains.values():
                if not entry.typical_queries:
                    continue
                # Embed all typical queries and average → domain anchor
                vecs = fs._embed_texts(entry.typical_queries[:10])
                entry.anchor_embedding = vecs.mean(axis=0)
                # Normalize
                norm = np.linalg.norm(entry.anchor_embedding)
                if norm > 0:
                    entry.anchor_embedding /= norm
        except Exception as e:
            print(f"  [registry] Anchor embedding failed: {e}", flush=True)

    def _measure_graph_coverage(self) -> None:
        """
        Query Neo4j to get actual entity counts per domain.
        Stores as a coverage score (0.0–1.0) on each DomainEntry.
        """
        try:
            import graph_store
            with graph_store.get_driver().session(database=config.NEO4J_DATABASE) as s:
                result = s.run(
                    "MATCH (n:Entity) RETURN n.label AS label, count(*) AS cnt "
                    "ORDER BY cnt DESC"
                )
                label_counts = {r["label"]: r["cnt"] for r in result if r["label"]}
            total_nodes = sum(label_counts.values()) or 1

            for domain_name, entry in self._domains.items():
                # Match Neo4j labels to domain keywords
                domain_node_count = sum(
                    cnt for label, cnt in label_counts.items()
                    if any(kw in label.lower() for kw in entry.keyword_set)
                )
                entry.graph_coverage = round(domain_node_count / total_nodes, 3)
                print(f"    [registry] Graph coverage '{domain_name}': "
                      f"{domain_node_count}/{total_nodes} = {entry.graph_coverage}", flush=True)
        except Exception as e:
            print(f"  [registry] Graph coverage measurement failed: {e}", flush=True)
            for entry in self._domains.values():
                entry.graph_coverage = 0.5   # neutral default

    # ── Query-Time APIs ──────────────────────────────────────────────────
    def classify_domain(
        self,
        query: str,
        query_vec: Optional[np.ndarray] = None,
    ) -> tuple[str, float]:
        """
        Classify query into a domain. Returns (domain_name, confidence).
        Three-pass strategy: keyword → semantic → default.
        No LLM call — sub-millisecond.
        """
        if not self._domains:
            return "general", 0.0

        query_lower = query.lower()

        # Pass 1: Keyword match (fast, deterministic)
        domain_scores: dict[str, int] = {}
        for name, entry in self._domains.items():
            score = sum(1 for kw in entry.keyword_set if kw in query_lower)
            if score > 0:
                domain_scores[name] = score

        if domain_scores:
            best_domain = max(domain_scores, key=domain_scores.get)
            max_score = domain_scores[best_domain]
            total_keywords = len(self._domains[best_domain].keyword_set) or 1
            confidence = min(max_score / max(total_keywords * 0.1, 1), 1.0)
            if confidence >= 0.3:    # clear keyword winner
                return best_domain, confidence

        # Pass 2: Semantic similarity against anchor embeddings
        if query_vec is not None:
            best_sim, best_name = -1.0, "general"
            for name, entry in self._domains.items():
                if entry.anchor_embedding is None:
                    continue
                sim = float(query_vec[0] @ entry.anchor_embedding)
                if sim > best_sim:
                    best_sim, best_name = sim, name
            if best_sim >= 0.40:    # meaningful semantic match
                return best_name, best_sim

        # Pass 3: Return most-documents domain as default
        if self._domains:
            most_common = max(
                self._domains, key=lambda n: len(self._domains[n].contributing_docs)
            )
            return most_common, 0.1

        return "general", 0.0

    def get_gliner_labels(self, domain: str) -> list[str]:
        """Domain-specific NER labels + universal labels."""
        entry = self._domains.get(domain)
        domain_labels = list(entry.ner_labels) if entry else []
        # Merge with universal labels, deduplicated
        all_labels = list(dict.fromkeys(domain_labels + UNIVERSAL_NER_LABELS))
        return all_labels or list(config.GLINER_LABELS)

    def get_ttl(self, domain: str) -> int:
        """Cache TTL in seconds for this domain."""
        from domain_profiler import TTL_CLASS_TO_SECONDS
        entry = self._domains.get(domain)
        if not entry:
            return TTL_CLASS_TO_SECONDS["quarterly"]
        return TTL_CLASS_TO_SECONDS.get(entry.ttl_class, TTL_CLASS_TO_SECONDS["quarterly"])

    def get_cache_threshold(self, domain: str, query_type: str) -> float:
        """
        Cosine similarity threshold for cache hit.
        Combines base query-type threshold with domain time-sensitivity modifier.
        """
        base = BASE_CACHE_THRESHOLDS.get(query_type, 0.90)
        entry = self._domains.get(domain)
        if not entry:
            return base
        modifier = SENSITIVITY_THRESHOLD_MODIFIER.get(entry.time_sensitivity, 0.0)
        return min(max(base + modifier, 0.80), 0.99)   # clamp to [0.80, 0.99]

    def get_prompt_preamble(self, domain: str, query_type: str) -> str:
        """
        Generate a dynamic prompt preamble based on domain characteristics.
        No hardcoded templates — preamble is assembled from domain metadata.
        """
        entry = self._domains.get(domain)
        if not entry:
            return _DEFAULT_PREAMBLE

        doc_types = ", ".join(sorted(entry.document_types)[:3])
        metrics = ", ".join(entry.key_metrics[:4]) if entry.key_metrics else "key figures"

        if query_type == "comparison":
            return (
                f"You are comparing information from {doc_types} documents. "
                f"Present your answer as a structured side-by-side table. "
                f"Focus on {metrics}. "
                f"Never blend facts from different entities in the same cell."
            )
        elif query_type == "aggregation":
            return (
                f"You are aggregating data from {doc_types} documents. "
                f"Report the computed total, then break it down by source document. "
                f"Focus on {metrics}. Cite the graph as [graph] when using graph data."
            )
        elif query_type == "direct_lookup":
            return (
                f"You are answering a specific factual question from a {doc_types} document. "
                f"Give the answer in ONE sentence. Cite as [1]. "
                f"If not found, say exactly: 'Not found in indexed documents.'"
            )
        else:  # open_ended
            themes = ", ".join(entry.key_themes[:3]) if entry.key_themes else "the main topics"
            return (
                f"You are synthesizing information from {doc_types} documents covering {themes}. "
                f"Structure your answer around the key {metrics}. "
                f"Cite each source as [Doc, p.N]. "
                f"If context is insufficient, identify the specific missing information."
            )

    def get_graph_coverage(self, domain: str) -> float:
        """Actual graph schema coverage for this domain (0.0–1.0)."""
        entry = self._domains.get(domain)
        return getattr(entry, "graph_coverage", 0.5) if entry else 0.5

    def domain_names(self) -> list[str]:
        return list(self._domains.keys())

    def get_stats(self) -> dict:
        return {
            "built_at": self._built_at,
            "corpus_size": self._corpus_size,
            "domains": {
                name: {
                    "docs": len(e.contributing_docs),
                    "ner_labels": len(e.ner_labels),
                    "ttl_class": e.ttl_class,
                    "time_sensitivity": e.time_sensitivity,
                    "graph_coverage": getattr(e, "graph_coverage", None),
                }
                for name, e in self._domains.items()
            }
        }


_DEFAULT_PREAMBLE = (
    "Answer using ONLY the context below. Cite sources as [1], [2]. "
    "If the answer is not in the context, say so explicitly."
)

# ── Module-level singleton ────────────────────────────────────────────────────
_registry: Optional[DomainRegistry] = None

def get_registry() -> DomainRegistry:
    global _registry
    if _registry is None:
        _registry = DomainRegistry()
    return _registry
```

---

## Component 3: `meta.json` Schema Extension

**Modified in**: `faiss_store.py:build_faiss_index_for_pdf()`

```python
# After build_parent_child_chunks(), before embedding:
from domain_profiler import profile_document

domain_profile = profile_document(pages_data, product_name, verbose=verbose)

# ... existing embedding + FAISS build ...

meta = {
    "slug":          slug,
    "product_name":  product_name,
    "source_file":   Path(pdf_path).name,
    "num_pages":     len(pages_data),
    "num_parents":   len(parents),
    "num_children":  len(children),
    "embed_dim":     dim,
    "methods_used":  list(methods_used),
    "claude_vision_pages": vision_pages,
    "local_pages":   local_pages,
    "model":         EMBED_MODEL_NAME,
    "domain_profile": domain_profile,     # ← NEW FIELD
    "indexed_at":    time.time(),
}
```

**Resulting `meta.json` for `Adani_Portfolio_H1FY25_ESG.pdf`** (auto-generated, never written by hand):
```json
{
  "slug": "adani_portfolio_h1fy25_esg",
  "product_name": "Adani_Portfolio_H1FY25_ESG",
  "domain_profile": {
    "document_type": "esg_sustainability_report",
    "primary_domain": "ESG sustainability",
    "secondary_domains": ["corporate governance", "energy infrastructure"],
    "key_themes": ["climate change adaptation", "renewable energy", "water management", "BRSR compliance", "net zero targets"],
    "key_entities": ["Adani Group", "Adani Enterprises", "Adani Green Energy"],
    "key_metrics": ["carbon emission intensity", "renewable capacity GW", "water consumption", "ESG score", "BRSR rating"],
    "ner_labels": ["carbon emission target", "renewable energy capacity", "ESG rating", "sustainability initiative", "BRSR indicator", "water consumption figure", "climate risk category"],
    "ttl_class": "quarterly",
    "typical_queries": ["What are the ESG initiatives?", "What is the carbon emission reduction target?", "How is Adani addressing climate change?"],
    "time_sensitivity": "medium"
  }
}
```

**Resulting `meta.json` for `SEBI_Master_Circular_MF_2024.pdf`** (different document, different profile):
```json
{
  "domain_profile": {
    "document_type": "sebi_regulatory_circular",
    "primary_domain": "mutual fund regulation",
    "secondary_domains": ["SEBI compliance", "AMC governance"],
    "key_themes": ["scheme categorization", "investment limits", "disclosure requirements", "exit load", "AMFI guidelines"],
    "key_entities": ["SEBI", "AMFI", "AMC", "mutual fund"],
    "key_metrics": ["investment limit percentage", "expense ratio cap", "minimum investment amount"],
    "ner_labels": ["SEBI circular reference", "regulatory deadline", "fund category", "compliance requirement", "investment limit percentage", "exit load value"],
    "ttl_class": "static",
    "typical_queries": ["What is the categorization rule?", "What are the investment limits?", "What did SEBI circular say about?"],
    "time_sensitivity": "low"
  }
}
```

---

## Component 4: Updated `query_classifier.py`

The classifier now uses the registry for domain classification — no more hardcoded domain lists:

```python
"""
query_classifier.py (updated)
===============================
Two classification dimensions:
  1. query_type   — HOW the query needs to be answered (aggregation/comparison/lookup/open)
  2. domain       — WHAT the query is about (discovered from corpus, not hardcoded)
"""
from __future__ import annotations
import re
import config
import llm_text_client

# ── Query type patterns (unchanged — these are structural, not domain-specific) ──
AGGREGATION_PATTERNS  = re.compile(r"\b(total|combined|sum|across all|aggregate|how many|cumulative)\b", re.I)
COMPARISON_PATTERNS   = re.compile(r"\b(compare|versus|vs\.?|difference between|which.*more|relative to)\b", re.I)
TEMPORAL_PATTERNS     = re.compile(r"\b(chang|evolv|difference)\b.{0,40}\b(between|from)\b", re.I)
LOOKUP_PATTERNS       = re.compile(r"\b(who (manages|holds|is)|what is the (benchmark|exit load|isin|nav|aum))\b", re.I)


def classify_query(query: str) -> str:
    """Classify query type (unchanged logic)."""
    if AGGREGATION_PATTERNS.search(query): return "aggregation"
    if COMPARISON_PATTERNS.search(query) or TEMPORAL_PATTERNS.search(query): return "comparison"
    if LOOKUP_PATTERNS.search(query): return "direct_lookup"

    result = llm_text_client.call_llm(
        _CLASSIFY_PROMPT.format(query=query),
        model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=10
    )
    result = (result or "").strip().lower()
    return result if result in ("aggregation", "comparison", "direct_lookup", "open_ended") else "open_ended"


def classify_domain(query: str, query_vec=None) -> tuple[str, float]:
    """
    Classify query domain using the corpus-driven registry.
    Returns (domain_name, confidence_score).
    Replaces all hardcoded domain pattern dicts.
    """
    from domain_registry import get_registry
    registry = get_registry()
    return registry.classify_domain(query, query_vec)


def classify_full(query: str, query_vec=None) -> dict:
    """
    Single call that returns both dimensions + intent_key.
    Used by retrieval.py as the single classification entry point.
    """
    query_type = classify_query(query)
    domain, domain_confidence = classify_domain(query, query_vec)
    return {
        "query_type":         query_type,
        "domain":             domain,
        "domain_confidence":  domain_confidence,
        "intent_key":         f"{query_type}::{domain}",
    }
```

---

## Component 5: Updated `intent_cache.py`

The cache now delegates all domain logic to the registry:

```python
# Key changes in IntentAwareCache:

def lookup(self, query_vec, query_type, domain, registry=None):
    intent_key = f"{query_type}::{domain}"
    
    # Get threshold from registry (dynamic, based on doc's time_sensitivity)
    if registry:
        threshold = registry.get_cache_threshold(domain, query_type)
    else:
        threshold = BASE_CACHE_THRESHOLDS.get(query_type, 0.90)
    
    # ... cosine similarity check against threshold ...

def store(self, ..., domain, registry=None):
    # Get TTL from registry (based on document type, not hardcoded)
    if registry:
        ttl = registry.get_ttl(domain)
    else:
        ttl = 86400  # 1 day default
    ...
```

---

## Component 6: Updated `ner_pipeline.py`

```python
def layer_b_gliner(text: str, domain: str = None) -> list:
    """GLiNER extraction with corpus-driven label routing."""
    model = _get_gliner()
    
    if domain:
        from domain_registry import get_registry
        labels = get_registry().get_gliner_labels(domain)
    else:
        labels = config.GLINER_LABELS   # fallback to global defaults
    
    raw = model.predict_entities(text, labels, threshold=config.GLINER_THRESHOLD)
    ...

def run_layers_ab(text: str, domain: str = None, skip_gliner: bool = False) -> list:
    # Pass domain through to GLiNER for label routing
    if should_run_gliner:
        ents += layer_b_gliner(text, domain=domain)
    ...
```

---

## Component 7: Updated `retrieval.py` Integration Point

The single entry point that wires everything together:

```python
def hybrid_graphrag(query: str, store) -> dict:
    t_start = time.perf_counter()
    
    # ── STEP 0A: Embed query once (reused for cache + graph + vector) ────
    query_vec = fs._embed_texts([query])

    # ── STEP 0B: Full intent classification (query_type + domain) ────────
    from query_classifier import classify_full
    from domain_registry import get_registry
    registry = get_registry()
    
    intent = classify_full(query, query_vec)
    query_type   = intent["query_type"]
    domain       = intent["domain"]
    intent_key   = intent["intent_key"]
    
    # ── STEP 0C: Cache lookup (dual-gate: similarity + intent_key) ────────
    cache = ic.get_cache()
    cached = cache.lookup(query_vec, query_type, domain, registry=registry)
    if cached:
        return _build_cached_response(cached, query, ...)

    # ── STEP 1: NER with domain-routed GLiNER labels ──────────────────────
    query_entities = ner_pipeline.run_layers_ab(query, domain=domain)
    
    # ── STEP 2: Graph + Vector (parallel, intent-controlled depth) ────────
    hops  = {aggregation: 2, comparison: 2, direct_lookup: 1, open_ended: 1}[query_type]
    top_k = {aggregation: 3, comparison: 4, direct_lookup: 2, open_ended: 6}[query_type]
    # ... parallel retrieval ...
    
    # ── STEP 3: Prompt (dynamic, domain-driven template) ──────────────────
    preamble = registry.get_prompt_preamble(domain, query_type)
    prompt = f"{preamble}\n\n{extra_sections}{graph_section}\nDOCUMENT PROSE:\n{vector_context}\n\nQUESTION: {query}\n\nANSWER:"
    
    # ── STEP 4: Confidence calibration (actual graph coverage) ────────────
    graph_coverage = registry.get_graph_coverage(domain)
    confidence = _calibrate_confidence(raw_confidence, graph_coverage)
    
    # ── STEP 5: Store in cache ────────────────────────────────────────────
    cache.store(..., domain=domain, registry=registry)
    
    # ── STEP 6: Audit log with full intent fingerprint ────────────────────
    log_query_audit({
        ...,
        "domain":            domain,
        "domain_confidence": intent["domain_confidence"],
        "intent_key":        intent_key,
        "gliner_labels_used": registry.get_gliner_labels(domain),
        "cache_threshold":   registry.get_cache_threshold(domain, query_type),
        "graph_coverage":    graph_coverage,
    })
```

---

## Data Flow: Adani ESG vs SEBI Circular (Same System, Fully Dynamic)

```
Query A: "What are the key ESG initiatives for climate change?"
  │
  ├─ classify_full() → query_type="open_ended", domain="ESG sustainability", confidence=0.87
  ├─ cache.lookup() threshold = registry.get_cache_threshold("ESG sustainability", "open_ended") = 0.88
  ├─ GLiNER labels = ["carbon emission target", "renewable energy capacity", "ESG rating", ...] ← from Adani meta.json
  ├─ prompt_preamble = "You are synthesizing from esg_sustainability_report docs covering
  │                     climate change adaptation, renewable energy, water management..."
  ├─ cache.store() TTL = registry.get_ttl("ESG sustainability") = 7 days (quarterly TTL)
  └─ confidence = "medium" (graph_coverage=0.12 for ESG domain → downgraded from high)

Query B: "What is the SEBI rule on mutual fund categorization?"
  │
  ├─ classify_full() → query_type="direct_lookup", domain="mutual fund regulation", confidence=0.91
  ├─ cache.lookup() threshold = registry.get_cache_threshold("mutual fund regulation", "direct_lookup") = 0.93 (low sensitivity → 0.96-0.03=0.93)
  ├─ GLiNER labels = ["SEBI circular reference", "fund category", "compliance requirement", ...] ← from SEBI meta.json
  ├─ prompt_preamble = "You are answering a specific factual question from a sebi_regulatory_circular document.
  │                     Give the answer in ONE sentence..."
  ├─ cache.store() TTL = registry.get_ttl("mutual fund regulation") = 30 days (static TTL)
  └─ confidence = "high" (graph_coverage=0.78 for regulatory domain → maintained)
```

---

## Implementation Phases

```
Phase 1 — Core Registry (1 day):
  ✅ domain_profiler.py (new file)
  ✅ domain_registry.py (new file)
  ✅ faiss_store.py — add domain_profile to meta.json write

Phase 2 — Integration (1 day):
  ✅ query_classifier.py — add classify_domain() using registry
  ✅ ner_pipeline.py — pass domain to layer_b_gliner()
  ✅ retrieval.py — wire registry into hybrid_graphrag()
  ✅ intent_cache.py — delegate TTL + threshold to registry

Phase 3 — Profiling Existing Documents (3–4 hours):
  ✅ Run profile_document() on all existing 10 documents
  ✅ Write domain_profile into their meta.json files
  ✅ Call registry.build_from_corpus() and inspect output

Phase 4 — Graph Coverage + Analytics (1 day):
  ✅ Enable measure_graph_coverage=True in startup build
  ✅ Surface domain registry stats in Analytics tab
  ✅ Show per-domain cache hit rates, coverage scores
```

---

## What Happens When You Add a New Document Type

You add a credit rating report from CRISIL. Previously: edit Python files.  
With this architecture:

```
1. build_faiss_index_for_pdf("CRISIL_Adani_Rating_2025.pdf")
2. domain_profiler.profile_document() → LLM extracts:
     document_type = "credit_rating_report"
     primary_domain = "credit rating"
     key_themes = ["credit rating methodology", "debt analysis", "rating outlook"]
     ner_labels = ["credit rating grade", "debt-to-equity ratio", "rating outlook", ...]
     ttl_class = "monthly"
3. Saved to meta.json["domain_profile"]
4. Next Streamlit restart → registry.build_from_corpus()
     → new domain "credit rating" appears automatically
     → GLiNER labels for credit rating queries now route correctly
     → cache TTL = 30 days (monthly class)
     → prompt preamble references "credit_rating_report" document type
5. Zero code changes required
```

---

## Open Questions for Review

1. **Re-profiling cadence**: Should `profile_document()` run on every `force_rebuild=True`, or only on first build? Re-profiling is useful when a document is replaced with a newer version.

2. **Domain granularity**: Should "ESG sustainability" and "corporate governance" be separate domains (as they are now) or merged? For Adani's ESG report, both apply — should the system handle overlapping domains in the cache key?

3. **Registry refresh trigger**: Currently the registry rebuilds at Streamlit startup. Should it also refresh when a new document is indexed mid-session (e.g., user uploads a PDF in the Upload tab)?

4. **Profiling cost**: Each `profile_document()` call is 1 Haiku LLM call (~300 tokens input, ~200 tokens output, ~$0.0004). For 50 documents, profiling costs ~$0.02 total. Is this acceptable? (It's a one-time cost per document.)
