"""
Schemas for patches, evaluation reports, and governance.

Wave 1.3 Batch B (B01): State Machine Implementation
- Versioned states: PENDING -> APPROVED -> STAGED -> VERIFIED -> ACTIVE
- Rejection/failure states: REJECTED, FAILED, ROLLED_BACK, SUPERSEDED
- Authorization vs publication separation
- Publication receipt tracking
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class PatchStatus(str, Enum):
    """
    B01: Authoritative patch lifecycle states.
    
    Normal flow:
    PENDING -> APPROVED -> STAGED -> VERIFIED -> ACTIVE
    
    Terminal states:
    REJECTED - Declined by reviewer
    FAILED - Technical failure during promotion
    ROLLED_BACK - Reverted after deployment
    SUPERSEDED - Replaced by newer version
    """
    # Initial state
    PENDING = "PENDING"              # Created, awaiting approval
    
    # Approval states  
    APPROVED = "APPROVED"            # Human approved, not yet published
    
    # Publication states
    STAGED = "STAGED"                # Queued for publication
    VERIFIED = "VERIFIED"            # Published and verified
    ACTIVE = "ACTIVE"                # Serving in answers (requires VERIFIED + receipt)
    
    # Terminal/failure states
    REJECTED = "REJECTED"            # Declined by reviewer
    FAILED = "FAILED"                # Technical failure
    ROLLED_BACK = "ROLLED_BACK"     # Reverted after deployment
    SUPERSEDED = "SUPERSEDED"        # Replaced by newer version


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
    
    # B01: State machine (replaces simple boolean)
    status: PatchStatus = PatchStatus.PENDING
    
    # B01: Backward compatibility - computed from status
    approved: bool = Field(default=False, description="Computed from status for compatibility")
    
    source: str = "feedback"
    provenance: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None
    
    # B01: State transition tracking
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    staged_at: Optional[str] = None
    verified_at: Optional[str] = None
    activated_at: Optional[str] = None
    
    # B01: Publication receipts
    publication_receipt: Optional[Dict[str, Any]] = None
    active_dataset_version: Optional[str] = None
    active_corpus_version: Optional[str] = None

    @model_validator(mode="after")
    def sync_original_and_canonical(self) -> "CorrectionPatch":
        """Validate sync original and canonical field.

        Returns:
            'CorrectionPatch': Resulting 'CorrectionPatch' instance.
        """
        if self.canonical_value is None and self.original_value is not None:
            object.__setattr__(self, "canonical_value", self.original_value)
        elif self.original_value is None and self.canonical_value is not None:
            object.__setattr__(self, "original_value", self.canonical_value)
        
        # B01: Sync approved field from status for backward compatibility
        is_approved = self.status in [
            PatchStatus.APPROVED,
            PatchStatus.STAGED,
            PatchStatus.VERIFIED,
            PatchStatus.ACTIVE
        ]
        object.__setattr__(self, "approved", is_approved)
        
        return self
    
    def can_serve(self) -> bool:
        """B01: Check if patch can serve in answers.
        
        Only ACTIVE patches with verified publication can serve.
        """
        return (
            self.status == PatchStatus.ACTIVE and
            self.publication_receipt is not None and
            self.verified_at is not None
        )

    def to_dict(self) -> Dict[str, Any]:
        """To dict.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
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
            "status": self.status.value,
            "approved": self.approved,
            "source": self.source,
            "provenance": self.provenance,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "staged_at": self.staged_at,
            "verified_at": self.verified_at,
            "activated_at": self.activated_at,
            "publication_receipt": self.publication_receipt,
            "active_dataset_version": self.active_dataset_version,
            "active_corpus_version": self.active_corpus_version,
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
        """Validate sync deployed promoted field.

        Returns:
            'GovernanceBatchReport': Resulting 'GovernanceBatchReport' instance.
        """
        if self.deployed == 0 and self.promoted_to_graph > 0:
            object.__setattr__(self, "deployed", self.promoted_to_graph)
        elif self.promoted_to_graph == 0 and self.deployed > 0:
            object.__setattr__(self, "promoted_to_graph", self.deployed)
        return self
