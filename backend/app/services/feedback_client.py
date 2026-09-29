"""
Client for Feedback Loop Service communication.
"""
import logging
from typing import Dict, List, Optional, Any

from .client_base import ServiceClient

logger = logging.getLogger("feedback_client")


class FeedbackServiceClient(ServiceClient):
    """
    Client for communicating with Feedback Loop Service.
    
    Used when feedback and platform are deployed as separate services.
    """
    
    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            service_name="feedback-loop",
            timeout=30.0
        )
    
    async def submit_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        original_query: str,
        original_response: str,
        issue_types: Optional[List[str]] = None,
        source: str = "web_interface"
    ) -> Dict[str, Any]:
        """
        Submit user feedback to feedback service.
        
        Returns:
            Response with status, message, and optional correction claim
        """
        payload = {
            "session_id": session_id,
            "response_id": response_id,
            "feedback_text": feedback_text,
            "original_query": original_query,
            "original_response": original_response,
            "issue_types": issue_types or ["general"],
            "source": source
        }
        
        logger.info(f"Submitting feedback: response_id={response_id}")
        
        return await self.post("/api/feedback", payload)
    
    async def detect_follow_up_correction(
        self,
        session_id: str,
        previous_response_id: str,
        original_query: str,
        original_response: str,
        follow_up_query: str,
        session_history: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Detect if follow-up query is a correction attempt.
        
        Returns:
            Detection result with is_correction flag and confidence
        """
        payload = {
            "session_id": session_id,
            "previous_response_id": previous_response_id,
            "original_query": original_query,
            "original_response": original_response,
            "follow_up_query": follow_up_query,
            "session_history": session_history or []
        }
        
        return await self.post("/api/feedback/follow-up-detection", payload)
    
    async def get_feedback(self, feedback_id: str) -> Dict[str, Any]:
        """Retrieve feedback record by ID."""
        return await self.get(f"/api/feedback/{feedback_id}")
    
    async def get_recent_feedback(
        self,
        limit: int = 20,
        issue_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent feedback submissions."""
        params = {"limit": limit}
        if issue_type:
            params["issue_type"] = issue_type
        
        response = await self.get("/api/feedback/recent", params=params)
        return response.get("feedback", [])
