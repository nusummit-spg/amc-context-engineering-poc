-- =============================================================================
-- SQL SCHEMA IMPLEMENTATION FOR AUDIT & COMPLIANCE EVIDENCE
-- =============================================================================
--
-- This file contains complete CREATE TABLE statements for SQLite/PostgreSQL
-- with indices, constraints, and sample data for the compliance audit system.
--
-- Version: 1.0
-- Created: 2026-09-02
-- Target DB: SQLite 3.x / PostgreSQL 14+
--
-- EXECUTION STEPS:
-- 1. Create tables in order (dependencies first)
-- 2. Add indices and constraints
-- 3. Run sample INSERT statements
-- 4. Verify with SELECT queries
--
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 1: audit_metadata
-- Primary audit execution tracking table
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_metadata (
    -- Identifiers
    audit_id               TEXT PRIMARY KEY,
    audit_run_timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- Scope & Context
    region                 TEXT NOT NULL CHECK (region IN ('SEBI', 'SEC', 'ESMA')),
    audit_type             TEXT NOT NULL CHECK (audit_type IN ('full_corpus', 'single_fund', 'batch', 'continuous')),
    funds_audited_count    INTEGER NOT NULL DEFAULT 0,
    funds_passed_count     INTEGER DEFAULT 0,
    funds_with_violations_count INTEGER DEFAULT 0,
    
    -- Rules & Violations
    total_rules_evaluated  INTEGER NOT NULL DEFAULT 0,
    total_violations_detected INTEGER NOT NULL DEFAULT 0,
    critical_violations    INTEGER DEFAULT 0,
    high_violations        INTEGER DEFAULT 0,
    medium_violations      INTEGER DEFAULT 0,
    low_violations         INTEGER DEFAULT 0,
    
    -- Performance Metrics
    audit_duration_ms      INTEGER DEFAULT 0,
    avg_rule_evaluation_ms FLOAT DEFAULT 0.0,
    p95_rule_evaluation_ms FLOAT DEFAULT 0.0,
    p99_rule_evaluation_ms FLOAT DEFAULT 0.0,
    
    -- Status & Audit Trail
    status                 TEXT NOT NULL DEFAULT 'started' CHECK (status IN ('started', 'in_progress', 'completed', 'failed')),
    triggered_by           TEXT,
    triggering_action      TEXT,
    error_message          TEXT,
    
    -- Compliance Assessment
    overall_compliance_score FLOAT DEFAULT 0.0,
    compliance_trend       TEXT DEFAULT 'stable' CHECK (compliance_trend IN ('improving', 'stable', 'declining')),
    
    -- Reference & Linking
    report_id              TEXT UNIQUE,
    escalation_triggered   BOOLEAN DEFAULT FALSE,
    
    -- Evidence Pack Reference
    evidence_pack_id       TEXT UNIQUE,
    evidence_manifest_json TEXT,
    
    -- Metadata
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    archived               BOOLEAN DEFAULT FALSE,
    
    -- Constraints
    UNIQUE(audit_run_timestamp, region, audit_type)
);

