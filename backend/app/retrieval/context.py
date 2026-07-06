"""WS5d — Context engineering: structured-facts prioritization, token budget
manager, source attribution assembler, context quality gate, and traversal
explanation generator.

Assembly order (highest priority first):
  1. Structured graph facts (verified, cheap in tokens) — always included first,
     up to graph_fact_quota × token_budget tokens.
  2. Exposure table (EXPOSURE_AGGREGATION queries only) — pre-computed markdown
     table from HOLDS facts so the LLM can echo structured rows accurately.
  3. Vector chunks by score, up to vector_quota × token_budget tokens.
  4. Source list for inline citation grounding.

WS5d changes vs. original:
  - Token budget is now split per section using TraversalStrategy quotas from
    query.py: graph facts and vector chunks each have their own ceiling instead
    of competing in a single first-come-first-served pool.
  - Quality gate is query-type aware: house_view_synthesis uses a lower threshold
    (0.20) because it is deliberately chunk-heavy (55% vector quota), while
    exposure_aggregation uses a higher threshold (0.50) because verified graph
    facts must be present before the LLM synthesises portfolio numbers.
  - _build_exposure_table(): pre-computes a markdown exposure table from HOLDS
    GraphFacts so the synthesis prompt can produce accurate structured_rows
    without hallucinating percentages.
"""
import logging

from backend.app.config import get_settings
from backend.app.ingestion.chunker import approx_tokens
from backend.app.schemas.query import (
    AssembledContext,
    QueryType,
    RetrievalResult,
    SourceAttribution,
    TRAVERSAL_STRATEGIES,
)

logger = logging.getLogger("retrieval")

# Per-query-type quality gate thresholds.
# Rationale:
#   exposure_aggregation — answer lives in HOLDS graph facts; if those are absent
#     the LLM has no verified numbers to cite → high bar.
#   compliance_check — needs both circular facts AND supporting document text;
#     moderate bar.
#   house_view_synthesis — design intent is 55% vector content; chunk-only context
#     is valid and expected → low bar so we don't fall back to the degraded prompt
#     unnecessarily.
#   entity_lookup / general — primarily vector; any semantic hit is useful.
_QUALITY_THRESHOLDS: dict[str, float] = {
    "exposure_aggregation": 0.50,
    "compliance_check":     0.40,
    "house_view_synthesis": 0.20,
    "entity_lookup":        0.25,
    "general":              0.10,
}


