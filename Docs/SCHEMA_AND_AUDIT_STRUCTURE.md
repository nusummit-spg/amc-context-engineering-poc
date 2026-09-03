# Schema & Audit Data Structure: JSON vs. Table Strategy

**Version**: 1.0  
**Date**: 2026-09-02  
**Owner**: Compliance Data Architecture  
**Status**: Ready for Implementation

---

## Executive Summary

This document provides a **definitive schema structure** and **JSON vs. table storage decision framework** for the Context Engineering Platform's audit and compliance evidence packs.

### Key Decisions

| Category | Storage | Rationale |
|----------|---------|-----------|
| **Audit Metadata** | **Table** | Fast queries, indexing, aggregations, reportable |
| **Violation Details** | **JSON (Table)** | Hybrid—stored as JSON in table for schema flexibility |
| **Query/Response Trace** | **JSON** | Unstructured LLM content, citations, provenance |
| **Feedback Evidence** | **Table** | Categorical data, human classifications, audit trails |
| **Compliance Facts** | **Table** | Reference data, rules, regulations, fund schemes |
| **Evidence Documents** | **File + Table** | Blobs on disk, metadata in table (keys) |

---

## Part 1: Complete Schema Definitions

### 1.1 Audit Metadata Table

**Purpose**: Track audit executions, provide audit trail, enable SLA reporting  
**Storage**: SQLite/PostgreSQL (Primary table)  
**Partition Key**: `audit_id` | `region` | `date_range`

```sql
CREATE TABLE audit_metadata (
    -- ─── Identifiers ──────────────────────────────────
    audit_id               TEXT PRIMARY KEY,
    audit_run_timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- ─── Scope & Context ──────────────────────────────
    region                 TEXT NOT NULL,  -- SEBI | SEC | ESMA
    audit_type             TEXT NOT NULL,  -- "full_corpus" | "single_fund" | "batch" | "continuous"
    funds_audited_count    INTEGER NOT NULL,
    funds_passed_count     INTEGER,
    funds_with_violations_count INTEGER,
    
    -- ─── Rules & Violations ───────────────────────────
    total_rules_evaluated  INTEGER NOT NULL,
    total_violations_detected INTEGER NOT NULL,
    critical_violations    INTEGER,
    high_violations        INTEGER,
    medium_violations      INTEGER,
    low_violations         INTEGER,
    
    -- ─── Performance Metrics ──────────────────────────
    audit_duration_ms      INTEGER,
    avg_rule_evaluation_ms FLOAT,
    p95_rule_evaluation_ms FLOAT,
    p99_rule_evaluation_ms FLOAT,
    
    -- ─── Status & Audit Trail ────────────────────────
    status                 TEXT NOT NULL,  -- "started" | "in_progress" | "completed" | "failed"
    triggered_by           TEXT,            -- user_id or system
    triggering_action      TEXT,            -- "manual_audit" | "scheduled" | "on_ingest" | "escalation"
    error_message          TEXT,
    
    -- ─── Compliance Assessment ────────────────────────
    overall_compliance_score FLOAT,         -- 0.0-100.0
    compliance_trend       TEXT,            -- "improving" | "stable" | "declining"
    
    -- ─── Reference & Linking ──────────────────────────
    report_id              TEXT UNIQUE,     -- Links to audit report (if generated)
    escalation_triggered   BOOLEAN DEFAULT FALSE,
    
    -- ─── Audit Evidence Pack ──────────────────────────
    evidence_pack_id       TEXT UNIQUE,     -- Links to evidence pack storage
    evidence_manifest_json TEXT,            -- JSON: {evidence_items: [...], hash, created_at}
    
    -- ─── Metadata ─────────────────────────────────────
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    archived               BOOLEAN DEFAULT FALSE,
    
    UNIQUE(audit_run_timestamp, region, audit_type)
);

-- ───────────────────────────────────────────────────────
-- INDICES for fast querying
-- ───────────────────────────────────────────────────────
CREATE INDEX idx_audit_region ON audit_metadata(region);
CREATE INDEX idx_audit_timestamp ON audit_metadata(audit_run_timestamp DESC);
CREATE INDEX idx_audit_status ON audit_metadata(status);
CREATE INDEX idx_audit_escalation ON audit_metadata(escalation_triggered);
CREATE INDEX idx_audit_evidence_pack ON audit_metadata(evidence_pack_id);
```

---

### 1.2 Violations Table

**Purpose**: Store individual violations with actionable details  
**Storage**: SQLite/PostgreSQL (Primary table)  
**Partition Key**: `region` | `violation_date` (monthly)

