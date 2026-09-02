"""
taxonomy_retrieval.py
======================
v2 Hybrid ContextGraph retrieval for the Streamlit UI.
Connects to the Taxonomy Neo4j graph (port 7688) and the
taxonomy_showcase FAISS index (backend/faiss_indexes/taxonomy_showcase/).
"""
import os
import time
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
import logging
logger = logging.getLogger("taxonomy_retrieval")



# ── Fix: Load .env BEFORE importing any module that reads config ──────────────
# We manually parse and inject into os.environ, then patch config directly
# because config.CLAUDE_API_KEY is a module-level string (cached on import).
_env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import config
# Patch the cached module-level string directly so llm_text_client picks it up
if not config.CLAUDE_API_KEY and os.environ.get("CLAUDE_API_KEY"):
    config.CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
    print(f"  [taxonomy] Patched config.CLAUDE_API_KEY from backend/.env", flush=True)

import faiss_store as fs
import llm_text_client

# ── Fix 1: Correct path — prioritize amc_master master index over sample showcase ─
_master_index_dir = Path(__file__).resolve().parent / "faiss_indexes" / "amc_master"
_showcase_index_dir = Path(__file__).resolve().parent.parent / "backend" / "faiss_indexes" / "taxonomy_showcase"
TAXONOMY_INDEX_DIR = _master_index_dir if (_master_index_dir / "index.faiss").exists() else _showcase_index_dir

TAXONOMY_NEO4J_URI = os.environ.get("TAXONOMY_NEO4J_URI", getattr(config, "NEO4J_URI", "bolt://localhost:7687"))
TAXONOMY_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
TAXONOMY_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "Hemant$1234")
TAXONOMY_NEO4J_DB = os.environ.get("NEO4J_DATABASE", "neo4j")


_taxonomy_index = None
_taxonomy_chunks: List[str] = []


def get_taxonomy_index():
    """Load the taxonomy FAISS index once, cache in module globals."""
    global _taxonomy_index, _taxonomy_chunks
    if _taxonomy_index is None:
        import faiss, pickle
        try:
            _taxonomy_index = faiss.read_index(str(TAXONOMY_INDEX_DIR / "index.faiss"), faiss.IO_FLAG_MMAP)
        except Exception:
            _taxonomy_index = faiss.read_index(str(TAXONOMY_INDEX_DIR / "index.faiss"))
        with open(TAXONOMY_INDEX_DIR / "index.pkl", "rb") as f:
            data = pickle.load(f)
            _taxonomy_chunks = data["children"]
        print(f"  [taxonomy] Loaded FAISS index: {_taxonomy_index.ntotal} vectors @ dim={_taxonomy_index.d}")
    return _taxonomy_index, _taxonomy_chunks


_taxonomy_driver = None
_neo4j_disabled = False

def _get_taxonomy_driver():
    global _taxonomy_driver, _neo4j_disabled
    if _neo4j_disabled:
        return None
    if _taxonomy_driver is None:
        try:
            from neo4j import GraphDatabase
            drv = GraphDatabase.driver(
                TAXONOMY_NEO4J_URI, auth=(TAXONOMY_NEO4J_USER, TAXONOMY_NEO4J_PASSWORD),
                max_connection_lifetime=300, connection_timeout=2,
            )
            drv.verify_connectivity()
            _taxonomy_driver = drv
        except Exception as exc:
            logger.info("Neo4j unavailable at %s — bypassing graph layer: %s", TAXONOMY_NEO4J_URI, exc)
            _neo4j_disabled = True
            return None
    return _taxonomy_driver


def close_driver():
    """Safe no-op — driver connection pooling is managed internally by Neo4j driver singleton."""
    pass


_active_sources_cache: set = set()
_active_sources_loaded_at: float = 0.0

def _get_active_sources() -> set:
    global _active_sources_cache, _active_sources_loaded_at
    now = time.time()
    if not _active_sources_cache or (now - _active_sources_loaded_at) > 300:
        try:
            import provenance_ledger
            _active_sources_cache = provenance_ledger.get_active_filenames()
            _active_sources_loaded_at = now
        except Exception:
            _active_sources_cache = set()
    return _active_sources_cache


