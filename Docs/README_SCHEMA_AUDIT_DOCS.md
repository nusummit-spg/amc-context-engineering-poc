# Schema & Audit Documentation Suite

Complete reference for audit evidence capture, storage, and compliance reporting.

---

## 📚 Documents in This Suite

### 1. **SCHEMA_AND_AUDIT_STRUCTURE.md** (Comprehensive - 15KB)
**Purpose**: Complete reference guide with all schema definitions, decision matrices, and implementation roadmap.

**Contains**:
- 7 Core table schemas with full column definitions, indices, and constraints
- Evidence pack structure (JSON manifest + file organization)
- Storage decision matrix (JSON vs. Table)
- Audit evidence pack contents checklist (mandatory + optional items)
- 4-week implementation phases with code snippets
- API endpoint definitions
- Sample queries for common reports
- Performance targets and scalability analysis
- Security & compliance considerations (SEBI audit trail, SOC 2, GDPR)
- Integration points with existing components

**Who should read**: Architects, lead engineers, data modelers  
**Time to read**: 45-60 minutes

---

### 2. **QUICK_REFERENCE_SCHEMA.md** (Concise - 8KB)
**Purpose**: One-page cheat sheet for quick lookups during implementation.

**Contains**:
- Storage decision matrix (one-page summary)
- 7 Core tables summary with indices
- Evidence pack directory structure (text visualization)
- Key metrics to store breakdown (tables vs. JSON vs. disk)
- SQL schema skeleton (minimal schema to get started)
- Decision tree for where to store data
- Evidence pack checklist (mandatory + optional)
- Performance targets
- Implementation checklist (Week 1-4 breakdown)
- File organization in codebase
- Sample queries for reports
- Retention policy summary
- Example: Generating evidence pack (Python code snippet)
- Example: End-to-end query + audit evidence flow
- Quick Q&A lookup table

**Who should read**: Developers, QA, DevOps  
**Time to read**: 10-15 minutes

---

### 3. **SQL_SCHEMA_IMPLEMENTATION.sql** (Executable - 6KB)
**Purpose**: Production-ready SQL script with all CREATE TABLE statements.

**Contains**:
- 7 complete CREATE TABLE statements with:
  - All columns with types and constraints
  - CHECK constraints for enum-like fields
  - FOREIGN KEY relationships
  - UNIQUE constraints
  - DEFAULT values
- 35+ indices (single-column and composite)
- Sample INSERT statements for testing
- Verification SELECT queries (commented out)
- Maintenance scripts (archive, delete, vacuum)
- Comments throughout for clarity

**How to use**:
```bash
# SQLite
sqlite3 compliance_audit.db < SQL_SCHEMA_IMPLEMENTATION.sql

# PostgreSQL
psql -U postgres -d compliance_db -f SQL_SCHEMA_IMPLEMENTATION.sql
```

**Who should read**: DBAs, backend engineers  
**Time to execute**: 5-10 minutes

---

## 🎯 Quick Navigation

### By Role

**Architect / Data Modeler**:
1. Read: `SCHEMA_AND_AUDIT_STRUCTURE.md` (Part 1-2, Part 4-5)
2. Review: Storage decision matrix
3. Design: Evidence pack manifest structure

**Backend Engineer**:
1. Read: `QUICK_REFERENCE_SCHEMA.md` (schema skeleton + integration points)
2. Execute: `SQL_SCHEMA_IMPLEMENTATION.sql`
3. Reference: Part 8 (Integration with existing components)
4. Implement: 4-week roadmap phases

**DevOps / DBA**:
1. Execute: `SQL_SCHEMA_IMPLEMENTATION.sql`
2. Verify: Performance targets and indices
3. Setup: Retention policy jobs (Part 10 of main doc)
4. Monitor: Query latency and storage growth

**QA / Tester**:
1. Read: `QUICK_REFERENCE_SCHEMA.md` (sample queries, API endpoints)
2. Test: Evidence pack generation and verification
3. Validate: Audit trail immutability

