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
        if not context.context_text.strip():
            return await self._fallback_no_context(query)
        prompt_name = "synthesis" if context.passed_quality_gate else "fallback_low_quality"
        prompt = get_prompt(prompt_name)
        rendered = prompt.render(query=query, context=context.context_text)
        result = await self._llm.complete_structured(
            rendered, _SYNTHESIS_SCHEMA, system=prompt.system,
        )
        return SynthesisOutput(
            answer=result["answer"],
            structured_rows=result.get("structured_rows", []),
            compliance_note=result.get("compliance_note"),
            citations=[Citation(**c) for c in result.get("citations", [])],
            confidence=result.get("confidence",
                                  "high" if context.passed_quality_gate else "low"),
        )

    async def _fallback_no_context(self, query: str) -> SynthesisOutput:
        prompt = get_prompt("fallback_no_context")
        text = await self._llm.complete(
            prompt.render(query=query), system=prompt.system, max_tokens=500,
        )
        return SynthesisOutput(answer=text, confidence="low")
