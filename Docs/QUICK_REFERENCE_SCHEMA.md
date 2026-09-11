# Quick Reference: Schema & Storage Decisions

**TL;DR Version** | Use this for quick lookups

---

## Storage Decision Matrix (One-Page)

```
┌─────────────────────────────┬──────────┬─────────────────────────┐
│ Data Category               │ Storage  │ Why                     │
├─────────────────────────────┼──────────┼─────────────────────────┤
│ Audit runs (start/end time) │ TABLE    │ Fast queries, SLA check │
│ Violations (500K+ rows)     │ TABLE    │ Aggregations, filters   │
│ Feedback (user ratings)     │ TABLE    │ Categorical + indexed   │
│ Query traces (JSON)         │ JSON col │ Flexible, semi-indexed  │
│ Compliance rules            │ TABLE    │ Reference data          │
│ Fund master data            │ TABLE    │ Lookup-heavy            │
│ Evidence bundles (1GB+)     │ FILE+DB  │ Audit-sealed archives   │
│ Source documents (PDFs)     │ FILE     │ In evidence pack dirs   │
│ Citations & provenance      │ JSON     │ Arrays, nested refs     │
│ Escalation events           │ JSON     │ In evidence manifest    │
└─────────────────────────────┴──────────┴─────────────────────────┘
```

---

## 7 Core Tables

### 1. **audit_metadata** (Primary)
Store: audit runs, scope, violation counts, compliance score, evidence_pack_id reference

Indices:
- `region` (SEBI|SEC|ESMA)
- `audit_run_timestamp` (DESC)
- `status` (started|completed|failed)
- `evidence_pack_id` (link to evidence)

### 2. **violations**
Store: individual violations with evidence references, status, resolution

Indices:
- `(region, severity, status)`
- `fund_id`
- `audit_id`
- `detected_at` (DESC)

### 3. **response_feedback**
Store: human feedback on query responses or violations, actor, categories

Indices:
- `session_id`
- `response_id`
- `actor_role`
- `created_at` (DESC)

### 4. **query_evidence** (JSON Columns)
Store: full query trace with synthesis output, citations, latency

Columns:
- `response_id` (PK)
- `assembled_context_json` (JSONB)
- `synthesis_output_json` (JSONB)
- `latency_ms` (INT, indexed)

### 5. **compliance_rules**
Store: rule definitions, conditions, applicability, effective dates

Indices:
- `(region, rule_type, is_active)`

### 6. **fund_schemes**
Store: fund metadata, AUM, category, applicable rules

Indices:
- `(region, category)`
- `fund_house`

### 7. **sessions** (Implicit)
Store: chat sessions, timestamps (may exist already)

Indices:
- `session_id` (PK)
- `created_at`

---

## Evidence Pack Structure (File-Based)

```
/audit_evidence_packs/
└── evidence_20260901_audit_12345/
    ├── manifest.json              ← Start here (violation summary, metadata)
    ├── violations.jsonl           ← One violation per line (streamed reads)
    ├── query_traces.jsonl         ← Query + synthesis + citations
    ├── feedback.jsonl             ← Human feedback records
    ├── compliance_scorecard.json  ← Overall % compliant, trend
    ├── assets/                    ← Source documents
    │   ├── doc_axis_bluechip_2026q3.pdf
    │   ├── doc_hdfc_growth_2026q3.pdf
    │   └── ...
    ├── manifest.json.sig          ← HMAC-SHA256 (tamper detection)
    └── evidence_20260901_audit_12345.tar.gz  ← Compressed archive
```

---

## Key Metrics to Store

### In Tables (Fast Queries)
- ✅ Audit timestamp, region, duration
- ✅ Violation count by severity
- ✅ Compliance score (%)
- ✅ Funds audited vs. compliant
- ✅ Rule evaluation latency (p95, p99)
- ✅ Escalation level, SLA hours

### In JSON (Structured Content)
- ✅ Full query text + answer (synthesis)
- ✅ Citations array with page/snippet
- ✅ Graph entities, relationships
- ✅ Evidence doc references
- ✅ Audit trail (timeline of changes)
- ✅ Feedback categories, free text
- ✅ Extracted values (actual vs. threshold)

### On Disk (Evidence Pack)
- ✅ Complete manifest (summary + details)
- ✅ Source PDFs, factsheets
- ✅ Violations list (JSONL format)
- ✅ Query traces with full provenance
- ✅ Integrity signature (HMAC)

---

## SQL Schema Skeleton