def retrieve_vector(query: str, index, chunks: List[str], top_k: int = 3, query_vec=None) -> List[dict]:
    """Embed query (or use precomputed query_vec) and return top-k text chunks with real FAISS scores."""
    vecs = query_vec if query_vec is not None else fs._embed_texts([query])
    D, I = index.search(vecs, top_k)
    active_sources = _get_active_sources() if getattr(config, "RETRIEVAL_ACTIVE_ONLY", True) else set()
    
    results = []
    for score, i in zip(D[0], I[0]):
        if i < len(chunks) and float(score) >= 0.35:
            chunk = chunks[i]
            chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
            source_file = chunk.get("source", "") if isinstance(chunk, dict) else ""
            if active_sources and source_file and source_file not in active_sources:
                continue
            results.append({"text": chunk_text, "score": float(score), "source": source_file})
    return results


def retrieve_graph(query: str, query_vec_list: List[float] = None) -> List[dict]:
    """
    Query the Taxonomy Knowledge Graph using native vector
    similarity search plus keyword-conditioned edge traversals.
    Returns a flat list of typed fact dicts (or empty list if Neo4j is offline).
    """
    graph_context: List[dict] = []
    try:
        driver = _get_taxonomy_driver()
        query_lower = query.lower()
        query_vector = query_vec_list if query_vec_list is not None else fs._embed_texts([query])[0].tolist()

        with driver.session(database=TAXONOMY_NEO4J_DB) as s:
            # ── 1. Semantic vector match on SchemeClass nodes ─────────────────
            try:
                r_vec = s.run("""
                    CALL db.index.vector.queryNodes('scheme_class_vector', 5, $vec)
                    YIELD node, score
                    WHERE score >= 0.50
                    MATCH (node)-[r]-(other)
                    RETURN labels(node)[0] AS n_type, node.name AS s, type(r) AS rel,
                           labels(other)[0] AS o_type, coalesce(other.name, other.text) AS o, score
                """, vec=query_vector)
                for rec in r_vec:
                    graph_context.append({
                        "type": "EntityEdge", "s": rec["s"], "rel": rec["rel"], "o": rec["o"],
                        "source": f"VectorMatch ({rec['n_type']}->{rec['o_type']})"
                    })
                
                res = s.run("""
                    CALL db.index.vector.queryNodes('tax_scheme_vector', 5, $query_vector)
                    YIELD node AS sc, score
                    RETURN sc.code AS code, sc.canonical_label AS label,
                           sc.investment_mandate AS mandate, sc.regime_id AS regime, score
                """, query_vector=query_vector)
                matched_codes = []
                for rec in res:
                    graph_context.append({
                        "type": "SchemeClass", "code": rec["code"], "label": rec["label"],
                        "mandate": rec["mandate"], "regime": rec["regime"]
                    })
                    matched_codes.append(rec["code"])

                if matched_codes:
                    res_me = s.run("""
                        UNWIND $codes AS code
                        MATCH (a:SchemeClass {code: code})-[:MUTUALLY_EXCLUSIVE_WITH]-(b:SchemeClass)
                        RETURN a.canonical_label AS from_label, b.canonical_label AS to_label, a.regime_id AS regime
                    """, codes=matched_codes)
                    for rec in res_me:
                        graph_context.append({
                            "type": "MutualExclusion",
                            "from_label": rec["from_label"],
                            "to_label": rec["to_label"],
                            "regime": rec["regime"]
                        })
            except Exception:
                pass  # tax_scheme_vector index not present in this instance — expected

            # ── 1c. Semantic vector match on StructuralChange nodes ───────────
            try:
                res1b = s.run("""
                    CALL db.index.vector.queryNodes('tax_change_vector', 3, $query_vector)
                    YIELD node AS sc, score
                    RETURN sc.description AS desc, score
                """, query_vector=query_vector)
                for rec in res1b:
                    if rec["score"] > 0.50:
                        graph_context.append({"type": "StructuralChange", "desc": rec["desc"]})
            except Exception:
                pass  # tax_change_vector index not present in this instance — expected

            # ── 2. Always include both regulatory regimes for temporal context ─
            try:
                res2 = s.run("""
                    MATCH (rr:RegulatoryRegime)
                    RETURN rr.regime_id AS rid, rr.label AS label,
                           rr.effective_from AS date, rr.status AS status
                """)
                for rec in res2:
                    graph_context.append({
                        "type": "Regime", "rid": rec["rid"], "label": rec["label"],
                        "date": rec["date"], "status": rec["status"]
                    })
            except Exception as exc:
                pass

            # ── 3. Circular & amendment traversal (keyword-conditioned) ────────
            try:
                if any(kw in query_lower for kw in ("circular", "sebi", "amendment", "2026", "2017")):
                    res3 = s.run("""
                        MATCH (c:RegulatoryCircular)-[:AMENDED_BY]->(a:Amendment)
                        RETURN c.circular_id AS cid, c.title AS title,
                               a.circular_id AS amend_cid, a.date AS amend_date,
                               a.change_summary AS change
                        LIMIT 5
                    """)
                    for rec in res3:
                        graph_context.append({
                            "type": "CircularAmendment", "circular": rec["cid"],
                            "title": rec["title"], "amendment_circular": rec["amend_cid"],
                            "amendment_date": rec["amend_date"], "change": rec["change"]
                        })
            except Exception as exc:
                pass

            # ── 4. Entity graph node & edge traversal ──────────────────────
            try:
                res_e = s.run("""
                    MATCH (e1:Entity)-[r]->(e2:Entity)
                    RETURN e1.text AS s, type(r) AS rel, e2.text AS o
                    LIMIT 15
                """)
                for rec in res_e:
                    graph_context.append({
                        "type": "EntityEdge", "s": rec["s"], "rel": rec["rel"], "o": rec["o"]
                    })
            except Exception as exc:
                print(f"  [taxonomy] Entity traversal notice: {exc}", flush=True)



    except Exception as exc:
        print(f"  [taxonomy] Graph DB notice ({TAXONOMY_NEO4J_URI}): {exc}, proceeding with vector context.", flush=True)

    return graph_context


