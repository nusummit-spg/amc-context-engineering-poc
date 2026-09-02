"""
Feedback Collection API Endpoints.

Routes:
- POST /api/feedback — Record user feedback
- GET /api/feedback/{feedback_id} — Get feedback status
- GET /api/feedback/stats/daily — Dashboard statistics
- GET /api/feedback/stats/summary — Summary statistics

DESIGN:
- Feedback recording is non-blocking (writes to PostgreSQL)
- Status is immediately available
- No waiting for LLM evaluation
- Evaluation happens asynchronously via scheduler
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.api.deps import Container, get_container
from app.schemas.feedback import FeedbackRequest, FeedbackResponse, RatingType
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# ============================================================================
# ENDPOINT: Record Feedback
# ============================================================================

@router.post(
    "/",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record user feedback on query response",
    responses={
        201: {"description": "Feedback recorded successfully"},
        404: {"description": "Response ID not found"},
        422: {"description": "Invalid feedback data"}
    }
)
async def record_feedback(
    request: FeedbackRequest,
    container: Container = Depends(get_container)
) -> FeedbackResponse:
    """
    Record user feedback on a query response.
    
    **FLOW:**
    1. Validate response_id exists (< 24h old)
    2. Pre-classify feedback (NER, sentiment, intent)
    3. Store in PostgreSQL immediately (non-blocking)
    4. Return feedback_id
    
    **NO WAITING** on LLM evaluation — that happens via scheduled task.
    
    **Query Parameters:**
    - None (all data in request body)
    
    **Request Body:**
    - response_id: UUID of response being rated
    - session_id: Session context
    - rating: "positive" | "negative" | "neutral"
    - feedback_type: Type of issue (entity, relationship, missing, etc.)
    - entity_name: (optional) Specific entity being corrected
    - notes: (optional) Detailed feedback text
    - corrections: (optional) Proposed corrections
    
    **Example:**
    ```json
    {
        "response_id": "550e8400-e29b-41d4-a716-446655440000",
        "session_id": "550e8400-e29b-41d4-a716-446655440001",
        "user_id": "user123",
        "rating": "negative",
        "feedback_type": "entity_incorrect",
        "entity_name": "Axis Equity Direct",
        "entity_type": "Scheme",
        "notes": "This fund was liquidated in 2022, should not appear in results",
        "corrections": {
            "status": "liquidated",
            "date_closed": "2022-01-15"
        }
    }
    ```
    
    **Response:**
    ```json
    {
        "feedback_id": "550e8400-e29b-41d4-a716-446655440002",
        "status": "recorded",
        "evaluation_status": "pending",
        "recorded_at": "2024-01-19T10:30:00Z",
        "quality_score": 0.75
    }
    ```
    """
    
    try:
        logger.info(
            f"Received feedback: "
            f"type={request.feedback_type}, "
            f"rating={request.rating}"
        )
        
        # Collect feedback (validates, classifies, stores)
        feedback_result = await container.feedback_collector.collect_feedback(
            feedback_request=request
        )
        
        logger.info(
            f"Feedback {feedback_result['feedback_id']} recorded successfully "
            f"(quality_score={feedback_result['quality_score']:.2f})"
        )
        
        # Return response
        return FeedbackResponse(
            feedback_id=feedback_result['feedback_id'],
            status="recorded",
            evaluation_status="pending",
            recorded_at=feedback_result['recorded_at'],
            message="Feedback recorded successfully"
        )
    
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    
    except ValidationError as e:
        logger.warning(f"Invalid request data: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    
    except Exception as e:
        logger.error(f"Error recording feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback. Please try again later."
        )


# ============================================================================
# ENDPOINT: Get Feedback Status
# ============================================================================

@router.get(
    "/{feedback_id}",
    summary="Get evaluation status of feedback",
    responses={
        200: {"description": "Feedback status found"},
        404: {"description": "Feedback not found"}
    }
)
async def get_feedback_status(
    feedback_id: str,
    container: Container = Depends(get_container)
):
    """
    Get evaluation status of a feedback record.
    
    **Use this to check if feedback has been evaluated.**
    
    **Response:**
    ```json
    {
        "feedback_id": "550e8400-e29b-41d4-a716-446655440002",
        "evaluation_status": "pending",
        "created_at": "2024-01-19T10:30:00Z",
        "processed_at": null
    }
    ```
    
    Status values:
    - "pending" — Awaiting evaluation
    - "processed" — Evaluation complete, recommendations generated
    - "rejected" — Low quality feedback, no recommendations
    - "failed" — Error during evaluation
    """
    
    try:
        status_info = await container.feedback_db.get_feedback_status(feedback_id)
        
        if not status_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feedback {feedback_id} not found"
            )
        
        return status_info
    
    except Exception as e:
        logger.error(f"Error fetching feedback status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve feedback status"
        )


# ============================================================================
# ENDPOINT: Daily Statistics
# ============================================================================

@router.get(
    "/stats/daily",
    summary="Get daily feedback statistics",
    responses={200: {"description": "Daily statistics"}}
)
async def get_daily_stats(
    days: int = 7,
    container: Container = Depends(get_container)
):
    """
    Get aggregated feedback statistics by day.
    
    **Use this for dashboard/analytics.**
    
    **Query Parameters:**
    - days: Number of days to retrieve (default: 7)
    
    **Response:**
    ```json
    [
        {
            "date": "2024-01-19",
            "total_feedback": 42,
            "positive_feedback": 28,
            "negative_feedback": 14,
            "entity_corrections": 12,
            "avg_confidence_score": 0.78
        },
        ...
    ]
    ```
    
    **NOTE:** These are pre-computed metrics (not on-demand aggregations).
    Computed daily at 3 AM for performance.
    """
    
    try:
        # Validate input
        if days < 1 or days > 365:
            raise ValueError("days must be between 1 and 365")
        
        # Fetch pre-computed metrics
        stats = await container.feedback_db.get_daily_stats(days=days)
        
        return {
            "period_days": days,
            "statistics": stats
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except Exception as e:
        logger.error(f"Error fetching daily stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )


# ============================================================================
# ENDPOINT: Summary Statistics
# ============================================================================

@router.get(
    "/stats/summary",
    summary="Get summary feedback statistics",
    responses={200: {"description": "Summary statistics"}}
)
async def get_summary_stats(
    days: int = 7,
    container: Container = Depends(get_container)
):
    """
    Get high-level summary of feedback statistics.
    
    **Use this for dashboard KPIs.**
    
    **Query Parameters:**
    - days: Period to summarize (default: 7)
    
    **Response:**
    ```json
    {
        "period_days": 7,
        "total_feedback": 294,
        "positive_feedback": 205,
        "negative_feedback": 89,
        "positive_percentage": 69.7,
        "avg_quality_score": 0.76,
        "total_corrections_applied": 45,
        "trending_entities": [
            {"name": "Axis Growth", "count": 12},
            {"name": "HDFC Mid-Cap", "count": 8}
        ]
    }
    ```
    """
    
    try:
        # Validate input
        if days < 1 or days > 365:
            raise ValueError("days must be between 1 and 365")
        
        # Use aggregator to compute summary
        summary = await container.feedback_aggregator.get_feedback_summary(days=days)
        
        return summary
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except Exception as e:
        logger.error(f"Error fetching summary stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve summary statistics"
        )


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get(
    "/health",
    summary="Health check for feedback system",
    responses={200: {"description": "Feedback system is healthy"}}
)
async def health_check(
    container: Container = Depends(get_container)
):
    """
    Check if feedback system is operational.
    
    **Response:**
    ```json
    {
        "status": "healthy",
        "timestamp": "2024-01-19T10:30:00Z",
        "database_connected": true,
        "pending_feedback_count": 42,
        "pending_evaluations": 3
    }
    ```
    """
    
    try:
        # Check database connection
        pending = await container.feedback_db.fetch_pending_feedback(limit=1)
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "database_connected": True,
            "pending_feedback_count": 0,  # Would need aggregation query
            "pending_evaluations": 0  # Would need job query
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feedback system is unavailable"
        )
