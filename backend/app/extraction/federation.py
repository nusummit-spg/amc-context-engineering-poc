# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Phase 3 — Federation layer: cross-document concept variance detection.

Adapted from Agentic Testing Platform's federation.py.

After SAME_AS edges are created by the cross-document resolver, this module
analyses whether the same concept has conflicting values across documents.
Each variance is classified as:
  - document_specific_variance: expected (e.g., different AUM as of date)
  - possible_conflict: same constraint defined differently (flag for review)
  - scope_difference: different product/scope (e.g., regular vs direct plan)

Variance records are stored as Neo4j ContextVariance nodes linked via
(ContextVariance)-[:CONFLICTS_BETWEEN]->(Document, Document).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

logger = logging.getLogger("extraction.federation")


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentFactSummary:
    """Lightweight summary of a DocumentFact for variance comparison."""
    fact_id:     str
    document_id: str
    subject:     str
    attribute:   str
    operator:    str
    value:       Any
    unit:        Optional[str]
    confidence:  float
    evidence_text: str = ""


@dataclass
class ContextVariance:
    """A detected variance for the same concept across multiple documents.

    Classification guide:
      document_specific_variance — expected; e.g., AUM changes over time
      possible_conflict           — same constraint defined inconsistently
      scope_difference            — different product scope explains the diff
    """
    variance_id:    str
    canonical_name: str           # entity / concept name
    attribute:      str           # e.g. "single_issuer_limit", "exit_load"
    unit:           Optional[str]
    document_values: list[dict[str, Any]] = field(default_factory=list)
    # Each entry: {document_id, operator, value, unit, confidence, evidence}
    classification: Literal[
        "document_specific_variance",
        "possible_conflict",
        "scope_difference",
    ] = "document_specific_variance"
    requires_resolution: bool = True
    reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def _values_conflict(values: list[Any]) -> bool:
    """True if there are genuinely different values (not just floating-point noise)."""
    unique = set()
    for v in values:
        try:
            unique.add(round(float(v), 4))
        except (TypeError, ValueError):
            unique.add(str(v).lower().strip())
    return len(unique) > 1


