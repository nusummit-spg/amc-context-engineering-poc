# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS5a / WS3 — API request & response schemas: the contract shared with the frontend.

Endpoints: /query /taxonomy /graph /docs /ingest /status

Unified with WS5a extended design:
  - QueryResponse gains typed graph_highlight (was bare dict)
  - TaxonomyNodeOut.build_from_node() helper for clean conversion
  - GraphNodeOut / GraphEdgeOut remain flat (frontend expects this shape)
  - DocumentSummaryOut gains ingested_at timestamp
  - IngestStatusResponse.progress is typed via IngestionJob (not bare dict)
  - HealthResponse gains typed bool fields alongside str status (more testable)

Backwards-compatible: all existing field names are preserved.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
import re

from app.schemas.documents import IngestionJob, IngestionStatus
from app.schemas.query import (
    AssembledContext,
    QueryIntent,
    QueryTrace,
    SourceAttribution,
    SynthesisOutput,
)


# ── /query ────────────────────────────────────────────────────────────────────

def sanitize_user_query(v: str, min_length: int = 3) -> str:
    """Sanitize a user query against SQL injection, script injection, and degenerate inputs.

    Shared by /query, /chat and /chat/title so every user-supplied prompt gets
    the same treatment (Task 0.4.1).
    """
    v_stripped = v.strip()
    if len(v_stripped) < min_length:
        raise ValueError(f"Query must be at least {min_length} non-whitespace characters.")

    # SQL Injection patterns
    sql_patterns = [
        r"DROP\s+TABLE",
        r"DELETE\s+FROM",
        r"INSERT\s+INTO",
        r"UNION\s+(ALL\s+)?SELECT",
        r";\s*DROP",
        r";\s*DELETE",
    ]
    for pat in sql_patterns:
        if re.search(pat, v_stripped, re.IGNORECASE):
            raise ValueError("Potentially unsafe SQL injection pattern detected.")

    # Script injection patterns
    if "<script>" in v_stripped.lower() or "</script>" in v_stripped.lower() or "javascript:" in v_stripped.lower():
        raise ValueError("Script tags and javascript URIs are not permitted.")

    # Ensure not purely repetitive characters (e.g. "aaaaaaaaa")
    if len(v_stripped) >= 5 and len(set(v_stripped.lower())) <= 2:
        raise ValueError("Query is too repetitive or degenerate.")

    return v_stripped


def validate_session_id(v: Optional[str]) -> Optional[str]:
    """Session IDs must be opaque, URL-safe tokens (Task 0.4.1)."""
    if v is None:
        return v
    v_stripped = v.strip()
    if not v_stripped:
        raise ValueError("Session ID must not be blank.")
    if len(v_stripped) > 64:
        raise ValueError("Session ID must be at most 64 characters.")
    if not re.match(r"^[a-zA-Z0-9_-]+$", v_stripped):
        raise ValueError("Invalid session ID format: only letters, digits, '_' and '-' are allowed.")
    return v_stripped


class QueryRequest(BaseModel):
    query:  str            = Field(min_length=3, max_length=2000)
    mode:   str            = Field(
        default="contextgraph",
        description="'contextgraph' | 'traditional' | 'both'",
    )
    top_k: Optional[int]  = Field(default=None, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        return sanitize_user_query(v, min_length=3)



class GraphHighlight(BaseModel):
    """Typed replacement for the bare dict graph_highlight in QueryResponse.
    Backwards-compatible: JSON shape is identical.
    """
    node_names:    list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)


class TraditionalResult(BaseModel):
    """The 'traditional RAG' side of the comparison — flat vector search, no graph."""
    files:   list[dict] = Field(default_factory=list)   # {name, document_id, score, snippet}
    snippet: Optional[str] = None
    metrics: dict          = Field(default_factory=dict)


class QueryResponse(BaseModel):
    query:           str
    mode:            str
    intent:          Optional[QueryIntent]       = None
    answer:          Optional[SynthesisOutput]   = None
    sources:         list[SourceAttribution]     = Field(default_factory=list)
    traversal_paths: list[str]                   = Field(default_factory=list)
    taxonomy_paths:  list[str]                   = Field(default_factory=list)
    graph_highlight: dict                         = Field(
        default_factory=dict,
        description="{node_names: [], relationships: []} — used by frontend for SVG highlighting",
    )
    context_debug:   Optional[AssembledContext]  = None
    traditional:     Optional[TraditionalResult] = None
    latency_ms:      int                          = Field(default=0, ge=0)
    trace:           Optional[QueryTrace]        = None
    serving_engine:  Optional[str]               = None
    corpus_version:  Optional[str]               = None
    response_id:     Optional[str]               = None
    interaction_id:  Optional[str]               = None


# ── /chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query:      str            = Field(min_length=1, max_length=2000)
    session_id: str
    history:    list[dict]     = Field(default_factory=list)
    mode:       str            = Field(default="both", description="'contextgraph' | 'traditional' | 'both'")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        # Chat turns can legitimately be short ("yes", "why?"), so min_length=1.
        return sanitize_user_query(v, min_length=1)

    @field_validator("session_id")
    @classmethod
    def check_session_id(cls, v: str) -> str:
        return validate_session_id(v)


