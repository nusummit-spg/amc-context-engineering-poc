"""Exact graph CAS ports: in-memory reference and optional Neo4j production adapter.

Neo4j adapter requires existing nodes, tenant_id+entity_id scope, a static label
allowlist, safe property identifiers, and a globally monotonic claim fence.
"""
from dataclasses import dataclass
from re import fullmatch
from typing import Any, Protocol
from .types import Conflict, VerificationFailed


class GraphPort(Protocol):
    def read(self, tenant: str, entity: str, attr: str) -> dict: ...
    def compare_and_set(self, tenant: str, entity: str, attr: str,
                        expected: dict, new_value: Any, fence: int) -> None: ...


class InMemoryGraphPort:
    """Deterministic fake for unit tests only; not persistent."""
    def __init__(self):
        self.values: dict[tuple, tuple[Any, int]] = {}

    def seed(self, tenant, entity, attr, value):
        self.values[(tenant, entity, attr)] = (value, 0)

    def read(self, tenant, entity, attr):
        item = self.values.get((tenant, entity, attr))
        return {"value": item[0] if item else None}

    def compare_and_set(self, tenant, entity, attr, expected, new_value, fence):
        k = (tenant, entity, attr)
        val, old_fence = self.values.get(k, (None, 0))
        if old_fence > fence:
            raise Conflict("stale graph fencing token")
        if val != expected["value"] and val != new_value:
            raise Conflict("graph preimage changed since approval")
        self.values[k] = (new_value, fence)


class Neo4jGraphPort:
    """Adapter for neo4j.Driver; no writes unless exact old value and fence match.

    Requires Neo4j 5.x and an entity graph with tenant_id / entity_id properties.
    Adapt those property names in a reviewed migration if the AMC graph differs.
    """
    def __init__(self, driver: Any, *, label: str = "Entity", database: str = "neo4j",
                 allowed_attributes: set[str] | None = None):
        if label not in {"Entity", "AMC", "Scheme", "Plan"}:
            raise ValueError("node label must be explicitly allowlisted")
        if not allowed_attributes:
            raise ValueError("production graph attribute allowlist required")
        self.driver = driver
        self.label = label
        self.database = database
        self.attributes = allowed_attributes

    def _field(self, attr: str):
        if attr not in self.attributes or not fullmatch(r"[A-Za-z][A-Za-z0-9_]*", attr):
            raise ValueError("graph field is not allowlisted")
        return f"n.`{attr}`"

    def read(self, tenant, entity, attr):
        field = self._field(attr)
        cypher = (f"MATCH (n:`{self.label}` {{tenant_id:$tenant, entity_id:$entity}}) "
                  f"RETURN {field} AS value")
        with self.driver.session(database=self.database) as s:
            rows = s.run(cypher, tenant=tenant, entity=entity)
            record = rows.single(strict=True)
            if record is None:
                raise VerificationFailed("graph target does not exist")
            return {"value": record["value"]}

    def compare_and_set(self, tenant, entity, attr, expected, new_value, fence):
        field = self._field(attr)
        # publication_fence orders claims across all jobs and workers, not just
        # within one job. Parameter values are never interpolated into Cypher.
        q = (f"MATCH (n:`{self.label}` {{tenant_id:$tenant, entity_id:$entity}}) "
             f"WHERE coalesce(n.publication_fence, 0) <= $fence "
             f"AND ({field} = $expected OR ({field} IS NULL AND $expected IS NULL) "
             f"OR {field} = $desired) "
             f"SET {field} = $desired, n.publication_fence = $fence "
             f"RETURN {field} AS observed")
        with self.driver.session(database=self.database) as s:
            record = s.run(q, tenant=tenant, entity=entity, fence=fence,
                           expected=expected["value"], desired=new_value).single()
            if not record or record["observed"] != new_value:
                raise Conflict("graph CAS or fencing rejected mutation")