```sql
CREATE TABLE violations (
    -- ─── Identifiers ──────────────────────────────────
    violation_id           TEXT PRIMARY KEY,
    audit_id               TEXT NOT NULL,
    rule_id                TEXT NOT NULL,
    fund_id                TEXT NOT NULL,
    
    -- ─── Classification ───────────────────────────────
    severity               TEXT NOT NULL,  -- "critical" | "high" | "medium" | "low"
    violation_type        TEXT NOT NULL,  -- Rule type: "portfolio" | "governance" | "kyc" | "risk" | "reporting"
    region                 TEXT NOT NULL,  -- SEBI | SEC | ESMA
    
    -- ─── Finding Details ──────────────────────────────
    description            TEXT NOT NULL,
    actual_value           TEXT,           -- JSON-serialized actual value
    threshold_value        TEXT,           -- JSON-serialized threshold
    gap_percentage         FLOAT,          -- (actual - threshold) / threshold * 100
    
    -- ─── Confidence & Assessment ──────────────────────
    confidence_score       FLOAT NOT NULL, -- 0.0-1.0
    evidence_count         INTEGER DEFAULT 0,
    
    -- ─── Status & Resolution ──────────────────────────
    status                 TEXT NOT NULL DEFAULT "detected",  -- "detected" | "reviewed" | "remediated" | "closed" | "waived"
    
    -- ─── Timeline ─────────────────────────────────────
    detected_at            TEXT NOT NULL,
    reviewed_at            TEXT,
    resolved_at            TEXT,
    
    -- ─── Resolution Action ────────────────────────────
    resolution_action      TEXT,           -- Remediation description
    resolved_by_user_id    TEXT,
    resolution_notes       TEXT,           -- Additional context
    
    -- ─── Evidence & Audit Trail ───────────────────────
    evidence_docs_json     TEXT,           -- JSON array: [{doc_id, doc_type, page, snippet, score}, ...]
    audit_trail_json       TEXT,           -- JSON: {changes: [{timestamp, field, old_val, new_val, changed_by}, ...]}
    
    -- ─── Escalation ───────────────────────────────────
    escalation_level       INTEGER DEFAULT 0,  -- 0=unescalated, 1=L1, 2=L2, 3=Board
    escalation_triggered_at TEXT,
    escalation_path_id     TEXT,
    
    -- ─── Metadata ─────────────────────────────────────
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    created_by             TEXT,           -- audit system or manual entry
    
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id),
    UNIQUE(audit_id, rule_id, fund_id)  -- Per audit, rule, fund is unique
);

-- ───────────────────────────────────────────────────────
-- INDICES for querying & reporting
-- ───────────────────────────────────────────────────────
CREATE INDEX idx_violation_audit ON violations(audit_id);
CREATE INDEX idx_violation_fund ON violations(fund_id);
CREATE INDEX idx_violation_rule ON violations(rule_id);
CREATE INDEX idx_violation_region ON violations(region);
CREATE INDEX idx_violation_severity ON violations(severity);
CREATE INDEX idx_violation_status ON violations(status);
CREATE INDEX idx_violation_detected_at ON violations(detected_at DESC);
CREATE INDEX idx_violation_escalation ON violations(escalation_level);

-- ───────────────────────────────────────────────────────
-- Composite indices for common queries
-- ───────────────────────────────────────────────────────
CREATE INDEX idx_violation_region_severity ON violations(region, severity);
CREATE INDEX idx_violation_fund_status ON violations(fund_id, status);
```

---

### 1.3 Feedback Evidence Table

**Purpose**: Human feedback on responses and audit findings  
**Storage**: SQLite (Primary)  
**Partition Key**: `session_id` | `feedback_date`

```sql
CREATE TABLE response_feedback (
    -- ─── Identifiers ──────────────────────────────────
    feedback_id            TEXT PRIMARY KEY,
    response_id            TEXT NOT NULL,
    interaction_id         TEXT NOT NULL,
    session_id             TEXT NOT NULL,
    
    -- ─── Context ──────────────────────────────────────
    turn_number            INTEGER NOT NULL,
    query_text             TEXT,
    
    -- ─── User & Actor ─────────────────────────────────
    actor_id               TEXT,           -- User who provided feedback
    actor_role             TEXT,           -- "compliance_officer" | "analyst" | "reviewer" | "admin"
    
    -- ─── Classification & Feedback ────────────────────
    selected_categories    TEXT NOT NULL,  -- JSON array: ["answer_incorrect", "missing_source", "harmful", "unclear", ...]
    free_text              TEXT,           -- Detailed feedback from human
    
    -- ─── Relevance & Quality ──────────────────────────
    answer_relevance_score INTEGER,        -- 1-5 Likert scale
    source_quality_score   INTEGER,        -- 1-5: Were citations helpful?
    completeness_score     INTEGER,        -- 1-5: Was answer complete?
    
    -- ─── Taxonomy Classifier (Automated) ───────────────
    automated_category     TEXT,           -- Predicted category if auto-labeling enabled
    automated_confidence   FLOAT,          -- 0.0-1.0
    
    -- ─── Client Submission ─────────────────────────────
    client_timestamp       TEXT,           -- When feedback was submitted from client
    
    -- ─── Audit Trail ──────────────────────────────────
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- ─── Linking ──────────────────────────────────────
    audit_id               TEXT,           -- Nullable: if this feedback relates to compliance audit
    violation_id           TEXT,           -- Nullable: if feedback is about a violation finding
    
    UNIQUE(response_id, actor_id),
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id)
);

-- ───────────────────────────────────────────────────────
-- INDICES
-- ───────────────────────────────────────────────────────
CREATE INDEX idx_feedback_response ON response_feedback(response_id);
CREATE INDEX idx_feedback_session ON response_feedback(session_id);
CREATE INDEX idx_feedback_actor ON response_feedback(actor_id);
CREATE INDEX idx_feedback_role ON response_feedback(actor_role);
CREATE INDEX idx_feedback_category ON response_feedback(selected_categories);
CREATE INDEX idx_feedback_created ON response_feedback(created_at DESC);
```

