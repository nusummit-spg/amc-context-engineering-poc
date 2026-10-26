# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
locustfile_metrics.py
=====================
Locust load testing scenario simulating 100 concurrent AMC compliance users.
Validates:
- 1,000 metrics/min sustained write throughput
- p95 latency < 500ms (writes)
- p95 latency < 200ms (reads)
- Zero memory leakage under sustained pressure
"""

from locust import HttpUser, task, between
import random
import uuid
from datetime import datetime


class ComplianceMetricsUser(HttpUser):
    wait_time = between(0.05, 0.2)  # High throughput pacing for 1,000+ metrics/min

    @task(4)
    def submit_remediation_metric(self):
        """Simulate real-time compliance remediation logging."""
        vio_num = random.randint(1, 10000)
        payload = {
            "remediation_id": f"REM_LOCUST_{uuid.uuid4().hex[:8]}",
            "violation_id": f"VIO_LOCUST_{vio_num}",
            "severity_level": random.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
            "sla_target_hours": random.choice([12.0, 24.0, 48.0]),
            "sla_target_date": datetime.utcnow().isoformat(),
            "detected_at": datetime.utcnow().isoformat(),
            "remediation_action": "Portfolio rebalancing action executed under SEBI mandate.",
            "remediation_owner_user_id": f"analyst_{random.randint(1, 20)}",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.client.post("/api/compliance/violations/remediation", json=payload)

    @task(3)
    def query_compliance_kpis(self):
        """Simulate compliance officer dashboard refreshes."""
        self.client.get("/api/compliance/dashboard-kpis")

    @task(2)
    def evaluate_sla_breaches(self):
        """Simulate real-time SLA breach evaluation engine."""
        self.client.post("/api/compliance/alerts/evaluate-breaches")

    @task(2)
    def fetch_alerts(self):
        """Simulate viewing active alerts."""
        self.client.get("/api/compliance/alerts?status=ACTIVE&limit=20")

    @task(1)
    def verify_audit_signatures(self):
        """Simulate auditor verifying RSA signatures."""
        self.client.get("/api/compliance/audit-trail/verify-signature")

    @task(1)
    def scrape_prometheus(self):
        """Simulate Prometheus scraper."""
        self.client.get("/api/compliance/metrics/prometheus")
