# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_safe_cypher.py
===================
Unit and security tests for Track 3: Cypher Query Safety Layer.
Verifies SafeCypherBuilder, CypherValidators, complexity enforcement, and audit logging.
"""

import pytest
from unittest.mock import MagicMock
from app.graph.cypher_validators import (
    CypherSecurityError,
    validate_entity_id,
    validate_attribute,
    validate_label,
    validate_relationship_type,
    validate_query_complexity,
)
from app.graph.safe_cypher_builder import SafeCypherBuilder
from app.graph.cypher_audit_log import CypherAuditLogger


@pytest.fixture
def mock_session():
    session = MagicMock()
    return session


@pytest.fixture
def audit_logger(tmp_path):
    log_file = tmp_path / "test_cypher_audit.jsonl"
    return CypherAuditLogger(str(log_file))


def test_validate_entity_id_valid_isin():
    assert validate_entity_id("INF846K01DP5") == "INF846K01DP5"
    assert validate_entity_id("INF769K01EW8") == "INF769K01EW8"


def test_validate_entity_id_valid_dedup_key():
    assert validate_entity_id("FUND::axis_bluechip") == "FUND::axis_bluechip"
    assert validate_entity_id("SCHEME::mirae-asset") == "SCHEME::mirae-asset"


def test_validate_entity_id_injection_attempt():
    injection_payloads = [
        "'; DROP TABLE Entity;--",
        "MATCH (n) DETACH DELETE n",
        "INF846K01DP5' OR '1'='1",
        "admin\" OR \"1\"=\"1",
        "INF846K01DP5; RETURN 1;",
    ]
    for payload in injection_payloads:
        with pytest.raises(CypherSecurityError):
            validate_entity_id(payload)


def test_validate_attribute_whitelist():
    assert validate_attribute("TER") == "TER"
    assert validate_attribute("NAV") == "NAV"
    assert validate_attribute("AUM") == "AUM"
    assert validate_attribute("ter") == "TER"  # Case-insensitive resolution


def test_validate_attribute_rejection():
    with pytest.raises(CypherSecurityError):
        validate_attribute("malicious_attribute")
    with pytest.raises(CypherSecurityError):
        validate_attribute("password")


def test_validate_label_whitelist():
    assert validate_label("Entity") == "Entity"
    assert validate_label("ISIN") == "ISIN"
    assert validate_label("FUND") == "FUND"

    with pytest.raises(CypherSecurityError):
        validate_label("MaliciousLabel")


def test_validate_relationship_type():
    assert validate_relationship_type("HAS_FACT") == "HAS_FACT"
    assert validate_relationship_type("MANAGED_BY") == "MANAGED_BY"

    with pytest.raises(CypherSecurityError):
        validate_relationship_type("EVIL_REL")


def test_validate_query_complexity():
    # Safe query
    validate_query_complexity("MATCH (n:Entity) RETURN n.text LIMIT 10")
    validate_query_complexity("MATCH (n:Entity) OPTIONAL MATCH (n)-[:HAS_FACT]->(f) RETURN n, f LIMIT 10")

    # Multiple statements
    with pytest.raises(CypherSecurityError, match="Multiple Cypher statements"):
        validate_query_complexity("MATCH (n) RETURN n; MATCH (m) RETURN m")

    # Write keyword
    with pytest.raises(CypherSecurityError, match="Write operations"):
        validate_query_complexity("MATCH (n) DELETE n")

    # UNION
    with pytest.raises(CypherSecurityError, match="UNION queries"):
        validate_query_complexity("MATCH (n) RETURN n UNION MATCH (m) RETURN m")

    # Excessive MATCH
    with pytest.raises(CypherSecurityError, match="max MATCH"):
        validate_query_complexity("MATCH (a) MATCH (b) MATCH (c) MATCH (d) RETURN a")

    # Excessive OPTIONAL MATCH
    with pytest.raises(CypherSecurityError, match="max OPTIONAL MATCH"):
        validate_query_complexity("MATCH (a) OPTIONAL MATCH (a)-[:R1]->(b) OPTIONAL MATCH (b)-[:R2]->(c) OPTIONAL MATCH (c)-[:R3]->(d) RETURN a")


def test_get_entity_facts_parameterization(mock_session, audit_logger):
    builder = SafeCypherBuilder(mock_session, audit_logger=audit_logger)

    mock_session.run.return_value = [
        {"attribute": "TER", "value": "0.82", "source": "AMFI_v18", "effective_date": "2026-08-17", "confidence": 0.95}
    ]

    facts = builder.get_entity_facts("INF846K01DP5", fact_type="TER")
    assert len(facts) == 1
    assert facts[0]["attribute"] == "TER"

    # Verify parameterized run call
    mock_session.run.assert_called_once()
    call_args = mock_session.run.call_args
    assert "parameters" in call_args.kwargs
    params = call_args.kwargs["parameters"]
    assert params["entity_id"] == "INF846K01DP5"
    assert params["fact_type"] == "TER"


def test_compare_entity_attributes(mock_session, audit_logger):
    builder = SafeCypherBuilder(mock_session, audit_logger=audit_logger)
    mock_session.run.return_value = [
        {"entity_id": "INF846K01DP5", "entity_name": "Axis Bluechip", "attribute": "TER", "value": "0.82"},
        {"entity_id": "INF769K01EW8", "entity_name": "Mirae Asset", "attribute": "TER", "value": "0.75"},
    ]

    res = builder.compare_entity_attributes(["INF846K01DP5", "INF769K01EW8"], ["TER"])
    assert len(res) == 2
    mock_session.run.assert_called_once()


def test_compare_entity_attributes_max_limit(mock_session, audit_logger):
    builder = SafeCypherBuilder(mock_session, audit_logger=audit_logger)
    too_many = [f"INF846K01D{i:02d}" for i in range(12)]
    with pytest.raises(CypherSecurityError, match="Maximum 10 entities"):
        builder.compare_entity_attributes(too_many, ["TER"])


def test_get_correction_candidates(mock_session, audit_logger):
    builder = SafeCypherBuilder(mock_session, audit_logger=audit_logger)
    mock_record = {
        "canonical_value": "0.79",
        "canonical_source": "factsheet_v17",
        "canonical_effective_date": "2026-06-01",
        "canonical_confidence": 0.9,
    }

    mock_result = MagicMock()
    mock_result.single.return_value = mock_record
    mock_session.run.return_value = mock_result

    res = builder.get_correction_candidates("INF846K01DP5", "TER", feedback_value="0.82")
    assert res["canonical_value"] == "0.79"
    assert res["feedback_asserted_value"] == "0.82"
    assert res["mismatch"] is True


def test_cypher_audit_logger(tmp_path):
    log_file = tmp_path / "test_audit.jsonl"
    logger = CypherAuditLogger(str(log_file))

    logger.log_query(
        query_method="test_method",
        parameters={"param1": "val1"},
        rows_returned=5,
        duration_ms=14.5
    )

    content = log_file.read_text()
    assert "test_method" in content
    assert '"rows_returned": 5' in content
    assert '"success": true' in content