---

### 1.4 Query & Synthesis Evidence (JSON in Table)

**Purpose**: Full query trace with LLM synthesis, citations, provenance  
**Storage**: PostgreSQL JSONB (structured + queryable) or SQLite JSON  
**Access Pattern**: Full content retrieval, audit lookups

```sql
CREATE TABLE query_evidence (
    -- ─── Identifiers ──────────────────────────────────
    response_id            TEXT PRIMARY KEY,
    session_id             TEXT NOT NULL,
    request_id             TEXT,           -- OpenTelemetry trace ID
    
    -- ─── Query Metadata ───────────────────────────────
    query_text             TEXT NOT NULL,
    query_type             TEXT,           -- "aggregation" | "comparison" | "direct_lookup" | "open_ended"
    query_intent           TEXT,           -- Classified intent
    
    -- ─── Retrieval Mode ───────────────────────────────
    retrieval_mode         TEXT NOT NULL,  -- "traditional" | "contextgraph" | "both"
    serving_engine         TEXT,           -- "legacy" | "v2_orchestrator"
    
    -- ─── Full JSON Content (Structured) ────────────────
    assembled_context_json TEXT NOT NULL,  -- JSON: {context_text, sources: [{source_index, document_id, chunk_id, snippet, score}, ...], quality_score, passed_quality_gate}
    
    synthesis_output_json  TEXT NOT NULL,  -- JSON: {answer, confidence, citations: [{source_index, document_title, verbatim_text}, ...], structured_rows, compliance_note}
    
    graph_highlight_json   TEXT,           -- JSON: {node_names, relationships, entities, labels}
    
    traditional_result_json TEXT,          -- JSON (if mode="both"): {files: [...], scores, reranking_info}
    
    -- ─── Performance & Quality ────────────────────────
    latency_ms             INTEGER,        -- End-to-end latency
    retrieval_latency_ms   INTEGER,        -- Just retrieval step
    synthesis_latency_ms   INTEGER,        -- Just LLM synthesis step
    
    quality_score          FLOAT,          -- 0.0-1.0 overall quality assessment
    confidence_level       TEXT,           -- "high" | "medium" | "low"
    
    -- ─── Audit Linking ────────────────────────────────
    audit_id               TEXT,           -- Which audit session, if any
    linked_violations_json TEXT,           -- JSON array: [violation_id, violation_id, ...]
    
    -- ─── Feedback & Corrections ───────────────────────
    has_feedback           BOOLEAN DEFAULT FALSE,
    feedback_summary_json  TEXT,           -- JSON: {categories, actor_feedback_count, issues_flagged}
    
    -- ─── Metadata ─────────────────────────────────────
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    archived               BOOLEAN DEFAULT FALSE,
    
    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id)
);

-- ───────────────────────────────────────────────────────
-- INDICES for retrieval
-- ───────────────────────────────────────────────────────
CREATE INDEX idx_query_session ON query_evidence(session_id);
CREATE INDEX idx_query_audit ON query_evidence(audit_id);
CREATE INDEX idx_query_confidence ON query_evidence(confidence_level);
CREATE INDEX idx_query_created ON query_evidence(created_at DESC);
CREATE INDEX idx_query_has_feedback ON query_evidence(has_feedback);
```

---

### 1.5 Compliance Rules Reference Table

**Purpose**: Master reference for all compliance rules (read-heavy, rarely updated)  
**Storage**: SQLite/PostgreSQL (Primary)

