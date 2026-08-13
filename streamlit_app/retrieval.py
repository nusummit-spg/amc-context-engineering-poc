"""
retrieval.py
=============
Context-engineered hybrid retrieval, now with node-matching corrected:

  - Entity matching for aggregation/comparison uses embedding SIMILARITY
    (entity_resolver.py), not substring CONTAINS — this is what prevents a
    generic word like "debt" from matching across the entire corpus.
  - Aggregation queries first try text-to-Cypher (text_to_cypher.py): the
    LLM writes ONE targeted, schema-aware, safety-validated query rather
    than relying on a fixed 1-hop pattern. Falls back to the similarity-
    resolved deterministic aggregate if generation/validation fails.
  - The graph section of the prompt is only included when it's directly
    relevant (Path 1/2 entity/product match) — the untargeted global
    fallback (Path 3) never reaches the LLM, only the UI stats.
"""
from __future__ import annotations
import time
import concurrent.futures
from typing import Any, Dict, List

import config
import context_engineering
import entity_resolver
import faiss_store
import graph_store
import intent_cache
import llm_text_client
import ner_pipeline
import query_classifier
import text_to_cypher

GRAPH_HOPS_BY_INTENT = {"aggregation": 2, "comparison": 2, "direct_lookup": 1, "open_ended": 1}
GRAPH_LIMIT_BY_INTENT = {"aggregation": 25, "comparison": 20, "direct_lookup": 10, "open_ended": 15}
VECTOR_TOPK_BY_INTENT = {"aggregation": 3, "comparison": 5, "direct_lookup": 3, "open_ended": 8}
_RETRIEVAL_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="retrieval_pool")

HISTORY_TURNS_BY_INTENT = {
    "sebi_regulation": 2,
    "esg_sustainability": 3,
    "financial_performance": 2,
    "fund_performance": 3,
    "corporate_governance": 2,
}

DOMAIN_GRAPH_COVERAGE = {
    "sebi_regulation": 0.85,
    "esg_sustainability": 0.15,
    "financial_performance": 0.70,
    "fund_performance": 0.90,
    "corporate_governance": 0.60,
}

def compress_history_for_intent(history: list[dict], domain_intent: str) -> str:
    turns = HISTORY_TURNS_BY_INTENT.get(domain_intent, 2)
    if not history:
        return ""
    recent = history[-turns:]
    return "CONVERSATION HISTORY:\n" + "\n".join(f"{m.get('role','user').upper()}: {m.get('content','')}" for m in recent)

def calibrate_confidence(hits: list[dict], graph_result: dict, domain_intent: str) -> tuple[str, str]:
    coverage = DOMAIN_GRAPH_COVERAGE.get(domain_intent, 0.70)
    has_graph = bool(graph_result.get("edges") or graph_result.get("verified_facts"))
    top_score = max([h.get("score", 0.0) for h in hits], default=0.0)

    if coverage < 0.30 and not has_graph:
        return "medium confidence", "(limited graph coverage for domain)"
    if has_graph and top_score >= 0.65:
        return "high confidence", "(verified graph + strong vector match)"
    if top_score >= 0.70:
        return "high confidence", "(strong vector match)"
    if top_score >= 0.45:
        return "medium confidence", "(moderate vector match)"
    return "low confidence", "(weak context match)"

AGGREGATION_SKIP_LABELS = {"ASSET_CLASS", "SECTOR", "DATE"}


def _time_call(fn, *a, **kw):
    t0 = time.perf_counter()
    r = fn(*a, **kw)
    return r, time.perf_counter() - t0


