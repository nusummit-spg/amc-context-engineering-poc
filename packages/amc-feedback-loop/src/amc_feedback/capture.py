"""
Passive follow-up feedback capture coordinator.
"""
from typing import Any, Dict, Optional
from .config import FeedbackConfig
from .schemas import FollowUpDetectionRequest, FollowUpDetectionResponse

class FeedbackCapture:
    def __init__(self, feedback_loop: Any):
        self.loop = feedback_loop

    async def detect_follow_up(self, request: FollowUpDetectionRequest) -> FollowUpDetectionResponse:
        claim = await self.loop.process_feedback(
            session_id=request.session_id,
            response_id=request.previous_response_id,
            feedback_text=request.follow_up_query,
            original_query=request.original_query,
            original_response=request.original_response,
            source="passive_follow_up"
        )

        if claim:
            return FollowUpDetectionResponse(
                is_correction=True,
                confidence=claim.confidence,
                reasons=["User query refutes earlier turn assertion"],
                structured_claim=claim
            )

        return FollowUpDetectionResponse(
            is_correction=False,
            confidence=0.0,
            reasons=["No contradictory fact claim detected"],
            structured_claim=None
        )