-- Indices for audit_metadata
CREATE INDEX IF NOT EXISTS idx_audit_region 
ON audit_metadata(region);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
ON audit_metadata(audit_run_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_status 
ON audit_metadata(status);

CREATE INDEX IF NOT EXISTS idx_audit_escalation 
ON audit_metadata(escalation_triggered);

CREATE INDEX IF NOT EXISTS idx_audit_evidence_pack 
ON audit_metadata(evidence_pack_id);

CREATE INDEX IF NOT EXISTS idx_audit_region_timestamp 
ON audit_metadata(region, audit_run_timestamp DESC);


-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 2: violations
-- Individual violations detected during audit
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS violations (
    -- Identifiers
    violation_id           TEXT PRIMARY KEY,
    audit_id               TEXT NOT NULL,
    rule_id                TEXT NOT NULL,
    fund_id                TEXT NOT NULL,
    
    -- Classification
    severity               TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    violation_type        TEXT NOT NULL CHECK (violation_type IN ('portfolio', 'governance', 'kyc', 'risk', 'reporting')),
    region                 TEXT NOT NULL CHECK (region IN ('SEBI', 'SEC', 'ESMA')),
    
    -- Finding Details
    description            TEXT NOT NULL,
    actual_value           TEXT,
    threshold_value        TEXT,
    gap_percentage         FLOAT,
    
    -- Confidence & Assessment
    confidence_score       FLOAT NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    evidence_count         INTEGER DEFAULT 0,
    
    -- Status & Resolution
    status                 TEXT NOT NULL DEFAULT 'detected' CHECK (status IN ('detected', 'reviewed', 'remediated', 'closed', 'waived')),
    
    -- Timeline
    detected_at            TEXT NOT NULL,
    reviewed_at            TEXT,
    resolved_at            TEXT,
    
    -- Resolution Action
    resolution_action      TEXT,
    resolved_by_user_id    TEXT,
    resolution_notes       TEXT,
    
    -- Evidence & Audit Trail (JSON columns)
    evidence_docs_json     TEXT,
    audit_trail_json       TEXT,
    
    -- Escalation
    escalation_level       INTEGER DEFAULT 0,
    escalation_triggered_at TEXT,
    escalation_path_id     TEXT,
    
    -- Metadata
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    created_by             TEXT,
    
    -- Foreign Keys
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id),
    UNIQUE(audit_id, rule_id, fund_id)
);

-- Indices for violations
CREATE INDEX IF NOT EXISTS idx_violation_audit 
ON violations(audit_id);

CREATE INDEX IF NOT EXISTS idx_violation_fund 
ON violations(fund_id);

CREATE INDEX IF NOT EXISTS idx_violation_rule 
ON violations(rule_id);

CREATE INDEX IF NOT EXISTS idx_violation_region 
ON violations(region);

CREATE INDEX IF NOT EXISTS idx_violation_severity 
ON violations(severity);

CREATE INDEX IF NOT EXISTS idx_violation_status 
ON violations(status);

CREATE INDEX IF NOT EXISTS idx_violation_detected_at 
ON violations(detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_violation_escalation 
ON violations(escalation_level);

-- Composite indices
CREATE INDEX IF NOT EXISTS idx_violation_region_severity 
ON violations(region, severity);

CREATE INDEX IF NOT EXISTS idx_violation_fund_status 
ON violations(fund_id, status);

CREATE INDEX IF NOT EXISTS idx_violation_created_at 
ON violations(created_at DESC);


-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 3: response_feedback
-- Human feedback on LLM responses and audit findings
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS response_feedback (
    -- Identifiers
    feedback_id            TEXT PRIMARY KEY,
    response_id            TEXT NOT NULL,
    interaction_id         TEXT NOT NULL,
    session_id             TEXT NOT NULL,
    
    -- Context
    turn_number            INTEGER NOT NULL,
    query_text             TEXT,
    
    -- User & Actor
    actor_id               TEXT,
    actor_role             TEXT,
    
    -- Classification & Feedback
    selected_categories    TEXT NOT NULL,  -- JSON array
   feedback_text              TEXT,
    
    -- Quality Scores (1-5 Likert)
    answer_relevance_score INTEGER CHECK (answer_relevance_score IS NULL OR (answer_relevance_score >= 1 AND answer_relevance_score <= 5)),
    source_quality_score   INTEGER CHECK (source_quality_score IS NULL OR (source_quality_score >= 1 AND source_quality_score <= 5)),
    completeness_score     INTEGER CHECK (completeness_score IS NULL OR (completeness_score >= 1 AND completeness_score <= 5)),
    
    -- Automated Classification
    automated_category     TEXT,
    automated_confidence   FLOAT CHECK (automated_confidence IS NULL OR (automated_confidence >= 0.0 AND automated_confidence <= 1.0)),
    
    -- Client Submission
    client_timestamp       TEXT,
    
    -- Audit Trail
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- Linking
    audit_id               TEXT,
    violation_id           TEXT,
    
    -- Constraints
    UNIQUE(response_id, actor_id),
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id)
);

