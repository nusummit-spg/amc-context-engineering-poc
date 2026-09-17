# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS5a — Relationship schemas: typed edges with properties.

Edge semantics (WS5b ontology) — full set:
  (Scheme)-[:HOLDS {pct_nav, holding_name, as_of_date}]->(Issuer)
  (Issuer)-[:ISSUED_BY]->(IssuerGroup)            # issuer belongs to conglomerate
  (Issuer)-[:IN_SECTOR]->(Sector)                 # ← required for house_view_synthesis
  (IssuerGroup)-[:MONITORED_FOR]->(RiskTheme)
  (Issuer)-[:FLAGGED_IN {document_id}]->(RiskTheme)
  (Analyst)-[:COVERS]->(Issuer|Sector)
  (RegulatoryCircular)-[:APPLIES_TO]->(ClauseType)  # ← required for compliance_check
  (ClauseType)-[:AFFECTS {status}]->(Scheme)
  (Document)-[:MENTIONS]->(any entity)              # ← provenance graph
  (Document)-[:TAGGED_AS {path}]->(TaxonomyNode)
  (Document)-[:REFERENCES]->(Document)              # ← circular/SID cross-reference

Unified with WS5a extended design:
  - RelationshipType gains IN_SECTOR, APPLIES_TO, MENTIONS (from colleague's code),
    and REFERENCES (new — Document→Document cross-reference)
  - Relationship gains source_chunk_id provenance field
  - Self-loop validator: source_entity_id != target_entity_id
  - Typed property helpers for all relationship types (not just HOLDS and AFFECTS)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class RelationshipType(str, Enum):
    HOLDS         = "HOLDS"           # Scheme → Issuer
    ISSUED_BY     = "ISSUED_BY"       # Issuer → IssuerGroup
    IN_SECTOR     = "IN_SECTOR"       # Issuer → Sector
    MONITORED_FOR = "MONITORED_FOR"   # IssuerGroup → RiskTheme
    FLAGGED_IN    = "FLAGGED_IN"      # Issuer → RiskTheme
    COVERS        = "COVERS"          # Analyst → Issuer | Sector
    APPLIES_TO    = "APPLIES_TO"      # RegulatoryCircular → ClauseType
    AFFECTS       = "AFFECTS"         # ClauseType → Scheme
    MENTIONS      = "MENTIONS"        # Document → any entity
    TAGGED_AS     = "TAGGED_AS"       # Document → TaxonomyNode
    REFERENCES    = "REFERENCES"      # Document → Document


class Relationship(BaseModel):
    """A typed, directed edge between two entities with full provenance."""
    relationship_id:   str              = Field(default_factory=lambda: str(uuid4()))
    relationship_type: RelationshipType
    source_entity_id:  str
    target_entity_id:  str
    # Edge-level properties (stored as Neo4j relationship properties)
    properties:        dict             = Field(default_factory=dict)
    # Provenance — both doc and chunk for fine-grained attribution
    source_document_id: Optional[str]  = None
    source_version_id:  Optional[str]  = None
    source_chunk_id:    Optional[str]  = None   # ← added for chunk-level provenance
    corpus_version:     Optional[str]  = None
    extraction_method:  str            = "rule"  # "rule" | "llm"
    confidence:         float          = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def no_self_loop(self) -> "Relationship":
        """An entity cannot have a relationship to itself."""
        if self.source_entity_id == self.target_entity_id:
            raise ValueError(
                f"Self-loop detected: source and target entity are both "
                f"'{self.source_entity_id}'. Relationships must connect distinct entities."
            )
        return self


# ── Typed property helpers ─────────────────────────────────────────────────────
# These are optional helpers for type-safe access to edge property dicts.
# The Relationship.properties dict stores the same data as Neo4j properties.

class HoldsProperties(BaseModel):
    """Typed properties for (Scheme)-[:HOLDS]->(Issuer)."""
    pct_nav:      Optional[float] = Field(default=None, ge=0.0, le=100.0)
    holding_name: Optional[str]   = None
    as_of_date:   Optional[str]   = Field(
        default=None,
        description="Month of portfolio snapshot, format YYYY-MM e.g. '2026-03'",
    )

    @model_validator(mode="after")
    def as_of_date_format(self) -> "HoldsProperties":
        if self.as_of_date is not None:
            import re
            if not re.match(r"^\d{4}-\d{2}$", self.as_of_date):
                raise ValueError(
                    f"as_of_date must be in YYYY-MM format (e.g. '2026-03'), "
                    f"got '{self.as_of_date}'"
                )
        return self


class AffectsProperties(BaseModel):
    """Typed properties for (ClauseType)-[:AFFECTS]->(Scheme)."""
    status:        str           = "not_reviewed"  # outdated | compliant | not_reviewed
    action_needed: Optional[str] = None

    @model_validator(mode="after")
    def valid_status(self) -> "AffectsProperties":
        allowed = {"outdated", "compliant", "not_reviewed"}
        if self.status not in allowed:
            raise ValueError(
                f"status must be one of {sorted(allowed)}, got '{self.status}'"
            )
        return self


class FlaggedInProperties(BaseModel):
    """Typed properties for (Issuer)-[:FLAGGED_IN]->(RiskTheme)."""
    document_id: Optional[str] = None
    flagged_at:  Optional[str] = None   # ISO date


class TaggedAsProperties(BaseModel):
    """Typed properties for (Document)-[:TAGGED_AS]->(TaxonomyNode)."""
    path:       str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
