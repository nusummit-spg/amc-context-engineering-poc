# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/response_quality.py
===========================
Pydantic schema for ResponseQualityMetrics (20 fields).
Aggregates reviewer and automated feedback into holistic response quality scores.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ResponseQualityMetrics(BaseModel):
    """
    Schema for ResponseQualityMetrics aggregating feedback to quantify overall response performance.
    Node type in Neo4j with indices on response_id, llm_model, retrieval_mode.
    """
    response_quality_id: str = Field(..., description="Unique identifier for response quality record")
    response_id: str = Field(..., description="Foreign key linking to specific QueryResponse ID")
    llm_model: str = Field(..., description="LLM model used for synthesis (e.g. gpt-oss-120b, groq-light)")
    retrieval_mode: str = Field(..., description="Serving pipeline mode: traditional, contextgraph, hybrid")
    query_type: str = Field(..., description="Classified intent/query type: compliance_check, direct_lookup, etc.")
    total_feedback_count: int = Field(default=0, ge=0, description="Total feedback submissions received for this response")
    positive_feedback_count: int = Field(default=0, ge=0, description="Count of positive / approval ratings")
    negative_feedback_count: int = Field(default=0, ge=0, description="Count of defect or dispute reports")
    overall_quality_score: float = Field(..., ge=0.0, le=1.0, description="Composite score (0-1) across accuracy, clarity, and compliance")
    accuracy_score: float = Field(..., ge=0.0, le=1.0, description="Factual and numerical accuracy rating (0-1)")
    clarity_score: float = Field(..., ge=0.0, le=1.0, description="Tone, structure, and readability rating (0-1)")
    compliance_risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Evaluated regulatory compliance risk level (0=clean, 1=critical breach)")
    inter_reviewer_agreement_pct: float = Field(default=100.0, ge=0.0, le=100.0, description="Inter-annotator agreement rate across reviews")
    failure_categories: List[str] = Field(default_factory=list, description="All failure taxonomy codes flagged for this response")
    most_common_failure_category: Optional[str] = Field(default=None, description="Dominant failure code if multiple issues reported")
    response_improved: bool = Field(default=False, description="Whether self-healing or re-synthesis yielded a better answer")
    comparable_traditional_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Baseline score under Traditional Vector RAG")
    comparable_contextgraph_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Performance score under ContextGraph pipeline")
    mode_performance_delta: Optional[float] = Field(default=None, description="Score delta (ContextGraph score - Traditional score)")
    top_k_used: int = Field(default=5, ge=1, description="Number of context passages/candidates utilized in prompt")
    top_k_optimal: Optional[int] = Field(default=None, ge=1, description="Optimal candidate k identified via retrospective retrieval analysis")


