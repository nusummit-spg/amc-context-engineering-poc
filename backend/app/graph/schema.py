"""WS5b — Neo4j graph schema: constraints + indexes for the 9 node labels."""
from app.graph.client import GraphClient

NODE_LABELS = [
    "Scheme", "Issuer", "IssuerGroup", "Analyst", "Sector",
    "RiskTheme", "RegulatoryCircular", "ClauseType", "Document", "TaxonomyNode",
]


async def apply_schema(graph: GraphClient) -> None:
    """Idempotent constraint/index creation. Run at startup / from seed script."""
    for label in NODE_LABELS:
        await graph.run(
            f"CREATE CONSTRAINT {label.lower()}_name IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.name IS UNIQUE"
        )
    await graph.run(
        "CREATE INDEX taxonomy_path IF NOT EXISTS FOR (n:TaxonomyNode) ON (n.path)"
    )
    await graph.run(
        "CREATE INDEX document_docid IF NOT EXISTS FOR (n:Document) ON (n.document_id)"
    )