```sql
-- Minimal schema to get started

CREATE TABLE audit_metadata (
    audit_id TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    total_violations INTEGER,
    compliance_score FLOAT,
    evidence_pack_id TEXT UNIQUE,
    status TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    INDEX(region, created_at DESC)
);

CREATE TABLE violations (
    violation_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL,
    fund_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT DEFAULT 'detected',
    evidence_docs_json TEXT,  -- JSON array
    audit_trail_json TEXT,    -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(audit_id) REFERENCES audit_metadata(audit_id),
    INDEX(audit_id, severity, status)
);

CREATE TABLE response_feedback (
    feedback_id TEXT PRIMARY KEY,
    response_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    selected_categories TEXT NOT NULL,  -- JSON array
    actor_role TEXT,
    feedback_text TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    INDEX(session_id), INDEX(response_id)
);

CREATE TABLE query_evidence (
    response_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    assembled_context_json TEXT NOT NULL,  -- JSONB
    synthesis_output_json TEXT NOT NULL,   -- JSONB
    latency_ms INTEGER,
    confidence_level TEXT,
    audit_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    INDEX(session_id), INDEX(audit_id)
);
```

---

## What Goes Where: Decision Tree

```
┌─ Is it tabular, relational data?
│  YES → TABLE (with indices)
│  NO  → Next
│
├─ Is it frequently queried/filtered?
│  YES → TABLE (even if has nested JSON)
│  NO  → Next
│
├─ Is it >100MB unstructured content?
│  YES → FILE (+ metadata in table)
│  NO  → Next
│
└─ Is it flexible-schema (arrays, dicts)?
   YES → JSON column in table OR JSON file
   NO  → TABLE
```

---

## Evidence Pack Checklist

**Mandatory in every audit evidence pack:**

- [ ] Audit metadata (scope, duration, region)
- [ ] Violation list with evidence references
- [ ] Query traces (if LLM synthesis was used)
- [ ] Compliance scorecard (% funds compliant)
- [ ] Source documents (PDFs, holdings lists)
- [ ] Manifest JSON (summary + file listing)
- [ ] HMAC signature (tamper detection)

**Optional (context-dependent):**

- [ ] Feedback records (if audit involved human review)
- [ ] Escalation events (if any critical violations)
- [ ] Neo4j graph snapshot (if graph queries were involved)
- [ ] Performance profiling (latency, memory usage)

---

## Performance Targets

| Operation | Latency | Notes |
|-----------|---------|-------|
| Query: "list all critical violations for region SEBI" | <100ms | Indexed query on (region, severity, status) |
| Query: "get audit scorecard for audit_id X" | <50ms | Single-row lookup from audit_metadata |
| Query: "list feedback for session Y" | <30ms | Session_id index |
| Generate evidence pack (10K violations) | <5s | Serialize JSON, copy PDFs, compress |
| Download evidence pack (500MB ZIP) | <30s | Network-dependent; verify sig <2s |

---

## Implementation Checklist

### Week 1: Schema + Storage
- [ ] Define 7 tables (audit_metadata, violations, etc.)
- [ ] Create indices (composite indices for fast queries)
- [ ] Test upsert operations (violations, feedback)
- [ ] Verify latency targets (<100ms)

### Week 2: Evidence Pack Generation
- [ ] Implement `EvidencePackGenerator` class
- [ ] Generate manifest.json with violation summary
- [ ] Create JSONL files (violations, query_traces)
- [ ] Test ZIP compression + signature

### Week 3: Query Evidence Recording
- [ ] Update `synthesizer.py` to call `QueryEvidenceRecorder`
- [ ] Serialize AssembledContext + SynthesisOutput to JSONB
- [ ] Index by session_id, audit_id, confidence_level

### Week 4: API Endpoints
- [ ] GET `/api/audit/{audit_id}/metadata`
- [ ] GET `/api/audit/{audit_id}/violations`
- [ ] GET `/api/audit/{audit_id}/evidence-pack`
- [ ] GET `/api/audit/{audit_id}/query-trace/{response_id}`
- [ ] POST `/api/audit/{audit_id}/evidence-pack/verify`

---

## File Organization in Codebase

```
backend/
├── app/
│   ├── schemas/
│   │   ├── audit_trail_access.py     (existing, for access metrics)
│   │   ├── compliance_models.py      (extend with table schemas)
│   │   └── query.py                  (extend for query_evidence)
│   │
│   ├── db/
│   │   ├── feedback.py               (update: add audit_id, violation_id)
│   │   ├── audit.py                  (NEW: audit_metadata, violations)
│   │   └── evidence_pack.py           (NEW: EvidencePackGenerator)
│   │
│   ├── compliance/
│   │   ├── violation_detector.py     (update: write to violations table)
│   │   ├── escalation_engine.py      (update: link to evidence pack)
│   │   └── evidence_pack_generator.py (NEW)
│   │
│   ├── retrieval/
│   │   ├── synthesizer.py            (update: call QueryEvidenceRecorder)
│   │   └── query_evidence_recorder.py (NEW)
│   │
│   └── api/
│       ├── routes/
│       │   └── audit_evidence.py     (NEW: /audit/* endpoints)
│       └── ...
│
├── scripts/
│   ├── init_audit_schema.py          (NEW: create tables)
│   ├── test_schema_upsert.py         (NEW: verify indices)
│   └── ...
│
└── tests/
    ├── test_audit_schema.py          (NEW)
    ├── test_evidence_pack.py         (NEW)
    └── test_query_evidence.py        (NEW)
```

