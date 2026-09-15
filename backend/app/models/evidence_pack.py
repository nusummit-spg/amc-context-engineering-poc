# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/evidence_pack.py
========================
Full EvidencePack schema — the immutable D0–D3 frozen snapshot created at
response-delivery time and referenced by the human-feedback-loop and
Evaluation Layer.

Design reference: REVISED_SUMMARY.md §Gap 2 and Docs/evidence_pack.md

Sections
--------
D0  Response Finalization  — cryptographic anchor + token/latency telemetry
D1  Interaction Snapshot   — query, entities, intent, channel metadata
D2  Evidence Pack Core     — retrieval artifact: chunks, scores, coverage flags
D3  Policy & Taxonomy      — graph paths, taxonomy, policy controls, citations

Why frozen?
    If the AMFI file updates tomorrow, the evaluation of today's response must
    still reference the source version that existed at response time.  This
    makes every diagnosis deterministic and auditable years later.

Replaces the minimal EvidenceSnapshot placeholder described in the design docs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Supporting model — individual evidence chunk (selected or rejected)
# ---------------------------------------------------------------------------

class EvidenceChunk(BaseModel):
    """
    A single retrieved chunk, used in both selected_context and rejected_context.

    Replaces the loose ``list[dict]`` shape referenced in the original
    EvidenceSnapshot spec and aligns with RetrievedChunk in query.py.
    """
    chunk_id: str = Field(..., description="Stable chunk identifier (matches FAISS / Qdrant payload)")
    document_id: str = Field(..., description="Parent document identifier")
    document_title: Optional[str] = Field(default=None, description="Human-readable document title")
    text: str = Field(..., description="Verbatim chunk text as retrieved (not truncated)")
    vector_score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score at retrieval time")
    rank: Optional[int] = Field(default=None, ge=1, description="Reranker output position (1 = top)")
    rejection_reason: Optional[str] = Field(
        default=None,
        description=(
            "Populated only for rejected chunks. "
            "E.g. 'below_score_threshold', 'dropped_by_reranker', 'context_window_overflow'"
        ),
    )
    source_version: Optional[str] = Field(
        default=None,
        description="Version tag of the source document at retrieval time, e.g. 'AMFI_v18'",
    )
    page_number: Optional[int] = Field(default=None, description="1-indexed page number within source document")
    taxonomy_paths: list[str] = Field(default_factory=list, description="Taxonomy path labels attached to this chunk")


# ---------------------------------------------------------------------------
# Core model — the full D0–D3 immutable evidence snapshot
# ---------------------------------------------------------------------------

