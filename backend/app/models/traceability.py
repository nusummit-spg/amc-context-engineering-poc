# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS3 — Traceability schema: bidirectional test-to-document chain.

Industry-grade taxonomy systems require full auditability: every generated
test case or compliance finding must be traceable back to the exact document,
section, page, and block that produced the underlying fact or rule.

TraceabilityChain models this source_chain:
  finding_id -> fact/rule_id -> section_id -> page_num -> document_id

Use cases:
  - Regulatory audit: "Show me the source for this test case"
  - Gap analysis: "Which sections have no test coverage?"
  - Conflict investigation: "Why did two documents produce conflicting facts?"
  - Coverage reporting: fact/rule coverage ratio per document
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SourceLink(BaseModel):
    """A single link in the traceability chain: one source artifact."""
    artifact_type: Literal["fact", "rule", "entity", "relationship", "chunk"]
    artifact_id:   str
    # Document provenance
    document_id:   str
    document_name: Optional[str] = None
    section_id:    Optional[str] = None
    section_title: Optional[str] = None
    page_num:      Optional[int] = None
    block_id:      Optional[str] = None
    # Evidence
    evidence_text: Optional[str] = None   # verbatim text snippet
    confidence:    float         = 1.0


class TraceabilityChain(BaseModel):
    """Full source chain from a finding/test back to its document evidence.

    A single finding (test case, compliance flag, variance report) may
    draw from multiple source artifacts across multiple documents.

    Source chain structure:
      finding_id -> [SourceLink, ...] -> document(s)

    Persist this alongside every generated test case and compliance finding.
    """
    chain_id:     str             = Field(default_factory=lambda: str(uuid4()))
    finding_id:   str             # ID of the test case, variance, or compliance flag
    finding_type: Literal[
        "test_case",
        "compliance_finding",
        "context_variance",
        "entity_conflict",
    ]
    # Ordered list of source artifacts (most specific first)
    sources:      list[SourceLink] = Field(default_factory=list)
    created_at:   datetime         = Field(default_factory=datetime.utcnow)
    metadata:     dict[str, Any]   = Field(default_factory=dict)

    @property
    def document_ids(self) -> list[str]:
        """All unique document IDs in this chain."""
        seen: set[str] = set()
        return [s.document_id for s in self.sources
                if s.document_id not in seen and not seen.add(s.document_id)]  # type: ignore

    @property
    def page_references(self) -> list[dict]:
        """Human-readable page references for reporting."""
        refs = []
        for s in self.sources:
            ref: dict[str, Any] = {"artifact_type": s.artifact_type}
            if s.document_name:
                ref["document"] = s.document_name
            if s.page_num:
                ref["page"] = s.page_num
            if s.section_title:
                ref["section"] = s.section_title
            refs.append(ref)
        return refs

    def summary_text(self) -> str:
        """One-line human-readable summary of the chain."""
        refs = self.page_references
        if not refs:
            return f"finding:{self.finding_id} (no source links)"
        ref_str = "; ".join(
            f"{r.get('document', 'unknown')} p.{r.get('page', '?')} [{r.get('section', '')}]"
            for r in refs[:3]
        )
        suffix = f" +{len(refs)-3} more" if len(refs) > 3 else ""
        return f"finding:{self.finding_id} <- {ref_str}{suffix}"


