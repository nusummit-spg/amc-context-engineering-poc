# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# Production Rollout Guide: Auto-Crawling & Dynamic Taxonomy Generation

**Document Status**: Phase 12 - Production Readiness  
**Last Updated**: 2026-08-24  
**Audience**: DevOps, System Administrators, Product Team

---

## 1. Pre-Rollout Checklist

### Engineering Sign-Off
- [ ] All 11 phases completed and tested (see `PHASES_SUMMARY.md`)
- [ ] Phase 11 regression tests pass: `pytest backend/app/engine/test_integration_full.py -v`
- [ ] No outstanding critical bugs in issue tracker
- [ ] Code review completed on all new modules
- [ ] Load testing results reviewed (target: 100 documents/minute ingestion rate)

### Legal & Compliance
- [ ] SEBI permission letter filed (Phase 0 legal kickoff) - **STATUS TO BE TRACKED SEPARATELY**
  - If letter not received: disable historical backfill in Phase 5; live RSS polling can proceed
- [ ] Data retention policy approved (regulatory documents: 7 years minimum)
- [ ] DPDP compliance audit completed (PII scrubbing enabled in config)
- [ ] Internal audit trail logging validated

### Operations & Infrastructure
- [ ] SQLite provenance database initialized and backed up daily
  - Location: `backend/app/engine/logs/provenance.db`
  - Backup cron: `0 2 * * * sqlite3 provenance.db ".backup provenance_$(date +\%Y\%m\%d).db"`
- [ ] Neo4j graph database backup strategy in place
- [ ] Log directory (`logs/`) monitored with rotation (30-day retention)
- [ ] Monitoring alerts configured (see Section 4)

### Stakeholder Training
- [ ] Admin UI operators trained on "Authorized Ingest" tab
- [ ] Compliance team trained on supersession review workflow
- [ ] Product team briefed on limitations (e.g., confidence thresholds for NER)

---

## 2. Environment Configuration

### `.env` Variables (Backend)

```bash
# ── ACQUISITION CHANNELS ──────────────────────────────────────
SEBI_RSS_URL=https://www.sebi.gov.in/rss/circulars_en.xml
AMFI_NAV_URL=https://www.amfiindia.com/spages/NAVAll.txt
AMFI_SID_SAI_URL=https://www.amfiindia.com/spages/SID_SAI_Listing_url.txt
MEMBER_PORTAL_INBOX=/data/member_inbox

# ── POLLING INTERVALS ─────────────────────────────────────────
SEBI_POLL_INTERVAL_MINUTES=240  # Every 4 hours
SEBI_DOWNLOAD_RATE_LIMIT=3      # Per minute

# ── RETRIEVAL ─────────────────────────────────────────────────
RETRIEVAL_ACTIVE_ONLY=true      # Hide superseded documents from searches
CACHE_GRAPH_MODE=memory          # Options: memory, redis, none

# ── NER CONFIGURATION ─────────────────────────────────────────
GLINER_MODEL_ID=urchade/gliner_medium-v2.1
GLINER_THRESHOLD=0.4             # Confidence threshold for NER extraction

# ── NEO4J ─────────────────────────────────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}  # Store in AWS Secrets Manager
NEO4J_DATABASE=neo4j

# ── FIBO MAPPING (Phase 6d) ──────────────────────────────────
FIBO_FUZZY_THRESHOLD=0.85        # Confidence for FIBO concept mapping
```

### Docker Compose (if containerized)

```yaml
version: '3.8'
services:
  backend:
    image: context-engineering:latest
    volumes:
      - ./logs:/app/logs
      - ./data/AMC:/app/data/AMC
      - ./data/member_inbox:/data/member_inbox
    environment:
      - SEBI_RSS_URL=${SEBI_RSS_URL}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
    depends_on:
      - neo4j
      - redis
    
  neo4j:
    image: neo4j:5.10
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
    volumes:
      - neo4j_data:/data
    
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  neo4j_data:
  redis_data:
```

---

## 3. Staged Rollout Plan

### Stage 1: Controlled Lab (Week 1)
**Channels Enabled**: Channel D (Admin) + Channel C (Member Portal)  
**Duration**: 1 week  
**Acceptance Criteria**:
- Admin users can successfully ingest documents via UI
- Member portal watcher detects and ingests files within 5 seconds
- No unhandled exceptions in logs
- Provenance ledger shows 100% successful ingestions

```bash
# Enable only admin and member channels
SEBI_POLL_INTERVAL_MINUTES=0  # Disabled
AMFI_FETCH_ENABLED=false
MEMBER_PORTAL_INBOX=/data/member_inbox_test
```

