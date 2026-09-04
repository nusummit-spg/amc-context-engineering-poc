# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_evidence_pack_schema.py
==================================
Unit tests for the EvidencePack and EvidenceChunk Pydantic schemas (D0-D3).
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.schemas import EvidenceChunk, EvidencePack


# ---------------------------------------------------------------------------
# 1. EvidenceChunk Schema Tests
# ---------------------------------------------------------------------------

def test_evidence_chunk_valid():
    chunk = EvidenceChunk(
        chunk_id="chunk_123",
        document_id="doc_sebi_001",
        document_title="SEBI Master Circular for Mutual Funds",
        text="All AMCs shall maintain appropriate asset allocation limits.",
        vector_score=0.88,
        rank=1,
        source_version="v2026.1",
        page_number=14,
        taxonomy_paths=["/compliance/asset_allocation"]
    )
    assert chunk.chunk_id == "chunk_123"
    assert chunk.document_id == "doc_sebi_001"
    assert chunk.vector_score == 0.88
    assert chunk.rank == 1
    assert chunk.rejection_reason is None
    assert chunk.page_number == 14


def test_evidence_chunk_rejected():
    chunk = EvidenceChunk(
        chunk_id="chunk_rejected_01",
        document_id="doc_old_002",
        text="Outdated guidelines from 2018.",
        vector_score=0.45,
        rank=12,
        rejection_reason="below_score_threshold",
    )
    assert chunk.chunk_id == "chunk_rejected_01"
    assert chunk.rejection_reason == "below_score_threshold"


def test_evidence_chunk_invalid_score_bounds():
    with pytest.raises(ValidationError):
        EvidenceChunk(
            chunk_id="bad_chunk",
            document_id="doc_1",
            text="Some text",
            vector_score=1.5  # > 1.0
        )

    with pytest.raises(ValidationError):
        EvidenceChunk(
            chunk_id="bad_chunk",
            document_id="doc_1",
            text="Some text",
            vector_score=-0.1  # < 0.0
        )


def test_evidence_chunk_invalid_rank():
    with pytest.raises(ValidationError):
        EvidenceChunk(
            chunk_id="bad_chunk",
            document_id="doc_1",
            text="Some text",
            vector_score=0.5,
            rank=0  # ge=1 required
        )


# ---------------------------------------------------------------------------
# 2. EvidencePack Schema Tests
# ---------------------------------------------------------------------------

def test_evidence_pack_minimal():
    pack = EvidencePack(
        response_id="resp_min_001",
        original_query="What is the expense ratio of HDFC Top 100?",
        response_text="The expense ratio of HDFC Top 100 is 1.15%."
    )
    assert pack.response_id == "resp_min_001"
    assert pack.original_query == "What is the expense ratio of HDFC Top 100?"
    assert pack.truncation_flag is False
    assert pack.source_ids == []
    assert pack.selected_context == []
    assert pack.rejected_context == []
    assert pack.interaction_mode == "INFORMATION"


