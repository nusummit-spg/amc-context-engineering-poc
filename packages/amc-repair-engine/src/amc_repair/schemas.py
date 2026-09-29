"""
Schemas for patches, evaluation reports, and governance.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator


class CorrectionPatch(BaseModel):
    patch_id: str
    entity_id: str
    entity_name: Optional[str] = None
    attribute: str
    corrected_value: Any
    original_value: Optional[Any] = None
    canonical_value: Optional[Any] = None
    source_chunk_id: Optional[str] = None
    confidence: float = 1.0
    approved: bool = False
    source: str = "feedback"
    provenance: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None

    @model_validator(mode="after")
    def sync_original_and_canonical(self) -> "CorrectionPatch":
        if self.canonical_value is None and self.original_value is not None:
            object.__setattr__(self, "canonical_value", self.original_value)
        elif self.original_value is None and self.canonical_value is not None:
            object.__setattr__(self, "original_value", self.canonical_value)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "attribute": self.attribute,
            "corrected_value": self.corrected_value,
            "original_value": self.original_value,
            "canonical_value": self.canonical_value,
            "source_chunk_id": self.source_chunk_id,
            "confidence": self.confidence,
            "approved": self.approved,
            "source": self.source,
            "provenance": self.provenance,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class EvaluationResult(BaseModel):
    response_id: str
    verdict: str  # PASS, REVISE, FAIL
    tier: str  # TIER_1A, TIER_1B, TIER_2, TIER_3
    confidence: float
    details: Dict[str, Any] = Field(default_factory=dict)


class GovernanceBatchReport(BaseModel):
    total_evaluated: int = 0
    approved: int = 0
    rejected: int = 0
    needs_review: int = 0
    promoted_to_graph: int = 0
    deployed: int = 0
    errors: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def sync_deployed_promoted(self) -> "GovernanceBatchReport":
        if self.deployed == 0 and self.promoted_to_graph > 0:
            object.__setattr__(self, "deployed", self.promoted_to_graph)
        elif self.promoted_to_graph == 0 and self.deployed > 0:
            object.__setattr__(self, "promoted_to_graph", self.deployed)
        return self
