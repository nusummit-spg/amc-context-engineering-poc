"""
graph_store.py
===============
Neo4j client + schema + MERGE writer. Entities dedupe on ISIN where present,
otherwise on (label, normalized text).
"""
from __future__ import annotations
from typing import Any, Dict, List
import re

import config

_driver = None

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|DETACH|LOAD\s+CSV)\b", re.I)
# CALL isn't a write keyword by itself, but Community Edition has no RBAC —
# any authenticated session can invoke admin/procedure calls (e.g.
# dbms.shutdown(), dbms.killQuery()). Since this validator gates
# LLM-generated Cypher on an internet-facing app, block CALL outright rather
# than trying to allow-list safe procedures — the intended feature (simple
# MATCH...RETURN aggregation) never needs it.
_CALL_KEYWORD = re.compile(r"\bCALL\b", re.I)

def get_driver():
    global _driver
    if _driver is None:
        from neo4j import GraphDatabase
        _driver = GraphDatabase.driver(
            config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
            max_connection_lifetime=200,       # recycle connections before Aura drops them
            connection_timeout=30,
            max_transaction_retry_time=30,
        )
def close_driver():
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
        _driver = None


def init_schema():
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        session.run("CREATE CONSTRAINT entity_key IF NOT EXISTS "
                     "FOR (e:Entity) REQUIRE e.dedup_key IS UNIQUE")
        session.run("CREATE INDEX entity_label IF NOT EXISTS FOR (e:Entity) ON (e.label)")
        session.run("CREATE INDEX entity_product_name IF NOT EXISTS "
                     "FOR (e:Entity) ON (e.product_name)")   # ← new
        session.run("CREATE INDEX entity_text IF NOT EXISTS "
                     "FOR (e:Entity) ON (e.text)")


