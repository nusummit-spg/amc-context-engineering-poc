"""WS5b — Taxonomy seeding script: applies the Neo4j schema, loads TaxonomyNode
nodes from seeds/taxonomy.json, and seeds canonical entities from
seeds/entity_aliases.json (empty graph -> taxonomy + entities pre-loaded).

Run:  python -m scripts.seed_neo4j   (from backend/)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import ALIAS_SEED_PATH, load_taxonomy  # noqa: E402
from app.extraction.resolver import EntityResolver  # noqa: E402
from app.core.llm import get_llm_client  # noqa: E402
from app.graph.client import get_graph_client  # noqa: E402
from app.graph.schema import apply_schema  # noqa: E402


async def main() -> None:
    graph = get_graph_client()

    print("Applying Neo4j schema (constraints + indexes)...")
    await apply_schema(graph)

    print("Seeding taxonomy nodes...")
    taxonomy = load_taxonomy()
    for node in taxonomy.flatten():
        await graph.run(
            """
            MERGE (t:TaxonomyNode {path: $path})
            SET t.name = $name, t.level = $level
            """,
            path=node.path, name=node.name, level=node.level,
        )
        if node.parent_path:
            await graph.run(
                """
                MATCH (p:TaxonomyNode {path: $parent}), (c:TaxonomyNode {path: $child})
                MERGE (p)-[:HAS_CHILD]->(c)
                """,
                parent=node.parent_path, child=node.path,
            )
    print(f"  {len(taxonomy.flatten())} taxonomy nodes")

    print("Seeding canonical entities from alias file...")
    resolver = EntityResolver(get_llm_client(), ALIAS_SEED_PATH)
    count = 0
    for entity in resolver._canonical.values():
        await graph.upsert_entity(entity)
        count += 1
    print(f"  {count} entities")

    # Static domain edges that don't come from documents: issuer -> group / sector.
    print("Seeding static ontology edges...")
    static_edges = [
        ("Adani Ports & SEZ", "ISSUED_BY", "Adani Group"),
        ("Adani Green Energy", "ISSUED_BY", "Adani Group"),
        ("Adani Enterprises", "ISSUED_BY", "Adani Group"),
        ("Adani Group", "MONITORED_FOR", "Concentration Risk"),
        ("Bajaj Finance", "IN_SECTOR", "NBFC"),
        ("Shriram Finance", "IN_SECTOR", "NBFC"),
        ("LIC Housing Finance", "IN_SECTOR", "NBFC"),
        ("Cholamandalam Investment & Finance", "IN_SECTOR", "NBFC"),
        ("Adani Ports & SEZ", "IN_SECTOR", "Infrastructure"),
        ("Adani Green Energy", "IN_SECTOR", "Infrastructure"),
        ("SEBI Circular May2026/0142", "APPLIES_TO", "Exit Load Clause"),
    ]
    for source, rel_type, target in static_edges:
        await graph.run(
            f"""
            MATCH (a {{name: $source}}), (b {{name: $target}})
            MERGE (a)-[:{rel_type}]->(b)
            """,
            source=source, target=target,
        )
    print(f"  {len(static_edges)} edges")

    await graph.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
