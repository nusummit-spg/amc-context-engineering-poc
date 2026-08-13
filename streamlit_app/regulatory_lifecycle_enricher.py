"""
regulatory_lifecycle_enricher.py
================================
Enriches Neo4j graph with RegulatoryDocument nodes and lifecycle edges:
- [:SUPERSEDES] and [:AMENDED_BY]
- Confidence-gated proposed edge queue for Admin confirmation (Q2 decision)
"""
from __future__ import annotations
import re
import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import config
import graph_store
import provenance_ledger

SUPERSESSION_REGEXES = [
    (re.compile(r"Amendment to (?:SEBI )?Circular (?:dated|on) (.+?) dated", re.I), "AMENDED_BY"),
    (re.compile(r"Addendum to (?:SEBI )?Circular(?: on)?(.+)", re.I), "AMENDED_BY"),
    (re.compile(r"Extension of timeline for implementation of(.*?)dated", re.I), "EXTENDS"),
    (re.compile(r"Deferment of timeline for(.*?)dated", re.I), "DEFERS"),
    (re.compile(r"Clarification(?: on| regarding)(.*?)Circular", re.I), "CLARIFIES"),
    (re.compile(r"(?:Modification|Review) of (?:framework|provisions)(.*)", re.I), "MODIFIES"),
]


@dataclass
class ProposedEdge:
    edge_id: str
    source_filename: str
    target_filename: str
    rel_type: str
    confidence: str = "medium"
    pending_confirmation: bool = True
    created_at: str = ""


def init_regulatory_schema() -> None:
    """Initialize constraints and indexes for RegulatoryDocument nodes in Neo4j."""
    try:
        driver = graph_store.get_driver()
        if not driver:
            return
        with driver.session(database=config.NEO4J_DATABASE) as s:
            s.run("CREATE CONSTRAINT regulatory_doc_key IF NOT EXISTS FOR (d:RegulatoryDocument) REQUIRE d.filename IS UNIQUE")
            s.run("CREATE INDEX reg_doc_status IF NOT EXISTS FOR (d:RegulatoryDocument) ON (d.status)")
            s.run("CREATE INDEX reg_doc_dept IF NOT EXISTS FOR (d:RegulatoryDocument) ON (d.department)")
    except Exception as exc:
        print(f"  [Lifecycle Enricher] Neo4j schema init notice: {exc}", flush=True)


def upsert_regulatory_document(record: provenance_ledger.ProvenanceRecord) -> None:
    """MERGE RegulatoryDocument node with metadata properties."""
    try:
        driver = graph_store.get_driver()
        if not driver:
            return
        with driver.session(database=config.NEO4J_DATABASE) as session:
            session.run("""
                MERGE (d:RegulatoryDocument {filename: $filename})
                SET d.status = $status,
                    d.department = $department,
                    d.entity_type = $entity_type,
                    d.acquisition_channel = $acquisition_channel,
                    d.sha256_hash = $sha256_hash,
                    d.effective_from = $effective_from,
                    d.superseded_by = $superseded_by
            """,
            filename=record.filename,
            status=record.status,
            department=record.department,
            entity_type=record.entity_type,
            acquisition_channel=record.acquisition_channel,
            sha256_hash=record.sha256_hash,
            effective_from=record.ingest_timestamp,
            superseded_by=record.superseded_by or ""
            )
    except Exception as exc:
        print(f"  [Lifecycle Enricher] Upsert node notice: {exc}", flush=True)