```sql
CREATE TABLE compliance_rules (
    -- ─── Identifiers ──────────────────────────────────
    rule_id                TEXT PRIMARY KEY,
    regulation_id          TEXT,
    
    -- ─── Rule Metadata ────────────────────────────────
    rule_type              TEXT NOT NULL,  -- "portfolio" | "governance" | "kyc" | "risk" | "reporting"
    region                 TEXT NOT NULL,  -- SEBI | SEC | ESMA
    title                  TEXT NOT NULL,
    description            TEXT,
    
    -- ─── Condition & Logic ────────────────────────────
    condition_plain_text   TEXT,           -- Human-readable condition
    condition_code_json    TEXT,           -- JSON: {logic_type, parameters, thresholds}
    
    -- ─── Applicability ────────────────────────────────
    applicable_categories  TEXT,           -- JSON array: ["large_cap", "mid_cap", ...]
    exclusions_json        TEXT,           -- JSON: {fund_ids: [...], categories: [...]}
    
    -- ─── Enforcement ──────────────────────────────────
    severity               TEXT,           -- "critical" | "high" | "medium" | "low"
    enforcement_level      TEXT,           -- "automatic" | "manual" | "advisory"
    confidence_threshold   FLOAT DEFAULT 0.95,
    
    -- ─── Evidence Requirements ────────────────────────
    required_evidence_types TEXT,          -- JSON array: ["fund_factsheet", "aum_report", "holdings_list"]
    
    -- ─── Effective & Versioning ───────────────────────
    effective_from         TEXT,
    effective_to           TEXT,
    is_active              BOOLEAN DEFAULT TRUE,
    version_number         INTEGER DEFAULT 1,
    
    -- ─── Source & Reference ───────────────────────────
    regulation_section     TEXT,           -- e.g., "SEBI(MF)Regulations, 2017, Clause 49.1"
    document_url           TEXT,
    
    -- ─── Metadata ─────────────────────────────────────
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    last_modified_by       TEXT,
    
    UNIQUE(rule_id, region, version_number)
);

-- ───────────────────────────────────────────────────────
-- INDICES
-- ───────────────────────────────────────────────────────
CREATE INDEX idx_rule_region ON compliance_rules(region);
CREATE INDEX idx_rule_type ON compliance_rules(rule_type);
CREATE INDEX idx_rule_active ON compliance_rules(is_active);
CREATE INDEX idx_rule_severity ON compliance_rules(severity);
```

---

### 1.6 Fund Schemes Reference Table

**Purpose**: Master reference for all funds  
**Storage**: SQLite/PostgreSQL (Primary)

```sql
CREATE TABLE fund_schemes (
    -- ─── Identifiers ──────────────────────────────────
    fund_id                TEXT PRIMARY KEY,
    isin                   TEXT UNIQUE,
    
    -- ─── Fund Details ─────────────────────────────────
    name                   TEXT NOT NULL,
    fund_house             TEXT NOT NULL,
    category               TEXT,           -- "large_cap" | "mid_cap" | "small_cap" | "equity_hybrid" | etc.
    mandate                TEXT,
    risk_profile           TEXT,           -- "low" | "moderate" | "high"
    
    -- ─── Financial Metrics ────────────────────────────
    aum_crores             FLOAT,          -- Assets Under Management
    nav_per_unit           FLOAT,
    
    -- ─── Regulatory ───────────────────────────────────
    region                 TEXT NOT NULL,  -- SEBI | SEC | ESMA
    applicable_rules_json  TEXT,           -- JSON array: [rule_id, rule_id, ...]
    
    -- ─── Metadata ─────────────────────────────────────
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(fund_id, region)
);

-- ───────────────────────────────────────────────────────
-- INDICES
-- ───────────────────────────────────────────────────────
CREATE INDEX idx_fund_region ON fund_schemes(region);
CREATE INDEX idx_fund_category ON fund_schemes(category);
CREATE INDEX idx_fund_house ON fund_schemes(fund_house);
```

---

### 1.7 Evidence Pack Manifest (JSON File)

**Purpose**: Bundle all evidence for an audit into a single navigable package  
**Storage**: JSON file on disk (`/audit_evidence_packs/`) + metadata in audit_metadata table  
**Format**: Hierarchical, compression-friendly

