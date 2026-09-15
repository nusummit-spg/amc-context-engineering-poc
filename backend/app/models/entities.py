# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS5a — Entity schemas: all 9 node types in the AMC knowledge graph.

Node types (mirrors WS5b Neo4j schema design):
  Scheme, Issuer, IssuerGroup, Analyst, Sector, RiskTheme,
  RegulatoryCircular, ClauseType, DocumentNode

Unified with WS5a extended design:
  - BaseEntity gains confidence tracking + needs_review auto-flag
  - Alias list is case-insensitive deduplicated on construction
  - AnyEntity uses a Pydantic v2 discriminated union (faster parsing, clearer errors)
  - RegulatoryCircular gains effective_date + issuing_body
  - ClauseType gains optional limit_value / limit_unit for breach-detection Cypher
  - IssuerGroup is kept; ISSUED_BY edge semantics remain unchanged (see relationships.py)
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class EntityType(str, Enum):
    SCHEME              = "Scheme"
    ISSUER              = "Issuer"
    ISSUER_GROUP        = "IssuerGroup"
    ANALYST             = "Analyst"
    SECTOR              = "Sector"
    RISK_THEME          = "RiskTheme"
    REGULATORY_CIRCULAR = "RegulatoryCircular"
    CLAUSE_TYPE         = "ClauseType"
    DOCUMENT            = "Document"
    TABLE_FACT          = "TableFact"
    FINANCIAL_METRIC    = "FinancialMetric"
    ESG_METRIC          = "ESGMetric"
    COMPLIANCE_RULE     = "ComplianceRule"
    PENALTY             = "Penalty"
    SECTION             = "Section"
    CLAUSE              = "Clause"


class BaseEntity(BaseModel):
    """Common fields for every entity node in the AMC knowledge graph.

    Confidence & review workflow:
      confidence < 0.90  → needs_review is automatically set True
      confidence = 1.0   → manually curated / alias-seed entry (default)
    """
    entity_id:           str        = Field(default_factory=lambda: str(uuid4()))
    entity_type:         EntityType
    name:                str        = Field(min_length=1)
    aliases:             list[str]  = Field(default_factory=list)
    source_document_ids: list[str]  = Field(default_factory=list)
    properties:          dict       = Field(default_factory=dict)

    # ── Quality tracking (from WS5a extended design) ──────────────────────
    confidence:   float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Extraction confidence [0,1]. "
            "Set to 1.0 for seed/manually curated entities. "
            "LLM-extracted entities carry the model's confidence score."
        ),
    )
    needs_review: bool = Field(
        default=False,
        description="True when confidence < 0.90 or entity was created provisionally.",
    )

    @field_validator("aliases", mode="before")
    @classmethod
    def deduplicate_aliases_case_insensitive(cls, v: list[str]) -> list[str]:
        """Remove duplicates preserving original casing of first occurrence."""
        seen: set[str] = set()
        result: list[str] = []
        for alias in v:
            key = alias.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(alias.strip())
        return result

    @model_validator(mode="after")
    def auto_flag_low_confidence(self) -> "BaseEntity":
        """Automatically set needs_review when confidence is below threshold."""
        if self.confidence < 0.90:
            self.needs_review = True
        return self


# ── Concrete entity subclasses ────────────────────────────────────────────────

class Scheme(BaseEntity):
    """A mutual fund scheme (e.g. NuSummit Infra Fund)."""
    entity_type:      Literal[EntityType.SCHEME] = EntityType.SCHEME
    scheme_code:      Optional[str]   = None
    aum_cr:           Optional[float] = None
    exit_load_format: Optional[str]   = None  # "narrative" | "schedule_iii"


class Issuer(BaseEntity):
    """A listed company / security issuer (e.g. Adani Ports & SEZ)."""
    entity_type: Literal[EntityType.ISSUER] = EntityType.ISSUER
    ticker:      Optional[str]   = None
    sector_name: Optional[str]   = None
    credit_rating: Optional[str] = None  # e.g. "AA", "BBB+"


class IssuerGroup(BaseEntity):
    """A conglomerate grouping of issuers (e.g. Adani Group)."""
    entity_type: Literal[EntityType.ISSUER_GROUP] = EntityType.ISSUER_GROUP