class ContextAssembler:
    def __init__(self) -> None:
        settings = get_settings()
        self._budget = settings.context_token_budget
        # Keep as absolute fallback when query type is unknown.
        self._min_quality = settings.min_context_quality_score

    def assemble(self, result: RetrievalResult) -> AssembledContext:
        # ── Derive per-section budgets from the TraversalStrategy registry ──────
        strategy = TRAVERSAL_STRATEGIES.get(result.intent.query_type)
        if strategy:
            graph_budget  = int(self._budget * strategy.graph_fact_quota)
            vector_budget = int(self._budget * strategy.vector_quota)
        else:
            # Fallback: split evenly, leaving 10% for system overhead.
            graph_budget  = int(self._budget * 0.45)
            vector_budget = int(self._budget * 0.45)

        sources: list[SourceAttribution] = []
        doc_to_index: dict[str, int] = {}

        def source_index(document_id: str, title: str, chunk_id: str | None = None,
                         snippet: str | None = None) -> int:
            if document_id not in doc_to_index:
                doc_to_index[document_id] = len(doc_to_index) + 1
                sources.append(SourceAttribution(
                    source_index=doc_to_index[document_id],
                    document_id=document_id,
                    document_title=title,
                    chunk_id=chunk_id,
                    snippet=snippet[:200] if snippet else None,
                ))
            return doc_to_index[document_id]

        parts: list[str] = []
        used_tokens = 0

        # ── 1. Structured facts (highest priority) ────────────────────────────
        fact_lines: list[str] = []
        graph_tokens_used = 0
        for fact in result.graph_facts:
            line = f"- {fact.statement}"
            refs = []
            for doc_id in fact.source_document_ids:
                title = self._doc_title(result, doc_id) or doc_id
                refs.append(f"[{source_index(doc_id, title)}]")
            if refs:
                line += " " + "".join(refs)
            line_cost = approx_tokens(line)
            if graph_tokens_used + line_cost > graph_budget:
                logger.debug(
                    "Graph fact budget exhausted after %d facts (budget=%d tokens)",
                    len(fact_lines), graph_budget,
                )
                break
            fact_lines.append(line)
            graph_tokens_used += line_cost

        if fact_lines:
            block = "STRUCTURED FACTS (from knowledge graph — verified):\n" + "\n".join(fact_lines)
            parts.append(block)
            used_tokens += approx_tokens(block)

        # ── 1b. Exposure table (EXPOSURE_AGGREGATION only) ───────────────────
        # Pre-compute a markdown table from HOLDS facts so the LLM can echo
        # accurate structured_rows without hallucinating pct_nav values.
        if result.intent.query_type == QueryType.EXPOSURE_AGGREGATION:
            table = self._build_exposure_table(result)
            if table:
                table_cost = approx_tokens(table)
                if used_tokens + table_cost <= self._budget:
                    parts.append(table)
                    used_tokens += table_cost

        # ── 2. Vector chunks by score within the vector section budget ────────
        chunks_included = 0
        chunks_dropped = 0
        vector_tokens_used = 0
        excerpt_parts: list[str] = []
        for chunk in sorted(result.chunks, key=lambda c: c.score, reverse=True):
            idx = source_index(
                chunk.document_id,
                chunk.document_title or chunk.document_id,
                chunk.chunk_id,
                chunk.text,
            )
            block = f"[{idx}] ({chunk.document_title}):\n{chunk.text}"
            cost = approx_tokens(block)
            if vector_tokens_used + cost > vector_budget:
                chunks_dropped += 1
                continue
            if used_tokens + cost > self._budget:   # safety net: never exceed total
                chunks_dropped += 1
                continue
            excerpt_parts.append(block)
            used_tokens += cost
            vector_tokens_used += cost
            chunks_included += 1
        if excerpt_parts:
            parts.append("DOCUMENT EXCERPTS:\n\n" + "\n\n".join(excerpt_parts))

        # ── 3. Source list for citation grounding ─────────────────────────────
        if sources:
            source_lines = "\n".join(
                f"[{s.source_index}] {s.document_title}" for s in sources
            )
            block = "SOURCES:\n" + source_lines
            parts.append(block)
            used_tokens += approx_tokens(block)

        context_text = "\n\n".join(parts)

        # ── Quality gate (query-type aware) ───────────────────────────────────
        quality = self._quality_score(result, chunks_included)
        query_type_key = result.intent.query_type.value
        threshold = _QUALITY_THRESHOLDS.get(query_type_key, self._min_quality)
        passed = quality >= threshold
        if not passed:
            logger.warning(
                "Context quality gate failed (score=%.3f < threshold=%.2f) "
                "for query_type=%s",
                quality, threshold, query_type_key,
            )

        return AssembledContext(
            context_text=context_text,
            token_count=used_tokens,
            token_budget=self._budget,
            structured_facts_included=len(fact_lines),
            chunks_included=chunks_included,
            chunks_dropped=chunks_dropped,
            sources=sources,
            quality_score=quality,
            passed_quality_gate=passed,
            traversal_explanation=result.traversal_paths,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_exposure_table(result: RetrievalResult) -> str:
        """Pre-compute a markdown exposure table from HOLDS GraphFacts.

        Gives the synthesis LLM a structured table it can echo back accurately
        as structured_rows, removing the risk of hallucinated pct_nav values.
        Only emitted for EXPOSURE_AGGREGATION queries.
        """
        rows = [
            f"| {f.subject} | {f.object} | {f.properties['pct_nav']}% |"
            for f in result.graph_facts
            if f.predicate == "HOLDS" and f.properties.get("pct_nav") is not None
        ]
        if not rows:
            return ""
        header = (
            "EXPOSURE TABLE (scheme → issuer → % of NAV):\n"
            "| Scheme | Issuer | % NAV |\n"
            "|---|---|---|"
        )
        return header + "\n" + "\n".join(rows)

    @staticmethod
    def _doc_title(result: RetrievalResult, document_id: str) -> str | None:
        for chunk in result.chunks:
            if chunk.document_id == document_id:
                return chunk.document_title
        return None

    @staticmethod
    def _quality_score(result: RetrievalResult, chunks_included: int) -> float:
        """Heuristic quality: graph fact density + top chunk scores.
        0.0 = nothing usable, 1.0 = rich verified context.

        Formula:
          fact_component  = min(fact_count / 5, 1.0) × 0.6
          chunk_component = avg(top-3 chunk scores)    × 0.4
        """
        if not result.graph_facts and not result.chunks:
            return 0.0
        fact_component = min(len(result.graph_facts) / 5.0, 1.0) * 0.6
        if result.chunks:
            top_scores = sorted((c.score for c in result.chunks), reverse=True)[:3]
            chunk_component = (sum(top_scores) / len(top_scores)) * 0.4
        else:
            chunk_component = 0.0
        if chunks_included == 0 and not result.graph_facts:
            return 0.0
        return round(fact_component + chunk_component, 3)
