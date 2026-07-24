"""
build_taxonomy_graph.py
=========================
Builds the dual-regime taxonomy knowledge graph (LEGACY_2017 / CURRENT_2026)
on the SAME local Neo4j instance graph_store.py already uses — not a second
instance. Every node this script writes is tagged source_db='taxonomy',
which is what makes sharing the instance safe: the existing AMC corporate
graph's :Entity-labeled nodes carry no such property, so the cleanup step
below can never touch them.

Node/relationship model:
  (:RegulatoryRegime)-[:GOVERNED_BY]->(:RegulatoryCircular)-[:AMENDED_BY]->(:Amendment)
  (:SchemeSection)-[:BELONGS_TO_REGIME]->(:RegulatoryRegime)
  (:SchemeClass)-[:BELONGS_TO]->(:SchemeSection)
  (:SchemeClass)-[:VALID_UNDER]->(:RegulatoryRegime)
  (:SchemeClass)-[:CROSSWALK_TO]->(:SchemeClass)   -- legacy code -> current code
  (:RegulatoryRegime)-[:INTRODUCED_CHANGE]->(:StructuralChange)
Plus two native Neo4j vector indexes (tax_scheme_vector, tax_change_vector)
for semantic routing at query time — this is what replaces brittle
`WHERE toLower(label) CONTAINS "..."` substring matching.

Run from streamlit_app/:
    python -m taxonomy_engine.build_taxonomy_graph
"""
from __future__ import annotations

import json
import re
from typing import List

import config
import faiss_store
import graph_store

_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _parse_crosswalk_codes(crosswalk_from: str, valid_legacy_codes: set[str]) -> List[str]:
    """'SOL_RETIREMENT + SOL_CHILDRENS (discontinued, replaced)' -> ['SOL_RETIREMENT', 'SOL_CHILDRENS']
    'DEBT_ULTRA_SHORT (renamed)' -> ['DEBT_ULTRA_SHORT']
    'NEW_NO_LEGACY_EQUIVALENT' -> []
    Anything not found in valid_legacy_codes is silently dropped (rather than
    creating a dangling MATCH that produces zero rows the way the original
    script's raw-string MATCH did)."""
    if not crosswalk_from or crosswalk_from == "NEW_NO_LEGACY_EQUIVALENT":
        return []
    stripped = _PARENTHETICAL_RE.sub("", crosswalk_from).strip()
    candidates = [c.strip() for c in stripped.split("+")]
    return [c for c in candidates if c in valid_legacy_codes]