def _graph_context_to_text(graph_context: List[dict]) -> str:
    """Serialise the graph fact list into a compact LLM-readable string."""
    lines, seen = [], set()
    for item in graph_context:
        t = item.get("type", "")
        key = None
        if t == "SchemeClass":
            key = f"SC:{item.get('code')}"
            if key not in seen:
                lines.append(
                    f"SchemeClass [{item.get('regime')}] '{item['label']}': "
                    f"{item.get('mandate','')}"
                )
        elif t == "MutualExclusion":
            key = f"ME:{item.get('from_label')}:{item.get('to_label')}"
            if key not in seen:
                lines.append(
                    f"MutualExclusion [{item.get('regime')}]: "
                    f"'{item['from_label']}' cannot coexist with '{item['to_label']}' in the same AMC."
                )
        elif t == "StructuralChange":
            key = f"SC_CHANGE:{item.get('desc','')[:20]}"
            if key not in seen:
                lines.append(f"Regime Change: {item.get('desc')}")
        elif t == "Regime":
            key = f"RR:{item.get('rid')}"
            if key not in seen:
                lines.append(
                    f"Regime: {item.get('rid')} ({item.get('status')}) — "
                    f"{item.get('label')} | Effective: {item.get('date')}"
                )
        elif t == "CircularAmendment":
            key = f"CA:{item.get('amendment_circular')}"
            if key not in seen:
                lines.append(
                    f"Circular {item.get('circular')} → Amendment {item.get('amendment_circular')} "
                    f"({item.get('amendment_date')}): {item.get('change','')}"
                )
        elif t == "EntityEdge":
            key = f"EE:{item.get('s')}:{item.get('rel')}:{item.get('o')}"
            if key not in seen:
                lines.append(f"Entity Relationship: ({item.get('s')}) -[{item.get('rel')}]-> ({item.get('o')})")
        if key:
            seen.add(key)
    return "\n".join(lines) if lines else "(no graph facts retrieved)"


def _build_entity_summary(graph_context: List[dict], matched_nodes: set) -> List[dict]:
    """Build the entity_summary list that compare_view.py uses for the Ontology panel."""
    from collections import Counter
    label_counts = Counter(item.get("type") for item in graph_context)
    label_map = {
        "SchemeClass": "Scheme Classes",
        "StructuralChange": "Structural Changes",
        "Regime": "Regulatory Regimes",
        "CircularAmendment": "Circulars & Amendments",
        "MutualExclusion": "Mutual Exclusion Rules",
        "EntityEdge": "Portfolio & ESG Entities",
    }

    summary = []
    for label, display in label_map.items():
        count = label_counts.get(label, 0)
        if count > 0:
            summary.append({"label": display, "count": count, "active": count > 0})
    return summary