class EvidencePack(BaseModel):
    """
    Immutable snapshot of all evidence available at response-delivery time.

    Created and frozen by AMC immediately after a response is sent to the user.
    The human-feedback-loop and Evaluation Layer reference this snapshot — never
    the live system state — so all evaluation is deterministic and auditable.

    Fields are grouped into the four design tiers (D0–D3) with inline comments.
    """

    # ── D0: Response Finalization ───────────────────────────────────────────
    # Cryptographic anchor + token/latency telemetry frozen at delivery time.

    response_id: str = Field(
        ...,
        description="Unique response identifier (e.g. 'resp_9c4f1a'); FK into response_feedback table",
    )
    original_query: str = Field(..., description="Verbatim query text submitted by the user")
    response_text: str = Field(..., description="Full response text as delivered to the user")

    response_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of response_text — deterministic proof of what was said",
    )
    model_id: Optional[str] = Field(
        default=None,
        description="LLM model identifier used to generate the response, e.g. 'claude-3-5-sonnet'",
    )
    prompt_template_version: Optional[str] = Field(
        default=None,
        description="Synthesis prompt template version, e.g. 'v2.4.1'",
    )
    citations_shown: list[str] = Field(
        default_factory=list,
        description="Document version tags shown to the user as inline citations, e.g. ['AMFI_v18', 'perf_v3']",
    )
    input_tokens: Optional[int] = Field(default=None, ge=0, description="LLM input token count")
    output_tokens: Optional[int] = Field(default=None, ge=0, description="LLM output token count")
    latency_ms: Optional[float] = Field(default=None, ge=0.0, description="End-to-end response latency in milliseconds")
    truncation_flag: bool = Field(
        default=False,
        description="True if the assembled context was truncated before synthesis",
    )

    # ── D1: Interaction Snapshot ────────────────────────────────────────────
    # Query-level intent, entity resolution, and session metadata.

    interaction_id: Optional[str] = Field(
        default=None,
        description="Session-scoped turn identifier, e.g. 'int_8b2e7f'",
    )
    entity_name: Optional[str] = Field(
        default=None,
        description="Primary entity name resolved from the query (human-readable)",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Canonical entity IDs resolved at query time, e.g. ['INF846K01DP5', 'INF769K01EW8']",
    )
    attributes: list[str] = Field(
        default_factory=list,
        description="Attribute tokens extracted from the query, e.g. ['TER', 'NAV', '5yr_return']",
    )
    detected_intent: Optional[str] = Field(
        default=None,
        description="Classifier output, e.g. 'CURRENT_NUMERIC_FACT + COMPARATIVE_CLAIM'",
    )
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Governing jurisdiction at query time, e.g. 'IN'",
    )
    channel: Optional[str] = Field(
        default=None,
        description="Delivery channel identifier, e.g. 'web_ui', 'api'",
    )
    user_role: Optional[str] = Field(
        default=None,
        description="RBAC role of the requesting user, e.g. 'compliance_officer'",
    )
    interaction_timestamp: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the interaction was initiated",
    )

    # ── D2: Evidence Pack Core ──────────────────────────────────────────────
    # Retrieval artifact: chunks, vector scores, coverage and overlap flags.

    source_ids: list[str] = Field(
        default_factory=list,
        description="Identifiers of all source documents considered during retrieval",
    )
    source_versions: list[str] = Field(
        default_factory=list,
        description=(
            "Version tags corresponding 1:1 with source_ids, e.g. ['AMFI_v18', 'perf_v3']. "
            "Frozen at retrieval time — never updated after delivery."
        ),
    )
    source_age_days: list[float] = Field(
        default_factory=list,
        description="Age in days of each source (1:1 with source_ids) at retrieval time",
    )
    source_version_mismatch: bool = Field(
        default=False,
        description="True if any source version diverges from the expected current version",
    )
    chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk IDs of all chunks passed to the synthesis step (selected set)",
    )
    vector_scores: list[float] = Field(
        default_factory=list,
        description="Cosine similarity scores 1:1 with chunk_ids",
    )
    selected_context: list[EvidenceChunk] = Field(
        default_factory=list,
        description="Fully typed chunks included in the synthesis context",
    )
    rejected_context: list[EvidenceChunk] = Field(
        default_factory=list,
        description="Chunks retrieved but dropped (reranker, score threshold, context overflow)",
    )
    citation_coverage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of citations in the response that map to an evidence chunk, e.g. 1.0 = 3/3",
    )
    vector_graph_overlap: Optional[str] = Field(
        default=None,
        description=(
            "Degree to which vector results and graph facts referenced the same sources: "
            "'HIGH', 'MEDIUM', or 'LOW'. LOW is a passive anomaly signal for retrieval degradation."
        ),
    )
    context_truncation: bool = Field(
        default=False,
        description="True if any chunk text was truncated during context assembly",
    )

    # ── D3: Policy & Taxonomy Context ──────────────────────────────────────
    # Graph traversal paths, taxonomy labels, policy controls, and citations.

    graph_paths: list[dict] = Field(
        default_factory=list,
        description=(
            "Graph traversal paths executed for this query. "
            "Each dict: {'path': str, 'hops': int, 'facts_returned': int}"
        ),
    )
    taxonomy_nodes: list[dict] = Field(
        default_factory=list,
        description=(
            "Taxonomy nodes matched during classification. "
            "Each dict: {'node_id': str, 'label': str, 'depth': int}"
        ),
    )
    citations: list[dict] = Field(
        default_factory=list,
        description=(
            "Full citation objects as shown in the response. "
            "Each dict: {'index': int, 'document_id': str, 'title': str, 'page': int|None}"
        ),
    )
    source_authority: list[str] = Field(
        default_factory=list,
        description="Authority tier tags 1:1 with source_ids, e.g. ['TIER_1_REGULATOR', 'TIER_2_OFFICIAL_FILING']",
    )
    effective_dates: list[datetime] = Field(
        default_factory=list,
        description="Effective dates 1:1 with source_ids at retrieval time",
    )
    content_hashes: list[str] = Field(
        default_factory=list,
        description="SHA-256 hashes of source document content 1:1 with source_ids, for tamper detection",
    )
    policy_pack: Optional[str] = Field(
        default=None,
        description="Active policy/regulatory pack identifier, e.g. 'INDIA_SEBI_v2026_03'",
    )
    applicable_controls: list[str] = Field(
        default_factory=list,
        description="Control codes applicable to this response, e.g. ['C01', 'C02', 'C07']",
    )
    mandatory_controls: list[str] = Field(
        default_factory=list,
        description="Subset of applicable_controls that are mandatory, e.g. ['C02_source_currency', 'C03_numeric_accuracy']",
    )
    advice_flag: bool = Field(
        default=False,
        description="True if the response was classified as financial advice (triggers escalation controls)",
    )
    interaction_mode: Optional[str] = Field(
        default="INFORMATION",
        description="Interaction mode classification: 'INFORMATION', 'COMPARISON', 'ADVISORY', or 'ESCALATION'",
    )
