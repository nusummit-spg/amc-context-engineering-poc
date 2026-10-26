# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Tests for Structured JSON Logging, Correlation IDs, and Metrics Dashboard & Prometheus endpoints."""
import json
import logging
from io import StringIO
import pytest
from fastapi.testclient import TestClient

from app.core.logging import JSONFormatter, set_correlation_ids, get_current_request_id, get_current_session_id
from app.core.errors import get_error_tracker
from app.core.metrics import get_metrics_store, QueryMetrics, ComponentMetric
from app.main import app

client = TestClient(app)


def test_json_formatter_outputs_valid_json():
    """Verify that JSONFormatter outputs compliant JSON with structured fields."""
    formatter = JSONFormatter()
    logger = logging.getLogger("test.json.formatter")
    logger.setLevel(logging.INFO)

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    try:
        # Set correlation IDs in context
        set_correlation_ids(request_id="req_test_1234", session_id="sess_test_5678")
        logger.info("Executing retrieval test", extra={"custom_tag": "test_tag_value"})

        output = stream.getvalue().strip()
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.json.formatter"
        assert data["message"] == "Executing retrieval test"
        assert data["request_id"] == "req_test_1234"
        assert data["session_id"] == "sess_test_5678"
        assert data["custom_tag"] == "test_tag_value"
        assert "timestamp" in data
        assert "line" in data
    finally:
        logger.removeHandler(handler)
        set_correlation_ids(request_id="", session_id="")


def test_error_tracker_metrics():
    """Verify ErrorTracker counts 4xx/5xx and computes correct error rate."""
    tracker = get_error_tracker()
    tracker.clear()

    tracker.record_request()
    tracker.record_request()
    tracker.record_request()
    tracker.record_request()

    tracker.record_error(status_code=404, error_code="not_found", message="Resource not found", path="/test")
    tracker.record_error(status_code=500, error_code="internal_error", message="Internal error", path="/test")

    summary = tracker.summary()
    assert summary["total_requests"] == 4
    assert summary["errors_4xx"] == 1
    assert summary["errors_5xx"] == 1
    assert summary["total_errors"] == 2
    assert summary["error_rate"] == 0.5
    assert len(summary["recent_errors"]) == 2


def test_metrics_summary_endpoint():
    """Verify /api/metrics/summary returns latency and error metrics."""
    res = client.get("/api/metrics/summary")
    assert res.status_code == 200
    data = res.json()
    assert "count" in data
    assert "latency_p50_ms" in data
    assert "latency_p99_ms" in data
    assert "cache_hit_rate" in data
    assert "error_metrics" in data


def test_metrics_dashboard_ui():
    """Verify /api/metrics/dashboard and root alias /metrics/dashboard serve HTML dashboard."""
    for path in ["/api/metrics/dashboard", "/metrics/dashboard"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        html = res.text
        assert "AMC ContextGraph Platform" in html
        assert "kpiCount" in html
        assert "kpiP50" in html
        assert "Recent Queries" in html


def test_prometheus_endpoint():
    """Verify /api/metrics/prometheus returns standard Prometheus exposition metrics."""
    res = client.get("/api/metrics/prometheus")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.text
    assert "# HELP amc_queries_total" in text
    assert "# TYPE amc_queries_total counter" in text
    assert "amc_queries_total" in text
    assert "amc_query_latency_p50_ms" in text
    assert "amc_cache_hit_rate" in text
    assert "amc_http_requests_total" in text


def test_request_timing_headers_and_correlation():
    """Verify middleware injects X-Request-ID and X-Process-Time headers."""
    res = client.get("/health")
    assert res.status_code == 200
    assert "x-request-id" in res.headers
    assert "x-process-time" in res.headers