def traditional_rag_v2(query: str) -> Dict[str, Any]:
    """
    Traditional vector-only retrieval using the taxonomy FAISS index.
    Used for the left (Traditional) panel in Streamlit Compare view.
    Returns same shape as retrieval.traditional_rag() so _to_traditional() adapter works.
    """
    t_start = time.perf_counter()
    index, chunks = get_taxonomy_index()

    hits = retrieve_vector(query, index, chunks, top_k=5)
    hit_texts = [h.get("text", "") if isinstance(h, dict) else h for h in hits]
    context = "\n\n---\n\n".join(hit_texts)

    prompt = (
        "You are an expert on SEBI Mutual Fund Regulations. "
        "Answer using ONLY the context below. If the answer isn't in the context, say so explicitly.\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {query}\n\nANSWER:"
    )
    answer, usage = llm_text_client.call_llm_with_usage(prompt)
    total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    total_time = time.perf_counter() - t_start

    docs = [
        {
            "name": f"Taxonomy Chunk {i+1}",
            "score": float(h.get("score", 0.0)) if isinstance(h, dict) else 0.0,
            "page": 1,
            "snippet": (h.get("text", "") if isinstance(h, dict) else h)[:160].replace("\n", " "),
            "full_text": h.get("text", "") if isinstance(h, dict) else h
        }
        for i, h in enumerate(hits)
    ]

    return {
        "answer": answer,
        "docs": docs,
        "total_tokens": total_tokens,
        "total_time": total_time,
    }


