# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_admin_api.py
=================
Unit tests for Admin and User Management API routes (/api/admin).
"""
import json
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import admin as admin_route

admin_test_app = FastAPI()
admin_test_app.include_router(admin_route.router, prefix="/api")


@pytest.fixture
def temp_users_config(monkeypatch):
    """Create a temporary users_rbac.json file for tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_admin_rbac_"))
    temp_config = temp_dir / "users_rbac.json"
    
    initial_users = [
        {
            "username": "compliance_officer",
            "full_name": "Chief Compliance Officer",
            "role": "Compliance & Regulatory Officer",
            "department": "Compliance & Legal",
            "email": "compliance@amc.com",
            "status": "Active",
        },
        {
            "username": "sarah_compliance",
            "full_name": "Sarah Jenkins",
            "role": "Compliance & Regulatory Officer",
            "department": "Regulatory & Legal Compliance",
            "email": "s.jenkins@amc.com",
            "status": "Active",
        },
        {
            "username": "john_custom",
            "full_name": "John Custom",
            "role": "Fund Manager / Portfolio Manager",
            "department": "Equities",
            "email": "john@amc.com",
            "status": "Active",
        },
    ]
    
    with open(temp_config, "w", encoding="utf-8") as f:
        json.dump(initial_users, f, indent=2)

    monkeypatch.setattr(admin_route, "CONFIG_PATHS", [temp_config])
    yield temp_config
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_list_users(temp_users_config):
    client = TestClient(admin_test_app)
    response = client.get("/api/admin/users")
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert len(data["users"]) == 3
    assert data["users"][0]["username"] == "compliance_officer"


def test_create_and_update_user(temp_users_config):
    client = TestClient(admin_test_app)
    
    # 1. Create a new user
    payload = {
        "username": "alice_test",
        "full_name": "Alice Test",
        "role": "ESG & Sustainability Analyst",
        "department": "ESG Unit",
        "email": "alice@amc.com",
    }
    create_res = client.post("/api/admin/users", json=payload)
    assert create_res.status_code == 200
    assert create_res.json()["updated"] is False
    assert "Saved profile for alice_test" in create_res.json()["message"]

    # Verify user list has 4 users
    list_res = client.get("/api/admin/users")
    assert len(list_res.json()["users"]) == 4

    # 2. Update existing user
    update_payload = {
        "username": "alice_test",
        "full_name": "Alice Updated",
        "role": "ESG & Sustainability Analyst",
        "department": "Senior ESG Unit",
        "email": "alice.updated@amc.com",
    }
    update_res = client.post("/api/admin/users", json=update_payload)
    assert update_res.status_code == 200
    assert update_res.json()["updated"] is True
    assert update_res.json()["user"]["full_name"] == "Alice Updated"


def test_delete_custom_user(temp_users_config):
    client = TestClient(admin_test_app)
    
    del_res = client.delete("/api/admin/users/john_custom")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] == "john_custom"
    assert "Deleted user john_custom." in del_res.json()["message"]

    list_res = client.get("/api/admin/users")
    usernames = [u["username"] for u in list_res.json()["users"]]
    assert "john_custom" not in usernames


def test_delete_system_user_prevented(temp_users_config):
    client = TestClient(admin_test_app)
    
    # Should prevent deletion of system users (compliance_officer, sarah_compliance, amc_auditor, amc_researcher)
    for protected in ["compliance_officer", "sarah_compliance", "amc_auditor", "amc_researcher"]:
        res = client.delete(f"/api/admin/users/{protected}")
        assert res.status_code == 400
        assert "Default system users cannot be deleted." in res.json()["detail"]


def test_get_rbac_matrix():
    client = TestClient(admin_test_app)
    res = client.get("/api/admin/rbac")
    assert res.status_code == 200
    data = res.json()
    assert "matrix" in data
    assert len(data["matrix"]) == 5
    
    compliance = next(r for r in data["matrix"] if r["role_name"] == "Compliance & Regulatory Officer")
    assert compliance["admin_access"] == "YES"
    assert compliance["audit_logs"] == "YES"
    assert compliance["unredacted_pii"] == "YES"
    assert compliance["cypher_tool"] == "YES"
    assert compliance["compare_analytics"] == "YES"


