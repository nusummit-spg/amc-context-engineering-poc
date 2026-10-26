# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
locustfile_amc_journey.py
=========================
Locust load testing suite simulating realistic concurrency profiles (10, 25, 50 concurrent users)
across the AMC Platform lifecycle:
  - Query & Search
  - Health & Metrics Inspection
  - Feedback Submission
  - Passive Follow-up Detection
  - Governance Queue Inspection
"""
import random
import uuid
from locust import HttpUser, between, task


class AMCPlatformUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.session_id = f"locust_sess_{uuid.uuid4().hex[:8]}"
        self.last_response_id = None
        self.last_query = "What is the TER of Axis Bluechip Fund?"

    @task(5)
    def check_health(self):
        """Simulate frequent container health probes."""
        self.client.get("/health")

    @task(4)
    def fetch_metrics_summary(self):
        """Simulate telemetry dashboards polling operational metrics."""
        self.client.get("/api/metrics/summary")

    @task(3)
    def view_metrics_dashboard(self):
        """Simulate operators viewing HTML dashboard."""
        self.client.get("/metrics/dashboard")

    @task(2)
    def scrape_prometheus(self):
        """Simulate Prometheus agent scraping metrics."""
        self.client.get("/api/metrics/prometheus")

    @task(4)
    def execute_query(self):
        """Simulate user querying mutual fund information."""
        funds = ["Axis Bluechip Fund", "HDFC Top 100 Fund", "Mirae Asset Large Cap Fund", "SBI Small Cap Fund"]
        attributes = ["TER", "NAV", "AUM", "Exit Load"]
        query_text = f"What is the {random.choice(attributes)} of {random.choice(funds)}?"
        self.last_query = query_text

        resp = self.client.post(
            "/api/query",
            json={
                "query": query_text,
                "session_id": self.session_id,
            },
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                self.last_response_id = data.get("response_id")
            except Exception:
                pass

    @task(2)
    def test_follow_up_correction_detection(self):
        """Simulate passive correction detection upon follow-up interaction."""
        if not self.last_response_id:
            return

        payload = {
            "session_id": self.session_id,
            "previous_response_id": self.last_response_id,
            "original_query": self.last_query,
            "original_response": "The Total Expense Ratio (TER) is 0.79%.",
            "follow_up_query": "Actually, the TER is 0.82% according to the latest factsheet.",
            "session_history": [self.last_query],
        }
        self.client.post("/api/feedback/follow-up-detection", json=payload)

    @task(1)
    def inspect_governance_queue(self):
        """Simulate compliance officer inspecting pending governance patches."""
        self.client.get("/api/governance/pending-corrections")