def hybrid_graphrag_v2(query: str, history: List[dict] = None) -> Dict[str, Any]:
    """
    Dual-Regime Hybrid ContextGraph retrieval.
    Fetches from Neo4j (port 7687) via native vector similarity + edge traversal using raw query,
    then blends with FAISS vector chunks into a single grounded LLM prompt.
    """
    t_start = time.perf_counter()
    import pii_scrub
    import compliance_guardrails
    import flashrank_reranker

    # PII Scrubbing with audit metrics
    query, pii_count, pii_types = pii_scrub.scrub_text_with_metrics(query)

    # Compliance Input Guardrail Validation
    input_guard = compliance_guardrails.validate_input_query(query)
    if not input_guard.get("is_safe", True):
        return {
            "answer": f"Query blocked by Compliance Safety Guard: {input_guard.get('risk_flag')}",
            "confidence_label": "BLOCKED", "docs": [], "total_tokens": 0, "total_time": 0.001,
            "telemetry_breakdown": {"status": "BLOCKED", "risk_flag": input_guard.get("risk_flag")}
        }

    index, chunks = get_taxonomy_index()

    import intent_cache
    domain_intent = intent_cache.classify_domain_intent(query)

    # ── Stage B: Fingerprint probe check BEFORE embedding ─────────────────────
    cached = None
    fingerprint_hit = False
    if config.ENABLE_INTENT_CACHE:
        cache = intent_cache.get_cache()
        cached = cache.fingerprint_probe(query, "v2_dual_regime_taxonomy", domain_intent)
        if cached is not None:
            fingerprint_hit = True

    query_vec_np = None
    query_vec_list = None

    if cached is None:
        # Single-pass query embedding only on cache miss or fallback
        query_vec_np = fs._embed_texts([query])
        query_vec_list = query_vec_np[0].tolist()

        if config.ENABLE_INTENT_CACHE:
            cache = intent_cache.get_cache()
            cached = cache.lookup(query_vec_np[0:1], "v2_dual_regime_taxonomy", domain_intent, query)

    # ── IntentCache Hit Processing (Smart Graph Mode & Honest Accounting) ───
    if cached is not None:
        graph_mode = getattr(config, "CACHE_GRAPH_MODE", "smart")
        cached_node_count = cached.graph_node_count or len(cached.graph_nodes or [])
        should_traverse = (
            graph_mode == "live"
            or (graph_mode == "smart" and cached_node_count > 5)
        )

        if should_traverse:
            if query_vec_np is None:
                query_vec_np = fs._embed_texts([query])
                query_vec_list = query_vec_np[0].tolist()
            t_cache_graph = time.perf_counter()
            live_graph_ctx = retrieve_graph(query, query_vec_list=query_vec_list)
            cache_graph_ms = (time.perf_counter() - t_cache_graph) * 1000
            cache_node_names: list = []
            cache_edges: list = []
            for _item in live_graph_ctx:
                if _item.get("type") == "EntityEdge":
                    cache_node_names.extend([_item["s"], _item["o"]])
                    cache_edges.append({"s": _item["s"], "rel": _item["rel"], "o": _item["o"], "conf": 1.0})
            cache_unique_nodes = list(dict.fromkeys(n for n in cache_node_names if n))
            cache_probe_tokens = 12
        else:
            cache_graph_ms = 0.0
            cache_unique_nodes = cached.graph_nodes or []
            cache_edges = cached.graph_edges or []
            cache_probe_tokens = 0 if fingerprint_hit else 12

        cold_equiv = cached.input_tokens_cold or cached.total_tokens or 1020
        tokens_saved = max(0, cold_equiv - cache_probe_tokens)
        intent_cache.get_savings_ledger().record_hit(tokens_saved)

        cache_elapsed_ms = (time.perf_counter() - t_start) * 1000
        hit_type = "Fingerprint Cache Hit" if fingerprint_hit else "Semantic Cache Hit"

        return {
            "answer": cached.answer,
            "query_type": "v2_dual_regime_taxonomy",
            "confidence_label": f"{cached.confidence_label} ({hit_type})",
            "docs": cached.provenance,
            "graph_nodes": cache_unique_nodes,
            "graph_edges": cache_edges,
            "matched_entity_texts": cache_unique_nodes,
            "active_labels": ["Entity"] if cache_unique_nodes else [],
            "graph_matched_by": f"intent_cache_{graph_mode}",
            "entity_summary": [],
            "total_tokens": cache_probe_tokens,
            "total_time": round(cache_elapsed_ms / 1000.0, 3),
            "telemetry_breakdown": {
                "cache_hit": True,
                "domain_intent": domain_intent,
                "live_graph_nodes": len(cache_unique_nodes),
                "latency_graph_db_ms": round(cache_graph_ms, 1),
                "latency_vector_db_ms": 0.0,
                "latency_llm_generation_ms": 0.0,
                "latency_ner_processing_ms": 0.0,
                "latency_post_retrieval_processing_ms": 0.0,
                "latency_total_pipeline_ms": round(cache_elapsed_ms, 1),
                "tokens_input": cache_probe_tokens,
                "tokens_output": 0,
                "tokens_total": cache_probe_tokens,
                "tokens_cold_equivalent": cold_equiv,
                "tokens_saved": tokens_saved,
                "db_candidates_surfaced": len(cache_unique_nodes),
                "vector_bypassed": True,
                "pipeline_mode": f"ContextGraph v2 ({hit_type})",
                "ui_badges": [
                    {"label": hit_type, "desc": f"Served from cache — {len(cache_unique_nodes)} nodes ({tokens_saved} tokens saved)", "type": "success"},
                    {"label": f"Intent: {domain_intent.upper()}", "desc": f"Domain: {domain_intent}", "type": "primary"},
                ],
                "triplet_table": [
                    {"s": e["s"], "rel": e["rel"], "o": e["o"], "conf": e.get("conf", 1.0)}
                    for e in cache_edges
                ],
            }
        }


    t_par = time.perf_counter()
    vec_time_ms = 0.0  # P0-4 Fix: Initialize vec_time_ms to avoid NameError in parallel mode

    if config.ENABLE_PARALLEL_RETRIEVAL:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f_graph = pool.submit(retrieve_graph, query, query_vec_list=query_vec_list)
            f_vec = pool.submit(retrieve_vector, query, index, chunks, top_k=5, query_vec=query_vec_np)
            graph_ctx = f_graph.result()
            raw_hyb_chunks = f_vec.result()
    else:
        graph_ctx = retrieve_graph(query, query_vec_list=query_vec_list)
        raw_hyb_chunks = retrieve_vector(query, index, chunks, top_k=5, query_vec=query_vec_np)

    graph_time_ms = (time.perf_counter() - t_par) * 1000

    # FlashRank Reranker with real FAISS scores (NEW-P1-A Fix)
    structured_hits = [
        {
            "parent_text": c.get("text", "") if isinstance(c, dict) else c,
            "product_name": f"Taxonomy Chunk {i+1}",
            "page_num": 1,
            "score": float(c.get("score", 0.85)) if isinstance(c, dict) else (0.85 - i * 0.05)
        }
        for i, c in enumerate(raw_hyb_chunks)
    ]
    reranked_hits = flashrank_reranker.rerank_passages(query, structured_hits, top_n=3)
    hyb_chunks = [h.get("parent_text", "") for h in reranked_hits]


    graph_str = _graph_context_to_text(graph_ctx)
    vector_context = "\n\n---\n\n".join(hyb_chunks)

    # Format compressed history for intent (P1-7 Fix)
    hist_text = ""
    if history:
        turns = config.INTENT_HISTORY_TURNS.get(domain_intent, 2)
        recent = history[-turns:]
        hist_text = "CONVERSATION HISTORY:\n" + "\n".join(f"{m.get('role','user').upper()}: {m.get('content','')}" for m in recent) + "\n\n"

    # Dynamic domain-based preamble selection (NEW-P2-2 Fix)
    domain_preambles = {
        "sebi_regulation": "You are an expert on SEBI Mutual Fund Regulations.",
        "esg_sustainability": "You are an expert on ESG Sustainability Disclosures and Climate Regulations.",
        "financial_performance": "You are an expert on Financial Performance Metrics and AMC Analytics.",
        "fund_performance": "You are an expert on Mutual Fund Scheme Performance and NAV Analytics.",
        "corporate_governance": "You are an expert on Corporate Governance & Compliance Rules.",
    }
    preamble = domain_preambles.get(domain_intent, "You are an expert on SEBI Mutual Fund Regulations and Enterprise Compliance.")

    # ── Token budget management — cap contexts to reduce LLM input tokens ────
    # Graph facts are concise triplets; 1200 chars ≈ 300 tokens covers 8-10 facts
    graph_str_trimmed = graph_str[:1200] if len(graph_str) > 1200 else graph_str
    # Vector chunks: cap each chunk to 350 chars, use top 2 only after reranking
    trimmed_chunks = [c[:350] for c in hyb_chunks[:2]]
    vector_context_trimmed = "\n\n---\n\n".join(trimmed_chunks)

    prompt = (
        f"{preamble} Answer using Graph Knowledge first, supplemented by Vector Context. "
        "If the answer is not in the context, say so.\n\n"
        f"{hist_text}"
        f"[GRAPH KNOWLEDGE]:\n{graph_str_trimmed}\n\n"
        f"[VECTOR CONTEXT]:\n{vector_context_trimmed}\n\n"
        f"Question: {query}\n\nAnswer:"
    )


    t_llm = time.perf_counter()
    raw_answer, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
    llm_time_ms = (time.perf_counter() - t_llm) * 1000

    # Compliance Output Guardrail Validation
    out_guard = compliance_guardrails.validate_llm_output(raw_answer, prompt, domain_intent)
    answer = out_guard.get("modified_answer", raw_answer)

    total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    total_time_ms = (time.perf_counter() - t_start) * 1000

    # Build Streamlit visualizer data
    node_names: List[str] = []
    edges: List[dict] = []
    labels: List[str] = []

    for item in graph_ctx:
        if item["type"] == "SchemeClass":
            node_names.append(item["label"])
            labels.append("SchemeClass")
        elif item["type"] == "MutualExclusion":
            node_names.extend([item["from_label"], item["to_label"]])
            labels.append("MutualExclusion")
            edges.append({
                "s": item["from_label"], "rel": "MUTUALLY_EXCLUSIVE_WITH",
                "o": item["to_label"], "conf": 1.0
            })
        elif item["type"] == "StructuralChange":
            node_names.append("Structural Change")
            labels.append("StructuralChange")
        elif item["type"] == "Regime":
            node_names.append(item["rid"])
            labels.append("RegulatoryRegime")
        elif item["type"] == "CircularAmendment":
            node_names += [item.get("circular", ""), item.get("amendment_circular", "")]
            labels += ["RegulatoryCircular", "Amendment"]
            edges.append({
                "s": item.get("circular"), "rel": "AMENDED_BY",
                "o": item.get("amendment_circular"), "conf": 1.0
            })
        elif item["type"] == "EntityEdge":
            node_names.extend([item["s"], item["o"]])
            labels.append("Entity")
            edges.append({
                "s": item["s"], "rel": item["rel"],
                "o": item["o"], "conf": 1.0
            })


    for item in graph_ctx:
        if item["type"] == "SchemeClass" and item.get("regime"):
            edges.append({
                "s": item["label"], "rel": "VALID_UNDER",
                "o": item["regime"], "conf": 1.0
            })

    unique_nodes = list(dict.fromkeys(n for n in node_names if n))
    entity_summary = _build_entity_summary(graph_ctx, set(unique_nodes))

    # Dynamic Confidence Label (NEW-P2-3 Fix)
    if len(unique_nodes) >= 3 and len(hyb_chunks) >= 2:
        conf_label = "High Confidence (Dual-Regime Graph + Vector)"
    elif len(unique_nodes) >= 1 or len(hyb_chunks) >= 1:
        conf_label = "Medium Confidence (Partial Graph/Vector Match)"
    else:
        conf_label = "Low Confidence (No Direct Match)"

    # Real Provenance Records (NEW-P1-1 Fix)
    real_provenance = [
        {
            "doc": h.get("product_name", f"Taxonomy Chunk {i+1}"),
            "page": h.get("page_num", 1),
            "score": h.get("flashrank_score", h.get("score", 0.8))
        }
        for i, h in enumerate(reranked_hits)
    ]

    # Store in IntentCache on success (NEW-P0-2 & NEW-P1-1 Fix)
    if answer and config.ENABLE_INTENT_CACHE:
        cache = intent_cache.get_cache()
        cache.store(
            query_vec=query_vec_np[0:1], query_type="v2_dual_regime_taxonomy",
            domain_intent=domain_intent, query_text=query, answer=answer,
            provenance=real_provenance,
            confidence_label=conf_label,
            confidence_reason="Dual-Regime Graph + Vector match", total_tokens=total_tokens,
            input_tokens_cold=usage.get("input_tokens", 0),
            output_tokens_cold=usage.get("output_tokens", 0),
            graph_nodes=unique_nodes,
            graph_edges=edges,
        )
        intent_cache.get_savings_ledger().record_miss()

    return {
        "answer": answer,
        "query_type": "v2_dual_regime_taxonomy",
        "confidence_label": conf_label,
        "docs": [
            {"name": h.get("doc", f"Taxonomy Chunk {i+1}"), "snippet": h.get("doc", "")[:200], "full_text": hyb_chunks[i] if i < len(hyb_chunks) else ""}
            for i, h in enumerate(real_provenance)
        ],

        "graph_nodes": unique_nodes,
        "graph_edges": edges,
        "graph_edges_used_in_prompt": edges,
        "matched_entity_texts": unique_nodes,
        "active_labels": list(set(labels)),
        "graph_matched_by": "vector_similarity (db.index.vector.queryNodes)",
        "used_verified_aggregate": False,
        "used_comparison_mode": False,
        "entity_summary": entity_summary,
        "total_tokens": total_tokens,
        "total_time": total_time_ms / 1000.0,  # seconds — matches _to_hybrid() adapter
        "telemetry_breakdown": {
            "latency_graph_db_ms": round(graph_time_ms, 1),
            "latency_vector_db_ms": round(vec_time_ms, 1),
            "latency_llm_generation_ms": round(llm_time_ms, 1),
            "latency_total_pipeline_ms": round(total_time_ms, 1),
            "latency_ner_processing_ms": 0.0,
            "tokens_input": usage.get("input_tokens", 0),
            "tokens_output": usage.get("output_tokens", 0),
            "tokens_total": total_tokens,
            "pii_entities_scrubbed_count": pii_count,
            "pii_types_found": pii_types,
            "advice_shield_triggered": out_guard.get("advice_shield_triggered", False),
            "db_candidates_surfaced": len(unique_nodes),
            "vector_bypassed": False,
            "pipeline_mode": "ContextGraph v2",
            "ui_badges": [
                {"label": f"LLM Engine: {llm_text_client._resolve_model_and_fallbacks()[0]}", "desc": "LiteLLM Provider", "type": "success"},
                {"label": f"Intent: {domain_intent.upper()}", "desc": f"Domain: {domain_intent}", "type": "primary"},
                {"label": "Dual-Regime Graph", "desc": f"Queried port 7688 — {len(unique_nodes)} nodes matched", "type": "primary"},
            ],
            "triplet_table": [
                {"s": e["s"], "rel": e["rel"], "o": e["o"], "conf": e["conf"]}
                for e in edges
            ],
        },
    }
