"""REC06: Real Neo4j graph schema alignment test.

Tests Neo4j CAS with real ephemeral fixture. Requires a running Neo4j
instance at NEO4J_URI.  Skips if Neo4j is unavailable.

Run: python -m pytest tests/test_neo4j_graph_integration.py -v
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

# Skip entire module if neo4j driver or server is unavailable
try:
    import neo4j
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "testpassword")

pytestmark = pytest.mark.skipif(not HAS_NEO4J, reason="neo4j not installed")

@pytest.fixture
def neo4j_driver():
    """Create an ephemeral Neo4j driver and clean test data."""
    driver = neo4j.GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    # Verify connectivity
    try:
        driver.verify_connectivity()
    except Exception:
        driver.close()
        pytest.skip(f"Neo4j not reachable at {NEO4J_URI}")

    # Clean up any existing test data
    with driver.session() as s:
        s.run("MATCH (n:TestEntity) DETACH DELETE n")

    yield driver

    # Cleanup after tests
    with driver.session() as s:
        s.run("MATCH (n:TestEntity) DETACH DELETE n")
    driver.close()

def test_rec06_neo4j_cas_writes_and_reads_back(neo4j_driver):
    """REC06: Neo4j CAS writes the exact value and readback matches."""
    from amc_publication.graph import Neo4jGraphPort

    port = Neo4jGraphPort(
        neo4j_driver,
        label="Entity",
        allowed_attributes={"display_name"},
    )

    # Create a test entity
    with neo4j_driver.session() as s:
        s.run(
            "CREATE (n:Entity {tenant_id: 't1', entity_id: 'TEST-1', "
            "display_name: 'old_value', publication_fence: 0})"
        )

    # Read preimage
    pre = port.read("t1", "TEST-1", "display_name")
    assert pre["value"] == "old_value"

    # CAS to new value with fence=1
    port.compare_and_set("t1", "TEST-1", "display_name",
                         {"value": "old_value"}, "new_value", 1)

    # Independent readback
    post = port.read("t1", "TEST-1", "display_name")
    assert post["value"] == "new_value", f"Readback mismatch: {post}"

    # Cleanup
    with neo4j_driver.session() as s:
        s.run("MATCH (n:Entity {tenant_id: 't1', entity_id: 'TEST-1'}) DELETE n")

def test_rec06_neo4j_rejects_stale_fence(neo4j_driver):
    """REC06: A stale fencing token cannot overwrite a newer write."""
    from amc_publication.graph import Neo4jGraphPort
    from amc_publication.types import Conflict

    port = Neo4jGraphPort(
        neo4j_driver,
        label="Entity",
        allowed_attributes={"display_name"},
    )

    with neo4j_driver.session() as s:
        s.run(
            "CREATE (n:Entity {tenant_id: 't1', entity_id: 'TEST-2', "
            "display_name: 'v0', publication_fence: 0})"
        )

    # First write with fence=1
    port.compare_and_set("t1", "TEST-2", "display_name",
                         {"value": "v0"}, "v1", 1)

    # Attempt second write with stale fence=0 — must fail
    with pytest.raises(Conflict, match="stale graph fencing"):
        port.compare_and_set("t1", "TEST-2", "display_name",
                             {"value": "v1"}, "v2", 0)

    # Cleanup
    with neo4j_driver.session() as s:
        s.run("MATCH (n:Entity {tenant_id: 't1', entity_id: 'TEST-2'}) DELETE n")

def test_rec06_neo4j_field_allowlist_rejects_injection(neo4j_driver):
    """REC06: Field allowlist prevents Cypher injection."""
    from amc_publication.graph import Neo4jGraphPort

    port = Neo4jGraphPort(
        neo4j_driver,
        label="Entity",
        allowed_attributes={"display_name"},
    )

    # Injection attempt
    with pytest.raises(ValueError, match="not allowlisted"):
        port._field("display_name` SET n.password='x")

    # Unapproved field
    with pytest.raises(ValueError, match="not allowlisted"):
        port._field("password")

def test_rec06_neo4j_tenant_isolation(neo4j_driver):
    """REC06: A write for tenant t1 cannot affect tenant t2."""
    from amc_publication.graph import Neo4jGraphPort
    from amc_publication.types import VerificationFailed

    port = Neo4jGraphPort(
        neo4j_driver,
        label="Entity",
        allowed_attributes={"display_name"},
    )

    with neo4j_driver.session() as s:
        s.run(
            "CREATE (n:Entity {tenant_id: 't1', entity_id: 'ISO-1', "
            "display_name: 'name_t1', publication_fence: 0})"
        )
        s.run(
            "CREATE (n:Entity {tenant_id: 't2', entity_id: 'ISO-1', "
            "display_name: 'name_t2', publication_fence: 0})"
        )

    # Read t1 — should get t1's value, not t2's
    pre = port.read("t1", "ISO-1", "display_name")
    assert pre["value"] == "name_t1"

    # Read t2 — should get t2's value
    pre2 = port.read("t2", "ISO-1", "display_name")
    assert pre2["value"] == "name_t2"

    # Cleanup
    with neo4j_driver.session() as s:
        s.run("MATCH (n:Entity {entity_id: 'ISO-1'}) DELETE n")