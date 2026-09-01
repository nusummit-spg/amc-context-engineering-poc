# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
compliance_schema.py
====================
Idempotent Neo4j constraints and indexes for the AMC Compliance Graph.
"""
import logging
from typing import Any
from app.graph.client import GraphClient

logger = logging.getLogger("graph.compliance_schema")


async def _apply_single_statement(graph: GraphClient, cypher: str, name: str) -> None:
    try:
        await graph.run(cypher)
        logger.debug("Applied compliance constraint/index: %s", name)
    except Exception as exc:
        msg = str(exc)
        if any(ign in msg for ign in ("already exists", "An equivalent constraint already exists", "IndexAlreadyExists")):
            logger.debug("Compliance constraint/index %s already exists in Neo4j", name)
        else:
            logger.warning("Could not apply compliance schema statement %s: %s", name, exc)


async def deploy_compliance_schema(graph: GraphClient) -> bool:
    """
    Deploy idempotent compliance graph schema:
    - Constraints: :Regulation(id), :Rule(id), :FundScheme(id), :Violation(id), :RiskThreshold(id), :EscalationPath(id)
    - Indexes: :Rule(rule_type), :Violation(severity), :Violation(status), :Violation(region), :Regulation(region)
    """
    constraints = [
        ("CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.id IS UNIQUE", "regulation_id"),
        ("CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE r.id IS UNIQUE", "rule_id"),
        ("CREATE CONSTRAINT fundscheme_id IF NOT EXISTS FOR (f:FundScheme) REQUIRE f.id IS UNIQUE", "fundscheme_id"),
        ("CREATE CONSTRAINT violation_id IF NOT EXISTS FOR (v:Violation) REQUIRE v.id IS UNIQUE", "violation_id"),
        ("CREATE CONSTRAINT riskthreshold_id IF NOT EXISTS FOR (t:RiskThreshold) REQUIRE t.id IS UNIQUE", "riskthreshold_id"),
        ("CREATE CONSTRAINT escalation_id IF NOT EXISTS FOR (e:EscalationPath) REQUIRE e.id IS UNIQUE", "escalation_id"),
    ]

    indexes = [
        ("CREATE INDEX idx_rule_type IF NOT EXISTS FOR (r:Rule) ON (r.rule_type)", "idx_rule_type"),
        ("CREATE INDEX idx_violation_severity IF NOT EXISTS FOR (v:Violation) ON (v.severity)", "idx_violation_severity"),
        ("CREATE INDEX idx_violation_status IF NOT EXISTS FOR (v:Violation) ON (v.status)", "idx_violation_status"),
        ("CREATE INDEX idx_violation_region IF NOT EXISTS FOR (v:Violation) ON (v.region)", "idx_violation_region"),
        ("CREATE INDEX idx_regulation_region IF NOT EXISTS FOR (r:Regulation) ON (r.region)", "idx_regulation_region"),
    ]

    try:
        for cypher, name in constraints:
            await _apply_single_statement(graph, cypher, name)
        for cypher, name in indexes:
            await _apply_single_statement(graph, cypher, name)
        logger.info("Compliance graph schema deployed successfully")
        return True
    except Exception as exc:
        logger.error("Failed to deploy compliance graph schema: %s", exc)
        return False
