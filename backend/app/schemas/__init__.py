"""WS5a — Unified schema package for the AMC ContextGraph backend.

Import from here for clean, stable access:
    from app.schemas import Document, Chunk, QueryIntent, AnyEntity, ...

Module dependency order (no circular imports):
    documents   →  (stdlib only)
    entities    →  (stdlib only)
    relationships → (stdlib only)
    taxonomy    →  (stdlib only)
    query       →  (stdlib only)
    api         →  documents, query
"""
# documents
from app.schemas.documents import (
    Chunk,
    Document,
    DocumentCategory,
    DocumentType,
    IngestionJob,
    IngestionStatus,
    Section,
)

# entities
from app.schemas.entities import (
    ENTITY_CLASS_BY_TYPE,
    Analyst,
    AnyEntity,
    BaseEntity,
    ClauseType,
    DocumentNode,
    EntityType,
    Issuer,
    IssuerGroup,
    RegulatoryCircular,
    RiskTheme,
    Scheme,
    Sector,
)

# relationships
from app.schemas.relationships import (
    AffectsProperties,
    FlaggedInProperties,
    HoldsProperties,
    Relationship,
    RelationshipType,
    TaggedAsProperties,
)

# taxonomy
from app.schemas.taxonomy import (
    TaxonomyClassificationResult,
    TaxonomyNode,
    TaxonomyTag,
    TaxonomyTree,
)

# query
from app.schemas.query import (
    TRAVERSAL_STRATEGIES,
    AssembledContext,
    Citation,
    GraphFact,
    QueryIntent,
    QueryType,
    ResolvedEntity,
    RetrievalResult,
    RetrievedChunk,
    SourceAttribution,
    SynthesisOutput,
    TraversalStrategy,
)

# api
from app.schemas.api import (
    DocumentDetailOut,
    DocumentSummaryOut,
    GraphEdgeOut,
    GraphHighlight,
    GraphNodeOut,
    GraphResponse,
    HealthResponse,
    IngestJobResponse,
    IngestStatusResponse,
    QueryRequest,
    QueryResponse,
    TaxonomyNodeDocsResponse,
    TaxonomyNodeOut,
    TaxonomyTreeResponse,
    TraditionalResult,
)

__all__ = [
    # documents
    "Chunk", "Document", "DocumentCategory", "DocumentType",
    "IngestionJob", "IngestionStatus", "Section",
    # entities
    "ENTITY_CLASS_BY_TYPE", "Analyst", "AnyEntity", "BaseEntity",
    "ClauseType", "DocumentNode", "EntityType", "Issuer", "IssuerGroup",
    "RegulatoryCircular", "RiskTheme", "Scheme", "Sector",
    # relationships
    "AffectsProperties", "FlaggedInProperties", "HoldsProperties",
    "Relationship", "RelationshipType", "TaggedAsProperties",
    # taxonomy
    "TaxonomyClassificationResult", "TaxonomyNode", "TaxonomyTag", "TaxonomyTree",
    # query
    "TRAVERSAL_STRATEGIES", "AssembledContext", "Citation", "GraphFact",
    "QueryIntent", "QueryType", "ResolvedEntity", "RetrievalResult",
    "RetrievedChunk", "SourceAttribution", "SynthesisOutput", "TraversalStrategy",
    # api
    "DocumentDetailOut", "DocumentSummaryOut", "GraphEdgeOut", "GraphHighlight",
    "GraphNodeOut", "GraphResponse", "HealthResponse", "IngestJobResponse",
    "IngestStatusResponse", "QueryRequest", "QueryResponse",
    "TaxonomyNodeDocsResponse", "TaxonomyNodeOut", "TaxonomyTreeResponse", "TraditionalResult",
]
