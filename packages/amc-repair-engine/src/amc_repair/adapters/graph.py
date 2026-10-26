"""
Graph database adapter implementations (Memory & Neo4j).
"""
import logging
from typing import Any, Dict, Optional
from .base import GraphAdapter

logger = logging.getLogger("amc_repair.graph")


class MemoryGraphAdapter(GraphAdapter):
    def __init__(self):
        """Initialize a new instance of MemoryGraphAdapter.
        """
        self._graph: Dict[str, Dict[str, Any]] = {}

    async def apply_entity_patch(self, entity_id: str, attribute: str, value: Any) -> bool:
        """Apply entity patch.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            value (Any): The value.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if entity_id not in self._graph:
            self._graph[entity_id] = {}
        self._graph[entity_id][attribute] = value
        return True

    async def get_entity_property(self, entity_id: str, attribute: str) -> Optional[Any]:
        """Retrieve entity property.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.

        Returns:
            Optional[Any]: Matching object or record if found, None otherwise.
        """
        return self._graph.get(entity_id, {}).get(attribute)

    async def create_shadow_patch(self, entity_id: str, patch_id: str, attribute: str, value: Any) -> bool:
        """Create shadow patch.

        Args:
            entity_id (str): Unique identifier of the entity.
            patch_id (str): Unique identifier of the patch.
            attribute (str): The attribute.
            value (Any): The value.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if not hasattr(self, "_shadow_patches"):
            self._shadow_patches = {}
        self._shadow_patches[patch_id] = {
            "entity_id": entity_id,
            "attribute": attribute,
            "value": value,
        }
        return True

    async def delete_shadow_patch(self, patch_id: str) -> bool:
        """Delete shadow patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if hasattr(self, "_shadow_patches") and patch_id in self._shadow_patches:
            del self._shadow_patches[patch_id]
        return True

    async def close(self):
        """Close operation.
        """
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
        """Initialize a new instance of Neo4jAdapter.

        Args:
            uri (str): The uri.
            user (str): The user.
            password (str): User's plaintext password.
            database (str): The database.
        """
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
        """Apply entity patch.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            value (Any): The value.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        # Update fallback cache
        await self._fallback.apply_entity_patch(entity_id, attribute, value)
        if self._driver:
            try:
                cypher = f"""
                MATCH (e) WHERE e.isin = $entity_id OR e.id = $entity_id OR e.name = $entity_id OR toLower(e.name) = toLower($entity_id) OR toLower(e.isin) = toLower($entity_id)
                SET e.{attribute} = $value,
                    e.{attribute}_updated_at = datetime()
                RETURN count(e) AS updated
                """
                with self._driver.session(database=self.database) as session:
                    res = session.run(cypher, entity_id=entity_id, value=value)
                    record = res.single()
                    return True
            except Exception as exc:
                logger.debug("Neo4j patch query error (%s), fallback used", exc)
                return True
        return True

    async def get_entity_property(self, entity_id: str, attribute: str) -> Optional[Any]:
        """Retrieve entity property.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.

        Returns:
            Optional[Any]: Matching object or record if found, None otherwise.
        """
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

    async def create_shadow_patch(self, entity_id: str, patch_id: str, attribute: str, value: Any) -> bool:
        """Create shadow patch.

        Args:
            entity_id (str): Unique identifier of the entity.
            patch_id (str): Unique identifier of the patch.
            attribute (str): The attribute.
            value (Any): The value.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        await self._fallback.create_shadow_patch(entity_id, patch_id, attribute, value)
        if self._driver:
            try:
                cypher = """
                MATCH (e) WHERE e.isin = $entity_id OR e.id = $entity_id OR e.name = $entity_id
                MERGE (p:ShadowPatch {patch_id: $patch_id})
                SET p.name = $attribute + ' = ' + toString($value),
                    p.attribute = $attribute,
                    p.corrected_value = $value,
                    p.status = 'approved',
                    p.created_at = datetime()
                MERGE (e)-[r:HAS_PATCH {attribute: $attribute}]->(p)
                RETURN count(p) AS created
                """
                with self._driver.session(database=self.database) as session:
                    res = session.run(cypher, entity_id=entity_id, patch_id=patch_id, attribute=attribute, value=str(value))
                    record = res.single()
                    return bool(record and record["created"] > 0)
            except Exception as exc:
                logger.debug("Neo4j create_shadow_patch notice (%s), fallback used", exc)
                return True
        return True

    async def delete_shadow_patch(self, patch_id: str) -> bool:
        """Delete shadow patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        await self._fallback.delete_shadow_patch(patch_id)
        if self._driver:
            try:
                cypher = """
                MATCH (p:ShadowPatch {patch_id: $patch_id})
                DETACH DELETE p
                RETURN count(p) AS deleted
                """
                with self._driver.session(database=self.database) as session:
                    res = session.run(cypher, patch_id=patch_id)
                    record = res.single()
                    return bool(record and record["deleted"] > 0)
            except Exception as exc:
                logger.debug("Neo4j delete_shadow_patch notice (%s), fallback used", exc)
                return True
        return True

    async def close(self):
        """Close operation.
        """
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
        await self._fallback.close()
