"""
streamlit_app.intent_cache
==========================
Intent-aware caching system for the AMC Context Engine.
Provides domain-partitioned caching with TTL, fingerprint-based retrieval,
and semantic cosine lookup.

Features:
- Intent classification for domain partitioning
- Date entity guards to prevent stale data hits
- TTL expiration per domain
- Savings ledger for token/cost tracking
- Disk persistence support
"""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_PATTERNS: Dict[str, List[str]] = {
    "sebi_regulation": [
        "sebi", "circular", "master circular", "regulation", "amendment",
        "guideline", "notification", "press release", "faq",
    ],
    "esg_sustainability": [
        "brsr", "esg", "sustainability", "carbon", "emission", "net zero",
        "decarbonization", "climate", "renewable", "green",
    ],
    "financial_performance": [
        "ebitda", "revenue", "profit", "loss", "debt", "leverage",
        "quarter", "q1", "q2", "q3", "q4", "fy", "financial",
    ],
    "fund_performance": [
        "expense ratio", "ter", "nav", "return", "yield", "exit load",
        "entry load", "benchmark", "performance", "fund",
    ],
    "corporate_governance": [
        "principal officer", "audit committee", "board", "governance",
        "compliance", "erp", "fiu-ind", "internal auditor",
    ],
}

DOMAIN_TTL: Dict[str, int] = {
    "sebi_regulation": 604800,      # 7 days
    "esg_sustainability": 2592000,  # 30 days
    "financial_performance": 2592000,  # 30 days
    "fund_performance": 604800,     # 7 days
    "corporate_governance": 604800,  # 7 days
}

