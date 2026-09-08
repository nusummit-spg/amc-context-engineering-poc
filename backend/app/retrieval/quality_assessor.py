# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
quality_assessor.py
===================
Retrieval Quality Assessment module.
Assesses retrieval sufficiency, entity coverage, and knowledge gaps using fast heuristics.
Implements Task 1.1 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("app.retrieval.quality_assessor")


@dataclass
class QualityAssessment:
    """Outcome of retrieval quality evaluation."""
    is_sufficient: bool
    entity_coverage: float
    chunk_quality_avg: float
    rounds_used: int = 1
    feedback: str = ""
    has_error: bool = False
    error_message: str = ""


class RetrievalQualityAssessor:
    """Fast, deterministic heuristic-based retrieval quality evaluator."""

    @staticmethod
    def assess(
        chunks: List[Any],
        facts: Optional[List[Any]] = None,
        query: str = "",
        resolved_entities: Optional[Dict[str, str]] = None,
        min_chunks_threshold: int = 2,
        entity_coverage_threshold: float = 0.5,
        min_relevance_score: float = 0.40,
    ) -> QualityAssessment:
        """
        Evaluate if the retrieved candidate chunks and graph facts are sufficient
        to generate an accurate answer without triggering hallucinations.
        """
        facts = facts or []
        resolved_entities = resolved_entities or {}

        # Check 1: Minimum chunk count
        if len(chunks) < min_chunks_threshold and not facts:
            return QualityAssessment(
                is_sufficient=False,
                entity_coverage=0.0,
                chunk_quality_avg=0.0,
                feedback=f"Insufficient chunk count: {len(chunks)} < {min_chunks_threshold}",
            )

        # Check 2: Entity coverage
        query_entities = set(k.lower().strip() for k in resolved_entities.keys())
        entity_coverage = 1.0

        if query_entities:
            combined_texts = []
            for c in chunks:
                if hasattr(c, "text"):
                    combined_texts.append(c.text.lower())
                elif isinstance(c, dict):
                    combined_texts.append((c.get("text") or c.get("child_text") or c.get("parent_text") or "").lower())

            all_text = " ".join(combined_texts)
            covered_count = sum(1 for ent in query_entities if ent in all_text)
            entity_coverage = covered_count / len(query_entities)

            if entity_coverage < entity_coverage_threshold and len(facts) == 0:
                return QualityAssessment(
                    is_sufficient=False,
                    entity_coverage=entity_coverage,
                    chunk_quality_avg=0.0,
                    feedback=f"Low entity coverage: {entity_coverage:.1%} < {entity_coverage_threshold:.1%}",
                )

        # Check 3: Chunk relevance scores
        scores = []
        for c in chunks:
            if hasattr(c, "score"):
                scores.append(float(c.score))
            elif isinstance(c, dict) and "score" in c:
                scores.append(float(c["score"]))

        avg_score = (sum(scores) / len(scores)) if scores else 0.5

        if scores and avg_score < min_relevance_score and not facts:
            return QualityAssessment(
                is_sufficient=False,
                entity_coverage=entity_coverage,
                chunk_quality_avg=avg_score,
                feedback=f"Low relevance score average: {avg_score:.2f} < {min_relevance_score:.2f}",
            )

        # Check 4: Knowledge gap signals in retrieved text
        gap_phrases = ["not found", "no information available", "unknown parameter", "not specified"]
        all_content = " ".join(
            (c.text if hasattr(c, "text") else (c.get("text") or "")) for c in chunks
        ).lower()
        gap_count = sum(all_content.count(gp) for gp in gap_phrases)
        if gap_count >= 3:
            return QualityAssessment(
                is_sufficient=False,
                entity_coverage=entity_coverage,
                chunk_quality_avg=avg_score,
                feedback=f"Knowledge gap markers detected in retrieved content ({gap_count} occurrences)",
            )

        # Passed all checks
        return QualityAssessment(
            is_sufficient=True,
            entity_coverage=entity_coverage,
            chunk_quality_avg=avg_score,
            feedback="Retrieval context meets sufficiency criteria",
        )


def assess_retrieval_quality(
    chunks: List[Any],
    facts: Optional[List[Any]] = None,
    query: str = "",
    resolved_entities: Optional[Dict[str, str]] = None,
    **kwargs,
) -> QualityAssessment:
    """Convenience helper function for quality assessment."""
    return RetrievalQualityAssessor.assess(
        chunks=chunks,
        facts=facts,
        query=query,
        resolved_entities=resolved_entities,
        **kwargs,
    )