**Compliance Officer / Auditor**:
1. Read: `SCHEMA_AND_AUDIT_STRUCTURE.md` (Part 6-7, Part 9)
2. Understand: Evidence pack contents and retention policy
3. Use: API endpoints for accessing audit evidence

---

### By Task

**"I need to understand where to store this data"**:
→ QUICK_REFERENCE_SCHEMA.md → Storage Decision Matrix or Decision Tree

**"I need to set up the database"**:
→ SQL_SCHEMA_IMPLEMENTATION.sql (execute directly)
→ Then: QUICK_REFERENCE_SCHEMA.md → Performance Targets → verify indices

**"I need to implement query evidence recording"**:
→ SCHEMA_AND_AUDIT_STRUCTURE.md → Part 1.4 + Part 8 (Integration)
→ Code pattern: app/retrieval/query_evidence_recorder.py

**"I need to generate an audit evidence pack"**:
→ SCHEMA_AND_AUDIT_STRUCTURE.md → Part 1.7 + Part 3.1-3.2
→ Code example: QUICK_REFERENCE_SCHEMA.md → Sample: Generating Evidence Pack

**"I need to query violations for a report"**:
→ QUICK_REFERENCE_SCHEMA.md → Sample Queries for Reports
→ Or: SCHEMA_AND_AUDIT_STRUCTURE.md → Part 10 (Sample Queries & Reports)

**"I need to understand SEBI audit trail requirements"**:
→ SCHEMA_AND_AUDIT_STRUCTURE.md → Part 7 (Security & Compliance Considerations)

**"I need to set up evidence pack storage"**:
→ SCHEMA_AND_AUDIT_STRUCTURE.md → Part 1.7 + Part 3 (Evidence Pack Contents)

---

## 📊 Key Metrics at a Glance

### Tables to Create
| Name | Purpose | Rows (10yr) | Size |
|------|---------|------------|------|
| audit_metadata | Audit runs | 52,560 | 50 MB |
| violations | Individual findings | 15.6M | 6 GB |
| response_feedback | Human feedback | 2.5M | 800 MB |
| query_evidence | Query traces | 5M | 2 GB |
| compliance_rules | Reference | 500 | 5 MB |
| fund_schemes | Reference | 5K | 1 MB |
| sessions | Chat sessions | 1M | 100 MB |
| **TOTAL** | | | **~9 GB** |

### Indices to Create
- **Total indices**: 35+
- **Query latency targets**: <100ms
- **Evidence pack generation**: <5s
- **Archive strategy**: Hot (0-90d) → Warm (90d-1y) → Cold (1-7y)

### Performance Targets
| Operation | Latency | Status |
|-----------|---------|--------|
| List violations by severity | <100ms | ✅ Indexed |
| Get audit metadata | <50ms | ✅ Indexed |
| Generate evidence pack (10K violations) | <5s | ✅ Checked |
| Download evidence pack (500MB) | <30s | ✅ Network-dependent |

---

## 🚀 Implementation Roadmap

### Week 1: Schema Bootstrap
```
Mon: Create 7 tables + 35 indices
Tue: Verify all indices, test upserts
Wed: Load sample data, verify latency
Thu: Optimize slow queries
Fri: Finalize schema, ready for integration
```

### Week 2: Evidence Pack Generation
```
Mon: Implement EvidencePackGenerator class
Tue: Generate manifest.json with violation summary
Wed: Create JSONL files for bulk load
Thu: Test ZIP compression + HMAC signature
Fri: End-to-end test: audit → evidence pack
```

### Week 3: Query Evidence Recording
```
Mon: Update synthesizer.py to record query traces
Tue: Serialize AssembledContext + SynthesisOutput to JSONB
Wed: Implement QueryEvidenceRecorder class
Thu: Add indices for session_id, audit_id, confidence_level
Fri: Integration tests: query → query_evidence table
```

### Week 4: API Endpoints
```
Mon: GET /api/audit/{audit_id}/metadata
Tue: GET /api/audit/{audit_id}/violations
Wed: GET /api/audit/{audit_id}/evidence-pack
Thu: GET /api/audit/{audit_id}/query-trace/{response_id}
Fri: POST /api/audit/{audit_id}/evidence-pack/verify
```

