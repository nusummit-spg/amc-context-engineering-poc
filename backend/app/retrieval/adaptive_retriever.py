# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
adaptive_retriever.py
=====================
Adaptive Multi-Round Retriever.
Executes self-correcting Round 2 retrieval with relaxed thresholds,
entity variation expansions, and deduplication.
Implements Task 1.1 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("app.retrieval.adaptive")


class AdaptiveRetriever:
    """Orchestrates multi-round retrieval when initial passes fail sufficiency gates."""

    def __init__(self, vector_store: Optional[Any] = None, graph_store: Optional[Any] = None):
        self.vector_store = vector_store
        self.graph_store = graph_store

    def generate_entity_variations(self, entities: List[str]) -> List[str]:
        """Generate domain synonym variations for query expansion."""
        variations: List[str] = []
        for ent in entities:
            ent_clean = ent.strip()
            ent_lower = ent_clean.lower()
            if "fund" in ent_lower and "scheme" not in ent_lower:
                variations.append(f"{ent_clean} mutual fund scheme")
            if "amc" in ent_lower:
                variations.append(f"{ent_clean} asset management company")
            if "sebi" in ent_lower:
                variations.append("SEBI circulars and regulations")
            if "nav" in ent_lower:
                variations.append("net asset value")
            if "aum" in ent_lower:
                variations.append("assets under management")
        return variations

    async def retrieve_round2(
        self,
        query: str,
        hyde_doc: str = "",
        plan: Optional[Any] = None,
        top_k: int = 10,
        intent: Optional[Any] = None,
        resolved_entities: Optional[List[str]] = None,
        original_threshold: float = 0.45,
        relaxed_threshold: float = 0.30,
    ) -> List[Any]:
        """
        Execute Round 2 retrieval with relaxed similarity floor and expanded query permutations.
        """
        resolved_entities = resolved_entities or []
        logger.info(
            "Executing Round 2 adaptive retrieval: relaxing threshold %.2f -> %.2f (top_k=%d)",
            original_threshold,
            relaxed_threshold,
            top_k * 2,
        )

        search_query = query
        if hyde_doc:
            search_query = f"{query}\n\nHYPOTHETICAL DOCUMENT:\n{hyde_doc}"

        candidates: List[Any] = []

        # 1. Relaxed Vector Search
        if self.vector_store is not None and hasattr(self.vector_store, "search"):
            try:
                res = await self.vector_store.search(
                    search_query,
                    top_k=top_k * 2,
                    similarity_threshold=relaxed_threshold,
                )
                if res:
                    candidates.extend(res)
            except TypeError:
                # Store signature might not take similarity_threshold
                res = await self.vector_store.search(search_query, top_k=top_k * 2)
                if res:
                    candidates.extend(res)
            except Exception as exc:
                logger.warning("Vector search in Round 2 notice: %s", exc)

        # 2. Entity variation expansion
        variations = self.generate_entity_variations(resolved_entities)
        for var in variations[:2]:  # cap at 2 expansions to keep low latency
            if self.vector_store is not None and hasattr(self.vector_store, "search"):
                try:
                    var_hits = await self.vector_store.search(f"{query} {var}", top_k=3)
                    if var_hits:
                        candidates.extend(var_hits)
                except Exception:
                    pass

        # 3. Deduplication by ID or text snippet
        seen_keys: Set[str] = set()
        deduped: List[Any] = []

        for item in candidates:
            item_id = None
            if hasattr(item, "id"):
                item_id = str(item.id)
            elif isinstance(item, dict) and "id" in item:
                item_id = str(item["id"])
            elif hasattr(item, "document_id"):
                item_id = f"{item.document_id}_{getattr(item, 'chunk_index', 0)}"
            elif isinstance(item, dict):
                item_id = f"{item.get('document_id', '')}_{item.get('chunk_index', '')}"

            if not item_id:
                # Fallback to text hash
                txt = item.text if hasattr(item, "text") else (item.get("text") or "")
                item_id = str(hash(txt[:80]))

            if item_id not in seen_keys:
                seen_keys.add(item_id)
                deduped.append(item)

        logger.info("Round 2 adaptive retrieval gathered %d unique chunks", len(deduped))
        return deduped
