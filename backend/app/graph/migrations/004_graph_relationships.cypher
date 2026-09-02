// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// Author: NuSummit Developers
//
// Migration 004: Audit Graph Relationships & Composite Indices
// ===========================================================================

// ---------------------------------------------------------------------------
// 1. Composite Query Performance Indices
// ---------------------------------------------------------------------------

CREATE INDEX idx_remediation_sla_violation IF NOT EXISTS 
  FOR (rm:RemediationMetrics) ON (rm.sla_adherence, rm.violation_id);

CREATE INDEX idx_audit_log_user_time IF NOT EXISTS 
  FOR (a:AuditTrailAccessMetrics) ON (a.user_id, a.accessed_at);


// ---------------------------------------------------------------------------
// 2. Core Compliance Graph Relationship Definitions
// ---------------------------------------------------------------------------

// Link Violations to Remediation Metrics
MATCH (v:ComplianceViolation), (rm:RemediationMetrics)
WHERE v.violation_id = rm.violation_id
MERGE (v)-[:TRACKED_BY]->(rm);

// Link Violations to Root Cause Analyses
MATCH (v:ComplianceViolation), (rca:RootCauseAnalysis)
WHERE v.violation_id = rca.violation_id
MERGE (v)-[:HAS_ROOT_CAUSE]->(rca);

// Link Root Cause Analyses to Systemic Violation Clusters
MATCH (rca:RootCauseAnalysis), (vc:ViolationCluster)
WHERE rca.cluster_id = vc.cluster_id
MERGE (rca)-[:PART_OF]->(vc);

// Link Violations to Supporting Evidentiary Documentation
MATCH (v:ComplianceViolation), (em:EvidenceMetadata)
WHERE v.violation_id = em.document_id OR em.document_id IN v.evidence_docs
MERGE (v)-[:SUPPORTED_BY]->(em);

// Link Funds to AMC Fund Family Analysis Nodes
MATCH (f:FundAuditMetadata), (ffa:FundFamilyAnalysis)
WHERE f.amc_id = ffa.amc_id
MERGE (f)-[:BELONGS_TO_FAMILY]->(ffa);
