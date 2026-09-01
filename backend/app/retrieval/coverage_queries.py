# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Multi-dimension coverage query sampling for taxonomy-aware retrieval.

Adapted from Spark Testing Tool's _COVERAGE_QUERIES strategy.
Ensures retrieval context represents ALL dimensions of a document's taxonomy
(not just the closest semantic match to the user query).

Usage:
    from app.retrieval.coverage_queries import build_taxonomy_context, AMC_COVERAGE_QUERIES

    # During ingestion or taxonomy building:
    context = await build_taxonomy_context(vector_store, document_id="doc-xyz")
    # context is a dict: {dimension: retrieved_text_chunks}

    # For prompt building:
    full_context = format_coverage_context(context)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# AMC domain coverage queries — 8 semantic dimensions
# Each query targets a different area of the AMC/regulatory knowledge graph.
# Running all queries ensures taxonomy completeness across the document corpus.
# ─────────────────────────────────────────────────────────────────────────────
AMC_COVERAGE_QUERIES: list[tuple[str, str]] = [
    (
        "scheme_holdings",
        "scheme portfolio holdings issuer allocation percentage nav exposure concentration",
    ),
    (
        "regulatory_compliance",
        "SEBI circular compliance clause exit load regulatory requirement status pending",
    ),
    (
        "risk_themes",
        "risk concentration funding cost pressure credit rating downgrade sector exposure",
    ),
    (
        "analyst_coverage",
        "analyst research note coverage recommendation buy sell hold sector view",
    ),
    (
        "financial_metrics",
        "AUM assets under management NAV returns performance benchmark financial metric",
    ),
    (
        "issuer_groups",
        "conglomerate group exposure Adani Tata Reliance group-level limit single issuer limit",
    ),
    (
        "esg_compliance",
        "ESG environmental social governance sustainability voting stewardship",
    ),
    (
        "temporal_changes",
        "effective date valid from applicable circular amendment revision superseded",
    ),
]

# Insurance domain coverage queries (for when domain_pack switches to insurance)
INSURANCE_COVERAGE_QUERIES: list[tuple[str, str]] = [
    ("eligibility", "premium calculation formula eligibility age sum assured benefit"),
    ("exclusions", "exclusion clause waiting period lapse revival surrender value"),
    ("claims", "claim settlement process documents required death benefit payout"),
    ("riders", "rider add-on optional benefit premium waiver accidental disability"),
    ("maturity", "maturity benefit bonus loyalty addition guaranteed return"),
    ("tax", "tax benefit section 80C 10(10D) GST deduction exemption"),
    ("policy_lifecycle", "free-look period grace period policy term payment mode"),
    ("underwriting", "medical examination underwriting decision entry age maximum minimum"),
]

# Domain-keyed registry
COVERAGE_QUERIES_BY_DOMAIN: dict[str, list[tuple[str, str]]] = {
    "AMC":       AMC_COVERAGE_QUERIES,
    "insurance": INSURANCE_COVERAGE_QUERIES,
}


@dataclass
class CoverageContext:
    """Result of a multi-dimension coverage retrieval pass."""
    document_id:   Optional[str]
    domain:        str
    dimension_hits: dict[str, list[str]] = field(default_factory=dict)
    # dimension_name -> list of retrieved text chunks

    @property
    def total_chunks(self) -> int:
        return sum(len(v) for v in self.dimension_hits.values())

    @property
    def covered_dimensions(self) -> list[str]:
        return [k for k, v in self.dimension_hits.items() if v]

    @property
    def coverage_ratio(self) -> float:
        """Fraction of dimensions that returned at least one hit."""
        queries = COVERAGE_QUERIES_BY_DOMAIN.get(self.domain, AMC_COVERAGE_QUERIES)
        if not queries:
            return 0.0
        return len(self.covered_dimensions) / len(queries)


def format_coverage_context(
    ctx: CoverageContext,
    max_chars_per_dim: int = 1200,
    separator: str = "\n\n---\n\n",
) -> str:
    """Format a CoverageContext into a single string suitable for LLM prompts.
    
    Each dimension is labeled and capped to max_chars_per_dim.
    """
    parts: list[str] = []
    for dim, chunks in ctx.dimension_hits.items():
        if not chunks:
            continue
        combined = separator.join(chunks)
        if len(combined) > max_chars_per_dim:
            combined = combined[:max_chars_per_dim] + "..."
        parts.append(f"[{dim.upper()}]\n{combined}")
    return (separator + "\n").join(parts)


async def build_taxonomy_context(
    vector_store: Any,
    domain: str = "AMC",
    document_id: Optional[str] = None,
    top_k_per_query: int = 3,
    filters: Optional[dict] = None,
) -> CoverageContext:
    """Run all coverage queries against the vector store and collect results.
    
    Args:
        vector_store: Any vector store with a .search(query, top_k, filters) method.
        domain: Domain key ("AMC" or "insurance") to select the right query set.
        document_id: If set, filters results to this document only.
        top_k_per_query: Number of chunks to retrieve per query dimension.
        filters: Additional metadata filters to apply to all queries.

    Returns:
        CoverageContext with hits per dimension.
    """
    queries = COVERAGE_QUERIES_BY_DOMAIN.get(domain, AMC_COVERAGE_QUERIES)
    ctx = CoverageContext(document_id=document_id, domain=domain)

    search_filters = dict(filters or {})
    if document_id:
        search_filters["document_id"] = document_id

    for dim_name, query_text in queries:
        try:
            results = await vector_store.search(
                query=query_text,
                top_k=top_k_per_query,
                filters=search_filters if search_filters else None,
            )
            # Normalize: handle list-of-str or list-of-dict results
            chunks: list[str] = []
            for r in results:
                if isinstance(r, str):
                    chunks.append(r)
                elif isinstance(r, dict):
                    chunks.append(r.get("text") or r.get("content") or str(r))
                elif hasattr(r, "text"):
                    chunks.append(r.text)
                else:
                    chunks.append(str(r))
            ctx.dimension_hits[dim_name] = chunks
        except Exception:
            ctx.dimension_hits[dim_name] = []

    return ctx


def get_coverage_queries(domain: str = "AMC") -> list[tuple[str, str]]:
    """Return the list of (dimension_name, query_text) tuples for a domain."""
    return COVERAGE_QUERIES_BY_DOMAIN.get(domain, AMC_COVERAGE_QUERIES)