```json
{
  "evidence_pack_id": "evidence_20260901_audit_12345",
  "audit_id": "audit_20260901_123456",
  "created_at": "2026-09-01T10:31:45Z",
  "created_by_system": "compliance_engine_v3.0",
  
  "metadata": {
    "region": "SEBI",
    "total_funds_audited": 154,
    "total_violations": 12,
    "total_rules_evaluated": 3080,
    "compliance_score": 92.5,
    "audit_duration_ms": 1234,
    "manifest_hash": "sha256:abc123def456..."
  },
  
  "violation_summary": {
    "by_severity": {
      "critical": 2,
      "high": 5,
      "medium": 5,
      "low": 0
    },
    "by_type": {
      "portfolio": 4,
      "governance": 2,
      "kyc": 3,
      "risk": 2,
      "reporting": 1
    },
    "by_fund": {
      "AXIS_BLUECHIP": 2,
      "HDFC_GROWTH": 1,
      ...
    }
  },
  
  "violations": [
    {
      "violation_id": "v_20260901_001",
      "audit_id": "audit_20260901_123456",
      "fund_id": "AXIS_BLUECHIP",
      "fund_name": "Axis Bluechip Fund",
      "rule_id": "SEBI_EQUITY_EXPOSURE_MIN",
      "rule_title": "Minimum Equity Exposure for Large-Cap Schemes",
      "severity": "high",
      "confidence": 0.98,
      "detected_at": "2026-09-01T10:30:15Z",
      "status": "detected",
      
      "finding": {
        "description": "Equity exposure 62% below minimum 65% for large-cap equity scheme",
        "actual_value": 0.62,
        "threshold_value": 0.65,
        "gap_percentage": -4.6
      },
      
      "evidence": [
        {
          "evidence_id": "ev_001",
          "evidence_type": "fund_factsheet",
          "document_id": "doc_axis_bluechip_2026q3",
          "document_title": "Axis Bluechip Fund Factsheet Q3 2026",
          "page_number": 5,
          "snippet": "Portfolio Composition: Equity 62%, Debt 18%, Cash 20%",
          "score": 0.98,
          "extracted_values": {
            "equity_pct": 62,
            "debt_pct": 18,
            "cash_pct": 20
          }
        },
        {
          "evidence_id": "ev_002",
          "evidence_type": "holdings_list",
          "document_id": "doc_axis_holdings_2026_09_01",
          "page_number": 1,
          "snippet": "Top 10 Holdings constitute 35% of portfolio",
          "score": 0.92
        }
      ],
      
      "audit_trail": [
        {
          "timestamp": "2026-09-01T10:30:15Z",
          "action": "violation_detected",
          "details": "Rule SEBI_EQUITY_EXPOSURE_MIN evaluated against fund AXIS_BLUECHIP"
        }
      ]
    },
    ...
  ],
  
  "query_traces": [
    {
      "response_id": "resp_20260901_a1b2c3",
      "query_text": "What is the current equity exposure of Axis Bluechip Fund?",
      "query_type": "direct_lookup",
      "retrieval_mode": "contextgraph",
      "confidence": "high",
      "latency_ms": 234,
      
      "answer": "The current equity exposure of Axis Bluechip Fund is 62%, as reported in their Q3 2026 factsheet.",
      
      "citations": [
        {
          "citation_id": "[1]",
          "document_id": "doc_axis_bluechip_2026q3",
          "document_title": "Axis Bluechip Fund Factsheet Q3 2026",
          "page_number": 5,
          "verbatim_snippet": "Portfolio Composition: Equity 62%, Debt 18%, Cash 20%"
        }
      ],
      
      "graph_entities": ["Axis Bluechip Fund", "Large Cap Equity"],
      "linked_violations": ["v_20260901_001"]
    }
  ],
  
  "feedback_summary": {
    "total_feedback_records": 3,
    "feedback_by_role": {
      "compliance_officer": 2,
      "analyst": 1
    },
    "feedback_issues": {
      "answer_incomplete": 1,
      "missing_source": 0,
      "data_mismatch": 1,
      "unclear_language": 0
    }
  },
  
  "compliance_scorecard": {
    "overall_score": 92.5,
    "compliance_percentage": "92.5%",
    "funds_compliant": 142,
    "funds_non_compliant": 12,
    "compliance_trend": "stable",
    "generated_at": "2026-09-01T10:31:45Z"
  },
  
  "escalation_events": [
    {
      "escalation_id": "esc_20260901_001",
      "violation_id": "v_20260901_001",
      "escalated_at": "2026-09-01T10:35:00Z",
      "escalation_level": 2,
      "assigned_to": "compliance_lead_email@org.com",
      "sla_hours": 24,
      "status": "open"
    }
  ],
  
  "files": {
    "document_map": {
      "doc_axis_bluechip_2026q3": {
        "title": "Axis Bluechip Fund Factsheet Q3 2026",
        "file_path": "evidence_assets/doc_axis_bluechip_2026q3.pdf",
        "file_size_bytes": 245632,
        "content_hash": "sha256:xyz789..."
      },
      ...
    }
  }
}
```

---

## Part 2: JSON vs. Table Storage Decision Matrix

### 2.1 Storage Decision Framework

| **Data Category** | **Candidate Storage** | **Decision** | **Why** |
|---|---|---|---|
| **Audit Metadata** | Table / JSON | **TABLE** | Fast aggregations, SLA queries, indexing, historical trends |
| **Violations** | Table / JSON | **TABLE** | Need to filter, sort, aggregate, report by severity/status/region |
| **Query Evidence** | Table / JSON | **TABLE (JSON col)** | Store full trace as JSONB; index queryable fields |
| **Feedback** | Table / JSON | **TABLE** | Categorical + textual; need role/category/session indexing |
| **Compliance Rules** | Table / JSON | **TABLE** | Reference data; rarely changes; lookup-heavy |
| **Fund Schemes** | Table / JSON | **TABLE** | Reference data; lookup-heavy |
| **Evidence Manifest** | File / JSON | **FILE + Table** | Large unstructured bundle; metadata in table; content on disk |
| **Citation & Provenance** | Table / JSON | **JSON (in Table)** | Flexible schema; array of sources; store as JSONB |
| **Audit Trail** | Table / JSON | **TABLE** | Immutable append-only; timestamp indexed; compliance requirement |

---

### 2.2 Hybrid Approach: JSON Columns in Tables

**Best of both worlds**: Use JSONB columns in PostgreSQL or JSON in SQLite for flexible nested structures while maintaining queryability and performance.

```sql
-- Example: PostgreSQL JSONB
ALTER TABLE query_evidence 
ADD COLUMN assembled_context JSONB 
GENERATED ALWAYS AS (json_build_object(
  'context_text', assembled_context_json->'context_text',
  'quality_score', (assembled_context_json->>'quality_score')::float,
  'passed_quality_gate', (assembled_context_json->>'passed_quality_gate')::boolean
)) STORED;

CREATE INDEX idx_query_context_quality 
ON query_evidence USING gin(assembled_context);
```

