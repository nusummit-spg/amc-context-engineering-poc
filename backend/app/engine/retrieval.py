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
from app.engine import entity_resolver
from app.engine import graph_store
from app.engine import llm_text_client
from app.engine import ner_pipeline
from app.engine import query_classifier
from app.engine import text_to_cypher
from app.engine import context_engineering

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
import re
def traditional_rag(query: str, store) -> Dict[str, Any]:
    period_mentions = len(re.findall(r'\bFY\d{2}\b', query, re.I))
    k = 5 if period_mentions <= 1 else min(5 * period_mentions, 15)
    hits, retrieve_time = _time_call(store.retrieve, query, top_k_children=k)
    context = "\n\n---\n\n".join(
        f"[{h['product_name']} | Page {h['page_num']}]\n{h['parent_text']}" for h in hits)

    prompt = f"""Answer using ONLY the context below. If the answer isn't in the
context, say so explicitly.

CONTEXT:
{context}

QUESTION: {query}

ANSWER:"""
    t_llm = time.perf_counter()
    answer, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
    llm_time = time.perf_counter() - t_llm
    total_tokens = usage["input_tokens"] + usage["output_tokens"]

    docs = [{"name": h["source"], "score": round(h["score"], 2),
         "page": h["page_num"],
         "snippet": h["child_text"][:160].replace("\n", " "),
         "full_text": h["parent_text"]} for h in hits]

    return {
        "mode": "traditional", "query": query,
        "answer": answer or "LLM unavailable — check credentials.",
        "docs": docs,
        "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
        "total_tokens": total_tokens,
        "retrieve_time": retrieve_time, "llm_time": llm_time,
        "total_time": retrieve_time + llm_time,
    }


# ─────────────────────────────────────────────────────────────────────────
# HYBRID
# ─────────────────────────────────────────────────────────────────────────

def hybrid_graphrag(query: str, store) -> Dict[str, Any]:

    query_entities = ner_pipeline.run_layers_ab(query)
    entity_texts = [e["text"] for e in query_entities]
    query_type = query_classifier.classify_query(query)

    # ── retrieval stage ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    period_mentions = len(re.findall(r'\bFY\d{2}\b', query, re.I))
    k = 5 if period_mentions <= 1 else min(5 * period_mentions, 15)
    if query_entities:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fut_hits = ex.submit(store.retrieve, query, top_k_children=k)
            fut_graph = ex.submit(graph_store.get_subgraph_for_query, query,
                                   product_names=None, hops=1, limit=15,
                                   query_entities=query_entities)
            hits = fut_hits.result()
            graph_result = fut_graph.result()
    else:
        hits = store.retrieve(query, top_k_children=k)
        graph_result = {"nodes": [], "edges": [], "matched_by": "none"}
    retrieve_time = time.perf_counter() - t0

    if not graph_result["edges"]:
        product_names = {h["product_name"] for h in hits}
        t1 = time.perf_counter()
        graph_result = graph_store.get_subgraph_for_query(
            query, product_names=product_names, hops=1, limit=15,
            query_entities=query_entities)
        graph_time = time.perf_counter() - t1
    else:
        graph_time = 0.0

    product_names_for_scope = {h["product_name"] for h in hits}

    # ── type-specific enrichment — similarity-resolved, schema-aware ──────
    # ── type-specific enrichment — only attempt when the graph actually has signal ──
    # ── type-specific enrichment — only attempt when the graph actually has signal ──
    verified_facts = ""
    comparison_blocks = ""
    hidden_tokens=0
    verified_facts_trustworthy = False
    t2 = time.perf_counter()

    graph_has_signal = graph_result.get("matched_by") in ("entity", "product") \
        and len(graph_result.get("edges", [])) >= 3

    if graph_has_signal and query_type == "aggregation" and entity_texts:
        cypher_rows, cypher_usage = text_to_cypher.generate_and_run(query, product_names_for_scope)
        hidden_tokens = cypher_usage["input_tokens"] + cypher_usage["output_tokens"]
        if cypher_rows:
            verified_facts = (
                "[VERIFIED AGGREGATE — generated Cypher query executed directly "
                "against the graph, scoped to the documents this question is about]\n"
                + _format_cypher_rows(cypher_rows)
            )
            verified_facts_trustworthy = True
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

    elif graph_has_signal and query_type == "comparison" and len(entity_texts) >= 2:
        resolved = entity_resolver.resolve_entities_for_query(entity_texts, product_names_for_scope)
        per_entity = graph_store.find_entities_for_comparison(resolved, hops=1)
        blocks = []
        for entity, rels in per_entity.items():
            if not rels:
                continue
            top_rels = _select_top_edges(
                [{"s": r["s"], "rel": r["rel_type"], "o": r["o"], "conf": None} for r in rels],
                max_edges=6)
            rel_lines = [f"  {r['s']} --{r['rel']}--> {r['o']}" for r in top_rels]
            blocks.append(f"[{entity}]\n" + "\n".join(rel_lines))
        comparison_blocks = "\n\n".join(blocks)

    else:
        hidden_tokens = 0

    enrichment_time = time.perf_counter() - t2
    top_edges = []
    if not (verified_facts or comparison_blocks) and graph_result.get("matched_by") in ("entity", "product") and graph_result["edges"]:
        top_edges = _select_top_edges(graph_result["edges"], max_edges=5)

    prompt,max_output_tokens= context_engineering.build_prompt(
    query=query, verified_facts=verified_facts, comparison_blocks=comparison_blocks,
    top_edges=top_edges, hits=hits, query_type=query_type,
    trust_verified_facts=verified_facts_trustworthy, total_token_budget=1500)
    if not isinstance(max_output_tokens, int) or max_output_tokens <= 0:
        max_output_tokens = 500

    t_llm = time.perf_counter()
    answer, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT,max_tokens=max_output_tokens)

    llm_time = time.perf_counter() - t_llm
    total_tokens = usage["input_tokens"] + usage["output_tokens"]+hidden_tokens

    print(f"[timing] retrieve={retrieve_time:.2f}s graph={graph_time:.2f}s "
      f"enrichment={enrichment_time:.2f}s llm={llm_time:.2f}s", flush=True)

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
         "full_text": h["parent_text"]} for h in hits]

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
    }


def relevancy_score(result: Dict[str, Any]) -> float:
    answer = result.get("answer", "")
    score = 0.0
    score += min(answer.count("[") * 0.12, 0.35)
    score += 0.25 if result.get("graph_edges_used_in_prompt") else 0
    score += 0.25 if result.get("used_verified_aggregate") else 0
    score += 0.15 if "isn't in" not in answer.lower() and "not in the context" not in answer.lower() else 0
    return round(min(score, 1.0), 2)