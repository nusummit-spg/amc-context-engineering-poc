# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
intent_cache.py
===============
Domain-Aware Semantic Query Cache with Dual-Gate Lookup, Date Entity Guards,
Per-Domain TTLs, and Reindex Bucket Invalidation.
"""
import os
import json
import re
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("intent_cache")


DOMAIN_PATTERNS = {
    "sebi_regulation": re.compile(
        r"\b(sebi|circular|master circular|categorization|rationalization|pmla|aml|cft|sif|reit|invit|distributor|lock-in|folio|nfo)\b", re.I
    ),
    "esg_sustainability": re.compile(
        r"\b(esg|sustainability|decarbonization|net zero|carbon|emissions|brsr|climate|water|green hydrogen|renewable)\b", re.I
    ),
    "financial_performance": re.compile(
        r"\b(ebitda|revenue|financial|quarter|q1|q2|q3|q4|fy23|fy24|fy25|credit rating|debt|leverage|aum|net worth)\b", re.I
    ),
    "fund_performance": re.compile(
        r"\b(fund|scheme|hybrid|exit load|asset allocation|ter|expense ratio|benchmark|nifty|flexicap|etf|elss)\b", re.I
    ),
    "corporate_governance": re.compile(
        r"\b(governance|erp|rating provider|audit|principal officer|board|compliance|fiu-ind)\b", re.I
    ),
}

CACHE_THRESHOLD_BY_INTENT = {
    "sebi_regulation": 0.94,
    "esg_sustainability": 0.92,
    "financial_performance": 0.93,
    "fund_performance": 0.95,
    "corporate_governance": 0.93,
}

DOMAIN_TTL = {
    "sebi_regulation": 86400 * 30,       # 30 days
    "esg_sustainability": 86400 * 14,     # 14 days
    "financial_performance": 86400 * 7,    # 7 days
    "fund_performance": 86400 * 7,         # 7 days
    "corporate_governance": 86400 * 14,    # 14 days
}

DATE_PATTERN = re.compile(r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|\d{4}|q[1-4]\s*fy\d{2})\b", re.I)


def classify_domain_intent(query: str) -> str:
    """Fast regex domain classifier.

    Args:
        query (str): Search query or input text.

    Returns:
        str: Resulting str instance.
    """
    for domain, pattern in DOMAIN_PATTERNS.items():
        if pattern.search(query):
            return domain
    return "sebi_regulation"  # default fallback domain


def _extract_date_entities(text: str) -> set[str]:
    """Extract date entities (e.g., '15 July', 'FY24', 'Q4') to guard direct_lookup cache hits.

    Args:
        text (str): Input text content.

    Returns:
        set[str]: List of resulting items or records.
    """
    matches = DATE_PATTERN.findall(text.lower())
    return set(m.strip() for m in matches)


import hashlib

@dataclass
class CacheEntry:
    query_vec: np.ndarray
    query_type: str
    domain_intent: str
    query_text: str
    answer: str
    provenance: List[Dict[str, Any]]
    confidence_label: str
    confidence_reason: str
    total_tokens: int
    input_tokens_cold: int = 0
    output_tokens_cold: int = 0
    graph_nodes: List[str] = field(default_factory=list)
    graph_edges: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    date_entities: set[str] = field(default_factory=set)
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None

    @property
    def graph_node_count(self) -> int:
        """Get graph node count property value.

        Returns:
            int: Resulting int instance.
        """
        return len(self.graph_nodes)


class IntentAwareCache:
    def __init__(self, shadow_mode: bool = False, disk_path: str = None):
        """Initialize a new instance of IntentAwareCache.

        Args:
            shadow_mode (bool): The shadow mode.
            disk_path (str): Filesystem path to the disk.
        """
        self.shadow_mode = shadow_mode
        backend_logs = Path(__file__).resolve().parent.parent.parent / "logs"
        self.disk_path = disk_path or str(backend_logs / "intent_cache_store.json")
        self._entries_by_domain: Dict[str, List[CacheEntry]] = {d: [] for d in DOMAIN_PATTERNS}
        self._fingerprint_index: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._load_from_disk()

    def _make_fingerprint_key(
        self,
        query_text: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> str:
        """Make fingerprint key.

        Args:
            query_text (str): The query text.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            str: Resulting str instance.
        """
        if user_id:
            from app.core.cache_utils import generate_cache_key
            return generate_cache_key(
                namespace="intent",
                key_components={"query": query_text.lower().strip()[:200]},
                user_id=user_id,
                tenant_id=tenant_id,
            )
        return hashlib.md5(query_text.lower().strip().encode()).hexdigest()

    def _update_fingerprint(self, entry: CacheEntry) -> None:
        """Update fingerprint.

        Args:
            entry (CacheEntry): The entry.
        """
        fp = self._make_fingerprint_key(entry.query_text, user_id=entry.user_id, tenant_id=entry.tenant_id)
        self._fingerprint_index[fp] = entry

    def _persist_to_disk(self) -> None:
        """Persist cache entries to disk so cache hits survive application restarts."""
        try:
            os.makedirs(Path(self.disk_path).parent, exist_ok=True)
            serializable = {}
            for domain, entries in self._entries_by_domain.items():
                serializable[domain] = [
                    {
                        "query_vec": e.query_vec.tolist(),
                        "query_type": e.query_type,
                        "domain_intent": e.domain_intent,
                        "query_text": e.query_text,
                        "answer": e.answer,
                        "provenance": e.provenance,
                        "confidence_label": e.confidence_label,
                        "confidence_reason": e.confidence_reason,
                        "total_tokens": e.total_tokens,
                        "input_tokens_cold": e.input_tokens_cold,
                        "output_tokens_cold": e.output_tokens_cold,
                        "graph_nodes": e.graph_nodes,
                        "graph_edges": e.graph_edges,
                        "created_at": e.created_at,
                        "date_entities": list(e.date_entities),
                        "user_id": e.user_id,
                        "tenant_id": e.tenant_id,
                    }
                    for e in entries
                ]
            with open(self.disk_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as exc:
            logger.warning("Could not persist IntentCache to disk: %s", exc)

    def _load_from_disk(self) -> None:
        """Load persisted cache entries from disk on startup."""
        if not os.path.exists(self.disk_path):
            return
        try:
            raw_text = None
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    with open(self.disk_path, "r", encoding=enc) as f:
                        raw_text = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            if not raw_text or raw_text.strip() in ("", "{}"):
                return
            raw_data = json.loads(raw_text)
            for domain, entries in raw_data.items():
                if domain not in self._entries_by_domain:
                    self._entries_by_domain[domain] = []
                for item in entries:
                    vec = np.array(item["query_vec"], dtype=np.float32)
                    norm_vec = vec / (np.linalg.norm(vec) + 1e-9)
                    entry = CacheEntry(
                        query_vec=norm_vec,
                        query_type=item["query_type"],
                        domain_intent=item["domain_intent"],
                        query_text=item["query_text"],
                        answer=item["answer"],
                        provenance=item["provenance"],
                        confidence_label=item["confidence_label"],
                        confidence_reason=item["confidence_reason"],
                        total_tokens=item["total_tokens"],
                        input_tokens_cold=item.get("input_tokens_cold", item.get("total_tokens", 0)),
                        output_tokens_cold=item.get("output_tokens_cold", 0),
                        graph_nodes=item.get("graph_nodes", []),
                        graph_edges=item.get("graph_edges", []),
                        created_at=item.get("created_at", time.time()),
                        date_entities=set(item.get("date_entities", [])),
                        user_id=item.get("user_id"),
                        tenant_id=item.get("tenant_id"),
                    )
                    self._entries_by_domain[domain].append(entry)
                    self._update_fingerprint(entry)
            print(f"  [IntentCache] Loaded persistent cache entries from disk ({self.disk_path}).", flush=True)
        except Exception as exc:
            logger.warning("Could not load IntentCache from disk: %s — resetting cache file.", exc)
            try:
                import pathlib
                pathlib.Path(self.disk_path).write_text("{}", encoding="utf-8")
            except Exception:
                pass



    def fingerprint_probe(
        self,
        query_text: str,
        query_type: str = "v2_dual_regime_taxonomy",
        domain_intent: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[CacheEntry]:
        """Stage 1: O(1) exact text fingerprint probe — avoids embedding computation entirely.

        Args:
            query_text (str): The query text.
            query_type (str): The query type.
            domain_intent (Optional[str]): The domain intent.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            Optional[CacheEntry]: Matching object or record if found, None otherwise.
        """
        fp = self._make_fingerprint_key(query_text, user_id=user_id, tenant_id=tenant_id)
        entry = self._fingerprint_index.get(fp)
        if not entry:
            return None
        if user_id and entry.user_id != user_id:
            return None
        if tenant_id and entry.tenant_id != tenant_id:
            return None
        if entry.query_type != query_type:
            return None
        if domain_intent and entry.domain_intent != domain_intent:
            return None
        query_dates = _extract_date_entities(query_text)
        if query_dates != entry.date_entities:
            return None
        now = time.time()
        ttl = DOMAIN_TTL.get(entry.domain_intent, 86400 * 7)
        if (now - entry.created_at) > ttl:
            return None

        self._hits += 1
        logger.info("IntentCache FINGERPRINT HIT for query: '%s'", query_text[:50])
        return entry

    def lookup(
        self,
        query_vec: np.ndarray,
        query_type: str,
        domain_intent: str,
        query_text: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[CacheEntry]:
        """Lookup.

        Args:
            query_vec (np.ndarray): The query vec.
            query_type (str): The query type.
            domain_intent (str): The domain intent.
            query_text (str): The query text.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            Optional[CacheEntry]: Matching object or record if found, None otherwise.
        """

        domain_entries = self._entries_by_domain.get(domain_intent, [])
        if not domain_entries:
            self._misses += 1
            return None

        # Clean expired entries
        now = time.time()
        ttl = DOMAIN_TTL.get(domain_intent, 86400 * 7)
        domain_entries = [e for e in domain_entries if (now - e.created_at) <= ttl]
        self._entries_by_domain[domain_intent] = domain_entries

        threshold = CACHE_THRESHOLD_BY_INTENT.get(domain_intent, 0.93)
        q_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)

        best_score = -1.0
        best_entry: Optional[CacheEntry] = None

        query_dates = _extract_date_entities(query_text)

        for entry in domain_entries:
            if user_id and entry.user_id != user_id:
                continue
            if tenant_id and entry.tenant_id != tenant_id:
                continue
            if entry.query_type != query_type:
                continue

            # Global Date Entity Guard: symmetric check — dates must match on BOTH sides
            if query_type == "direct_lookup":
                if query_dates != entry.date_entities:
                    continue
            elif query_dates and query_dates != entry.date_entities:
                continue

            sim = float(np.dot(q_norm.flatten(), entry.query_vec.flatten()))

            if sim > best_score:
                best_score = sim
                best_entry = entry

        if best_entry and best_score >= threshold:
            self._hits += 1
            logger.info("IntentCache HIT (score=%.3f >= %.2f) for query: '%s'", best_score, threshold, query_text[:50])
            if self.shadow_mode:
                print(f"  [IntentCache SHADOW HIT] score={best_score:.3f} | query='{query_text[:40]}'", flush=True)
                return None
            return best_entry

        self._misses += 1
        return None

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
        input_tokens_cold: int = 0,
        output_tokens_cold: int = 0,
        graph_nodes: List[str] = None,
        graph_edges: List[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Store.

        Args:
            query_vec (np.ndarray): The query vec.
            query_type (str): The query type.
            domain_intent (str): The domain intent.
            query_text (str): The query text.
            answer (str): The answer.
            provenance (List[Dict[str, Any]]): The provenance.
            confidence_label (str): The confidence label.
            confidence_reason (str): The confidence reason.
            total_tokens (int): Collection or list of total tokens.
            input_tokens_cold (int): The input tokens cold.
            output_tokens_cold (int): The output tokens cold.
            graph_nodes (List[str]): Collection or list of graph nodes.
            graph_edges (List[Dict[str, Any]]): Collection or list of graph edges.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
        """
        date_ents = _extract_date_entities(query_text)
        norm_vec = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        entry = CacheEntry(
            query_vec=norm_vec,
            query_type=query_type,
            domain_intent=domain_intent,
            query_text=query_text,
            answer=answer,
            provenance=provenance,
            confidence_label=confidence_label,
            confidence_reason=confidence_reason,
            total_tokens=total_tokens,
            input_tokens_cold=input_tokens_cold or total_tokens,
            output_tokens_cold=output_tokens_cold,
            graph_nodes=graph_nodes or [],
            graph_edges=graph_edges or [],
            date_entities=date_ents,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        if domain_intent not in self._entries_by_domain:
            self._entries_by_domain[domain_intent] = []
        self._entries_by_domain[domain_intent].append(entry)
        self._update_fingerprint(entry)
        self._persist_to_disk()

    def invalidate_user(self, user_id: str, tenant_id: Optional[str] = None) -> int:
        """Invalidate all cache entries for a specific user across domains and fingerprint index.

        Args:
            user_id (str): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            int: Resulting int instance.
        """
        if not user_id:
            return 0
        removed_count = 0
        for domain, entries in self._entries_by_domain.items():
            survivors = []
            for e in entries:
                match = (e.user_id == user_id)
                if match and tenant_id:
                    match = (e.tenant_id == tenant_id)
                if match:
                    removed_count += 1
                else:
                    survivors.append(e)
            self._entries_by_domain[domain] = survivors

        # Rebuild fingerprint index
        self._fingerprint_index = {
            self._make_fingerprint_key(e.query_text, user_id=e.user_id, tenant_id=e.tenant_id): e
            for entries in self._entries_by_domain.values()
            for e in entries
        }
        self._persist_to_disk()
        return removed_count

    def invalidate_domain(self, domain_intent: str) -> None:
        """Invalidate specific domain bucket on reindex events.

        Args:
            domain_intent (str): The domain intent.
        """
        if domain_intent in self._entries_by_domain:
            self._entries_by_domain[domain_intent].clear()
            self._persist_to_disk()
            print(f"  [IntentCache] Invalidated cache bucket for domain '{domain_intent}'.", flush=True)

    def clear_all(self) -> None:
        """Clear all cache buckets AND pending feedback index."""
        for d in self._entries_by_domain:
            self._entries_by_domain[d].clear()
        self._fingerprint_index.clear()
        self._clear_pending_feedback_cache()
        self._persist_to_disk()

        print("  [IntentCache] Cleared all cache buckets + pending feedback index.", flush=True)

    def _clear_pending_feedback_cache(self) -> None:
        """Invalidate pending feedback notice cache."""
        try:
            from app.feedback.intent_matcher import clear_pending_feedback_cache
            clear_pending_feedback_cache(suppress_prior_feedbacks=True)
            logger.info("Cleared pending feedback notice cache")
        except Exception as e:
            logger.warning(f"Failed to clear pending feedback cache: {e}")


    def stats(self) -> dict:
        """Stats.

        Returns:
            dict: Dictionary containing result data or status.
        """
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1), 3),
            "hit_rate_pct": round(self._hits / max(total, 1) * 100, 1),
            "buckets": {d: len(entries) for d, entries in self._entries_by_domain.items()},
        }


