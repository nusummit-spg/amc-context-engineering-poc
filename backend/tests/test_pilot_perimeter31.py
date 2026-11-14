"""Standalone HTTP tests of the verified pilot perimeter; no AMC services."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location(
    "pilot_perimeter31", Path(__file__).resolve().parents[1]/"app"/"api"/"pilot_perimeter31.py")
perimeter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perimeter)


def client():
    app = FastAPI()
    @app.get("/api/docs")
    def unsafe_docs(): return {"unsafe": True}
    @app.post("/api/admin/ingestion/run")
    def unsafe_ingest(): return {"unsafe": True}
    @app.post("/api/query/v2")
    def query(): return {"v2": True}
    @app.get("/api/publication/status/work123")
    def status(): return {"receipt": "simulated"}
    @app.get("/api/health")
    def health(): return {"healthy": True}
    @app.get("/assets/app.js")
    def asset(): return {"static": True}
    @app.get("/files/raw.pdf")
    def raw(): return {"unsafe": True}
    @app.get("/metrics")
    def metrics(): return {"unsafe": True}
    app.add_middleware(perimeter.VerifiedPilotPerimeter31)
    return TestClient(app)


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/docs"), ("POST", "/api/admin/ingestion/run"),
    ("GET", "/files/raw.pdf"), ("GET", "/metrics"),
    ("POST", "/api/feedback"), ("GET", "/api/compliance"),
    ("GET", "/api/query/v2"), ("POST", "/api/query/traditional"),
    ("POST", "/api/query/v2/anything"),
    ("GET", "/api/publication/status/work/other"),
])
def test_unknown_paths_refused_in_enforced_mode(monkeypatch, method, path):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    with client() as c:
        resp = c.request(method, path)
    assert resp.status_code == 503


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/query/v2"), ("GET", "/api/health"),
    ("GET", "/api/publication/status/work123"), ("GET", "/assets/app.js"),
])
def test_allowlisted_paths_reach_app(monkeypatch, method, path):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    with client() as c:
        resp = c.request(method, path)
    assert resp.status_code == 200


def test_off_mode_preserves_legacy(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "off")
    with client() as c:
        assert c.get("/api/docs").status_code == 200
        assert c.post("/api/admin/ingestion/run").status_code == 200


def test_typo_fails_closed(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforc")
    with client() as c:
        assert c.post("/api/query/v2").status_code == 503


def test_exact_path_and_method_policy():
    allow = perimeter.is_pilot_route_allowed
    assert allow("POST", "/api/query/v2")
    assert not allow("GET", "/api/query/v2")
    assert not allow("POST", "/api/admin/ingestion/run")
    assert not allow("GET", "/assets/../files")
    assert not allow("GET", "/api/publication/status/123/other")
    assert not allow("GET", "/api/query%2Ftraditional")
    assert not allow("GET", "//api/query/v2")

def test_legacy_startup_policy(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "off")
    assert perimeter.legacy_services_allowed() is True
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforce")
    assert perimeter.legacy_services_allowed() is False
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE", "enforc")
    with pytest.raises(RuntimeError):
        perimeter.legacy_services_allowed()
