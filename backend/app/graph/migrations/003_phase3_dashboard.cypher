// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// Author: NuSummit Developers
//
// Migration 003: Phase 3 Dashboard Layer Constraints & Performance Indices
// ===========================================================================

// ---------------------------------------------------------------------------
// 1. Node Key & Uniqueness Constraints (3 Constraints)
// ---------------------------------------------------------------------------

CREATE CONSTRAINT audit_access_log_id IF NOT EXISTS 
  FOR (a:AuditTrailAccessMetrics) REQUIRE a.access_log_id IS UNIQUE;

CREATE CONSTRAINT rt_monitoring_id IF NOT EXISTS 
  FOR (m:RealTimeMonitoringMetrics) REQUIRE m.monitoring_id IS UNIQUE;

CREATE CONSTRAINT compliance_kpi_id IF NOT EXISTS 
  FOR (k:ComplianceDashboardKPIs) REQUIRE k.kpi_id IS UNIQUE;


// ---------------------------------------------------------------------------
// 2. High-Performance Dashboard Indices (4 Performance Indices)
// ---------------------------------------------------------------------------

CREATE INDEX idx_audit_access_user IF NOT EXISTS 
  FOR (a:AuditTrailAccessMetrics) ON (a.user_id);

CREATE INDEX idx_audit_access_time IF NOT EXISTS 
  FOR (a:AuditTrailAccessMetrics) ON (a.accessed_at);

CREATE INDEX idx_rt_monitoring_start IF NOT EXISTS 
  FOR (m:RealTimeMonitoringMetrics) ON (m.monitoring_window_start);

CREATE INDEX idx_kpi_reporting_date IF NOT EXISTS 
  FOR (k:ComplianceDashboardKPIs) ON (k.reporting_date);
