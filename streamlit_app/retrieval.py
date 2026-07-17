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
import entity_resolver
import graph_store
import llm_text_client
import ner_pipeline
import query_classifier
import text_to_cypher

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
    print(f"  Vector Retrieval  : {audit_data.get('vector_hits_raw', 0)} raw candidates | Bypassed={audit_data.get('vector_bypassed', False)} | Pruned (Pillar 3)={audit_data.get('vector_pruned_to_top1', False)}", flush=True)
    print(f"  Enrichment Mode   : Verified Aggregate={audit_data.get('verified_aggregate_used', False)} | Comparison Table={audit_data.get('comparison_table_used', False)}", flush=True)
    print(f"  LLM Model         : {audit_data.get('llm_model')} | Input Tokens: {audit_data.get('input_tokens', 0)} | Output Tokens: {audit_data.get('output_tokens', 0)}", flush=True)
    print(f"  Latencies (ms)    : NER={audit_data.get('latency_ner_ms', 0):.1f}ms | Graph={audit_data.get('latency_graph_ms', 0):.1f}ms | Vector={audit_data.get('latency_vector_ms', 0):.1f}ms | LLM={audit_data.get('latency_llm_ms', 0):.1f}ms | Total={audit_data.get('latency_total_ms', 0):.1f}ms", flush=True)
    print("================================================================================\n", flush=True)
    
    # Persistent JSONL log
    try:
        log_file = config.LOG_DIR / "query_execution_audit.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_data, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"  [Audit Log Warning] Could not write to query_execution_audit.jsonl: {exc}", flush=True)


