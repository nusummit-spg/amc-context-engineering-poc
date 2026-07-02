"""WS5a — Relationship schemas: typed edges with properties.

Edge semantics (WS5b ontology):
  (Scheme)-[:HOLDS {pct_nav, holding_name}]->(Issuer)
  (Issuer)-[:ISSUED_BY]->(IssuerGroup)          # issuer belongs to conglomerate
  (Issuer)-[:IN_SECTOR]->(Sector)
  (IssuerGroup)-[:MONITORED_FOR]->(RiskTheme)
  (Issuer)-[:FLAGGED_IN {document_id}]->(RiskTheme)
  (Analyst)-[:COVERS]->(Issuer|Sector)
  (RegulatoryCircular)-[:APPLIES_TO]->(ClauseType)
  (ClauseType)-[:AFFECTS {status}]->(Scheme)     # status: outdated | compliant | not_reviewed
  (Document)-[:MENTIONS]->(any entity)
  (Document)-[:TAGGED_AS {path}]->(TaxonomyNode)
"""
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class RelationshipType(str, Enum):
    HOLDS = "HOLDS"
    ISSUED_BY = "ISSUED_BY"
    IN_SECTOR = "IN_SECTOR"
    MONITORED_FOR = "MONITORED_FOR"
    FLAGGED_IN = "FLAGGED_IN"
    COVERS = "COVERS"
    APPLIES_TO = "APPLIES_TO"
    AFFECTS = "AFFECTS"
    MENTIONS = "MENTIONS"
    TAGGED_AS = "TAGGED_AS"


class Relationship(BaseModel):
    """A typed, directed edge between two entities with optional properties."""
    relationship_id: str = Field(default_factory=lambda: str(uuid4()))
    relationship_type: RelationshipType
    source_entity_id: str
    target_entity_id: str
    # Common edge properties (all optional; stored on the Neo4j relationship)
    properties: dict = Field(default_factory=dict)
    # Provenance
    source_document_id: Optional[str] = None
    source_chunk_id: Optional[str] = None
    extraction_method: str = "rule"  # "rule" | "llm"
    confidence: float = 1.0


class HoldsProperties(BaseModel):
    """Typed helper for HOLDS edge props: Scheme -[HOLDS]-> Issuer."""
    pct_nav: Optional[float] = None
    holding_name: Optional[str] = None
    as_of_date: Optional[str] = None


class AffectsProperties(BaseModel):
    """Typed helper for AFFECTS edge props: ClauseType -[AFFECTS]-> Scheme."""
    status: str = "not_reviewed"  # outdated | compliant | not_reviewed
    action_needed: Optional[str] = None
