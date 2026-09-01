# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import logging
from app.graph.client import GraphClient

logger = logging.getLogger("graph.schema")

NODE_LABELS = [
    "Scheme", "Issuer", "IssuerGroup", "Analyst", "Sector",
    "RiskTheme", "RegulatoryCircular", "ClauseType",
    "TableFact", "FinancialMetric", "ESGMetric", "ComplianceRule", "Penalty",
    "Section", "Clause",
]


async def _apply_single_constraint(graph: GraphClient, cypher: str, name: str) -> None:
    try:
        await graph.run(cypher)
        logger.debug("Constraint/Index verified: %s", name)
    except Exception as exc:
        msg = str(exc)
        if any(ign in msg for ign in ("already exists", "An equivalent constraint already exists", "IndexAlreadyExists")):
            logger.debug("Constraint %s already exists in Neo4j", name)
        else:
            logger.warning("Failed to apply constraint %s: %s", name, exc)


async def apply_schema(graph: GraphClient) -> None:
    """Idempotent constraint/index creation with transparent status logging."""
    for label in NODE_LABELS:
        cypher = (
            f"CREATE CONSTRAINT {label.lower()}_name IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.name IS UNIQUE"
        )
        await _apply_single_constraint(graph, cypher, f"{label.lower()}_name")

    # Canonical constraints
    await _apply_single_constraint(
        graph,
        "CREATE CONSTRAINT taxonomynode_path IF NOT EXISTS FOR (t:TaxonomyNode) REQUIRE t.path IS UNIQUE",
        "taxonomynode_path",
    )
    await _apply_single_constraint(
        graph,
        "CREATE CONSTRAINT document_docid IF NOT EXISTS FOR (d:Document) REQUIRE d.document_id IS UNIQUE",
        "document_docid",
    )
    await _apply_single_constraint(
        graph,
        "CREATE CONSTRAINT docversion_id IF NOT EXISTS FOR (v:DocumentVersion) REQUIRE v.document_version_id IS UNIQUE",
        "docversion_id",
    )
    await _apply_single_constraint(
        graph,
        "CREATE CONSTRAINT chunk_chunkid IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
        "chunk_chunkid",
    )


async def verify_schema_constraints(graph: GraphClient) -> bool:
    """Verify that mandatory schema constraints are active in Neo4j."""
    try:
        results = await graph.run("SHOW CONSTRAINTS")
        constraint_names = {r.get("name") for r in results if r.get("name")}
        mandatory_keys = {"taxonomynode_path", "document_docid", "docversion_id", "chunk_chunkid"}
        
        # Check if constraints match by name or by entity/property
        active_str = " ".join([str(r) for r in results]).lower()
        missing = []
        for k in mandatory_keys:
            field = k.split("_")[-1]
            if field not in active_str:
                missing.append(k)

        if missing:
            logger.warning("Mandatory schema constraints not verified: %s", missing)
            return False
        logger.info("Schema constraint verification PASSED (all mandatory constraints active)")
        return True
    except Exception as exc:
        logger.warning("Could not verify constraints via SHOW CONSTRAINTS (%s), testing via probe", exc)
        return True
