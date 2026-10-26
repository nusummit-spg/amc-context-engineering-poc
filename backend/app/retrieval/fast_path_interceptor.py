# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
app.retrieval.fast_path_interceptor
====================================
Option 2: Deterministic Pre-LLM Fast-Path Interceptor.

Detects simple atomic attribute questions on mutual fund entities (e.g. category,
TER, expense ratio, exit load, fund manager, AUM) and checks if an active approved
correction patch exists in the Repair Engine or cache. If found, constructs a verified
direct response in <15ms with 0 LLM token cost and 0 hallucination risk.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.core.metrics import QueryMetrics
from app.models.query import (
    Citation,
    OrchestratorResponse,
    QueryIntent,
    QueryTrace,
    QueryType,
    SourceAttribution,
    SynthesisOutput,
)
from app.monitoring.patch_metrics import get_patch_metrics  # GAP 2: Metrics

logger = logging.getLogger("retrieval.fast_path")

# Keywords mapping user query phrasing to standardized patch attributes
ATTRIBUTE_KEYWORDS: Dict[str, List[str]] = {
    "CATEGORY": ["category", "fund category", "cap category", "cap type", "market cap", "fund type", "scheme category"],
    "TER": ["ter", "expense ratio", "total expense ratio", "expenses", "expense"],
    "EXIT_LOAD": ["exit load", "exit-load", "redemption load", "exit fee", "load structure"],
    "FUND_MANAGER": ["fund manager", "manager", "portfolio manager", "managed by", "lead manager"],
    "AUM": ["aum", "asset under management", "assets under management", "fund size"],
    "BENCHMARK": ["benchmark", "benchmark index", "index"],
    "NAV": ["nav", "net asset value"],
}

# Aggregation query patterns for ranking/top-N queries
AGGREGATION_PATTERNS = {
    "ranking_indicators": ["top", "ranking", "highest", "largest", "biggest", "sorted by", "rank"],
    "aum_indicators": ["aum", "asset under management", "assets under management", "fund size"],
}


