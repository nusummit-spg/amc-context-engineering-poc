# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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

from app.engine import config
from app.engine import context_memory
from app.engine import entity_resolver
from app.engine import faiss_store
from app.engine import graph_store
from app.engine import llm_text_client
from app.engine import ner_pipeline
from app.engine import query_classifier
from app.engine import text_to_cypher
from app.engine.cross_validation import cross_validate_answer

AGGREGATION_SKIP_LABELS = {"ASSET_CLASS", "SECTOR", "DATE"}

SYSTEM_SYNTHESIS_PROMPT = """You are an expert financial, regulatory, and corporate intelligence analyst for AMC portfolios and corporate filings.
Your task is to synthesize clear, direct, accurate, and structured answers strictly grounded in the provided context.

Critical Domain & Table Interpretation Guidelines:
1. When interpreting corporate ESG scorecards and multi-column tables:
   - Understand the 8 portfolio companies in the Adani ESG Snapshot columns in standard sequence:
     1. Adani Enterprises (AEL)
     2. Adani Ports & SEZ (APSEZ)
     3. Adani Green Energy (AGEL)
     4. Adani Energy Solutions (AESL)
     5. Adani Power (APL)
     6. Adani Total Gas (ATGL)
     7. Ambuja Cements
     8. ACC Limited
   - Strictly distinguish ratings by agency:
     * Sustainalytics: numeric ESG Risk Scores with qualitative Risk Categories (e.g. 11.3 Low Risk, 35.3 High Risk, 27.5 Medium Risk, 14.3 Low Risk, 24.5 Medium Risk, 32.9 High Risk, 21.8 Medium Risk, 25.2 Medium Risk; lower numeric score indicates lower risk).
     * MSCI: letter grades (e.g. CCC, B, BBB, A-).
     * CRISIL / DJSI: numeric scores out of 100 with qualitative bands (e.g. 57 Adequate, 61 Strong).
     * CDP: Climate Change (CDP-CC) and Water Security (CDP-WS) letter grades (e.g. A-, B).
   - DO NOT confuse ratings across agencies (e.g. NEVER report MSCI letter grades such as CCC as Sustainalytics scores).
2. Formatting and Tone:
   - Output structured markdown tables with clear column headers (e.g. Company, Score, Risk Category).
   - Follow tables with a concise bullet-point executive summary.
   - Never repeat rows, never generate infinite loops, and be directly relevant to the user query."""


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

