"""WS5d — Context engineering: structured-facts prioritization, token budget
manager, source attribution assembler, context quality gate, and traversal
explanation generator.

Assembly order (highest priority first):
  1. Structured graph facts (verified, cheap in tokens) — always included.
  2. Vector chunks by score, until the token budget is exhausted.
"""
import logging

from backend.app.config import get_settings
from backend.app.ingestion.chunker import approx_tokens
from backend.app.schemas.query import (
    AssembledContext,
    RetrievalResult,
    SourceAttribution,
)

logger = logging.getLogger("retrieval")


class ContextAssembler:
    def __init__(self) -> None:
        settings = get_settings()
        self._budget = settings.context_token_budget
        self._min_quality = settings.min_context_quality_score

    def assemble(self, result: RetrievalResult) -> AssembledContext:
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

        # --- 1. Structured facts (priority) ---
        fact_lines: list[str] = []
        for fact in result.graph_facts:
            line = f"- {fact.statement}"
            refs = []
            for doc_id in fact.source_document_ids:
                title = self._doc_title(result, doc_id) or doc_id
                refs.append(f"[{source_index(doc_id, title)}]")
            if refs:
                line += " " + "".join(refs)
            fact_lines.append(line)
        if fact_lines:
            block = "STRUCTURED FACTS (from knowledge graph — verified):\n" + "\n".join(fact_lines)
            parts.append(block)
            used_tokens += approx_tokens(block)

        # --- 2. Vector chunks by score within the remaining budget ---
        chunks_included = 0
        chunks_dropped = 0
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
            if used_tokens + cost > self._budget:
                chunks_dropped += 1
                continue
            excerpt_parts.append(block)
            used_tokens += cost
            chunks_included += 1
        if excerpt_parts:
            parts.append("DOCUMENT EXCERPTS:\n\n" + "\n\n".join(excerpt_parts))

        # --- 3. Source list for citation grounding ---
        if sources:
            source_lines = "\n".join(
                f"[{s.source_index}] {s.document_title}" for s in sources
            )
            block = "SOURCES:\n" + source_lines
            parts.append(block)
            used_tokens += approx_tokens(block)

        context_text = "\n\n".join(parts)

        # --- Quality gate ---
        quality = self._quality_score(result, chunks_included)

        return AssembledContext(
            context_text=context_text,
            token_count=used_tokens,
            token_budget=self._budget,
            structured_facts_included=len(result.graph_facts),
            chunks_included=chunks_included,
            chunks_dropped=chunks_dropped,
            sources=sources,
            quality_score=quality,
            passed_quality_gate=quality >= self._min_quality,
            traversal_explanation=result.traversal_paths,
        )

    @staticmethod
    def _doc_title(result: RetrievalResult, document_id: str) -> str | None:
        for chunk in result.chunks:
            if chunk.document_id == document_id:
                return chunk.document_title
        return None

    @staticmethod
    def _quality_score(result: RetrievalResult, chunks_included: int) -> float:
        """Heuristic gate: graph facts are strong signal; chunk scores are weaker.
        0.0 = nothing usable, 1.0 = rich verified context."""
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