---

### 2.3 Evidence Pack Storage Strategy

**Why separate files + metadata in table?**

1. **Immutability**: Evidence packs are audit-sealed; store once, never update
2. **Compliance**: Full audit trail in single ZIP/TAR archive with manifest signature
3. **Performance**: 500MB+ evidence packs don't belong in database
4. **Portability**: Ship evidence packs to external auditors, legal teams

**Directory Structure**:

```
/audit_evidence_packs/
├── evidence_20260901_audit_12345/
│   ├── manifest.json               # Metadata, violation summary
│   ├── violations.jsonl            # One violation per line (bulk load-friendly)
│   ├── query_traces.jsonl
│   ├── feedback.jsonl
│   ├── assets/
│   │   ├── doc_axis_bluechip_2026q3.pdf
│   │   ├── doc_hdfc_growth_2026q3.pdf
│   │   └── ...
│   ├── manifest.json.sig           # HMAC-SHA256 signature for tamper detection
│   └── evidence_20260901_audit_12345.tar.gz  # Compressed archive
├── evidence_20260902_audit_12346/
└── ...
```

**Access Pattern**:

```python
# 1. Query audit metadata from table (fast)
audit = db.query("SELECT * FROM audit_metadata WHERE audit_id = ?", [audit_id])
evidence_pack_id = audit.evidence_pack_id

# 2. Retrieve evidence pack manifest (fast, ~500KB JSON)
manifest = json.load(open(f"/audit_evidence_packs/{evidence_pack_id}/manifest.json"))

# 3. Stream violations from JSONL (efficient for large audits)
violations = (json.loads(line) for line in open(f"/audit_evidence_packs/{evidence_pack_id}/violations.jsonl"))

# 4. Access evidence documents as needed
for violation in violations:
    for evidence_item in violation.evidence:
        doc_path = f"/audit_evidence_packs/{evidence_pack_id}/assets/{evidence_item.document_id}.pdf"
        # Extract page, deliver to user
```

---

## Part 3: Audit Evidence Pack Contents (Complete Checklist)

### 3.1 Mandatory Evidence Items

Each audit evidence pack **MUST** contain:

**A. Audit Execution Records**
- [ ] Audit start timestamp, end timestamp, duration
- [ ] Region, audit type (full corpus / single fund / batch)
- [ ] Triggered by (user ID or system event)
- [ ] Triggering action description
- [ ] Neo4j query execution logs (query count, avg latency)
- [ ] Rule evaluation breakdown (rules evaluated per agent, time per rule)

**B. Violations & Findings**
- [ ] For each violation:
  - Violation ID, rule ID, fund ID
  - Severity, confidence score
  - Actual vs. threshold values
  - Finding description
  - Status (detected, reviewed, remediated, closed)
  - Supporting evidence references (document pages, snippets)
  - Audit trail (detection → review → resolution timeline)

**C. Query Traces (if audit involved LLM synthesis)**
- [ ] User query text
- [ ] Query classification (intent, type)
- [ ] Retrieved context (graph facts, vector chunks)
- [ ] LLM-generated answer
- [ ] Citations & inline references
- [ ] Confidence level
- [ ] Latency breakdown (retrieval, synthesis, total)
- [ ] Quality score

**D. Feedback & Corrections**
- [ ] For each feedback submission:
  - Actor (user ID, role)
  - Categories selected (answer_incorrect, missing_source, etc.)
  - Free-text feedback
  - Linked violation (if applicable)
  - Timestamp

**E. Supporting Documents**
- [ ] PDF factsheets, regulatory documents
- [ ] Holdings lists, financial reports
- [ ] Any external source referenced in violations or query traces

**F. Compliance Assessment**
- [ ] Overall compliance scorecard (% compliant funds, violations by severity)
- [ ] Compliance trend (improving, stable, declining)
- [ ] Escalation summary (critical violations requiring L2/L3 review)

**G. Audit Manifest & Integrity**
- [ ] Generation timestamp
- [ ] System version (compliance_engine_v3.0)
- [ ] Manifest hash (SHA-256 of all contents)
- [ ] HMAC signature (tamper detection)
- [ ] Evidence retention policy (e.g., "retain for 7 years")

---

### 3.2 Optional Evidence Items

Include if available/enabled:

- [ ] Neo4j graph snapshots (node/relationship counts per entity type)
- [ ] FAISS index metadata (embedding dimension, total vectors indexed)
- [ ] Performance profiling data (heap memory, CPU, latency percentiles)
- [ ] Escalation events (who approved what, when)
- [ ] Compliance rule version history (rules active at audit time)
- [ ] External audit team sign-off (if submitted for review)

---

## Part 4: Implementation Roadmap

### Phase 1: Schema Bootstrap (Week 1)

