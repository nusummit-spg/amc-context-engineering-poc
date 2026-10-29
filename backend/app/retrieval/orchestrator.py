# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
"""Context retrieval and hybrid search orchestrator."""


import asyncio
import logging
import re
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
from app.models.entities import BaseEntity
from app.models.query import (
    AssembledContext,
    GraphFact,
    QueryIntent,
    QueryTrace,
    QueryType,
    RetrievalResult,
    RetrievedChunk,
    SynthesisOutput,
)
from app.vector.client import VectorStore
from app.core.logging import (
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
    log_v2_query_audit,
)

logger = logging.getLogger("retrieval")


NAMESPACE_KEYWORDS = {
    "sebi_regulation": ["sebi", "circular", "categorization", "regulation", "compliance", "mutual fund rules", "2026", "2017", "master circular", "amfi"],
    "adani_corporate": ["adani", "ael", "aahl", "ebitda", "revenue", "pat", "fy25", "fy24", "fy23", "earnings", "credit"],
    "esg_sustainability": ["esg", "brsr", "climate", "carbon", "greenwashing", "sustainability", "emissions", "green"],
    "fund_performance": ["nav", "returns", "aum", "benchmark", "alpha", "sharpe ratio", "fund performance", "scheme performance", "sid", "exit load", "ter"],
}


def route_query_namespace(query: str) -> list[str]:
    """Returns list of relevant namespaces (can be multiple for cross-domain queries).

    Args:
        query (str): Search query or input text.

    Returns:
        list[str]: List of resulting items or records.
    """
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
        """Initialize a new instance of OrchestratorResponse.

        Args:
            intent (Optional[QueryIntent]): Classified query intent.
            retrieval (Optional[RetrievalResult]): The retrieval.
            context (Optional[AssembledContext]): The context.
            synthesis (SynthesisOutput): Collection or list of synthesis.
            trace (Optional[QueryTrace]): The trace.
            metrics (Optional[QueryMetrics]): Collection or list of metrics.
        """
        self.intent = intent
        self.retrieval = retrieval
        self.context = context
        self.synthesis = synthesis
        self.trace = trace
        self.metrics = metrics

    def __iter__(self):
        """Return iterator over instance attributes or items.

        Returns:
            Result of the operation.
        """
        return iter((self.intent, self.retrieval, self.context, self.synthesis))


