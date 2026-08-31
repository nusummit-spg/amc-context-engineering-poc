"""Feedback API routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import FeedbackRecord
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from uuid import UUID


router = APIRouter(
    prefix="/feedback",
    tags=["feedback"],
)


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_feedback(
    feedback: FeedbackRequest,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    """
    Store user feedback.

    Duplicate feedback from the same session is rejected if another
    feedback record exists within the previous five minutes.
    """

    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    five_minutes_ago = now - timedelta(minutes=5)

    duplicate = db.scalar(
        select(FeedbackRecord)
        .where(
            FeedbackRecord.session_id == str(feedback.session_id),
            FeedbackRecord.timestamp >= five_minutes_ago,
        )
        .order_by(FeedbackRecord.timestamp.desc())
    )

    if duplicate is not None:
        # For now, simply return the existing feedback ID.
        # We can change this to a 409 Conflict later if required.
        return FeedbackResponse(
            feedback_id=UUID(duplicate.feedback_id),
            response_id=UUID(duplicate.response_id),
            session_id=UUID(duplicate.session_id),
            message="Feedback already recorded for this session recently.",
        )

    # ------------------------------------------------------------------
    # Create database record
    # ------------------------------------------------------------------

    record = FeedbackRecord(
        response_id=str(feedback.response_id),
        session_id=str(feedback.session_id),
        user_id=str(feedback.user_id) if feedback.user_id else None,
        rating=feedback.rating,
        feedback_type=feedback.feedback_type,
        entity_name=feedback.entity_name,
        entity_type=feedback.entity_type,
        notes=feedback.notes,
        corrections=feedback.corrections,
        timestamp=feedback.timestamp or now,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return FeedbackResponse(
        feedback_id=UUID(record.feedback_id),
        response_id=UUID(record.response_id),
        session_id=UUID(record.session_id),
        message="Feedback recorded successfully.",
    )
