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
from app.models.documents import (
    Chunk,
    Document,
    DocumentCategory,
    DocumentType,
    IngestionJob,
    IngestionStatus,
    Section,
)

# entities
from app.models.entities import (
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
from app.models.relationships import (
    AffectsProperties,
    FlaggedInProperties,
    HoldsProperties,
    Relationship,
    RelationshipType,
    TaggedAsProperties,
)

# taxonomy
from app.models.taxonomy import (
    TaxonomyClassificationResult,
    TaxonomyNode,
    TaxonomyTag,
    TaxonomyTree,
)

# query
from app.models.query import (
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
from app.models.api import (
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
from app.models.regulatory_metadata import RegulatoryMetadata
from app.models.fund_metadata import FundAuditMetadata
from app.models.remediation_metrics import RemediationMetrics
from app.models.feedback_quality import FeedbackQualityMetrics
from app.models.feedback_analytics import FeedbackCategoryAnalytics
from app.models.response_quality import ResponseQualityMetrics

# phase 2 analysis schemas
from app.models.root_cause_analysis import RootCauseAnalysis
from app.models.violation_cluster import ViolationCluster
from app.models.evidence_metadata import EvidenceMetadata
from app.models.evidence_pack import EvidenceChunk, EvidencePack
from app.models.fund_family_analysis import FundFamilyAnalysis

# phase 3 dashboard schemas
from app.models.audit_trail_access import AuditTrailAccessMetrics
from app.models.realtime_monitoring import RealTimeMonitoringMetrics
from app.models.compliance_dashboard_kpis import ComplianceDashboardKPIs

# monitoring & alert schemas
from app.models.compliance_alert import ComplianceAlert, AlertSeverity, AlertStatus, EscalationTier

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