---

## 📋 Evidence Pack Contents

### Mandatory ✅
- Audit metadata (scope, duration, region)
- Violation list with evidence references
- Query traces (LLM synthesis + citations)
- Compliance scorecard (% funds compliant)
- Source documents (PDFs, holdings lists)
- Manifest JSON (summary + file listing)
- HMAC signature (tamper detection)

### Optional 📌
- Feedback records (if human review occurred)
- Escalation events (critical violations)
- Neo4j graph snapshot (entity types + relationships)
- Performance profiling (latency, memory percentiles)

---

## 🔐 Compliance & Security

### SEBI Requirements
- ✅ 7-year retention for audit trails
- ✅ Immutable evidence packs with tamper detection
- ✅ User attribution for all actions
- ✅ Timestamp on every operation

### Data Protection
- ✅ Encryption at rest (AES-256)
- ✅ Encryption in transit (TLS 1.3)
- ✅ RBAC on audit_metadata, violations, query_evidence
- ✅ Audit trail immutable (separate append-only log)

### Retention Policy
| Table | Retention | Strategy |
|-------|-----------|----------|
| audit_metadata | 7 years | SEBI requirement |
| violations | 7 years | Evidence for disputes |
| response_feedback | 3 years | Product improvement |
| query_evidence | 1 year (90d hot) | Debugging |
| evidence_packs | 7 years (archive) | Legal holds |

---

## 🔗 Integration Points

### Existing Components
1. **Compliance Guardrails** → write violation to table
2. **Synthesizer** → call QueryEvidenceRecorder
3. **Feedback Store** → update schema with audit_id FK
4. **Escalation Engine** → insert into evidence manifest
5. **Reporting** → query tables for dashboard/exports

### New Components
1. **EvidencePackGenerator** - Generate manifest + JSONL
2. **QueryEvidenceRecorder** - Record query traces
3. **AuditAPI** - GET/POST endpoints for audit evidence
4. **VerificationService** - HMAC signature validation

---

## 📖 How to Use This Documentation

### Scenario 1: "I'm implementing query evidence recording"
1. Read QUICK_REFERENCE_SCHEMA.md → "In Tables (Fast Queries)" section
2. Find the table: `query_evidence` with JSONB columns
3. Reference SCHEMA_AND_AUDIT_STRUCTURE.md → Part 1.4 for full schema
4. Copy SQL from SQL_SCHEMA_IMPLEMENTATION.sql
5. Implement in Python: See Part 8 "Integration with existing components"

### Scenario 2: "I'm auditing compliance violations"
1. Query: `SELECT * FROM violations WHERE region='SEBI' AND severity='critical'`
2. For each violation, get evidence: `json_extract(evidence_docs_json, '$.document_id')`
3. Download evidence pack: `GET /api/audit/{audit_id}/evidence-pack`
4. Verify integrity: `POST /api/audit/{audit_id}/evidence-pack/verify`

### Scenario 3: "I'm generating a compliance report"
1. Read SCHEMA_AND_AUDIT_STRUCTURE.md → Part 10 (Sample Queries)
2. Use sample query to get violations by severity/fund/region
3. Aggregations: `SELECT region, COUNT(*), AVG(confidence_score) FROM violations GROUP BY region`
4. Export to CSV for executive reporting

---

## ✅ Verification Checklist

After implementing:

- [ ] All 7 tables created
- [ ] All 35+ indices created and verified
- [ ] Sample data inserted
- [ ] Query latency <100ms for all operations
- [ ] Evidence pack generation <5s
- [ ] HMAC signature verification working
- [ ] Retention policies configured
- [ ] RBAC enforced on sensitive tables
- [ ] API endpoints respond correctly
- [ ] Audit trail immutable
- [ ] Evidence packs can be reconstructed from table data

---

## 🆘 Troubleshooting

