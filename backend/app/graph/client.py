"""Neo4j client wrapper — async driver, query helper, entity/relationship upserts."""
import logging
from typing import Any, Optional

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import get_settings
from app.schemas.entities import BaseEntity
from app.schemas.relationships import Relationship

logger = logging.getLogger("graph")


class GraphClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._database = settings.neo4j_database

    async def close(self) -> None:
        await self._driver.close()

    async def run(self, cypher: str, **params: Any) -> list[dict]:
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, **params)
            return [record.data() async for record in result]

    async def ping(self) -> bool:
        try:
            await self.run("RETURN 1 AS ok")
            return True
        except Exception:
            return False

    # ---------- upserts ----------

    async def upsert_entity(self, entity: BaseEntity) -> None:
        label = entity.entity_type.value
        await self.run(
            f"""
            MERGE (e:{label} {{name: $name}})
            SET e.entity_id = coalesce(e.entity_id, $entity_id),
                e.aliases = $aliases,
                e += $properties
            """,
            name=entity.name,
            entity_id=entity.entity_id,
            aliases=entity.aliases,
            properties={k: v for k, v in entity.properties.items() if v is not None},
        )

    async def upsert_relationship(self, rel: Relationship, source_name: str, target_name: str) -> None:
        rel_type = rel.relationship_type.value
        props = dict(rel.properties)
        props["extraction_method"] = rel.extraction_method
        props["confidence"] = rel.confidence
        if rel.source_document_id:
            props["source_document_id"] = rel.source_document_id
        await self.run(
            f"""
            MATCH (a {{name: $source_name}}), (b {{name: $target_name}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $props
            """,
            source_name=source_name,
            target_name=target_name,
            props=props,
        )

    # ---------- reads for /graph endpoints ----------

    async def full_graph(self, limit: int = 500) -> dict:
        nodes = await self.run(
            "MATCH (n) WHERE n.name IS NOT NULL "
            "RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props LIMIT $limit",
            limit=limit,
        )
        edges = await self.run(
            "MATCH (a)-[r]->(b) WHERE a.name IS NOT NULL AND b.name IS NOT NULL "
            "RETURN elementId(r) AS id, elementId(a) AS source, elementId(b) AS target, "
            "type(r) AS rel_type, properties(r) AS props LIMIT $limit",
            limit=limit,
        )
        return {"nodes": nodes, "edges": edges}

    async def neighborhood(self, name: str, depth: int = 1) -> dict:
        depth = max(1, min(depth, 3))
        records = await self.run(
            f"""
            MATCH path = (n {{name: $name}})-[*1..{depth}]-(m)
            WITH nodes(path) AS ns, relationships(path) AS rs
            UNWIND ns AS node
            WITH collect(DISTINCT node) AS all_nodes, collect(rs) AS rel_lists
            UNWIND rel_lists AS rl
            UNWIND rl AS rel
            WITH all_nodes, collect(DISTINCT rel) AS all_rels
            RETURN
              [n IN all_nodes | {{id: elementId(n), labels: labels(n), props: properties(n)}}] AS nodes,
              [r IN all_rels | {{id: elementId(r), source: elementId(startNode(r)),
                                 target: elementId(endNode(r)), rel_type: type(r),
                                 props: properties(r)}}] AS edges
            """,
            name=name,
        )
        if not records:
            return {"nodes": [], "edges": []}
        return records[0]


_graph_client: Optional[GraphClient] = None


def get_graph_client() -> GraphClient:
    global _graph_client
    if _graph_client is None:
        _graph_client = GraphClient()
    return _graph_client
