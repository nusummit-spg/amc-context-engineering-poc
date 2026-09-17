# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# AMC Compliance System — Incident Response & Remediation Runbook

## 1. Overview & Purpose
This runbook provides actionable procedures for managing compliance incidents, latency SLA breaches, data integrity issues, and disaster recovery events in the AMC Multi-Region Compliance Operations Suite.

---

## 2. Incident Severity Classification & SLA Matrix

| Severity Level | Response SLA | Target Resolution | Escalation Path | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Critical** | **15 minutes** | **< 4 hours** | Chief Compliance Officer (CCO), Head of Risk, Trustee Board | Breach of statutory investment limits (e.g. SEBI 15% single holding cap, SEC 5% limit, unhedged VaR > 4%) |
| **High** | **1 hour** | **< 24 hours** | Compliance Officer, Portfolio Manager | Re-KYC delinquency (>365 days), NAV publishing delay (>21:00 IST), Sector exposure breach |
| **Medium** | **4 hours** | **< 72 hours** | Senior Analyst, Compliance Team | Governance document expiry, missing trustee attestations |
| **Low** | **8 hours** | **< 7 days** | Operations Team | Minor reporting formatting discrepancies |

---

## 3. Incident Response Procedures

### 3.1 Scenario A: Critical Concentration Breach (Portfolio Agent)
1. **Detection**: Alert triggered on Prometheus (`CriticalComplianceViolationSpike`) or dashboard `/violations`.
2. **Immediate Action**:
   - Query violating fund via API:
     ```bash
     curl -s "http://localhost:8000/api/compliance/fund/{fund_id}/violations"
     ```
   - Notify Portfolio Manager and place temporary trade restriction on the affected security.
3. **Remediation**:
   - Rebalance portfolio to reduce asset holding below threshold.
   - Record resolution via `/api/compliance/violations/{id}/resolve` with `Role: resolver` or `Role: admin`:
     ```bash
     curl -X POST "http://localhost:8000/api/compliance/violations/{id}/resolve" \
       -H "X-User-Role: resolver" \
       -H "Content-Type: application/json" \
       -d '{"resolution_action": "Divested excess holding by 2.5% to comply with SEBI 10% limit"}'
     ```
4. **Post-Mortem**: Generate audit trail report (`GET /api/compliance/audit-report`) and file regulatory note.

---

### 3.2 Scenario B: Scorecard Latency SLA Breach (>500ms)
1. **Diagnosis**: Check `/api/compliance/health` and verify cache state.
2. **Action**:
   - Inspect scorecard cache TTL in `compliance.py` (default 60 seconds).
   - If Neo4j socket timeout occurred, verify container health:
     ```bash
     docker-compose ps neo4j
     ```
   - Restart cache or scale backend replicas via Kubernetes HPA:
     ```bash
     kubectl scale deployment compliance-api --replicas=5 -n amc-compliance
     ```

---

### 3.3 Scenario C: Disaster Recovery & Graph Database Restore
1. **Backup Verification**:
   - Inspect latest backup archive in `backups/compliance/`.
2. **Execute Restore**:
   - Run disaster recovery script:
     ```powershell
     .\scripts\restore_compliance_graph.ps1 -BackupFile "backups/compliance/neo4j_dump_latest.dump"
     ```
   - Or on Linux:
     ```bash
     ./scripts/restore_compliance_graph.sh backups/compliance/neo4j_dump_latest.dump
     ```
3. **Verify Integrity**:
   - Call `/api/compliance/load-rules` to warm the rules cache.
   - Check `/api/compliance/health` ensuring `neo4j_connected: true` and `rules_cached_count > 0`.