def _dedup_key(label: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return f"{label}::{norm}"


def upsert_entities(entities: List[Dict[str, Any]], product_name: str, source: str,
                     batch_size: int = 200):
    """Batched via UNWIND — avoids hundreds of individual round-trips to Aura."""
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
                ON MATCH SET n.isin = coalesce(n.isin, row.isin),
                              n.product_name = coalesce(n.product_name, row.product_name),
                              n.source = coalesce(n.source, row.source)
                """,
                rows=batch,
            )


def upsert_relations(relations: List[Dict[str, Any]], product_name: str, source: str,
                      batch_size: int = 100):
    """Batched via UNWIND, grouped by predicate (since predicate is used as a
    relationship TYPE and can't be parameterized in Cypher)."""
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

def resolve_unresolved_entities():
    """
    Post-pass: for UNRESOLVED nodes created by relation MERGE (because the
    subject/object text wasn't seen by NER Layer A/B directly), try to match
    them onto an existing resolved Entity node using the indexed dedup_key.
    """
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        session.run("""
            MATCH (u:Entity {label: 'UNRESOLVED'})
            MATCH (r:Entity) WHERE r.label <> 'UNRESOLVED'
              AND r.dedup_key = u.dedup_key
            SET u.label = r.label, u.isin = coalesce(u.isin, r.isin)
        """)


def get_subgraph(limit: int = 200) -> Dict[str, list]:
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        result = session.run(
            "MATCH (s:Entity)-[r]->(o:Entity) "
            "RETURN s.text AS s, s.label AS s_label, type(r) AS rel, "
            "       r.confidence AS conf, o.text AS o, o.label AS o_label "
            "LIMIT $limit", limit=limit)
        rows = [dict(record) for record in result]
    return {"edges": rows}

# graph_store.py — replace get_subgraph_for_query

def get_subgraph_for_query(query: str, product_names: set | None = None,
                            hops: int = 1, limit: int = 15,
                            query_entities: list | None = None) -> Dict[str, list]:
    """
    Three-path fallback ladder, each path progressively less targeted —
    and progressively tighter-capped, since less-targeted results are
    more likely to be noise the LLM will pay tokens to read and ignore.
    """
    import ner_pipeline
    hops = max(int(hops), 1)
    if query_entities is None:
        query_entities = ner_pipeline.run_layers_ab(query)
    entity_texts = list({e["text"] for e in query_entities})

    edges = []
    path_matched = "none"
    # Path 1 — literal entity mentions in the query text.
    if entity_texts:
        try:
            with get_driver().session(database=config.NEO4J_DATABASE) as session:
                result = session.run(
                    f"""
                    MATCH (n:Entity) WHERE n.text IN $texts
                    MATCH path = (n)-[r*1..{hops}]-(m)
                    UNWIND relationships(path) AS rel
                    WITH startNode(rel) AS s, rel, endNode(rel) AS o
                    RETURN DISTINCT s.text AS s, s.label AS s_label, type(rel) AS rel,
                           rel.confidence AS conf, o.text AS o, o.label AS o_label
                    ORDER BY rel.confidence DESC
                    LIMIT $limit
                    """, texts=entity_texts, limit=limit)
                edges += [dict(r) for r in result]
                if edges:
                    path_matched = "entity"
        except Exception as exc:
            print(f"  [graph] Neo4j Path 1 offline: {exc}", flush=True)

    # Path 2 — product-name fallback (what vector search already found).
    if not edges and product_names:
        try:
            with get_driver().session(database=config.NEO4J_DATABASE) as session:
                result = session.run(
                    """
                    MATCH (n:Entity) WHERE n.product_name IN $products
                    MATCH (n)-[r]-(m)
                    RETURN DISTINCT n.text AS s, n.label AS s_label, type(r) AS rel,
                           r.confidence AS conf, m.text AS o, m.label AS o_label
                    ORDER BY r.confidence DESC
                    LIMIT $limit
                    """, products=list(product_names), limit=limit)
                edges += [dict(r) for r in result]
                if edges:
                    path_matched = "product"
        except Exception as exc:
            print(f"  [graph] Neo4j Path 2 offline: {exc}", flush=True)

    nodes = list({e["s"] for e in edges} | {e["o"] for e in edges})
    return {"nodes": nodes, "edges": edges, "matched_by": path_matched}

def get_entity_type_summary(active_labels: set | None = None) -> list[dict]:
    """Real counts per entity label — powers the Ontology View tree.
    active_labels marks which types this specific query's matched entities belong to."""
    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (n:Entity) RETURN n.label AS label, count(*) AS n ORDER BY n DESC")
            rows = [dict(r) for r in result]
        active_labels = active_labels or set()
        return [{"label": r["label"] or "UNLABELED", "count": r["n"],
                  "active": r["label"] in active_labels} for r in rows]
    except Exception:
        return []

def get_all_entity_texts(product_names: set | None = None, limit: int = 500) -> list[dict]:
    """Distinct entity texts — the candidate pool for embedding-based
    similarity matching in entity_resolver.py. Scoped by product_names when
    given, so a candidate pool for one query never leaks into another."""
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
            return [dict(r) for r in result]
    except Exception:
        return []



def get_relationship_types() -> list[str]:
    """Real relationship types present in the graph — fed into the
    text-to-Cypher prompt so the LLM only writes queries against types
    that actually exist."""
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        result = session.run("CALL db.relationshipTypes() YIELD relationshipType "
                              "RETURN relationshipType")
        return [r["relationshipType"] for r in result]


def get_entity_label_values() -> list[str]:
    """Distinct values of the `label` property (SCHEME_NAME, FUND_MANAGER,
    etc.) — NOT Neo4j node labels, since every node here is :Entity."""
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        result = session.run(
            "MATCH (n:Entity) WHERE n.label IS NOT NULL RETURN DISTINCT n.label AS label")
        return [r["label"] for r in result]


def run_safe_cypher(cypher: str, params: dict | None = None,
                     max_rows: int = 25) -> list[dict] | None:
    """
    Executes an LLM-generated Cypher query after validation. Returns None on
    ANY validation or execution failure — callers must treat None as "this
    didn't work, fall back to the deterministic path," never as an error to
    surface directly.

    Validation:
      - single statement only (no ';' mid-string)
      - must start with MATCH
      - no write keywords (CREATE/MERGE/DELETE/SET/REMOVE/DROP/DETACH/LOAD CSV)
      - LIMIT is enforced (added if the LLM forgot it)
    """
    cypher_stripped = cypher.strip().rstrip(";")
    if ";" in cypher_stripped:
        print("  [cypher-guard] rejected: multiple statements", flush=True)
        return None
    if not re.match(r"^\s*(MATCH|CALL)\b", cypher_stripped, re.I):
        print("  [cypher-guard] rejected: must start with MATCH or CALL", flush=True)
        return None
    if getattr(config, "READ_ONLY_MODE", False) and not re.match(r"^\s*(MATCH|CALL)\b", cypher_stripped, re.I):
        print("  [cypher-guard] rejected: READ_ONLY_MODE active — non-MATCH/CALL query prohibited", flush=True)
        return None
    if _WRITE_KEYWORDS.search(cypher_stripped):
        print("  [cypher-guard] rejected: write keyword detected", flush=True)
        return None

    if not re.search(r"\bLIMIT\s+\d+\b", cypher_stripped, re.I):
        cypher_stripped += f" LIMIT {max_rows}"

    try:
        with get_driver().session(database=config.NEO4J_DATABASE) as session:
            rows = session.execute_read(
                lambda tx: [dict(r) for r in tx.run(cypher_stripped, params or {})]
            )[:max_rows]
        return rows
    except Exception as e:
        print(f"  [cypher-guard] execution failed: {e}", flush=True)
        return None
def get_aggregate_for_entity(entity_texts: list[str], hops: int = 1, limit_sources: int = 25,
                              product_names: set | None = None) -> dict | None:
    """
    Deterministic rollup — now takes a LIST of already-resolved exact entity
    texts (from entity_resolver's similarity matching), matched via `IN`,
    NOT a substring CONTAINS on raw query text. This is what prevents a
    generic word like "debt" from silently matching every debt-related node
    across the entire corpus.
    """
    if not entity_texts:
        return None

    scope_clause = ""
    params = {"entity_texts": entity_texts, "limit_sources": limit_sources}
    if product_names:
        scope_clause = "AND n.product_name IN $product_names"
        params["product_names"] = list(product_names)

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
    if not rows:
        return None
    return {"entity_query": ", ".join(entity_texts), "breakdown": rows}

def find_entities_for_comparison(resolved_entities: dict[str, list[str]], hops: int = 1) -> dict:
    """Batch-traverse all comparison entities in a single Neo4j round-trip using UNWIND."""
    all_targets = []
    target_to_orig = {}
    for orig_name, matches in resolved_entities.items():
        for m in matches:
            all_targets.append(m)
            target_to_orig[m] = orig_name

    grouped = {orig: [] for orig in resolved_entities.keys()}
    if not all_targets:
        return grouped

    # Single-shot O(V+E) traversal instead of O(N) Python loops
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
        return grouped

def get_node_neighborhood(node_text: str, limit: int = 25) -> Dict[str, list]:
    """1-hop neighborhood of a single node — powers 'click a node to explore'."""
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        result = session.run(
            """
            MATCH (n:Entity {text: $text})-[r]-(m)
            RETURN DISTINCT n.text AS s, n.label AS s_label, type(r) AS rel,
                   r.confidence AS conf, m.text AS o, m.label AS o_label
            LIMIT $limit
            """, text=node_text, limit=limit)
        edges = [dict(r) for r in result]
    nodes = list({e["s"] for e in edges} | {e["o"] for e in edges})
    return {"nodes": nodes, "edges": edges}

def get_entity_source_info(node_text: str) -> dict | None:
    """Pulls source doc + first-seen chunk id for a node, so the UI can
    show the actual passage the entity came from."""
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        result = session.run(
            "MATCH (n:Entity {text: $text}) "
            "RETURN n.source AS source, n.product_name AS product_name, "
            "       n.first_seen_chunk AS chunk_id LIMIT 1",
            text=node_text)
        rec = result.single()
        return dict(rec) if rec else None
def get_entities_source_info_batch(node_texts: list[str]) -> dict[str, dict]:
    """Source/product/label info for multiple nodes in one round-trip —
    powers the 'why is this node here' detail panel without N+1 queries."""
    if not node_texts:
        return {}
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        result = session.run(
            """
            UNWIND $texts AS t
            MATCH (n:Entity {text: t})
            RETURN n.text AS text, n.source AS source, n.product_name AS product_name,
                   n.label AS label, n.first_seen_chunk AS chunk_id
            """, texts=node_texts)
        rows = [dict(r) for r in result]
    return {r["text"]: r for r in rows}