class Analyst(BaseEntity):
    """An internal research analyst (e.g. P. Sharma — BFSI)."""
    entity_type:   Literal[EntityType.ANALYST] = EntityType.ANALYST
    coverage_area: Optional[str] = None


class Sector(BaseEntity):
    """An industry sector node (e.g. NBFC, Infrastructure).

    Enables the house_view_synthesis traversal:
      Analyst → COVERS → Issuer → IN_SECTOR → Sector
    """
    entity_type:  Literal[EntityType.SECTOR] = EntityType.SECTOR
    sector_type:  Optional[str] = None  # e.g. "equity", "debt", "multi-asset"


class RiskTheme(BaseEntity):
    """A risk / compliance concept (e.g. Funding Cost Pressure, Concentration Risk)."""
    entity_type: Literal[EntityType.RISK_THEME] = EntityType.RISK_THEME


class RegulatoryCircular(BaseEntity):
    """A SEBI (or other regulator) circular.

    Extended from original: added effective_date and issuing_body.
    """
    entity_type:     Literal[EntityType.REGULATORY_CIRCULAR] = EntityType.REGULATORY_CIRCULAR
    reference:       Optional[str] = None   # e.g. SEBI/HO/IMD/May2026/0142
    issued_date:     Optional[str] = None   # ISO date string "YYYY-MM-DD"
    effective_date:  Optional[str] = None   # ISO date string
    required_format: Optional[str] = None   # e.g. "schedule_iii"
    issuing_body:    Optional[str] = None   # e.g. "SEBI", "RBI"


class ClauseType(BaseEntity):
    """A clause category inside scheme documents (e.g. Exit Load Clause).

    Extended from original: added limit_value / limit_unit for breach-detection Cypher.
    Example: limit_value=25.0, limit_unit="percentage_of_nav" enables
      MATCH (c:ClauseType {name: 'Single Issuer Limit'}) WHERE c.limit_value < $exposure
    """
    entity_type:  Literal[EntityType.CLAUSE_TYPE] = EntityType.CLAUSE_TYPE
    clause_type:  Optional[str]   = None   # e.g. "single_group_limit", "exit_load"
    limit_value:  Optional[float] = None   # numeric threshold (e.g. 25.0)
    limit_unit:   Optional[str]   = None   # e.g. "percentage_of_nav"

    @field_validator("limit_value")
    @classmethod
    def limit_value_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("limit_value must be >= 0")
        return v


class DocumentNode(BaseEntity):
    """Graph mirror of an ingested document — enables provenance edges
    (Document)-[:MENTIONS]->(any entity), (Document)-[:TAGGED_AS]->(TaxonomyNode).
    """
    entity_type: Literal[EntityType.DOCUMENT] = EntityType.DOCUMENT
    doc_type:    Optional[str] = None
    category:    Optional[str] = None


# ── Discriminated union (Pydantic v2 native, faster parsing than plain Union) ──

AnyEntity = Annotated[
    Union[
        Scheme, Issuer, IssuerGroup, Analyst, Sector,
        RiskTheme, RegulatoryCircular, ClauseType, DocumentNode,
    ],
    Field(discriminator="entity_type"),
]
"""
Pydantic v2 discriminated union on entity_type.
Usage:
    from pydantic import TypeAdapter
    ta = TypeAdapter(AnyEntity)
    entity = ta.validate_python({"entity_type": "Scheme", "name": "HDFC Flexi Cap", ...})
    # → Scheme instance

Faster than plain Union: O(1) dispatch instead of try-each-class.
Clearer error messages: "entity_type='X' is not a valid EntityType" instead of
"none of the union branches matched".
"""

ENTITY_CLASS_BY_TYPE: dict[EntityType, type[BaseEntity]] = {
    EntityType.SCHEME:              Scheme,
    EntityType.ISSUER:              Issuer,
    EntityType.ISSUER_GROUP:        IssuerGroup,
    EntityType.ANALYST:             Analyst,
    EntityType.SECTOR:              Sector,
    EntityType.RISK_THEME:          RiskTheme,
    EntityType.REGULATORY_CIRCULAR: RegulatoryCircular,
    EntityType.CLAUSE_TYPE:         ClauseType,
    EntityType.DOCUMENT:            DocumentNode,
}
