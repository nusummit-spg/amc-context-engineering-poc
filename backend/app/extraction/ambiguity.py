# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Ambiguity detection and LLM gate for the ingestion pipeline.

Adapted from Agentic Testing Platform's quality gate design.
The gate analyzes extraction results and decides whether LLM calls
are warranted. This prevents wasteful LLM calls on clean documents.

Core principle:
  Deterministic extraction first.
  LLM called ONLY when ambiguity_count > 0 AND priority >= threshold.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

logger = logging.getLogger("extraction.ambiguity")


@dataclass
class EntityConflict:
    """Two entities of the same type with the same normalized_name but different properties."""
    entity_name: str
    entity_type: str
    conflicting_properties: list[dict[str, Any]] = field(default_factory=list)
    source_sections: list[str] = field(default_factory=list)
    priority: Literal["low", "medium", "high"] = "medium"


@dataclass
class AmbiguityReport:
    """Quality report produced by the ambiguity detector."""
    document_id: str
    # Entity-level signals
    total_entities: int = 0
    low_confidence_entities: int = 0   # confidence < 0.80
    entity_conflicts: list[EntityConflict] = field(default_factory=list)
    # Section-level coverage
    sections_covered: int = 0
    sections_total: int = 0
    coverage_ratio: float = 0.0
    # Gate decision
    eligible_for_llm: bool = False
    llm_priority: Literal["low", "medium", "high"] = "low"
    reason: str = ""

    @property
    def high_priority_conflicts(self) -> int:
        return sum(1 for c in self.entity_conflicts if c.priority == "high")

    @property
    def conflict_count(self) -> int:
        return len(self.entity_conflicts)


def detect_entity_conflicts(
    mentions: list,  # list[ExtractedMention] — avoid circular import
) -> list[EntityConflict]:
    """Detect entities with the same name but different properties across sections.
    
    This catches cases like an entity appearing as 'Issuer' in one section
    and 'IssuerGroup' in another, or conflicting property values.
    """
    from collections import defaultdict
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for m in mentions:
        key = (m.type, m.normalized_name.lower())
        groups[key].append(m)

    conflicts: list[EntityConflict] = []
    for (etype, ename), group in groups.items():
        if len(group) <= 1:
            continue
        # Compare property dicts — any difference is a potential conflict
        prop_sets = [frozenset((k, str(v)) for k, v in m.properties.items()) for m in group]
        unique_props = {frozenset(ps) for ps in prop_sets}
        if len(unique_props) > 1:
            priority = "high" if len(unique_props) > 2 else "medium"
            conflicts.append(EntityConflict(
                entity_name=ename,
                entity_type=etype,
                conflicting_properties=[dict(m.properties) for m in group[:5]],
                source_sections=[m.context[:100] for m in group[:5]],
                priority=priority,
            ))
    return conflicts


def compute_coverage_ratio(
    mentions: list,       # list[ExtractedMention]
    sections: list,       # list[Section]
) -> tuple[int, int, float]:
    """Compute what fraction of document sections have at least one entity mention.
    Returns (sections_covered, sections_total, ratio).
    """
    if not sections:
        return 0, 0, 0.0
    covered = 0
    for section in sections:
        section_text_lower = section.text.lower()
        for m in mentions:
            if m.normalized_name.lower() in section_text_lower or \
               m.surface_form.lower() in section_text_lower:
                covered += 1
                break
    total = len(sections)
    return covered, total, round(covered / total, 4)


def build_ambiguity_report(
    document_id: str,
    mentions: list,       # list[ExtractedMention]
    sections: list,       # list[Section]
    confidence_threshold: float = 0.80,
    coverage_threshold: float = 0.60,
) -> AmbiguityReport:
    """Build a full ambiguity report for a document's extraction results.
    
    The LLM gate fires when:
      - High-priority conflicts exist, OR
      - Too many low-confidence entities (> 20% of total), OR
      - Coverage ratio is below threshold (document has uncovered sections)
    """
    report = AmbiguityReport(document_id=document_id)

    # Entity counts
    report.total_entities = len(mentions)
    report.low_confidence_entities = sum(
        1 for m in mentions if getattr(m, "confidence", 0.85) < confidence_threshold
    )

    # Conflict detection
    report.entity_conflicts = detect_entity_conflicts(mentions)

    # Coverage
    covered, total, ratio = compute_coverage_ratio(mentions, sections)
    report.sections_covered = covered
    report.sections_total = total
    report.coverage_ratio = ratio

    # Gate decision
    high_conflicts = report.high_priority_conflicts
    low_conf_ratio = (
        report.low_confidence_entities / max(1, report.total_entities)
    )
    low_coverage = ratio < coverage_threshold and total > 2

    if high_conflicts > 0:
        report.eligible_for_llm = True
        report.llm_priority = "high"
        report.reason = f"{high_conflicts} high-priority entity conflicts detected."
    elif low_conf_ratio > 0.20:
        report.eligible_for_llm = True
        report.llm_priority = "medium"
        report.reason = (
            f"{report.low_confidence_entities}/{report.total_entities} entities "
            f"below confidence threshold {confidence_threshold}."
        )
    elif low_coverage:
        report.eligible_for_llm = True
        report.llm_priority = "medium"
        report.reason = (
            f"Document coverage ratio {ratio:.0%} below threshold {coverage_threshold:.0%}. "
            f"Only {covered}/{total} sections have entity mentions."
        )
    else:
        report.eligible_for_llm = False
        report.llm_priority = "low"
        report.reason = (
            f"Extraction quality is good: {report.total_entities} entities, "
            f"{ratio:.0%} section coverage, no high-priority conflicts."
        )

    logger.info(
        "Ambiguity report for %s: eligible=%s priority=%s — %s",
        document_id, report.eligible_for_llm, report.llm_priority, report.reason,
    )
    return report


def should_run_relationship_llm(
    report: AmbiguityReport,
    min_priority: Literal["low", "medium", "high"] = "medium",
) -> bool:
    """Decide whether the relationship LLM extractor should run for this document.
    
    Default: run LLM only when priority >= 'medium'.
    Setting min_priority='low' always runs LLM (old behavior).
    Setting min_priority='high' is the most conservative (cost-saving) mode.
    """
    if not report.eligible_for_llm:
        return False
    priority_rank = {"low": 0, "medium": 1, "high": 2}
    return priority_rank.get(report.llm_priority, 0) >= priority_rank.get(min_priority, 1)
