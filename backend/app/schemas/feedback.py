# """Feedback API schemas."""

# from datetime import datetime
# from typing import Any
# from uuid import UUID

# from pydantic import BaseModel, ConfigDict, Field
# from app.core.models import FeedbackType, RatingType


# class FeedbackRequest(BaseModel):
#     response_id: UUID
#     session_id: UUID
#     user_id: UUID | None = None

#     rating: RatingType
#     feedback_type: FeedbackType

#     entity_name: str | None = None
#     entity_type: str | None = None

#     notes: str | None = Field(default=None, max_length=2000)
#     corrections: dict[str, Any] | None = None

#     timestamp: datetime | None = None


# class FeedbackResponse(BaseModel):
#     feedback_id: UUID
#     response_id: UUID
#     session_id: UUID
#     message: str


# # --- NEW: Step 1-6 pipeline output ---

# class EvaluationSummary(BaseModel):
#     model_config = ConfigDict(from_attributes=True)

#     id: int
#     session_id: str
#     response_id: str
#     entry_route: str
#     adjudication_verdict: str
#     adjudication_confidence: float | None
#     root_cause: str | None
#     severity: str | None
#     lifecycle_status: str
#     repair: bool
#     repair_target: str | None


# class FeedbackWithEvaluationResponse(FeedbackResponse):
#     evaluation: EvaluationSummary