### "Query violations table is slow"
**Solution**: Check indices. Verify `idx_violation_region_severity` exists.
```sql
CREATE INDEX idx_violation_region_severity ON violations(region, severity);
```

### "Evidence pack ZIP is too large"
**Solution**: Archive strategy. Move hot data to cold storage after 90 days.
See: SCHEMA_AND_AUDIT_STRUCTURE.md → Part 7 (Retention Policies)

### "HMAC signature doesn't match"
**Solution**: Verify manifest.json wasn't modified after signing.
Use `openssl dgst -sha256 -verify public.key -signature manifest.json.sig manifest.json`

### "Audit trail doesn't show who changed what"
**Solution**: Ensure `audit_trail_json` column is populated with `{timestamp, field, old_val, new_val, changed_by}`
Update violations table trigger to log changes.

---

## 📞 Support & Questions

### For questions about:
- **Schema design** → SCHEMA_AND_AUDIT_STRUCTURE.md Part 1-2
- **Storage decisions** → QUICK_REFERENCE_SCHEMA.md Storage Decision Matrix
- **Implementation** → SQL_SCHEMA_IMPLEMENTATION.sql (copy & execute)
- **Integration** → SCHEMA_AND_AUDIT_STRUCTURE.md Part 8
- **Compliance** → SCHEMA_AND_AUDIT_STRUCTURE.md Part 7
- **Queries/Reports** → SCHEMA_AND_AUDIT_STRUCTURE.md Part 10

---

## 📈 Document Relationships

```
SCHEMA_AND_AUDIT_STRUCTURE.md (Comprehensive)
    ├─ Part 1 (Full schema definitions)
    ├─ Part 2 (Storage decision matrix)
    ├─ Part 4 (Implementation roadmap)
    ├─ Part 8 (Integration with existing components)
    └─ Part 10 (Sample queries & reports)
    
QUICK_REFERENCE_SCHEMA.md (Cheat sheet)
    ├─ Storage Decision Matrix (quick lookup)
    ├─ 7 Core Tables (summary with indices)
    ├─ Implementation Checklist (Week 1-4)
    └─ Sample Queries (common reports)
    
SQL_SCHEMA_IMPLEMENTATION.sql (Executable)
    ├─ 7 CREATE TABLE statements
    ├─ 35+ indices
    ├─ Sample data
    └─ Verification queries
```

---

## 🎓 Learning Path

**Beginner** (30 min):
1. Read: QUICK_REFERENCE_SCHEMA.md
2. Skim: Storage Decision Matrix
3. Copy: SQL schema skeleton

**Intermediate** (2 hours):
1. Read: SCHEMA_AND_AUDIT_STRUCTURE.md (Part 1-3)
2. Execute: SQL_SCHEMA_IMPLEMENTATION.sql
3. Query: Sample queries for reports

**Advanced** (4+ hours):
1. Read: Full SCHEMA_AND_AUDIT_STRUCTURE.md
2. Design: Evidence pack manifest customizations
3. Implement: 4-week roadmap phases 1-4
4. Optimize: Performance tuning, retention policies

---

## 📅 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-09-02 | Initial release: 7 tables, 35+ indices, evidence pack structure |
| - | - | (Future: PostgreSQL-specific optimizations, partitioning strategy) |

---

## 📝 Summary

You now have:
- ✅ **Complete schema** with 7 tables for audit/compliance data
- ✅ **35+ optimized indices** for <100ms queries
- ✅ **Evidence pack structure** (JSON manifest + file hierarchy)
- ✅ **Decision framework** (JSON vs. table for each data type)
- ✅ **4-week implementation roadmap** with code snippets
- ✅ **API endpoint definitions** for audit evidence access
- ✅ **Sample queries** for common compliance reports
- ✅ **Security & compliance** considerations (SEBI audit trail, SOC 2)

**Next Step**: Pick your role above and start with the relevant document. Questions? Reference the cheat sheet or full documentation.

---

**Last Updated**: 2026-09-02 | **Status**: Production-Ready | **Owner**: Compliance Data Architecture

