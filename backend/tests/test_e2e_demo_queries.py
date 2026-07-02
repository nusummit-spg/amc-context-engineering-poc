"""WS5e — End-to-end integration tests for the 3 demo queries.

Requires the full stack (Neo4j + Qdrant + ANTHROPIC_API_KEY) with the demo
corpus ingested. Skipped automatically when the stack isn't reachable.

Run:  pytest tests/test_e2e_demo_queries.py -m e2e -v
"""
import os

import pytest

pytestmark = pytest.mark.e2e

DEMO_QUERIES = {
    "adani": "What's our exposure to Adani Group across all schemes, and what's the latest risk commentary?",
    "sebi": "Which schemes need exit load disclosure updates after SEBI's latest circular?",
    "nbfc": "Summarize our house view on NBFCs across all analyst notes this quarter",
}


@pytest.fixture(scope="module")
def container():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    from app.api.deps import init_container
    c = init_container()
    if not c.vector.ping():
        pytest.skip("Qdrant not reachable")
    return c


@pytest.mark.asyncio
async def test_adani_exposure_query(container):
    intent, retrieval, context, synthesis = await container.orchestrator.answer(
        DEMO_QUERIES["adani"]
    )
    assert intent.query_type.value == "exposure_aggregation"
    assert "Adani Group" in retrieval.resolved_entities.values()
    assert retrieval.graph_facts, "expected HOLDS facts from graph traversal"
    assert synthesis.answer
    assert synthesis.citations


@pytest.mark.asyncio
async def test_sebi_compliance_query(container):
    intent, retrieval, context, synthesis = await container.orchestrator.answer(
        DEMO_QUERIES["sebi"]
    )
    assert intent.query_type.value == "compliance_check"
    statuses = {f.properties.get("status") for f in retrieval.graph_facts}
    assert "outdated" in statuses or "compliant" in statuses
    assert synthesis.answer


@pytest.mark.asyncio
async def test_nbfc_house_view_query(container):
    intent, retrieval, context, synthesis = await container.orchestrator.answer(
        DEMO_QUERIES["nbfc"]
    )
    assert intent.query_type.value == "house_view_synthesis"
    assert synthesis.answer
    assert context.chunks_included > 0