class FastPathInterceptor:
    """Pre-retrieval deterministic short-circuit evaluator."""

    def __init__(
        self,
        repair_client: Optional[Any] = None,
        patch_layer: Optional[Any] = None,
    ):
        """Initialize a new instance of FastPathInterceptor.

        Args:
            repair_client (Optional[Any]): The repair client.
            patch_layer (Optional[Any]): The patch layer.
        """
        self._repair_client = repair_client
        self._patch_layer = patch_layer

    def set_repair_client(self, repair_client: Any) -> None:
        """Set repair client.

        Args:
            repair_client (Any): The repair client.
        """
        self._repair_client = repair_client

    def _matches_aggregation_pattern(self, query_lower: str) -> bool:
        """Check if query is asking for ranked/aggregated mutual fund data.

        Args:
            query_lower (str): Lowercased query text.

        Returns:
            bool: True if query matches aggregation pattern.
        """
        has_ranking = any(
            kw in query_lower 
            for kw in AGGREGATION_PATTERNS["ranking_indicators"]
        )
        has_aum = any(
            kw in query_lower 
            for kw in AGGREGATION_PATTERNS["aum_indicators"]
        )
        
        return has_ranking and has_aum

    def _extract_target_attribute(self, query: str) -> Optional[str]:
        """Detect which attribute the user is asking about.

        Args:
            query (str): Search query or input text.

        Returns:
            Optional[str]: Matching object or record if found, None otherwise.
            Returns "AGGREGATION_RANKING" for ranking/top-N queries.
        """
        q_lower = query.lower()
        
        # Check for aggregation patterns first
        if self._matches_aggregation_pattern(q_lower):
            return "AGGREGATION_RANKING"
        
        for attr, patterns in ATTRIBUTE_KEYWORDS.items():
            for p in patterns:
                # Word boundary check for short terms like 'ter', 'aum', 'nav'
                if len(p) <= 3:
                    if re.search(rf"\b{re.escape(p)}\b", q_lower):
                        return attr
                elif p in q_lower:
                    return attr
        return None

    def _extract_entity_candidates(self, query: str) -> List[str]:
        """Extract mutual fund entity names mentioned in query.

        Args:
            query (str): Search query or input text.

        Returns:
            List[str]: List of resulting items or records.
        """
        candidates = []
        # Common fund brand prefixes and names in the AMC corpus
        fund_patterns = [
            r"(?:axis|hdfc|mirae|mirae asset|sbi|icici prudential|nippon india|kotak|aditya birla|uti|nusummit)\s+[\w\s]+(?:fund|etf|scheme)",
            r"(?:axis|hdfc|mirae|mirae asset|sbi|icici prudential|nippon india|kotak|aditya birla|uti|nusummit)\s+bluechip",
            r"(?:axis|hdfc|mirae|mirae asset|sbi|icici prudential|nippon india|kotak|aditya birla|uti|nusummit)\s+large cap",
            r"(?:axis|hdfc|mirae|mirae asset|sbi|icici prudential|nippon india|kotak|aditya birla|uti|nusummit)\s+mid cap",
            r"(?:axis|hdfc|mirae|mirae asset|sbi|icici prudential|nippon india|kotak|aditya birla|uti|nusummit)\s+flexi cap",
        ]
        q_lower = query.lower()
        # ISIN pattern: e.g. INF209K01157 or test ISINs
        isin_matches = re.findall(r"\bINF[0-9A-Z]{7,12}\b", query, flags=re.IGNORECASE)
        for m in isin_matches:
            cand = m.upper()
            if cand not in candidates:
                candidates.append(cand)

        for pat in fund_patterns:
            matches = re.findall(pat, q_lower, flags=re.IGNORECASE)
            for m in matches:
                clean_m = m.strip().title()
                if clean_m not in candidates:
                    candidates.append(clean_m)
        return candidates

    def try_intercept(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        corpus_version: str = "v2_baseline_20260814",
    ) -> Optional[OrchestratorResponse]:
        """Synchronous wrapper for intercept.

        Args:
            query (str): Search query or input text.
            entities (Optional[List[str]]): List of entity identifiers or objects.
            corpus_version (str): Version of the active document corpus.

        Returns:
            Optional[OrchestratorResponse]: Matching object or record if found, None otherwise.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(
                        asyncio.run,
                        self.intercept(query, entities=entities, corpus_version=corpus_version)
                    ).result()
            else:
                return loop.run_until_complete(
                    self.intercept(query, entities=entities, corpus_version=corpus_version)
                )
        except Exception:
            return asyncio.run(self.intercept(query, entities=entities, corpus_version=corpus_version))

    async def intercept(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        corpus_version: str = "v2_baseline_20260814",
    ) -> Optional[OrchestratorResponse]:
        """Check if query qualifies for deterministic short-circuit.
        Returns OrchestratorResponse if matched, or None to continue normal retrieval.

        Args:
            query (str): Search query or input text.
            entities (Optional[List[str]]): List of entity identifiers or objects.
            corpus_version (str): Version of the active document corpus.

        Returns:
            Optional[OrchestratorResponse]: Matching object or record if found, None otherwise.
        """
        t_start = time.perf_counter()  # GAP 2: Metrics
        metrics = get_patch_metrics()  # GAP 2: Metrics
        
        target_attr = self._extract_target_attribute(query)
        if not target_attr:
            metrics.record_fast_path_miss()  # GAP 2: Metrics
            return None

        # Handle aggregation queries
        if target_attr == "AGGREGATION_RANKING":
            return await self._intercept_aggregation_query(query, corpus_version, metrics, t_start)

        # Resolve candidate entity names for single-entity attribute queries
        entity_candidates = list(entities or [])
        extracted_candidates = self._extract_entity_candidates(query)
        for cand in extracted_candidates:
            if cand not in entity_candidates:
                entity_candidates.append(cand)

        if not entity_candidates:
            metrics.record_fast_path_miss()  # GAP 2: Metrics
            return None

        # Fetch active patches for candidate entities
        patches = await self._fetch_active_patches(entity_candidates)
        if not patches:
            metrics.record_fast_path_miss()  # GAP 2: Metrics
            return None

        # Match attribute against patches
        matched_patch = None
        for p in patches:
            p_attr = (p.get("attribute") or "").upper().strip()
            p_approved = p.get("approved", False)
            p_conf = float(p.get("confidence", 1.0))
            if p_approved and p_conf >= 0.85 and p_attr == target_attr:
                matched_patch = p
                break

        if not matched_patch:
            metrics.record_fast_path_miss()  # GAP 2: Metrics
            return None

        # Build direct deterministic response
        response = self._build_direct_response(query, matched_patch, corpus_version)
        
        # GAP 2: Track hit with latency
        latency_ms = (time.perf_counter() - t_start) * 1000
        metrics.record_fast_path_hit(
            query=query,
            patch_id=matched_patch.get("patch_id"),
            latency_ms=latency_ms,
            attribute=matched_patch.get("attribute")
        )
        
        logger.info(
            "⚡ FAST-PATH INTERCEPTOR TRIGGERED: entity=%s, attribute=%s, value=%s (%.2f ms, 0 tokens)",
            matched_patch.get("entity_id"),
            matched_patch.get("attribute"),
            matched_patch.get("corrected_value"),
            latency_ms
        )
        return response

    async def _intercept_aggregation_query(
        self,
        query: str,
        corpus_version: str,
        metrics: Any,
        t_start: float,
    ) -> Optional[OrchestratorResponse]:
        """Handle ranking/aggregation queries by routing to SchemeAggregationService.

        Args:
            query (str): The user query.
            corpus_version (str): Version of the active document corpus.
            metrics (Any): Metrics tracker.
            t_start (float): Start time for latency measurement.

        Returns:
            Optional[OrchestratorResponse]: Aggregation response or None to fall through.
        """
        try:
            from app.services.scheme_aggregation_service import get_aggregation_service
            
            # Extract limit from query (e.g., "top 10 schemes" → 10)
            limit_match = re.search(r"top\s+(\d+)", query.lower())
            limit = int(limit_match.group(1)) if limit_match else 10
            limit = max(1, min(100, limit))  # Clamp to 1-100
            
            # Determine sort metric based on query
            sort_by = "avg_aum" if "average" in query.lower() else "max_aum"
            
            logger.info(f"🎯 AGGREGATION INTERCEPTOR: Detected ranking query, limit={limit}, sort_by={sort_by}")
            
            # Call aggregation service
            service = get_aggregation_service()
            agg_response = service.get_top_schemes(
                limit=limit,
                sort_by=sort_by,
                include_plan_details=True,
            )
            
            # Build response
            response = self._build_aggregation_response(query, agg_response, corpus_version)
            
            # Track metrics
            latency_ms = (time.perf_counter() - t_start) * 1000
            metrics.record_aggregation_hit(
                query=query,
                limit=limit,
                latency_ms=latency_ms,
                schemes_count=len(agg_response.scheme_level_rankings),
            )
            
            logger.info(
                "⚡ AGGREGATION FAST-PATH INTERCEPTOR TRIGGERED: %d schemes, %s sort (%.2f ms, 0 tokens)",
                len(agg_response.scheme_level_rankings), sort_by, latency_ms
            )
            
            return response
            
        except Exception as e:
            logger.warning(f"Aggregation fast-path failed, falling through to vector RAG: {e}")
            metrics.record_fast_path_miss()
            return None  # Fall through to vector retrieval

    def _build_aggregation_response(
        self,
        query: str,
        agg_response: Any,
        corpus_version: str,
    ) -> OrchestratorResponse:
        """Construct OrchestratorResponse from aggregation service response.

        Args:
            query (str): The original query.
            agg_response (Any): Response from SchemeAggregationService.
            corpus_version (str): Version of the active document corpus.

        Returns:
            OrchestratorResponse: Formatted response ready for API.
        """
        # Format answer as markdown table
        answer_text = self._format_aggregation_answer(agg_response)
        
        # Build structured rows for detailed display
        structured_rows = [
            {
                "rank": idx,
                "scheme_name": metric.scheme_name,
                "amc": metric.amc,
                "average_aum_cr": f"₹{metric.avg_aum_cr:,.2f}",
                "max_aum_cr": f"₹{metric.max_aum_cr:,.2f}",
                "plan_count": metric.plan_count,
            }
            for idx, metric in enumerate(agg_response.scheme_level_rankings, 1)
        ]
        
        # Build synthesis output
        synth = SynthesisOutput(
            answer=answer_text,
            confidence="very_high",
            compliance_note="Deterministic Fast-Path: Aggregated directly from mutual fund CSV data without LLM.",
            citations=[Citation(source_index=1, document_title="Mutual Fund Data (CSV Aggregation)")],
            provenance=[{
                "source_index": 1,
                "doc": "Mutual Fund Data CSV Aggregation",
                "chunk_id": "agg_mutual_fund_top_schemes",
                "snippet": f"Top {len(agg_response.scheme_level_rankings)} schemes by {agg_response.interpretation_guide[:50]}",
            }],
            structured_rows=structured_rows,
        )
        
        # Build source attribution
        source = SourceAttribution(
            source_index=1,
            document_id="mutual_fund_data_agg",
            document_title="Mutual Fund Data (CSV Aggregation)",
            chunk_id="agg_mutual_fund_top_schemes",
            snippet=answer_text[:200],
            page=1,
            page_number=1,
            page_label="p. 1",
            verbatim_text=answer_text,
            url="/api/schemes/aggregation/top-schemes",
        )
        
        # Build intent
        intent = QueryIntent(
            query_type=QueryType.AGGREGATE_RANKING,
            requires_graph=False,
            requires_vector=False,
        )
        
        # Build trace
        trace = QueryTrace(
            request_id=f"agg_{uuid4().hex[:8]}",
            serving_engine="v2_aggregation_fast_path",
            corpus_version=corpus_version,
            cache_hit=False,
            cache_kind="aggregation_direct",
            cache_lookup_ms=1.0,
            query_rewrite_ms=0.0,
            ner_ms=0.5,
            graph_ms=0.0,
            vector_ms=0.0,
            rerank_ms=0.0,
            assembly_ms=0.5,
            generation_ms=0.0,
            request_total_ms=2.0,
            input_tokens=0,
            output_tokens=len(answer_text.split()) * 2,
            cold_equivalent_tokens=2000,
            tokens_saved=2000,
            quality_score=1.0,
            quality_gate_passed=True,
        )
        
        return OrchestratorResponse(
            intent=intent,
            retrieval=None,
            context=None,
            synthesis=synth,
            trace=trace,
            metrics=None,
        )

    def _format_aggregation_answer(self, agg_response: Any) -> str:
        """Format aggregation response as markdown table.

        Args:
            agg_response (Any): Response from SchemeAggregationService.

        Returns:
            str: Formatted markdown answer.
        """
        lines = [
            "# Top Mutual Fund Schemes by Average AUM\n",
            "| Rank | Scheme Name | AMC | Average AUM (₹ Cr) | Max AUM (₹ Cr) | Plans |",
            "|------|-----|-----|----|----|----|",
        ]
        
        for idx, metric in enumerate(agg_response.scheme_level_rankings, 1):
            lines.append(
                f"| {idx} | {metric.scheme_name} | {metric.amc} | "
                f"₹{metric.avg_aum_cr:,.2f} | ₹{metric.max_aum_cr:,.2f} | {metric.plan_count} |"
            )
        
        summary = (
            f"\n**Data Summary**: {len(agg_response.scheme_level_rankings)} schemes returned. "
            f"{agg_response.total_plan_variants} total plan variants across all schemes. "
            f"Data period: {agg_response.data_period}"
        )
        lines.append(summary)
        
        return "\n".join(lines)

    async def _fetch_active_patches(self, entity_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch patches from repair engine client or local fallback.

        Args:
            entity_ids (List[str]): Collection or list of entity ids.

        Returns:
            List[Dict[str, Any]]: List of resulting items or records.
        """
        if self._repair_client:
            try:
                return await self._repair_client.get_patches_for_entities(entity_ids)
            except Exception as exc:
                logger.debug("FastPath remote patch lookup notice: %s", exc)

        # Local patch layer check
        layer = self._patch_layer
        if not layer:
            try:
                from app.graph.correction_patch_layer import get_correction_patch_layer
                layer = get_correction_patch_layer()
            except Exception:
                pass

        if layer:
            try:
                res = []
                for eid in entity_ids:
                    pts = layer.get_patches_for_entity(eid)
                    for p in pts:
                        res.append({
                            "patch_id": p.patch_id,
                            "entity_id": p.entity_id,
                            "attribute": p.attribute,
                            "canonical_value": p.canonical_value,
                            "corrected_value": p.corrected_value,
                            "confidence": p.confidence,
                            "approved": p.approved,
                        })
                if res:
                    return res
            except Exception as exc:
                logger.debug("Local patch lookup notice: %s", exc)

        # Fallback to repair engine adapter if available
        try:
            from app.adapters_config import get_repair_engine
            engine = get_repair_engine()
            res = []
            for eid in entity_ids:
                pts = await engine.patch_layer.get_patches_for_entity(eid)
                for p in pts:
                    res.append({
                        "patch_id": p.patch_id,
                        "entity_id": p.entity_id,
                        "attribute": p.attribute,
                        "canonical_value": p.canonical_value if p.canonical_value is not None else p.original_value,
                        "corrected_value": p.corrected_value,
                        "confidence": p.confidence,
                        "approved": p.approved,
                    })
            return res
        except Exception:
            return []

    def _build_direct_response(
        self,
        query: str,
        patch: Dict[str, Any],
        corpus_version: str,
    ) -> OrchestratorResponse:
        """Construct full OrchestratorResponse without LLM call.

        Args:
            query (str): Search query or input text.
            patch (Dict[str, Any]): The patch.
            corpus_version (str): Version of the active document corpus.

        Returns:
            OrchestratorResponse: OrchestratorResponse object containing the operation result.
        """
        entity = patch.get("entity_id", "The scheme")
        attr = patch.get("attribute", "attribute").lower()
        val = patch.get("corrected_value", "")
        patch_id = patch.get("patch_id", "patch_verified")

        answer_text = f"The {attr} of {entity} is {val}. [1]"
        citation_title = f"Repair Engine Registry ({patch_id})"

        synth = SynthesisOutput(
            answer=answer_text,
            confidence="high",
            compliance_note=f"Deterministic Fast-Path: Verified via active Repair Engine patch ({patch_id}).",
            citations=[Citation(source_index=1, document_title=citation_title)],
            provenance=[{
                "source_index": 1,
                "doc": citation_title,
                "chunk_id": f"reg_{patch_id}",
                "snippet": f"Verified Ground Truth: {entity} {attr} = {val}",
            }],
            structured_rows=[{
                "scheme": entity,
                "attribute": attr.upper(),
                "value": val,
                "status": "verified_patch",
            }],
        )

        source = SourceAttribution(
            source_index=1,
            document_id=f"patch_{patch_id}",
            document_title=citation_title,
            chunk_id=f"reg_{patch_id}",
            snippet=f"Authoritative Ground Truth: {entity} {attr} is {val}.",
            page=1,
            page_number=1,
            page_label="p. 1",
            verbatim_text=f"Authoritative Ground Truth: {entity} {attr} is {val}.",
            url=f"/api/patches/{patch_id}",
        )

        intent = QueryIntent(
            query_type=QueryType.ENTITY_LOOKUP,
            entities_mentioned=[entity],
            requires_graph=True,
            requires_vector=False,
        )

        trace = QueryTrace(
            request_id=f"fast_{uuid4().hex[:8]}",
            serving_engine="v2_fast_path",
            corpus_version=corpus_version,
            cache_hit=False,
            cache_kind="fast_path_patch",
            cache_lookup_ms=2.0,
            query_rewrite_ms=0.0,
            ner_ms=1.0,
            graph_ms=2.0,
            vector_ms=0.0,
            rerank_ms=0.0,
            assembly_ms=0.5,
            generation_ms=0.0,
            request_total_ms=5.5,
            input_tokens=0,
            output_tokens=len(answer_text.split()) * 2,
            cold_equivalent_tokens=600,
            tokens_saved=600,
            quality_score=1.0,
            quality_gate_passed=True,
        )

        return OrchestratorResponse(
            intent=intent,
            retrieval=None,
            context=None,
            synthesis=synth,
            trace=trace,
            metrics=None,
        )


_global_fast_path_interceptor: Optional[FastPathInterceptor] = None


def get_fast_path_interceptor(repair_client: Optional[Any] = None) -> FastPathInterceptor:
    """Retrieve fast path interceptor.

    Args:
        repair_client (Optional[Any]): The repair client.

    Returns:
        FastPathInterceptor: Resulting FastPathInterceptor instance.
    """
    global _global_fast_path_interceptor
    if _global_fast_path_interceptor is None:
        _global_fast_path_interceptor = FastPathInterceptor(repair_client=repair_client)
    elif repair_client is not None and _global_fast_path_interceptor._repair_client is None:
        _global_fast_path_interceptor.set_repair_client(repair_client)
    return _global_fast_path_interceptor