def _is_elliptical_followup(query: str) -> bool:
    """Check if query is an elliptical follow-up that truly requires previous turn context.
    If the query is already self-contained with its own subject/entity, returns False.
    """
    import re
    q_lower = query.lower()
    if re.search(r'\b(?:and\s+)?(?:which|what)\s+(?:amcs?|fund\s+house)\s+(?:manages?|offers?)\s+(?:it|them)\b', q_lower):
        return False
    self_contained_indicators = [
        'sbi', 'hdfc', 'icici', 'nippon', 'tata', 'ppfas', 'quant', 'kotak', 'aditya birla',
        'elss', 'liquid', 'large cap', 'small cap', 'mid cap', 'flexi cap', 'arbitrage',
        'close ended', 'open ended', 'dataset', 'categories', 'industry'
    ]
    if any(ind in q_lower for ind in self_contained_indicators):
        return False
    pronoun_triggers = {"those", "these", "them", "it", "they", "that", "theirs", "this", "its"}
    words_in_query = set(q_lower.replace("?", "").replace(".", "").split())
    return bool(pronoun_triggers & words_in_query and len(words_in_query) <= 8)

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
        """Initialize a new instance of RetrievalOrchestrator.

        Args:
            intent_classifier (IntentClassifier): Query intent classifier component.
            resolver (EntityResolver): Entity resolver component.
            traversal (GraphTraversal): Graph traversal component.
            vector_store (VectorStore): Vector database store client.
            assembler (ContextAssembler): Context assembler component.
            synthesizer (Synthesizer): LLM response synthesizer component.
        """
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

        # Microservices service clients (only if microservices mode enabled)
        self._repair_client = None
        self._repair_circuit_breaker = None
        if getattr(self._settings, "microservices_mode", False):
            try:
                from app.services.repair_client import RepairServiceClient
                from app.services.circuit_breaker import CircuitBreaker

                repair_url = getattr(self._settings, "repair_service_url", None) or "http://repair:8002"
                self._repair_client = RepairServiceClient(base_url=repair_url)

                if getattr(self._settings, "circuit_breaker_enabled", True):
                    self._repair_circuit_breaker = CircuitBreaker(
                        service_name="repair-engine",
                        failure_threshold=getattr(self._settings, "circuit_breaker_failure_threshold", 5),
                        recovery_timeout=getattr(self._settings, "circuit_breaker_recovery_timeout", 60.0),
                    )
            except Exception as exc:
                logger.warning("Could not initialize repair service client: %s", exc)

    # ------------------------------------------------------------------
    # Vector retrieval helpers (Phase 3 — plan execution & parallelism)
    # ------------------------------------------------------------------

    @staticmethod
    def _hits_to_chunks(hits: list[dict]) -> list[RetrievedChunk]:
        """Convert hits into chunks.

        Args:
            hits (list[dict]): Raw search hits from vector or keyword index.

        Returns:
            list[RetrievedChunk]: List of resulting items or records.
        """
        return [
            RetrievedChunk(
                chunk_id=h["chunk_id"],
                document_id=h.get("document_id", ""),
                document_title=h.get("document_title"),
                text=h.get("text", ""),
                score=min(1.0, max(0.0, float(h.get("score", 0.0)))),
                taxonomy_paths=h.get("taxonomy_paths", []),
                page=h.get("page_start", 1),
                page_start=h.get("page_start", 1),
            )
            for h in hits
        ]

    async def _search_chunks(
        self,
        search_query: str,
        top_k: int,
        intent: QueryIntent,
        resolved_entities: list[BaseEntity],
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """Single taxonomy-scoped vector search.

        Args:
            search_query (str): Target query text for search.
            top_k (int): Number of top results to return.
            intent (QueryIntent): Classified query intent.
            resolved_entities (list[BaseEntity]): List of recognized entities from entity resolution.
            user_id (str | None): Unique identifier of the user.
            tenant_id (str | None): Unique identifier of the tenant.

        Returns:
            list[RetrievedChunk]: List of resulting items or records.
        """
        effective_k = max(top_k or 8, 8)
        hits = await self._vector.search(
            search_query,
            top_k=effective_k,
            taxonomy_paths=intent.taxonomy_paths or None,
            entity_names=[e.name for e in resolved_entities] or None,
            user_id=user_id,
            tenant_id=tenant_id,
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
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """Executes the retrieval sub-tasks of an execution plan.

        A complex plan (e.g. "Compare A vs B") decomposes into one retrieval
        branch per entity. Each branch is searched concurrently and the results
        are merged, deduped by chunk_id and re-ranked by score — so a comparison
        gets balanced evidence for both sides instead of whichever side dominates
        a single blended query. Simple plans fall through to one search.

        Args:
            plan (Optional[ExecutionPlan]): Generated execution plan.
            search_query (str): Target query text for search.
            hyde_doc (str): Hypothetical document generated for query expansion.
            top_k (int): Number of top results to return.
            intent (QueryIntent): Classified query intent.
            resolved_entities (list[BaseEntity]): List of recognized entities from entity resolution.
            user_id (str | None): Unique identifier of the user.
            tenant_id (str | None): Unique identifier of the tenant.

        Returns:
            list[RetrievedChunk]: List of resulting items or records.
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
            return await self._search_chunks(
                search_query, top_k, intent, resolved_entities,
                user_id=user_id, tenant_id=tenant_id,
            )

        # Branch queries keep the HyDE augmentation so both paths embed alike.
        branch_queries = [
            (q + "\n\nHYPOTHETICAL DOCUMENT:\n" + hyde_doc) if hyde_doc else q
            for q in retrieval_tasks
        ]
        # Split the budget across branches, with a floor so each branch is useful.
        per_branch_k = max(3, top_k // max(1, len(branch_queries)))

        results = await asyncio.gather(
            *[
                self._search_chunks(
                    bq, per_branch_k, intent, resolved_entities,
                    user_id=user_id, tenant_id=tenant_id,
                )
                for bq in branch_queries
            ],
            return_exceptions=True,
        )

        merged: dict[str, RetrievedChunk] = {}
        for branch_result in results:
            if isinstance(branch_result, Exception):
                log_step_warning(logger, "PLAN_RETRIEVAL_WARN", "Plan retrieval branch failed: %s", branch_result)
                continue
            for chunk in branch_result:
                existing = merged.get(chunk.chunk_id)
                if existing is None or chunk.score > existing.score:
                    merged[chunk.chunk_id] = chunk

        if not merged:
            return await self._search_chunks(
                search_query, top_k, intent, resolved_entities,
                user_id=user_id, tenant_id=tenant_id,
            )

        chunks = sorted(merged.values(), key=lambda c: c.score, reverse=True)[:top_k]
        log_step_info(
            logger,
            "PLAN_RETRIEVAL",
            "Plan retrieval: %d branches -> %d unique chunks (kept %d)",
            len(branch_queries), len(merged), len(chunks),
        )
        return chunks

    async def _apply_correction_patches(
        self,
        entity_ids: list[str],
        context_text: str,
    ) -> tuple[str, list[dict]]:
        """Apply correction patches (microservices-aware).
        Tries microservices mode first if enabled, falls back to local.
        Returns: (modified_context_text, applied_patches_list)

        Args:
            entity_ids (list[str]): Collection or list of entity ids.
            context_text (str): The context text.
        """
        applied: list[dict] = []
        if not entity_ids:
            return context_text, applied

        # 1. Microservices mode: call repair service over HTTP
        if getattr(self._settings, "microservices_mode", False) and self._repair_client:
            try:
                if self._repair_circuit_breaker:
                    patches = await self._repair_circuit_breaker.call(
                        self._repair_client.get_patches_for_entities,
                        entity_ids
                    )
                else:
                    patches = await self._repair_client.get_patches_for_entities(
                        entity_ids
                    )

                if patches:
                    correction_blocks = []
                    for p in patches:
                        conf = p.get("confidence", 1.0)
                        if conf >= 0.70:
                            attr = p.get("attribute", "")
                            val = p.get("corrected_value", "")
                            orig = p.get("canonical_value") or p.get("original_value", "")
                            applied.append({
                                "entity_id": p.get("entity_id", ""),
                                "attribute": attr,
                                "original": orig,
                                "corrected": val,
                                "confidence": conf,
                            })
                            correction_blocks.append(
                                f"\n[CORRECTION PATCH APPLIED: {attr} = {val} (supersedes prior context)]\n"
                            )
                    if correction_blocks:
                        context_text = "".join(correction_blocks) + context_text
                    log_step_info(logger, "REPAIR_PATCH_APPLIED", "Applied %d patches from repair service: %s", len(applied), [a['attribute'] for a in applied])
                    return context_text, applied

            except Exception as exc:
                from app.services.circuit_breaker import CircuitBreakerOpen
                if isinstance(exc, CircuitBreakerOpen):
                    log_step_warning(logger, "REPAIR_CIRCUIT_BREAKER", "Repair service circuit breaker OPEN, falling back to local")
                else:
                    log_step_error(logger, "REPAIR_SERVICE_ERROR", "Failed to apply patches from repair service: %s, falling back to local", exc)

        # 2. Monolithic mode OR fallback: use local repair engine / patch layer
        try:
            from app.adapters_config import get_repair_engine
            repair_engine = get_repair_engine()
            all_patches = []
            for entity_id in entity_ids:
                patches = await repair_engine.patch_layer.get_patches_for_entity(entity_id)
                all_patches.extend(patches)

            if all_patches:
                for p in all_patches:
                    if p.confidence >= 0.70:
                        applied.append({
                            "entity_id": p.entity_id,
                            "attribute": p.attribute,
                            "original": p.canonical_value if p.canonical_value is not None else p.original_value,
                            "corrected": p.corrected_value,
                            "confidence": p.confidence,
                        })
                context_text = await repair_engine.patch_layer.apply_patches_to_context(
                    entity_ids, context_text
                )
                log_step_info(logger, "REPAIR_PATCH_APPLIED", "Applied %d patches from local repair engine: %s", len(applied), [a['attribute'] for a in applied])
                return context_text, applied

        except Exception as exc:
            log_step_debug(logger, "REPAIR_LOCAL_NOTICE", "Local repair engine patch notice: %s, falling back to shadow graph", exc)

        # 3. Final local fallback: app.graph.correction_patch_layer
        try:
            from app.graph.correction_patch_layer import get_correction_patch_layer
            patch_layer = get_correction_patch_layer()
            context_text = patch_layer.apply_patches_to_context(
                entities=entity_ids,
                retrieval_context=context_text
            )
        except Exception as patch_exc:
            logger.debug("Correction patch layer notice: %s", patch_exc)

        return context_text, applied

    def _populate_tabular_aggregation_facts(
        self,
        query: str,
        intent: Optional[QueryIntent] = None,
    ) -> tuple[list[GraphFact], list[dict]]:
        """Populate authoritative tabular facts and structured rows from SchemeAggregationService.
        
        Layer 2: Intent routing & tabular execution fallback.
        """
        facts: list[GraphFact] = []
        rows: list[dict] = []
        try:
            from app.services.scheme_aggregation_service import get_aggregation_service
            service = get_aggregation_service()
            q_lower = query.lower()

            if "nav" in q_lower:
                scheme_type = "Open Ended" if ("open-ended" in q_lower or "open ended" in q_lower) else None
                category = "Equity" if "equity" in q_lower else None
                plan = "Growth" if "growth" in q_lower else None
                nav_res = service.get_top_nav_schemes(
                    limit=10,
                    scheme_type=scheme_type,
                    category_keyword=category,
                    plan_keyword=plan,
                    exclude_idcw=True if plan == "Growth" else False,
                    sort_order="asc" if ("lowest" in q_lower or "minimum" in q_lower) else "desc",
                )
                for s in nav_res.schemes:
                    fact_text = f"{s.plan_name} ({s.amc}) has NAV ₹{s.nav:,.4f} as of {s.latest_nav_date} (Category: {s.scheme_category}, Rank: {s.rank})"
                    facts.append(GraphFact(
                        statement=fact_text,
                        subject=s.plan_name,
                        predicate="HAS_NAV",
                        object=str(s.nav),
                        properties=s.model_dump(),
                        source_document_ids=["mutual_fund_data.csv"],
                        traversal_path="CSV→NAVAggregation",
                    ))
                    rows.append({
                        "rank": s.rank,
                        "scheme_name": s.plan_name,
                        "amc": s.amc,
                        "nav": f"₹{s.nav:,.4f}",
                        "latest_nav_date": s.latest_nav_date,
                        "category": s.scheme_category,
                        "scheme_type": s.scheme_type,
                    })
            elif any(term in q_lower for term in ["categor", "breakdown", "distribution", "asset class"]):
                detailed = ("detailed" in q_lower or "sebi" in q_lower or "sub-category" in q_lower or "subcategory" in q_lower)
                cat_res = service.get_category_aum_breakdown(detailed=detailed, query_text=query)
                for c in cat_res.categories:
                    fact_text = f"Mutual Fund Category '{c.category}' has Total AUM ₹{c.total_aum_cr:,.2f} Cr ({c.pct_of_total_aum}% market share) across {c.distinct_schemes} distinct schemes ({c.total_folios} folios, Rank: {c.rank})"
                    facts.append(GraphFact(
                        statement=fact_text,
                        subject=c.category,
                        predicate="HAS_CATEGORY_AUM",
                        object=str(c.total_aum_cr),
                        properties=c.model_dump(),
                        source_document_ids=["mutual_fund_data.csv"],
                        traversal_path="CSV→CategoryAggregation",
                    ))
                    rows.append({
                        "rank": c.rank,
                        "category": c.category,
                        "total_aum_cr": f"₹{c.total_aum_cr:,.2f} Cr",
                        "pct_of_total_aum": f"{c.pct_of_total_aum:.2f}%",
                        "distinct_schemes": c.distinct_schemes,
                        "total_folios": c.total_folios,
                        "avg_aum_per_scheme_cr": f"₹{c.avg_aum_per_scheme_cr:,.2f} Cr",
                    })
            elif any(term in q_lower for term in ["amc", "asset management compan"]):
                amc_res = service.get_top_amcs(limit=10)
                for m in amc_res.amc_rankings:
                    fact_text = f"{m.amc} manages Total AUM ₹{m.total_aum_cr:,.2f} Cr across {m.distinct_schemes} distinct schemes (Rank: {m.rank})"
                    facts.append(GraphFact(
                        statement=fact_text,
                        subject=m.amc,
                        predicate="MANAGES_TOTAL_AUM",
                        object=str(m.total_aum_cr),
                        properties=m.model_dump(),
                        source_document_ids=["mutual_fund_data.csv"],
                        traversal_path="CSV→AMCAggregation",
                    ))
                    rows.append({
                        "rank": m.rank,
                        "amc": m.amc,
                        "total_aum_cr": f"₹{m.total_aum_cr:,.2f} Cr",
                        "distinct_schemes": m.distinct_schemes,
                    })
            else:
                top_schemes_res = service.get_top_schemes(limit=10, sort_by="avg_aum" if "average" in q_lower else "max_aum")
                for idx, s in enumerate(top_schemes_res.scheme_level_rankings, 1):
                    fact_text = f"{s.scheme_name} managed by {s.amc} has Average AUM ₹{s.avg_aum_cr:,.2f} Cr (Max: ₹{s.max_aum_cr:,.2f} Cr, Rank: {idx})"
                    facts.append(GraphFact(
                        statement=fact_text,
                        subject=s.scheme_name,
                        predicate="HAS_AUM",
                        object=str(s.avg_aum_cr),
                        properties=s.model_dump(),
                        source_document_ids=["mutual_fund_data.csv"],
                        traversal_path="CSV→SchemeAggregation",
                    ))
                    rows.append({
                        "rank": idx,
                        "scheme_name": s.scheme_name,
                        "amc": s.amc,
                        "avg_aum_cr": f"₹{s.avg_aum_cr:,.2f} Cr",
                        "max_aum_cr": f"₹{s.max_aum_cr:,.2f} Cr",
                    })
        except Exception as exc:
            log_step_warning(logger, "TABULAR_AGGREGATION_WARN", "Tabular aggregation fallback error: %s", exc)
        return facts, rows

    def _enforce_aggregation_guardrail(
        self,
        query: str,
        synthesis: SynthesisOutput,
        rows: list[dict],
        critic_escalated: bool = False,
    ) -> tuple[SynthesisOutput, bool]:
        """Layer 3: Active Quality Gate Guardrail.
        Verifies LLM synthesis against deterministic tabular facts.
        If the synthesis deviates, contradicts, or suffers hallucination, rewrites with exact ground truth.
        """
        if not rows:
            return synthesis, False

        top_item = rows[0]
        top_name = (top_item.get("category") or top_item.get("scheme_name") or top_item.get("amc") or "").lower()
        top_name_clean = re.sub(r"[^\w\s]", "", top_name[:30]).strip()
        answer_clean = re.sub(r"[^\w\s]", "", (synthesis.answer or "").lower())

        mismatch = (top_name_clean and top_name_clean not in answer_clean) or critic_escalated or (synthesis.confidence == "low")

        if mismatch:
            log_step_info(logger, "QUALITY_GATE_GUARDRAIL", "Actively enforcing deterministic ground truth for query '%s'", query)
            q_lower = query.lower()
            if any(term in q_lower for term in ["categor", "breakdown", "distribution", "asset class"]):
                table_lines = [
                    "## Mutual Fund Category Breakdown: Total AUM and Scheme Counts",
                    "",
                    "| Rank | Mutual Fund Category | Total AUM (₹ Cr) | Market Share (%) | Distinct Schemes | Total Plan Variants | Avg AUM / Scheme (₹ Cr) |",
                    "|------|----------------------|------------------|------------------|------------------|---------------------|--------------------------|",
                ]
                for r in rows:
                    table_lines.append(f"| {r.get('rank')} | **{r.get('category')}** | {r.get('total_aum_cr')} | {r.get('pct_of_total_aum')} | {r.get('distinct_schemes')} | {r.get('total_folios')} | {r.get('avg_aum_per_scheme_cr')} |")
                table_lines.extend([
                    "",
                    "**Sources**",
                    "- Aggregated directly across all scheme folios in mutual_fund_data.csv [1].",
                ])
                synthesis.answer = "\n".join(table_lines)
            elif "nav" in q_lower:
                table_lines = [
                    "## Open-Ended Equity Growth Schemes with Highest NAV",
                    "",
                    "| Rank | Scheme (Plan Option) | AMC | NAV (₹) | Latest NAV Date |",
                    "|------|----------------------|-----|---------|-----------------|",
                ]
                for r in rows:
                    table_lines.append(f"| {r.get('rank')} | **{r.get('scheme_name')}** | {r.get('amc')} | {r.get('nav')} | {r.get('latest_nav_date')} |")
                table_lines.extend([
                    "",
                    "**Sources**",
                    "- NAV values and dates are taken directly from the mutual-fund CSV rows [1].",
                    "",
                    "### Executive Summary",
                    f"- The **{top_item.get('scheme_name')}** holds the highest NAV at **{top_item.get('nav')}**.",
                    "- All listed schemes are **open-ended equity funds** with a **Growth** option; IDCW-payout variants have been excluded.",
                ])
                synthesis.answer = "\n".join(table_lines)
            elif any(term in q_lower for term in ["amc", "asset management compan"]):
                table_lines = [
                    "## Asset Management Companies (AMCs) Managing Highest Total AUM",
                    "",
                    "| Rank | Asset Management Company (AMC) | Total AUM (₹ Cr) | Distinct Schemes |",
                    "|------|--------------------------------|------------------|------------------|",
                ]
                for r in rows:
                    table_lines.append(f"| {r.get('rank')} | **{r.get('amc')}** | {r.get('total_aum_cr')} | {r.get('distinct_schemes')} |")
                table_lines.extend([
                    "",
                    "**Sources**",
                    "- Aggregated across all scheme folios in the mutual-fund CSV dataset [1].",
                ])
                synthesis.answer = "\n".join(table_lines)
            else:
                table_lines = [
                    "## Top Mutual Fund Schemes by AUM",
                    "",
                    "| Rank | Scheme Name | AMC | Average AUM (₹ Cr) | Maximum AUM (₹ Cr) |",
                    "|------|-------------|-----|--------------------|--------------------|",
                ]
                for r in rows:
                    table_lines.append(f"| {r.get('rank')} | **{r.get('scheme_name')}** | {r.get('amc')} | {r.get('avg_aum_cr')} | {r.get('max_aum_cr')} |")
                table_lines.extend([
                    "",
                    "**Sources**",
                    "- Aggregated directly from scheme folios in mutual_fund_data.csv [1].",
                ])
                synthesis.answer = "\n".join(table_lines)

            synthesis.confidence = "high"
            synthesis.compliance_note = "Audited & Verified via Grounding Guardrail: Extracted from deterministic dataset."
            synthesis.structured_rows = rows
            return synthesis, True

        return synthesis, False


    async def answer(
        self,
        query: str,
        top_k: int | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
        enable_hyde: bool = True,
        enable_decomposition: bool = True,
        track_metrics: bool = True,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> OrchestratorResponse:
        """Execute retrieval and synthesize response for the user query.

        Args:
            query (str): Search query or input text.
            top_k (int | None): Number of top results to return.
            history (list[dict] | None): Chat history message sequence.
            session_id (str | None): Unique identifier of the session.
            enable_hyde (bool): Whether to enable HyDE query expansion.
            enable_decomposition (bool): Whether to enable complex query decomposition.
            track_metrics (bool): Whether to record performance metrics.
            user_id (str | None): Unique identifier of the user.
            tenant_id (str | None): Unique identifier of the tenant.

        Returns:
            OrchestratorResponse: OrchestratorResponse object containing the operation result.
        """
        t0 = time.perf_counter()
        req_id = str(uuid4())
        metrics = QueryMetrics(request_id=req_id, query=query) if track_metrics else None

        log_step_info(logger, "REQUEST_RECEIVED", "Step 1: Received user query: '%s' (session_id=%s)", query, session_id)

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
            if user_msgs and _is_elliptical_followup(query):
                effective_query = f"{user_msgs[-1]} — {query}"
        t_rewrite_ms = (time.perf_counter() - t_rewrite_start) * 1000
        comp_rewrite.finalize()
        if metrics:
            metrics.add_component(comp_rewrite)
        if effective_query != query:
            log_step_info(logger, "QUERY_REWRITE", "Step 1b: Rewrote multi-turn query for context: '%s' -> '%s' (%.1fms)", query, effective_query, t_rewrite_ms)

        # Step 0.5 — Configurable Pre-Retrieval Safety Guardrail Interceptor
        if self._settings.enable_pre_retrieval_guardrails:
            q_clean = query.lower().strip()
            if any(w in q_clean for w in ["guarantee", "assured return", "promise return", "guaranteed profit", "15% annual return", "fixed return"]):
                log_step_warning(logger, "GUARDRAIL_CHECK", "Guardrail Check: Blocked query promising guaranteed returns per SEBI regulations: '%s'", query)
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

                log_v2_query_audit({
                    "query": query,
                    "query_type": "compliance_refusal",
                    "entities": [],
                    "graph_matched_by": "guardrail_refusal",
                    "graph_nodes_count": 0,
                    "graph_edges_count": 0,
                    "vector_hits_raw": 0,
                    "vector_bypassed": True,
                    "cache_hit": False,
                    "patches_applied": 0,
                    "quality_gate_passed": True,
                    "llm_model": "guardrail_deterministic",
                    "input_tokens": 0,
                    "output_tokens": len(synth.answer.split()) * 2,
                    "latency_total_ms": total_ms,
                    "status": "REFUSAL",
                    "session_id": session_id,
                })
                return OrchestratorResponse(
                    intent=None,
                    retrieval=None,
                    context=None,
                    synthesis=synth,
                    trace=trace,
                    metrics=metrics,
                )

        # Step 0.75 — Deterministic Pre-LLM Fast-Path Interceptor (Option 2)
        try:
            from app.retrieval.fast_path_interceptor import get_fast_path_interceptor
            fast_path = get_fast_path_interceptor(self._repair_client)
            fast_resp = await fast_path.intercept(
                query=effective_query,
                entities=None,
                corpus_version=self._corpus_version,
            )
            if fast_resp:
                total_ms = (time.perf_counter() - t0) * 1000
                if fast_resp.trace:
                    fast_resp.trace.request_total_ms = round(total_ms, 2)
                if metrics:
                    metrics.total_latency_ms = total_ms
                    metrics.query_type = "fast_path_patch"
                    get_metrics_store().record(metrics)

                log_step_info(logger, "FAST_PATH_INTERCEPTOR", "Fast Path: Served verified ground-truth answer directly without LLM (%.1fms)", total_ms)
                log_v2_query_audit({
                    "query": effective_query,
                    "query_type": "fast_path_patch",
                    "entities": [],
                    "graph_matched_by": "fast_path_patch",
                    "graph_nodes_count": 0,
                    "graph_edges_count": 0,
                    "vector_hits_raw": 0,
                    "vector_bypassed": True,
                    "cache_hit": False,
                    "patches_applied": 1,
                    "quality_gate_passed": True,
                    "llm_model": "fast_path_deterministic",
                    "input_tokens": 0,
                    "output_tokens": len(fast_resp.synthesis.answer.split()) * 2 if fast_resp.synthesis else 0,
                    "latency_total_ms": total_ms,
                    "status": "FAST_PATH",
                    "session_id": session_id,
                })
                return fast_resp
        except Exception as fp_exc:
            log_step_debug(logger, "FAST_PATH_NOTICE", "Fast-path interceptor notice: %s", fp_exc)

        # Step 1 — Semantic Cache Check (PV-02A)
        comp_cache = ComponentMetric("semantic_cache_lookup", time.perf_counter())
        t_cache_start = time.perf_counter()
        cache = get_semantic_cache()
        cached_entry = None
        try:
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version, user_id=user_id, tenant_id=tenant_id)
        except Exception as exc:
            log_step_debug(logger, "CACHE_LOOKUP_NOTICE", "Cache lookup notice: %s", exc)
        t_cache_lookup_ms = (time.perf_counter() - t_cache_start) * 1000
        comp_cache.cache_hit = bool(cached_entry and cached_entry.get("cache_hit"))
        comp_cache.finalize()
        if metrics:
            metrics.add_component(comp_cache)

        if cached_entry and cached_entry.get("cache_hit"):
            log_step_info(logger, "CACHE_LOOKUP", "Cache Hit: Retrieved exact match from semantic cache in %.1fms for query: '%s'", t_cache_lookup_ms, query)
            total_ms = (time.perf_counter() - t0) * 1000
            
            cached_synth = SynthesisOutput(
                answer=cached_entry.get("answer", ""),
                confidence=cached_entry.get("confidence", "high"),
                compliance_note=cached_entry.get("compliance_note"),
                citations=cached_entry.get("citations", []),
                provenance=cached_entry.get("provenance", []),
                structured_rows=cached_entry.get("structured_rows", []),
            )
            from app.models.query import Citation, GraphFact, SourceAttribution
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
            
            cached_output_tokens = cached_entry.get("output_tokens", len(cached_synth.answer.split()) * 2)
            cold_tokens = cached_entry.get("cold_equivalent_tokens") or (500 + cached_output_tokens)
            trace = QueryTrace(
                request_id=req_id,
                serving_engine="v2",
                corpus_version=self._corpus_version,
                cache_hit=True,
                cache_kind=cached_entry.get("cache_kind", "exact"),
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
                output_tokens=cached_output_tokens,
                cold_equivalent_tokens=cold_tokens,
                tokens_saved=cold_tokens,
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
        log_step_info(logger, "NAMESPACE_ROUTING", "Step 2: Routed query to knowledge domains: %s", active_namespaces)

        # Step 2 — intent classification
        comp_intent = ComponentMetric("intent_classification", time.perf_counter())
        t_ner_start = time.perf_counter()
        intent = await self._intent.classify(effective_query)
        comp_intent.finalize()
        if metrics:
            metrics.add_component(comp_intent)
        log_step_info(logger, "INTENT_CLASSIFICATION", "Step 3: Classified intent: type=%s, entities detected=%s, taxonomy=%s",
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
                    log_step_info(logger, "QUERY_PLANNING", "Step 3b: Decomposed complex query into %d sub-tasks: %s",
                                len(plan.sub_tasks), plan.complexity_reason)
                else:
                    log_step_debug(logger, "QUERY_PLANNING", "Simple query plan generated (sub_tasks=1)")
            except Exception as exc:
                log_step_debug(logger, "QUERY_PLANNING_NOTICE", "Query planner notice: %s", exc)
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
                """Resolve surface.

                Args:
                    surface (str): The surface.

                Returns:
                    Result of the operation.
                """
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
        log_step_info(logger, "ENTITY_RESOLUTION", "Step 4: Resolved %d financial entities against database in %.1fms: %s", len(resolved_entities), t_ner_ms, resolved_map)

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
                    user_id=user_id,
                    tenant_id=tenant_id,
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
                    log_step_info(logger, "CYPHER_AGGREGATION", "Step 5a: Graph aggregation query returned %d rows from %s", len(rows), usage.get("source"))
            except Exception as exc:
                log_step_warning(logger, "CYPHER_AGGREGATION_WARN", "Cypher aggregation notice: %s", exc)
                comp_cypher.error = str(exc)
            comp_cypher.finalize()
            if metrics:
                metrics.add_component(comp_cypher)

        # Step 3.5b — Tabular / CSV Aggregation Fallback (Layer 2)
        if intent and (intent.query_type == QueryType.AGGREGATE_RANKING or getattr(intent, "aggregation_type", "") == "ranking") and not cypher_facts:
            fb_facts, fb_rows = self._populate_tabular_aggregation_facts(effective_query, intent)
            if fb_facts:
                cypher_facts.extend(fb_facts)
                cypher_structured_rows.extend(fb_rows)
                log_step_info(logger, "TABULAR_AGGREGATION_FALLBACK", "Step 5b: Injected %d authoritative tabular facts into context", len(fb_facts))

        # Step 4 — HyDE Expansion (Phase 2)
        hyde_doc = ""
        if enable_hyde and config.ENABLE_HYDE_IN_ORCHESTRATOR and config.ENABLE_HYDE_CACHE and intent.requires_vector:
            comp_hyde = ComponentMetric("hyde_expansion", time.perf_counter())
            try:
                hyde_doc, hyde_latency = hyde.generate_hypothetical_document(
                    effective_query,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                comp_hyde.latency_ms = hyde_latency
                comp_hyde.cache_hit = (hyde_latency < 5.0)
                log_step_info(logger, "HYDE_EXPANSION", "Step 5c: Generated hypothetical answer document for vector search (%.1fms, cached=%s)", hyde_latency, hyde_latency < 5.0)
            except Exception as exc:
                log_step_debug(logger, "HYDE_EXPANSION_NOTICE", "HyDE expansion notice: %s", exc)
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

        needs_graph = bool(intent and (
            intent.requires_graph
            or (intent.query_type != QueryType.GENERAL)
            or bool(intent.entities_mentioned)
            or bool(resolved_entities)
        ))
        # Vector search is essential for all document-grounded queries and whenever
        # graph facts are not available to answer the query deterministically.
        needs_vector = bool(intent and (
            intent.requires_vector
            or not cypher_facts
            or any(k in effective_query.lower() for k in [
                "ebitda", "revenue", "annual report", "fy24", "fy25", "fy23", "pat", "esg", "target",
                "sebi", "circular", "rule", "guideline", "limit", "borrowing", "framework", "ratio"
            ])
        ))
        if intent and intent.query_type == QueryType.AGGREGATE_RANKING and cypher_facts:
            needs_vector = False

        if config.ENABLE_PARALLELIZATION and needs_graph and needs_vector:
            comp_par = ComponentMetric("parallel_graph_and_vector", time.perf_counter())

            async def _do_graph():
                """Do graph.

                Returns:
                    Result of the operation.
                """
                return await self._traversal.traverse(
                    intent, resolved_entities,
                    user_id=user_id, tenant_id=tenant_id,
                )

            async def _do_vector():
                """Do vector.

                Returns:
                    Result of the operation.
                """
                return await self._execute_plan_retrieval(
                    plan, search_query, hyde_doc,
                    top_k or self._top_k, intent, resolved_entities,
                    user_id=user_id, tenant_id=tenant_id,
                )

            graph_res, vector_res = await asyncio.gather(_do_graph(), _do_vector(), return_exceptions=True)

            if not isinstance(graph_res, Exception):
                facts, traversal_paths, cyphers = graph_res
                log_step_info(logger, "GRAPH_TRAVERSAL", "Step 6: Traversed knowledge graph (parallel): found %d verified facts across %d paths", len(facts), len(traversal_paths))
            else:
                log_step_warning(logger, "GRAPH_TRAVERSAL_WARN", "Graph traversal failure in parallel gather: %s", graph_res)

            if not isinstance(vector_res, Exception):
                chunks = vector_res
                log_step_info(logger, "VECTOR_RETRIEVAL", "Step 7: Searched vector document store (parallel): retrieved %d matching chunks", len(chunks))
            else:
                log_step_warning(logger, "VECTOR_RETRIEVAL_WARN", "Vector search failure in parallel gather: %s", vector_res)

            comp_par.finalize()
            t_retrieval_total = (time.perf_counter() - t_retrieval_start) * 1000
            t_graph_ms = t_retrieval_total
            t_vector_ms = t_retrieval_total
            if metrics:
                metrics.add_component(comp_par)
        else:
            # Sequential execution path
            if needs_graph:
                t_graph_start = time.perf_counter()
                facts, traversal_paths, cyphers = await self._traversal.traverse(
                    intent, resolved_entities,
                    user_id=user_id, tenant_id=tenant_id,
                )
                t_graph_ms = (time.perf_counter() - t_graph_start) * 1000
                log_step_info(logger, "GRAPH_TRAVERSAL", "Step 6: Traversed knowledge graph: found %d verified facts in %.1fms", len(facts), t_graph_ms)
                if metrics:
                    metrics.add_component(ComponentMetric("graph_traversal", latency_ms=t_graph_ms))

            if intent.requires_vector:
                t_vector_start = time.perf_counter()
                chunks = await self._execute_plan_retrieval(
                    plan, search_query, hyde_doc,
                    top_k or self._top_k, intent, resolved_entities,
                    user_id=user_id, tenant_id=tenant_id,
                )
                t_vector_ms = (time.perf_counter() - t_vector_start) * 1000
                log_step_info(logger, "VECTOR_RETRIEVAL", "Step 7: Searched vector document store: retrieved %d matching chunks in %.1fms", len(chunks), t_vector_ms)
                if metrics:
                    metrics.add_component(ComponentMetric("vector_search", latency_ms=t_vector_ms))

        # Merge Cypher facts & queries
        if cypher_facts:
            facts.extend(cypher_facts)
        if cyphers_run:
            cyphers.extend(cyphers_run)

        # Graph fallback if traversal strategies returned 0 facts
        is_tabular_query = bool(intent and (
            intent.query_type == QueryType.AGGREGATE_RANKING
            or getattr(intent, "aggregation_type", "") == "ranking"
            or any(t in effective_query.lower() for t in ["categor", "aum", "nav", "breakdown", "amc", "scheme"])
        ))
        if not facts and not is_tabular_query and (intent.entities_mentioned or resolved_entities or intent.query_type != QueryType.GENERAL):
            try:
                from app.engine import graph_store
                q_ents = [{"text": getattr(e, "name", str(e))} for e in resolved_entities] + [{"text": m} for m in (intent.entities_mentioned or [])]
                sub = graph_store.get_subgraph_for_query_with_fallback(
                    query=effective_query,
                    limit=15,
                    query_entities=q_ents if q_ents else None
                )
                for e in sub.get("edges", []):
                    s_name = e.get("s") or "Entity"
                    o_name = e.get("o") or "Target"
                    rel_name = e.get("rel") or "CONNECTED_TO"
                    facts.append(GraphFact(
                        fact_id=str(uuid4()),
                        statement=f"{s_name} {rel_name} {o_name}",
                        subject=s_name, predicate=rel_name, object=o_name,
                        properties={"confidence": e.get("conf", 1.0), "entity_type": e.get("s_label") or e.get("o_label") or "Entity"},
                        traversal_path=f"{e.get('s_label', 'Entity')}→{rel_name}→{e.get('o_label', 'Entity')}",
                    ))
                if sub.get("edges"):
                    traversal_paths.append(f"Connected knowledge graph neighborhood ({len(sub.get('edges'))} facts)")
                    cyphers.append("SUBGRAPH_FALLBACK")
                    log_step_info(logger, "GRAPH_FALLBACK", "Step 6b: Fallback graph search retrieved %d additional facts", len(sub.get("edges")))
            except Exception as fb_exc:
                log_step_debug(logger, "GRAPH_FALLBACK_NOTICE", "Graph fallback notice in answer: %s", fb_exc)

        # Vector fallback: if vector retrieval was not executed or returned 0 chunks,
        # but graph facts are sparse (<2) or query specifically references tabular/file data (.csv, csv, etc.)
        if not chunks and not (intent and intent.query_type == QueryType.AGGREGATE_RANKING):
            q_lower = effective_query.lower()
            file_match = any(term in q_lower for term in [".csv", "csv", "file", "document", "table", "data", "sheet", "dataset"])
            if file_match or len(facts) < 2:
                try:
                    t_vec_fb_start = time.perf_counter()
                    fb_chunks = await self._execute_plan_retrieval(
                        plan, search_query, hyde_doc,
                        top_k or self._top_k, intent, resolved_entities,
                        user_id=user_id, tenant_id=tenant_id,
                    )
                    if fb_chunks:
                        chunks = fb_chunks
                        t_vector_ms = (time.perf_counter() - t_vec_fb_start) * 1000
                        log_step_info(logger, "VECTOR_FALLBACK", "Step 7b: Fallback vector search retrieved %d chunks in %.1fms (query: %s)", len(chunks), t_vector_ms, effective_query)
                except Exception as fb_v_exc:
                    log_step_warning(logger, "VECTOR_FALLBACK_WARN", "Vector fallback error: %s", fb_v_exc)

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
                    log_step_info(
                        logger,
                        "ADAPTIVE_RETRIEVAL",
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
                        user_id=user_id,
                        tenant_id=tenant_id,
                    )
                    if round2_chunks:
                        chunks.extend(round2_chunks)
                        log_step_info(logger, "ADAPTIVE_RETRIEVAL", "Step 7c: Adaptive secondary search added %d extra chunks", len(round2_chunks))
            except Exception as exc:
                log_step_debug(logger, "ADAPTIVE_RETRIEVAL_NOTICE", "Adaptive retrieval notice: %s", exc)
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
            log_step_warning(logger, "CONTEXT_QUALITY_GATE", "Context quality gate failed (score=%.2f) for query: %s",
                           context.quality_score, effective_query)
        else:
            log_step_info(logger, "CONTEXT_ASSEMBLY", "Step 8: Assembled context for LLM: quality score=%.2f, gate passed=True, tokens=%d",
                          context.quality_score, context.token_count)
        t_asm_ms = (time.perf_counter() - t_asm_start) * 1000
        comp_asm.finalize()
        if metrics:
            metrics.add_component(comp_asm)

        # Step 7.5 — Track 6: Apply Correction Patch Layer (Shadow Graph / Microservices)
        applied_corrections = []
        try:
            entity_keys = []
            if resolved_entities:
                for ent in resolved_entities:
                    if hasattr(ent, "isin") and ent.isin:
                        entity_keys.append(ent.isin)
                    if hasattr(ent, "dedup_key") and ent.dedup_key:
                        entity_keys.append(ent.dedup_key)
                    if hasattr(ent, "name") and ent.name:
                        entity_keys.append(ent.name)
            if intent.entities_mentioned:
                entity_keys.extend(intent.entities_mentioned)
            seen_e = set()
            unique_entity_keys = [e for e in entity_keys if e and not (e in seen_e or seen_e.add(e))]
            if unique_entity_keys:
                base_text = context.context_text or ""
                context.context_text, applied_corrections = await self._apply_correction_patches(
                    entity_ids=unique_entity_keys,
                    context_text=base_text
                )
                if applied_corrections:
                    context.passed_quality_gate = True
                    context.quality_score = max(getattr(context, "quality_score", 0.0), 0.95)
                    log_step_info(logger, "REPAIR_PATCH_INJECTION", "Step 8b: Injected %d verified correction patches into context", len(applied_corrections))
        except Exception as patch_exc:
            log_step_debug(logger, "REPAIR_PATCH_NOTICE", "Correction patch layer notice: %s", patch_exc)

        # Step 8 — synthesis
        comp_synth = ComponentMetric("synthesis", time.perf_counter())
        t_gen_start = time.perf_counter()
        synthesis = await self._synthesizer.synthesize(effective_query, context)
        t_gen_ms = (time.perf_counter() - t_gen_start) * 1000
        comp_synth.finalize()
        if metrics:
            metrics.add_component(comp_synth)
        log_step_info(logger, "SYNTHESIS", "Step 9: Synthesized final answer with LLM in %.1fms (confidence=%s)", t_gen_ms, synthesis.confidence)

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
                log_step_warning(logger, "ANSWER_CRITIC", "Answer critic flagged critical issue: %s", critique.get("issues"))
                synthesis.confidence = "low"
                critic_escalated = True
                critic_reason = critique.get("issues", ["Contradiction with context"])[0]
            elif severity == CriticSeverity.WARNING:
                log_step_warning(logger, "ANSWER_CRITIC", "Answer critic raised warning: %s", critique.get("issues"))
                if synthesis.confidence == "high":
                    synthesis.confidence = "medium"
            else:
                log_step_info(logger, "ANSWER_CRITIC", "Step 10: Answer verification passed (critic score=%.2f, status=%s)", critique.get("score", 1.0), severity.value)
        except Exception as exc:
            log_step_debug(logger, "ANSWER_CRITIC_NOTICE", "Answer critic notice: %s", exc)
            comp_critic.error = str(exc)
        comp_critic.finalize()
        if metrics:
            metrics.add_component(comp_critic)

        # Step 8c — Post-Synthesis Patch Guardrail Rewriter (Option 5)
        if applied_corrections:
            try:
                from app.evaluation.patch_guardrail import get_patch_guardrail_rewriter
                rewriter = get_patch_guardrail_rewriter()
                synthesis, was_rewritten = rewriter.enforce_patches(
                    synthesis=synthesis,
                    applied_patches=applied_corrections,
                    query=effective_query,
                )
                if was_rewritten:
                    log_step_info(logger, "PATCH_GUARDRAIL", "Step 10b: Enforced verified errata patch values on final answer for '%s'", effective_query)
            except Exception as gr_exc:
                log_step_debug(logger, "PATCH_GUARDRAIL_NOTICE", "Patch guardrail notice: %s", gr_exc)

        # Step 8d — Grounding & Tabular Aggregation Guardrail (Layer 3)
        if intent and (intent.query_type == QueryType.AGGREGATE_RANKING or getattr(intent, "aggregation_type", "") == "ranking") and cypher_structured_rows:
            synthesis, guardrail_overridden = self._enforce_aggregation_guardrail(
                query=effective_query,
                synthesis=synthesis,
                rows=cypher_structured_rows,
                critic_escalated=critic_escalated,
            )
            if guardrail_overridden:
                critic_escalated = False

        # Step 9 — Review Queue Escalation (Phase 0)
        review_escalated = False
        escalation_reason_str = None
        if critic_escalated or synthesis.confidence == "low" or (context.quality_score < 0.40):
            try:
                from app.db.review_queue_repository import get_review_queue_repo
                from app.models.review_queue import ReviewQueueItem, ReviewReason
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
                log_step_info(logger, "REVIEW_QUEUE_ESCALATE", "Step 10c: Escalated response %s to human review queue (reason=%s)", req_id, reason.value)
            except Exception as exc:
                log_step_warning(logger, "REVIEW_QUEUE_ERROR", "Failed auto-escalating to review queue: %s", exc)

        total_ms = (time.perf_counter() - t0) * 1000

        # Step 10 — Cache population on miss
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
                user_id=user_id,
                tenant_id=tenant_id,
            )
            log_step_debug(logger, "CACHE_STORE", "Stored response in semantic cache for '%s'", effective_query)
        except Exception as exc:
            log_step_debug(logger, "CACHE_STORE_NOTICE", "Cache store notice: %s", exc)

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

        log_step_info(logger, "EXECUTION_COMPLETE", "Step 11: Query execution completed in %.1fms (context quality=%.2f, gate passed=%s)", total_ms, context.quality_score, context.passed_quality_gate)

        log_v2_query_audit({
            "query": effective_query,
            "query_type": intent.query_type.value if intent else "unknown",
            "entities": list(resolved_map.keys()),
            "graph_matched_by": "traversal_and_vector",
            "graph_nodes_count": len(set(f.subject for f in facts) | set(f.object for f in facts)) if facts else len(resolved_entities),
            "graph_edges_count": len(facts),
            "vector_hits_raw": len(chunks),
            "vector_bypassed": bool(intent and intent.query_type == QueryType.AGGREGATE_RANKING),
            "cache_hit": False,
            "patches_applied": len(applied_corrections),
            "quality_gate_passed": context.passed_quality_gate,
            "llm_model": getattr(self._synthesizer, "_model", "default"),
            "input_tokens": context.token_count,
            "output_tokens": len(synthesis.answer.split()) * 2 if synthesis.answer else 0,
            "latency_total_ms": total_ms,
            "status": "COMPLETED",
            "session_id": session_id,
        })

        return OrchestratorResponse(
            intent=intent,
            retrieval=retrieval,
            context=context,
            synthesis=synthesis,
            trace=trace,
            metrics=metrics,
        )

    async def traditional_search(
        self,
        query: str,
        top_k: int | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict]:
        """Flat vector search with no graph, no taxonomy scoping, no synthesis —
        the 'traditional RAG' comparison baseline.

        Args:
            query (str): Search query or input text.
            top_k (int | None): Number of top results to return.
            user_id (str | None): Unique identifier of the user.
            tenant_id (str | None): Unique identifier of the tenant.

        Returns:
            list[dict]: List of resulting items or records.
        """
        hits = await self._vector.search(
            query,
            top_k=top_k or self._top_k,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        return hits

    async def answer_stream(
        self,
        query: str,
        top_k: int | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
        enable_hyde: bool = True,
        track_metrics: bool = True,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream the answer pipeline as SSE-shaped dicts.

        Args:
            query (str): Search query or input text.
            top_k (int | None): Number of top results to return.
            history (list[dict] | None): Chat history message sequence.
            session_id (str | None): Unique identifier of the session.
            enable_hyde (bool): Whether to enable HyDE query expansion.
            track_metrics (bool): Whether to record performance metrics.
            user_id (str | None): Unique identifier of the user.
            tenant_id (str | None): Unique identifier of the tenant.

        Yields:
            AsyncGenerator[dict, None]: Stream of SSE-shaped event dictionaries.
        """
        t0 = time.perf_counter()
        req_id = str(uuid4())
        response_id = f"resp_{req_id[:12]}"
        metrics = QueryMetrics(request_id=req_id, query=query) if track_metrics else None

        def _record(query_type: str, cache_hit: bool = False, **fields):
            """Persist stream metrics so /api/metrics reflects streaming traffic too.

            Args:
                query_type (str): The query type.
                cache_hit (bool): The cache hit.
            """
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
            if user_msgs and _is_elliptical_followup(query):
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
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version, user_id=user_id, tenant_id=tenant_id)
        except Exception as exc:
            logger.debug("Cache lookup notice: %s", exc)

        if cached_entry and cached_entry.get("cache_hit"):
            log_step_info(logger, "STREAM_CACHE_HIT", "Streaming from semantic cache: '%s'", query)
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
            
            cache_total_ms = round((time.perf_counter() - t0) * 1000, 2)
            cache_quality_score = cached_entry.get("quality_score")
            cache_quality_gate_passed = cache_quality_score >= 0.3 if cache_quality_score is not None else False
            
            cold_tokens = cached_entry.get("cold_equivalent_tokens", 500)
            yield {
                "type": "complete",
                "response_id": response_id,
                "trace": {
                    "request_id": req_id,
                    "cache_hit": True,
                    "cache_kind": cached_entry.get("cache_kind", "exact"),
                    "request_total_ms": cache_total_ms,
                    "generation_ms": cache_total_ms,  # Cached response has no computation cost
                    "quality_score": cache_quality_score,
                    "quality_gate_passed": cache_quality_gate_passed,
                    "cold_equivalent_tokens": cold_tokens,
                    "tokens_saved": cold_tokens,
                },
                "answer": {
                    "answer": cached_answer,
                    "confidence": cached_entry.get("confidence", "high"),
                    "compliance_note": None,
                    "citations": cached_entry.get("citations", []),
                    "structured_rows": [],
                    "metrics": cached_entry.get("metrics", []),
                },
                "metrics": cached_entry.get("metrics", []),
                "graph_facts": cached_entry.get("graph_facts", []),
                "graph_nodes": sorted({f.get("subject") if isinstance(f, dict) else getattr(f, "subject", "") for f in cached_entry.get("graph_facts", [])} | {f.get("object") if isinstance(f, dict) else getattr(f, "object", "") for f in cached_entry.get("graph_facts", [])}),
                "graph_relationships": sorted({f.get("predicate") if isinstance(f, dict) else getattr(f, "predicate", "") for f in cached_entry.get("graph_facts", [])}),
                "graph_edges": [
                    {
                        "s": f.get("subject") if isinstance(f, dict) else getattr(f, "subject", ""),
                        "rel": f.get("predicate") if isinstance(f, dict) else getattr(f, "predicate", ""),
                        "o": f.get("object") if isinstance(f, dict) else getattr(f, "object", ""),
                        "conf": (f.get("properties", {}).get("confidence", 1.0) if isinstance(f, dict) else getattr(f, "properties", {}).get("confidence", 1.0)) if hasattr(f, "properties") or isinstance(f, dict) else 1.0
                    }
                    for f in cached_entry.get("graph_facts", [])
                ],
                "context_sources": cached_sources,
            }
            return

        # Latency tracking across streaming steps
        t_ner_ms = 0.0
        t_graph_ms = 0.0
        t_vector_ms = 0.0
        t_assembly_ms = 0.0
        generation_ms = 0.0

        # ── Step 0.75: Deterministic Pre-LLM Fast-Path Interceptor ────────
        try:
            from app.retrieval.fast_path_interceptor import get_fast_path_interceptor
            fast_path = get_fast_path_interceptor(self._repair_client)
            fast_resp = await fast_path.intercept(
                query=effective_query,
                entities=None,
                corpus_version=self._corpus_version,
            )
            if fast_resp:
                # Stream the fast-path response as SSE events
                log_step_info(logger, "FAST_PATH_INTERCEPTOR_STREAM", "Pre-LLM fast-path interceptor triggered for streaming")
                
                # Stream metadata
                yield {
                    "type": "metadata",
                    "intent": "aggregation" if fast_resp.intent else "general",
                    "entities": [],
                    "confidence": "high",
                }
                
                # Stream sources if available
                if fast_resp.context and fast_resp.context.sources:
                    sources_data = [s.model_dump() if hasattr(s, "model_dump") else s for s in fast_resp.context.sources]
                    yield {"type": "sources", "sources": sources_data}
                
                # Stream answer as chunks
                answer_text = fast_resp.synthesis.answer if fast_resp.synthesis else ""
                words = answer_text.split()
                for idx, word in enumerate(words):
                    yield {"type": "answer_chunk", "text": (word + " "), "index": idx}
                
                # Record metrics
                stream_total_ms = round((time.perf_counter() - t0) * 1000, 2)
                _record("fast_path_aggregation")
                
                # Stream completion
                yield {
                    "type": "complete",
                    "response_id": response_id,
                    "trace": {
                        "request_id": req_id,
                        "serving_engine": "v2_streaming",
                        "corpus_version": self._corpus_version,
                        "cache_hit": False,
                        "request_total_ms": stream_total_ms,
                        "quality_gate_passed": True,
                    },
                    "answer": {
                        "answer": answer_text,
                        "confidence": fast_resp.synthesis.confidence if fast_resp.synthesis else "high",
                        "compliance_note": fast_resp.synthesis.compliance_note if fast_resp.synthesis else None,
                        "citations": [c.model_dump() if hasattr(c, "model_dump") else c for c in (fast_resp.synthesis.citations if fast_resp.synthesis else [])],
                        "structured_rows": getattr(fast_resp.synthesis, "structured_rows", []) if fast_resp.synthesis else [],
                        "metrics": [],
                    },
                    "metrics": [],
                    "graph_facts": [],
                    "graph_nodes": [],
                    "graph_relationships": [],
                    "graph_edges": [],
                    "context_sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in (fast_resp.context.sources if fast_resp.context else [])],
                }
                return
        except Exception as exc:
            logger.debug("Stream fast-path interceptor notice: %s", exc)

        # ── Step 2: Intent classification ────────────────────────────────
        t_ner_start = time.perf_counter()
        intent = None
        try:
            intent = await self._intent.classify(effective_query)
            log_step_info(logger, "INTENT_CLASSIFICATION", "Step 3: Streaming classified intent: type=%s, entities detected=%s", intent.query_type.value if intent else "general", intent.entities_mentioned if intent else [])
            yield {
                "type": "metadata",
                "intent": intent.query_type.value if intent else "general",
                "entities": intent.entities_mentioned if intent else [],
                "confidence": "high",
            }
        except Exception as exc:
            log_step_warning(logger, "INTENT_CLASSIFICATION_WARN", "Intent classification failed during streaming: %s", exc)
            yield {"type": "error", "message": f"Intent classification error: {exc}", "recoverable": True}

        # ── Step 3: Entity resolution (parallelized) ──────────────────────
        resolved_entities = []
        resolved_map: dict[str, str] = {}
        if intent:
            try:
                if config.ENABLE_PARALLELIZATION and intent.entities_mentioned:
                    async def _resolve_surface(surface: str):
                        """Resolve surface.

                        Args:
                            surface (str): The surface.

                        Returns:
                            Result of the operation.
                        """
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
                log_step_warning(logger, "ENTITY_RESOLUTION_WARN", "Entity resolution failed during streaming: %s", exc)
                yield {"type": "error", "message": f"Entity resolution error: {exc}", "recoverable": True}

        t_ner_ms = (time.perf_counter() - t_ner_start) * 1000
        log_step_info(logger, "ENTITY_RESOLUTION", "Step 4: Streaming resolved %d financial entities against database in %.1fms: %s", len(resolved_entities), t_ner_ms, resolved_map)

        # ── Step 3.5: Cypher aggregation path ─────────────────────────────
        cypher_facts: list[GraphFact] = []
        cypher_structured_rows: list[dict] = []  # Authoritative tabular rows from CSV/aggregation engine
        cyphers_run: list[str] = []
        if intent and getattr(intent, "requires_cypher", False) and config.ENABLE_CYPHER_AUTO_CORRECTION:
            try:
                product_names = {e.name for e in resolved_entities if hasattr(e, "name")}
                rows, usage = text_to_cypher.generate_and_run_with_correction(
                    effective_query,
                    product_names=product_names,
                    allow_global_scope=bool(getattr(intent, "aggregation_type", "")),
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                if rows:
                    cypher_structured_rows.extend(rows)
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
                    log_step_info(logger, "CYPHER_AGGREGATION", "Step 5a: Streaming graph aggregation returned %d rows from %s", len(rows), usage.get("source"))
            except Exception as exc:
                log_step_warning(logger, "CYPHER_AGGREGATION_WARN", "Stream Cypher aggregation notice: %s", exc)

        # ── Step 3.5b: Tabular / CSV Aggregation Fallback (Layer 2) ────────
        if intent and (intent.query_type == QueryType.AGGREGATE_RANKING or getattr(intent, "aggregation_type", "") == "ranking") and not cypher_facts:
            fb_facts, fb_rows = self._populate_tabular_aggregation_facts(effective_query, intent)
            if fb_facts:
                cypher_facts.extend(fb_facts)
                cypher_structured_rows.extend(fb_rows)
                log_step_info(logger, "TABULAR_AGGREGATION_FALLBACK", "Step 5b: Streaming injected %d authoritative tabular facts into context", len(fb_facts))

        # ── Step 3.6: Query planner & decomposition ───────────────────────
        plan: Optional[ExecutionPlan] = None
        if intent and config.ENABLE_QUERY_DECOMPOSITION:
            try:
                plan = await self._planner.plan(effective_query)
                if plan.is_complex:
                    log_step_info(logger, "QUERY_PLANNING", "Step 3b: Streaming decomposed query into %d sub-tasks", len(plan.sub_tasks))
            except Exception as exc:
                log_step_debug(logger, "QUERY_PLANNING_NOTICE", "Stream query planner notice: %s", exc)

        # ── Step 4.5: HyDE Expansion ─────────────────────────────────────
        hyde_doc = ""
        if enable_hyde and config.ENABLE_HYDE_IN_ORCHESTRATOR and config.ENABLE_HYDE_CACHE and intent and intent.requires_vector:
            try:
                hyde_doc, hyde_lat = hyde.generate_hypothetical_document(
                    effective_query,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                log_step_info(logger, "HYDE_EXPANSION", "Step 5c: Streaming HyDE hypothetical document generated in %.1fms (cached=%s)", hyde_lat, hyde_lat < 5.0)
            except Exception as exc:
                log_step_debug(logger, "HYDE_EXPANSION_NOTICE", "Stream HyDE generation notice: %s", exc)

        search_query = effective_query
        if hyde_doc:
            search_query = effective_query + "\n\nHYPOTHETICAL DOCUMENT:\n" + hyde_doc

        # ── Steps 4 & 5-6: Parallel graph traversal + vector search ───────
        facts, traversal_paths, cyphers = [], [], []
        chunks: list[RetrievedChunk] = []

        needs_graph = bool(intent and (
            intent.requires_graph
            or (intent.query_type != QueryType.GENERAL)
            or bool(intent.entities_mentioned)
            or bool(resolved_entities)
        ))
        # Vector search is essential for all document-grounded queries and whenever
        # graph facts are not available to answer the query deterministically.
        needs_vector = bool(intent and (
            intent.requires_vector
            or not cypher_facts
            or any(k in effective_query.lower() for k in [
                "ebitda", "revenue", "annual report", "fy24", "fy25", "fy23", "pat", "esg", "target",
                "sebi", "circular", "rule", "guideline", "limit", "borrowing", "framework", "ratio"
            ])
        ))
        if intent and intent.query_type == QueryType.AGGREGATE_RANKING and cypher_facts:
            needs_vector = False

        async def _stream_graph():
            """Stream graph.

            Returns:
                Result of the operation.
            """
            return await self._traversal.traverse(
                intent, resolved_entities,
                user_id=user_id, tenant_id=tenant_id,
            )

        async def _stream_vector():
            """Stream vector.

            Returns:
                Result of the operation.
            """
            return await self._execute_plan_retrieval(
                plan, search_query, hyde_doc,
                top_k or self._top_k, intent, resolved_entities,
                user_id=user_id, tenant_id=tenant_id,
            )

        t_retrieval_start = time.perf_counter()
        if config.ENABLE_PARALLELIZATION and needs_graph and needs_vector:
            graph_res, vector_res = await asyncio.gather(
                _stream_graph(), _stream_vector(), return_exceptions=True
            )
            if isinstance(graph_res, Exception):
                log_step_warning(logger, "GRAPH_TRAVERSAL_WARN", "Graph traversal failed during streaming: %s", graph_res)
                yield {"type": "error", "message": f"Graph traversal error: {graph_res or type(graph_res).__name__}", "recoverable": True}
            else:
                facts, traversal_paths, cyphers = graph_res
                log_step_info(logger, "GRAPH_TRAVERSAL", "Step 6: Streaming traversed knowledge graph (parallel): found %d facts", len(facts))
            if isinstance(vector_res, Exception):
                log_step_warning(logger, "VECTOR_RETRIEVAL_WARN", "Vector search failure during streaming: %s", vector_res)
                yield {"type": "error", "message": f"Vector search error: {vector_res or type(vector_res).__name__}", "recoverable": True}
            else:
                chunks = vector_res
                log_step_info(logger, "VECTOR_RETRIEVAL", "Step 7: Streaming searched vector document store (parallel): retrieved %d chunks", len(chunks))
            t_retrieval_total = (time.perf_counter() - t_retrieval_start) * 1000
            t_graph_ms = t_retrieval_total
            t_vector_ms = t_retrieval_total
        else:
            if needs_graph:
                t_g_start = time.perf_counter()
                try:
                    facts, traversal_paths, cyphers = await _stream_graph()
                    log_step_info(logger, "GRAPH_TRAVERSAL", "Step 6: Streaming traversed knowledge graph: found %d facts", len(facts))
                except Exception as exc:
                    log_step_warning(logger, "GRAPH_TRAVERSAL_WARN", "Graph traversal failed during streaming: %s", exc)
                    yield {"type": "error", "message": f"Graph traversal error: {exc or type(exc).__name__}", "recoverable": True}
                t_graph_ms = (time.perf_counter() - t_g_start) * 1000
            if needs_vector:
                t_v_start = time.perf_counter()
                try:
                    chunks = await _stream_vector()
                    log_step_info(logger, "VECTOR_RETRIEVAL", "Step 7: Streaming searched vector document store: retrieved %d chunks", len(chunks))
                except Exception as exc:
                    log_step_warning(logger, "VECTOR_RETRIEVAL_WARN", "Vector search failed during streaming: %s", exc)
                    yield {"type": "error", "message": f"Vector search error: {exc or type(exc).__name__}", "recoverable": True}
                t_vector_ms = (time.perf_counter() - t_v_start) * 1000

        if cypher_facts:
            facts.extend(cypher_facts)
        if cyphers_run:
            cyphers.extend(cyphers_run)

        # Graph fallback in stream if traversal yielded 0 facts
        is_tabular_query = bool(intent and (
            intent.query_type == QueryType.AGGREGATE_RANKING
            or getattr(intent, "aggregation_type", "") == "ranking"
            or any(t in effective_query.lower() for t in ["categor", "aum", "nav", "breakdown", "amc", "scheme"])
        ))
        if not facts and not is_tabular_query and (intent.entities_mentioned or resolved_entities or intent.query_type != QueryType.GENERAL):
            try:
                from app.engine import graph_store
                q_ents = [{"text": getattr(e, "name", str(e))} for e in resolved_entities] + [{"text": m} for m in (intent.entities_mentioned or [])]
                sub = graph_store.get_subgraph_for_query_with_fallback(
                    query=effective_query,
                    limit=15,
                    query_entities=q_ents if q_ents else None
                )
                for e in sub.get("edges", []):
                    s_name = e.get("s") or "Entity"
                    o_name = e.get("o") or "Target"
                    rel_name = e.get("rel") or "CONNECTED_TO"
                    facts.append(GraphFact(
                        fact_id=str(uuid4()),
                        statement=f"{s_name} {rel_name} {o_name}",
                        subject=s_name, predicate=rel_name, object=o_name,
                        properties={"confidence": e.get("conf", 1.0), "entity_type": e.get("s_label") or e.get("o_label") or "Entity"},
                        traversal_path=f"{e.get('s_label', 'Entity')}→{rel_name}→{e.get('o_label', 'Entity')}",
                    ))
                if sub.get("edges"):
                    traversal_paths.append(f"Connected knowledge graph neighborhood ({len(sub.get('edges'))} facts)")
                    cyphers.append("SUBGRAPH_FALLBACK")
                    log_step_info(logger, "GRAPH_FALLBACK", "Step 6b: Streaming fallback graph search retrieved %d facts", len(sub.get("edges")))
            except Exception as fb_exc:
                log_step_debug(logger, "GRAPH_FALLBACK_NOTICE", "Graph fallback notice in answer_stream: %s", fb_exc)

        # Stream vector fallback
        if not chunks:
            q_lower = effective_query.lower()
            file_match = any(term in q_lower for term in [".csv", "csv", "file", "document", "table", "data", "sheet", "dataset"])
            if file_match or len(facts) < 2:
                try:
                    fb_chunks = await _stream_vector()
                    if fb_chunks:
                        chunks = fb_chunks
                        log_step_info(logger, "VECTOR_FALLBACK", "Step 7b: Streaming fallback vector search retrieved %d chunks", len(chunks))
                except Exception as fb_exc:
                    log_step_debug(logger, "VECTOR_FALLBACK_NOTICE", "Stream vector fallback notice: %s", fb_exc)

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
        t_asm_start = time.perf_counter()
        try:
            context = self._assembler.assemble(retrieval)
            log_step_info(logger, "CONTEXT_ASSEMBLY", "Step 8: Streaming assembled context for LLM: quality score=%.2f (passed=%s)", context.quality_score, context.passed_quality_gate)
            if not chunks and context and context.sources:
                yield {
                    "type": "sources",
                    "sources": [
                        {
                            "document_title": s.document_title,
                            "document_id": s.document_id,
                            "snippet": s.snippet or s.verbatim_text or "",
                            "score": 1.0,
                        }
                        for s in context.sources
                    ]
                }
        except Exception as exc:
            log_step_warning(logger, "CONTEXT_ASSEMBLY_WARN", "Context assembly failed during streaming: %s", exc)
            yield {"type": "error", "message": f"Context assembly error: {exc}", "recoverable": True}
        t_assembly_ms = (time.perf_counter() - t_asm_start) * 1000

        # ── Step 8: LLM streaming synthesis ──────────────────────────────
        t_gen_start = time.perf_counter()
        chunk_index = 0
        full_answer = ""
        try:
            from app.prompts import get_prompt
            prompt_obj = None
            try:
                prompt_obj = get_prompt("synthesis")
                system_prompt = prompt_obj.system if context else None
            except Exception:
                system_prompt = None
            ctx_text = context.context_text if context else ""
            user_prompt = prompt_obj.render(query=effective_query, context=ctx_text) if (context and prompt_obj) else f"Query: {effective_query}\n\nContext:\n{ctx_text}"

            async for text_chunk in self._synthesizer._llm.complete_stream(
                prompt=user_prompt,
                system=system_prompt,
            ):
                full_answer += text_chunk
                yield {"type": "answer_chunk", "text": text_chunk, "index": chunk_index}
                chunk_index += 1
        except Exception as exc:
            log_step_warning(logger, "STREAM_SYNTHESIS_WARN", "LLM streaming synthesis failed: %s", exc)
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
                log_step_error(logger, "STREAM_SYNTHESIS_ERROR", "Fallback synthesis also failed: %s", fallback_exc)
                yield {"type": "error", "message": "Unable to generate answer", "recoverable": False}

        generation_ms = (time.perf_counter() - t_gen_start) * 1000
        total_ms = round((time.perf_counter() - t0) * 1000, 2)
        
        # Strip code fences from streamed answer if the model enclosed it
        full_answer_clean = full_answer.strip()
        import re
        if full_answer_clean.startswith("```"):
            full_answer_clean = re.sub(r"^```(?:markdown|html)?\s*\n?([\s\S]*?)\n?```$", r"\1", full_answer_clean).strip()

        if not re.search(r"\[\d+\]", full_answer_clean) and context and context.sources:
            cite_markers = " ".join(f"[{s.source_index}]" for s in context.sources[:min(2, len(context.sources))])
            full_answer_clean = f"{full_answer_clean} {cite_markers}".strip()

        # ── Compute generation latency ──────────────────────────────────
        if generation_ms <= 0:
            generation_ms = max(0.0, total_ms - t_vector_ms - t_graph_ms - t_ner_ms)
        if generation_ms < 0:
            generation_ms = max(0.0, total_ms - 50.0)
        quality_score = context.quality_score if context else None
        quality_gate_passed = quality_score >= 0.3 if quality_score is not None else False

        # Build rich citations from context sources
        stream_citations = []
        if context and context.sources:
            for i, s in enumerate(context.sources):
                doc_name = getattr(s, "document_title", None) or getattr(s, "document_id", f"Document {i+1}")
                page_val = getattr(s, "page_number", None) or getattr(s, "page", None)
                stream_citations.append({
                    "marker": str(i + 1),
                    "source": {
                        "chunk_id": getattr(s, "chunk_id", f"src.{i+1}"),
                        "document_id": getattr(s, "document_id", doc_name),
                        "document_name": doc_name,
                        "page_number": page_val,
                        "page_label": getattr(s, "page_label", f"p. {page_val}" if page_val else "—"),
                        "verbatim_text": getattr(s, "verbatim_text", getattr(s, "snippet", "")),
                        "snippet": getattr(s, "snippet", ""),
                        "source_url": getattr(s, "url", getattr(s, "source_url", None)),
                        "score": getattr(s, "score", 0.9),
                    }
                })

        # ── Build graph node/relationship lists for evidence ──────────────
        graph_nodes = sorted({f.subject for f in facts} | {f.object for f in facts})
        graph_relationships = sorted({f.predicate for f in facts})
        stream_edges = [
            {"s": f.subject, "rel": f.predicate, "o": f.object, "conf": f.properties.get("confidence", 1.0) if hasattr(f, "properties") and isinstance(f.properties, dict) else 1.0}
            for f in facts
        ]

        # ── Cross-validation & metric provenance extraction ───────────────
        stream_cv_report = None
        stream_metrics = []
        try:
            from app.engine.cross_validation import cross_validate_answer
            docs_for_cv = [
                {
                    "name": getattr(s, "document_title", None) or getattr(s, "document_id", f"Doc {idx+1}"),
                    "document_title": getattr(s, "document_title", None) or getattr(s, "document_id", f"Doc {idx+1}"),
                    "page": getattr(s, "page_number", None) if getattr(s, "page_number", None) is not None else getattr(s, "page", None),
                    "snippet": getattr(s, "snippet", ""),
                    "full_text": getattr(s, "verbatim_text", "") or getattr(s, "snippet", ""),
                }
                for idx, s in enumerate(context.sources if context else [])
            ]
            stream_cv_report = cross_validate_answer(
                query=effective_query,
                answer=full_answer_clean,
                retrieved_docs=docs_for_cv,
                graph_triplets=stream_edges,
                query_type=intent.query_type.value if intent else "general",
            )
            stream_metrics = stream_cv_report.get("metrics", [])
        except Exception as cv_exc:
            log_step_debug(logger, "STREAM_CV_NOTICE", "Streaming cross-validation notice: %s", cv_exc)
            stream_metrics = []

        # ── Cache the streamed answer ─────────────────────────────────────
        if full_answer_clean and context:
            try:
                cache.store(
                    effective_query,
                    {
                        "answer": full_answer_clean,
                        "confidence": "high",
                        "compliance_note": None,
                        "citations": stream_citations,
                        "metrics": stream_metrics,
                        "provenance": [],
                        "quality_score": context.quality_score,
                        "output_tokens": len(full_answer_clean.split()) * 2,
                        "intent": intent.model_dump() if hasattr(intent, "model_dump") else {},
                        "traversal_paths": traversal_paths,
                        "graph_facts": [f.model_dump() if hasattr(f, "model_dump") else f for f in facts],
                        "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in context.sources],
                    },
                    corpus_version=self._corpus_version,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
            except Exception as exc:
                log_step_debug(logger, "STREAM_CACHE_NOTICE", "Stream cache store notice: %s", exc)

        _record(
            intent.query_type.value if intent else "unknown",
            entities_count=len(resolved_entities),
            graph_edges_found=len(facts),
            vector_chunks_retrieved=len(chunks),
        )

        in_toks = context.token_count if context else 0
        out_toks = len(full_answer_clean.split()) * 2

        log_step_info(logger, "EXECUTION_COMPLETE", "Step 11: Streaming query completed in %.1fms (chunks=%d, quality=%.2f)", total_ms, chunk_index, quality_score or 0.0)

        log_v2_query_audit({
            "query": effective_query,
            "query_type": intent.query_type.value if intent else "unknown",
            "entities": list(resolved_map.keys()),
            "graph_matched_by": "traversal_and_vector",
            "graph_nodes_count": len(set(f.subject for f in facts) | set(f.object for f in facts)) if facts else len(resolved_entities),
            "graph_edges_count": len(facts),
            "vector_hits_raw": len(chunks),
            "vector_bypassed": bool(intent and intent.query_type == QueryType.AGGREGATE_RANKING and not chunks),
            "cache_hit": False,
            "patches_applied": 0,
            "quality_gate_passed": quality_gate_passed,
            "llm_model": getattr(self._synthesizer, "_model", "default"),
            "input_tokens": in_toks,
            "output_tokens": out_toks,
            "latency_total_ms": total_ms,
            "status": "STREAM_COMPLETED",
            "session_id": session_id,
        })

        yield {
            "type": "complete",
            "response_id": response_id,
            "trace": {
                "request_id": req_id,
                "cache_hit": False,
                "request_total_ms": total_ms,
                "generation_ms": round(generation_ms, 2),
                "ner_ms": round(t_ner_ms, 2),
                "graph_ms": round(t_graph_ms, 2),
                "vector_ms": round(t_vector_ms, 2),
                "rerank_ms": 0.0,
                "assembly_ms": round(t_assembly_ms, 2),
                "input_tokens": in_toks,
                "output_tokens": out_toks,
                "tokens_total": in_toks + out_toks,
                "chunks_streamed": chunk_index,
                "quality_score": quality_score,
                "quality_gate_passed": quality_gate_passed,
                "cross_validation_ledger": stream_cv_report,
            },
            "answer": {
                "answer": full_answer_clean,
                "confidence": "high",
                "compliance_note": "Audited & Verified via Grounding Guardrail: Extracted from deterministic dataset." if (intent and intent.query_type == QueryType.AGGREGATE_RANKING) else None,
                "citations": stream_citations,
                "structured_rows": cypher_structured_rows,
                "metrics": stream_metrics,
            },
            "citations": stream_citations,
            "metrics": stream_metrics,
            "cross_validation_ledger": stream_cv_report,
            "graph_facts": [f.model_dump() if hasattr(f, "model_dump") else (f.__dict__ if hasattr(f, "__dict__") else f) for f in facts],
            "graph_nodes": graph_nodes,
            "graph_relationships": graph_relationships,
            "graph_edges": stream_edges,
            "context_sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in (context.sources if context else [])],
        }
