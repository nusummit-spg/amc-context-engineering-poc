# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unified Provenance, Citation, and Metric Schemas (Implementation Plan §2.1).

Defines Pydantic models for:
- SourceChunk: guaranteed page_number, page_label, document_name, full verbatim_text
- Citation: marker ("1", "16") + SourceChunk
- MetricProvenance: numeric claims with explanation, formula, inputs, assumption basis
- UnifiedLLMAnswer: structured answer with citations and metric claims
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SourceChunk(BaseModel):
    """Guaranteed provenance chunk carrying document details, page numbers, and full verbatim text."""
    chunk_id: str = Field(description="Internal identifier for telemetry/debugging")
    document_id: str = Field(description="Stable document identifier or filename")
    document_name: str = Field(description="Human-readable document name for display")
    page_number: Optional[int] = Field(default=None, description="Primary 1-indexed page number")
    page_label: Optional[str] = Field(default=None, description="Formatted page string, e.g. '16' or '16-17'")
    section_heading: Optional[str] = Field(default=None, description="Section heading or clause title")
    verbatim_text: str = Field(description="Full untruncated source text")
    source_url: Optional[str] = Field(default=None, description="Direct URL or PDF route anchor")
    local_doc_path: Optional[str] = Field(default=None, description="Local filepath or viewer URI")
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    score: Optional[float] = None


class Citation(BaseModel):
    """Citation marker embedded in the synthesized answer mapped to its source chunk."""
    marker: str = Field(description="Marker number or key, e.g. '1', '16'")
    source: SourceChunk


class MetricProvenance(BaseModel):
    """Provenance for a numeric figure or metric claim in the synthesized answer."""
    marker: str = Field(description="Unique metric identifier, e.g. 'm1'")
    surface_text: str = Field(description="Exact substring as it appears in the answer, e.g. '20% of Net Assets'")
    value: Optional[str] = Field(default=None, description="Normalized numeric value, e.g. '20%'")
    provenance_type: Literal["verbatim", "computed", "assumed"] = Field(
        default="verbatim",
        description="Whether number is quoted directly from source, computed by formula, or based on assumption"
    )
    explanation: str = Field(description="Human-readable justification explaining the provenance of the number")
    supporting_citation_markers: List[str] = Field(
        default_factory=list,
        description="List of citation markers supporting this metric (e.g. ['1', '2'])"
    )
    formula: Optional[str] = Field(default=None, description="Arithmetic formula or equation if computed")
    inputs_used: Optional[Dict[str, str]] = Field(default=None, description="Named inputs and definitions used")
    assumption_basis: Optional[str] = Field(default=None, description="Basis or reasoning if assumed")


class UnifiedLLMAnswer(BaseModel):
    """Unified synthesized answer carrying inline markdown citations, sources, and metric annotations."""
    answer_markdown: str = Field(description="Synthesized markdown with [[cite:N]] and [[metric:mX]] tokens")
    citations: List[Citation] = Field(default_factory=list)
    metrics: List[MetricProvenance] = Field(default_factory=list)
    retrieval_mode: Optional[str] = None
