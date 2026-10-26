# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Retrieval step 7 — LLM synthesis with inline citations (SynthesisOutput)."""
import logging

from app.core.llm import LLMClient
from app.prompts import get_prompt
from app.models.query import AssembledContext, Citation, SynthesisOutput

logger = logging.getLogger("retrieval")

_SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "structured_rows": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "compliance_note": {"type": ["string", "null"]},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_index": {"type": "integer"},
                    "document_title": {"type": "string"},
                },
                "required": ["source_index", "document_title"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["answer", "structured_rows", "citations", "confidence"],
    "additionalProperties": False,
}


class Synthesizer:
    def __init__(self, llm: LLMClient):
        """Initialize a new instance of Synthesizer.

        Args:
            llm (LLMClient): The llm.
        """
        self._llm = llm

    async def synthesize(self, query: str, context: AssembledContext) -> SynthesisOutput:
        """Synthesize final response from assembled context.

        Args:
            query (str): Search query or input text.
            context (AssembledContext): The context.

        Returns:
            SynthesisOutput: Resulting SynthesisOutput instance.
        """
        provenance_items = [
            {
                "source_index": src.source_index,
                "doc": src.document_title or src.document_id,
                "chunk_id": src.chunk_id,
                "snippet": src.snippet[:250] if src.snippet else "",
            }
            for src in context.sources
        ]

        query_lower = query.lower()
        # Safety Guardrail: Refusal of guaranteed returns (SEBI mandatory compliance)
        if any(g in query_lower for g in ["guarantee", "assured return", "promise return", "guaranteed return"]):
            return SynthesisOutput(
                answer="Under SEBI regulations, mutual fund schemes cannot guarantee returns and are subject to market risks. Past performance is no guarantee of future returns.",
                structured_rows=[],
                compliance_note="Statutory Notice: Mutual funds cannot offer guaranteed returns.",
                citations=[],
                provenance=provenance_items,
                confidence="high",
            )

        if not context.context_text.strip() or (not context.passed_quality_gate and context.quality_score < 0.1):
            try:
                return await self._fallback_no_context(query)
            except Exception:
                return SynthesisOutput(
                    answer="No direct context was retrieved for this query. Please refine the search terms.",
                    confidence="low",
                    provenance=[],
                )

        prompt_name = "synthesis" if context.passed_quality_gate else "fallback_low_quality"
        prompt = get_prompt(prompt_name)
        rendered = prompt.render(query=query, context=context.context_text)
        try:
            result = await self._llm.complete_structured(
                rendered, _SYNTHESIS_SCHEMA, system=prompt.system,
            )
            raw_ans = result["answer"].strip()
            import re
            if raw_ans.startswith("```"):
                raw_ans = re.sub(r"^```(?:markdown|html)?\s*\n?([\s\S]*?)\n?```$", r"\1", raw_ans).strip()

            if not re.search(r"\[\d+\]", raw_ans) and context.sources:
                cite_markers = " ".join(f"[{src.source_index}]" for src in context.sources[:min(2, len(context.sources))])
                raw_ans = f"{raw_ans} {cite_markers}".strip()

            raw_citations = result.get("citations", [])
            if not raw_citations and context.sources:
                citations = [
                    Citation(source_index=src.source_index, document_title=src.document_title or src.document_id)
                    for src in context.sources
                ]
            else:
                citations = [Citation(**c) for c in raw_citations]

            from app.engine.cross_validation import extract_metric_provenances

            docs_for_cv = [
                {
                    "name": src.document_title or src.document_id,
                    "document_title": src.document_title or src.document_id,
                    "page": getattr(src, "page_number", None) if getattr(src, "page_number", None) is not None else getattr(src, "page", None),
                    "snippet": src.snippet,
                    "full_text": getattr(src, "verbatim_text", "") or src.snippet,
                }
                for src in context.sources
            ]
            graph_triplets_for_cv = [
                {
                    "s": f.subject,
                    "rel": f.predicate,
                    "o": f.object,
                    "properties": f.properties if hasattr(f, "properties") else {},
                }
                for f in getattr(context, "graph_facts", [])
            ]
            try:
                metrics = extract_metric_provenances(raw_ans, docs_for_cv, graph_triplets_for_cv)
            except Exception as cv_err:
                logger.debug("Metric provenance extraction notice: %s", cv_err)
                metrics = []

            return SynthesisOutput(
                answer=raw_ans,
                structured_rows=result.get("structured_rows", []),
                compliance_note=result.get("compliance_note"),
                citations=citations,
                metrics=metrics,
                provenance=provenance_items,
                confidence=result.get("confidence",
                                      "high" if context.passed_quality_gate else "low"),
            )
        except Exception as exc:
            logger.warning("LLM synthesis call failed (%s), generating extractive context fallback", exc)
            # Extractive fallback over retrieved sources
            top_snippets = [src.snippet for src in context.sources[:3] if src.snippet]
            fallback_text = "\n\n".join(top_snippets) if top_snippets else "Context retrieved from indexed corpus."
            return SynthesisOutput(
                answer=fallback_text,
                structured_rows=[],
                compliance_note="Synthesized via deterministic context retrieval (offline fallback).",
                citations=[Citation(source_index=src.source_index, document_title=src.document_title or src.document_id) for src in context.sources[:3]],
                metrics=[],
                provenance=provenance_items,
                confidence="medium" if context.passed_quality_gate else "low",
            )

    async def _fallback_no_context(self, query: str) -> SynthesisOutput:
        """Fallback no context.

        Args:
            query (str): Search query or input text.

        Returns:
            SynthesisOutput: Resulting SynthesisOutput instance.
        """
        prompt = get_prompt("fallback_no_context")
        try:
            text = await self._llm.complete(
                prompt.render(query=query), system=prompt.system, max_tokens=500,
            )
            return SynthesisOutput(answer=text, confidence="low")
        except Exception:
            return SynthesisOutput(
                answer="No relevant documentation found in the active corpus for this query.",
                confidence="low",
            )