class SavingsLedger:
    def __init__(self, disk_path: str = None):
        """Initialize a new instance of SavingsLedger.

        Args:
            disk_path (str): Filesystem path to the disk.
        """
        backend_logs = Path(__file__).resolve().parent.parent.parent / "logs"
        self.disk_path = disk_path or str(backend_logs / "savings_ledger.json")
        self._data = self._load()

    def _load(self) -> dict:
        """Load operation.

        Returns:
            dict: Dictionary containing result data or status.
        """
        if os.path.exists(self.disk_path):
            try:
                with open(self.disk_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "total_hits": 0,
            "total_misses": 0,
            "tokens_saved_cumulative": 0,
            "cost_saved_cumulative_usd": 0.0,
            "co2_saved_grams": 0.0,
        }

    def _save(self) -> None:
        """Save operation.
        """
        try:
            os.makedirs(Path(self.disk_path).parent, exist_ok=True)
            with open(self.disk_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def record_hit(self, tokens_saved: int, cold_cost_usd: float = 0.0031) -> None:
        """Record hit.

        Args:
            tokens_saved (int): The tokens saved.
            cold_cost_usd (float): The cold cost usd.
        """
        self._data["total_hits"] += 1
        self._data["tokens_saved_cumulative"] += tokens_saved
        self._data["cost_saved_cumulative_usd"] = round(self._data["cost_saved_cumulative_usd"] + cold_cost_usd, 4)
        self._data["co2_saved_grams"] = round(self._data["co2_saved_grams"] + (tokens_saved * 0.0002), 2)
        self._save()

    def record_miss(self) -> None:
        """Record miss.
        """
        self._data["total_misses"] += 1
        self._save()

    def clear(self) -> None:
        """Clear.
        """
        self._data = {"total_hits": 0, "total_misses": 0, "tokens_saved_cumulative": 0, "cost_saved_cumulative_usd": 0.0, "co2_saved_grams": 0.0}
        self._save()

    def summary(self) -> dict:
        """Summary.

        Returns:
            dict: Dictionary containing result data or status.
        """
        total = self._data["total_hits"] + self._data["total_misses"]
        return {
            "total_hits": self._data["total_hits"],
            "total_misses": self._data["total_misses"],
            "hit_rate_pct": round(self._data["total_hits"] / max(total, 1) * 100, 1),
            "tokens_saved_cumulative": self._data["tokens_saved_cumulative"],
            "cost_saved_cumulative_usd": self._data["cost_saved_cumulative_usd"],
            "co2_saved_grams": self._data["co2_saved_grams"],
        }


_cache_instance: Optional[IntentAwareCache] = None
_savings_ledger_instance: Optional[SavingsLedger] = None


def get_cache() -> IntentAwareCache:
    """Retrieve cache.

    Returns:
        IntentAwareCache: Resulting IntentAwareCache instance.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = IntentAwareCache(shadow_mode=False)
    return _cache_instance


def get_savings_ledger() -> SavingsLedger:
    """Retrieve savings ledger.

    Returns:
        SavingsLedger: Resulting SavingsLedger instance.
    """
    global _savings_ledger_instance
    if _savings_ledger_instance is None:
        _savings_ledger_instance = SavingsLedger()
    return _savings_ledger_instance


def clear_cache() -> None:
    """Clear all in-memory and disk persistent cache entries."""
    get_cache().clear_all()


def invalidate_user_intent_cache(user_id: str, tenant_id: Optional[str] = None) -> int:
    """Invalidate all intent cache entries for a specific user.

    Args:
        user_id (str): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        int: Resulting int instance.
    """
    return get_cache().invalidate_user(user_id, tenant_id)

