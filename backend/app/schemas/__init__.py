# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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

# phase 1 metrics schemas
from app.schemas.regulatory_metadata import RegulatoryMetadata
from app.schemas.fund_metadata import FundAuditMetadata
from app.schemas.remediation_metrics import RemediationMetrics
from app.schemas.feedback_quality import FeedbackQualityMetrics
from app.schemas.feedback_analytics import FeedbackCategoryAnalytics
from app.schemas.response_quality import ResponseQualityMetrics

# phase 2 analysis schemas
from app.schemas.root_cause_analysis import RootCauseAnalysis
from app.schemas.violation_cluster import ViolationCluster
from app.schemas.evidence_metadata import EvidenceMetadata
from app.schemas.evidence_pack import EvidenceChunk, EvidencePack
from app.schemas.fund_family_analysis import FundFamilyAnalysis

# phase 3 dashboard schemas
from app.schemas.audit_trail_access import AuditTrailAccessMetrics
from app.schemas.realtime_monitoring import RealTimeMonitoringMetrics
from app.schemas.compliance_dashboard_kpis import ComplianceDashboardKPIs

# monitoring & alert schemas
from app.schemas.compliance_alert import ComplianceAlert, AlertSeverity, AlertStatus, EscalationTier

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
    # phase 1 metrics
    "RegulatoryMetadata", "FundAuditMetadata", "RemediationMetrics",
    "FeedbackQualityMetrics", "FeedbackCategoryAnalytics", "ResponseQualityMetrics",
    # phase 2 analysis
    "RootCauseAnalysis", "ViolationCluster", "EvidenceMetadata", "FundFamilyAnalysis",
    "EvidenceChunk", "EvidencePack",
    # phase 3 dashboard
    "AuditTrailAccessMetrics", "RealTimeMonitoringMetrics", "ComplianceDashboardKPIs",
    # alerts
    "ComplianceAlert", "AlertSeverity", "AlertStatus", "EscalationTier",
]




