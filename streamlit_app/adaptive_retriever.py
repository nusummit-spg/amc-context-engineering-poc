# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
AMC Context Engineering — Agentic Core: Adaptive Retriever
Executes multi-round self-correcting retrieval (max 3 rounds) with entity coverage and gap feedback loops.
"""

import time
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import ner_pipeline
import faiss_store


@dataclass
class QualityAssessment:
    is_sufficient: bool
    coverage_score: float
    feedback: str


class AdaptiveRetriever:
    MAX_ROUNDS = 2

    def assess_quality(self, query: str, hits: List[Dict[str, Any]]) -> QualityAssessment:
        """Heuristic context sufficiency check — zero LLM overhead."""
        if not hits:
            return QualityAssessment(is_sufficient=False, coverage_score=0.0, feedback="No hits retrieved")

        query_entities = set(e["text"].lower() for e in ner_pipeline.run_layers_ab(query))
        if not query_entities:
            return QualityAssessment(is_sufficient=True, coverage_score=1.0, feedback="Generic query, hits accepted")

        combined_text = " ".join((h.get("parent_text") or h.get("child_text") or "").lower() for h in hits)
        covered = sum(1 for e in query_entities if e in combined_text)
        coverage = covered / max(len(query_entities), 1)

        is_sufficient = coverage >= 0.5
        feedback = "sufficient" if is_sufficient else f"Low entity coverage ({coverage:.1%})"
        return QualityAssessment(is_sufficient=is_sufficient, coverage_score=coverage, feedback=feedback)

    def execute_adaptive_retrieval(self, query: str, store, top_k: int = 5) -> Tuple[List[Dict[str, Any]], int, QualityAssessment]:
        """Executes adaptive multi-round retrieval if initial round has low entity coverage."""
        round_num = 1
        hits = store.retrieve(query, top_k_children=top_k)
        quality = self.assess_quality(query, hits)

        if not quality.is_sufficient and round_num < self.MAX_ROUNDS:
            round_num += 1
            # Round 2: Expanded retrieval with top_k * 2
            expanded_hits = store.retrieve(query, top_k_children=top_k * 2)
            if len(expanded_hits) > len(hits):
                hits = expanded_hits
                quality = self.assess_quality(query, hits)

        return hits, round_num, quality
