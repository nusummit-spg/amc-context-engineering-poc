# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# AMC Compliance System — Production Deployment Guide

## 1. Architecture Overview
The AMC Multi-Region Compliance Operations Suite consists of:
- **FastAPI Core Service**: High-performance asynchronous REST API handling rule execution, domain agent orchestration, and RBAC authentication.
- **5 Autonomous Domain Agents**: Portfolio, Governance, KYC, Risk, and Reporting audit agents.
- **Streamlit Operations Hub**: 5-page enterprise dashboard for compliance monitoring, violation exploration, and SLA remediation.
- **Neo4j Graph Database**: Knowledge graph storing regulations, circulars, clauses, rules, funds, and immutable violation audit trails.
- **Redis (Optional)**: High-speed distributed cache and event queue.

---

## 2. Prerequisites & Environment Setup

### 2.1 System Requirements
- Kubernetes 1.25+ or Docker Engine 24.0+ / Docker Compose 2.20+
- Python 3.10+
- Minimum 4 CPU cores, 8GB RAM for full stack cluster

### 2.2 Environment Variables
| Variable | Description | Default |
| :--- | :--- | :--- |
| `APP_ENV` | Application environment (`production`, `staging`, `development`) | `production` |
| `NEO4J_URI` | Neo4j Bolt connection URI | `bolt://neo4j:7687` |
| `NEO4J_USER` | Neo4j authentication user | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j authentication password | `contextgraph` |
| `COMPLIANCE_ENCRYPTION_KEY` | 32-byte Fernet base64 encryption key | `secret` |
| `DEFAULT_REGION` | Default regulatory region (`SEBI`, `SEC`, `ESMA`) | `SEBI` |

---

## 3. Deployment Methods

### 3.1 Method A: Kubernetes Cluster Rollout
```bash
# 1. Create Namespace
kubectl apply -f deploy/k8s/namespace.yaml

# 2. Deploy ConfigMap and Secrets
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secrets.yaml

# 3. Deploy Backend & Services
kubectl apply -f deploy/k8s/backend-deployment.yaml
kubectl apply -f deploy/k8s/backend-service.yaml

# 4. Deploy Streamlit Dashboard & Ingress
kubectl apply -f deploy/k8s/dashboard-deployment.yaml
kubectl apply -f deploy/k8s/dashboard-service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
kubectl apply -f deploy/k8s/hpa.yaml

# 5. Verify Pod Health
kubectl get pods -n amc-compliance
```

### 3.2 Method B: Docker Compose Deployment
```bash
# Build and launch services
docker-compose up -d --build

# Inspect logs
docker-compose logs -f api streamlit
```

---

## 4. Verification & Smoke Testing
1. **Health Diagnostic Check**:
   ```bash
   curl -s http://localhost:8000/api/compliance/health | jq .
   ```
2. **Prometheus Metrics Probe**:
   ```bash
   curl -s http://localhost:8000/api/compliance/metrics/prometheus
   ```
3. **Scorecard SLA Latency Test**:
   ```bash
   curl -I http://localhost:8000/api/compliance/scorecard
   ```
   *Verify `X-Process-Time` is `< 500ms` and status is `200 OK`.*

4. **Multi-Agent Audit Trigger**:
   ```bash
   curl -X POST http://localhost:8000/api/compliance/agents/audit \
     -H "Content-Type: application/json" \
     -d '{"fund_id": "SEBI_FUND_001", "region": "SEBI"}'
   ```
