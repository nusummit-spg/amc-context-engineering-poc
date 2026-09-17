# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# AMC Compliance Auditing System — Operations & Deployment Runbook

## Overview
The **AMC Compliance Auditing System** evaluates asset management fund schemes against regulatory requirements (SEBI, SEC, ESMA). It features a deterministic rules engine, 5 domain-specific compliance agents, SLA escalation routing, and real-time scorecards.

---

## 1. Prerequisites
- **Python**: 3.10+ / 3.12
- **FastAPI**: 0.115+
- **Neo4j**: 5.24+ (Optional for offline testing; engine features in-memory caching and graceful fallback)
- **FAISS & SentenceTransformers**: For embedding and semantic indexing

---

## 2. Architecture & Data Flow

```
[CSV Regulatory Seeds] ---> [ComplianceRulesIngester] ---> [Neo4j Compliance Graph]
                                                                  |
                                                                  v
[Fund Holdings & Metrics] -----------------------------> [Deterministic RulesEngine]
                                                                  |
                +-------------------------------------------------+-------------------------+
                |                                                 |                         |
                v                                                 v                         v
       [ViolationDetector]                            [5 Domain Agents]            [EscalationEngine]
   - audit_all_funds()                           - PortfolioAgent (15% limit)      - Critical: 1h SLA
   - /api/compliance/scorecard                   - GovernanceAgent (CFA/CAIA)      - High: 4h SLA
   - /api/compliance/violations                  - KYCAgent (365d freshness)       - Routing to CCO / Board
                                                 - RiskAgent (VaR / 5% Cash)
                                                 - ReportingAgent (21:00 NAV)
```

---

## 3. Deployment & Verification Steps

### Step 3.1: Run Schema & Data Ingestion
```bash
# Seed regulations, rules, and fund schemes
python -c "
import asyncio
from app.ingestion.compliance_rules_ingester import seed_compliance_data
async def main():
    res = await seed_compliance_data()
    print('Seed results:', res)
asyncio.run(main())
"
```

### Step 3.2: Verify REST API Endpoints
Start the FastAPI server:
```bash
uvicorn app.main:app --reload --port 8000
```

1. **Trigger Full Compliance Audit**:
   ```bash
   curl -X POST "http://localhost:8000/api/compliance/audit?region=SEBI"
   ```
2. **Fetch Real-Time Compliance Scorecard**:
   ```bash
   curl "http://localhost:8000/api/compliance/scorecard?region=SEBI"
   ```
3. **Query Active High/Critical Violations**:
   ```bash
   curl "http://localhost:8000/api/compliance/violations?region=SEBI&severity=high"
   ```
4. **Run 5-Agent Domain Audit on Single Fund**:
   ```bash
   curl -X POST "http://localhost:8000/api/compliance/agents/audit" \
        -H "Content-Type: application/json" \
        -d '{"fund_id": "Adani_Growth_2024"}'
   ```
5. **Remediate Violation**:
   ```bash
   curl -X POST "http://localhost:8000/api/compliance/violations/V_20240115_RULE_PORT_CONC_001/resolve" \
        -H "Content-Type: application/json" \
        -d '{"resolution_action": "Rebalanced technology holding to 14.2% within regulatory cap."}'
   ```

---

## 4. Troubleshooting
| Symptom | Cause | Solution |
|---|---|---|
| `Neo4j Connection Refused` | Neo4j server is offline or unreachable | The rules engine automatically falls back to in-memory caching and local seed rules. No action required for offline tests. |
| `0 Violations Detected` | Metric keys mismatch in fund payload | Ensure nested dictionary properties match rule conditions (e.g. `holdings.max_single_holding`). |
| `Low Scorecard Compliance %` | Active breaches in audited funds | Remediate violations via `/api/compliance/violations/{id}/resolve`. |