def _classify_variance(
    attribute: str,
    operators: list[str],
    values: list[Any],
    unique_documents: int,
) -> tuple[Literal["document_specific_variance", "possible_conflict", "scope_difference"], str]:
    """Classify a detected variance and return (classification, reason)."""
    # Financial metrics change over time — these are expected
    time_varying_subjects = {
        "nav", "aum", "returns", "holding_percentage",
        "expense_ratio", "credit_rating",
    }
    if attribute in time_varying_subjects:
        return (
            "document_specific_variance",
            f"'{attribute}' is time-varying; values naturally differ across documents."
        )

    # Structural limits should be consistent — conflicts here are serious
    structural_limit_subjects = {
        "single_issuer_limit", "single_group_limit", "exit_load",
        "minimum_investment", "lock_in_period",
    }
    if attribute in structural_limit_subjects:
        # Check if operators differ (>= vs <=) — indicates genuine conflict
        unique_ops = set(operators)
        if len(unique_ops) > 1:
            return (
                "possible_conflict",
                f"'{attribute}' has conflicting operators ({sorted(unique_ops)}) across "
                f"{unique_documents} documents — same constraint defined differently."
            )
        return (
            "possible_conflict",
            f"Structural limit '{attribute}' has different values "
            f"({sorted(set(str(v) for v in values))}) across {unique_documents} documents."
        )

    # Default: flag as possible conflict for manual review
    return (
        "possible_conflict",
        f"'{attribute}' has different values across {unique_documents} documents — "
        "manual review recommended."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def detect_context_variances(
    facts_by_document: dict[str, list[DocumentFactSummary]],
) -> list[ContextVariance]:
    """Detect variances in the same concept across multiple documents.

    Args:
        facts_by_document: Mapping from document_id to list of extracted facts.

    Returns:
        List of ContextVariance records, one per conflicting (subject, attribute, unit) triple.

    Algorithm:
        1. Group all facts by (subject, attribute, unit).
        2. For each group spanning > 1 document, check if values differ.
        3. If values differ, classify and emit a ContextVariance.
    """
    from collections import defaultdict

    # Group facts by (subject, attribute, unit)
    groups: dict[
        tuple[str, str, str | None],
        list[DocumentFactSummary],
    ] = defaultdict(list)

    for doc_id, facts in facts_by_document.items():
        for f in facts:
            key = (f.subject, f.attribute, f.unit)
            groups[key].append(f)

    variances: list[ContextVariance] = []

    for (subject, attribute, unit), fact_list in groups.items():
        # Only consider groups that span multiple documents
        doc_ids = {f.document_id for f in fact_list}
        if len(doc_ids) <= 1:
            continue

        values  = [f.value for f in fact_list]
        ops     = [f.operator for f in fact_list]

        # Only flag if values actually differ
        if not _values_conflict(values):
            continue

        classification, reason = _classify_variance(
            attribute=attribute,
            operators=ops,
            values=values,
            unique_documents=len(doc_ids),
        )

        vid = _stable_id(
            "VAR",
            f"{subject}:{attribute}:{unit}:{sorted(doc_ids)}",
        )

        variances.append(ContextVariance(
            variance_id=vid,
            canonical_name=subject,
            attribute=attribute,
            unit=unit,
            document_values=[
                {
                    "document_id":  f.document_id,
                    "operator":     f.operator,
                    "value":        f.value,
                    "unit":         f.unit,
                    "confidence":   f.confidence,
                    "evidence":     f.evidence_text[:200],
                }
                for f in fact_list[:10]
            ],
            classification=classification,
            requires_resolution=classification == "possible_conflict",
            reason=reason,
        ))

        logger.info(
            "Context variance detected: %s/%s/%s — %s across %d documents [%s]",
            subject, attribute, unit, classification, len(doc_ids), vid,
        )

    logger.info(
        "Federation scan complete: %d variances detected (%d require resolution).",
        len(variances),
        sum(1 for v in variances if v.requires_resolution),
    )
    return variances


async def persist_variances(
    variances: list[ContextVariance],
    graph_client: Any,  # GraphClient — avoid circular import
) -> int:
    """Persist ContextVariance records to Neo4j.

    Creates ContextVariance nodes and links them to the relevant Document nodes.
    Returns the number of variance nodes created or updated.
    """
    if not variances:
        return 0

    created = 0
    for v in variances:
        try:
            await graph_client.run(
                """
                MERGE (cv:ContextVariance {variance_id: $vid})
                SET cv.canonical_name    = $canonical_name,
                    cv.attribute         = $attribute,
                    cv.unit              = $unit,
                    cv.classification    = $classification,
                    cv.requires_resolution = $requires_resolution,
                    cv.reason            = $reason,
                    cv.document_count    = $doc_count
                """,
                vid=v.variance_id,
                canonical_name=v.canonical_name,
                attribute=v.attribute,
                unit=v.unit or "",
                classification=v.classification,
                requires_resolution=v.requires_resolution,
                reason=v.reason,
                doc_count=len(v.document_values),
            )
            # Link to each contributing document
            for dv in v.document_values:
                await graph_client.run(
                    """
                    MATCH (cv:ContextVariance {variance_id: $vid})
                    MATCH (d:Document {document_id: $doc_id})
                    MERGE (cv)-[r:CONFLICTS_BETWEEN]->(d)
                    SET r.value    = $value,
                        r.operator = $operator,
                        r.unit     = $unit
                    """,
                    vid=v.variance_id,
                    doc_id=dv["document_id"],
                    value=str(dv.get("value", "")),
                    operator=dv.get("operator", "="),
                    unit=dv.get("unit") or "",
                )
            created += 1
        except Exception as exc:
            logger.warning("Failed to persist variance %s: %s", v.variance_id, exc)

    logger.info("Persisted %d/%d variance nodes to Neo4j.", created, len(variances))
    return created