```bash
# 1. Create SQLite schema
sqlite3 logs/compliance_audit.db < schema_definitions.sql

# 2. Verify indices
.indices audit_metadata
.indices violations
.indices response_feedback

# 3. Test upsert operations
python scripts/test_upsert.py
```

### Phase 2: Evidence Pack Generation (Week 2)

```python
# app/compliance/evidence_pack_generator.py
class EvidencePackGenerator:
    def generate(self, audit_id: str) -> str:
        """
        Generates evidence pack directory and manifest.
        Returns: evidence_pack_id
        """
        # 1. Query audit_metadata from DB
        # 2. Collect violations from DB
        # 3. Collect query traces from DB
        # 4. Assemble manifest.json
        # 5. Copy source documents to assets/
        # 6. Create HMAC signature
        # 7. TAR.GZ compress
        # 8. Update audit_metadata.evidence_pack_id
        return evidence_pack_id
```

### Phase 3: Audit Trail & Query Evidence (Week 3)

```python
# app/retrieval/query_evidence_recorder.py
class QueryEvidenceRecorder:
    async def record_synthesis(
        self,
        response_id: str,
        query: str,
        assembled_context: AssembledContext,
        synthesis_output: SynthesisOutput,
        latency_ms: int,
        audit_id: Optional[str] = None
    ):
        """Record query trace to query_evidence table with JSONB columns."""
        # Serialize context, synthesis, citations to JSON
        # Insert with full traceability
        pass
```

### Phase 4: Feedback Integration (Week 4)

```python
# Existing: app/db/feedback.py
# Already has upsert_feedback() method
# Just update table schema to link audit_id, violation_id
```

---

## Part 5: Audit Evidence Pack - Complete Example

See section **1.7** above for full JSON structure.

**How to use:**

1. **For compliance officer**: Open `manifest.json`, scan violation_summary, drill into specific violations
2. **For auditor/external team**: Receive `evidence_20260901_audit_12345.tar.gz`, extract, verify signature, inspect manifest
3. **For system**: Load evidence pack into re-analysis engine (disputes, appeals, etc.)
4. **For archival**: Store with tamper-detection hash; retention policy = 7 years (SEBI requirement)

---

## Part 6: Performance & Scalability Targets

### Query Performance

| Query | Latency Target | Notes |
|-------|----------------|-------|
| `SELECT * FROM audit_metadata WHERE region='SEBI' ORDER BY audit_run_timestamp DESC LIMIT 10` | <50ms | 100K+ rows indexed by region + timestamp |
| `SELECT * FROM violations WHERE severity='critical' AND status='detected' AND region='SEBI'` | <100ms | Composite index on (region, severity, status) |
| `SELECT * FROM response_feedback WHERE session_id=? ORDER BY created_at DESC` | <30ms | Session PK lookup + ordering by created_at |
| `SELECT COUNT(*) FROM violations WHERE fund_id=? AND audit_id IN (...)` | <50ms | Index on (fund_id, audit_id) |
| Evidence pack ZIP generation | <5s | For 10,000 violations + 100 source documents |

### Storage Footprint

| Data | Volume | Size |
|------|--------|------|
| audit_metadata (10 years) | 52,560 rows | ~50 MB |
| violations (10 years) | 15.6M rows | ~6 GB (with indices) |
| response_feedback (10 years) | 2.5M rows | ~800 MB |
| query_evidence (10 years) | 5M rows | ~2 GB (with JSON columns) |
| evidence packs (on disk) | 52,560 packs × ~100 MB avg | ~5.3 TB (archive storage) |

---

## Part 7: Security & Compliance Considerations

### Data Protection

- **Encryption at rest**: All audit tables + evidence packs encrypted (AES-256)
- **Encryption in transit**: TLS 1.3 for all API transfers
- **Access control**: RBAC on audit_metadata, violations, query_evidence
- **Audit trail immutable**: All table changes logged to separate immutable_audit_log table

### Retention Policies

| Table | Retention | Reason |
|-------|-----------|--------|
| audit_metadata | 7 years | SEBI requirement |
| violations | 7 years | Evidence for compliance disputes |
| response_feedback | 3 years | Product improvement + training data |
| query_evidence | 1 year (archive after 90 days) | Debugging + pattern analysis |
| evidence packs | 7 years (archive to cold storage) | Legal holds + external audits |

### Compliance Certifications

- ✅ **SEBI Audit Trail**: All operations timestamped, user-attributed, immutable
- ✅ **SOC 2 Type II**: Encryption, access logs, retention policies
- ✅ **GDPR**: Personal data (actor_id, feedback, etc.) can be redacted; evidence packs anonymized if needed

---

## Part 8: Integration with Existing Components

### Integration Points

1. **Compliance Guardrails** (`app/compliance/compliance_guardrails.py`)
   - After rule evaluation → write violation to `violations` table
   - Include evidence docs references

2. **Synthesizer** (`app/retrieval/synthesizer.py`)
   - After LLM synthesis → call `QueryEvidenceRecorder.record_synthesis()`
   - Serialize AssembledContext + SynthesisOutput to JSONB

