"""WS5a — Query intent, retrieval result, assembled context, and synthesis output schemas."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class QueryType(str, Enum):
    """Drives the traversal strategy (WS5d query-type -> traversal-strategy mapper)."""
    EXPOSURE_AGGREGATION = "exposure_aggregation"    # e.g. "Adani exposure across all schemes"
    COMPLIANCE_CHECK = "compliance_check"            # e.g. "which SIDs need updates after circular X"
    HOUSE_VIEW_SYNTHESIS = "house_view_synthesis"    # e.g. "summarize our view on NBFCs"
    ENTITY_LOOKUP = "entity_lookup"                  # single-entity factual question
    GENERAL = "general"                              # fallback: pure vector search


class QueryIntent(BaseModel):
    """Output of the intent classifier (step 1 of the retrieval flow)."""
    query_type: QueryType
    entities_mentioned: list[str] = Field(default_factory=list)   # raw surface forms from the query
    taxonomy_paths: list[str] = Field(default_factory=list)       # activated taxonomy branches
    requires_graph: bool = True
    requires_vector: bool = True
    reasoning: Optional[str] = None


class GraphFact(BaseModel):
    """A structured fact returned by graph traversal — prioritized over prose in context assembly."""
    fact_id: str
    statement: str                       # human-readable, e.g. "Infra Fund HOLDS 5.8% Adani Green"
    subject: str
    predicate: str
    object: str
    properties: dict = Field(default_factory=dict)
    source_document_ids: list[str] = Field(default_factory=list)
    traversal_path: Optional[str] = None  # e.g. "Scheme→HOLDS→Issuer→ISSUED_BY→IssuerGroup"


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: Optional[str] = None
    text: str
    score: float
    taxonomy_paths: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    """Combined output of graph traversal + scoped vector search (steps 2-5)."""
    intent: QueryIntent
    resolved_entities: dict[str, str] = Field(default_factory=dict)  # surface form -> canonical entity_id
    graph_facts: list[GraphFact] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    traversal_paths: list[str] = Field(default_factory=list)
    cypher_queries_run: list[str] = Field(default_factory=list)


class SourceAttribution(BaseModel):
    source_index: int                    # [1], [2] ... used for inline citations
    document_id: str
    document_title: str
    chunk_id: Optional[str] = None
    snippet: Optional[str] = None


class AssembledContext(BaseModel):
    """Output of the context engineering layer (WS5d, step 6)."""
    context_text: str
    token_count: int
    token_budget: int
    structured_facts_included: int
    chunks_included: int
    chunks_dropped: int
    sources: list[SourceAttribution] = Field(default_factory=list)
    quality_score: float = 0.0           # context quality gate metric
    passed_quality_gate: bool = True
    traversal_explanation: list[str] = Field(default_factory=list)  # for the UI ontology view


class Citation(BaseModel):
    source_index: int
    document_title: str


class SynthesisOutput(BaseModel):
    """WS5a — LLM output schema (step 7). The synthesis prompt instructs the model to
    return this shape via structured outputs."""
    answer: str                              # markdown, with inline [n] citation markers
    structured_rows: list[dict] = Field(default_factory=list)  # tabular facts for the answer card UI
    compliance_note: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    confidence: str = "high"                 # high | medium | low
