# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/regulatory_metadata.py
==============================
Pydantic schema for RegulatoryMetadata (15 fields).
Links compliance rules and violations to SEBI/SEC/ESMA/AMFI regulatory requirements.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class RegulatoryMetadata(BaseModel):
    """
    Schema for RegulatoryMetadata linking compliance rules and violations to statutory requirements.
    Node type in Neo4j with indices on rule_id, regulation_source, effective_date.
    """
    metadata_id: str = Field(..., description="Unique identifier for regulatory metadata record")
    rule_id: str = Field(..., description="Foreign key linking to compliance Rule ID (e.g., SEBI_EQUITY_ALLOC_001)")
    regulation_source: str = Field(..., description="Regulatory body: SEBI, SEC, ESMA, AMFI, etc.")
    regulation_section: str = Field(..., description="Specific regulation section or circular reference")
    regulation_url: Optional[str] = Field(default=None, description="Official URL to circular or statutory text")
    effective_date: str = Field(..., description="Date from which regulation is legally in force (YYYY-MM-DD)")
    sunset_date: Optional[str] = Field(default=None, description="Date when regulation is superseded or expired (YYYY-MM-DD)")
    is_mandatory: bool = Field(default=True, description="Whether adherence to this rule is statutory/mandatory")
    enforcement_level: str = Field(default="STRICT", description="Enforcement tier: STRICT, WARNING, ADVISORY, CRITICAL")
    framework_version: str = Field(default="2026.1", description="Version of regulatory framework taxonomy")
    jurisdiction_hierarchy: List[str] = Field(
        default_factory=lambda: ["GLOBAL", "IN", "SEBI"],
        description="Jurisdiction hierarchy path: e.g. ['GLOBAL', 'IN', 'SEBI']"
    )
    related_regulations: List[str] = Field(
        default_factory=list,
        description="Cross-referenced circulars or regulation IDs"
    )
    supersedes_rules: List[str] = Field(
        default_factory=list,
        description="Previous rule IDs superseded by this regulation"
    )
    created_by: str = Field(default="system", description="User or process that registered this metadata")
    updated_at: str = Field(..., description="ISO 8601 timestamp of last metadata update")

    @field_validator("enforcement_level")
    @classmethod
    def validate_enforcement_level(cls, v: str) -> str:
        valid_levels = {"STRICT", "WARNING", "ADVISORY", "CRITICAL"}
        upper_v = v.strip().upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid enforcement_level '{v}'. Must be one of {sorted(valid_levels)}")
        return upper_v

