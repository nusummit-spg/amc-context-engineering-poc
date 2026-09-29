"""
AMC Feedback Loop - Standalone package for feedback collection and correction extraction.
"""
from typing import List, Optional
from .config import FeedbackConfig
from .schemas import (
    EntityMention,
    ResolvedEntity,
    CorrectionClaim,
    FollowUpDetectionRequest,
    FollowUpDetectionResponse,
)
from .ner import NERPipeline
from .matcher import EntityMatcher
from .detector import DissatisfactionDetector
from .extractor import CorrectionExtractor
from .capture import FeedbackCapture
from .adapters.base import DatabaseAdapter, EvidenceAdapter
from .adapters.database import SQLiteAdapter
from .adapters.evidence import InMemoryEvidenceAdapter

__version__ = "0.1.0"
__all__ = [
    "FeedbackConfig",
    "FeedbackLoop",
    "DatabaseAdapter",
    "EvidenceAdapter",
    "SQLiteAdapter",
    "InMemoryEvidenceAdapter",
    "EntityMention",
    "ResolvedEntity",
    "CorrectionClaim",
    "FollowUpDetectionRequest",
    "FollowUpDetectionResponse",
]

class FeedbackLoop:
    """
    Main interface coordinating feedback loop operations.
    """

    def __init__(
        self,
        config: Optional[FeedbackConfig] = None,
        db_adapter: Optional[DatabaseAdapter] = None,
        evidence_adapter: Optional[EvidenceAdapter] = None,
    ):
        self.config = config or FeedbackConfig()
        self.db = db_adapter or SQLiteAdapter(":memory:")
        self.evidence = evidence_adapter or InMemoryEvidenceAdapter()

        self.ner = NERPipeline(self.config)
        self.matcher = EntityMatcher(self.config)
        self.detector = DissatisfactionDetector(self.config)
        self.extractor = CorrectionExtractor(self.config, self.ner, self.matcher)
        self.capture = FeedbackCapture(self)

    async def process_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        original_query: str = "",
        original_response: str = "",
        issue_types: Optional[List[str]] = None,
        source: str = "web_interface",
    ) -> Optional[CorrectionClaim]:
        is_corr, conf, signals = self.detector.is_correction_attempt(
            feedback_text=feedback_text,
            original_query=original_query,
            original_response=original_response,
        )

        if not is_corr or conf < self.config.correction_confidence_min:
            return None

        claim = self.extractor.extract_claim(
            feedback_text=feedback_text,
            original_response=original_response,
        )

        if not claim:
            return None

        # Store feedback in database
        feedback_id = await self.db.store_feedback(
            session_id=session_id,
            response_id=response_id,
            feedback_text=feedback_text,
            issue_types=issue_types or ["F02-Accuracy"],
            source=source,
            confidence=conf,
        )

        # Store unified evaluation record
        eval_record = {
            "feedback_id": feedback_id,
            "response_id": response_id,
            "query_text": original_query,
            "response_text": original_response,
            "claim": claim.to_dict(),
            "detection_confidence": conf,
            "signals": signals,
        }
        await self.db.store_evaluation_record(eval_record)

        return claim

    async def detect_follow_up(self, request: FollowUpDetectionRequest) -> FollowUpDetectionResponse:
        return await self.capture.detect_follow_up(request)

    async def close(self):
        await self.db.close()
        await self.evidence.close()