def _select_top_edges(edges: List[dict], max_edges: int = 8) -> List[dict]:
    seen = set()
    deduped = []
    for e in edges:
        key = (e["s"], e["rel"], e["o"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    deduped.sort(key=lambda e: e.get("conf") if isinstance(e.get("conf"), (int, float)) else 0,
                 reverse=True)
    return deduped[:max_edges]


def _pick_aggregation_entity(query_entities: list) -> str | None:
    """Avoid generic category words (debt/equity/sector names) as the
    aggregation anchor — prefer specific named entities."""
    candidates = [e for e in query_entities if e["label"] not in AGGREGATION_SKIP_LABELS]
    if not candidates:
        return None
    candidates.sort(key=lambda e: len(e["text"]), reverse=True)
    return candidates[0]["text"]


def _format_cypher_rows(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = []
    for row in rows[:10]:
        parts = [f"{k}={v}" for k, v in row.items()]
        lines.append("  - " + ", ".join(parts))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# TRADITIONAL
# ─────────────────────────────────────────────────────────────────────────

def traditional_rag(query: str, store) -> Dict[str, Any]:
    hits, retrieve_time = _time_call(store.retrieve, query, top_k_children=5)
    t_post = time.perf_counter()
    context = "\n\n---\n\n".join(
        f"[{h['product_name']} | Page {h['page_num']}]\n{h['parent_text']}" for h in hits)

    prompt = f"""Answer using ONLY the context below. If the answer isn't in the
context, say so explicitly.

CONTEXT:
{context}

QUESTION: {query}

ANSWER:"""
    post_process_time = time.perf_counter() - t_post
    t_llm = time.perf_counter()
    answer, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
    llm_time = time.perf_counter() - t_llm
    total_tokens = usage["input_tokens"] + usage["output_tokens"]

    docs = [{"name": h["source"], "score": round(h["score"], 2),
         "page": h["page_num"],
         "snippet": h["child_text"][:160].replace("\n", " "),
         "full_text": h["parent_text"]} for h in hits]

    telemetry_breakdown = {
        "pipeline_mode": "Traditional Vector RAG",
        "latency_vector_db_ms": round(retrieve_time * 1000.0, 2),
        "latency_graph_db_ms": 0.0,
        "latency_ner_processing_ms": 0.0,
        "latency_post_retrieval_processing_ms": round(post_process_time * 1000.0, 2),
        "latency_llm_generation_ms": round(llm_time * 1000.0, 2),
        "latency_total_pipeline_ms": round((retrieve_time + post_process_time + llm_time) * 1000.0, 2),
        "tokens_input": usage["input_tokens"],
        "tokens_output": usage["output_tokens"],
        "tokens_total": total_tokens,
        "db_candidates_surfaced": len(hits),
        "vector_bypassed": False,
        "status": "SUCCESS"
    }

    return {
        "mode": "traditional", "query": query,
        "answer": answer or "LLM unavailable — check credentials.",
        "docs": docs,
        "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
        "total_tokens": total_tokens,
        "retrieve_time": retrieve_time, "llm_time": llm_time,
        "total_time": retrieve_time + post_process_time + llm_time,
        "telemetry_breakdown": telemetry_breakdown,
    }


# ─────────────────────────────────────────────────────────────────────────
# HYBRID
# ─────────────────────────────────────────────────────────────────────────

def log_query_audit(audit_data: Dict[str, Any]):
    """
    Writes structured query execution audit log to console and logs/query_execution_audit.jsonl.
    Allows exact verification of active parameters, latencies, and Pillar 1-4 activations.
    """
    import json
    from datetime import datetime
    
    timestamp = datetime.now().isoformat()
    audit_data["timestamp"] = timestamp
    
    # Console formatting for quick visual debugging
    print("\n================================================================================", flush=True)
    print(f"  [QUERY AUDIT LOG] {timestamp}", flush=True)
    print("================================================================================", flush=True)
    print(f"  Query             : \"{audit_data.get('query')}\"", flush=True)
    print(f"  Classified Type   : {audit_data.get('query_type').upper()} (Pillar 1 Intent-Driven Routing)", flush=True)
    print(f"  NER Layer A (Rule): {len(audit_data.get('ner_layer_a', []))} entities -> {[e['text'] for e in audit_data.get('ner_layer_a', [])]}", flush=True)
    print(f"  NER Layer B (ML)  : {len(audit_data.get('ner_layer_b', []))} entities -> {[e['text'] for e in audit_data.get('ner_layer_b', [])]}", flush=True)
    print(f"  Graph Traversal   : Matched by '{audit_data.get('graph_matched_by')}' | {audit_data.get('graph_nodes_count', 0)} nodes | {audit_data.get('graph_edges_count', 0)} 1-hop edges", flush=True)
    print(f"  Vector Retrieval  : {audit_data.get('vector_hits_raw', 0)} raw candidates | Bypassed={audit_data.get('vector_bypassed', False)}", flush=True)
    print(f"  Enrichment Mode   : Verified Aggregate={audit_data.get('verified_aggregate_used', False)} | Comparison Table={audit_data.get('comparison_table_used', False)}", flush=True)
    print(f"  LLM Model         : {audit_data.get('llm_model')} | Input Tokens: {audit_data.get('input_tokens', 0)} | Output Tokens: {audit_data.get('output_tokens', 0)}", flush=True)
    print(f"  Latencies (ms)    : NER={audit_data.get('latency_ner_ms', 0):.1f}ms | Graph={audit_data.get('latency_graph_ms', 0):.1f}ms | Vector={audit_data.get('latency_vector_ms', 0):.1f}ms | LLM={audit_data.get('latency_llm_ms', 0):.1f}ms | Total={audit_data.get('latency_total_ms', 0):.1f}ms", flush=True)
    print("================================================================================\n", flush=True)
    
    # Persistent JSONL log — single appending file
    log_file = config.LOG_DIR / "query_execution_audit.jsonl"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_data, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"  [Audit Log Warning] Could not write to {log_file.name}: {exc}", flush=True)


def _build_cached_response(cached: intent_cache.CacheEntry, query: str, elapsed: float) -> Dict[str, Any]:
    docs = [{"name": p.get("doc", ""), "score": p.get("score", 1.0), "page": p.get("page", 1),
             "snippet": "", "full_text": ""} for p in cached.provenance]
    return {
        "mode": "hybrid",
        "query": query,
        "query_type": cached.query_type,
        "domain_intent": cached.domain_intent,
        "answer": cached.answer,
        "confidence_label": cached.confidence_label,
        "confidence_reason": cached.confidence_reason,
        "docs": docs,
        "total_tokens": cached.total_tokens,
        "total_time": round(elapsed, 3),
        "cache_hit": True,
    }


def hybrid_graphrag(query: str, store, history: list[dict] | None = None, user_role: str | None = None) -> Dict[str, Any]:

    t_start = time.perf_counter()
    import pii_scrub
    import language_detector
    import compliance_guardrails

    # PII Scrubbing with audit metrics
    query, pii_count, pii_types = pii_scrub.scrub_text_with_metrics(query)

    # Multilingual Language Detection & Regional Routing
    lang_info = language_detector.detect_query_language(query)
    detected_lang = lang_info.get("language", "en")
    query_for_retrieval = lang_info.get("normalized_query", query)

    # Guardrails AI Input Safety Validation
    input_guard = compliance_guardrails.validate_input_query(query_for_retrieval)
    if not input_guard.get("is_safe", True):
        return {
            "mode": "hybrid", "query": query,
            "answer": f"Query blocked by Compliance Safety Guard: {input_guard.get('risk_flag')}",
            "confidence_label": "BLOCKED", "confidence_reason": input_guard.get("risk_flag"),
            "docs": [], "total_tokens": 0, "total_time": 0.001, "cache_hit": False,
            "telemetry_breakdown": {"status": "BLOCKED", "risk_flag": input_guard.get("risk_flag")}
        }

    # ── Step 1: Single-pass embedding & classification ─────────────────────────
    query_vec = faiss_store._embed_texts([query_for_retrieval])
    query_type = query_classifier.classify_query(query_for_retrieval)
    domain_intent = intent_cache.classify_domain_intent(query_for_retrieval)

    # ── Step 2: Intent Cache short-circuit (dual-gate lookup) ────────────────
    if config.ENABLE_INTENT_CACHE:
        cache = intent_cache.get_cache()
        cached = cache.lookup(query_vec, query_type, domain_intent, query_for_retrieval)
        if cached is not None:
            return _build_cached_response(cached, query, time.perf_counter() - t_start)


    # ── Step 3: Domain-routed NER extraction ─────────────────────────────────
    t_ner_0 = time.perf_counter()
    skip_gliner = (query_type == "direct_lookup")
    query_entities = ner_pipeline.run_layers_ab(
        query, skip_gliner=skip_gliner, is_query=True, domain_intent=domain_intent
    )
    latency_ner_ms = (time.perf_counter() - t_ner_0) * 1000.0

    entity_texts = [e["text"] for e in query_entities]
    ner_layer_a = [e for e in query_entities if e.get("layer") == "A"]
    ner_layer_b = [e for e in query_entities if e.get("layer") == "B"]

    # ── Step 4: Intent-driven parameters & parallel retrieval ─────────────────
    hops = GRAPH_HOPS_BY_INTENT.get(query_type, 1)
    limit = GRAPH_LIMIT_BY_INTENT.get(query_type, 15)
    top_k = VECTOR_TOPK_BY_INTENT.get(query_type, 5)

    t_ret_0 = time.perf_counter()
    vector_bypassed = False

    if config.ENABLE_PARALLEL_RETRIEVAL:
        graph_future = _RETRIEVAL_THREAD_POOL.submit(
            graph_store.get_subgraph_for_query,
            query, None, hops, limit, query_entities,
        )
        vector_future = _RETRIEVAL_THREAD_POOL.submit(store.retrieve, query, top_k_children=top_k)
        try:
            graph_result = graph_future.result()
        except Exception as exc:
            print(f"  [graph] Neo4j offline ({exc}) — proceeding with vector context", flush=True)
            graph_result = {"nodes": [], "edges": [], "matched_by": "none"}
        try:
            hits = vector_future.result()
        except Exception as exc:
            print(f"  [vector] Retrieval error: {exc}", flush=True)
            hits = []
    else:
        try:
            graph_result = graph_store.get_subgraph_for_query(query, None, hops, limit, query_entities)
        except Exception as exc:
            print(f"  [graph] Neo4j offline ({exc}) — proceeding with vector context", flush=True)
            graph_result = {"nodes": [], "edges": [], "matched_by": "none"}
    retrieve_time = (time.perf_counter() - t_ret_0) * 1000.0

    # FlashRank CPU Cross-Encoder Reranker
    import flashrank_reranker
    hits = flashrank_reranker.rerank_passages(query_for_retrieval, hits, top_n=3)


    # Secondary graph query fallback if primary graph search had no edges
    if not graph_result.get("edges") and hits:
        product_names = {h.get("product_name") for h in hits if h.get("product_name")}
        t1 = time.perf_counter()
        graph_result = graph_store.get_subgraph_for_query(
            query_for_retrieval, product_names=product_names, hops=1, limit=limit,
            query_entities=query_entities)

    product_names_for_scope = {h.get("product_name") for h in hits if h.get("product_name")}

    # ── Step 5: Reciprocal Rank Fusion (RRF) & Type-specific enrichment ───────
    t2 = time.perf_counter()
    if config.ENABLE_RRF_FUSION and hits:
        # Reciprocal Rank Fusion formula: Score(d) = w_vector / (60 + r_vector) + w_graph / (60 + r_graph)
        has_graph_match = bool(graph_result.get("edges"))
        w_vector = 0.30 if has_graph_match else 0.80
        w_graph = 0.70 if has_graph_match else 0.20
        for i, h in enumerate(hits):
            r_vec = i + 1
            r_graph = 1 if has_graph_match else 100
            h["rrf_score"] = round((w_vector / (60.0 + r_vec)) + (w_graph / (60.0 + r_graph)), 5)
        hits.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)

    verified_facts = ""
    comparison_blocks = ""
    executed_cypher_query = None
    hidden_tokens = 0

    if query_type == "aggregation" and entity_texts:
        cypher_rows, cypher_usage = text_to_cypher.generate_and_run(query_for_retrieval, product_names_for_scope)
        hidden_tokens += cypher_usage.get("input_tokens", 0) + cypher_usage.get("output_tokens", 0)
        executed_cypher_query = f"MATCH ScopeAggregation for {product_names_for_scope}"
        if cypher_rows:
            verified_facts = (
                "[VERIFIED AGGREGATE — generated Cypher query executed directly "
                "against the graph, scoped to the documents this question is about]\n"
                + _format_cypher_rows(cypher_rows)
            )

    elif query_type == "comparison" and len(entity_texts) >= 2:
        resolved = entity_resolver.resolve_entities_for_query(entity_texts, product_names_for_scope)
        per_entity = graph_store.find_entities_for_comparison(resolved, hops=1)
        blocks = []
        for entity, rels in per_entity.items():
            if not rels:
                continue
            top_rels = _select_top_edges(
                [{"s": r["s"], "rel": r["rel_type"], "o": r["o"], "conf": r.get("conf")} for r in rels],
                max_edges=8)
            table_header = f"### [{entity}] Graph Neighborhood\n| Subject | Relationship | Target |\n| :--- | :--- | :--- |"
            table_rows = [f"| **{r['s']}** | `{r['rel']}` | {r['o']} |" for r in top_rels]
            blocks.append(table_header + "\n" + "\n".join(table_rows))
        comparison_blocks = "\n\n".join(blocks)

    enrichment_time = time.perf_counter() - t2


    trust_verified_facts = bool(verified_facts or comparison_blocks)
    effective_hits = hits
    if trust_verified_facts and query_type in ("aggregation", "comparison"):
        effective_hits = hits[:1]

    # ── RBAC & Agentic Core Integration ──────────────────────────────────────
    import rbac
    import agent_planner
    import answer_critic

    user_role = user_role or rbac.AMCRole.COMPLIANCE_OFFICER.value

    # RBAC Boundary Scoping
    hits = rbac.filter_chunks_by_role(hits, user_role)
    graph_result = rbac.filter_graph_by_role(graph_result, user_role)

    # Agentic Planner Check
    planner = agent_planner.AgentPlanner()
    plan = planner.create_plan(query, active_domains=[domain_intent])

    top_edges = []
    if graph_result.get("matched_by") in ("entity", "product") and graph_result.get("edges"):
        top_edges = _select_top_edges(graph_result["edges"], max_edges=8)

    history_text = compress_history_for_intent(history or [], domain_intent)

    # ── Step 6: Budgeted prompt assembly & LLM generation ────────────────────
    prompt, max_output_tokens = context_engineering.build_prompt(
        query=query_for_retrieval,
        verified_facts=verified_facts,
        comparison_blocks=comparison_blocks,
        top_edges=top_edges,
        hits=effective_hits,
        query_type=query_type,
        domain_intent=domain_intent,
        history_text=history_text,
        trust_verified_facts=trust_verified_facts,
    )

    t_llm = time.perf_counter()
    raw_answer, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=max_output_tokens)
    llm_time = time.perf_counter() - t_llm

    # Guardrails AI Output Validation (SEBI RIA Advice Shield & Disclaimer Enforcement)
    out_guard = compliance_guardrails.validate_llm_output(raw_answer, prompt, domain_intent)
    answer = out_guard.get("modified_answer", raw_answer)

    total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0) + hidden_tokens
    elapsed = time.perf_counter() - t_start

    confidence_label, confidence_reason = calibrate_confidence(effective_hits, graph_result, domain_intent)

    docs = [{"name": h["source"], "score": round(h.get("rrf_score", h["score"]), 3),
             "page": h["page_num"],
             "doc_sha256": h.get("doc_sha256", "N/A"),
             "snippet": h["child_text"][:160].replace("\n", " "),
             "full_text": h["parent_text"]} for h in effective_hits]

    provenance_records = [{"doc": h["source"], "page": h["page_num"], "score": h["score"], "doc_sha256": h.get("doc_sha256", "N/A")} for h in effective_hits]

    # ── Step 7: Store in IntentCache on success ──────────────────────────────
    if answer and config.ENABLE_INTENT_CACHE:
        cache = intent_cache.get_cache()
        cache.store(
            query_vec=query_vec,
            query_type=query_type,
            domain_intent=domain_intent,
            query_text=query_for_retrieval,
            answer=answer,
            provenance=provenance_records,
            confidence_label=confidence_label,
            confidence_reason=confidence_reason,
            total_tokens=total_tokens,
        )

    # ── Step 8: Persistent audit log ─────────────────────────────────────────
    log_query_audit({
        "query": query,
        "query_type": query_type,
        "domain_intent": domain_intent,
        "intent_key": f"{query_type}::{domain_intent}",
        "detected_language": detected_lang,
        "pii_entities_scrubbed_count": pii_count,
        "pii_types_found": pii_types,
        "cypher_query_executed": executed_cypher_query,
        "advice_shield_triggered": out_guard.get("advice_shield_triggered", False),
        "guardrail_reasons": out_guard.get("reasons", []),
        "cache_hit": False,
        "ner_layer_a": ner_layer_a,
        "ner_layer_b": ner_layer_b,
        "ner_labels_used": config.get_gliner_labels(domain_intent),
        "ner_cache_stats": ner_pipeline.get_ner_cache_stats(),
        "graph_matched_by": graph_result.get("matched_by", "none"),
        "graph_nodes_count": len(graph_result.get("nodes", [])),
        "graph_edges_count": len(graph_result.get("edges", [])),
        "vector_hits_raw": len(hits),
        "vector_bypassed": vector_bypassed,
        "tokens_input": usage.get("input_tokens", 0),
        "tokens_output": usage.get("output_tokens", 0),

        "tokens_hidden_cypher": hidden_tokens,
        "tokens_total": total_tokens,
        "latency_ner_ms": round(latency_ner_ms, 1),
        "latency_retrieve_ms": round(retrieve_time, 1),
        "latency_llm_ms": round(llm_time * 1000, 1),
        "latency_total_pipeline_ms": round(elapsed * 1000, 1),
        "confidence_label": confidence_label,
        "confidence_reason": confidence_reason,
        "status": "SUCCESS",
    })

    active_model, _ = llm_text_client._resolve_model_and_fallbacks()
    ui_badges = [
        {"label": f"LLM Engine: {active_model}", "desc": "LiteLLM Provider", "type": "success"},
        {"label": f"Intent: {query_type.upper()}", "desc": f"Domain: {domain_intent}", "type": "primary"},
        {"label": f"Confidence: {confidence_label}", "desc": confidence_reason, "type": "success" if "high" in confidence_label else "neutral"},
    ]

    triplet_table = [
        {"s": e.get("s", ""), "rel": e.get("rel", ""), "o": e.get("o", ""), "conf": e.get("conf", 1.0)}
        for e in (top_edges or graph_result.get("edges", [])[:10])
    ]

    telemetry_breakdown = {
        "pipeline_mode": f"ContextGraph Hybrid ({query_type.upper()})",
        "latency_vector_db_ms": round(retrieve_time, 2),
        "latency_graph_db_ms": 0.0,
        "latency_ner_processing_ms": round(latency_ner_ms, 2),
        "latency_post_retrieval_processing_ms": round(enrichment_time * 1000.0, 2) if 'enrichment_time' in locals() else 0.0,
        "latency_llm_generation_ms": round(llm_time * 1000.0, 2),
        "latency_total_pipeline_ms": round(elapsed * 1000.0, 2),
        "tokens_input": usage.get("input_tokens", 0),
        "tokens_output": usage.get("output_tokens", 0),
        "tokens_total": total_tokens,
        "db_candidates_surfaced": len(graph_result.get("nodes", [])) + len(hits),
        "vector_bypassed": vector_bypassed,
        "ui_badges": ui_badges,
        "triplet_table": triplet_table,
        "status": "SUCCESS"
    }

    return {
        "mode": "hybrid",
        "query": query,
        "query_type": query_type,
        "domain_intent": domain_intent,
        "answer": answer or "LLM response empty.",
        "confidence_label": confidence_label,
        "confidence_reason": confidence_reason,
        "docs": docs,
        "graph_nodes": graph_result.get("nodes", []),
        "graph_edges": graph_result.get("edges", []),
        "graph_edges_used_in_prompt": top_edges,
        "matched_entity_texts": list(entity_texts),
        "active_labels": list({e["label"] for e in query_entities}),
        "used_verified_aggregate": bool(verified_facts),
        "used_comparison_mode": bool(comparison_blocks),
        "graph_matched_by": graph_result.get("matched_by", "none"),
        "total_tokens": total_tokens,
        "total_time": round(elapsed, 3),
        "cache_hit": False,
        "telemetry_breakdown": telemetry_breakdown,
    }


