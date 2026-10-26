"""Data models and database schemas for feedback."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


VALID_CODES = {f"F{i:02d}" for i in range(1, 13)}


class FeedbackIn(BaseModel):
    response_id: str = Field(..., min_length=1, description="Ties feedback to exact ContextGraph answer")
    interaction_id: str = Field(..., min_length=1, description="Interaction or conversation ID")
    session_id: str = Field(..., min_length=1, description="Session ID")
    turn_number: int = Field(..., ge=1, description="1-indexed turn number in session")
    query_text: Optional[str] = Field(default=None, max_length=2000, description="Question asked by user")
    actor_id: Optional[str] = Field(default=None, max_length=200, description="Reviewer / user identifier")
    actor_role: Optional[str] = Field(default="Compliance & Regulatory Officer", max_length=200)
    selected_categories: list[str] = Field(default_factory=list, description="Array of failure taxonomy codes F01-F12")
    feedback_text: Optional[str] = Field(default=None, max_length=2000, description="Reviewer commentary")
    client_timestamp: Optional[str] = Field(default=None, description="ISO timestamp from client")

    @field_validator("selected_categories")
    @classmethod
    def validate_codes(cls, v: list[str]) -> list[str]:
        """Validate validate codes field.

        Args:
            v (list[str]): The v.

        Returns:
            list[str]: List of resulting items or records.
        """
        cleaned = [c.strip().upper() for c in v if c and c.strip()]
        bad = set(cleaned) - VALID_CODES
        if bad:
            raise ValueError(f"Unknown failure category codes: {sorted(bad)}. Allowed: {sorted(VALID_CODES)}")
        return cleaned


class FeedbackOut(BaseModel):
    feedback_id: str
    response_id: str
    stored_at: str
    status: str = "recorded"
    priority_tier: Optional[str] = None
    signal_quality_score: Optional[float] = None
    issue_id: Optional[str] = None
    issue_status: Optional[str] = None
    was_matched_to_existing_issue: Optional[bool] = False
    match_type: Optional[str] = None


class CategoryBreakdownItem(BaseModel):
    code: str
    label: str
    count: int


class FeedbackStatusCheckResponse(BaseModel):
    has_existing_issue: bool
    issue_id: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    match_type: Optional[str] = None
    similarity_score: Optional[float] = None
    contributor_count: Optional[int] = None
    category_breakdown: Optional[list[CategoryBreakdownItem]] = None
    cached: Optional[bool] = False



class PendingFeedbackNotice(BaseModel):
    has_pending_feedback: bool = True
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Semantic similarity score (0.0 - 1.0)")
    original_query_text: Optional[str] = Field(default=None, description="Original query text (admin only)")
    feedback_submitted_at: Optional[str] = Field(default=None, description="ISO timestamp when original feedback was submitted")
    feedback_categories: list[str] = Field(default_factory=list, description="Taxonomy categories reported")
    repair_lifecycle_status: str = Field(default="open", description="Lifecycle status: open, diagnosing")
    match_count: int = Field(default=1, ge=1, description="Number of matching feedback entries with pending repairs")
    suppressed_by_cache_clear: bool = Field(default=False, description="True if suppressed due to intent cache clear")


class IssueRepairTransitionRequest(BaseModel):
    actor_id: Optional[str] = Field(default=None, description="Reviewer or triage actor initiating repair")
    metadata: Optional[dict] = Field(default=None, description="Optional extra triage metadata")


class IssueRepairTransitionResponse(BaseModel):
    issue_id: str
    repair_task_id: Optional[str] = None
    status: str
    task_created: bool
    reused: bool
    message: str


class IssueStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Target status: reported, under_review, in_repair, resolved, closed, reopened")
    resolution_notes: Optional[str] = Field(default=None, description="Resolution or closing justification")
    actor_id: Optional[str] = Field(default=None, description="Actor initiating transition")


class FeedbackIssueDetailOut(BaseModel):
    issue_id: str
    canonical_query_text: str
    query_hash: str
    status: str
    repair_task_id: Optional[str] = None
    contributor_count: int
    primary_entities: list[str] = Field(default_factory=list)
    taxonomy_paths: list[str] = Field(default_factory=list)
    tenant_id: Optional[str] = None
    created_at: str
    updated_at: str
    resolution_notes: Optional[str] = None
    linked_feedback_count: int = 0
    linked_feedback_ids: list[str] = Field(default_factory=list)


class FeedbackIssueListOut(BaseModel):
    total: int
    page: Optional[int] = 1
    page_size: Optional[int] = 50
    total_pages: Optional[int] = 1
    items: list[FeedbackIssueDetailOut]


class MyFeedbackItemOut(BaseModel):
    issue_id: str
    canonical_query_text: str
    status: str
    repair_task_id: Optional[str] = None
    also_reported_by_count: int = 0
    primary_entities: list[str] = Field(default_factory=list)
    taxonomy_paths: list[str] = Field(default_factory=list)
    user_reported_categories: list[str] = Field(default_factory=list)
    user_feedback_count: int = 1
    user_feedback_texts: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class MyFeedbackListOut(BaseModel):
    total: int
    page: Optional[int] = 1
    page_size: Optional[int] = 50
    total_pages: Optional[int] = 1
    items: list[MyFeedbackItemOut]



