# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import logging
import time
from typing import AsyncGenerator, Optional
from uuid import uuid4

from app.config import get_settings
from app.extraction.resolver import EntityResolver
from app.retrieval.context import ContextAssembler
from app.retrieval.intent import IntentClassifier
from app.retrieval.synthesizer import Synthesizer
from app.retrieval.traversal import GraphTraversal
from app.schemas.entities import BaseEntity
from app.schemas.query import (
    AssembledContext,
    QueryIntent,
    QueryTrace,
    RetrievalResult,
    RetrievedChunk,
    SynthesisOutput,
)
from app.vector.client import VectorStore

logger = logging.getLogger("retrieval")


NAMESPACE_KEYWORDS = {
    "sebi_regulation": ["sebi", "circular", "categorization", "regulation", "compliance", "mutual fund rules", "2026", "2017", "master circular", "amfi"],
    "adani_corporate": ["adani", "ael", "aahl", "ebitda", "revenue", "pat", "fy25", "fy24", "fy23", "earnings", "credit"],
    "esg_sustainability": ["esg", "brsr", "climate", "carbon", "greenwashing", "sustainability", "emissions", "green"],
    "fund_performance": ["nav", "returns", "aum", "benchmark", "alpha", "sharpe ratio", "fund performance", "scheme performance", "sid", "exit load", "ter"],
}


def route_query_namespace(query: str) -> list[str]:
    """Returns list of relevant namespaces (can be multiple for cross-domain queries)."""
    query_lower = query.lower()
    active = []
    for ns, keywords in NAMESPACE_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            active.append(ns)
    return active if active else ["all"]


class OrchestratorResponse:
    """Wrapper that supports both 4-tuple unpacking and direct attribute access including trace."""
    def __init__(
        self,
        intent: QueryIntent,
        retrieval: RetrievalResult,
        context: AssembledContext,
        synthesis: SynthesisOutput,
        trace: Optional[QueryTrace] = None,
    ):
        self.intent = intent
        self.retrieval = retrieval
        self.context = context
        self.synthesis = synthesis
        self.trace = trace

    def __iter__(self):
        return iter((self.intent, self.retrieval, self.context, self.synthesis))