class CoverageReport(BaseModel):
    """Coverage report for a document: which sections/facts have findings."""
    document_id:   str
    document_name: Optional[str] = None

    # Section-level coverage
    total_sections:    int   = 0
    covered_sections:  int   = 0   # sections with at least one source link
    section_coverage:  float = 0.0

    # Fact/rule-level coverage
    total_facts:   int   = 0
    covered_facts: int   = 0   # facts referenced in at least one chain
    fact_coverage: float = 0.0

    total_rules:   int   = 0
    covered_rules: int   = 0
    rule_coverage: float = 0.0

    # Uncovered sections (for gap analysis)
    uncovered_section_ids:    list[str] = Field(default_factory=list)
    uncovered_section_titles: list[str] = Field(default_factory=list)

    @classmethod
    def compute(
        cls,
        document_id: str,
        document_name: Optional[str],
        section_ids: list[str],
        section_titles: list[str],
        fact_ids: list[str],
        rule_ids: list[str],
        chains: list[TraceabilityChain],
    ) -> "CoverageReport":
        """Compute coverage ratios from a set of traceability chains."""
        covered_sections: set[str] = set()
        covered_facts:    set[str] = set()
        covered_rules:    set[str] = set()

        for chain in chains:
            for src in chain.sources:
                if src.document_id != document_id:
                    continue
                if src.section_id:
                    covered_sections.add(src.section_id)
                if src.artifact_type == "fact" and src.artifact_id:
                    covered_facts.add(src.artifact_id)
                if src.artifact_type == "rule" and src.artifact_id:
                    covered_rules.add(src.artifact_id)

        total_s = len(section_ids)
        total_f = len(fact_ids)
        total_r = len(rule_ids)

        uncovered_s_ids = [sid for sid in section_ids if sid not in covered_sections]
        uncovered_s_titles = [
            section_titles[i] for i, sid in enumerate(section_ids)
            if sid in uncovered_s_ids and i < len(section_titles)
        ]

        return cls(
            document_id=document_id,
            document_name=document_name,
            total_sections=total_s,
            covered_sections=len(covered_sections),
            section_coverage=round(len(covered_sections) / max(1, total_s), 4),
            total_facts=total_f,
            covered_facts=len(covered_facts),
            fact_coverage=round(len(covered_facts) / max(1, total_f), 4),
            total_rules=total_r,
            covered_rules=len(covered_rules),
            rule_coverage=round(len(covered_rules) / max(1, total_r), 4),
            uncovered_section_ids=uncovered_s_ids,
            uncovered_section_titles=uncovered_s_titles,
        )


def build_fact_chain(
    finding_id: str,
    finding_type: Literal["test_case", "compliance_finding", "context_variance", "entity_conflict"],
    fact: Any,   # DocumentFact
    document: Any,  # Document
) -> TraceabilityChain:
    """Build a TraceabilityChain from a DocumentFact.

    Args:
        finding_id:   ID of the finding/test that references this fact.
        finding_type: Type of the finding.
        fact:         A DocumentFact instance.
        document:     The source Document.

    Returns:
        TraceabilityChain with one SourceLink pointing to the fact.
    """
    section_title: Optional[str] = None
    if fact.section_id and hasattr(document, "sections"):
        for sec in document.sections:
            if sec.section_id == fact.section_id:
                section_title = sec.title
                break

    return TraceabilityChain(
        finding_id=finding_id,
        finding_type=finding_type,
        sources=[
            SourceLink(
                artifact_type="fact",
                artifact_id=fact.fact_id,
                document_id=fact.document_id,
                document_name=getattr(document, "title", None) or getattr(document, "filename", None),
                section_id=fact.section_id,
                section_title=section_title,
                page_num=fact.page_num,
                block_id=fact.block_id,
                evidence_text=fact.evidence_text[:300] if fact.evidence_text else None,
                confidence=fact.confidence,
            )
        ],
    )


def build_rule_chain(
    finding_id: str,
    finding_type: Literal["test_case", "compliance_finding", "context_variance", "entity_conflict"],
    rule: Any,   # DocumentRule
    document: Any,  # Document
) -> TraceabilityChain:
    """Build a TraceabilityChain from a DocumentRule."""
    section_title: Optional[str] = None
    if rule.section_id and hasattr(document, "sections"):
        for sec in document.sections:
            if sec.section_id == rule.section_id:
                section_title = sec.title
                break

    return TraceabilityChain(
        finding_id=finding_id,
        finding_type=finding_type,
        sources=[
            SourceLink(
                artifact_type="rule",
                artifact_id=rule.rule_id,
                document_id=rule.document_id,
                document_name=getattr(document, "title", None) or getattr(document, "filename", None),
                section_id=rule.section_id,
                section_title=section_title,
                page_num=rule.page_num,
                block_id=rule.block_id,
                evidence_text=rule.evidence_text[:300] if rule.evidence_text else None,
                confidence=rule.confidence,
            )
        ],
    )
