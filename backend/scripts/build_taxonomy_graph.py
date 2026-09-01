# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
build_taxonomy_graph.py
========================
Builds a deterministic Neo4j knowledge graph for the Mutual Fund Taxonomy
on a SEPARATE Neo4j instance (bolt://localhost:7688).
Now upgraded to support a Dual-Regime Taxonomy (LEGACY_2017 & CURRENT_2026).

Run from: backend/
    python scripts/build_taxonomy_graph.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine import faiss_store as fs

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "data" / "taxonomy" / "mutual_fund_taxonomy_v0_3.json"
NEO4J_URI      = "bolt://localhost:7688"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "contextgraph"
NEO4J_DATABASE = "neo4j"

def get_driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def build_graph():
    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    driver = get_driver()

    with driver.session(database=NEO4J_DATABASE) as s:
        print("== Step 1: Clearing existing taxonomy nodes ==", flush=True)
        s.run("MATCH (n) WHERE n.source_db = 'taxonomy' DETACH DELETE n")

        print("== Step 2: Schema constraints ==", flush=True)
        s.run("CREATE CONSTRAINT tax_scheme_class IF NOT EXISTS FOR (n:SchemeClass) REQUIRE n.code IS UNIQUE")
        s.run("CREATE CONSTRAINT tax_regime IF NOT EXISTS FOR (n:RegulatoryRegime) REQUIRE n.regime_id IS UNIQUE")
        s.run("CREATE INDEX tax_scheme_label IF NOT EXISTS FOR (n:SchemeClass) ON (n.canonical_label)")
        s.run("CREATE VECTOR INDEX tax_scheme_vector IF NOT EXISTS FOR (n:SchemeClass) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}")
        s.run("CREATE VECTOR INDEX tax_change_vector IF NOT EXISTS FOR (n:StructuralChange) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}")

        print("== Step 3: Processing Regimes ==", flush=True)
        total_scheme_nodes = 0
        
        for regime in tax.get("regimes", []):
            regime_id = regime["regime_id"]
            print(f" -> Processing Regime: {regime_id}", flush=True)
            
            # Create Regime Node
            s.run("""
                MERGE (rr:RegulatoryRegime {regime_id: $rid})
                SET rr.label = $label, rr.effective_from = $eff_from, rr.status = $status, rr.source_db = 'taxonomy'
            """, rid=regime_id, label=regime["label"], eff_from=regime.get("effective_from", ""), status=regime.get("status", ""))
            
            # Regulatory Basis
            rb = regime["regulatory_basis"]
            s.run("""
                MERGE (c:RegulatoryCircular {circular_id: $cid})
                SET c.title = $title, c.date = $date, c.source_db = 'taxonomy'
                WITH c
                MATCH (rr:RegulatoryRegime {regime_id: $rid})
                MERGE (rr)-[:GOVERNED_BY]->(c)
            """, cid=rb["primary_circular"], title=rb["primary_circular_title"], date=rb.get("primary_circular_date", ""), rid=regime_id)

            for amend in rb.get("key_amendments", []):
                s.run("""
                    MERGE (a:Amendment {circular_id: $cid})
                    SET a.date = $date, a.change_summary = $change, a.source_db = 'taxonomy'
                    WITH a
                    MATCH (c:RegulatoryCircular {circular_id: $parent_cid})
                    MERGE (c)-[:AMENDED_BY]->(a)
                """, cid=amend["circular"], date=amend["date"], change=amend["change"], parent_cid=rb["primary_circular"])

            # Groups (Sections)
            for group in regime.get("groups", []):
                sec_id = f"{regime_id}_{group['section']}"
                s.run("""
                    MERGE (ss:SchemeSection {section_id: $sid})
                    SET ss.label = $label, ss.original_section = $orig_sec, ss.source_db = 'taxonomy'
                    WITH ss
                    MATCH (rr:RegulatoryRegime {regime_id: $rid})
                    MERGE (ss)-[:BELONGS_TO_REGIME]->(rr)
                """, sid=sec_id, label=group["label"], orig_sec=group["section"], rid=regime_id)
                
            # Structural Changes
            for idx, change in enumerate(regime.get("structural_changes_vs_legacy", [])):
                embed_text = f"[{regime_id} Structural Change] {change}"
                embedding = fs._embed_texts([embed_text])[0].tolist()
                s.run("""
                    MERGE (sc:StructuralChange {change_id: $cid})
                    SET sc.description = $desc,
                        sc.source_db = 'taxonomy',
                        sc.embedding = $embedding
                    WITH sc
                    MATCH (rr:RegulatoryRegime {regime_id: $rid})
                    MERGE (rr)-[:INTRODUCED_CHANGE]->(sc)
                """, cid=f"{regime_id}_change_{idx}", desc=change, rid=regime_id, embedding=embedding)

            # Scheme Classes
            for scheme in regime.get("scheme_classes", []):
                embed_text = f"[{regime_id}] {scheme['canonical_label']} - {scheme.get('investment_mandate', '')}"
                embedding = fs._embed_texts([embed_text])[0].tolist()
                
                s.run("""
                    MERGE (sc:SchemeClass {code: $code})
                    SET sc.canonical_label = $label,
                        sc.investment_mandate = $mandate,
                        sc.csv_category = $csv_cat,
                        sc.data_status = $status,
                        sc.source_db = 'taxonomy',
                        sc.regime_id = $rid,
                        sc.embedding = $embedding
                """, code=scheme["code"], label=scheme["canonical_label"],
                     mandate=scheme.get("investment_mandate", ""),
                     csv_cat=scheme.get("csv_category_string", ""),
                     status=scheme.get("data_status", ""),
                     rid=regime_id,
                     embedding=embedding)
                     
                sec_id = f"{regime_id}_{scheme['section']}"
                s.run("""
                    MATCH (sc:SchemeClass {code: $code})
                    MATCH (ss:SchemeSection {section_id: $sid})
                    MATCH (rr:RegulatoryRegime {regime_id: $rid})
                    MERGE (sc)-[:BELONGS_TO]->(ss)
                    MERGE (sc)-[:VALID_UNDER]->(rr)
                """, code=scheme["code"], sid=sec_id, rid=regime_id)
                
                # Crosswalk
                if scheme.get("crosswalk_from"):
                    s.run("""
                        MATCH (modern:SchemeClass {code: $code})
                        MATCH (legacy:SchemeClass {code: $legacy_code})
                        MERGE (legacy)-[:CROSSWALK_TO]->(modern)
                    """, code=scheme["code"], legacy_code=scheme["crosswalk_from"])
                    
                total_scheme_nodes += 1
                
        print(f"   Created {total_scheme_nodes} SchemeClass nodes with Dual-Regime routing", flush=True)

        # Final count
        result = s.run("MATCH (n) WHERE n.source_db = 'taxonomy' RETURN count(n) AS total")
        total = result.single()["total"]
        print(f"\n  [OK] Graph build complete!", flush=True)
        print(f"    Total taxonomy nodes: {total}", flush=True)

    driver.close()

if __name__ == "__main__":
    build_graph()