-- Indices for response_feedback
CREATE INDEX IF NOT EXISTS idx_feedback_response 
ON response_feedback(response_id);

CREATE INDEX IF NOT EXISTS idx_feedback_session 
ON response_feedback(session_id);

CREATE INDEX IF NOT EXISTS idx_feedback_actor 
ON response_feedback(actor_id);

CREATE INDEX IF NOT EXISTS idx_feedback_role 
ON response_feedback(actor_role);

CREATE INDEX IF NOT EXISTS idx_feedback_created 
ON response_feedback(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_audit 
ON response_feedback(audit_id);


-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 4: query_evidence
-- Full query trace with LLM synthesis, citations, provenance
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS query_evidence (
    -- Identifiers
    response_id            TEXT PRIMARY KEY,
    session_id             TEXT NOT NULL,
    request_id             TEXT,
    
    -- Query Metadata
    query_text             TEXT NOT NULL,
    query_type             TEXT,
    query_intent           TEXT,
    
    -- Retrieval Mode
    retrieval_mode         TEXT NOT NULL DEFAULT 'contextgraph',
    serving_engine         TEXT,
    
    -- Full JSON Content
    assembled_context_json TEXT NOT NULL,
    synthesis_output_json  TEXT NOT NULL,
    graph_highlight_json   TEXT,
    traditional_result_json TEXT,
    
    -- Performance & Quality
    latency_ms             INTEGER,
    retrieval_latency_ms   INTEGER,
    synthesis_latency_ms   INTEGER,
    quality_score          FLOAT,
    confidence_level       TEXT CHECK (confidence_level IN ('high', 'medium', 'low', NULL)),
    
    -- Audit Linking
    audit_id               TEXT,
    linked_violations_json TEXT,
    
    -- Feedback & Corrections
    has_feedback           BOOLEAN DEFAULT FALSE,
    feedback_summary_json  TEXT,
    
    -- Metadata
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    archived               BOOLEAN DEFAULT FALSE,
    
    -- Foreign Keys
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id)
);

-- Indices for query_evidence
CREATE INDEX IF NOT EXISTS idx_query_session 
ON query_evidence(session_id);

CREATE INDEX IF NOT EXISTS idx_query_audit 
ON query_evidence(audit_id);

CREATE INDEX IF NOT EXISTS idx_query_confidence 
ON query_evidence(confidence_level);

