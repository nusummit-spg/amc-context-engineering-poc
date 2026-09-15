# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/feedback_quality.py
===========================
Pydantic schema for FeedbackQualityMetrics (16 fields).
Assesses individual feedback quality and signal reliability for the feedback loop.
"""

from pydantic import BaseModel, Field


class FeedbackQualityMetrics(BaseModel):
    """
    Schema for FeedbackQualityMetrics to assess and score human and automated feedback.
    Node type in Neo4j with indices on feedback_id, priority_tier.
    """
    quality_id: str = Field(..., description="Unique identifier for feedback quality evaluation")
    feedback_id: str = Field(..., description="Foreign key linking to specific Feedback record ID")
    response_id: str = Field(..., description="Foreign key linking to evaluated Response ID")
    detail_score: float = Field(..., ge=0.0, le=1.0, description="Granularity and depth of feedback commentary (0-1)")
    clarity_score: float = Field(..., ge=0.0, le=1.0, description="Clarity and unambiguous nature of feedback (0-1)")
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Completeness of problem specification (0-1)")
    reviewer_credibility_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Historical accuracy/credibility weight of the reviewer (0-1)")
    actionability_score: float = Field(..., ge=0.0, le=1.0, description="How directly actionable the feedback is for engineering repair (0-1)")
    is_actionable: bool = Field(default=True, description="Whether feedback contains sufficient information to execute a repair")
    action_difficulty: str = Field(default="MEDIUM", description="Estimated repair complexity: LOW, MEDIUM, HIGH")
    has_reproduction_steps: bool = Field(default=False, description="Whether feedback contains steps to reproduce failure")
    inter_reviewer_agreement_pct: float = Field(default=100.0, ge=0.0, le=100.0, description="Agreement percentage across multiple annotators")
    signal_quality_score: float = Field(..., ge=0.0, le=1.0, description="Composite signal strength metric combining clarity, detail, and credibility")
    is_duplicate_feedback: bool = Field(default=False, description="Whether feedback matches an existing active cluster")
    review_confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Reviewer self-reported or inferred certainty score (0-1)")
    priority_tier: str = Field(default="P2", description="Priority ranking for triage: P0 (Critical/Regulatory), P1 (High), P2 (Medium), P3 (Low)")
    evaluated_at: str = Field(..., description="ISO 8601 evaluation timestamp")