def detect_and_link_amendments_from_titles(records: List[provenance_ledger.ProvenanceRecord]) -> List[ProposedEdge]:
    """
    Pattern match circular titles to detect supersession/amendment relationships.
    Creates proposed edges in Neo4j with confidence="medium" and pending_confirmation=True.
    """
    init_regulatory_schema()
    driver = graph_store.get_driver()
    proposed: List[ProposedEdge] = []
    if not driver:
        return proposed

    # Build filename map
    all_filenames = [r.filename for r in records]

    for rec in records:
        upsert_regulatory_document(rec)
        title = rec.filename

        for pattern, rel_type in SUPERSESSION_REGEXES:
            m = pattern.search(title)
            if not m:
                continue

            target_phrase = m.group(1).strip().lower()
            # Match against existing filenames
            for target_fname in all_filenames:
                if target_fname == rec.filename:
                    continue
                if target_phrase in target_fname.lower() or target_fname.lower() in target_phrase:
                    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
                    p_edge = ProposedEdge(
                        edge_id=edge_id,
                        source_filename=rec.filename,
                        target_filename=target_fname,
                        rel_type=rel_type,
                        confidence="medium",
                        pending_confirmation=True,
                        created_at=datetime.now().isoformat()
                    )
                    proposed.append(p_edge)

                    # Write proposed edge to Neo4j
                    try:
                        with driver.session(database=config.NEO4J_DATABASE) as s:
                            s.run(f"""
                                MERGE (src:RegulatoryDocument {{filename: $src_file}})
                                MERGE (tgt:RegulatoryDocument {{filename: $tgt_file}})
                                MERGE (src)-[r:{rel_type}]->(tgt)
                                SET r.edge_id = $edge_id,
                                    r.confidence = 'medium',
                                    r.pending_confirmation = true,
                                    r.created_at = $created_at
                            """, src_file=rec.filename, tgt_file=target_fname, edge_id=edge_id, created_at=p_edge.created_at)
                    except Exception as e:
                        print(f"  [Lifecycle Enricher] Edge write notice: {e}", flush=True)
                    break

    return proposed


def confirm_supersession_edge(edge_id: str, authorized_by: str = "admin") -> bool:
    """Admin confirms a proposed supersession edge."""
    driver = graph_store.get_driver()
    if not driver:
        return False
    try:
        with driver.session(database=config.NEO4J_DATABASE) as s:
            res = s.run("""
                MATCH (src:RegulatoryDocument)-[r]->(tgt:RegulatoryDocument)
                WHERE r.edge_id = $edge_id
                SET r.confidence = 'confirmed',
                    r.pending_confirmation = false,
                    r.confirmed_by = $admin,
                    tgt.status = 'superseded',
                    tgt.superseded_by = src.filename
                RETURN src.filename AS src, tgt.filename AS tgt
            """, edge_id=edge_id, admin=authorized_by)
            rec = res.fetchone()
            if rec:
                provenance_ledger.update_status(rec["tgt"], "superseded", superseded_by=rec["src"])
                print(f"  [Lifecycle Enricher] Confirmed edge {edge_id}: {rec['src']} -> {rec['tgt']}", flush=True)
                return True
    except Exception as exc:
        print(f"  [Lifecycle Enricher] Confirm edge error: {exc}", flush=True)
    return False


def reject_supersession_edge(edge_id: str) -> bool:
    """Admin rejects a proposed supersession edge."""
    driver = graph_store.get_driver()
    if not driver:
        return False
    try:
        with driver.session(database=config.NEO4J_DATABASE) as s:
            s.run("""
                MATCH (src:RegulatoryDocument)-[r]->(tgt:RegulatoryDocument)
                WHERE r.edge_id = $edge_id
                DELETE r
            """, edge_id=edge_id)
            print(f"  [Lifecycle Enricher] Rejected & deleted edge {edge_id}", flush=True)
            return True
    except Exception as exc:
        print(f"  [Lifecycle Enricher] Reject edge error: {exc}", flush=True)
    return False


def get_pending_proposed_edges() -> List[Dict[str, Any]]:
    """Fetch list of pending proposed edges for Admin review queue."""
    driver = graph_store.get_driver()
    if not driver:
        return []
    edges = []
    try:
        with driver.session(database=config.NEO4J_DATABASE) as s:
            res = s.run("""
                MATCH (src:RegulatoryDocument)-[r]->(tgt:RegulatoryDocument)
                WHERE r.pending_confirmation = true
                RETURN r.edge_id AS edge_id, src.filename AS source, type(r) AS rel,
                       tgt.filename AS target, r.confidence AS confidence, r.created_at AS created_at
            """)
            for row in res:
                edges.append(dict(row))
    except Exception as exc:
        print(f"  [Lifecycle Enricher] Fetch proposed edges error: {exc}", flush=True)
    return edges
