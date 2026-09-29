"""
Data contracts and schemas for feedback and correction extraction.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class EntityMention(BaseModel):
    text: str
    label: str
    start: int
    end: int
    score: float = 1.0
    layer: str = "rule"

class ResolvedEntity(BaseModel):
    canonical_id: str
    canonical_name: str
    confidence: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CorrectionClaim(BaseModel):
    resolved_entity_id: Optional[str] = None
    resolved_entity_name: Optional[str] = None
    attribute: str
    asserted_value: str
    rejected_value: Optional[str] = None
    confidence: float = 1.0
    context_chunk_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolved_entity_id": self.resolved_entity_id,
            "resolved_entity_name": self.resolved_entity_name,
            "attribute": self.attribute,
            "asserted_value": self.asserted_value,
            "rejected_value": self.rejected_value,
            "confidence": self.confidence,
            "context_chunk_id": self.context_chunk_id,
        }

class FollowUpDetectionRequest(BaseModel):
    session_id: str
    previous_response_id: str
    original_query: str
    original_response: str
    follow_up_query: str
    session_history: List[str] = Field(default_factory=list)

class FollowUpDetectionResponse(BaseModel):
    is_correction: bool
    confidence: float
    reasons: List[str] = Field(default_factory=list)
    structured_claim: Optional[CorrectionClaim] = None
