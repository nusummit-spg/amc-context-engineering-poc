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
from app.schemas.query import AssembledContext, Citation, SynthesisOutput

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
        self._llm = llm

    async def synthesize(self, query: str, context: AssembledContext) -> SynthesisOutput:
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
            return SynthesisOutput(
                answer=result["answer"],
                structured_rows=result.get("structured_rows", []),
                compliance_note=result.get("compliance_note"),
                citations=[Citation(**c) for c in result.get("citations", [])],
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
                provenance=provenance_items,
                confidence="medium" if context.passed_quality_gate else "low",
            )

    async def _fallback_no_context(self, query: str) -> SynthesisOutput:
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
