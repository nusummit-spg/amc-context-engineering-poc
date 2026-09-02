// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// Author: NuSummit Developers
//
// Migration 001: Phase 1 Foundation Layer Metrics Constraints & Indices
// ===========================================================================

// ---------------------------------------------------------------------------
// 1. Node Key & Uniqueness Constraints (6 Constraints)
// ---------------------------------------------------------------------------

CREATE CONSTRAINT regulatory_meta_id IF NOT EXISTS 
  FOR (r:RegulatoryMetadata) REQUIRE r.metadata_id IS UNIQUE;

CREATE CONSTRAINT fund_meta_id IF NOT EXISTS 
  FOR (f:FundAuditMetadata) REQUIRE f.fund_id IS UNIQUE;

CREATE CONSTRAINT remediation_meta_id IF NOT EXISTS 
  FOR (rm:RemediationMetrics) REQUIRE rm.remediation_id IS UNIQUE;

CREATE CONSTRAINT feedback_qual_id IF NOT EXISTS 
  FOR (fq:FeedbackQualityMetrics) REQUIRE fq.quality_id IS UNIQUE;

CREATE CONSTRAINT feedback_cat_id IF NOT EXISTS 
  FOR (fca:FeedbackCategoryAnalytics) REQUIRE fca.analytics_id IS UNIQUE;

CREATE CONSTRAINT response_qual_id IF NOT EXISTS 
  FOR (rq:ResponseQualityMetrics) REQUIRE rq.response_quality_id IS UNIQUE;


// ---------------------------------------------------------------------------
// 2. High-Performance Query & Segment Indices (18 Performance Indices)
// ---------------------------------------------------------------------------

// Regulatory Indices
CREATE INDEX idx_regulatory_rule IF NOT EXISTS 
  FOR (r:RegulatoryMetadata) ON (r.rule_id);

CREATE INDEX idx_regulatory_source IF NOT EXISTS 
  FOR (r:RegulatoryMetadata) ON (r.regulation_source);

CREATE INDEX idx_regulatory_effective IF NOT EXISTS 
  FOR (r:RegulatoryMetadata) ON (r.effective_date);

// Fund Audit Metadata Indices
CREATE INDEX idx_fund_category IF NOT EXISTS 
  FOR (f:FundAuditMetadata) ON (f.fund_category);

CREATE INDEX idx_fund_amc IF NOT EXISTS 
  FOR (f:FundAuditMetadata) ON (f.amc_id);

CREATE INDEX idx_fund_manager IF NOT EXISTS 
  FOR (f:FundAuditMetadata) ON (f.fund_manager_id);

// Remediation & SLA Indices
CREATE INDEX idx_remediation_violation IF NOT EXISTS 
  FOR (rm:RemediationMetrics) ON (rm.violation_id);

CREATE INDEX idx_remediation_sla IF NOT EXISTS 
  FOR (rm:RemediationMetrics) ON (rm.sla_adherence);

CREATE INDEX idx_remediation_effectiveness IF NOT EXISTS 
  FOR (rm:RemediationMetrics) ON (rm.remediation_effectiveness);

// Feedback Quality Indices
CREATE INDEX idx_fq_feedback IF NOT EXISTS 
  FOR (fq:FeedbackQualityMetrics) ON (fq.feedback_id);

CREATE INDEX idx_fq_priority IF NOT EXISTS 
  FOR (fq:FeedbackQualityMetrics) ON (fq.priority_tier);

CREATE INDEX idx_fq_response IF NOT EXISTS 
  FOR (fq:FeedbackQualityMetrics) ON (fq.response_id);

// Feedback Category Analytics Indices
CREATE INDEX idx_fca_period IF NOT EXISTS 
  FOR (fca:FeedbackCategoryAnalytics) ON (fca.reporting_period);

CREATE INDEX idx_fca_category IF NOT EXISTS 
  FOR (fca:FeedbackCategoryAnalytics) ON (fca.category_id);

CREATE INDEX idx_fca_trend IF NOT EXISTS 
  FOR (fca:FeedbackCategoryAnalytics) ON (fca.trend);

// Response Quality Indices
CREATE INDEX idx_response_qual_response IF NOT EXISTS 
  FOR (rq:ResponseQualityMetrics) ON (rq.response_id);

CREATE INDEX idx_response_qual_model IF NOT EXISTS 
  FOR (rq:ResponseQualityMetrics) ON (rq.llm_model);

CREATE INDEX idx_response_qual_mode IF NOT EXISTS 
  FOR (rq:ResponseQualityMetrics) ON (rq.retrieval_mode);
