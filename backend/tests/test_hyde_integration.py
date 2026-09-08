# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_hyde_integration.py
=========================
Integration tests verifying HyDE integration within the RetrievalOrchestrator:
- Triggers when enable_hyde=True and intent requires vector
- Bypassed when enable_hyde=False
- Bypassed when ENABLE_HYDE_IN_ORCHESTRATOR=False
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine import config, hyde
from app.schemas.query import QueryIntent, QueryType, AssembledContext, SynthesisOutput


@pytest.fixture
def mock_orchestrator():
    from app.retrieval.orchestrator import RetrievalOrchestrator
    
    mock_intent_classifier = MagicMock()
    mock_intent = QueryIntent(
        query_type=QueryType.GENERAL,
        entities_mentioned=[],
        taxonomy_paths=[],
        requires_graph=False,
        requires_vector=True,
    )
    mock_intent_classifier.classify = AsyncMock(return_value=mock_intent)

    mock_resolver = MagicMock()
    mock_traversal = MagicMock()
    mock_traversal.traverse = AsyncMock(return_value=([], [], []))

    mock_vector = MagicMock()
    mock_vector.search = AsyncMock(return_value=[
        {"chunk_id": "c1", "document_id": "d1", "text": "Sample text", "score": 0.88, "taxonomy_paths": []}
    ])

    mock_assembler = MagicMock()
    mock_assembler.assemble = MagicMock(return_value=AssembledContext(
        context_text="Sample context",
        token_count=100,
        token_budget=12000,
        sources=[],
        quality_score=1.0,
        passed_quality_gate=True,
    ))

    mock_synth = MagicMock()
    mock_synth.synthesize = AsyncMock(return_value=SynthesisOutput(
        answer="Sample generated answer",
        confidence="high",
        citations=[],
        provenance=[],
    ))

    return RetrievalOrchestrator(
        intent_classifier=mock_intent_classifier,
        resolver=mock_resolver,
        traversal=mock_traversal,
        vector_store=mock_vector,
        assembler=mock_assembler,
        synthesizer=mock_synth,
    )


@pytest.mark.asyncio
async def test_hyde_called_when_enabled(mock_orchestrator):
    config.ENABLE_HYDE_CACHE = True
    config.ENABLE_HYDE_IN_ORCHESTRATOR = True

    with patch("app.engine.hyde.generate_hypothetical_document", return_value=("Hypo doc", 1.2)) as mock_hyde:
        resp = await mock_orchestrator.answer("What is NAV?", enable_hyde=True)
        assert mock_hyde.called
        assert resp.synthesis.answer == "Sample generated answer"


@pytest.mark.asyncio
async def test_hyde_not_called_when_disabled_param(mock_orchestrator):
    with patch("app.engine.hyde.generate_hypothetical_document") as mock_hyde:
        await mock_orchestrator.answer("What is NAV?", enable_hyde=False)
        assert not mock_hyde.called


@pytest.mark.asyncio
async def test_hyde_not_called_when_disabled_config(mock_orchestrator):
    original = config.ENABLE_HYDE_IN_ORCHESTRATOR
    try:
        config.ENABLE_HYDE_IN_ORCHESTRATOR = False
        with patch("app.engine.hyde.generate_hypothetical_document") as mock_hyde:
            await mock_orchestrator.answer("What is NAV?", enable_hyde=True)
            assert not mock_hyde.called
    finally:
        config.ENABLE_HYDE_IN_ORCHESTRATOR = original
