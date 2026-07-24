"""
taxonomy_retrieval.py
=======================
Query-time helpers for the dual-regime taxonomy graph + FAISS index, adapted
from the original showcase's multiturn_taxonomy_query.py — same retrieval
logic (native vector-index SchemeClass/StructuralChange routing, the
compact deduplicating graph-context formatter that made its token savings
real), now querying the SAME Neo4j instance and FAISS store convention the
rest of this app already uses, so retrieval.py can call these directly
instead of a standalone script.
"""
from __future__ import annotations

from typing import Any, Dict, List

import config
import faiss_store
import graph_store

_store = None


def _get_taxonomy_store():
    global _store
    if _store is None:
        _store = faiss_store.get_store(config.TAXONOMY_FAISS_SLUG)
    return _store


def retrieve_taxonomy_chunks(query: str, top_k: int = 3) -> List[str]:
    """Top-k parent-text chunks from the taxonomy_showcase FAISS index."""
    try:
        store = _get_taxonomy_store()
    except FileNotFoundError:
        return []
    hits = store.retrieve(query, top_k_children=top_k)
    return [h["parent_text"] for h in hits]


def retrieve_taxonomy_graph(query: str) -> List[Dict[str, Any]]:
    """Native vector-index lookup on SchemeClass/StructuralChange, all
    RegulatoryRegime nodes, and keyword-gated CircularAmendment lookup."""
    graph_context: List[Dict[str, Any]] = []
    query_lower = query.lower()
    query_vector = faiss_store._embed_texts([query])[0].tolist()

    with graph_store.get_driver().session(database=config.NEO4J_DATABASE) as s:
        res = s.run("""
            CALL db.index.vector.queryNodes('tax_scheme_vector', 5, $query_vector)
            YIELD node AS sc, score
            RETURN sc.code AS code, sc.canonical_label AS label, sc.investment_mandate AS mandate, sc.regime_id AS regime
        """, query_vector=query_vector)
        for rec in res:
            graph_context.append({
                "type": "SchemeClass", "code": rec["code"], "label": rec["label"],
                "mandate": rec["mandate"], "regime": rec["regime"],
            })

        res1b = s.run("""
            CALL db.index.vector.queryNodes('tax_change_vector', 3, $query_vector)
            YIELD node AS sc, score
            RETURN sc.description AS desc, score
        """, query_vector=query_vector)
        for rec in res1b:
            if rec["score"] > 0.5:
                graph_context.append({"type": "StructuralChange", "desc": rec["desc"]})

        res2 = s.run("""MATCH (rr:RegulatoryRegime) WHERE rr.source_db = 'taxonomy'
                         RETURN rr.regime_id AS rid, rr.label AS label, rr.effective_from AS date, rr.status AS status""")
        for rec in res2:
            graph_context.append({"type": "Regime", "rid": rec["rid"], "label": rec["label"], "date": rec["date"], "status": rec["status"]})

        if "circular" in query_lower or "sebi" in query_lower:
            res3 = s.run("""MATCH (c:RegulatoryCircular)-[:AMENDED_BY]->(a:Amendment)
                             RETURN c.circular_id AS cid, c.title AS title, a.circular_id AS amend_cid,
                                    a.date AS amend_date, a.change_summary AS change LIMIT 5""")
            for rec in res3:
                graph_context.append({
                    "type": "CircularAmendment", "circular": rec["cid"], "title": rec["title"],
                    "amendment_circular": rec["amend_cid"], "amendment_date": rec["amend_date"], "change": rec["change"],
                })

    return graph_context


def graph_context_to_text(graph_context: List[Dict[str, Any]]) -> str:
    """Compact, deduplicated formatter — this is what keeps the taxonomy
    graph section cheap in tokens instead of dumping raw JSON into the
    prompt (the original showcase's ~500-token -> ~120-token fix)."""
    lines, seen = [], set()
    for item in graph_context:
        t = item.get("type", "")
        key = None
        if t == "SchemeClass":
            key = f"SC:{item.get('code')}"
            if key not in seen:
                lines.append(f"SchemeClass [{item.get('regime')}] '{item['label']}': {item.get('mandate', '')}")
        elif t == "StructuralChange":
            key = f"SC_CHANGE:{(item.get('desc') or '')[:20]}"
            if key not in seen:
                lines.append(f"Regime Change: {item.get('desc')}")
        elif t == "Regime":
            key = f"RR:{item.get('rid')}"
            if key not in seen:
                lines.append(f"Regime: {item.get('rid')} ({item.get('status')}) - {item.get('label')} Effective: {item.get('date')}")
        elif t == "CircularAmendment":
            key = f"CA:{item.get('amendment_circular')}"
            if key not in seen:
                lines.append(f"Circular {item.get('circular')}. Amend: {item.get('change', '')}")
        if key:
            seen.add(key)
    return "\n".join(lines) if lines else ""