### Stage 2: AMFI Data (Week 2)
**Channels Enabled**: Channels B, C, D  
**Duration**: 1 week  
**Acceptance Criteria**:
- NAV/SID fetches succeed daily
- Taxonomy extraction produces ≥50 new fund houses/schemes
- No merge conflicts on `taxonomy.json`
- Drift detection sample shows <5% stale documents

```bash
AMFI_FETCH_ENABLED=true
SEBI_POLL_INTERVAL_MINUTES=0  # Still disabled
```

### Stage 3: Full Production (Week 3+)
**Channels Enabled**: All (A, B, C, D)  
**Duration**: Ongoing  
**Acceptance Criteria**:
- SEBI RSS polling runs every 4 hours
- ≥2 new circulars ingested per week
- Supersession detection rate: 5-15% of new docs (confidence-dependent)
- Admin confirms/rejects proposed edges within SLA (24 hours)
- Zero data loss events

```bash
# All channels enabled
SEBI_POLL_INTERVAL_MINUTES=240
AMFI_FETCH_ENABLED=true
```

---

## 4. Monitoring & Alerting

### Key Metrics (Dashboard)

1. **Ingestion Health**
   - Documents ingested per day
   - Duplicate rate (target: <2%)
   - Ingest latency p95 (target: <5s)
   - Failed ingestions (alert if >5%)

2. **Taxonomy Health**
   - New terms added per day
   - Taxonomy merge conflicts (alert if >0)
   - Taxonomy backup creation success rate (target: 100%)

3. **Supersession Workflow**
   - Proposed edges per day
   - Time-to-confirmation (target median: <12 hours)
   - False positive rate (monitor and tune confidence threshold)

4. **Data Quality**
   - NER extraction precision (sample audit monthly)
   - FIBO mapping coverage (target: ≥80% for fund houses)
   - Staleness drift alerts (investigate all critical)

### Alert Configuration

| Alert | Threshold | Action |
|-------|-----------|--------|
| Ingest failure rate | >5% | Page on-call; check error logs |
| Taxonomy merge failed | Any | P1 incident; manual merge review |
| RSS feed offline | 2 consecutive polls fail | P2; check connectivity; manual check SEBI site |
| Duplicate rate | >10% | P3; investigate dedup logic |
| Staleness critical drift | Any | P2; verify document authenticity |

### Log Aggregation

All pipeline execution logs written to:
- `logs/pipeline_execution.jsonl` (structured event log)
- `logs/sebi_poll_log.jsonl` (RSS polling details)
- `logs/member_portal_log.jsonl` (member inbox events)
- `logs/staleness_check_log.jsonl` (drift detection)

Aggregate with ELK stack or CloudWatch:
```bash
# CloudWatch tail (AWS)
aws logs tail /ecs/context-engineering/pipeline --follow

# Local JSON parsing
tail -f logs/pipeline_execution.jsonl | jq '.status, .sebi_rss.downloaded_count'
```

---

## 5. Rollback Procedures

### If Critical Issue Occurs

1. **Immediate**: Stop pipeline scheduler
   ```bash
   systemctl stop context-engineering-pipeline
   ```

2. **Assess**: Check logs for root cause
   ```bash
   tail -100 logs/pipeline_execution.jsonl | jq '.[] | select(.status != "success")'
   ```

3. **Containment**: Disable problematic channel(s) in `.env`
   ```bash
   # E.g., if SEBI RSS is crashing:
   SEBI_POLL_INTERVAL_MINUTES=0
   systemctl restart context-engineering-pipeline
   ```

4. **Recovery**: Restore taxonomy from backup
   ```bash
   # Restore to previous version
   python -c "
   from app.engine.taxonomy import list_taxonomy_versions, restore_taxonomy_version
   versions = list_taxonomy_versions()
   if versions:
       restore_taxonomy_version(versions[1][0])  # Second newest version
   "
   ```

5. **Provenance Ledger**: Rollback by updating document status
   ```python
   from app.engine.provenance_ledger import get_ledger, DocumentStatus
   ledger = get_ledger()
   ledger.update_status("problem_hash", DocumentStatus.REJECTED, 
                        reason="Rolled back due to incident XYZ")
   ```

### Channel Rollback Matrix

| Channel | Rollback Impact | Recovery Time |
|---------|-----------------|---------------|
| Admin (D) | Low; manual only | Immediate (disable UI tab) |
| Member Portal (C) | Low; local files | Immediate (stop watcher) |
| AMFI (B) | Medium; daily data | ~1 hour (skip 1 day) |
| SEBI RSS (A) | High; regulatory | ~4 hours (miss 1 poll cycle) |

---

## 6. Burn-In Period Checklist

Before declaring production-ready, complete a **4-week burn-in**:

### Week 1: Admin & Portal Only
- [ ] Zero admin UI crashes
- [ ] Member portal watcher survives 100+ file operations
- [ ] Provenance DB backup runs successfully daily
- [ ] Stakeholder feedback collected

### Week 2: Add AMFI Data
- [ ] NAV/SID fetches complete 14 times (daily + one extra)
- [ ] Taxonomy merged successfully 14 times
- [ ] Zero taxonomy conflicts
- [ ] Drift detection runs without errors
- [ ] Graph nodes created and searchable

### Week 3: Add SEBI RSS (Limited)
- [ ] RSS polling enabled at 4-hour intervals
- [ ] ≥2 new circulars detected
- [ ] PDF downloads complete successfully
- [ ] Supersession detection triggers (confidence >0.8)
- [ ] Admin review workflow used (proposed → confirm → graph link)

### Week 4: Full Operations
- [ ] All channels running nominal
- [ ] Metrics stable (no unexpected spikes)
- [ ] Pager duty integration tested (inject test alert)
- [ ] Disaster recovery drill: restore taxonomy from backup
- [ ] Full regression test suite passes again

### Sign-Off

Upon completion:

```
[X] Engineering Lead: ________________  Date: ________
[X] DevOps Lead: ____________________  Date: ________
[X] Product Manager: ________________  Date: ________
[X] Compliance Officer: _____________  Date: ________
```

---

## 7. Post-Rollout Operations

### Daily Tasks
- Monitor dashboard for anomalies
- Review overnight SEBI RSS polling results
- Check admin review queue (proposed supersessions)

### Weekly Tasks
- Audit ingest statistics and taxonomy growth
- Sample NER extraction results for precision
- Review staleness drift alerts

### Monthly Tasks
- Full regression test suite run
- Taxonomy version audit (check backup chain)
- Capacity planning review (database size trends)

### Quarterly Tasks
- FIBO mapping coverage review and tuning
- Confidence threshold review (adjust GLINER_THRESHOLD if needed)
- Legal/compliance review of ingested documents scope

---

## 8. Known Limitations & Workarounds

| Limitation | Workaround | Ticket |
|-----------|-----------|--------|
| GliNER NER can miss domain-specific terms | Monthly manual review + add to compliance_concepts keywords | BACKLOG-123 |
| SEBI RSS occasionally has malformed XML | Feed parser has error tolerance; manual PDF ingest via admin UI | BACKLOG-124 |
| AMFI NAV files sometimes have encoding issues | Fallback to UTF-8 error='ignore' mode | BACKLOG-125 |
| Concurrent write races on `taxonomy.json` rare but possible | Atomic write via temp file + rename mitigates; monitor provenance log | BACKLOG-126 |
| Historical SEBI backfill requires legal permission | Live RSS feed proceeds immediately; backfill waits for letter | LEGAL-001 |

---

## 9. Success Metrics (30-Day Review)

By end of Week 4:

- **Uptime**: ≥99.5% pipeline success rate
- **Latency**: P95 ingest latency <10s
- **Accuracy**: ≥90% of auto-proposed supersessions confirmed (no false positives)
- **Coverage**: Taxonomy grown by ≥100 new fund houses/schemes
- **Cost**: Compute/storage within budget projections
- **User Adoption**: 100% of admin users trained; feedback <3.0/5 → investigate

---

## 10. Escalation Path

### Critical Issues (Page On-Call)
- Pipeline crashed and not auto-recovering
- Provenance DB corruption detected
- Graph update failing systematically

### High Priority (Team Notified)
- Ingest failure rate >5%
- Taxonomy merge conflict
- Staleness drift on critical documents

### Medium Priority (Backlog)
- NER extraction precision trending down
- FIBO mapping coverage <80%
- Admin review SLA breached once

---

## Appendix: Module Dependencies

```
Pipeline Scheduler (orchestrator)
    ├─ SEBI Feed Ingester (Channel A)
    ├─ AMFI Portal Adapter (Channel B)
    ├─ Member Portal Watcher (Channel C)
    ├─ Admin UI (Channel D)
    └─ Ingestion Gateway (dedup + provenance)
        ├─ Provenance Ledger (SQLite)
        ├─ Taxonomy Extractor (6a-6g)
        │   ├─ Tabular NAV/SID extract
        │   ├─ NER Circular extract
        │   ├─ Normalization
        │   ├─ FIBO mapping
        │   ├─ Merge + versioning
        │   ├─ Graph node generation
        │   └─ NER hot-reload
        └─ Regulatory Lifecycle Enricher
            └─ Supersession Manager
                └─ Graph Store (Neo4j edges)
    
    └─ Staleness Monitor (drift detection)
    └─ Pipeline Scheduler (logging & metrics)
```

---

**End of Production Rollout Guide**

For questions or updates, contact: DevOps Team <devops@nusummit.tech>
