# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_cypher_injection.py
==============================
Security tests verifying zero Cypher injection vulnerability:
1. Identifier validation blocks malicious node labels, relationship types, and property keys
2. Safe parameterized merge & relationship building binds 100% of user data to $params
3. Tests against 10+ hostile Cypher injection payloads
4. MetricsStore.generate_neo4j_sync_cypher() outputs purely parameterized queries
"""

import pytest
from app.graph.cypher_builder import CypherBuilder, CypherSecurityError
from app.compliance.metrics_store import get_metrics_store
from app.schemas.remediation_metrics import RemediationMetrics


HOSTILE_CYPHER_PAYLOADS = [
    "' OR 1=1 --",
    "MATCH (n) DETACH DELETE n",
    "' UNION MATCH (u:User) RETURN u --",
    "\'; DROP TABLE users; --",
    'admin" OR "1"="1',
    "1; RETURN 1; //",
    "x' OR 'a'='a",
    "CALL dbms.security.createUser('hacker', 'password', false)",
    "LOAD CSV FROM 'file:///etc/passwd' AS line RETURN line",
    "' OR exists(u.password) --",
    "\x00' OR '1'='1",
]


def test_cypher_builder_blocks_malicious_identifiers():
    """Verify that identifiers containing injection characters are immediately rejected."""
    bad_identifiers = [
        "User; DETACH DELETE n; //",
        "Label' OR 1=1",
        "Node`name",
        "Rel-Type",
        "has space",
        "user--comment",
        "admin/*comment*/",
    ]
    for bad in bad_identifiers:
        with pytest.raises(CypherSecurityError):
            CypherBuilder.validate_identifier(bad)


def test_cypher_builder_accepts_valid_identifiers():
    """Verify standard alphanumeric identifiers and underscores are accepted."""
    valid_identifiers = [
        "RemediationMetrics",
        "ComplianceViolation",
        "TRACKED_BY",
        "violation_id",
        "sla_target_hours",
        "FundAuditMetadata_v2",
    ]
    for valid in valid_identifiers:
        assert CypherBuilder.validate_identifier(valid) == valid


def test_cypher_builder_parameterizes_all_hostile_payloads():
    """Verify all 10+ hostile payloads are safely bound to $params and not concatenated into query text."""
    for idx, payload in enumerate(HOSTILE_CYPHER_PAYLOADS):
        cypher, params = CypherBuilder.build_parameterized_merge(
            label="RemediationMetrics",
            id_key="remediation_id",
            id_value=f"REM_{idx}",
            properties={
                "remediation_action": payload,
                "remediation_owner_user_id": payload,
            },
            param_prefix=f"p{idx}"
        )
        # The query text must NEVER contain raw injection substrings
        assert payload not in cypher
        # The query text must contain parameter references
        assert f"$p{idx}_remediation_action" in cypher
        assert f"$p{idx}_remediation_owner_user_id" in cypher
        # Parameters dictionary must safely hold the raw payload unchanged
        assert params[f"p{idx}_remediation_action"] == payload
        assert params[f"p{idx}_remediation_owner_user_id"] == payload


def test_metrics_store_neo4j_sync_is_parameterized():
    """Verify that generate_neo4j_sync_cypher() produces safe queries with separate params."""
    store = get_metrics_store()
    # Inject an edge case remediation with potentially dangerous characters
    hostile_rem = RemediationMetrics(
        remediation_id="REM_INJECT_TEST",
        violation_id="VIO' OR '1'='1; DETACH DELETE n; //",
        severity_level="CRITICAL",
        sla_target_hours=24.0,
        sla_target_date="2026-09-03T10:00:00Z",
        detected_at="2026-09-02T10:00:00Z",
        remediation_action="Portfolio rebalance; // drop nodes",
        remediation_owner_user_id="auditor_test",
        created_at="2026-09-02T10:00:00Z",
        updated_at="2026-09-02T10:00:00Z",
    )
    store.record_remediation(hostile_rem)

    statements = store.generate_neo4j_sync_cypher()
    assert len(statements) >= 1
    for stmt in statements:
        assert isinstance(stmt, dict)
        assert "cypher" in stmt
        assert "params" in stmt
        # Raw malicious characters must not be in the Cypher query template
        assert "DETACH DELETE" not in stmt["cypher"]
        assert "$violation_id" in stmt["cypher"]
        assert ("$remediation_id" in stmt["cypher"] or "$rca_id" in stmt["cypher"])