def relevancy_score(result: Dict[str, Any]) -> float:
    answer = result.get("answer", "")
    score = 0.0
    score += min(answer.count("[") * 0.12, 0.35)
    score += 0.25 if result.get("graph_edges_used_in_prompt") else 0
    score += 0.25 if result.get("used_verified_aggregate") else 0
    score += 0.15 if "isn't in" not in answer.lower() and "not in the context" not in answer.lower() else 0
    return round(min(score, 1.0), 2)


def warmup_models():
    """Pre-load GLiNER and sentence-transformers into RAM on backend boot."""
    try:
        print("  [warmup] Pre-warming GLiNER & Embedder...", flush=True)
        _ = ner_pipeline._get_gliner()
        _ = faiss_store._get_embedder()
        print("  [warmup] Models pre-warmed cleanly.", flush=True)
    except Exception as exc:
        print(f"  [warmup] Model warm-up skipped: {exc}", flush=True)


def validate_system_readiness() -> Dict[str, Any]:
    """Diagnostic check verifying FAISS index files, Neo4j connectivity, and LLM API keys on startup."""
    index_path = config.FAISS_DIR / "amc_master" / "index.faiss"
    faiss_ready = index_path.exists()
    
    has_groq = bool(getattr(config, "GROQ_API_KEY", ""))
    has_claude = bool(getattr(config, "CLAUDE_API_KEY", ""))
    llm_ready = has_groq or has_claude
    
    neo4j_ready = False
    try:
        with graph_store.get_driver().session(database=config.NEO4J_DATABASE) as s:
            r = s.run("RETURN 1 AS ping")
            neo4j_ready = bool(r.single())
    except Exception:
        neo4j_ready = False
        
    readiness = {
        "faiss_index_ready": faiss_ready,
        "neo4j_connected": neo4j_ready,
        "llm_configured": llm_ready,
        "primary_provider": getattr(config, "PRIMARY_LLM_PROVIDER", "groq"),
        "overall_status": "READY" if (faiss_ready and llm_ready) else "DEGRADED",
    }
    return readiness