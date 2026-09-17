# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/evidence_metadata.py
============================
Pydantic schema for EvidenceMetadata (9 fields).
Cryptographic hash, chain of custody, and retention tracking for audit compliance.
"""

from typing import Optional
from pydantic import BaseModel, Field


class EvidenceMetadata(BaseModel):
    """
    Schema for EvidenceMetadata to ensure cryptographic chain of custody for audit defense.
    Node type in Neo4j with indices on document_id, document_hash.
    """
    evidence_id: str = Field(..., description="Unique evidence tracking identifier")
    document_id: str = Field(..., description="Foreign key linking to Document or Evidence node")
    document_hash: str = Field(..., description="Cryptographic SHA-256 checksum of evidentiary document")
    collected_at: str = Field(..., description="ISO 8601 timestamp when evidence was collected and frozen")
    retention_expiry_date: str = Field(..., description="Mandated statutory retention expiry date (YYYY-MM-DD)")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Evaluated relevance score to target violation (0-1)")
    chain_of_custody_signoff: str = Field(..., description="Sign-off key or user identifier of custodial officer")
    source_authority_tier: str = Field(
        default="TIER_1_REGULATOR",
        description="Source credibility tier: TIER_1_REGULATOR, TIER_2_OFFICIAL_FILING, TIER_3_INTERNAL, TIER_4_RESEARCH"
    )
    is_tamper_evident: bool = Field(default=True, description="Whether cryptographic seal is intact and verified")
    document_size_bytes: Optional[int] = Field(default=None, ge=0, description="Size of evidentiary file in bytes")
    compression_ratio: Optional[float] = Field(default=None, ge=0.0, description="Storage compression ratio")