3. **Feedback Store** (`app/db/feedback.py`)
   - Already exists; update schema to add `audit_id`, `violation_id` FKs

4. **Escalation Engine** (`app/compliance/escalation_engine.py`)
   - When escalating violation → insert escalation_events entry in evidence pack manifest

5. **Reporting** (new)
   - Query `audit_metadata` + `violations` + `query_evidence` for dashboard/exports
   - Generate evidence pack manifest and ZIP

---

## Part 9: API Endpoints for Audit Evidence Access

### GET `/api/audit/{audit_id}/metadata`

Fetch audit metadata (response time: <50ms)

```json
{
  "audit_id": "audit_20260901_123456",
  "region": "SEBI",
  "total_funds_audited": 154,
  "total_violations": 12,
  "compliance_score": 92.5,
  "status": "completed",
  "evidence_pack_id": "evidence_20260901_audit_12345",
  "created_at": "2026-09-01T10:31:45Z"
}
```

### GET `/api/audit/{audit_id}/violations`

Fetch all violations from this audit with pagination

**Query Params**: `page=1&limit=50&severity=high&status=detected`

### GET `/api/audit/{audit_id}/evidence-pack`

Download evidence pack as ZIP (with signature verification)

### GET `/api/audit/{audit_id}/query-trace/{response_id}`

Fetch detailed query trace (full LLM synthesis + citations)

### GET `/api/audit/{audit_id}/feedback`

Fetch all human feedback for this audit session

### POST `/api/audit/{audit_id}/evidence-pack/verify`

Verify evidence pack integrity (HMAC signature + hash)

```json
{
  "evidence_pack_id": "evidence_20260901_audit_12345",
  "verified": true,
  "tamper_detected": false,
  "signature_timestamp": "2026-09-01T10:31:45Z",
  "retention_expires": "2033-09-01T23:59:59Z"
}
```

---

## Part 10: Sample Queries & Reports

### 10.1 Compliance Scorecard Query

```sql
SELECT
  region,
  COUNT(DISTINCT fund_id) as total_funds,
  SUM(CASE WHEN status IN ('detected', 'reviewed') THEN 1 ELSE 0 END) as funds_with_violations,
  ROUND(100.0 * (COUNT(DISTINCT fund_id) - SUM(CASE WHEN status IN ('detected', 'reviewed') THEN 1 ELSE 0 END)) / COUNT(DISTINCT fund_id), 2) as compliance_pct,
  SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) as critical_violations,
  SUM(CASE WHEN severity='high' THEN 1 ELSE 0 END) as high_violations
FROM violations
WHERE audit_id = ? AND created_at >= date('now', '-30 days')
GROUP BY region;
```

### 10.2 Violation Trends (30-day rolling)

```sql
SELECT
  DATE(created_at) as violation_date,
  severity,
  COUNT(*) as count,
  AVG(confidence_score) as avg_confidence
FROM violations
WHERE region = 'SEBI'
  AND created_at >= date('now', '-30 days')
GROUP BY DATE(created_at), severity
ORDER BY violation_date DESC;
```

### 10.3 Query Quality by Confidence Level

```sql
SELECT
  confidence_level,
  COUNT(response_id) as query_count,
  AVG(CAST(json_extract(synthesis_output_json, '$.confidence') AS REAL)) as avg_confidence,
  AVG(quality_score) as avg_quality_score,
  SUM(CASE WHEN has_feedback THEN 1 ELSE 0 END) as feedback_count
FROM query_evidence
WHERE created_at >= date('now', '-7 days')
GROUP BY confidence_level;
```

### 10.4 Feedback Issues by Category

```sql
SELECT
  actor_role,
  selected_categories,
  COUNT(*) as issue_count
FROM response_feedback
WHERE created_at >= date('now', '-30 days')
GROUP BY actor_role, selected_categories
ORDER BY issue_count DESC;
```

---

## Summary: Storage Decision Lookup

| **Need This...** | **Store Here** |
|---|---|
| Query audit status, SLA tracking, trend analysis | **audit_metadata table** |
| Individual violation details, drill-down reports, escalation routing | **violations table** |
| Human feedback for response quality, taxonomy classification | **response_feedback table** |
| Full query trace with LLM synthesis + citations + latency breakdown | **query_evidence table (JSONB column)** |
| Compliance rules (rarely updated, lookup-heavy) | **compliance_rules table** |
| Fund master data | **fund_schemes table** |
| Complete audit-sealed evidence bundle for external auditors | **evidence_pack JSON + file directory** |
| Large source documents (PDFs, holdings lists) | **assets/ directory inside evidence pack** |

---

## Conclusion

This schema design balances:
- **Queryability**: Fast SQL aggregations on audit_metadata, violations
- **Flexibility**: JSONB columns for unstructured query traces, citations
- **Auditability**: Immutable evidence packs, retention policies, HMAC signatures
- **Performance**: Indexed lookups <100ms, evidence pack generation <5s
- **Compliance**: SEBI audit trail, 7-year retention, external auditor access

Implement phases 1-4 over 4 weeks to achieve full audit evidence capture and reporting capability.

