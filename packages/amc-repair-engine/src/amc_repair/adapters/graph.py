"""
Graph database adapter implementations (Memory & Neo4j).
"""
import logging
from typing import Any, Dict, Optional
from .base import GraphAdapter

logger = logging.getLogger("amc_repair.graph")


class MemoryGraphAdapter(GraphAdapter):
    def __init__(self):
        self._graph: Dict[str, Dict[str, Any]] = {}

    async def apply_entity_patch(self, entity_id: str, attribute: str, value: Any) -> bool:
        if entity_id not in self._graph:
            self._graph[entity_id] = {}
        self._graph[entity_id][attribute] = value
        return True

    async def get_entity_property(self, entity_id: str, attribute: str) -> Optional[Any]:
        return self._graph.get(entity_id, {}).get(attribute)

    async def close(self):
        self._graph.clear()


# Alias for compatibility with Task 2.2
MemoryAdapter = MemoryGraphAdapter


class Neo4jAdapter(GraphAdapter):
    """Neo4j graph database adapter with in-memory fallback if Neo4j is unavailable."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self._driver = None
        self._fallback = MemoryGraphAdapter()
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        except Exception as exc:
            logger.warning("Neo4j driver initialization failed (%s); using in-memory fallback", exc)

    async def apply_entity_patch(self, entity_id: str, attribute: str, value: Any) -> bool:
        # Update fallback cache
        await self._fallback.apply_entity_patch(entity_id, attribute, value)
        if self._driver:
            try:
                cypher = f"""
                MATCH (e) WHERE e.isin = $entity_id OR e.id = $entity_id OR e.name = $entity_id
                SET e.{attribute} = $value,
                    e.{attribute}_updated_at = datetime()
                RETURN count(e) AS updated
                """
                with self._driver.session(database=self.database) as session:
                    res = session.run(cypher, entity_id=entity_id, value=value)
                    record = res.single()
                    return bool(record and record["updated"] > 0)
            except Exception as exc:
                logger.debug("Neo4j patch query error (%s), fallback used", exc)
                return True
        return True

    async def get_entity_property(self, entity_id: str, attribute: str) -> Optional[Any]:
        if self._driver:
            try:
                cypher = f"""
                MATCH (e) WHERE e.isin = $entity_id OR e.id = $entity_id OR e.name = $entity_id
                RETURN e.{attribute} AS val
                """
                with self._driver.session(database=self.database) as session:
                    res = session.run(cypher, entity_id=entity_id)
                    record = res.single()
                    if record:
                        return record["val"]
            except Exception as exc:
                logger.debug("Neo4j property query error (%s), fallback used", exc)
        return await self._fallback.get_entity_property(entity_id, attribute)

    async def close(self):
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
        await self._fallback.close()