CACHE_THRESHOLD_BY_INTENT: Dict[str, float] = {
    "sebi_regulation": 0.85,
    "esg_sustainability": 0.85,
    "financial_performance": 0.80,
    "fund_performance": 0.80,
    "corporate_governance": 0.80,
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CacheEntry:
    """A single cache entry with metadata."""
    query_vec: np.ndarray
    query_type: str
    domain_intent: str
    query_text: str
    answer: str
    provenance: List[Dict[str, Any]]
    confidence_label: str
    confidence_reason: str
    total_tokens: int
    created_at: float = field(default_factory=time.time)
    input_tokens_cold: Optional[int] = None
    output_tokens_cold: Optional[int] = None
    graph_nodes: Optional[List[str]] = None
    graph_edges: Optional[List[Dict[str, Any]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "query_vec": self.query_vec.tolist() if isinstance(self.query_vec, np.ndarray) else self.query_vec,
            "query_type": self.query_type,
            "domain_intent": self.domain_intent,
            "query_text": self.query_text,
            "answer": self.answer,
            "provenance": self.provenance,
            "confidence_label": self.confidence_label,
            "confidence_reason": self.confidence_reason,
            "total_tokens": self.total_tokens,
            "created_at": self.created_at,
            "input_tokens_cold": self.input_tokens_cold,
            "output_tokens_cold": self.output_tokens_cold,
            "graph_nodes": self.graph_nodes,
            "graph_edges": self.graph_edges,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        """Create CacheEntry from dictionary."""
        data = data.copy()
        if isinstance(data.get("query_vec"), list):
            data["query_vec"] = np.array(data["query_vec"], dtype=np.float32)
        return cls(**data)


@dataclass
class CacheHit:
    """Result of a cache lookup."""
    answer: str
    provenance: List[Dict[str, Any]]
    confidence_label: str
    confidence_reason: str
    total_tokens: int
    created_at: float


class IntentAwareCache:
    """Intent-aware cache with domain partitioning and TTL support."""
    
    def __init__(
        self,
        shadow_mode: bool = False,
        disk_path: Optional[str] = None,
        default_ttl: Optional[int] = None,
    ):
        """Initialize the intent cache.
        
        Args:
            shadow_mode: If True, don't write to disk or modify cache
            disk_path: Optional path for disk persistence
            default_ttl: Default TTL in seconds (uses DOMAIN_TTL if None)
        """
        self.shadow_mode = shadow_mode
        self.disk_path = Path(disk_path) if disk_path else None
        self.default_ttl = default_ttl
        
        # In-memory storage
        self._entries_by_domain: Dict[str, List[CacheEntry]] = {}
        self._fingerprint_index: Dict[str, CacheEntry] = {}  # hash -> entry
        
        # Load from disk if exists
        if self.disk_path and self.disk_path.exists() and not shadow_mode:
            self._load_from_disk()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Core Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def store(
        self,
        query_vec: np.ndarray,
        query_type: str,
        domain_intent: str,
        query_text: str,
        answer: str,
        provenance: List[Dict[str, Any]],
        confidence_label: str,
        confidence_reason: str,
        total_tokens: int,
        input_tokens_cold: Optional[int] = None,
        output_tokens_cold: Optional[int] = None,
        graph_nodes: Optional[List[str]] = None,
        graph_edges: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Store a new cache entry.
        
        Args:
            query_vec: Embedding vector
            query_type: Type of query (direct_lookup, comparison, etc.)
            domain_intent: Classified domain intent
            query_text: Original query text
            answer: Cached answer
            provenance: Source references
            confidence_label: Confidence level label
            confidence_reason: Confidence reason
            total_tokens: Total tokens used
            input_tokens_cold: Input tokens for cold start
            output_tokens_cold: Output tokens for cold start
            graph_nodes: Graph nodes used
            graph_edges: Graph edges used
        """
        if self.shadow_mode:
            return
        
        # Create entry
        entry = CacheEntry(
            query_vec=query_vec,
            query_type=query_type,
            domain_intent=domain_intent,
            query_text=query_text,
            answer=answer,
            provenance=provenance,
            confidence_label=confidence_label,
            confidence_reason=confidence_reason,
            total_tokens=total_tokens,
            input_tokens_cold=input_tokens_cold,
            output_tokens_cold=output_tokens_cold,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
        )
        
        # Add to domain bucket
        if domain_intent not in self._entries_by_domain:
            self._entries_by_domain[domain_intent] = []
        self._entries_by_domain[domain_intent].append(entry)
        
        # Index by fingerprint
        fp = self._compute_fingerprint(query_text, query_type, domain_intent)
        self._fingerprint_index[fp] = entry
        
        # Persist to disk
        self._save_to_disk()
    
    def lookup(
        self,
        query_vec: np.ndarray,
        query_type: str,
        domain_intent: str,
        query_text: str,
        threshold: Optional[float] = None,
    ) -> Optional[CacheHit]:
        """Look up a cache entry using fingerprint and semantic lookup.
        
        Args:
            query_vec: Query embedding vector
            query_type: Type of query
            domain_intent: Domain intent
            query_text: Query text
            threshold: Semantic similarity threshold (uses default if None)
            
        Returns:
            CacheHit if found, None otherwise
        """
        # Step 1: Try fingerprint probe (exact/historical match)
        hit = self.fingerprint_probe(query_text, query_type, domain_intent)
        if hit:
            return hit
        
        # Step 2: Semantic lookup (if vector provided)
        if query_vec is not None and domain_intent in self._entries_by_domain:
            threshold = threshold or CACHE_THRESHOLD_BY_INTENT.get(
                domain_intent, 0.85
            )
            best_hit = None
            best_score = threshold
            
            for entry in self._entries_by_domain[domain_intent]:
                score = self._cosine_similarity(query_vec, entry.query_vec)
                if score >= best_score:
                    best_score = score
                    best_hit = entry
            
            if best_hit and not self._is_expired(best_hit):
                return CacheHit(
                    answer=best_hit.answer,
                    provenance=best_hit.provenance,
                    confidence_label=best_hit.confidence_label,
                    confidence_reason=best_hit.confidence_reason,
                    total_tokens=best_hit.total_tokens,
                    created_at=best_hit.created_at,
                )
        
        return None
    
    def fingerprint_probe(
        self,
        query_text: str,
        query_type: Optional[str] = None,
        domain_intent: Optional[str] = None,
    ) -> Optional[CacheHit]:
        """Probe cache using fingerprint only (no vector comparison).
        
        Args:
            query_text: Query text to probe
            query_type: Optional query type filter
            domain_intent: Optional domain intent filter
            
        Returns:
            CacheHit if found, None otherwise
        """
        fp = self._compute_fingerprint(query_text, query_type, domain_intent)
        entry = self._fingerprint_index.get(fp)
        
        if entry and not self._is_expired(entry):
            return CacheHit(
                answer=entry.answer,
                provenance=entry.provenance,
                confidence_label=entry.confidence_label,
                confidence_reason=entry.confidence_reason,
                total_tokens=entry.total_tokens,
                created_at=entry.created_at,
            )
        
        return None
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if entry has expired based on its domain TTL."""
        ttl = DOMAIN_TTL.get(entry.domain_intent, self.default_ttl or 604800)
        return (time.time() - entry.created_at) > ttl
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))
    
    def _compute_fingerprint(
        self,
        query_text: str,
        query_type: Optional[str],
        domain_intent: Optional[str],
    ) -> str:
        """Compute fingerprint for query text."""
        key_parts = [query_text.lower().strip()]
        if query_type:
            key_parts.append(query_type)
        if domain_intent:
            key_parts.append(domain_intent)
        combined = "|".join(key_parts)
        return hashlib.md5(combined.encode()).hexdigest()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def clear_all(self) -> None:
        """Clear all cache entries and reset state."""
        self._entries_by_domain.clear()
        self._fingerprint_index.clear()
        if self.disk_path and not self.shadow_mode:
            self._save_to_disk()
    
    def invalidate_domain(self, domain_intent: str) -> None:
        """Invalidate all entries for a specific domain."""
        if domain_intent in self._entries_by_domain:
            del self._entries_by_domain[domain_intent]
        
        # Remove fingerprint index entries for this domain
        to_remove = [
            fp for fp, entry in self._fingerprint_index.items()
            if entry.domain_intent == domain_intent
        ]
        for fp in to_remove:
            del self._fingerprint_index[fp]
        
        if self.disk_path and not self.shadow_mode:
            self._save_to_disk()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = sum(len(entries) for entries in self._entries_by_domain.values())
        
        return {
            "total_entries": total_entries,
            "buckets": {k: len(v) for k, v in self._entries_by_domain.items()},
            "fingerprint_index_size": len(self._fingerprint_index),
            "shadow_mode": self.shadow_mode,
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # Persistence Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        if not self.disk_path:
            return
        
        self.disk_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "entries": {
                domain: [entry.to_dict() for entry in entries]
                for domain, entries in self._entries_by_domain.items()
            },
            "fingerprint_index": {
                fp: entry.to_dict()
                for fp, entry in self._fingerprint_index.items()
            },
            "saved_at": time.time(),
        }
        
        with open(self.disk_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if not self.disk_path or not self.disk_path.exists():
            return
        
        try:
            with open(self.disk_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Load entries
            for domain, entries_data in data.get("entries", {}).items():
                self._entries_by_domain[domain] = [
                    CacheEntry.from_dict(e) for e in entries_data
                ]
            
            # Load fingerprint index
            for fp, entry_data in data.get("fingerprint_index", {}).items():
                self._fingerprint_index[fp] = CacheEntry.from_dict(entry_data)
        
        except (json.JSONDecodeError, IOError):
            # Corrupted file, start fresh
            self._entries_by_domain.clear()
            self._fingerprint_index.clear()


class SavingsLedger:
    """Ledger for tracking cache hit savings (tokens, cost, CO2)."""
    
    def __init__(self, disk_path: Optional[str] = None):
        """Initialize the savings ledger.
        
        Args:
            disk_path: Optional path for disk persistence
        """
        self.disk_path = Path(disk_path) if disk_path else None
        
        # In-memory counters
        self.total_hits = 0
        self.total_misses = 0
        self.tokens_saved_cumulative = 0
        self.cost_saved_cumulative_usd = 0.0
        self.co2_saved_grams = 0.0
    
    def record_hit(self, tokens_saved: int, cost_usd: float) -> None:
        """Record a cache hit.
        
        Args:
            tokens_saved: Number of tokens saved by using cache
            cost_usd: Cost in USD that was saved
        """
        self.total_hits += 1
        self.tokens_saved_cumulative += tokens_saved
        self.cost_saved_cumulative_usd += cost_usd
        # Approximate: 1 token ≈ 0.0002g CO2
        self.co2_saved_grams += tokens_saved * 0.0002
        
        if self.disk_path:
            self._save_to_disk()
    
    def record_miss(self) -> None:
        """Record a cache miss."""
        self.total_misses += 1
        
        if self.disk_path:
            self._save_to_disk()
    
    def summary(self) -> Dict[str, Any]:
        """Get ledger summary."""
        total = self.total_hits + self.total_misses
        hit_rate = (self.total_hits / total * 100) if total > 0 else 0.0
        
        return {
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "hit_rate_pct": hit_rate,
            "tokens_saved_cumulative": self.tokens_saved_cumulative,
            "cost_saved_cumulative_usd": self.cost_saved_cumulative_usd,
            "co2_saved_grams": self.co2_saved_grams,
        }
    
    def _save_to_disk(self) -> None:
        """Save ledger to disk."""
        if not self.disk_path:
            return
        
        self.disk_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "tokens_saved_cumulative": self.tokens_saved_cumulative,
            "cost_saved_cumulative_usd": self.cost_saved_cumulative_usd,
            "co2_saved_grams": self.co2_saved_grams,
            "last_updated": time.time(),
        }
        
        with open(self.disk_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Intent Classification Functions
# ─────────────────────────────────────────────────────────────────────────────

def classify_domain_intent(query_text: str) -> str:
    """Classify the domain intent of a query.
    
    Args:
        query_text: Query text to classify
        
    Returns:
        Domain intent category
    """
    query_lower = query_text.lower()
    
    # Score each domain
    scores: Dict[str, int] = {domain: 0 for domain in DOMAIN_PATTERNS}
    
    for domain, patterns in DOMAIN_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in query_lower:
                scores[domain] += 1
    
    # Return domain with highest score
    if scores:
        best_domain = max(scores, key=scores.get)
        if scores[best_domain] > 0:
            return best_domain
    
    # Default fallback
    return "sebi_regulation"


def _extract_date_entities(text: str) -> List[str]:
    """Extract date entities from text.
    
    Args:
        text: Input text
        
    Returns:
        List of extracted date entities (quarters, dates, etc.)
    """
    date_patterns = [
        # Quarter patterns: Q1 FY24, Q2 2023, etc.
        r'(?:Q[1-4]\s*FY?\s*\d{2,4})',
        r'(?:FY\s*\d{2,4})',
        # Date patterns
        r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*',
        r'\d{4}-\d{2}-\d{2}',
        # Year patterns
        r'\b(?:20\d{2})\b',
    ]
    
    dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dates.extend(matches)
    
    return dates


# ─────────────────────────────────────────────────────────────────────────────
# Module-level Cache Instance
# ─────────────────────────────────────────────────────────────────────────────

_global_cache: Optional[IntentAwareCache] = None


def get_cache() -> IntentAwareCache:
    """Get the global intent cache instance.
    
    Returns:
        Global IntentAwareCache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = IntentAwareCache()
    return _global_cache


# ─────────────────────────────────────────────────────────────────────────────
# Backward compatibility aliases
# ─────────────────────────────────────────────────────────────────────────────

IntentCache = IntentAwareCache
get_global_cache = get_cache
