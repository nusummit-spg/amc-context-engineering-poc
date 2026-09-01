# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import json
import sys
import time
from pathlib import Path
import groq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine import config
from app.engine import faiss_store as fs

TAXONOMY_INDEX_DIR = Path(__file__).resolve().parent.parent / "faiss_indexes" / "taxonomy_showcase"
TAXONOMY_NEO4J_URI = "bolt://localhost:7688"
TAXONOMY_NEO4J_USER = "neo4j"
TAXONOMY_NEO4J_PASSWORD = "contextgraph"
TAXONOMY_NEO4J_DB = "neo4j"
GROQ_MODEL = "llama-3.1-8b-instant"

def load_taxonomy_index():
    import faiss, pickle
    index = faiss.read_index(str(TAXONOMY_INDEX_DIR / "index.faiss"))
    with open(TAXONOMY_INDEX_DIR / "index.pkl", "rb") as f:
        data = pickle.load(f)
    return index, data["children"]

def retrieve_vector(query: str, index, chunks, top_k=5):
    vecs = fs._embed_texts([query])
    D, I = index.search(vecs, top_k)
    return [chunks[i] for i in I[0] if i < len(chunks)]

def retrieve_graph(query: str):
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(TAXONOMY_NEO4J_URI, auth=(TAXONOMY_NEO4J_USER, TAXONOMY_NEO4J_PASSWORD))
    graph_context = []
    query_lower = query.lower()
    query_vector = fs._embed_texts([query])[0].tolist()
    with driver.session(database=TAXONOMY_NEO4J_DB) as s:
        # 1. Vector match (SchemeClass)
        res = s.run("""
            CALL db.index.vector.queryNodes('tax_scheme_vector', 5, $query_vector)
            YIELD node AS sc, score
            RETURN sc.code AS code, sc.canonical_label AS label, sc.investment_mandate AS mandate, sc.regime_id AS regime
        """, query_vector=query_vector)
        for rec in res:
            graph_context.append({
                "type": "SchemeClass", "code": rec["code"], "label": rec["label"],
                "mandate": rec["mandate"], "regime": rec["regime"]
            })
            
        # 1b. Vector match (StructuralChange)
        res1b = s.run("""
            CALL db.index.vector.queryNodes('tax_change_vector', 3, $query_vector)
            YIELD node AS sc, score
            RETURN sc.description AS desc, score
        """, query_vector=query_vector)
        for rec in res1b:
            if rec["score"] > 0.5:  # threshold to ensure relevance
                graph_context.append({
                    "type": "StructuralChange", "desc": rec["desc"]
                })
            
        # 2. Fetch Regime context
        res2 = s.run("MATCH (rr:RegulatoryRegime) RETURN rr.regime_id AS rid, rr.label AS label, rr.effective_from AS date, rr.status AS status")
        for rec in res2:
            graph_context.append({"type": "Regime", "rid": rec["rid"], "label": rec["label"], "date": rec["date"], "status": rec["status"]})

        # 3. Circular/Amendments
        if "circular" in query_lower or "sebi" in query_lower:
            res3 = s.run("MATCH (c:RegulatoryCircular)-[:AMENDED_BY]->(a:Amendment) RETURN c.circular_id AS cid, c.title AS title, a.circular_id AS amend_cid, a.date AS amend_date, a.change_summary AS change LIMIT 5")
            for rec in res3:
                graph_context.append({"type": "CircularAmendment", "circular": rec["cid"], "title": rec["title"], "amendment_circular": rec["amend_cid"], "amendment_date": rec["amend_date"], "change": rec["change"]})

    driver.close()
    return graph_context

def _graph_context_to_text(graph_context: list[dict]) -> str:
    lines, seen = [], set()
    for item in graph_context:
        t = item.get("type", "")
        key = None
        if t == "SchemeClass":
            key = f"SC:{item.get('code')}"
            if key not in seen:
                lines.append(f"SchemeClass [{item.get('regime')}] '{item['label']}': {item.get('mandate','')}")
        elif t == "StructuralChange":
            key = f"SC_CHANGE:{item.get('desc')[:20]}"
            if key not in seen:
                lines.append(f"Regime Change: {item.get('desc')}")
        elif t == "Regime":
            key = f"RR:{item.get('rid')}"
            if key not in seen:
                lines.append(f"Regime: {item.get('rid')} ({item.get('status')}) - {item.get('label')} Effective: {item.get('date')}")
        elif t == "CircularAmendment":
            key = f"CA:{item.get('amendment_circular')}"
            if key not in seen:
                lines.append(f"Circular {item.get('circular')}. Amend: {item.get('change','')}")
        if key: seen.add(key)
    return "\n".join(lines) if lines else "(no graph facts retrieved)"

def format_history(history: list[dict]) -> str:
    if not history: return ""
    return "CONVERSATION HISTORY:\n" + "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history]) + "\n\n"

def build_traditional_prompt(query: str, history: list[dict], chunks: list[str]) -> str:
    context = "\n\n---\n\n".join(chunks)
    hist_text = format_history(history)
    return f"""You are an expert on SEBI Mutual Fund Regulations. Answer the question using ONLY the provided context.

{hist_text}Context:
{context}

Question: {query}

Answer:"""

def build_hybrid_prompt(query: str, history: list[dict], chunks: list[str], graph_context: list[dict]) -> str:
    vector_context = "\n\n---\n\n".join(chunks[:3])
    graph_str = _graph_context_to_text(graph_context)
    hist_text = format_history(history)
    return f"""You are an expert on SEBI Mutual Fund Regulations.

{hist_text}[GRAPH KNOWLEDGE]:
{graph_str}

[VECTOR CONTEXT]:
{vector_context}

Question: {query}

Answer using Graph Knowledge first, supplemented by Vector Context. Answer:"""

def call_llm(prompt: str) -> str:
    client = groq.Groq(api_key=config.GROQ_API_KEY)
    msg = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.choices[0].message.content or ""

if __name__ == "__main__":
    import sys
    query = sys.argv[1]
    history_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    history = []
    if history_file and Path(history_file).exists():
        history = json.loads(Path(history_file).read_text())
        
    index, chunks = load_taxonomy_index()
    
    # Traditional
    trad_chunks = retrieve_vector(query, index, chunks, top_k=5)
    trad_prompt = build_traditional_prompt(query, history, trad_chunks)
    trad_answer = call_llm(trad_prompt)
    
    # Hybrid
    hyb_chunks = retrieve_vector(query, index, chunks, top_k=3)
    graph_ctx = retrieve_graph(query)
    hyb_prompt = build_hybrid_prompt(query, history, hyb_chunks, graph_ctx)
    hyb_answer = call_llm(hyb_prompt)
    
    print(json.dumps({
        "traditional_answer": trad_answer,
        "hybrid_answer": hyb_answer,
        "trad_sources": [c[:40] + "..." for c in trad_chunks],
        "hyb_sources": [c[:40] + "..." for c in hyb_chunks],
        "graph_facts": _graph_context_to_text(graph_ctx).split("\n")
    }, indent=2))
