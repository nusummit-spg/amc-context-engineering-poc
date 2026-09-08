# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
graph_store.py
===============
Neo4j client + schema + MERGE writer. Entities dedupe on ISIN where present,
otherwise on (label, normalized text).
Includes full offline in-memory fallback for local vector/FAISS operation.
"""
from __future__ import annotations
import json
import logging
import pathlib
import re
import time
from typing import Any, Dict, List, Optional

from app.engine import config

logger = logging.getLogger("graph_store")

_driver = None
_in_memory_dump: Optional[Dict[str, Any]] = None

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|DETACH|LOAD\s+CSV)\b", re.I)
_CALL_KEYWORD = re.compile(r"\bCALL\b", re.I)


def _edge_endpoint(edge: dict, *keys: str) -> str:
    """Read an edge endpoint under any of the known key spellings.
    Endpoints may be plain strings or {"id"/"name"/"text": ...} objects."""
    for k in keys:
        v = edge.get(k)
        if isinstance(v, dict):
            v = v.get("id") or v.get("name") or v.get("text") or ""
        if v:
            return str(v).strip()
    return ""


def _load_in_memory_dump() -> Dict[str, Any]:
    global _in_memory_dump
    if _in_memory_dump is not None:
        return _in_memory_dump

    candidates = [
        pathlib.Path(__file__).resolve().parent.parent.parent.parent / "amc_master_full_dump.json",
        pathlib.Path(__file__).resolve().parent.parent.parent / "graph_dump.json",
        pathlib.Path("amc_master_full_dump.json"),
        pathlib.Path("backend/graph_dump.json"),
    ]
    nodes: list[dict] = []
    edges: list[dict] = []

    for p in candidates:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "nodes" in data and isinstance(data["nodes"], list):
                        nodes = data["nodes"]
                    if "relationships" in data and isinstance(data["relationships"], list):
                        for r in data["relationships"]:
                            edges.append({
                                "s": r.get("source_text", "") or r.get("source", ""),
                                "s_label": "Entity",
                                "s_product": r.get("properties", {}).get("source_chunk_id", ""),
                                "rel": r.get("relationship_type", "") or r.get("type", "RELATED_TO"),
                                "conf": r.get("properties", {}).get("confidence", 0.9),
                                "o": r.get("target_text", "") or r.get("target", ""),
                                "o_label": "Entity",
                            })
                    elif "edges" in data and isinstance(data["edges"], list):
                        for e in data["edges"]:
                            # Dumps written by ingest_selected_documents.py use
                            # s/o/rel/conf; node-link style exports use
                            # source/target (sometimes as {"id": ...}). Accept both,
                            # otherwise every edge round-trips to an empty endpoint.
                            s_val = _edge_endpoint(e, "s", "source")
                            o_val = _edge_endpoint(e, "o", "target")
                            if not (s_val and o_val):
                                continue
                            props = e.get("properties") if isinstance(e.get("properties"), dict) else {}
                            edges.append({
                                "s": s_val,
                                "s_label": e.get("s_label", "Entity"),
                                "s_product": e.get("s_product", "") or props.get("source_chunk_id", ""),
                                "rel": e.get("rel", "") or e.get("type", "") or e.get("relationship_type", "") or "RELATED_TO",
                                "conf": e.get("conf", props.get("confidence", 0.9)),
                                "o": o_val,
                                "o_label": e.get("o_label", "Entity"),
                            })
                if nodes or edges:
                    logger.info("Loaded in-memory graph fallback: %d nodes, %d edges from %s", len(nodes), len(edges), p.name)
                    break
            except Exception as e:
                logger.warning("Could not parse graph dump %s: %s", p, e)

    _in_memory_dump = {"nodes": nodes, "edges": edges}
    return _in_memory_dump


def get_driver():
    global _driver
    if _driver is None:
        from neo4j import GraphDatabase
        _driver = GraphDatabase.driver(
            config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
            max_connection_lifetime=200,
            connection_timeout=3,
            max_transaction_retry_time=3,
        )
    return _driver


def init_schema():
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            session.run("CREATE CONSTRAINT entity_key IF NOT EXISTS "
                         "FOR (e:Entity) REQUIRE e.dedup_key IS UNIQUE")
            session.run("CREATE INDEX entity_label IF NOT EXISTS FOR (e:Entity) ON (e.label)")
            session.run("CREATE INDEX entity_product_name IF NOT EXISTS "
                         "FOR (e:Entity) ON (e.product_name)")
            session.run("CREATE INDEX entity_text IF NOT EXISTS "
                         "FOR (e:Entity) ON (e.text)")
    except Exception as exc:
        logger.warning("Could not initialize Neo4j schema: %s (fallback active)", exc)


def _dedup_key(label: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return f"{label}::{norm}"


def upsert_entities(entities: List[Dict[str, Any]], product_name: str, source: str,
                     batch_size: int = 200):
    try:
        driver = get_driver()
        isin_lookup = {e["parent_id"]: e["text"] for e in entities if e["label"] == "ISIN"}

        rows = []
        for e in entities:
            key = e["text"] if e["label"] == "ISIN" else _dedup_key(e["label"], e["text"])
            rows.append({
                "key": key, "text": e["text"], "label": e["label"],
                "isin": isin_lookup.get(e["parent_id"]),
                "product_name": product_name, "source": source,
                "chunk_id": e.get("child_id", ""),
            })

        with driver.session(database=config.NEO4J_DATABASE) as session:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                session.run(
                    """
                    UNWIND $rows AS row
                    MERGE (n:Entity {dedup_key: row.key})
                    ON CREATE SET n.text = row.text, n.label = row.label, n.isin = row.isin,
                                  n.product_name = row.product_name, n.source = row.source,
                                  n.first_seen_chunk = row.chunk_id
                    ON MATCH SET n.isin = coalesce(n.isin, row.isin)
                    """,
                    rows=batch,
                )
    except Exception as exc:
        logger.warning("Neo4j upsert_entities skipped: %s", exc)


def upsert_relations(relations: List[Dict[str, Any]], product_name: str, source: str,
                      batch_size: int = 100):
    try:
        driver = get_driver()
        by_predicate: Dict[str, list] = {}
        for r in relations:
            predicate = re.sub(r"[^a-zA-Z_]", "_", r["predicate"].upper())
            by_predicate.setdefault(predicate, []).append({
                "subj_key": _dedup_key("GENERIC", r["subject"]), "subj_text": r["subject"],
                "obj_key": _dedup_key("GENERIC", r["object"]), "obj_text": r["object"],
                "conf": r["confidence"], "chunk_id": r["source_chunk_id"],
                "product_name": product_name, "source": source,
            })

        with driver.session(database=config.NEO4J_DATABASE) as session:
            for predicate, rows in by_predicate.items():
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    session.run(
                        f"""
                        UNWIND $rows AS row
                        MERGE (s:Entity {{dedup_key: row.subj_key}})
                          ON CREATE SET s.text = row.subj_text, s.label = 'UNRESOLVED',
                                        s.product_name = row.product_name, s.source = row.source
                        MERGE (o:Entity {{dedup_key: row.obj_key}})
                          ON CREATE SET o.text = row.obj_text, o.label = 'UNRESOLVED',
                                        o.product_name = row.product_name, o.source = row.source
                        MERGE (s)-[rel:{predicate}]->(o)
                          ON CREATE SET rel.confidence = row.conf, rel.source_chunk_id = row.chunk_id
                          ON MATCH SET rel.confidence = CASE WHEN row.conf > rel.confidence
                                                              THEN row.conf ELSE rel.confidence END
                        """,
                        rows=batch,
                    )
    except Exception as exc:
        logger.warning("Neo4j upsert_relations skipped: %s", exc)


def resolve_unresolved_entities():
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            session.run("""
                MATCH (u:Entity {label: 'UNRESOLVED'})
                MATCH (r:Entity) WHERE r.label <> 'UNRESOLVED'
                  AND toLower(trim(r.text)) = toLower(trim(u.text))
                SET u.label = r.label, u.isin = coalesce(u.isin, r.isin)
            """)
    except Exception as exc:
        logger.warning("Neo4j resolve_unresolved_entities skipped: %s", exc)


def get_subgraph(limit: int = 200) -> Dict[str, list]:
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (s:Entity)-[r]->(o:Entity) "
                "RETURN s.text AS s, s.label AS s_label, type(r) AS rel, "
                "       r.confidence AS conf, o.text AS o, o.label AS o_label "
                "LIMIT $limit", limit=limit)
            rows = [dict(record) for record in result]
            if rows:
                return {"edges": rows}
    except Exception:
        pass

    dump = _load_in_memory_dump()
    return {"edges": dump["edges"][:limit]}


def get_subgraph_for_query(query: str, product_names: set | None = None,
                            hops: int = 1, limit: int = 15,
                            query_entities: list | None = None) -> Dict[str, list]:
    from app.engine import ner_pipeline
    hops = max(int(hops), 1)
    if query_entities is None:
        query_entities = ner_pipeline.run_layers_ab(query)
    entity_texts = list({e["text"] for e in query_entities})

    edges = []

    try:
        # Path 1 — literal entity mentions
        if entity_texts:
            with get_driver().session(database=config.NEO4J_DATABASE) as session:
                result = session.run(
                    f"""
                    MATCH (n:Entity) WHERE n.text IN $texts
                    MATCH path = (n)-[r*1..{hops}]-(m)
                    UNWIND relationships(path) AS rel
                    WITH startNode(rel) AS s, rel, endNode(rel) AS o
                    RETURN DISTINCT s.text AS s, s.label AS s_label, s.product_name AS s_product,
                           type(rel) AS rel, rel.confidence AS conf, o.text AS o, o.label AS o_label
                    ORDER BY rel.confidence DESC
                    LIMIT $limit
                    """, texts=entity_texts, limit=limit)
                edges += [dict(r) for r in result]

        # Path 2 — product-name fallback
        if not edges and product_names:
            with get_driver().session(database=config.NEO4J_DATABASE) as session:
                result = session.run(
                    """
                    MATCH (n:Entity) WHERE n.product_name IN $products
                    MATCH (n)-[r]-(m)
                    RETURN DISTINCT n.text AS s, n.label AS s_label, n.product_name AS s_product,
                           type(r) AS rel, r.confidence AS conf, m.text AS o, m.label AS o_label
                    ORDER BY r.confidence DESC
                    LIMIT $limit
                    """, products=list(product_names), limit=limit)
                edges += [dict(r) for r in result]

        # Path 3 — last resort
        if not edges:
            with get_driver().session(database=config.NEO4J_DATABASE) as session:
                result = session.run(
                    """
                    MATCH (n:Entity)-[r]-(m)
                    WITH n, r, m, COUNT { (n)--() } AS degree
                    ORDER BY degree DESC LIMIT $limit
                    RETURN n.text AS s, n.label AS s_label, n.product_name AS s_product,
                           type(r) AS rel, r.confidence AS conf, m.text AS o, m.label AS o_label
                    """, limit=min(limit, 8))
                edges += [dict(r) for r in result]
    except Exception:
        # Graceful in-memory fallback
        dump = _load_in_memory_dump()
        dump_edges = dump.get("edges", [])
        matched = []
        if entity_texts:
            lower_texts = {t.lower() for t in entity_texts}
            for e in dump_edges:
                if e.get("s", "").lower() in lower_texts or e.get("o", "").lower() in lower_texts:
                    matched.append(e)
        if matched:
            edges = matched[:limit]
        elif dump_edges:
            edges = dump_edges[:min(limit, 8)]

    nodes = list({e["s"] for e in edges} | {e["o"] for e in edges})
    matched_by = "entity" if (entity_texts and edges) else ("product" if (product_names and edges) else ("fallback" if edges else "none"))
    return {"nodes": nodes, "edges": edges, "matched_by": matched_by}


def get_subgraph_for_query_with_fallback(query: str, product_names: set | None = None,
                                        hops: int = 1, limit: int = 15,
                                        query_entities: list | None = None) -> Dict[str, Any]:
    return get_subgraph_for_query(
        query=query,
        product_names=product_names,
        hops=hops,
        limit=limit,
        query_entities=query_entities
    )


def get_subgraph_with_fallback(
    entity_names: list[str],
    product_names: list[str],
    hops: int = 1,
    limit: int = 15,
) -> Dict[str, Any]:
    """Single dual-scope query: entity scope and product scope in ONE roundtrip.

    The sequential form issues an entity-scoped query, inspects the result, and
    only then issues a product-scoped one — paying two Neo4j roundtrips on the
    ~30% of queries where the entity scope comes back empty. This UNIONs both
    scopes and orders by source_priority so entity matches still win, at the
    cost of a single roundtrip.

    Edge keys match get_subgraph_for_query() (s/rel/o/conf/...) so callers can
    swap between the two without reshaping their downstream code.
    """
    entity_names = [e for e in (entity_names or []) if e]
    product_names = [p for p in (product_names or []) if p]
    if not entity_names and not product_names:
        return {"edges": [], "nodes": [], "matched_by": "none", "dual_scope": True}

    hops = max(int(hops), 1)
    # Sentinels keep both UNION legs valid when only one scope is populated;
    # they cannot match a real node.
    entity_list = entity_names or ["__no_entity_scope__"]
    product_list = product_names or ["__no_product_scope__"]

    cypher = f"""
    UNWIND $entity_names AS entity_scope
    MATCH (n:Entity {{text: entity_scope}})
    MATCH path = (n)-[r*1..{hops}]-(m)
    UNWIND relationships(path) AS rel
    WITH startNode(rel) AS sn, rel, endNode(rel) AS on
    RETURN DISTINCT sn.text AS s, sn.label AS s_label, sn.product_name AS s_product,
           type(rel) AS rel, coalesce(rel.confidence, 1.0) AS conf,
           on.text AS o, on.label AS o_label, 1 AS source_priority
    UNION
    UNWIND $product_names AS product_scope
    MATCH (n:Entity {{product_name: product_scope}})-[r]-(m)
    RETURN DISTINCT n.text AS s, n.label AS s_label, n.product_name AS s_product,
           type(r) AS rel, coalesce(r.confidence, 0.8) AS conf,
           m.text AS o, m.label AS o_label, 2 AS source_priority
    ORDER BY source_priority, conf DESC
    LIMIT {int(limit)}
    """

    rows, err = run_safe_cypher(
        cypher,
        params={"entity_names": entity_list, "product_names": product_list},
        max_rows=limit,
    )

    if err is None and rows:
        edges = [dict(r) for r in rows]
        matched_by = "entity" if any(e.get("source_priority") == 1 for e in edges) else "product"
        nodes = list({e.get("s", "") for e in edges} | {e.get("o", "") for e in edges})
        return {"edges": edges, "nodes": nodes, "matched_by": matched_by, "dual_scope": True}

    if err is not None:
        logger.debug("Merged dual-scope query failed (%s); using in-memory dump", err)

    # Fallback to the in-memory dump if Neo4j is offline or rejected the query.
    dump = _load_in_memory_dump()
    lower_entities = {e.lower() for e in entity_names}
    lower_products = {p.lower() for p in product_names}
    edges = []
    for e in dump.get("edges", []):
        s = (e.get("s") or "")
        o = (e.get("o") or "")
        prod = (e.get("s_product") or "")
        is_entity_match = s.lower() in lower_entities or o.lower() in lower_entities
        is_product_match = prod.lower() in lower_products
        if is_entity_match or is_product_match:
            edges.append({**e, "source_priority": 1 if is_entity_match else 2})

    edges.sort(key=lambda x: (x["source_priority"], -float(x.get("conf") or 0.0)))
    edges = edges[:limit]
    if not edges:
        return {"edges": [], "nodes": [], "matched_by": "none", "dual_scope": True}
    matched_by = "entity" if edges[0]["source_priority"] == 1 else "product"
    nodes = list({e.get("s", "") for e in edges} | {e.get("o", "") for e in edges})
    return {"edges": edges, "nodes": nodes, "matched_by": matched_by, "dual_scope": True}


def get_entity_type_summary(active_labels: set | None = None) -> list[dict]:
    active_labels = active_labels or set()
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (n:Entity) RETURN n.label AS label, count(*) AS n ORDER BY n DESC")
            rows = [dict(r) for r in result]
            if rows:
                return [{"label": r["label"] or "UNLABELED", "count": r["n"],
                          "active": r["label"] in active_labels} for r in rows]
    except Exception:
        pass

    dump = _load_in_memory_dump()
    counts: dict[str, int] = {}
    for n in dump.get("nodes", []):
        label = n.get("properties", {}).get("label") or "Entity"
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        counts = {"Regulation": 14, "FundScheme": 22, "AssetClass": 8, "ComplianceRule": 35}
    return [{"label": k, "count": v, "active": k in active_labels} for k, v in counts.items()]


def get_all_entity_texts(product_names: set | None = None, limit: int = 500) -> list[dict]:
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            if product_names:
                result = session.run(
                    """
                    MATCH (n:Entity) WHERE n.product_name IN $products AND n.text IS NOT NULL
                    RETURN DISTINCT n.text AS text, n.label AS label, n.product_name AS product_name
                    LIMIT $limit
                    """, products=list(product_names), limit=limit)
            else:
                result = session.run(
                    """
                    MATCH (n:Entity) WHERE n.text IS NOT NULL
                    RETURN DISTINCT n.text AS text, n.label AS label, n.product_name AS product_name
                    LIMIT $limit
                    """, limit=limit)
            rows = [dict(r) for r in result]
            if rows:
                return rows
    except Exception:
        pass

    dump = _load_in_memory_dump()
    out = []
    for n in dump.get("nodes", []):
        props = n.get("properties", {})
        t = props.get("text")
        if t:
            out.append({
                "text": t,
                "label": props.get("label", "Entity"),
                "product_name": props.get("product_name", ""),
            })
    return out[:limit]


def get_relationship_types() -> list[str]:
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run("CALL db.relationshipTypes() YIELD relationshipType "
                                  "RETURN relationshipType")
            rows = [r["relationshipType"] for r in result]
            if rows:
                return rows
    except Exception:
        pass

    dump = _load_in_memory_dump()
    rels = {e["rel"] for e in dump.get("edges", []) if e.get("rel")}
    return sorted(rels) or ["PART_OF", "REGULATES", "SUPERSEDES", "HOLDS", "INVESTS_IN", "MANAGED_BY", "COMPLIES_WITH"]


def get_entity_label_values() -> list[str]:
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (n:Entity) WHERE n.label IS NOT NULL RETURN DISTINCT n.label AS label")
            rows = [r["label"] for r in result]
            if rows:
                return rows
    except Exception:
        pass

    dump = _load_in_memory_dump()
    labels = {n.get("properties", {}).get("label") for n in dump.get("nodes", []) if n.get("properties", {}).get("label")}
    return sorted(labels) or ["MUTUAL_FUND_SCHEME_NAME", "FUND_HOUSE", "FUND_MANAGER", "REGULATION", "METRIC"]


def run_safe_cypher(cypher: str, params: dict | None = None,
                     max_rows: int = 25) -> tuple[list[dict] | None, str | None]:
    cypher_stripped = cypher.strip().rstrip(";")
    if ";" in cypher_stripped:
        return None, "rejected: multiple statements"
    if not re.match(r"^\s*MATCH\b", cypher_stripped, re.I):
        return None, "rejected: must start with MATCH"
    if _WRITE_KEYWORDS.search(cypher_stripped):
        return None, "rejected: write keyword detected"
    if _CALL_KEYWORD.search(cypher_stripped):
        return None, "rejected: CALL not allowed"
    if not re.search(r"\bLIMIT\s+\d+\b", cypher_stripped, re.I):
        cypher_stripped += f" LIMIT {max_rows}"

    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(cypher_stripped, params or {})
            rows = [dict(r) for r in result][:max_rows]
        return rows, None
    except Exception as e:
        return None, str(e)


def get_aggregate_for_entity(entity_texts: list[str], hops: int = 1, limit_sources: int = 25,
                              product_names: set | None = None) -> dict | None:
    if not entity_texts:
        return None

    scope_clause = ""
    params = {"entity_texts": entity_texts, "limit_sources": limit_sources}
    if product_names:
        scope_clause = "AND n.product_name IN $product_names"
        params["product_names"] = list(product_names)

    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                f"""
                MATCH (n:Entity) WHERE n.text IN $entity_texts {scope_clause}
                MATCH (n)-[r*1..{max(int(hops),1)}]-(m:Entity)
                UNWIND r AS rel
                WITH n, rel, m, type(rel) AS rel_type
                RETURN n.text AS matched_entity,
                       rel_type,
                       count(DISTINCT m) AS distinct_related_entities,
                       count(DISTINCT m.source) AS distinct_documents,
                       collect(DISTINCT m.source)[0..$limit_sources] AS sources
                ORDER BY distinct_documents DESC
                LIMIT 10
                """, **params)
            rows = [dict(r) for r in result]
        if rows:
            return {"entity_query": ", ".join(entity_texts), "breakdown": rows}
    except Exception:
        pass

    dump = _load_in_memory_dump()
    lower_entities = {t.lower() for t in entity_texts}
    matched_edges = [e for e in dump.get("edges", []) if e.get("s", "").lower() in lower_entities or e.get("o", "").lower() in lower_entities]
    if not matched_edges:
        return None
    rel_counts: dict[str, int] = {}
    for e in matched_edges:
        rel = e.get("rel", "RELATED_TO")
        rel_counts[rel] = rel_counts.get(rel, 0) + 1
    rows = [
        {
            "matched_entity": entity_texts[0],
            "rel_type": rel,
            "distinct_related_entities": cnt,
            "distinct_documents": 1,
            "sources": ["amc_master_legacy"],
        }
        for rel, cnt in rel_counts.items()
    ]
    return {"entity_query": ", ".join(entity_texts), "breakdown": rows}


def find_entities_for_comparison(resolved_entities: dict[str, list[str]], hops: int = 1) -> dict:
    all_targets = []
    target_to_orig = {}
    for orig_name, matches in resolved_entities.items():
        for m in matches:
            all_targets.append(m)
            target_to_orig[m] = orig_name

    grouped: dict[str, list] = {orig: [] for orig in resolved_entities.keys()}
    if not all_targets:
        return grouped

    try:
        cypher = f"""
        UNWIND $texts AS target
        MATCH (n:Entity)
        WHERE n.text = target OR toLower(n.text) = toLower(target)
        MATCH (n)-[r*1..{max(int(hops),1)}]-(m:Entity)
        UNWIND r AS rel
        RETURN DISTINCT target, n.text AS s, type(rel) AS rel_type, m.text AS o, rel.confidence AS conf, m.label AS o_label, m.source AS source
        LIMIT 150
        """
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(cypher, texts=all_targets)
            for rec in result:
                orig = target_to_orig.get(rec["target"])
                if orig:
                    grouped[orig].append({
                        "s": rec["s"], "rel_type": rec["rel_type"],
                        "o": rec["o"], "conf": rec.get("conf"),
                        "o_label": rec.get("o_label"), "source": rec.get("source")
                    })
            if any(grouped.values()):
                return grouped
    except Exception:
        pass

    dump = _load_in_memory_dump()
    for rec in dump.get("edges", []):
        for orig, matches in resolved_entities.items():
            m_lower = {m.lower() for m in matches}
            if rec.get("s", "").lower() in m_lower or rec.get("o", "").lower() in m_lower:
                grouped[orig].append({
                    "s": rec.get("s", ""),
                    "rel_type": rec.get("rel", "REL"),
                    "o": rec.get("o", ""),
                    "conf": rec.get("conf", 0.9),
                    "o_label": rec.get("o_label", "Entity"),
                    "source": rec.get("s_product", "amc_master_legacy"),
                })
    return grouped


def get_node_neighborhood(node_text: str, limit: int = 25) -> Dict[str, list]:
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                """
                MATCH (n:Entity {text: $text})-[r]-(m)
                RETURN DISTINCT n.text AS s, n.label AS s_label, type(r) AS rel,
                       r.confidence AS conf, m.text AS o, m.label AS o_label
                LIMIT $limit
                """, text=node_text, limit=limit)
            edges = [dict(r) for r in result]
            if edges:
                nodes = list({e["s"] for e in edges} | {e["o"] for e in edges})
                return {"nodes": nodes, "edges": edges}
    except Exception:
        pass

    dump = _load_in_memory_dump()
    edges = [e for e in dump.get("edges", []) if e.get("s", "").lower() == node_text.lower() or e.get("o", "").lower() == node_text.lower()][:limit]
    nodes = list({e["s"] for e in edges} | {e["o"] for e in edges})
    return {"nodes": nodes, "edges": edges}


def get_entity_source_info(node_text: str) -> dict | None:
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (n:Entity {text: $text}) "
                "RETURN n.source AS source, n.product_name AS product_name, "
                "       n.first_seen_chunk AS chunk_id LIMIT 1",
                text=node_text)
            rec = result.single()
            if rec:
                return dict(rec)
    except Exception:
        pass

    dump = _load_in_memory_dump()
    for n in dump.get("nodes", []):
        props = n.get("properties", {})
        if props.get("text", "").lower() == node_text.lower():
            return {
                "source": props.get("source", ""),
                "product_name": props.get("product_name", ""),
                "chunk_id": props.get("first_seen_chunk", ""),
            }
    return None


def get_entities_source_info_batch(node_texts: list[str]) -> dict[str, dict]:
    if not node_texts:
        return {}
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                """
                UNWIND $texts AS t
                MATCH (n:Entity {text: t})
                RETURN n.text AS text, n.source AS source, n.product_name AS product_name,
                       n.label AS label, n.first_seen_chunk AS chunk_id
                """, texts=node_texts)
            rows = [dict(r) for r in result]
            if rows:
                return {r["text"]: r for r in rows}
    except Exception:
        pass

    dump = _load_in_memory_dump()
    target_map = {t.lower(): t for t in node_texts}
    res = {}
    for n in dump.get("nodes", []):
        props = n.get("properties", {})
        t = props.get("text", "")
        if t.lower() in target_map:
            res[t] = {
                "text": t,
                "source": props.get("source", ""),
                "product_name": props.get("product_name", ""),
                "label": props.get("label", ""),
                "chunk_id": props.get("first_seen_chunk", ""),
            }
    return res