class RetrievalOrchestrator:
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        resolver: EntityResolver,
        traversal: GraphTraversal,
        vector_store: VectorStore,
        assembler: ContextAssembler,
        synthesizer: Synthesizer,
    ):
        self._intent = intent_classifier
        self._resolver = resolver
        self._traversal = traversal
        self._vector = vector_store
        self._assembler = assembler
        self._synthesizer = synthesizer
        self._settings = get_settings()
        self._top_k = self._settings.vector_top_k
        self._corpus_version = getattr(self._settings, "active_corpus_version", "v2_baseline_20260814")

    async def answer(
        self,
        query: str,
        top_k: int | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> OrchestratorResponse:
        t0 = time.perf_counter()
        req_id = str(uuid4())

        # Step 0 — Multi-turn context rewrite & Coreference resolution (PV-02B)
        t_rewrite_start = time.perf_counter()
        effective_query = query
        if history and len(history) > 0:
            user_msgs = []
            for msg in history:
                role = msg.get("role") or msg.get("sender") or ""
                content = msg.get("content") or msg.get("text") or msg.get("query") or ""
                if (role.lower() in ("user", "human") or not role) and content:
                    user_msgs.append(content)
            if user_msgs:
                last_user_query = user_msgs[-1]
                pronoun_triggers = {"those", "these", "them", "it", "they", "that", "theirs", "this"}
                words_in_query = set(query.lower().replace("?", "").replace(".", "").split())
                if pronoun_triggers & words_in_query:
                    effective_query = f"{last_user_query} — {query}"
        t_rewrite_ms = (time.perf_counter() - t_rewrite_start) * 1000

        # Step 0.5 — Configurable Pre-Retrieval Safety Guardrail Interceptor
        if self._settings.enable_pre_retrieval_guardrails:
            q_clean = query.lower().strip()
            if any(w in q_clean for w in ["guarantee", "assured return", "promise return", "guaranteed profit", "15% annual return", "fixed return"]):
                logger.info("Pre-retrieval safety guardrail triggered: SEBI guaranteed return refusal")
                synth = SynthesisOutput(
                    answer="Under SEBI regulations, mutual fund schemes cannot guarantee returns and are subject to market risks. Past performance is no guarantee of future returns.",
                    compliance_note="Statutory Notice: Mutual funds cannot offer guaranteed returns.",
                    citations=[],
                    provenance=[],
                    confidence="high",
                )
                total_ms = (time.perf_counter() - t0) * 1000
                trace = QueryTrace(
                    request_id=req_id,
                    serving_engine="v2",
                    corpus_version=self._corpus_version,
                    cache_hit=False,
                    request_total_ms=round(total_ms, 2),
                    quality_gate_passed=True,
                )
                return OrchestratorResponse(
                    intent=None,
                    retrieval=None,
                    context=None,
                    synthesis=synth,
                    trace=trace,
                )

        # Step 1 — Semantic Cache Check (PV-02A)
        t_cache_start = time.perf_counter()
        from app.retrieval.cache import get_semantic_cache
        cache = get_semantic_cache()
        cached_entry = None
        try:
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version)
        except Exception as exc:
            logger.debug("Cache lookup notice: %s", exc)
        t_cache_lookup_ms = (time.perf_counter() - t_cache_start) * 1000

        if cached_entry and cached_entry.get("cache_hit"):
            logger.info("Serving from semantic cache (<30ms short-circuit): %s", query)
            total_ms = (time.perf_counter() - t0) * 1000
            
            cached_synth = SynthesisOutput(
                answer=cached_entry.get("answer", ""),
                confidence=cached_entry.get("confidence", "high"),
                compliance_note=cached_entry.get("compliance_note"),
                citations=cached_entry.get("citations", []),
                provenance=cached_entry.get("provenance", []),
                structured_rows=cached_entry.get("structured_rows", []),
            )
            from app.schemas.query import Citation, GraphFact, SourceAttribution
            cached_sources = [
                SourceAttribution(**s) if isinstance(s, dict) else s
                for s in cached_entry.get("sources", [])
            ]
            cached_facts = [
                GraphFact(**f) if isinstance(f, dict) else f
                for f in cached_entry.get("graph_facts", [])
            ]
            cached_intent = QueryIntent(**cached_entry["intent"]) if "intent" in cached_entry else QueryIntent(query_type="general")
            
            cached_context = AssembledContext(
                context_text=cached_entry.get("context_text", cached_synth.answer),
                token_count=0,
                token_budget=getattr(self._settings, "context_token_budget", 12000),
                sources=cached_sources,
                quality_score=cached_entry.get("quality_score", 1.0),
                passed_quality_gate=True,
            )
            cached_retrieval = RetrievalResult(
                intent=cached_intent,
                resolved_entities={},
                graph_facts=cached_facts,
                chunks=[],
                traversal_paths=cached_entry.get("traversal_paths", []),
                cypher_queries_run=[],
            )
            
            trace = QueryTrace(
                request_id=req_id,
                serving_engine="v2",
                corpus_version=self._corpus_version,
                cache_hit=True,
                cache_lookup_ms=round(t_cache_lookup_ms, 2),
                query_rewrite_ms=round(t_rewrite_ms, 2),
                ner_ms=0.0,
                graph_ms=0.0,
                vector_ms=0.0,
                rerank_ms=0.0,
                assembly_ms=0.0,
                generation_ms=0.0,
                request_total_ms=round(total_ms, 2),
                input_tokens=0,
                output_tokens=cached_entry.get("output_tokens", len(cached_synth.answer.split()) * 2),
                quality_score=round(cached_entry.get("quality_score", 1.0), 2),
                quality_gate_passed=True,
                fallback_used=False,
                fallback_reason=None,
            )
            return OrchestratorResponse(
                intent=cached_intent,
                retrieval=cached_retrieval,
                context=cached_context,
                synthesis=cached_synth,
                trace=trace,
            )

        active_namespaces = route_query_namespace(effective_query)
        logger.info("Query routed to namespaces: %s", active_namespaces)

        # Step 2 — intent
        t_ner_start = time.perf_counter()
        intent = await self._intent.classify(effective_query)
        logger.info("Intent: %s | entities=%s | taxonomy=%s",
                    intent.query_type.value, intent.entities_mentioned, intent.taxonomy_paths)

        # Step 3 — entity resolution
        resolved_entities: list[BaseEntity] = []
        resolved_map: dict[str, str] = {}
        for surface in intent.entities_mentioned:
            res = self._resolver.resolve_surface_form(surface)
            if res and res.entity:
                resolved_entities.append(res.entity)
                resolved_map[surface] = res.entity.name
        t_ner_ms = (time.perf_counter() - t_ner_start) * 1000

        # Step 4 — graph traversal
        t_graph_start = time.perf_counter()
        facts, traversal_paths, cyphers = [], [], []
        if intent.requires_graph and resolved_entities:
            facts, traversal_paths, cyphers = await self._traversal.traverse(
                intent, resolved_entities
            )
        t_graph_ms = (time.perf_counter() - t_graph_start) * 1000

        # Steps 5-6 — taxonomy-scoped vector search
        t_vector_start = time.perf_counter()
        chunks: list[RetrievedChunk] = []
        if intent.requires_vector:
            hits = await self._vector.search(
                effective_query,
                top_k=top_k or self._top_k,
                taxonomy_paths=intent.taxonomy_paths or None,
                entity_names=[e.name for e in resolved_entities] or None,
            )
            chunks = [
                RetrievedChunk(
                    chunk_id=h["chunk_id"],
                    document_id=h.get("document_id", ""),
                    document_title=h.get("document_title"),
                    text=h.get("text", ""),
                    score=h.get("score", 0.0),
                    taxonomy_paths=h.get("taxonomy_paths", []),
                )
                for h in hits
            ]
        t_vector_ms = (time.perf_counter() - t_vector_start) * 1000

        retrieval = RetrievalResult(
            intent=intent,
            resolved_entities=resolved_map,
            graph_facts=facts,
            chunks=chunks,
            traversal_paths=traversal_paths,
            cypher_queries_run=cyphers,
        )

        # Step 7 — context assembly
        t_asm_start = time.perf_counter()
        context = self._assembler.assemble(retrieval)
        if not context.passed_quality_gate:
            logger.warning("Context quality gate failed (score=%.2f) for query: %s",
                           context.quality_score, effective_query)
        t_asm_ms = (time.perf_counter() - t_asm_start) * 1000

        # Step 8 — synthesis
        t_gen_start = time.perf_counter()
        synthesis = await self._synthesizer.synthesize(effective_query, context)
        t_gen_ms = (time.perf_counter() - t_gen_start) * 1000

        total_ms = (time.perf_counter() - t0) * 1000

        # Cache population on miss
        try:
            cache.store(
                effective_query,
                {
                    "answer": synthesis.answer,
                    "confidence": synthesis.confidence,
                    "compliance_note": synthesis.compliance_note,
                    "citations": [c.model_dump() for c in synthesis.citations],
                    "provenance": synthesis.provenance,
                    "quality_score": context.quality_score,
                    "output_tokens": len(synthesis.answer.split()) * 2 if synthesis.answer else 0,
                    "intent": intent.model_dump(),
                    "traversal_paths": traversal_paths,
                    "graph_facts": [f.model_dump() for f in facts],
                    "sources": [s.model_dump() for s in context.sources],
                },
                corpus_version=self._corpus_version,
            )
        except Exception as exc:
            logger.debug("Cache store notice: %s", exc)

        trace = QueryTrace(
            request_id=req_id,
            serving_engine="v2",
            corpus_version=self._corpus_version,
            cache_hit=False,
            cache_lookup_ms=round(t_cache_lookup_ms, 2),
            query_rewrite_ms=round(t_rewrite_ms, 2),
            ner_ms=round(t_ner_ms, 2),
            graph_ms=round(t_graph_ms, 2),
            vector_ms=round(t_vector_ms, 2),
            rerank_ms=0.0,
            assembly_ms=round(t_asm_ms, 2),
            generation_ms=round(t_gen_ms, 2),
            request_total_ms=round(total_ms, 2),
            input_tokens=context.token_count,
            output_tokens=len(synthesis.answer.split()) * 2 if synthesis.answer else 0,
            quality_score=round(context.quality_score, 2),
            quality_gate_passed=context.passed_quality_gate,
            fallback_used=False,
            fallback_reason=None,
        )

        return OrchestratorResponse(
            intent=intent,
            retrieval=retrieval,
            context=context,
            synthesis=synthesis,
            trace=trace,
        )

    async def traditional_search(self, query: str, top_k: int | None = None) -> list[dict]:
        """Flat vector search with no graph, no taxonomy scoping, no synthesis —
        the 'traditional RAG' comparison baseline."""
        hits = await self._vector.search(query, top_k=top_k or self._top_k)
        return hits

    async def answer_stream(
        self,
        query: str,
        top_k: int | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream the answer pipeline as SSE-shaped dicts.

        Event shapes:
            {"type": "metadata",  "intent": ..., "entities": ...}
            {"type": "sources",   "sources": [...]}
            {"type": "answer_chunk", "text": "...", "index": N}
            {"type": "complete",  "response_id": "...", "trace": {...}}
            {"type": "error",     "message": "...", "recoverable": True/False}

        Edge cases handled:
        - Cache hit: yields complete answer immediately in chunks (simulated stream)
        - Step failure: yields error chunk with recoverable=True, continues degraded
        - Multi-turn: rewrites query via coreference resolution before streaming
        """
        t0 = time.perf_counter()
        req_id = str(uuid4())
        response_id = f"resp_{req_id[:12]}"

        # ── Step 0: Multi-turn query rewrite ─────────────────────────────
        effective_query = query
        if history:
            user_msgs = []
            for msg in history:
                role = msg.get("role") or msg.get("sender") or ""
                content = msg.get("content") or msg.get("text") or msg.get("query") or ""
                if (role.lower() in ("user", "human") or not role) and content:
                    user_msgs.append(content)
            if user_msgs:
                pronoun_triggers = {"those", "these", "them", "it", "they", "that", "theirs", "this"}
                words_in_query = set(query.lower().replace("?", "").replace(".", "").split())
                if pronoun_triggers & words_in_query:
                    effective_query = f"{user_msgs[-1]} — {query}"

        # ── Step 0.5: Pre-retrieval safety guardrail ──────────────────────
        if self._settings.enable_pre_retrieval_guardrails:
            q_clean = query.lower().strip()
            if any(w in q_clean for w in ["guarantee", "assured return", "promise return", "guaranteed profit",
                                           "15% annual return", "fixed return"]):
                safe_answer = (
                    "Under SEBI regulations, mutual fund schemes cannot guarantee returns "
                    "and are subject to market risks. Past performance is no guarantee of future returns."
                )
                for idx, word in enumerate(safe_answer.split()):
                    yield {"type": "answer_chunk", "text": (word + " "), "index": idx}
                yield {"type": "complete", "response_id": response_id, "trace": {}}
                return

        # ── Step 1: Semantic cache lookup ─────────────────────────────────
        from app.retrieval.cache import get_semantic_cache
        cache = get_semantic_cache()
        cached_entry = None
        try:
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version)
        except Exception as exc:
            logger.debug("Cache lookup notice: %s", exc)

        if cached_entry and cached_entry.get("cache_hit"):
            logger.info("Streaming from semantic cache: %s", query)
            # Stream cached intent as metadata
            cached_intent = cached_entry.get("intent", {})
            yield {
                "type": "metadata",
                "intent": cached_intent.get("query_type", "general"),
                "entities": cached_intent.get("entities_mentioned", []),
                "confidence": cached_entry.get("confidence", "high"),
            }
            # Stream cached sources
            cached_sources = cached_entry.get("sources", [])
            if cached_sources:
                yield {"type": "sources", "sources": cached_sources}
            # Stream cached answer word-by-word
            cached_answer = cached_entry.get("answer", "")
            words = cached_answer.split()
            for idx, word in enumerate(words):
                yield {"type": "answer_chunk", "text": (word + " "), "index": idx}
            yield {
                "type": "complete",
                "response_id": response_id,
                "trace": {"cache_hit": True, "request_total_ms": round((time.perf_counter() - t0) * 1000, 2)},
            }
            return

        # ── Step 2: Intent classification ────────────────────────────────
        intent = None
        try:
            intent = await self._intent.classify(effective_query)
            yield {
                "type": "metadata",
                "intent": intent.query_type.value if intent else "general",
                "entities": intent.entities_mentioned if intent else [],
                "confidence": "high",
            }
        except Exception as exc:
            logger.warning("Intent classification failed during streaming: %s", exc)
            yield {"type": "error", "message": f"Intent classification error: {exc}", "recoverable": True}

        # ── Step 3: Entity resolution ─────────────────────────────────────
        resolved_entities = []
        resolved_map: dict[str, str] = {}
        if intent:
            try:
                for surface in intent.entities_mentioned:
                    res = self._resolver.resolve_surface_form(surface)
                    if res and res.entity:
                        resolved_entities.append(res.entity)
                        resolved_map[surface] = res.entity.name
            except Exception as exc:
                logger.warning("Entity resolution failed during streaming: %s", exc)
                yield {"type": "error", "message": f"Entity resolution error: {exc}", "recoverable": True}

        # ── Step 4: Graph traversal ───────────────────────────────────────
        facts, traversal_paths, cyphers = [], [], []
        if intent and intent.requires_graph and resolved_entities:
            try:
                facts, traversal_paths, cyphers = await self._traversal.traverse(intent, resolved_entities)
            except Exception as exc:
                logger.warning("Graph traversal failed during streaming: %s", exc)
                yield {"type": "error", "message": f"Graph traversal error: {exc}", "recoverable": True}

        # ── Steps 5-6: Vector search ──────────────────────────────────────
        from app.schemas.query import RetrievedChunk
        chunks: list[RetrievedChunk] = []
        if intent and intent.requires_vector:
            try:
                hits = await self._vector.search(
                    effective_query,
                    top_k=top_k or self._top_k,
                    taxonomy_paths=intent.taxonomy_paths or None,
                    entity_names=[e.name for e in resolved_entities] or None,
                )
                chunks = [
                    RetrievedChunk(
                        chunk_id=h["chunk_id"],
                        document_id=h.get("document_id", ""),
                        document_title=h.get("document_title"),
                        text=h.get("text", ""),
                        score=h.get("score", 0.0),
                        taxonomy_paths=h.get("taxonomy_paths", []),
                    )
                    for h in hits
                ]
                # Stream sources immediately so frontend can render them
                sources_payload = [
                    {
                        "document_title": c.document_title or c.document_id,
                        "document_id": c.document_id,
                        "snippet": c.text[:200] if c.text else "",
                        "score": c.score,
                    }
                    for c in chunks
                ]
                yield {"type": "sources", "sources": sources_payload}
            except Exception as exc:
                logger.warning("Vector search failed during streaming: %s", exc)
                yield {"type": "error", "message": f"Vector search error: {exc}", "recoverable": True}

        # ── Step 7: Context assembly ──────────────────────────────────────
        from app.schemas.query import RetrievalResult
        retrieval = RetrievalResult(
            intent=intent,
            resolved_entities=resolved_map,
            graph_facts=facts,
            chunks=chunks,
            traversal_paths=traversal_paths,
            cypher_queries_run=cyphers,
        )

        context = None
        try:
            context = self._assembler.assemble(retrieval)
        except Exception as exc:
            logger.warning("Context assembly failed during streaming: %s", exc)
            yield {"type": "error", "message": f"Context assembly error: {exc}", "recoverable": True}

        # ── Step 8: LLM streaming synthesis ──────────────────────────────
        chunk_index = 0
        full_answer = ""
        try:
            from app.prompts import get_prompt
            try:
                system_prompt = get_prompt("synthesis_system").text if context else None
            except Exception:
                system_prompt = None
            ctx_text = context.context_text if context else ""

            async for text_chunk in self._synthesizer._llm.complete_stream(
                prompt=f"Query: {effective_query}\n\nContext:\n{ctx_text}",
                system=system_prompt,
            ):
                full_answer += text_chunk
                yield {"type": "answer_chunk", "text": text_chunk, "index": chunk_index}
                chunk_index += 1
        except Exception as exc:
            logger.warning("LLM streaming synthesis failed: %s", exc)
            # Fallback: attempt non-streaming synthesis
            yield {"type": "error", "message": f"Streaming synthesis error, attempting fallback: {exc}", "recoverable": True}
            try:
                if context:
                    synth = await self._synthesizer.synthesize(effective_query, context)
                    fallback_text = synth.answer or ""
                    for idx, word in enumerate(fallback_text.split()):
                        full_answer += word + " "
                        yield {"type": "answer_chunk", "text": word + " ", "index": chunk_index + idx}
                    full_answer = fallback_text
            except Exception as fallback_exc:
                logger.error("Fallback synthesis also failed: %s", fallback_exc)
                yield {"type": "error", "message": "Unable to generate answer", "recoverable": False}

        total_ms = round((time.perf_counter() - t0) * 1000, 2)

        # ── Cache the streamed answer ─────────────────────────────────────
        if full_answer and context:
            try:
                cache.store(
                    effective_query,
                    {
                        "answer": full_answer.strip(),
                        "confidence": "high",
                        "compliance_note": None,
                        "citations": [],
                        "provenance": [],
                        "quality_score": context.quality_score,
                        "output_tokens": len(full_answer.split()) * 2,
                        "intent": intent.model_dump() if intent else {},
                        "traversal_paths": traversal_paths,
                        "graph_facts": [f.model_dump() for f in facts],
                        "sources": [s.model_dump() for s in context.sources],
                    },
                    corpus_version=self._corpus_version,
                )
            except Exception as exc:
                logger.debug("Stream cache store notice: %s", exc)

        yield {
            "type": "complete",
            "response_id": response_id,
            "trace": {
                "cache_hit": False,
                "request_total_ms": total_ms,
                "chunks_streamed": chunk_index,
            },
        }