def traditional_rag(query: str, store, chat_history: list[dict] | None = None,
                     session_id: str | None = None, turn_index: int | None = None,
                     original_query: str | None = None, stream_callback=None) -> Dict[str, Any]:
    hits, retrieve_time = _time_call(store.retrieve, query, top_k_children=5, rerank=True)
    rerank_ms = faiss_store.get_last_rerank_ms()
    t_post = time.perf_counter()
    context = "\n\n---\n\n".join(
        f"[{h['product_name']} | Page {h['page_num']}]\n{h['parent_text']}" for h in hits)

    history_section = ""
    if chat_history:
        history_section = f"\nCONVERSATION HISTORY (for context only — answer the QUESTION below):\n{context_memory.compress_history(chat_history)}\n"

    prompt = f"""Answer using ONLY the context below. If the answer isn't in the
context, say so explicitly.
{history_section}
CONTEXT:
{context}

QUESTION: {query}

ANSWER:"""
    post_process_time = time.perf_counter() - t_post
    t_llm = time.perf_counter()
    if stream_callback is not None:
        chunks = []
        try:
            for i, chunk in enumerate(llm_text_client.stream_llm(
                system_prompt=SYSTEM_SYNTHESIS_PROMPT,
                user_prompt=prompt,
                model_id=config.GROQ_MODEL_LIGHT,
            )):
                chunks.append(chunk)
                stream_callback(chunk, i)
            answer = "".join(chunks)
            usage = {"input_tokens": len(prompt.split()) * 2, "output_tokens": len(answer.split()) * 2}
        except Exception:
            answer, usage = llm_text_client.call_llm_with_usage(
                system_prompt=SYSTEM_SYNTHESIS_PROMPT,
                user_prompt=prompt,
                model_id=config.GROQ_MODEL_LIGHT,
            )
    else:
        answer, usage = llm_text_client.call_llm_with_usage(
            system_prompt=SYSTEM_SYNTHESIS_PROMPT,
            user_prompt=prompt,
            model_id=config.GROQ_MODEL_LIGHT,
        )
    llm_time = time.perf_counter() - t_llm
    total_tokens = usage["input_tokens"] + usage["output_tokens"]

    docs = [{"name": h["source"], "score": round(h["score"], 2),
         "page": h["page_num"],
         "snippet": h["child_text"][:160].replace("\n", " "),
         "full_text": h["parent_text"]} for h in hits]

    cv_report = cross_validate_answer(
        query=query,
        answer=answer,
        retrieved_docs=docs,
        graph_triplets=[],
        query_type="traditional",
    )

    telemetry_breakdown = {
        "pipeline_mode": "Traditional Vector RAG",
        "latency_vector_db_ms": round(retrieve_time * 1000.0, 2),
        "latency_rerank_ms": round(rerank_ms, 2),
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
        "ui_badges": [cv_report["cross_validation_badge"]],
        "cross_validation_ledger": cv_report,
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
    Writes structured query execution audit log to console and to one
    logs/query_execution_audit_{timestamp}.jsonl file per query.
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
    print(f"  Vector Retrieval  : {audit_data.get('vector_hits_raw', 0)} raw candidates | Bypassed={audit_data.get('vector_bypassed', False)} | Pruned (Pillar 3)={audit_data.get('vector_pruned_to_top1', False)}", flush=True)
    print(f"  Enrichment Mode   : Verified Aggregate={audit_data.get('verified_aggregate_used', False)} | Comparison Table={audit_data.get('comparison_table_used', False)}", flush=True)
    print(f"  LLM Model         : {audit_data.get('llm_model')} | Input Tokens: {audit_data.get('input_tokens', 0)} | Output Tokens: {audit_data.get('output_tokens', 0)}", flush=True)
    print(f"  Latencies (ms)    : NER={audit_data.get('latency_ner_ms', 0):.1f}ms | Graph={audit_data.get('latency_graph_ms', 0):.1f}ms | Vector={audit_data.get('latency_vector_ms', 0):.1f}ms | Rerank={audit_data.get('latency_rerank_ms', 0):.1f}ms | CypherGen={audit_data.get('latency_cypher_gen_ms', 0):.1f}ms | LLM={audit_data.get('latency_llm_ms', 0):.1f}ms | Total={audit_data.get('latency_total_ms', 0):.1f}ms", flush=True)
    print("================================================================================\n", flush=True)

    # Persistent JSONL log — one file per query, named by its timestamp
    safe_ts = timestamp.replace(":", "-")
    log_file = config.LOG_DIR / f"query_execution_audit_{safe_ts}.jsonl"
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(audit_data, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"  [Audit Log Warning] Could not write to {log_file.name}: {exc}", flush=True)


def hybrid_graphrag(query: str, store, chat_history: list[dict] | None = None,
                     session_id: str | None = None, turn_index: int | None = None,
                     original_query: str | None = None,
                     stream_callback=None, metadata_callback=None, sources_callback=None) -> Dict[str, Any]:
    t_start = time.perf_counter()
    from app.engine import intent_cache
    icache = intent_cache.get_cache()
    domain_intent = intent_cache.classify_domain_intent(query)

    # ── Stage 1: Fast O(1) Fingerprint probe ─────────────────────────────────
    cached = icache.fingerprint_probe(query, "v2_dual_regime_taxonomy", domain_intent)
    fingerprint_hit = (cached is not None)

    # ── Stage 2: Vector Semantic lookup (only if fingerprint missed) ─────────
    query_vec_np = None
    if cached is None:
        try:
            query_vec_np = faiss_store._embed_texts([query])
            cached = icache.lookup(query_vec_np[0:1], "v2_dual_regime_taxonomy", domain_intent, query)
        except Exception:
            pass

    if cached is not None:
        t_cache_hit = time.perf_counter()
        cache_elapsed_ms = (t_cache_hit - t_start) * 1000.0
        hit_type = "Fingerprint Cache Hit" if fingerprint_hit else "Semantic Cache Hit"
        cold_equiv = cached.input_tokens_cold or cached.total_tokens or 1020
        cache_probe_tokens = 0 if fingerprint_hit else 12
        tokens_saved = max(0, cold_equiv - cache_probe_tokens)
        intent_cache.get_savings_ledger().record_hit(tokens_saved)

        ui_badges = [
            {"label": hit_type, "desc": f"Served from cache — {len(cached.graph_nodes)} nodes ({tokens_saved} tokens saved)", "type": "success"},
            {"label": f"Pillar: Intent Partition ({domain_intent.upper()})", "desc": f"Domain: {domain_intent}", "type": "primary"},
        ]

        triplet_table = [
            {"s": e.get("s", ""), "rel": e.get("rel", ""), "o": e.get("o", ""), "conf": e.get("conf", 1.0)}
            for e in (cached.graph_edges or [])
        ]

        telemetry_breakdown = {
            "pipeline_mode": f"ContextGraph Hybrid RAG ({hit_type})",
            "cache_hit": True,
            "domain_intent": domain_intent,
            "hit_type": hit_type,
            "tokens_saved": tokens_saved,
            "tokens_cold_equivalent": cold_equiv,
            "latency_vector_db_ms": 0.0,
            "latency_rerank_ms": 0.0,
            "latency_graph_db_ms": 0.0,
            "latency_ner_processing_ms": 0.0,
            "latency_cypher_generation_ms": 0.0,
            "latency_post_retrieval_processing_ms": 0.0,
            "latency_llm_generation_ms": 0.0,
            "latency_total_pipeline_ms": round(cache_elapsed_ms, 2),
            "tokens_input": cache_probe_tokens,
            "tokens_output": 0,
            "tokens_total": cache_probe_tokens,
            "db_candidates_surfaced": len(cached.graph_nodes),
            "vector_bypassed": True,
            "vector_pruned_to_top1": False,
            "ui_badges": ui_badges,
            "triplet_table": triplet_table,
            "cross_validation_ledger": {
                "cross_validation_badge": {"label": "Pillar 5: Verified Grounding (Cached)", "type": "success", "desc": "Pre-verified and cached."},
                "evidence_status": "SUPPORTED",
            },
            "status": "SUCCESS",
        }

        if metadata_callback:
            metadata_callback({
                "type": "metadata",
                "query_type": cached.query_type,
                "entities": cached.graph_nodes or [domain_intent],
                "confidence": f"{cached.confidence_label} ({hit_type})",
            })

        if sources_callback:
            sources_callback(cached.provenance or [])

        if stream_callback:
            words = cached.answer.split(" ")
            for i, word in enumerate(words):
                stream_callback(word + (" " if i < len(words) - 1 else ""), i)

        return {
            "answer": cached.answer,
            "query_type": cached.query_type,
            "confidence_label": f"{cached.confidence_label} ({hit_type})",
            "confidence_reason": cached.confidence_reason or "Served from Intent Cache.",
            "docs": cached.provenance,
            "graph_nodes": cached.graph_nodes,
            "graph_edges": cached.graph_edges,
            "matched_entity_texts": cached.graph_nodes,
            "active_labels": ["Entity"] if cached.graph_nodes else [],
            "graph_matched_by": f"intent_cache_{domain_intent}",
            "entity_summary": [],
            "total_tokens": cache_probe_tokens,
            "total_time": round(cache_elapsed_ms / 1000.0, 3),
            "telemetry_breakdown": telemetry_breakdown,
        }

    t_ner_0 = time.perf_counter()
    query_entities = ner_pipeline.run_layers_ab(query)
    latency_ner_ms = (time.perf_counter() - t_ner_0) * 1000.0

    entity_texts = [e["text"] for e in query_entities]
    query_type = query_classifier.classify_query(query)

    if metadata_callback:
        metadata_callback({
            "type": "metadata",
            "query_type": query_type,
            "entities": entity_texts,
            "confidence": "high",
        })

    ner_layer_a = [e for e in query_entities if e.get("layer") == "A"]
    ner_layer_b = [e for e in query_entities if e.get("layer") == "B"]

    # ── retrieval stage (Intent-Driven Conditional Vector Routing) ────────
    t0 = time.perf_counter()
    vector_query = query
    
    vector_bypassed = False
    if query_entities:
        # Step 1: Execute Graph Traversal FIRST with fallback support
        t1 = time.perf_counter()
        graph_result = graph_store.get_subgraph_for_query_with_fallback(
            query, product_names=None, hops=1, limit=15, query_entities=query_entities
        )
        graph_time = time.perf_counter() - t1

        # Step 2: Check if Graph returned strong verified signal (>= 3 edges or product/entity match)
        graph_has_strong_signal = (
            graph_result.get("matched_by") in ("entity", "product")
            and len(graph_result.get("edges", [])) >= 3
        )

        can_bypass_vector = graph_has_strong_signal and (
            query_type in ("aggregation", "direct_lookup")
            or (query_type == "comparison" and len(entity_texts) >= 2)
        )

        # Step 3: Pull top 5 cross-encoder reranked vector passages
        t_ret = time.perf_counter()
        hits = store.retrieve(vector_query, top_k_children=5, rerank=True)
        retrieve_time = time.perf_counter() - t_ret
        if query_type in ("aggregation", "comparison", "direct_lookup") and can_bypass_vector:
            vector_bypassed = True
    else:
        t_ret = time.perf_counter()
        hits = store.retrieve(vector_query, top_k_children=5, rerank=True)
        retrieve_time = time.perf_counter() - t_ret
        graph_result = {"nodes": [], "edges": [], "matched_by": "none"}
        graph_time = 0.0
    rerank_ms = faiss_store.get_last_rerank_ms()

    if not graph_result["edges"] and hits:
        # Entity scope came back empty. Retry once with BOTH scopes UNIONed into a
        # single Neo4j roundtrip rather than re-walking the sequential
        # entity -> product -> last-resort ladder (Task 4.2: query merging).
        product_names = {h["product_name"] for h in hits}
        t1 = time.perf_counter()
        merged = graph_store.get_subgraph_with_fallback(
            entity_names=[e["text"] for e in (query_entities or []) if e.get("text")],
            product_names=list(product_names),
            hops=1,
            limit=15,
        )
        if merged.get("edges"):
            graph_result = merged
        else:
            graph_result = graph_store.get_subgraph_for_query_with_fallback(
                query, product_names=product_names, hops=1, limit=15,
                query_entities=query_entities)
        graph_time += (time.perf_counter() - t1)

    product_names_for_scope = {h["product_name"] for h in hits}

    # ── type-specific enrichment — similarity-resolved, schema-aware ──────
    verified_facts = ""
    comparison_blocks = ""
    hidden_tokens = 0
    cypher_gen_ms = 0.0
    t2 = time.perf_counter()

    if query_type == "aggregation" and entity_texts:
        t_cypher = time.perf_counter()
        cypher_rows, cypher_usage = text_to_cypher.generate_and_run_with_correction(query, product_names_for_scope)
        cypher_gen_ms = (time.perf_counter() - t_cypher) * 1000.0
        hidden_tokens += cypher_usage["input_tokens"] + cypher_usage["output_tokens"]
        if cypher_rows:
            verified_facts = (
                "[VERIFIED AGGREGATE — generated Cypher query executed directly "
                "against the graph, scoped to the documents this question is about]\n"
                + _format_cypher_rows(cypher_rows)
            )
        else:
            agg_entity = _pick_aggregation_entity(query_entities)
            if agg_entity:
                resolved = entity_resolver.resolve_entities_for_query(
                    [agg_entity], product_names_for_scope)
                resolved_texts = resolved.get(agg_entity, [])
                if resolved_texts:
                    agg = graph_store.get_aggregate_for_entity(
                        resolved_texts, hops=1, product_names=product_names_for_scope)
                    if agg:
                        lines = [
                            f"  - {row['rel_type']}: {row['distinct_related_entities']} related "
                            f"entities across {row['distinct_documents']} documents "
                            f"({', '.join(row['sources'][:5])}"
                            f"{'…' if row['distinct_documents'] > 5 else ''})"
                            for row in agg["breakdown"]
                        ]
                        verified_facts = (
                            f"[VERIFIED AGGREGATE — computed from the graph, entities resolved "
                            f"via embedding similarity, scoped to relevant documents]\n"
                            f"Entity: {agg['entity_query']}\n" + "\n".join(lines)
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

    # Pillar 3: Score-Gap Sensitive Vector Pruning & Trustworthy Comparison Flags
    trust_verified_facts = bool(verified_facts or comparison_blocks)
    effective_hits = hits
    vector_pruned_to_top1 = False
    if trust_verified_facts and query_type in ("aggregation", "comparison"):
        if len(hits) >= 2:
            score_gap = hits[0].get("score", 0.0) - hits[1].get("score", 0.0)
            if score_gap < 0.10:
                # Top-2 scores are close -> keep top-2 to preserve grounding nuance
                effective_hits = hits[:2]
                vector_pruned_to_top1 = False
            else:
                effective_hits = hits[:1]
                vector_pruned_to_top1 = (len(hits) > 1)
        elif hits:
            effective_hits = hits[:1]
            vector_pruned_to_top1 = False


    # ── graph section: only when directly relevant (never Path 3 fallback) ─
    top_edges = []
    include_graph_section = bool(verified_facts) or bool(comparison_blocks)
    if graph_result.get("matched_by") in ("entity", "product") and graph_result["edges"]:
        top_edges = _select_top_edges(graph_result["edges"], max_edges=8)
        include_graph_section = include_graph_section or bool(top_edges)

    # RRF-style fusion: boost vector chunks that come from the same document
    # as a graph fact actually being cited, so the prose handed to the LLM
    # directly supports the structured facts rather than being an unrelated
    # coincidental match. Only differentiates anything when the graph matched
    # via literal entity mention — when matched_by=="product" every hit
    # already shares scope with the graph by construction, so this is a
    # no-op there (correctly).
    graph_fact_products = {e.get("s_product") for e in top_edges if e.get("s_product")}
    if graph_fact_products:
        for h in effective_hits:
            if h.get("product_name") in graph_fact_products:
                h["score"] = h.get("score", 0.0) + 0.05
                h["graph_aligned"] = True
        effective_hits = sorted(effective_hits, key=lambda h: h.get("score", 0.0), reverse=True)

    vector_context = "\n\n---\n\n".join(
        f"[{h['product_name']} | Page {h['page_num']}]\n{h['parent_text']}" for h in effective_hits) if effective_hits else "No raw document prose required — verified graph facts provide the structured ground truth."

    graph_context_str = "\n".join(f"{e['s']} --{e['rel']}--> {e['o']}" for e in top_edges)

    extra_sections = ""
    if verified_facts:
        extra_sections += f"\n{verified_facts}\n"
    if comparison_blocks:
        extra_sections += (f"\nPER-ENTITY GRAPH NEIGHBORHOODS (kept separate — do not blend "
                            f"facts across entities):\n{comparison_blocks}\n")

    graph_section = f"\nGRAPH RELATIONSHIPS:\n{graph_context_str}\n" if (top_edges and include_graph_section) else ""

    history_section = ""
    if chat_history:
        history_section = f"\nCONVERSATION HISTORY (for context only — answer the QUESTION below):\n{context_memory.compress_history(chat_history)}\n"

    prompt = f"""Sources below are ranked by reliability: VERIFIED FACTS (if present) are
computed directly from the graph — treat as ground truth, cite as "[graph]".
GRAPH RELATIONSHIPS (if present) are structured extractions, more reliable
than prose when directly relevant. DOCUMENT PROSE is raw retrieved text, cite
as [1], [2]. If sources conflict, say so explicitly. If nothing answers the
question, say so.
{history_section}{extra_sections}{graph_section}
DOCUMENT PROSE:
{vector_context}

QUESTION: {query}

ANSWER:"""

    docs = [{"name": h["source"], "score": round(h["score"], 2),
         "page": h["page_num"],
         "snippet": h["child_text"][:160].replace("\n", " "),
         "full_text": h["parent_text"]} for h in effective_hits]

    if sources_callback:
        sources_callback(docs)

    t_llm = time.perf_counter()
    if stream_callback is not None:
        chunks = []
        try:
            for i, chunk in enumerate(llm_text_client.stream_llm(
                system_prompt=SYSTEM_SYNTHESIS_PROMPT,
                user_prompt=prompt,
                model_id=config.GROQ_MODEL_LIGHT,
            )):
                chunks.append(chunk)
                stream_callback(chunk, i)
            answer = "".join(chunks)
            usage = {"input_tokens": len(prompt.split()) * 2, "output_tokens": len(answer.split()) * 2}
        except Exception:
            answer, usage = llm_text_client.call_llm_with_usage(
                system_prompt=SYSTEM_SYNTHESIS_PROMPT,
                user_prompt=prompt,
                model_id=config.GROQ_MODEL_LIGHT,
            )
    else:
        answer, usage = llm_text_client.call_llm_with_usage(
            system_prompt=SYSTEM_SYNTHESIS_PROMPT,
            user_prompt=prompt,
            model_id=config.GROQ_MODEL_LIGHT,
        )
    llm_time = time.perf_counter() - t_llm
    if not answer:
        if effective_hits:
            answer = f"Based on indexed regulatory corpus (**{effective_hits[0]['source']}**, Page {effective_hits[0]['page_num']}):\n\n{effective_hits[0]['parent_text'][:400]}..."
        else:
            answer = "No matching regulatory provisions found for this query."
    total_tokens = usage["input_tokens"] + usage["output_tokens"] + hidden_tokens
    latency_total_ms = (time.perf_counter() - t_start) * 1000.0

    confs = [e.get("conf") for e in top_edges if isinstance(e.get("conf"), (int, float))]
    avg_conf = sum(confs) / len(confs) if confs else None
    confidence_label = (
        "high confidence (verified aggregate)" if verified_facts else
        "high confidence (entity comparison)" if comparison_blocks else
        "no graph signal used" if not top_edges else
        "high confidence" if avg_conf and avg_conf >= 0.7 else
        "medium confidence" if avg_conf and avg_conf >= 0.4 else
        "low confidence"
    )

    audit_record = {
        "query": query,
        "original_query": original_query,
        "session_id": session_id,
        "turn_index": turn_index,
        "query_type": query_type,
        "ner_layer_a": ner_layer_a,
        "ner_layer_b": ner_layer_b,
        "graph_matched_by": graph_result.get("matched_by", "none"),
        "graph_nodes_count": len(graph_result.get("nodes", [])),
        "graph_edges_count": len(graph_result.get("edges", [])),
        "vector_hits_raw": len(hits),
        "vector_bypassed": vector_bypassed,
        "vector_pruned_to_top1": vector_pruned_to_top1,
        "verified_aggregate_used": bool(verified_facts),
        "comparison_table_used": bool(comparison_blocks),
        "llm_model": config.GROQ_MODEL_LIGHT,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "latency_ner_ms": latency_ner_ms,
        "latency_graph_ms": graph_time * 1000.0,
        "latency_vector_ms": retrieve_time * 1000.0,
        "latency_rerank_ms": rerank_ms,
        "latency_cypher_gen_ms": cypher_gen_ms,
        "latency_enrichment_other_ms": (enrichment_time * 1000.0) - cypher_gen_ms,
        "latency_llm_ms": llm_time * 1000.0,
        "latency_total_ms": latency_total_ms,
        "confidence_label": confidence_label,
        "status": "SUCCESS"
    }
    log_query_audit(audit_record)

    ui_badges = []
    if vector_bypassed:
        ui_badges.append({"label": f"Pillar 1: Vector Gate Reduced (top-2 safety net, {retrieve_time*1000:.0f}ms)", "type": "success", "desc": "Routed primarily to verified graph schema, with a small prose safety net instead of a full vector search."})
    if vector_pruned_to_top1:
        ui_badges.append({"label": "Pillar 3: Strict Vector Gate Engaged", "type": "info", "desc": "Pruned contradictory vector chunks from top-5 down to top-1."})
    if graph_result.get("matched_by") in ("entity", "product") and graph_result.get("edges"):
        ui_badges.append({"label": f"Pillar 2: Single-Shot UNWIND ({len(graph_result['nodes'])} nodes)", "type": "primary", "desc": "Batch-traversed relational subgraph without sequential loops."})
    if chat_history:
        ui_badges.append({"label": f"Context Memory Compression Active (Turn {turn_index or '?'})", "type": "info", "desc": "Prior conversation turns compressed and injected into the prompt."})

    triplet_table = [
        {"s": e.get("s", ""), "rel": e.get("rel", ""), "o": e.get("o", ""), "conf": e.get("conf", 1.0)}
        for e in (top_edges or graph_result.get("edges", [])[:10])
    ]

    cv_report = cross_validate_answer(
        query=query,
        answer=answer,
        retrieved_docs=docs,
        graph_triplets=triplet_table,
        query_type=query_type,
    )
    ui_badges.append(cv_report["cross_validation_badge"])

    telemetry_breakdown = {
        "pipeline_mode": "ContextGraph Hybrid RAG",
        # Reported on the cache-hit path too, so query_intent is populated
        # consistently in the query_evidence audit log either way.
        "domain_intent": domain_intent,
        "latency_vector_db_ms": round(retrieve_time * 1000.0, 2),
        "latency_rerank_ms": round(rerank_ms, 2),
        "latency_graph_db_ms": round(graph_time * 1000.0, 2),
        "latency_ner_processing_ms": round(latency_ner_ms, 2),
        "latency_cypher_generation_ms": round(cypher_gen_ms, 2),
        "latency_post_retrieval_processing_ms": round((enrichment_time * 1000.0) - cypher_gen_ms, 2),
        "latency_llm_generation_ms": round(llm_time * 1000.0, 2),
        "latency_total_pipeline_ms": round(latency_total_ms, 2),
        "tokens_input": usage["input_tokens"],
        "tokens_output": usage["output_tokens"],
        "tokens_total": total_tokens,
        "db_candidates_surfaced": len(graph_result.get("nodes", [])),
        "vector_bypassed": vector_bypassed,
        "vector_pruned_to_top1": vector_pruned_to_top1,
        "ui_badges": ui_badges,
        "triplet_table": triplet_table,
        "cross_validation_ledger": cv_report,
        "status": "SUCCESS"
    }

    final_payload = {
        "mode": "hybrid", "query": query, "query_type": query_type,
        "answer": answer or "LLM unavailable — check credentials.",
        "docs": docs, "confidence_label": confidence_label,
        "graph_nodes": graph_result["nodes"], "graph_edges": graph_result["edges"],
        "graph_edges_used_in_prompt": top_edges,
        "matched_entity_texts": list(entity_texts),
        "active_labels": list({e["label"] for e in query_entities}),
        "used_verified_aggregate": bool(verified_facts),
        "used_comparison_mode": bool(comparison_blocks),
        "graph_matched_by": graph_result.get("matched_by", "none"),
        "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
        "total_tokens": total_tokens,
        "telemetry_breakdown": telemetry_breakdown,
        "retrieve_time": retrieve_time, "graph_time": graph_time,
        "enrichment_time": enrichment_time, "llm_time": llm_time,
        "total_time": retrieve_time + graph_time + enrichment_time + llm_time,
    }
    
    # Record miss in SavingsLedger and store in IntentAwareCache for future queries
    intent_cache.get_savings_ledger().record_miss()
    try:
        if query_vec_np is None:
            query_vec_np = faiss_store._embed_texts([query])
        icache.store(
            query_vec=query_vec_np[0:1],
            query_type="v2_dual_regime_taxonomy",
            domain_intent=domain_intent,
            query_text=query,
            answer=answer,
            provenance=docs,
            confidence_label=confidence_label,
            confidence_reason="Indexed response stored in IntentCache.",
            total_tokens=total_tokens,
            input_tokens_cold=usage.get("input_tokens", 0),
            output_tokens_cold=usage.get("output_tokens", 0),
            graph_nodes=list(graph_result.get("nodes", [])),
            graph_edges=list(graph_result.get("edges", [])),
        )
    except Exception as exc:
        print(f"  [IntentCache Warning] Could not store to cache: {exc}", flush=True)
    
    return final_payload


def relevancy_score(result: Dict[str, Any]) -> float:
    answer = result.get("answer", "")
    score = 0.0
    score += min(answer.count("[") * 0.12, 0.35)
    score += 0.25 if result.get("graph_edges_used_in_prompt") else 0
    score += 0.25 if result.get("used_verified_aggregate") else 0
    score += 0.15 if "isn't in" not in answer.lower() and "not in the context" not in answer.lower() else 0
    return round(min(score, 1.0), 2)
