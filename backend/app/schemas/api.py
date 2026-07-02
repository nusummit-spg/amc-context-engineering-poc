"""WS5a / WS3 — API request & response schemas: the contract shared with the frontend.

Endpoints (matching architecture diagram): /query /taxonomy /graph /docs /ingest /status
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.query import (
    AssembledContext,
    QueryIntent,
    SourceAttribution,
    SynthesisOutput,
)


# ---------- /query ----------

class QueryRequest(BaseModel):
    query: str
    mode: str = "contextgraph"       # "contextgraph" | "traditional" (for the comparison UI)
    top_k: Optional[int] = None


class TraditionalResult(BaseModel):
    """The 'traditional RAG' side of the comparison — flat vector search, no graph."""
    files: list[dict] = Field(default_factory=list)   # {name, document_id, score, snippet}
    snippet: Optional[str] = None
    metrics: dict = Field(default_factory=dict)


class QueryResponse(BaseModel):
    query: str
    mode: str
    intent: Optional[QueryIntent] = None
    answer: Optional[SynthesisOutput] = None
    sources: list[SourceAttribution] = Field(default_factory=list)
    traversal_paths: list[str] = Field(default_factory=list)
    taxonomy_paths: list[str] = Field(default_factory=list)
    graph_highlight: dict = Field(default_factory=dict)   # {node_ids: [], edge_ids: []} for UI
    context_debug: Optional[AssembledContext] = None
    traditional: Optional[TraditionalResult] = None
    latency_ms: int = 0


# ---------- /taxonomy ----------

class TaxonomyNodeOut(BaseModel):
    node_id: str
    name: str
    path: str
    level: int
    document_count: int = 0
    children: list["TaxonomyNodeOut"] = Field(default_factory=list)


class TaxonomyTreeResponse(BaseModel):
    version: str
    domain: str
    roots: list[TaxonomyNodeOut]


class TaxonomyNodeDocsResponse(BaseModel):
    path: str
    documents: list[dict] = Field(default_factory=list)  # {document_id, title, doc_type}


# ---------- /graph ----------

class GraphNodeOut(BaseModel):
    id: str
    label: str
    entity_type: str
    properties: dict = Field(default_factory=dict)


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    relationship_type: str
    label: str = ""
    properties: dict = Field(default_factory=dict)


class GraphResponse(BaseModel):
    nodes: list[GraphNodeOut] = Field(default_factory=list)
    edges: list[GraphEdgeOut] = Field(default_factory=list)


# ---------- /docs ----------

class DocumentSummaryOut(BaseModel):
    document_id: str
    filename: str
    title: Optional[str] = None
    doc_type: str
    category: str
    author: Optional[str] = None
    chunk_count: int = 0
    taxonomy_paths: list[str] = Field(default_factory=list)


class DocumentDetailOut(DocumentSummaryOut):
    chunks: list[dict] = Field(default_factory=list)  # {chunk_id, text, order}


# ---------- /ingest ----------

class IngestJobResponse(BaseModel):
    job_id: str
    status: str            # queued | running | completed | failed
    filename: Optional[str] = None
    detail: Optional[str] = None


class IngestStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: dict = Field(default_factory=dict)  # {stage, docs_done, docs_total, errors}


# ---------- /status ----------

class HealthResponse(BaseModel):
    status: str
    neo4j: str
    qdrant: str
    llm: str
    documents_indexed: int = 0
    chunks_indexed: int = 0


TaxonomyNodeOut.model_rebuild()