def test_get_audit_logs(monkeypatch, tmp_path):
    client = TestClient(admin_test_app)
    
    # 1. Test empty log
    empty_log = tmp_path / "empty_audit.jsonl"
    empty_log.touch()
    monkeypatch.setattr(admin_route, "AUDIT_LOG_PATHS", [empty_log])
    res_empty = client.get("/api/admin/audit")
    assert res_empty.status_code == 200
    assert res_empty.json()["total_lines"] == 0
    assert res_empty.json()["lines"] == []

    # 2. Test populated log with 40 lines
    sample_lines = [json.dumps({"event_id": i, "query": f"test query {i}", "status": "SUCCESS"}) for i in range(40)]
    populated_log = tmp_path / "query_execution_audit.jsonl"
    populated_log.write_text("\n".join(sample_lines), encoding="utf-8")
    monkeypatch.setattr(admin_route, "AUDIT_LOG_PATHS", [populated_log])
    
    res = client.get("/api/admin/audit?limit=30")
    assert res.status_code == 200
    data = res.json()
    assert data["filename"] == "query_execution_audit.jsonl"
    assert data["total_lines"] == 40
    assert data["display_count"] == 30
    assert len(data["lines"]) == 30
    # Last line should be event_id 39
    assert '"event_id": 39' in data["lines"][-1]


def test_run_production_pipeline():
    client = TestClient(admin_test_app)
    res = client.post("/api/admin/ingestion/run")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "elapsed_seconds" in data
    assert "sebi_rss" in data


def test_check_staleness_drift():
    client = TestClient(admin_test_app)
    res = client.post("/api/admin/ingestion/staleness")
    assert res.status_code == 200
    data = res.json()
    assert "drift_detected" in data
    assert "summary" in data


def test_upload_document_file(tmp_path, monkeypatch):
    client = TestClient(admin_test_app)
    monkeypatch.setattr(admin_route, "Path", lambda p: tmp_path / p if p == "scratch/admin_uploads" else Path(p))
    
    file_content = b"%PDF-1.4 Mock PDF Content"
    files = {"file": ("test_circular.pdf", file_content, "application/pdf")}
    data = {
        "doc_type": "circular",
        "department": "IMD",
        "entity_type": "AMC",
        "authorized_by": "sarah_compliance",
    }
    res = client.post("/api/admin/ingestion/upload", files=files, data=data)
    assert res.status_code == 200
    resp_data = res.json()
    assert resp_data["accepted"] is True
    assert resp_data["doc_name"] == "test_circular.pdf"
    assert resp_data["authorizing_officer"] == "sarah_compliance"
    assert "task_id" in resp_data


def test_upload_document_validation():
    client = TestClient(admin_test_app)
    
    # Missing both file and url
    res1 = client.post("/api/admin/ingestion/upload", data={"authorized_by": "sarah_compliance"})
    assert res1.status_code == 400
    assert "Please provide a Source URL or upload a file." in res1.json()["detail"]

    # Missing authorizing officer
    res2 = client.post("/api/admin/ingestion/upload", data={"source_url": "https://sebi.gov.in/test.pdf", "authorized_by": ""})
    assert res2.status_code == 400
    assert "Authorizing Officer is required." in res2.json()["detail"]


def test_get_indexing_tasks():
    client = TestClient(admin_test_app)
    res = client.get("/api/admin/ingestion/tasks")
    assert res.status_code == 200
    data = res.json()
    assert "tasks" in data
    assert len(data["tasks"]) >= 1
    assert data["tasks"][0]["status"] == "COMPLETED"


def test_get_proposed_edges():
    client = TestClient(admin_test_app)
    res = client.get("/api/admin/ingestion/proposed-edges")
    assert res.status_code == 200
    data = res.json()
    assert "edges" in data
    assert len(data["edges"]) >= 1


def test_confirm_reject_proposed_edge():
    client = TestClient(admin_test_app)
    res_conf = client.post("/api/admin/ingestion/edges/edge-prop-001/confirm")
    assert res_conf.status_code == 200
    assert res_conf.json()["confirmed"] is True

    res_rej = client.post("/api/admin/ingestion/edges/edge-prop-002/reject")
    assert res_rej.status_code == 200
    assert res_rej.json()["rejected"] is True


def test_get_compliance_report():
    client = TestClient(admin_test_app)
    res = client.get("/api/admin/ingestion/compliance-report")
    assert res.status_code == 200
    data = res.json()
    assert "report_markdown" in data
    assert "Regulation 16C" in data["report_markdown"]


def test_clear_intent_cache():
    client = TestClient(admin_test_app)
    res = client.post("/api/admin/cache/clear")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "Intent Cache cleared cleanly" in data["message"]





