// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// Author: NuSummit Developers
//
// Migration 002: Phase 2 Analysis Layer Constraints, Indices & Relationships
// ===========================================================================

// ---------------------------------------------------------------------------
// 1. Node Key & Uniqueness Constraints (4 Constraints)
// ---------------------------------------------------------------------------

CREATE CONSTRAINT rca_meta_id IF NOT EXISTS 
  FOR (rca:RootCauseAnalysis) REQUIRE rca.rca_id IS UNIQUE;

CREATE CONSTRAINT violation_cluster_id IF NOT EXISTS 
  FOR (vc:ViolationCluster) REQUIRE vc.cluster_id IS UNIQUE;

CREATE CONSTRAINT evidence_meta_id IF NOT EXISTS 
  FOR (em:EvidenceMetadata) REQUIRE em.evidence_id IS UNIQUE;

CREATE CONSTRAINT fund_family_id IF NOT EXISTS 
  FOR (ffa:FundFamilyAnalysis) REQUIRE ffa.analysis_id IS UNIQUE;


// ---------------------------------------------------------------------------
// 2. High-Performance Query & Analytics Indices (8 Indices)
// ---------------------------------------------------------------------------

// RootCauseAnalysis Indices
CREATE INDEX idx_rca_violation IF NOT EXISTS 
  FOR (rca:RootCauseAnalysis) ON (rca.violation_id);

CREATE INDEX idx_rca_primary_cat IF NOT EXISTS 
  FOR (rca:RootCauseAnalysis) ON (rca.primary_category);

CREATE INDEX idx_rca_systemic IF NOT EXISTS 
  FOR (rca:RootCauseAnalysis) ON (rca.is_systemic);

// ViolationCluster Indices
CREATE INDEX idx_cluster_amc IF NOT EXISTS 
  FOR (vc:ViolationCluster) ON (vc.affected_amc_id);

CREATE INDEX idx_cluster_severity IF NOT EXISTS 
  FOR (vc:ViolationCluster) ON (vc.severity);

// EvidenceMetadata Indices
CREATE INDEX idx_evidence_doc IF NOT EXISTS 
  FOR (em:EvidenceMetadata) ON (em.document_id);

CREATE INDEX idx_evidence_hash IF NOT EXISTS 
  FOR (em:EvidenceMetadata) ON (em.document_hash);

// FundFamilyAnalysis Indices
CREATE INDEX idx_family_amc IF NOT EXISTS 
  FOR (ffa:FundFamilyAnalysis) ON (ffa.amc_id);

CREATE INDEX idx_family_systemic IF NOT EXISTS 
  FOR (ffa:FundFamilyAnalysis) ON (ffa.systemic_risk_flag);