def test_evidence_pack_full_d0_to_d3():
    now = datetime.now(timezone.utc)
    selected_chunk = EvidenceChunk(
        chunk_id="chunk_sel_01",
        document_id="doc_amfi_v18",
        document_title="AMFI Monthly TER Factsheet",
        text="HDFC Top 100 regular plan TER is 1.15% as of August 2026.",
        vector_score=0.94,
        rank=1,
        source_version="AMFI_v18",
        page_number=5,
        taxonomy_paths=["/mutual_funds/equity/ter"]
    )
    rejected_chunk = EvidenceChunk(
        chunk_id="chunk_rej_01",
        document_id="doc_amfi_v17",
        document_title="AMFI July Factsheet",
        text="HDFC Top 100 regular plan TER was 1.18%.",
        vector_score=0.72,
        rank=5,
        rejection_reason="dropped_by_reranker",
        source_version="AMFI_v17"
    )

    pack = EvidencePack(
        # D0
        response_id="resp_9c4f1a",
        original_query="What is the current TER for HDFC Top 100?",
        response_text="The current Total Expense Ratio (TER) is 1.15% as of August 2026.",
        response_hash="a7f3c9d821e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991",
        model_id="claude-3-5-sonnet",
        prompt_template_version="v2.4.1",
        citations_shown=["AMFI_v18", "perf_v3"],
        input_tokens=850,
        output_tokens=120,
        latency_ms=1450.5,
        truncation_flag=False,
        # D1
        interaction_id="int_8b2e7f",
        entity_name="HDFC Top 100 Fund",
        entities=["INF846K01DP5"],
        attributes=["TER"],
        detected_intent="CURRENT_NUMERIC_FACT",
        jurisdiction="IN",
        channel="web_ui",
        user_role="compliance_officer",
        interaction_timestamp=now,
        # D2
        source_ids=["doc_amfi_v18", "doc_perf_v3"],
        source_versions=["AMFI_v18", "perf_v3"],
        source_age_days=[3.0, 10.0],
        source_version_mismatch=False,
        chunk_ids=["chunk_sel_01"],
        vector_scores=[0.94],
        selected_context=[selected_chunk],
        rejected_context=[rejected_chunk],
        citation_coverage=1.0,
        vector_graph_overlap="HIGH",
        context_truncation=False,
        # D3
        graph_paths=[{"path": "Scheme->HOLDS->TER", "hops": 1, "facts_returned": 1}],
        taxonomy_nodes=[{"node_id": "TAX_TER_01", "label": "TER", "depth": 2}],
        citations=[{"index": 1, "document_id": "doc_amfi_v18", "title": "AMFI Monthly", "page": 5}],
        source_authority=["TIER_1_REGULATOR", "TIER_2_OFFICIAL_FILING"],
        effective_dates=[now],
        content_hashes=["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
        policy_pack="INDIA_SEBI_v2026_03",
        applicable_controls=["C01", "C02_source_currency", "C03_numeric_accuracy"],
        mandatory_controls=["C02_source_currency", "C03_numeric_accuracy"],
        advice_flag=False,
        interaction_mode="INFORMATION",
    )

    assert pack.response_id == "resp_9c4f1a"
    assert pack.model_id == "claude-3-5-sonnet"
    assert len(pack.selected_context) == 1
    assert pack.selected_context[0].chunk_id == "chunk_sel_01"
    assert len(pack.rejected_context) == 1
    assert pack.rejected_context[0].rejection_reason == "dropped_by_reranker"
    assert pack.citation_coverage == 1.0
    assert pack.vector_graph_overlap == "HIGH"
    assert pack.interaction_mode == "INFORMATION"


def test_evidence_pack_validation_bounds():
    # Negative tokens
    with pytest.raises(ValidationError):
        EvidencePack(
            response_id="bad_tokens",
            original_query="q",
            response_text="r",
            input_tokens=-5
        )

    # Negative latency
    with pytest.raises(ValidationError):
        EvidencePack(
            response_id="bad_latency",
            original_query="q",
            response_text="r",
            latency_ms=-1.0
        )

    # citation_coverage > 1.0
    with pytest.raises(ValidationError):
        EvidencePack(
            response_id="bad_coverage",
            original_query="q",
            response_text="r",
            citation_coverage=1.5
        )


def test_evidence_pack_serialization_roundtrip():
    pack = EvidencePack(
        response_id="resp_ser_01",
        original_query="Query?",
        response_text="Answer.",
        selected_context=[
            EvidenceChunk(
                chunk_id="c1",
                document_id="d1",
                text="Text",
                vector_score=0.9
            )
        ]
    )

    dumped = pack.model_dump()
    assert dumped["response_id"] == "resp_ser_01"
    assert len(dumped["selected_context"]) == 1
    assert dumped["selected_context"][0]["chunk_id"] == "c1"

    json_str = pack.model_dump_json()
    reconstructed = EvidencePack.model_validate_json(json_str)
    assert reconstructed.response_id == pack.response_id
    assert reconstructed.selected_context[0].chunk_id == "c1"
