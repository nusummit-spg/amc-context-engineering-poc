# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_health_endpoint.py
========================
Tests for comprehensive component health checks on /health, /api/health, and /api/status/health.
Implements Task 6 (Health Checks) of Phase 1.
"""
from fastapi.testclient import TestClient

from app.main import create_app

app = create_app()
client = TestClient(app)


def test_root_health_endpoint():
    """Verify GET /health returns structured component health."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] in ["ok", "degraded", "healthy"]
    assert "components" in data
    components = data["components"]
    assert "database" in components
    assert "neo4j" in components
    assert "vector_store" in components
    assert "scheduler" in components
    assert "llm" in components
    assert components["database"] == "ok"


def test_api_health_endpoint():
    """Verify GET /api/health returns structured component health matching /health."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "components" in data
    assert data["components"]["database"] == "ok"


def test_status_health_endpoint():
    """Verify GET /api/status/health returns component status."""
    response = client.get("/api/status/health")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "components" in data
