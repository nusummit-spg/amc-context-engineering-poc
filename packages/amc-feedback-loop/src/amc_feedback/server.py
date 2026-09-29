"""
FastAPI server for Feedback Loop Service.
Standalone microservice for feedback processing.
"""
import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import FeedbackLoop, FeedbackConfig
from .adapters.database import SQLiteAdapter, PostgreSQLAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("feedback_service")

# Create FastAPI app
app = FastAPI(
    title="AMC Feedback Loop Service",
    description="Microservice for feedback collection and correction extraction",
    version="0.1.0"
)

# Global feedback loop instance
_feedback_loop: Optional[FeedbackLoop] = None


def get_feedback_loop() -> FeedbackLoop:
    """Get or create feedback loop singleton."""
    global _feedback_loop
    
    if _feedback_loop is None:
        # Configure from environment
        config = FeedbackConfig(
            domain_name=os.getenv("DOMAIN_NAME", "amc"),
            entity_master_path=os.getenv("ENTITY_MASTER_PATH"),
            fuzzy_match_threshold=float(os.getenv("FUZZY_THRESHOLD", "0.70")),
            enable_passive_capture=os.getenv("ENABLE_PASSIVE", "true").lower() == "true"
        )
        
        # Database adapter
        db_url = os.getenv("DATABASE_URL", "sqlite:///./feedback.db")
        if "sqlite" in db_url:
            db_path = db_url.replace("sqlite:///", "").replace("sqlite:////", "/")
            db_adapter = SQLiteAdapter(db_path)
        else:
            db_adapter = PostgreSQLAdapter(db_url)
        
        _feedback_loop = FeedbackLoop(
            config=config,
            db_adapter=db_adapter,
            evidence_adapter=None
        )
        
        logger.info("Feedback loop initialized")
    
    return _feedback_loop


# ── Request/Response Models ───────────────────────────────────

class FeedbackRequest(BaseModel):
    session_id: str
    response_id: str
    feedback_text: str
    original_query: Optional[str] = ""
    original_response: Optional[str] = ""
    issue_types: Optional[List[str]] = None
    source: str = "web_interface"


class FollowUpDetectionRequest(BaseModel):
    session_id: str
    previous_response_id: str
    original_query: str
    original_response: str
    follow_up_query: str
    session_history: Optional[List[str]] = None


# ── API Endpoints ─────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "feedback-loop",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """
    Submit user feedback for processing.
    Detects corrections and creates structured claims.
    """
    try:
        loop = get_feedback_loop()
        
        claim = await loop.process_feedback(
            session_id=request.session_id,
            response_id=request.response_id,
            feedback_text=request.feedback_text,
            original_query=request.original_query or "",
            original_response=request.original_response or "",
            issue_types=request.issue_types,
            source=request.source
        )
        
        if claim and claim.resolved_entity_id:
            return {
                "status": "correction_detected",
                "message": "Correction detected and will be reviewed",
                "claim": {
                    "entity_id": claim.resolved_entity_id,
                    "entity_name": claim.resolved_entity_name,
                    "attribute": claim.attribute,
                    "asserted_value": claim.asserted_value,
                    "rejected_value": claim.rejected_value,
                    "confidence": claim.confidence
                }
            }
        else:
            return {
                "status": "feedback_recorded",
                "message": "Thank you for your feedback",
                "claim": claim.to_dict() if claim else None
            }
    
    except Exception as exc:
        logger.error(f"Feedback processing error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/feedback/follow-up-detection")
async def detect_follow_up(request: FollowUpDetectionRequest):
    """
    Detect if follow-up query is a correction attempt (passive feedback).
    """
    try:
        loop = get_feedback_loop()
        
        is_correction, confidence, signals = loop.detector.is_correction_attempt(
            feedback_text=request.follow_up_query,
            original_query=request.original_query,
            original_response=request.original_response
        )
        
        if is_correction and confidence >= 0.70:
            # Auto-create feedback
            claim = await loop.process_feedback(
                session_id=request.session_id,
                response_id=request.previous_response_id,
                feedback_text=request.follow_up_query,
                original_query=request.original_query,
                original_response=request.original_response,
                issue_types=["F02-Accuracy"],
                source="passive_followup"
            )
            
            return {
                "is_correction": True,
                "confidence": confidence,
                "signals": signals,
                "claim": claim.to_dict() if claim else None,
                "auto_created": True
            }
        else:
            return {
                "is_correction": False,
                "confidence": confidence,
                "signals": signals,
                "claim": None,
                "auto_created": False
            }
    
    except Exception as exc:
        logger.error(f"Follow-up detection error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/feedback/recent")
async def get_recent_feedback(
    limit: int = Query(default=20, ge=1, le=100),
    issue_type: Optional[str] = None
):
    """Get recent feedback submissions."""
    try:
        loop = get_feedback_loop()
        records = await loop.db.get_recent_feedback(limit=limit, issue_type=issue_type)
        return {"total": len(records), "feedback": records}
    except Exception as exc:
        logger.error(f"Get recent feedback error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/feedback/{feedback_id}")
async def get_feedback(feedback_id: str):
    """Retrieve feedback by ID."""
    try:
        loop = get_feedback_loop()
        feedback = await loop.db.get_feedback(feedback_id)
        
        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")
        
        return feedback
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Get feedback error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global _feedback_loop
    if _feedback_loop:
        await _feedback_loop.close()
        logger.info("Feedback loop closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