---

## Sample Queries for Reports

### Audit Scorecard (30-day trend)
```sql
SELECT
  DATE(created_at) as audit_date,
  region,
  AVG(overall_compliance_score) as avg_compliance,
  SUM(total_violations_detected) as total_violations
FROM audit_metadata
WHERE created_at >= date('now', '-30 days')
GROUP BY DATE(created_at), region;
```

### Critical Violations (active)
```sql
SELECT
  violation_id, fund_id, rule_id, severity,
  detected_at, resolution_action
FROM violations
WHERE severity = 'critical'
  AND status IN ('detected', 'reviewed')
  AND detected_at >= date('now', '-7 days')
ORDER BY detected_at DESC;
```

### Feedback Quality Issues
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

## Retention Policy Summary

| Table | Retention | Reason |
|-------|-----------|--------|
| audit_metadata | 7 years | SEBI compliance audit trail |
| violations | 7 years | Evidence for disputes/appeals |
| response_feedback | 3 years | Product improvement + training data |
| query_evidence | 1 year (90 days hot) | Debugging + pattern analysis |
| evidence_packs | 7 years (archive to cold storage) | Legal holds, external audits |

Archive strategy:
- **Hot** (0-90 days): SSD, actively queried
- **Warm** (90 days - 1 year): Archive storage (S3 Glacier), occasional retrieval
- **Cold** (1-7 years): Deep archive, legal hold only

---

## Example: Generating an Evidence Pack

```python
from app.compliance.evidence_pack_generator import EvidencePackGenerator
from app.db.audit import get_audit_metadata

# 1. Audit completes
audit_result = await compliance_orchestrator.audit_all_funds(region="SEBI")

# 2. Write violations to violations table
for violation in audit_result.violations:
    db.violations.insert(violation)

# 3. Generate evidence pack
generator = EvidencePackGenerator()
evidence_pack_id = generator.generate(
    audit_id=audit_result.audit_id,
    output_dir="/audit_evidence_packs"
)

# 4. Update audit metadata with reference
db.audit_metadata.update(
    audit_id=audit_result.audit_id,
    evidence_pack_id=evidence_pack_id,
    status="completed"
)

# 5. Return audit to user with evidence link
return {
    "audit_id": audit_result.audit_id,
    "evidence_pack_id": evidence_pack_id,
    "download_url": f"/api/audit/{audit_result.audit_id}/evidence-pack"
}
```

---

## End-to-End Example: Query + Audit Evidence

```python
# User submits query
query_response = await query_engine.query("What is Axis Bluechip's equity exposure?")

# 1. Synthesizer records query evidence
await query_evidence_recorder.record_synthesis(
    response_id=query_response.response_id,
    query=query_response.query,
    assembled_context=query_response.context,
    synthesis_output=query_response.synthesis,
    audit_id=current_audit_id  # If audit in progress
)

# 2. Storage: query_evidence table + JSON columns
# - response_id (PK)
# - assembled_context_json (JSONB) ← Full graph facts + chunks
# - synthesis_output_json (JSONB) ← Answer + citations + confidence
# - latency_ms (INT) ← 234
# - audit_id (FK)

# 3. For audit reporting, query evidence is included in manifest:
# {
#   "query_traces": [
#     {
#       "response_id": "resp_20260901_a1b2c3",
#       "query_text": "What is Axis Bluechip's equity exposure?",
#       "answer": "62%, as per Q3 2026 factsheet",
#       "citations": [{ "doc": "...", "page": 5, "snippet": "..." }],
#       "linked_violations": ["v_20260901_001"]
#     }
#   ]
# }

# 4. Human feedback links back:
feedback = {
    "response_id": "resp_20260901_a1b2c3",
    "actor_role": "compliance_officer",
    "selected_categories": ["answer_correct"],
    "audit_id": audit_id,  # Now trackable
    "violation_id": "v_20260901_001"  # If related
}
```

---

## Questions? Look Here

| Question | Answer | Location |
|----------|--------|----------|
| Where do I store large JSON objects? | JSONB column in table (queryable) or JSON file (if >100MB) | Section 1.4, 1.7 |
| How do I track who changed what? | Audit trail JSON column in violations table | violations.audit_trail_json |
| How do I ensure audit immutability? | HMAC-SHA256 signature on evidence pack manifest | evidence_pack_id.tar.gz.sig |
| How long must I keep evidence? | 7 years (SEBI requirement) | Retention policy section |
| How do I speed up queries? | Use composite indices (region, severity, status) | Section 2.2 |
| How do I generate audit reports? | Query audit_metadata + violations tables, build manifest.json | Part 5, Part 6 |

---

**Last Updated**: 2026-09-02 | **Schema Version**: 1.0 | **Status**: Ready for Implementation