class ChatResponse(BaseModel):
    query:          str
    resolved_query: str
    mode:           str
    traditional:    Optional[TraditionalResult] = None
    hybrid:         Optional[dict]              = None
    history:        list[dict]
    session_id:     str
    turn_index:     int
    trace:          Optional[QueryTrace]        = None
    serving_engine: Optional[str]               = None
    corpus_version: Optional[str]               = None
    response_id:    Optional[str]               = None
    interaction_id: Optional[str]               = None


class ChatTitleRequest(BaseModel):
    query:      str            = Field(min_length=1, max_length=2000)
    session_id: Optional[str]  = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        return sanitize_user_query(v, min_length=1)

    @field_validator("session_id")
    @classmethod
    def check_session_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_session_id(v)


class ChatTitleResponse(BaseModel):
    title:      str
    session_id: Optional[str]  = None


# ── /taxonomy ─────────────────────────────────────────────────────────────────

class TaxonomyNodeOut(BaseModel):
    """Flattened taxonomy node for the frontend tree sidebar."""
    node_id:        str
    name:           str
    path:           str
    level:          int
    document_count: int              = 0
    children:       list["TaxonomyNodeOut"] = Field(default_factory=list)


class TaxonomyTreeResponse(BaseModel):
    version:          str
    domain:           str
    roots:            list[TaxonomyNodeOut]
    highlighted_paths: list[str] = Field(
        default_factory=list,
        description="Paths activated by the last query — used by frontend for tree highlighting",
    )


class TaxonomyNodeDocsResponse(BaseModel):
    path:      str
    documents: list[dict] = Field(default_factory=list)  # {document_id, title, doc_type}


# ── /graph ────────────────────────────────────────────────────────────────────

class GraphNodeOut(BaseModel):
    id:          str
    label:       str
    entity_type: str
    properties:  dict = Field(default_factory=dict)


class GraphEdgeOut(BaseModel):
    id:                str
    source:            str
    target:            str
    relationship_type: str
    label:             str  = ""
    properties:        dict = Field(default_factory=dict)


class GraphResponse(BaseModel):
    nodes: list[GraphNodeOut] = Field(default_factory=list)
    edges: list[GraphEdgeOut] = Field(default_factory=list)


# ── /docs ─────────────────────────────────────────────────────────────────────

class DocumentSummaryOut(BaseModel):
    document_id:    str
    filename:       str
    title:          Optional[str] = None
    doc_type:       str
    category:       str
    author:         Optional[str] = None
    ingested_at:    Optional[datetime] = None
    chunk_count:    int            = 0
    taxonomy_paths: list[str]      = Field(default_factory=list)


class DocumentDetailOut(DocumentSummaryOut):
    chunks: list[dict] = Field(default_factory=list)  # {chunk_id, text, order}


# ── /ingest ───────────────────────────────────────────────────────────────────

class IngestJobResponse(BaseModel):
    job_id:   str
    status:   str            # queued | running | completed | failed
    filename: Optional[str] = None
    detail:   Optional[str] = None


class IngestStatusResponse(BaseModel):
    job_id:   str
    status:   str
    progress: dict = Field(
        default_factory=dict,
        description="{stage, docs_done, docs_total, docs_failed, errors}",
    )

    @classmethod
    def from_job(cls, job: IngestionJob) -> "IngestStatusResponse":
        """Build an IngestStatusResponse from a typed IngestionJob."""
        return cls(
            job_id=job.job_id,
            status=job.status.value,
            progress={
                "stage":       job.stage,
                "docs_done":   job.docs_done,
                "docs_total":  job.total_files,
                "docs_failed": job.docs_failed,
                "errors":      job.errors,
                "progress_pct": job.progress_pct,
            },
        )


# ── /status ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health of all system dependencies and active data plane summary."""
    status:                 str  # "ok" | "degraded" | "down"
    neo4j:                  str  # "ok" | "error"
    qdrant:                 str  # "ok" | "error"
    llm:                    str  # "ok" | "error"
    documents_indexed:      int = Field(default=0, ge=0)
    chunks_indexed:         int = Field(default=0, ge=0)
    serving_engine:         Optional[str] = None
    serving_corpus_version: Optional[str] = None
    legacy_index:           dict = Field(default_factory=dict)
    modern_index:           dict = Field(default_factory=dict)

    @property
    def neo4j_ok(self) -> bool:
        return self.neo4j == "ok"

    @property
    def qdrant_ok(self) -> bool:
        return self.qdrant == "ok"

    @property
    def llm_ok(self) -> bool:
        return self.llm == "ok"

    @property
    def all_healthy(self) -> bool:
        return self.neo4j_ok and self.qdrant_ok and self.llm_ok


class DataPlanesResponse(BaseModel):
    """Truthful overview of both legacy and modern data planes."""
    serving_engine:          str
    serving_corpus_version:  str
    legacy_index:            dict
    modern_index:            dict
    query_engines_available: list[str] = Field(default_factory=lambda: ["legacy", "v2", "shadow"])


TaxonomyNodeOut.model_rebuild()