CREATE INDEX IF NOT EXISTS idx_query_created 
ON query_evidence(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_query_has_feedback 
ON query_evidence(has_feedback);

CREATE INDEX IF NOT EXISTS idx_query_latency 
ON query_evidence(latency_ms);


-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 5: compliance_rules
-- Master reference for all compliance rules
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS compliance_rules (
    -- Identifiers
    rule_id                TEXT PRIMARY KEY,
    regulation_id          TEXT,
    
    -- Rule Metadata
    rule_type              TEXT NOT NULL CHECK (rule_type IN ('portfolio', 'governance', 'kyc', 'risk', 'reporting')),
    region                 TEXT NOT NULL CHECK (region IN ('SEBI', 'SEC', 'ESMA')),
    title                  TEXT NOT NULL,
    description            TEXT,
    
    -- Condition & Logic
    condition_plain_text   TEXT,
    condition_code_json    TEXT,
    
    -- Applicability
    applicable_categories  TEXT,  -- JSON array
    exclusions_json        TEXT,
    
    -- Enforcement
    severity               TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    enforcement_level      TEXT DEFAULT 'automatic',
    confidence_threshold   FLOAT DEFAULT 0.95 CHECK (confidence_threshold >= 0.0 AND confidence_threshold <= 1.0),
    
    -- Evidence Requirements
    required_evidence_types TEXT,  -- JSON array
    
    -- Versioning
    effective_from         TEXT,
    effective_to           TEXT,
    is_active              BOOLEAN DEFAULT TRUE,
    version_number         INTEGER DEFAULT 1,
    
    -- Source & Reference
    regulation_section     TEXT,
    document_url           TEXT,
    
    -- Metadata
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    last_modified_by       TEXT,
    
    -- Constraints
    UNIQUE(rule_id, region, version_number)
);

-- Indices for compliance_rules
CREATE INDEX IF NOT EXISTS idx_rule_region 
ON compliance_rules(region);

CREATE INDEX IF NOT EXISTS idx_rule_type 
ON compliance_rules(rule_type);

CREATE INDEX IF NOT EXISTS idx_rule_active 
ON compliance_rules(is_active);

CREATE INDEX IF NOT EXISTS idx_rule_severity 
ON compliance_rules(severity);


-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 6: fund_schemes
-- Master reference for all funds
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fund_schemes (
    -- Identifiers
    fund_id                TEXT PRIMARY KEY,
    isin                   TEXT UNIQUE,
    
    -- Fund Details
    name                   TEXT NOT NULL,
    fund_house             TEXT NOT NULL,
    category               TEXT,
    mandate                TEXT,
    risk_profile           TEXT,
    
    -- Financial Metrics
    aum_crores             FLOAT,
    nav_per_unit           FLOAT,
    
    -- Regulatory
    region                 TEXT NOT NULL CHECK (region IN ('SEBI', 'SEC', 'ESMA')),
    applicable_rules_json  TEXT,  -- JSON array
    
    -- Metadata
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- Constraints
    UNIQUE(fund_id, region)
);

-- Indices for fund_schemes
CREATE INDEX IF NOT EXISTS idx_fund_region 
ON fund_schemes(region);

CREATE INDEX IF NOT EXISTS idx_fund_category 
ON fund_schemes(category);

CREATE INDEX IF NOT EXISTS idx_fund_house 
ON fund_schemes(fund_house);


-- ─────────────────────────────────────────────────────────────────────────
-- TABLE 7: sessions (Optional - if not exists)
-- Chat/interaction session tracking
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
    -- Identifiers
    session_id             TEXT PRIMARY KEY,
    user_id                TEXT,
    
    -- Metadata
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at               TEXT,
    
    -- Context
    audit_id               TEXT,
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id)
);

-- Indices for sessions
CREATE INDEX IF NOT EXISTS idx_session_user 
ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_session_created 
ON sessions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_session_audit 
ON sessions(audit_id);


-- ═════════════════════════════════════════════════════════════════════════
-- SAMPLE DATA FOR TESTING
-- ═════════════════════════════════════════════════════════════════════════

-- Insert sample audit
INSERT OR IGNORE INTO audit_metadata (
    audit_id,
    region,
    audit_type,
    funds_audited_count,
    funds_passed_count,
    funds_with_violations_count,
    total_rules_evaluated,
    total_violations_detected,
    critical_violations,
    high_violations,
    overall_compliance_score,
    status,
    triggered_by,
    triggering_action
) VALUES (
    'audit_20260901_123456',
    'SEBI',
    'full_corpus',
    154,
    142,
    12,
    3080,
    12,
    2,
    5,
    92.5,
    'completed',
    'system',
    'scheduled'
);

-- Insert sample violation
INSERT OR IGNORE INTO violations (
    violation_id,
    audit_id,
    rule_id,
    fund_id,
    severity,
    violation_type,
    region,
    description,
    actual_value,
    threshold_value,
    gap_percentage,
    confidence_score,
    status,
    detected_at
) VALUES (
    'v_20260901_001',
    'audit_20260901_123456',
    'SEBI_EQUITY_EXPOSURE_MIN',
    'AXIS_BLUECHIP',
    'high',
    'portfolio',
    'SEBI',
    'Equity exposure 62% below minimum 65% for large-cap equity scheme',
    '0.62',
    '0.65',
    -4.6,
    0.98,
    'detected',
    '2026-09-01T10:30:15Z'
);

