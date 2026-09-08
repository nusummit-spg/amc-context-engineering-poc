# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import asyncio
import logging
import time
from typing import AsyncGenerator, Optional
from uuid import uuid4

from app.config import get_settings
from app.core.metrics import ComponentMetric, QueryMetrics, get_metrics_store
from app.engine import config, hyde, text_to_cypher
from app.extraction.resolver import EntityResolver
from app.retrieval.cache import get_semantic_cache
from app.retrieval.context import ContextAssembler
from app.retrieval.intent import IntentClassifier
from app.retrieval.planner import ExecutionPlan, get_planner
from app.retrieval.synthesizer import Synthesizer
from app.retrieval.traversal import GraphTraversal
from app.schemas.entities import BaseEntity
from app.schemas.query import (
    AssembledContext,
    GraphFact,
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
    """Wrapper that supports both 4-tuple unpacking and direct attribute access including trace and metrics."""
    def __init__(
        self,
        intent: Optional[QueryIntent],
        retrieval: Optional[RetrievalResult],
        context: Optional[AssembledContext],
        synthesis: SynthesisOutput,
        trace: Optional[QueryTrace] = None,
        metrics: Optional[QueryMetrics] = None,
    ):
        self.intent = intent
        self.retrieval = retrieval
        self.context = context
        self.synthesis = synthesis
        self.trace = trace
        self.metrics = metrics

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
        self._planner = get_planner()

    # ------------------------------------------------------------------
    # Vector retrieval helpers (Phase 3 — plan execution & parallelism)
    # ------------------------------------------------------------------

    @staticmethod
    def _hits_to_chunks(hits: list[dict]) -> list[RetrievedChunk]:
        return [
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

    async def _search_chunks(
        self,
        search_query: str,
        top_k: int,
        intent: QueryIntent,
        resolved_entities: list[BaseEntity],
    ) -> list[RetrievedChunk]:
        """Single taxonomy-scoped vector search."""
        hits = await self._vector.search(
            search_query,
            top_k=top_k,
            taxonomy_paths=intent.taxonomy_paths or None,
            entity_names=[e.name for e in resolved_entities] or None,
        )
        return self._hits_to_chunks(hits)

    async def _execute_plan_retrieval(
        self,
        plan: Optional[ExecutionPlan],
        search_query: str,
        hyde_doc: str,
        top_k: int,
        intent: QueryIntent,
        resolved_entities: list[BaseEntity],
    ) -> list[RetrievedChunk]:
        """Executes the retrieval sub-tasks of an execution plan.

        A complex plan (e.g. "Compare A vs B") decomposes into one retrieval
        branch per entity. Each branch is searched concurrently and the results
        are merged, deduped by chunk_id and re-ranked by score — so a comparison
        gets balanced evidence for both sides instead of whichever side dominates
        a single blended query. Simple plans fall through to one search.
        """
        retrieval_tasks = []
        if plan is not None and plan.is_complex:
            from app.retrieval.planner import ExecutionToolType

            for group in plan.parallel_groups():
                for task in group:
                    if task.tool != ExecutionToolType.VECTOR_SEARCH:
                        continue
                    sub_query = (task.params or {}).get("query")
                    if sub_query and sub_query.strip():
                        retrieval_tasks.append(sub_query.strip())

        if not retrieval_tasks:
            return await self._search_chunks(search_query, top_k, intent, resolved_entities)

        # Branch queries keep the HyDE augmentation so both paths embed alike.
        branch_queries = [
            (q + "\n\nHYPOTHETICAL DOCUMENT:\n" + hyde_doc) if hyde_doc else q
            for q in retrieval_tasks
        ]
        # Split the budget across branches, with a floor so each branch is useful.
        per_branch_k = max(3, top_k // max(1, len(branch_queries)))

        results = await asyncio.gather(
            *[
                self._search_chunks(bq, per_branch_k, intent, resolved_entities)
                for bq in branch_queries
            ],
            return_exceptions=True,
        )

        merged: dict[str, RetrievedChunk] = {}
        for branch_result in results:
            if isinstance(branch_result, Exception):
                logger.warning("Plan retrieval branch failed: %s", branch_result)
                continue
            for chunk in branch_result:
                existing = merged.get(chunk.chunk_id)
                if existing is None or chunk.score > existing.score:
                    merged[chunk.chunk_id] = chunk

        if not merged:
            return await self._search_chunks(search_query, top_k, intent, resolved_entities)

        chunks = sorted(merged.values(), key=lambda c: c.score, reverse=True)[:top_k]
        logger.info(
            "Plan retrieval: %d branches -> %d unique chunks (kept %d)",
            len(branch_queries), len(merged), len(chunks),
        )
        return chunks

    async def answer(
        self,
        query: str,
        top_k: int | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
        enable_hyde: bool = True,
        enable_decomposition: bool = True,
        track_metrics: bool = True,
    ) -> OrchestratorResponse:
        t0 = time.perf_counter()
        req_id = str(uuid4())
        metrics = QueryMetrics(request_id=req_id, query=query) if track_metrics else None

        # Step 0 — Multi-turn context rewrite & Coreference resolution (PV-02B)
        comp_rewrite = ComponentMetric("query_rewrite", time.perf_counter())
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
        comp_rewrite.finalize()
        if metrics:
            metrics.add_component(comp_rewrite)

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
                if metrics:
                    metrics.total_latency_ms = total_ms
                    metrics.query_type = "compliance_refusal"
                    get_metrics_store().record(metrics)
                return OrchestratorResponse(
                    intent=None,
                    retrieval=None,
                    context=None,
                    synthesis=synth,
                    trace=trace,
                    metrics=metrics,
                )

        # Step 1 — Semantic Cache Check (PV-02A)
        comp_cache = ComponentMetric("semantic_cache_lookup", time.perf_counter())
        t_cache_start = time.perf_counter()
        cache = get_semantic_cache()
        cached_entry = None
        try:
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version)
        except Exception as exc:
            logger.debug("Cache lookup notice: %s", exc)
        t_cache_lookup_ms = (time.perf_counter() - t_cache_start) * 1000
        comp_cache.cache_hit = bool(cached_entry and cached_entry.get("cache_hit"))
        comp_cache.finalize()
        if metrics:
            metrics.add_component(comp_cache)

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
            if metrics:
                metrics.total_latency_ms = total_ms
                metrics.cache_hit = True
                metrics.query_type = cached_intent.query_type.value if hasattr(cached_intent, "query_type") else "general"
                get_metrics_store().record(metrics)

            return OrchestratorResponse(
                intent=cached_intent,
                retrieval=cached_retrieval,
                context=cached_context,
                synthesis=cached_synth,
                trace=trace,
                metrics=metrics,
            )

        active_namespaces = route_query_namespace(effective_query)
        logger.info("Query routed to namespaces: %s", active_namespaces)

        # Step 2 — intent classification
        comp_intent = ComponentMetric("intent_classification", time.perf_counter())
        t_ner_start = time.perf_counter()
        intent = await self._intent.classify(effective_query)
        comp_intent.finalize()
        if metrics:
            metrics.add_component(comp_intent)
        logger.info("Intent: %s | entities=%s | taxonomy=%s",
                    intent.query_type.value, intent.entities_mentioned, intent.taxonomy_paths)

        # Step 2.5 — Query Planner & Decomposition (Phase 3)
        plan: Optional[ExecutionPlan] = None
        if enable_decomposition and config.ENABLE_QUERY_DECOMPOSITION:
            comp_plan = ComponentMetric("query_decomposition", time.perf_counter())
            try:
                plan = await self._planner.plan(effective_query)
                comp_plan.metadata["is_complex"] = plan.is_complex
                comp_plan.metadata["sub_tasks"] = len(plan.sub_tasks)
                comp_plan.metadata["synthesis_strategy"] = plan.synthesis_strategy
                if plan.is_complex:
                    logger.info("Decomposed complex query into %d sub-tasks: %s",
                                len(plan.sub_tasks), plan.complexity_reason)
            except Exception as exc:
                logger.debug("Query planner notice: %s", exc)
                comp_plan.error = str(exc)
            comp_plan.finalize()
            if metrics:
                metrics.add_component(comp_plan)

        # Step 3 — entity resolution (Parallelized if enabled)
        comp_ner = ComponentMetric("entity_resolution", time.perf_counter())
        resolved_entities: list[BaseEntity] = []
        resolved_map: dict[str, str] = {}
        if config.ENABLE_PARALLELIZATION and intent.entities_mentioned:
            async def _resolve_surface(surface: str):
                try:
                    res = self._resolver.resolve_surface_form(surface)
                    return surface, (res.entity if (res and res.entity) else None)
                except Exception:
                    return surface, None

            tasks = [_resolve_surface(s) for s in intent.entities_mentioned]
            results = await asyncio.gather(*tasks)
            for surface, ent in results:
                if ent:
                    resolved_entities.append(ent)
                    resolved_map[surface] = ent.name
        else:
            for surface in intent.entities_mentioned:
                res = self._resolver.resolve_surface_form(surface)
                if res and res.entity:
                    resolved_entities.append(res.entity)
                    resolved_map[surface] = res.entity.name
        t_ner_ms = (time.perf_counter() - t_ner_start) * 1000
        comp_ner.finalize()
        if metrics:
            metrics.add_component(comp_ner)

        # Step 3.5 — Cypher Aggregation Path with Syntax Auto-Correction (Phase 4)
        cypher_facts: list[GraphFact] = []
        cypher_structured_rows: list[dict] = []
        cyphers_run: list[str] = []
        if getattr(intent, "requires_cypher", False) and config.ENABLE_CYPHER_AUTO_CORRECTION:
            comp_cypher = ComponentMetric("cypher_aggregation", time.perf_counter())
            try:
                product_names = {e.name for e in resolved_entities if hasattr(e, "name")} if resolved_entities else set()
                rows, usage = text_to_cypher.generate_and_run_with_correction(
                    effective_query,
                    product_names=product_names,
                    # Corpus-wide aggregations ("total AUM of all schemes") resolve
                    # no entities, so they must be allowed to run unscoped.
                    allow_global_scope=bool(getattr(intent, "aggregation_type", "")),
                )
                if rows:
                    cypher_structured_rows.extend(rows)
                    cypher_used = usage.get("cypher") or "CYPHER_AGGREGATION"
                    cyphers_run.append(cypher_used)
                    for r in rows:
                        cypher_facts.append(GraphFact(
                            statement=f"Aggregation fact: {r}",
                            subject=next(iter(product_names)) if product_names else "Corpus",
                            predicate="AGGREGATED_AS",
                            object=str(r),
                            properties=r if isinstance(r, dict) else {"val": r},
                            traversal_path="Cypher→Aggregation",
                        ))
                    comp_cypher.metadata["source"] = usage.get("source")
                    comp_cypher.input_tokens = usage.get("input_tokens", 0)
                    comp_cypher.output_tokens = usage.get("output_tokens", 0)
                    logger.info("Cypher aggregation succeeded: %d rows from %s", len(rows), usage.get("source"))
            except Exception as exc:
                logger.warning("Cypher aggregation notice: %s", exc)
                comp_cypher.error = str(exc)
            comp_cypher.finalize()
            if metrics:
                metrics.add_component(comp_cypher)

        # Step 4 — HyDE Expansion (Phase 2)
        hyde_doc = ""
        if enable_hyde and config.ENABLE_HYDE_IN_ORCHESTRATOR and config.ENABLE_HYDE_CACHE and intent.requires_vector:
            comp_hyde = ComponentMetric("hyde_expansion", time.perf_counter())
            try:
                hyde_doc, hyde_latency = hyde.generate_hypothetical_document(effective_query)
                comp_hyde.latency_ms = hyde_latency
                comp_hyde.cache_hit = (hyde_latency < 5.0)
                logger.info("HyDE document generated (%.1fms, cached=%s)", hyde_latency, hyde_latency < 5.0)
            except Exception as exc:
                logger.debug("HyDE expansion notice: %s", exc)
                comp_hyde.error = str(exc)
            comp_hyde.finalize()
            if metrics:
                metrics.add_component(comp_hyde)

        search_query = effective_query
        if hyde_doc:
            search_query = f"{effective_query}\n\nHYPOTHETICAL DOCUMENT:\n{hyde_doc}"

        # Steps 4 & 5 — Parallel Graph Traversal & Vector Search (Phase 3)
        facts, traversal_paths, cyphers = [], [], []
        chunks: list[RetrievedChunk] = []

        t_retrieval_start = time.perf_counter()
        t_graph_ms = 0.0
        t_vector_ms = 0.0

        if config.ENABLE_PARALLELIZATION and (intent.requires_graph and resolved_entities) and intent.requires_vector:
            comp_par = ComponentMetric("parallel_graph_and_vector", time.perf_counter())

            async def _do_graph():
                return await self._traversal.traverse(intent, resolved_entities)

            async def _do_vector():
                return await self._execute_plan_retrieval(
                    plan, search_query, hyde_doc,
                    top_k or self._top_k, intent, resolved_entities,
                )

            graph_res, vector_res = await asyncio.gather(_do_graph(), _do_vector(), return_exceptions=True)

            if not isinstance(graph_res, Exception):
                facts, traversal_paths, cyphers = graph_res
            else:
                logger.warning("Graph traversal failure in parallel gather: %s", graph_res)

            if not isinstance(vector_res, Exception):
                chunks = vector_res
            else:
                logger.warning("Vector search failure in parallel gather: %s", vector_res)

            comp_par.finalize()
            t_retrieval_total = (time.perf_counter() - t_retrieval_start) * 1000
            t_graph_ms = t_retrieval_total
            t_vector_ms = t_retrieval_total
            if metrics:
                metrics.add_component(comp_par)
        else:
            # Sequential execution path
            if intent.requires_graph and resolved_entities:
                t_graph_start = time.perf_counter()
                facts, traversal_paths, cyphers = await self._traversal.traverse(intent, resolved_entities)
                t_graph_ms = (time.perf_counter() - t_graph_start) * 1000
                if metrics:
                    metrics.add_component(ComponentMetric("graph_traversal", latency_ms=t_graph_ms))

            if intent.requires_vector:
                t_vector_start = time.perf_counter()
                chunks = await self._execute_plan_retrieval(
                    plan, search_query, hyde_doc,
                    top_k or self._top_k, intent, resolved_entities,
                )
                t_vector_ms = (time.perf_counter() - t_vector_start) * 1000
                if metrics:
                    metrics.add_component(ComponentMetric("vector_search", latency_ms=t_vector_ms))

        # Merge Cypher facts & queries
        if cypher_facts:
            facts.extend(cypher_facts)
        if cyphers_run:
            cyphers.extend(cyphers_run)

        # Step 6 — Multi-round Adaptive Retrieval (Phase 1)
        if config.ENABLE_QUERY_DECOMPOSITION:
            comp_adaptive = ComponentMetric("adaptive_retrieval", time.perf_counter())
            try:
                from app.retrieval.quality_assessor import assess_retrieval_quality
                from app.retrieval.adaptive_retriever import AdaptiveRetriever

                quality_check = assess_retrieval_quality(
                    chunks=chunks,
                    facts=facts,
                    query=effective_query,
                    resolved_entities=resolved_map,
                    min_chunks_threshold=2,
                    entity_coverage_threshold=0.5,
                )

                if not quality_check.is_sufficient and not quality_check.has_error:
                    logger.info(
                        "Round 1 retrieval insufficient (%s), triggering Round 2 relaxed retrieval",
                        quality_check.feedback,
                    )
                    adaptive = AdaptiveRetriever(vector_store=self._vector, graph_store=self._traversal)
                    round2_chunks = await adaptive.retrieve_round2(
                        query=effective_query,
                        hyde_doc=hyde_doc,
                        plan=plan,
                        top_k=top_k or self._top_k,
                        intent=intent,
                        resolved_entities=resolved_entities,
                        original_threshold=0.45,
                        relaxed_threshold=0.30,
                    )
                    if round2_chunks:
                        chunks.extend(round2_chunks)
                        logger.info("Round 2 adaptive retrieval added %d chunks", len(round2_chunks))
            except Exception as exc:
                logger.debug("Adaptive retrieval notice: %s", exc)
                comp_adaptive.error = str(exc)
            comp_adaptive.finalize()
            if metrics:
                metrics.add_component(comp_adaptive)

        retrieval = RetrievalResult(
            intent=intent,
            resolved_entities=resolved_map,
            graph_facts=facts,
            chunks=chunks,
            traversal_paths=traversal_paths,
            cypher_queries_run=cyphers,
        )

        # Step 7 — context assembly
        comp_asm = ComponentMetric("context_assembly", time.perf_counter())
        t_asm_start = time.perf_counter()
        context = self._assembler.assemble(retrieval)
        if not context.passed_quality_gate:
            logger.warning("Context quality gate failed (score=%.2f) for query: %s",
                           context.quality_score, effective_query)
        t_asm_ms = (time.perf_counter() - t_asm_start) * 1000
        comp_asm.finalize()
        if metrics:
            metrics.add_component(comp_asm)

        # Step 8 — synthesis
        comp_synth = ComponentMetric("synthesis", time.perf_counter())
        t_gen_start = time.perf_counter()
        synthesis = await self._synthesizer.synthesize(effective_query, context)
        t_gen_ms = (time.perf_counter() - t_gen_start) * 1000
        comp_synth.finalize()
        if metrics:
            metrics.add_component(comp_synth)

        if cypher_structured_rows:
            synthesis.structured_rows.extend(cypher_structured_rows)

        # Step 8b — Answer Critic & Verification (Phase 1)
        critic_escalated = False
        critic_reason = None
        comp_critic = ComponentMetric("answer_critic", time.perf_counter())
        try:
            from app.evaluation.answer_critic import CriticSeverity, get_answer_critic
            critic = get_answer_critic()
            severity, critique = await critic.critique(
                query=effective_query,
                answer=synthesis.answer,
                context=context.context_text,
                intent=intent,
            )
            comp_critic.metadata["severity"] = severity.value
            comp_critic.metadata["score"] = critique.get("score", 0.5)

            if severity == CriticSeverity.CRITICAL:
                logger.warning("Answer critic flagged critical issue: %s", critique.get("issues"))
                synthesis.confidence = "low"
                critic_escalated = True
                critic_reason = critique.get("issues", ["Contradiction with context"])[0]
            elif severity == CriticSeverity.WARNING:
                if synthesis.confidence == "high":
                    synthesis.confidence = "medium"
        except Exception as exc:
            logger.debug("Answer critic notice: %s", exc)
            comp_critic.error = str(exc)
        comp_critic.finalize()
        if metrics:
            metrics.add_component(comp_critic)

        # Step 9 — Review Queue Escalation (Phase 0)
        review_escalated = False
        escalation_reason_str = None
        if critic_escalated or synthesis.confidence == "low" or (context.quality_score < 0.40):
            try:
                from app.db.review_queue_repository import get_review_queue_repo
                from app.schemas.review_queue import ReviewQueueItem, ReviewReason
                repo = get_review_queue_repo()

                if critic_escalated:
                    reason = ReviewReason.HALLUCINATION_DETECTED
                    escalation_reason_str = critic_reason or "Flagged by Answer Critic"
                elif context.quality_score < 0.40:
                    reason = ReviewReason.INCOMPLETE_ANSWER
                    escalation_reason_str = f"Low context quality score ({context.quality_score:.2f})"
                else:
                    reason = ReviewReason.CONFIDENCE_LOW
                    escalation_reason_str = "Model low confidence"

                item = ReviewQueueItem(
                    response_id=req_id,
                    query=effective_query,
                    user_answer=synthesis.answer,
                    reason=reason,
                    confidence_score=context.quality_score,
                    metadata={
                        "intent": intent.query_type.value if intent else "unknown",
                        "entities": list(resolved_map.keys()),
                        "graph_edges": len(facts),
                    },
                )
                await repo.enqueue(item)
                review_escalated = True
                logger.info("Response %s auto-escalated to review queue (reason=%s)", req_id, reason.value)
            except Exception as exc:
                logger.warning("Failed auto-escalating to review queue: %s", exc)

        total_ms = (time.perf_counter() - t0) * 1000

        # Cache population on miss
        try:
            cache.store(
                effective_query,
                {
                    "answer": synthesis.answer,
                    "confidence": synthesis.confidence,
                    "compliance_note": synthesis.compliance_note,
                    "citations": [c.model_dump() if hasattr(c, "model_dump") else c for c in synthesis.citations],
                    "provenance": synthesis.provenance,
                    "quality_score": context.quality_score,
                    "output_tokens": len(synthesis.answer.split()) * 2 if synthesis.answer else 0,
                    "intent": intent.model_dump() if hasattr(intent, "model_dump") else {},
                    "traversal_paths": traversal_paths,
                    "graph_facts": [f.model_dump() if hasattr(f, "model_dump") else f for f in facts],
                    "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in context.sources],
                    "structured_rows": synthesis.structured_rows,
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
            review_queue_escalated=review_escalated,
            escalation_reason=escalation_reason_str,
        )


        if metrics:
            metrics.total_latency_ms = total_ms
            metrics.query_type = intent.query_type.value if intent else "unknown"
            metrics.entities_count = len(resolved_entities)
            metrics.graph_edges_found = len(facts)
            metrics.vector_chunks_retrieved = len(chunks)
            metrics.finalize()
            get_metrics_store().record(metrics)

        return OrchestratorResponse(
            intent=intent,
            retrieval=retrieval,
            context=context,
            synthesis=synthesis,
            trace=trace,
            metrics=metrics,
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
        enable_hyde: bool = True,
        track_metrics: bool = True,
    ) -> AsyncGenerator[dict, None]:
        """Stream the answer pipeline as SSE-shaped dicts."""
        t0 = time.perf_counter()
        req_id = str(uuid4())
        response_id = f"resp_{req_id[:12]}"
        metrics = QueryMetrics(request_id=req_id, query=query) if track_metrics else None

        def _record(query_type: str, cache_hit: bool = False, **fields):
            """Persist stream metrics so /api/metrics reflects streaming traffic too."""
            if not metrics:
                return
            metrics.total_latency_ms = (time.perf_counter() - t0) * 1000
            metrics.query_type = query_type
            metrics.cache_hit = cache_hit
            for key, value in fields.items():
                setattr(metrics, key, value)
            try:
                get_metrics_store().record(metrics)
            except Exception as exc:
                logger.debug("Stream metrics record notice: %s", exc)

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
                _record("compliance_refusal")
                yield {"type": "complete", "response_id": response_id, "trace": {}}
                return

        # ── Step 1: Semantic cache lookup ─────────────────────────────────
        cache = get_semantic_cache()
        cached_entry = None
        try:
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version)
        except Exception as exc:
            logger.debug("Cache lookup notice: %s", exc)

        if cached_entry and cached_entry.get("cache_hit"):
            logger.info("Streaming from semantic cache: %s", query)
            cached_intent = cached_entry.get("intent", {})
            yield {
                "type": "metadata",
                "intent": cached_intent.get("query_type", "general"),
                "entities": cached_intent.get("entities_mentioned", []),
                "confidence": cached_entry.get("confidence", "high"),
            }
            cached_sources = cached_entry.get("sources", [])
            if cached_sources:
                yield {"type": "sources", "sources": cached_sources}
            cached_answer = cached_entry.get("answer", "")
            words = cached_answer.split()
            for idx, word in enumerate(words):
                yield {"type": "answer_chunk", "text": (word + " "), "index": idx}
            _record(cached_intent.get("query_type", "general") if isinstance(cached_intent, dict) else "general",
                    cache_hit=True)
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

        # ── Step 3: Entity resolution (parallelized) ──────────────────────
        resolved_entities = []
        resolved_map: dict[str, str] = {}
        if intent:
            try:
                if config.ENABLE_PARALLELIZATION and intent.entities_mentioned:
                    async def _resolve_surface(surface: str):
                        try:
                            res = self._resolver.resolve_surface_form(surface)
                            return surface, (res.entity if (res and res.entity) else None)
                        except Exception:
                            return surface, None

                    for surface, ent in await asyncio.gather(
                        *[_resolve_surface(s) for s in intent.entities_mentioned]
                    ):
                        if ent:
                            resolved_entities.append(ent)
                            resolved_map[surface] = ent.name
                else:
                    for surface in intent.entities_mentioned:
                        res = self._resolver.resolve_surface_form(surface)
                        if res and res.entity:
                            resolved_entities.append(res.entity)
                            resolved_map[surface] = res.entity.name
            except Exception as exc:
                logger.warning("Entity resolution failed during streaming: %s", exc)
                yield {"type": "error", "message": f"Entity resolution error: {exc}", "recoverable": True}

        # ── Step 3.5: Cypher aggregation path ─────────────────────────────
        cypher_facts: list[GraphFact] = []
        cyphers_run: list[str] = []
        if intent and getattr(intent, "requires_cypher", False) and config.ENABLE_CYPHER_AUTO_CORRECTION:
            try:
                product_names = {e.name for e in resolved_entities if hasattr(e, "name")}
                rows, usage = text_to_cypher.generate_and_run_with_correction(
                    effective_query,
                    product_names=product_names,
                    allow_global_scope=bool(getattr(intent, "aggregation_type", "")),
                )
                if rows:
                    cyphers_run.append(usage.get("cypher") or "CYPHER_AGGREGATION")
                    for r in rows:
                        cypher_facts.append(GraphFact(
                            statement=f"Aggregation fact: {r}",
                            subject=next(iter(product_names)) if product_names else "Corpus",
                            predicate="AGGREGATED_AS",
                            object=str(r),
                            properties=r if isinstance(r, dict) else {"val": r},
                            traversal_path="Cypher→Aggregation",
                        ))
                    logger.info("Stream Cypher aggregation: %d rows from %s", len(rows), usage.get("source"))
            except Exception as exc:
                logger.warning("Stream Cypher aggregation notice: %s", exc)

        # ── Step 3.6: Query planner & decomposition ───────────────────────
        plan: Optional[ExecutionPlan] = None
        if intent and config.ENABLE_QUERY_DECOMPOSITION:
            try:
                plan = await self._planner.plan(effective_query)
                if plan.is_complex:
                    logger.info("Stream decomposed query into %d sub-tasks", len(plan.sub_tasks))
            except Exception as exc:
                logger.debug("Stream query planner notice: %s", exc)

        # ── Step 4.5: HyDE Expansion ─────────────────────────────────────
        hyde_doc = ""
        if enable_hyde and config.ENABLE_HYDE_IN_ORCHESTRATOR and config.ENABLE_HYDE_CACHE and intent and intent.requires_vector:
            try:
                hyde_doc, hyde_lat = hyde.generate_hypothetical_document(effective_query)
                logger.info("Stream HyDE: %.1fms (cached=%s)", hyde_lat, hyde_lat < 5.0)
            except Exception as exc:
                logger.debug("Stream HyDE generation notice: %s", exc)

        search_query = effective_query
        if hyde_doc:
            search_query = effective_query + "\n\nHYPOTHETICAL DOCUMENT:\n" + hyde_doc

        # ── Steps 4 & 5-6: Parallel graph traversal + vector search ───────
        facts, traversal_paths, cyphers = [], [], []
        chunks: list[RetrievedChunk] = []

        needs_graph = bool(intent and intent.requires_graph and resolved_entities)
        needs_vector = bool(intent and intent.requires_vector)

        async def _stream_graph():
            return await self._traversal.traverse(intent, resolved_entities)

        async def _stream_vector():
            return await self._execute_plan_retrieval(
                plan, search_query, hyde_doc,
                top_k or self._top_k, intent, resolved_entities,
            )

        if config.ENABLE_PARALLELIZATION and needs_graph and needs_vector:
            graph_res, vector_res = await asyncio.gather(
                _stream_graph(), _stream_vector(), return_exceptions=True
            )
            if isinstance(graph_res, Exception):
                logger.warning("Graph traversal failed during streaming: %s", graph_res)
                yield {"type": "error", "message": f"Graph traversal error: {graph_res}", "recoverable": True}
            else:
                facts, traversal_paths, cyphers = graph_res
            if isinstance(vector_res, Exception):
                logger.warning("Vector search failed during streaming: %s", vector_res)
                yield {"type": "error", "message": f"Vector search error: {vector_res}", "recoverable": True}
            else:
                chunks = vector_res
        else:
            if needs_graph:
                try:
                    facts, traversal_paths, cyphers = await _stream_graph()
                except Exception as exc:
                    logger.warning("Graph traversal failed during streaming: %s", exc)
                    yield {"type": "error", "message": f"Graph traversal error: {exc}", "recoverable": True}
            if needs_vector:
                try:
                    chunks = await _stream_vector()
                except Exception as exc:
                    logger.warning("Vector search failed during streaming: %s", exc)
                    yield {"type": "error", "message": f"Vector search error: {exc}", "recoverable": True}

        if cypher_facts:
            facts.extend(cypher_facts)
        if cyphers_run:
            cyphers.extend(cyphers_run)

        if chunks:
            yield {
                "type": "sources",
                "sources": [
                    {
                        "document_title": c.document_title or c.document_id,
                        "document_id": c.document_id,
                        "snippet": c.text[:200] if c.text else "",
                        "score": c.score,
                    }
                    for c in chunks
                ],
            }


        # ── Step 7: Context assembly ──────────────────────────────────────
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
                        "intent": intent.model_dump() if hasattr(intent, "model_dump") else {},
                        "traversal_paths": traversal_paths,
                        "graph_facts": [f.model_dump() if hasattr(f, "model_dump") else f for f in facts],
                        "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in context.sources],
                    },
                    corpus_version=self._corpus_version,
                )
            except Exception as exc:
                logger.debug("Stream cache store notice: %s", exc)

        _record(
            intent.query_type.value if intent else "unknown",
            entities_count=len(resolved_entities),
            graph_edges_found=len(facts),
            vector_chunks_retrieved=len(chunks),
        )

        yield {
            "type": "complete",
            "response_id": response_id,
            "trace": {
                "cache_hit": False,
                "request_total_ms": total_ms,
                "chunks_streamed": chunk_index,
            },
        }
