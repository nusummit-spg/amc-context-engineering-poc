# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS5a/WS3 — Contract tests: schemas validate, taxonomy loads, prompts render.
These run without Neo4j / Qdrant / an API key."""
from pathlib import Path

import pytest

from app.api.deps import load_taxonomy
from app.prompts import get_prompt, list_prompts
from app.schemas.api import QueryRequest, QueryResponse
from app.schemas.documents import Chunk, Document, DocumentType, Section
from app.schemas.entities import EntityType, Scheme
from app.schemas.query import GraphFact, QueryIntent, QueryType, RetrievalResult
from app.schemas.relationships import Relationship, RelationshipType


def test_document_schema_roundtrip():
    doc = Document(
        filename="Scheme_SID_InfraFund.pdf",
        doc_type=DocumentType.PDF,
        sections=[Section(title="Exit Load", text="An exit load of 1% ...", order=0)],
    )
    assert doc.full_text.startswith("An exit load")
    assert Document.model_validate(doc.model_dump()).document_id == doc.document_id


def test_entity_and_relationship_schemas():
    scheme = Scheme(name="NuSummit Infra Fund")
    assert scheme.entity_type == EntityType.SCHEME
    rel = Relationship(
        relationship_type=RelationshipType.HOLDS,
        source_entity_id=scheme.entity_id,
        target_entity_id="x",
        properties={"pct_nav": 5.8},
    )
    assert rel.relationship_type.value == "HOLDS"


def test_taxonomy_loads_four_levels():
    tree = load_taxonomy()
    nodes = tree.flatten()
    assert nodes, "taxonomy seed should not be empty"
    assert max(n.level for n in nodes) == 4
    assert tree.find("Risk/Concentration Exposure/Issuer Group/Monitoring") is not None


def test_prompt_library_registry():
    names = list_prompts()
    for required in (
        "taxonomy_classification", "entity_extraction", "entity_disambiguation",
        "relationship_extraction", "query_intent", "synthesis",
        "fallback_no_context", "fallback_low_quality",
    ):
        assert required in names, f"missing prompt: {required}"
    rendered = get_prompt("query_intent").render(taxonomy_paths="A/B", query="test?")
    assert "test?" in rendered
    assert "<example>" in rendered  # few-shots included


def test_query_api_contract():
    req = QueryRequest(query="What's our Adani exposure?", mode="both")
    assert req.mode == "both"
    resp = QueryResponse(query=req.query, mode=req.mode)
    dumped = resp.model_dump()
    for key in ("intent", "answer", "sources", "traversal_paths", "traditional", "latency_ms"):
        assert key in dumped


def test_retrieval_result_schema():
    intent = QueryIntent(query_type=QueryType.EXPOSURE_AGGREGATION)
    fact = GraphFact(
        fact_id="1", statement="Infra Fund holds Adani Green at 5.8% of NAV",
        subject="NuSummit Infra Fund", predicate="HOLDS", object="Adani Green Energy",
    )
    result = RetrievalResult(intent=intent, graph_facts=[fact])
    assert result.graph_facts[0].predicate == "HOLDS"
