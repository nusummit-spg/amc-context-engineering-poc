"""Feedback API schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    response_id: UUID
    session_id: UUID
    user_id: UUID | None = None

    rating: str
    feedback_type: str

    entity_name: str | None = None
    entity_type: str | None = None

    notes: str | None = Field(
        default=None,
        max_length=2000,
    )

    corrections: dict[str, Any] | None = None

    timestamp: datetime | None = None


class FeedbackResponse(BaseModel):
    feedback_id: UUID
    response_id: UUID
    session_id: UUID
    message: str
