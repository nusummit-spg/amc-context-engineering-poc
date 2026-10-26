# backend/tests/test_data_dir_independence.py
"""
Tests verifying that backend and engine do not crash when data/* folder
is missing, empty, or unpopulated at initial stage.
"""
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.vector.client import VectorStore
from app.ingestion.ledger import IngestionLedger, IngestionStage
from app.engine.faiss_store import BrochureFAISSStore
from app.engine.taxonomy import build_taxonomy, load_taxonomy
from app.main import app


def test_vector_store_initialization_with_missing_dir():
    """VectorStore must initialize safely when faiss_dir points to non-existent directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        missing_dir = Path(tmpdir) / "does_not_exist" / "vector_store"
        
        # Test initialization does not crash
        store = VectorStore(faiss_dir=str(missing_dir))
        assert store.ping() is True
        assert store.count() >= 0


@pytest.mark.asyncio
async def test_vector_store_empty_operations():
    """VectorStore search, list_documents, and chunks must work without crashing when empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        missing_dir = Path(tmpdir) / "empty_store"
        store = VectorStore(faiss_dir=str(missing_dir))
        # Ensure pure empty state
        store._index = store._new_index()
        store._payloads = {}
        store._next_id = 0

        hits = await store.search("test query", top_k=5)
        assert hits == []

        sim_hits = await store.similarity_search(query="test query", limit=5)
        assert sim_hits == []

        docs = await store.list_documents()
        assert docs == []

        chunks = await store.get_document_chunks("doc_123")
        assert chunks == []


def test_brochure_faiss_store_fallback():
    """BrochureFAISSStore must not raise FileNotFoundError when index is missing."""
    store = BrochureFAISSStore("completely_nonexistent_slug_12345")
    assert store.index is not None
    assert store.children == []
    assert store.parents_map == {}

    hits = store.retrieve("test query", top_k_children=3)
    assert hits == []

    ctx = store.get_context_string("test query", top_k=3)
    assert ctx == ""


def test_ingestion_ledger_with_missing_dir():
    """IngestionLedger must safely create its directory and record stages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_dir = Path(tmpdir) / "new_ledger_dir" / "v_test"
        ledger = IngestionLedger(corpus_version="v_test", ledger_dir=ledger_dir)

        assert ledger_dir.exists()
        assert ledger.is_activated("doc_v1") is False
        assert ledger.get_stage("doc_v1") is None

        ledger.record_stage("doc_v1", IngestionStage.PARSED)
        assert ledger.get_stage("doc_v1") == IngestionStage.PARSED.value


def test_taxonomy_build_without_source_data():
    """build_taxonomy must produce valid categories whether scanned or baseline."""
    tax = build_taxonomy(verbose=False)
    assert isinstance(tax, dict)
    assert "categories" in tax
    assert len(tax["categories"]) > 0
    assert any("Fund" in c or "Equity" in c or "Debt" in c for c in tax["categories"])


def test_api_routes_without_relying_on_data():
    """FastAPI routes must return valid HTTP responses without 500 when data/* is absent."""
    client = TestClient(app)

    # 1. Documents endpoint returns 200 without error
    docs_resp = client.get("/api/docs")
    assert docs_resp.status_code == 200
    assert isinstance(docs_resp.json(), list)

    # 2. File retrieval endpoint for missing PDF returns 404 JSON, not 500
    file_resp = client.get("/api/files/sample_not_found.pdf")
    assert file_resp.status_code == 404

    # 3. Query route in traditional mode executes cleanly even if vector index is empty
    with patch("app.engine.llm_text_client.call_llm_with_usage", return_value=("Mock answer", {"input_tokens": 10, "output_tokens": 10})):
        query_resp = client.post(
            "/api/query",
            json={"query": "What is the fund strategy?", "mode": "traditional"}
        )
        assert query_resp.status_code == 200
        data = query_resp.json()
        assert "traditional" in data
