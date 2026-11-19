"""Wave 4.0 (TDS-40 E1/E3): the structured answer path inside the v2 orchestrator.

Active only when AMC_VERIFIED_SERVING_MODE=enforce AND AMC_FIN_PLANE=on. Then, before any cache, graph, vector
or LLM step, the router decides. For STRUCTURED / ABSTAIN / CLARIFY this module returns the final
SynthesisOutput and the orchestrator returns it as-is; there is no fall-through. Only DOCUMENT returns None
and lets the existing verified retrieval path run.

Flags (TDS-40 §5.1) are validated: any value other than "on"/"off" raises, so a typo fails closed instead of
silently disabling the control.
"""
from __future__ import annotations

import asyncio
import logging
import os

from app.models.query import SynthesisOutput
from app.retrieval import composer40
from app.retrieval.intent_router40 import KIND_DOCUMENT, KIND_STRUCTURED, route

logger = logging.getLogger(__name__)

FLAG_FIN_PLANE = "AMC_FIN_PLANE"
FLAG_NUMERIC_GUARD = "AMC_NUMERIC_GUARD"


def _flag(name: str) -> bool:
    value = os.environ.get(name, "off").strip().lower()
    if value not in ("on", "off"):
        raise ValueError(f"{name} must be 'on' or 'off'")
    return value == "on"


def _enforce() -> bool:
    return os.environ.get("AMC_VERIFIED_SERVING_MODE", "off") == "enforce"


def structured_enabled() -> bool:
    return _enforce() and _flag(FLAG_FIN_PLANE)


def numeric_guard_enabled() -> bool:
    return _enforce() and _flag(FLAG_NUMERIC_GUARD)


def validate_flags() -> None:
    """Startup check: refuse to boot with a malformed flag."""
    _flag(FLAG_FIN_PLANE)
    _flag(FLAG_NUMERIC_GUARD)


def _abstain(code: str, message: str | None, options=None, *, kind: str = "ABSTAIN") -> SynthesisOutput:
    text = composer40.abstention_text(code, message, options)
    payload = {"code": code, "message": message or composer40.ABSTAIN_TEXT.get(code, ""),
               "suggestions": list(options or [])}
    return SynthesisOutput(
        answer=text, confidence="high", citations=[], provenance=[],
        compliance_note="No figure was given because it could not be verified.",
        answer_kind=kind,
        abstention=payload if kind == "ABSTAIN" else None,
        clarification={"question": message, "options": list(options or [])} if kind == "CLARIFY" else None,
    )


def _from_result(result) -> SynthesisOutput:
    sr = result.as_dict()
    return SynthesisOutput(
        answer=composer40.render_structured(result),
        structured_rows=composer40.structured_rows(result),
        compliance_note=result.disclosure,
        citations=[],
        provenance=[{
            "source_id": result.dataset_version, "document_id": result.dataset_version,
            "citation_display_label": f"Verified fund dataset {result.dataset_version}",
            "receipt_id": result.receipt_id, "page": None, "kind": "structured_dataset",
            "row_anchor_count": result.row_anchor_count, "anchor_set_sha256": result.anchor_set_sha256,
        }],
        confidence="high",
        answer_kind="STRUCTURED",
        structured_result=sr,
    )


async def structured_answer(query: str, tenant_id: str | None) -> SynthesisOutput | None:
    """Return the final answer for STRUCTURED/ABSTAIN/CLARIFY routes, or None for DOCUMENT."""
    from amc_publication.fin_query40 import FinQueryError
    from amc_publication.serving27 import ServingDenied
    from amc_publication.structured_serving40 import get_structured_executor

    try:
        executor = get_structured_executor()
        catalog = await asyncio.to_thread(executor.catalog, tenant_id)
    except ServingDenied as exc:
        logger.warning("structured catalog unavailable: %s", exc)
        catalog = None
    decision = route(query, catalog)
    if decision.kind == KIND_DOCUMENT:
        return None
    if decision.kind != KIND_STRUCTURED:
        return _abstain(decision.code or "UNSUPPORTED_METRIC", decision.message, decision.options,
                        kind=decision.kind)
    if catalog is None:
        # The question IS about fund numbers but the verified dataset is unavailable: abstain, never fall back.
        return _abstain("STRUCTURED_SOURCE_UNAVAILABLE", None)
    try:
        result = await asyncio.to_thread(executor.execute, tenant_id, decision.plan)
    except FinQueryError as exc:
        kind = "CLARIFY" if exc.code == "AMBIGUOUS_QUERY" and exc.options else "ABSTAIN"
        return _abstain(exc.code, exc.message, exc.options, kind=kind)
    except ServingDenied as exc:
        logger.warning("structured serving denied: %s", exc)
        return _abstain("STRUCTURED_SOURCE_UNAVAILABLE", None)
    except Exception:            # noqa: BLE001  any executor fault abstains; it must not reach the LLM path
        logger.exception("structured executor failed")
        return _abstain("STRUCTURED_SOURCE_UNAVAILABLE", None)
    return _from_result(result)


def guard_document_answer(synthesis: SynthesisOutput, evidence_texts: list[str], question: str) -> SynthesisOutput:
    """Apply the numeric guardrail to a DOCUMENT answer (enforce + AMC_NUMERIC_GUARD=on only)."""
    if synthesis is None or not numeric_guard_enabled():
        return synthesis
    text, dropped = composer40.numeric_guardrail(synthesis.answer, evidence_texts, question)
    if not dropped:
        return synthesis
    logger.warning("numeric guardrail removed %d unsupported sentence(s)", dropped)
    if len(text) < 5:
        return _abstain("UNGROUNDED_NUMBER", None)
    synthesis.answer = text
    synthesis.has_gaps = True
    synthesis.gap_description = f"{dropped} sentence(s) with figures not found in the cited sources were removed."
    return synthesis


__all__ = ["structured_answer", "structured_enabled", "numeric_guard_enabled", "validate_flags",
           "guard_document_answer"]
