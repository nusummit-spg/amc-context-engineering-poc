"""Regression: legacy serving routes cannot bypass active publication authority.

Guard behavior is tested without providers; AST confirms every identified legacy
ingress invokes a guard. Full HTTP and live data tests are still required.
"""
from __future__ import annotations
import ast
from pathlib import Path
import pytest
from fastapi import HTTPException
from app.api.routes.legacy_guard31 import (
    reject_legacy_in_verified_mode, require_v2_in_verified_mode, require_verified_tenant,
)
ROOT=Path(__file__).resolve().parents[1]/"app"/"api"/"routes"

def _called_names(path, function):
    tree=ast.parse((ROOT/path).read_text(encoding="utf-8"))
    matches=[x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name==function]
    assert len(matches)==1
    return {n.func.id for n in ast.walk(matches[0])
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}

@pytest.mark.parametrize("file,func,gate",[
    ("query.py","run_traditional","reject_legacy_in_verified_mode"),
    ("query.py","run_contextgraph","reject_legacy_in_verified_mode"),
    ("query.py","run_query","require_v2_in_verified_mode"),
    ("query.py","run_query_v2","require_verified_tenant"),
    ("query.py","query_stream","require_verified_tenant"),
    ("chat.py","run_chat","require_v2_in_verified_mode"),
    ("chat.py","chat_stream","require_v2_in_verified_mode"),
    ("graph.py","full_graph","reject_legacy_in_verified_mode"),
    ("graph.py","neighborhood","reject_legacy_in_verified_mode"),
    ("graph.py","traversal_highlight","reject_legacy_in_verified_mode"),
    ("files.py","download_file","reject_legacy_in_verified_mode"),
    ("files.py","get_file","reject_legacy_in_verified_mode"),
    ("docs.py","list_documents","reject_legacy_in_verified_mode"),
    ("docs.py","get_document","reject_legacy_in_verified_mode"),
    ("taxonomy.py","get_tree","reject_legacy_in_verified_mode"),
    ("taxonomy.py","node_documents","reject_legacy_in_verified_mode"),
])
def test_route_has_guard(file,func,gate):
    assert gate in _called_names(file,func)

def test_off_mode_preserves_legacy(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","off")
    reject_legacy_in_verified_mode(route="/query/traditional")
    require_v2_in_verified_mode("legacy",route="/query")
    require_verified_tenant(None,route="/query/v2")

def test_enforce_disables_legacy(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","enforce")
    with pytest.raises(HTTPException) as e:
        reject_legacy_in_verified_mode(route="/graph")
    assert e.value.status_code==503
    with pytest.raises(HTTPException) as e:
        require_v2_in_verified_mode("canary",route="/chat")
    assert e.value.status_code==503
    require_v2_in_verified_mode("v2",route="/chat")

def test_enforce_requires_tenant(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","enforce")
    with pytest.raises(HTTPException) as e:
        require_verified_tenant(None,route="/query/stream")
    assert e.value.status_code==403
    with pytest.raises(HTTPException):
        require_verified_tenant(type("U",(),{"tenant_id":""})(),route="/query/v2")
    require_verified_tenant(type("U",(),{"tenant_id":"abc"})(),route="/query/v2")

def test_invalid_mode_rejected(monkeypatch):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","enforc")
    with pytest.raises(Exception):
        reject_legacy_in_verified_mode(route="/query")


def test_aggregation_router_is_gated_and_files_are_private():
    scheme=(ROOT/"scheme_aggregation_routes.py").read_text(encoding="utf-8")
    files=(ROOT/"files.py").read_text(encoding="utf-8")
    assert "dependencies=[Depends(_require_verified_aggregation_boundary)]" in scheme
    assert '"Cache-Control": "private, no-store"' in files
    assert '"Cache-Control": "public, max-age=3600"' not in files
