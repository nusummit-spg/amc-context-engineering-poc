"""WS5a — Entity schemas: all 9 node types in the AMC knowledge graph.

Node types (mirrors WS5b Neo4j schema design):
  Scheme, Issuer, IssuerGroup, Analyst, Sector, RiskTheme,
  RegulatoryCircular, ClauseType, DocumentNode
"""
from enum import Enum
from typing import Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    SCHEME = "Scheme"
    ISSUER = "Issuer"
    ISSUER_GROUP = "IssuerGroup"
    ANALYST = "Analyst"
    SECTOR = "Sector"
    RISK_THEME = "RiskTheme"
    REGULATORY_CIRCULAR = "RegulatoryCircular"
    CLAUSE_TYPE = "ClauseType"
    DOCUMENT = "Document"


class BaseEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_type: EntityType
    name: str
    aliases: list[str] = Field(default_factory=list)
    source_document_ids: list[str] = Field(default_factory=list)
    properties: dict = Field(default_factory=dict)


class Scheme(BaseEntity):
    """A mutual fund scheme (e.g. NuSummit Infra Fund)."""
    entity_type: EntityType = EntityType.SCHEME
    scheme_code: Optional[str] = None
    aum_cr: Optional[float] = None
    exit_load_format: Optional[str] = None  # "narrative" | "schedule_iii" — drives compliance flagging


class Issuer(BaseEntity):
    """A listed company / security issuer (e.g. Adani Ports & SEZ)."""
    entity_type: EntityType = EntityType.ISSUER
    ticker: Optional[str] = None
    sector_name: Optional[str] = None


class IssuerGroup(BaseEntity):
    """A conglomerate grouping of issuers (e.g. Adani Group)."""
    entity_type: EntityType = EntityType.ISSUER_GROUP


class Analyst(BaseEntity):
    """An internal research analyst (e.g. P. Sharma — BFSI)."""
    entity_type: EntityType = EntityType.ANALYST
    coverage_area: Optional[str] = None


class Sector(BaseEntity):
    entity_type: EntityType = EntityType.SECTOR


class RiskTheme(BaseEntity):
    """A risk / compliance concept (e.g. Funding Cost Pressure, Concentration Risk)."""
    entity_type: EntityType = EntityType.RISK_THEME


class RegulatoryCircular(BaseEntity):
    """A SEBI (or other regulator) circular."""
    entity_type: EntityType = EntityType.REGULATORY_CIRCULAR
    reference: Optional[str] = None      # e.g. SEBI/HO/IMD/May2026/0142
    issued_date: Optional[str] = None
    required_format: Optional[str] = None  # e.g. "schedule_iii"


class ClauseType(BaseEntity):
    """A clause category inside scheme documents (e.g. Exit Load Clause)."""
    entity_type: EntityType = EntityType.CLAUSE_TYPE


class DocumentNode(BaseEntity):
    """Graph mirror of an ingested document, for provenance edges."""
    entity_type: EntityType = EntityType.DOCUMENT
    doc_type: Optional[str] = None
    category: Optional[str] = None


AnyEntity = Union[
    Scheme, Issuer, IssuerGroup, Analyst, Sector,
    RiskTheme, RegulatoryCircular, ClauseType, DocumentNode,
]

ENTITY_CLASS_BY_TYPE: dict[EntityType, type[BaseEntity]] = {
    EntityType.SCHEME: Scheme,
    EntityType.ISSUER: Issuer,
    EntityType.ISSUER_GROUP: IssuerGroup,
    EntityType.ANALYST: Analyst,
    EntityType.SECTOR: Sector,
    EntityType.RISK_THEME: RiskTheme,
    EntityType.REGULATORY_CIRCULAR: RegulatoryCircular,
    EntityType.CLAUSE_TYPE: ClauseType,
    EntityType.DOCUMENT: DocumentNode,
}
