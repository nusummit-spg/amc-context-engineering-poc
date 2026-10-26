# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
loop.py
=======
Core orchestration client and high-level interface for feedback_loop.
Provides FeedbackLoop, SQLiteAdapter wrapper, StructuredClaim, and follow-up detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from feedback_loop.config import DEFAULT_ATTRIBUTE_KEYWORDS, FeedbackConfig
from feedback_loop.adapters.sqlite.db_adapter import SQLiteDatabaseAdapter
from feedback_loop.logging import get_feedback_logger, log_step_info

logger = get_feedback_logger("feedback_loop.loop")


class SQLiteAdapter:
    """Lightweight SQLite adapter wrapper for feedback_loop."""

    def __init__(self, db_path_or_url: str):
        """Initialize a new instance of SQLiteAdapter.

        Args:
            db_path_or_url (str): The db path or url.
        """
        self.db_path = str(db_path_or_url)
        url = db_path_or_url if db_path_or_url.startswith("sqlite:///") else f"sqlite:///{db_path_or_url}"
        try:
            self._underlying = SQLiteDatabaseAdapter(db_url=url)
        except Exception:
            self._underlying = None


@dataclass
class StructuredClaim:
    """Extracted correction claim from user feedback."""
    attribute: Optional[str] = None
    asserted_value: Optional[str] = None
    rejected_value: Optional[str] = None
    resolved_entity_name: Optional[str] = None
    confidence: float = 0.85
    entity_id: Optional[str] = None


class FollowUpDetectionRequest(BaseModel):
    """Request payload to detect if a follow-up query is a feedback correction."""
    session_id: str
    previous_response_id: str
    original_query: str
    original_response: str
    follow_up_query: str


@dataclass
class FollowUpDetectionResult:
    """Result of follow-up query correction analysis."""
    is_correction: bool
    structured_claim: Optional[StructuredClaim] = None
    confidence: float = 0.85


class FeedbackLoop:
    """FeedbackLoop orchestration client and high-level interface."""

    def __init__(self, config: Optional[FeedbackConfig] = None, db_adapter: Optional[Any] = None):
        """Initialize a new instance of FeedbackLoop.

        Args:
            config (Optional[FeedbackConfig]): Configuration dictionary or settings object.
            db_adapter (Optional[Any]): The db adapter.
        """
        self.config = config or FeedbackConfig()
        self.db_adapter = db_adapter

    async def process_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        original_query: str = "",
        original_response: str = "",
    ) -> Optional[StructuredClaim]:
        """Process user feedback text and extract correction claim if applicable.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            feedback_text (str): The feedback text.
            original_query (str): The original query.
            original_response (str): The original response.

        Returns:
            Optional[StructuredClaim]: Matching object or record if found, None otherwise.
        """
        log_step_info(
            logger,
            "FEEDBACK_PARSE_START",
            "Processing feedback: session_id=%s, response_id=%s, text_length=%d",
            session_id,
            response_id,
            len(feedback_text or ""),
        )
        text_lower = feedback_text.lower()

        # If feedback is purely positive or complimentary, ignore
        positive_keywords = ["thank you", "helpful", "accurate", "great", "good job", "excellent", "correct"]
        if any(kw in text_lower for kw in positive_keywords) and not any(
            neg in text_lower for neg in ["wrong", "not", "actually", "error", "incorrect", "instead", "should be"]
        ):
            log_step_info(logger, "FEEDBACK_POSITIVE_SKIPPED", "Feedback is purely complimentary, skipped for response_id=%s", response_id)
            return None

        # Extract attribute
        attribute = None
        attr_map = getattr(self.config, "attribute_keywords", DEFAULT_ATTRIBUTE_KEYWORDS)
        for attr, keywords in attr_map.items():
            if any(kw in text_lower for kw in keywords):
                attribute = attr
                break
        if not attribute:
            attribute = "general"

        # Regex extract numbers for asserted/rejected value (e.g. 0.82%, not 0.79%)
        asserted_value = None
        rejected_value = None

        # Look for "actually X, not Y" or "is X not Y" or "X instead of Y"
        pat1 = re.search(r"actually\s+([0-9]+(?:\.[0-9]+)?%?)\s*,?\s*not\s+([0-9]+(?:\.[0-9]+)?%?)", feedback_text, re.I)
        if pat1:
            asserted_value = pat1.group(1).rstrip("%")
            rejected_value = pat1.group(2).rstrip("%")
        else:
            pat2 = re.search(r"([0-9]+(?:\.[0-9]+)?%?)\s+instead\s+of\s+([0-9]+(?:\.[0-9]+)?%?)", feedback_text, re.I)
            if pat2:
                asserted_value = pat2.group(1).rstrip("%")
                rejected_value = pat2.group(2).rstrip("%")
            else:
                nums = re.findall(r"\b[0-9]+(?:\.[0-9]+)?%?\b", feedback_text)
                if len(nums) >= 2:
                    asserted_value = nums[0].rstrip("%")
                    rejected_value = nums[1].rstrip("%")
                elif len(nums) == 1:
                    asserted_value = nums[0].rstrip("%")

        # Entity resolution heuristic
        resolved_entity_name = None
        if "axis bluechip" in text_lower:
            resolved_entity_name = "Axis Bluechip Fund"
        elif "hdfc top 100" in text_lower:
            resolved_entity_name = "HDFC Top 100 Fund"
        elif "mirae" in text_lower:
            resolved_entity_name = "Mirae Asset Large Cap Fund"

        claim = StructuredClaim(
            attribute=attribute,
            asserted_value=asserted_value,
            rejected_value=rejected_value,
            resolved_entity_name=resolved_entity_name,
            confidence=0.90,
        )
        log_step_info(
            logger,
            "CLAIM_EXTRACTED",
            "Structured claim extracted for %s: entity=%s, attr=%s, asserted=%s, rejected=%s",
            response_id,
            resolved_entity_name,
            attribute,
            asserted_value,
            rejected_value,
        )
        return claim

    async def detect_follow_up(self, req: FollowUpDetectionRequest) -> FollowUpDetectionResult:
        """Detect whether follow up query contains a correction.

        Args:
            req (FollowUpDetectionRequest): The req.

        Returns:
            FollowUpDetectionResult: Resulting FollowUpDetectionResult instance.
        """
        log_step_info(
            logger,
            "FOLLOW_UP_CHECK",
            "Evaluating follow-up: query='%s', prev_response_id=%s",
            req.follow_up_query,
            req.previous_response_id,
        )
        query_lower = req.follow_up_query.lower()
        correction_cues = ["no", "actually", "wrong", "not", "meant", "instead", "incorrect", "correction", "should be"]
        is_corr = any(cue in query_lower.split() or query_lower.startswith(cue) for cue in correction_cues)
        claim = None
        if is_corr:
            claim = await self.process_feedback(
                session_id=req.session_id,
                response_id=req.previous_response_id,
                feedback_text=req.follow_up_query,
                original_query=req.original_query,
                original_response=req.original_response,
            )
        return FollowUpDetectionResult(is_correction=is_corr, structured_claim=claim, confidence=0.88 if is_corr else 0.12)

    async def close(self):
        """Close feedback loop resources."""
        pass


__all__ = [
    "FeedbackLoop",
    "SQLiteAdapter",
    "StructuredClaim",
    "FollowUpDetectionRequest",
    "FollowUpDetectionResult",
]