-- Insert sample fund
INSERT OR IGNORE INTO fund_schemes (
    fund_id,
    isin,
    name,
    fund_house,
    category,
    risk_profile,
    aum_crores,
    region
) VALUES (
    'AXIS_BLUECHIP',
    'INF846K01337',
    'Axis Bluechip Fund',
    'Axis Mutual Fund',
    'large_cap',
    'high',
    8500.50,
    'SEBI'
);

-- Insert sample compliance rule
INSERT OR IGNORE INTO compliance_rules (
    rule_id,
    region,
    rule_type,
    title,
    description,
    severity,
    enforcement_level,
    regulation_section,
    is_active
) VALUES (
    'SEBI_EQUITY_EXPOSURE_MIN',
    'SEBI',
    'portfolio',
    'Minimum Equity Exposure for Large-Cap Schemes',
    'Large-cap equity schemes must maintain minimum 65% equity exposure',
    'high',
    'automatic',
    'SEBI(MF)Regulations, 2017, Clause 49.1',
    TRUE
);


-- ═════════════════════════════════════════════════════════════════════════
-- VERIFICATION QUERIES
-- ═════════════════════════════════════════════════════════════════════════

-- View all audit runs
-- SELECT * FROM audit_metadata ORDER BY created_at DESC;

-- View violations for specific audit
-- SELECT * FROM violations WHERE audit_id = 'audit_20260901_123456' ORDER BY severity DESC;

-- View violations by severity (aggregation)
-- SELECT severity, COUNT(*) as count FROM violations GROUP BY severity;

-- View feedback by role
-- SELECT actor_role, COUNT(*) as count FROM response_feedback GROUP BY actor_role;

-- View query latency statistics
-- SELECT 
--   ROUND(AVG(latency_ms), 2) as avg_latency_ms,
--   ROUND(AVG(CAST(json_extract(synthesis_output_json, '$.confidence') AS REAL)), 2) as avg_confidence
-- FROM query_evidence
-- WHERE created_at >= date('now', '-7 days');

-- Compliance scorecard (per region, last 30 days)
-- SELECT
--   region,
--   COUNT(DISTINCT fund_id) as total_funds,
--   SUM(CASE WHEN status IN ('detected', 'reviewed') THEN 1 ELSE 0 END) as funds_with_violations,
--   ROUND(100.0 * (COUNT(DISTINCT fund_id) - SUM(CASE WHEN status IN ('detected', 'reviewed') THEN 1 ELSE 0 END)) / COUNT(DISTINCT fund_id), 2) as compliance_pct
-- FROM violations
-- WHERE created_at >= date('now', '-30 days')
-- GROUP BY region;


-- ═════════════════════════════════════════════════════════════════════════
-- MAINTENANCE SCRIPTS
-- ═════════════════════════════════════════════════════════════════════════

-- Archive old query evidence (>1 year, before cold storage)
-- UPDATE query_evidence SET archived = TRUE 
-- WHERE created_at < date('now', '-365 days') AND archived = FALSE;

-- Delete very old feedback (>3 years)
-- DELETE FROM response_feedback 
-- WHERE created_at < date('now', '-1095 days');

-- Check index fragmentation (SQLite)
-- PRAGMA index_info(idx_violation_region_severity);

-- Vacuum database (optimize storage)
-- VACUUM;

-- Export compliance scorecard to CSV (Python)
-- SELECT * FROM violations WHERE region='SEBI' 
-- ORDER BY detected_at DESC;


-- ═════════════════════════════════════════════════════════════════════════
-- END OF SCHEMA DEFINITION
-- ═════════════════════════════════════════════════════════════════════════

-- Total tables: 7 (audit_metadata, violations, response_feedback, query_evidence, compliance_rules, fund_schemes, sessions)
-- Total indices: 35+
-- Target latency: <100ms for all queries
-- Estimated storage: ~8 GB for 10 years of audit data
-- Retention policy: 7 years (SEBI requirement)
