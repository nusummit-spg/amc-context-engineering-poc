# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Import taxonomy tree from data/taxonomy_v2.json into Neo4j graph.

Creates:
  (:TaxonomyNode {path, name, level, domain})
  (:TaxonomyNode)-[:PARENT_OF]->(:TaxonomyNode)
  (:SchemeClass {name, path, regime, level})
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from neo4j import GraphDatabase
from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("taxonomy_import")


def main():
    settings = get_settings()
    tax_path = root / "seeds" / "taxonomy.json"
    if not tax_path.exists():
        tax_path = root / "data" / "taxonomy_v2.json"
    if not tax_path.exists():
        tax_path = root / "app" / "engine" / "taxonomy.json"
    if not tax_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found at {tax_path}")

    data = json.loads(tax_path.read_text(encoding="utf-8"))
    logger.info("Loaded taxonomy seed: domain=%s, version=%s", data.get("domain"), data.get("version"))

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    session = driver.session(database=settings.neo4j_database)

    # 1. Create constraints
    try:
        session.run("CREATE CONSTRAINT taxonomy_path_unique IF NOT EXISTS FOR (t:TaxonomyNode) REQUIRE t.path IS UNIQUE")
    except Exception as exc:
        logger.warning("Constraint creation notice: %s", exc)

    domain = data.get("domain", "AMC")

    # 2. Support tree dictionary or roots list
    def _import_tree_dict(subtree: dict, parent_path: str = "", level: int = 1):
        for key, value in subtree.items():
            current_path = f"{parent_path}/{key}" if parent_path else key
            session.run(
                """
                MERGE (t:TaxonomyNode {path: $path})
                SET t.name = $name,
                    t.level = $level,
                    t.domain = $domain,
                    t.source_db = 'taxonomy'
                """,
                path=current_path,
                name=key,
                level=level,
                domain=domain,
            )
            if parent_path:
                session.run(
                    """
                    MATCH (p:TaxonomyNode {path: $parent_path}), (c:TaxonomyNode {path: $child_path})
                    MERGE (p)-[:PARENT_OF]->(c)
                    """,
                    parent_path=parent_path,
                    child_path=current_path,
                )
            if isinstance(value, dict):
                _import_tree_dict(value, current_path, level + 1)
            elif isinstance(value, list):
                for leaf in value:
                    leaf_path = f"{current_path}/{leaf}"
                    session.run(
                        """
                        MERGE (t:TaxonomyNode {path: $path})
                        SET t.name = $name,
                            t.level = $level,
                            t.domain = $domain,
                            t.source_db = 'taxonomy'
                        MERGE (s:SchemeClass {path: $path})
                        SET s.name = $name,
                            s.level = $level,
                            s.regime = '2026_harmonized'
                        MERGE (s)-[:CLASSIFIED_UNDER]->(t)
                        """,
                        path=leaf_path,
                        name=leaf,
                        level=level + 1,
                        domain=domain,
                    )
                    session.run(
                        """
                        MATCH (p:TaxonomyNode {path: $parent_path}), (c:TaxonomyNode {path: $child_path})
                        MERGE (p)-[:PARENT_OF]->(c)
                        """,
                        parent_path=current_path,
                        child_path=leaf_path,
                    )

    if "tree" in data:
        _import_tree_dict(data["tree"])
    elif "roots" in data:
        def _import_node_list(node: dict, parent_path: str = "", level: int = 1):
            name = node.get("name")
            current_path = f"{parent_path}/{name}" if parent_path else name
            session.run(
                """
                MERGE (t:TaxonomyNode {path: $path})
                SET t.name = $name,
                    t.level = $level,
                    t.domain = $domain,
                    t.source_db = 'taxonomy'
                """,
                path=current_path,
                name=name,
                level=level,
                domain=domain,
            )
            if parent_path:
                session.run(
                    """
                    MATCH (p:TaxonomyNode {path: $parent_path}), (c:TaxonomyNode {path: $child_path})
                    MERGE (p)-[:PARENT_OF]->(c)
                    """,
                    parent_path=parent_path,
                    child_path=current_path,
                )
            for child in node.get("children", []):
                _import_node_list(child, current_path, level + 1)
        for root_node in data["roots"]:
            _import_node_list(root_node)

    # Verification count
    node_count = session.run("MATCH (t:TaxonomyNode) RETURN count(t) AS count").single()["count"]
    scheme_count = session.run("MATCH (s:SchemeClass) RETURN count(s) AS count").single()["count"]
    logger.info("Imported taxonomy successfully: %d TaxonomyNode records, %d SchemeClass records", node_count, scheme_count)

    session.close()
    driver.close()


if __name__ == "__main__":
    main()