def build_graph() -> None:
    tax = json.loads(config.MF_TAXONOMY_PATH.read_text(encoding="utf-8"))
    driver = graph_store.get_driver()

    legacy_regime = next((r for r in tax["regimes"] if r["regime_id"] == "LEGACY_2017"), None)
    valid_legacy_codes = {s["code"] for s in legacy_regime["scheme_classes"]} if legacy_regime else set()

    with driver.session(database=config.NEO4J_DATABASE) as s:
        print("== Step 1: Clearing existing taxonomy nodes (source_db='taxonomy' only) ==", flush=True)
        s.run("MATCH (n) WHERE n.source_db = 'taxonomy' DETACH DELETE n")

        print("== Step 2: Schema constraints + vector indexes ==", flush=True)
        s.run("CREATE CONSTRAINT tax_scheme_class IF NOT EXISTS FOR (n:SchemeClass) REQUIRE n.code IS UNIQUE")
        s.run("CREATE CONSTRAINT tax_regime IF NOT EXISTS FOR (n:RegulatoryRegime) REQUIRE n.regime_id IS UNIQUE")
        s.run("CREATE INDEX tax_scheme_label IF NOT EXISTS FOR (n:SchemeClass) ON (n.canonical_label)")
        s.run("""CREATE VECTOR INDEX tax_scheme_vector IF NOT EXISTS FOR (n:SchemeClass) ON (n.embedding)
                 OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}""")
        s.run("""CREATE VECTOR INDEX tax_change_vector IF NOT EXISTS FOR (n:StructuralChange) ON (n.embedding)
                 OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}""")

        print("== Step 3: Processing regimes ==", flush=True)
        total_scheme_nodes = 0
        total_crosswalk_edges = 0

        for regime in tax.get("regimes", []):
            regime_id = regime["regime_id"]
            print(f"  -> {regime_id}", flush=True)

            s.run("""
                MERGE (rr:RegulatoryRegime {regime_id: $rid})
                SET rr.label = $label, rr.effective_from = $eff_from, rr.status = $status, rr.source_db = 'taxonomy'
            """, rid=regime_id, label=regime["label"], eff_from=regime.get("effective_from", ""), status=regime.get("status", ""))

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

            for group in regime.get("groups", []):
                sec_id = f"{regime_id}_{group['section']}"
                s.run("""
                    MERGE (ss:SchemeSection {section_id: $sid})
                    SET ss.label = $label, ss.original_section = $orig_sec, ss.source_db = 'taxonomy'
                    WITH ss
                    MATCH (rr:RegulatoryRegime {regime_id: $rid})
                    MERGE (ss)-[:BELONGS_TO_REGIME]->(rr)
                """, sid=sec_id, label=group["label"], orig_sec=group["section"], rid=regime_id)

            for idx, change in enumerate(regime.get("structural_changes_vs_legacy", [])):
                embed_text = f"[{regime_id} Structural Change] {change}"
                embedding = faiss_store._embed_texts([embed_text])[0].tolist()
                s.run("""
                    MERGE (sc:StructuralChange {change_id: $cid})
                    SET sc.description = $desc, sc.source_db = 'taxonomy', sc.embedding = $embedding
                    WITH sc
                    MATCH (rr:RegulatoryRegime {regime_id: $rid})
                    MERGE (rr)-[:INTRODUCED_CHANGE]->(sc)
                """, cid=f"{regime_id}_change_{idx}", desc=change, rid=regime_id, embedding=embedding)

            for scheme in regime.get("scheme_classes", []):
                embed_text = f"[{regime_id}] {scheme['canonical_label']} - {scheme.get('investment_mandate', '')}"
                embedding = faiss_store._embed_texts([embed_text])[0].tolist()

                s.run("""
                    MERGE (sc:SchemeClass {code: $code})
                    SET sc.canonical_label = $label, sc.investment_mandate = $mandate,
                        sc.csv_category = $csv_cat, sc.data_status = $status,
                        sc.source_db = 'taxonomy', sc.regime_id = $rid, sc.embedding = $embedding
                """, code=scheme["code"], label=scheme["canonical_label"],
                     mandate=scheme.get("investment_mandate", ""),
                     csv_cat=scheme.get("csv_category_string", ""),
                     status=scheme.get("data_status", ""), rid=regime_id, embedding=embedding)

                sec_id = f"{regime_id}_{scheme['section']}"
                s.run("""
                    MATCH (sc:SchemeClass {code: $code})
                    MATCH (ss:SchemeSection {section_id: $sid})
                    MATCH (rr:RegulatoryRegime {regime_id: $rid})
                    MERGE (sc)-[:BELONGS_TO]->(ss)
                    MERGE (sc)-[:VALID_UNDER]->(rr)
                """, code=scheme["code"], sid=sec_id, rid=regime_id)

                # Crosswalk — parsed to handle compound/annotated crosswalk_from
                # values (e.g. "SOL_RETIREMENT + SOL_CHILDRENS (discontinued, replaced)"),
                # which a raw-string MATCH would silently match zero rows for.
                legacy_codes = _parse_crosswalk_codes(scheme.get("crosswalk_from", ""), valid_legacy_codes)
                for legacy_code in legacy_codes:
                    s.run("""
                        MATCH (modern:SchemeClass {code: $code})
                        MATCH (legacy:SchemeClass {code: $legacy_code})
                        MERGE (legacy)-[:CROSSWALK_TO]->(modern)
                    """, code=scheme["code"], legacy_code=legacy_code)
                    total_crosswalk_edges += 1

                total_scheme_nodes += 1

        print(f"  Created {total_scheme_nodes} SchemeClass nodes, {total_crosswalk_edges} CROSSWALK_TO edges", flush=True)

        result = s.run("MATCH (n) WHERE n.source_db = 'taxonomy' RETURN count(n) AS total")
        total = result.single()["total"]
        entity_result = s.run("MATCH (n:Entity) RETURN count(n) AS total")
        entity_total = entity_result.single()["total"]
        print(f"\n  [OK] Graph build complete.", flush=True)
        print(f"    Taxonomy nodes: {total}", flush=True)
        print(f"    Existing AMC :Entity nodes (should be unchanged): {entity_total}", flush=True)


if __name__ == "__main__":
    build_graph()