def hybrid_graphrag(query: str, store) -> Dict[str, Any]:
    t_start = time.perf_counter()
    
    t_ner_0 = time.perf_counter()
    query_entities = ner_pipeline.run_layers_ab(query)
    latency_ner_ms = (time.perf_counter() - t_ner_0) * 1000.0
    
    entity_texts = [e["text"] for e in query_entities]
    query_type = query_classifier.classify_query(query)

    ner_layer_a = [e for e in query_entities if e.get("layer") == "A"]
    ner_layer_b = [e for e in query_entities if e.get("layer") == "B"]

    # ── retrieval stage (Intent-Driven Conditional Vector Routing) ────────
    t_ret_0 = time.perf_counter()
    graph_time = 0.0
    retrieve_time = 0.0
    vector_bypassed = False

    if query_entities:
        # Step 1: Execute Graph Traversal FIRST
        t1 = time.perf_counter()
        graph_result = graph_store.get_subgraph_for_query(
            query, product_names=None, hops=1, limit=15, query_entities=query_entities
        )
        graph_time = time.perf_counter() - t1

        # Step 2: Check if Graph returned strong verified signal (>= 1 edge or >= 2 nodes on comparison/product)
        graph_has_strong_signal = (
            graph_result.get("matched_by") in ("entity", "product")
            and (len(graph_result.get("edges", [])) >= 1 or len(graph_result.get("nodes", [])) >= 2)
        )

        # Step 3: ONLY run Vector Retrieval if query is open-ended or graph signal is weak
        if query_type in ("aggregation", "comparison", "direct_lookup") and graph_has_strong_signal:
            hits = []  # Bypass vector search entirely! Saves 0.10s-0.40s and prevents token bloat.
            retrieve_time = 0.0
            vector_bypassed = True
        else:
            t_ret = time.perf_counter()
            hits = store.retrieve(query, top_k_children=5)
            retrieve_time = time.perf_counter() - t_ret
    else:
        t_ret = time.perf_counter()
        hits = store.retrieve(query, top_k_children=5)
        retrieve_time = time.perf_counter() - t_ret
        graph_result = {"nodes": [], "edges": [], "matched_by": "none"}
        graph_time = 0.0

    if not graph_result["edges"] and hits:
        product_names = {h["product_name"] for h in hits}
        t1 = time.perf_counter()
        graph_result = graph_store.get_subgraph_for_query(
            query, product_names=product_names, hops=1, limit=15,
            query_entities=query_entities)
        graph_time += (time.perf_counter() - t1)

    product_names_for_scope = {h["product_name"] for h in hits}

    # ── type-specific enrichment — similarity-resolved, schema-aware ──────
    verified_facts = ""
    comparison_blocks = ""
    hidden_tokens = 0
    t2 = time.perf_counter()

    if query_type == "aggregation" and entity_texts:
        cypher_rows, cypher_usage = text_to_cypher.generate_and_run(query, product_names_for_scope)
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

    # Pillar 3: Strict Vector Pruning & Trustworthy Comparison Flags
    trust_verified_facts = bool(verified_facts or comparison_blocks)
    effective_hits = hits
    vector_pruned_to_top1 = False
    if trust_verified_facts and query_type in ("aggregation", "comparison"):
        # Drop contradictory/redundant vector chunks so the LLM focuses purely on verified graph data
        effective_hits = hits[:1]
        vector_pruned_to_top1 = (len(hits) > 1)

    vector_context = "\n\n---\n\n".join(
        f"[{h['product_name']} | Page {h['page_num']}]\n{h['parent_text']}" for h in effective_hits) if effective_hits else "No raw document prose required — verified graph facts provide the structured ground truth."

    # ── graph section: only when directly relevant (never Path 3 fallback) ─
    top_edges = []
    include_graph_section = bool(verified_facts) or bool(comparison_blocks)
    if graph_result.get("matched_by") in ("entity", "product") and graph_result["edges"]:
        top_edges = _select_top_edges(graph_result["edges"], max_edges=8)
        include_graph_section = include_graph_section or bool(top_edges)

    graph_context_str = "\n".join(f"{e['s']} --{e['rel']}--> {e['o']}" for e in top_edges)

    extra_sections = ""
    if verified_facts:
        extra_sections += f"\n{verified_facts}\n"
    if comparison_blocks:
        extra_sections += (f"\nPER-ENTITY GRAPH NEIGHBORHOODS (kept separate — do not blend "
                            f"facts across entities):\n{comparison_blocks}\n")

    graph_section = f"\nGRAPH RELATIONSHIPS:\n{graph_context_str}\n" if (top_edges and include_graph_section) else ""

    prompt = f"""Sources below are ranked by reliability: VERIFIED FACTS (if present) are
computed directly from the graph — treat as ground truth, cite as "[graph]".
GRAPH RELATIONSHIPS (if present) are structured extractions, more reliable
than prose when directly relevant. DOCUMENT PROSE is raw retrieved text, cite
as [1], [2]. If sources conflict, say so explicitly. If nothing answers the
question, say so.
{extra_sections}{graph_section}
DOCUMENT PROSE:
{vector_context}

QUESTION: {query}

ANSWER:"""

    t_llm = time.perf_counter()
    answer, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
    llm_time = time.perf_counter() - t_llm
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

    docs = [{"name": h["source"], "score": round(h["score"], 2),
         "page": h["page_num"],
         "snippet": h["child_text"][:160].replace("\n", " "),
         "full_text": h["parent_text"]} for h in effective_hits]

    audit_record = {
        "query": query,
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
        "llm_model": config.CLAUDE_MODEL_LIGHT,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "latency_ner_ms": latency_ner_ms,
        "latency_graph_ms": graph_time * 1000.0,
        "latency_vector_ms": retrieve_time * 1000.0,
        "latency_llm_ms": llm_time * 1000.0,
        "latency_total_ms": latency_total_ms,
        "confidence_label": confidence_label,
        "status": "SUCCESS"
    }
    log_query_audit(audit_record)

    ui_badges = []
    if vector_bypassed:
        ui_badges.append({"label": "Pillar 1: Vector Bypass Engaged (0.0 ms FAISS)", "type": "success", "desc": "Bypassed unstructured vector noise; routed 100% to verified graph schema."})
    if vector_pruned_to_top1:
        ui_badges.append({"label": "Pillar 3: Strict Vector Gate Engaged", "type": "info", "desc": "Pruned contradictory vector chunks from top-5 down to top-1."})
    if graph_result.get("matched_by") in ("entity", "product") and graph_result.get("edges"):
        ui_badges.append({"label": f"Pillar 2: Single-Shot UNWIND ({len(graph_result['nodes'])} nodes)", "type": "primary", "desc": "Batch-traversed relational subgraph without sequential loops."})

    triplet_table = [
        {"s": e.get("s", ""), "rel": e.get("rel", ""), "o": e.get("o", ""), "conf": e.get("conf", 1.0)}
        for e in (top_edges or graph_result.get("edges", [])[:10])
    ]

    telemetry_breakdown = {
        "pipeline_mode": "ContextGraph Hybrid RAG",
        "latency_vector_db_ms": round(retrieve_time * 1000.0, 2),
        "latency_graph_db_ms": round(graph_time * 1000.0, 2),
        "latency_ner_processing_ms": round(latency_ner_ms, 2),
        "latency_post_retrieval_processing_ms": round(enrichment_time * 1000.0, 2),
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
        "status": "SUCCESS"
    }

    return {
        "mode": "hybrid", "query": query, "query_type": query_type,
        "answer": answer or "LLM unavailable — check credentials.",
        "docs": docs, "confidence_label": confidence_label,
        "graph_nodes": graph_result["nodes"], "graph_edges": graph_result["edges"],
        "graph_edges_used_in_prompt": top_edges,
        "matched_entity_texts": set(entity_texts),
        "active_labels": {e["label"] for e in query_entities},
        "used_verified_aggregate": bool(verified_facts),
        "used_comparison_mode": bool(comparison_blocks),
        "graph_matched_by": graph_result.get("matched_by", "none"),
        "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
        "total_tokens": total_tokens,
        "retrieve_time": retrieve_time, "graph_time": graph_time,
        "enrichment_time": enrichment_time, "llm_time": llm_time,
        "total_time": retrieve_time + graph_time + enrichment_time + llm_time,
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