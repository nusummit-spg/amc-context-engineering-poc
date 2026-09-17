# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
review_queue.py
===============
Pydantic schemas for the Human Review Queue and Escalation subsystem.
Implements Task 0.1 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class ReviewReason(str, Enum):
    CONFIDENCE_LOW = "confidence_low"
    HALLUCINATION_DETECTED = "hallucination_detected"
    FACTUAL_ERROR = "factual_error"
    COMPLIANCE_VIOLATION = "compliance_violation"
    USER_FLAGGED = "user_flagged"
    INCOMPLETE_ANSWER = "incomplete_answer"


class Verdict(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CORRECT = "partially_correct"
    NEEDS_CORRECTION = "needs_correction"
    AMBIGUOUS = "ambiguous"


class ReviewQueueItem(BaseModel):
    """Core review queue entity representing a low-confidence or flagged answer."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    response_id: str = Field(..., description="ID of the synthesized query response")
    query: str = Field(..., description="Original user prompt or query")
    user_answer: str = Field(..., description="Generated answer presented or held from user")
    reason: ReviewReason = Field(default=ReviewReason.CONFIDENCE_LOW)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    priority: int = Field(default=5, ge=1, le=10, description="1 (Urgent/Critical) to 10 (Low)")
    status: ReviewStatus = Field(default=ReviewStatus.PENDING)
    assigned_to: Optional[str] = Field(default=None, description="Username or ID of assigned reviewer")
    verdict: Optional[str] = Field(default=None, description="Resolution verdict")
    notes: Optional[str] = Field(default=None, description="Reviewer comments and notes")
    rejection_reason: Optional[str] = Field(default=None)
    rejected_by: Optional[str] = Field(default=None)
    rejected_at: Optional[datetime] = Field(default=None)
    resolved_by: Optional[str] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)



class EscalateRequest(BaseModel):
    response_id: str
    query: str
    user_answer: str
    reason: ReviewReason = ReviewReason.CONFIDENCE_LOW
    confidence_score: float = 0.5
    priority: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class AssignRequest(BaseModel):
    user_id: str


class ApproveRequest(BaseModel):
    verdict: str = "confirmed"  # confirmed, partially_correct, needs_correction
    notes: Optional[str] = ""


class RejectRequest(BaseModel):
    reason: str


class ReviewQueueStats(BaseModel):
    time_range_days: int
    total_items: int
    pending_count: int
    approved_count: int
    rejected_count: int
    in_review_count: int
    by_reason: Dict[str, int] = Field(default_factory=dict)
    average_resolution_time_seconds: float = 0.0
