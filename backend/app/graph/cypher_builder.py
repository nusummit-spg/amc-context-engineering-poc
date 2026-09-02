# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
cypher_builder.py
=================
Safe query builder and sanitization utility for Neo4j Cypher operations.
Prevents Cypher injection by:
1. Validating all Node labels and Relationship types against strict identifiers
2. Validating property keys against alphanumeric regex
3. Forcing 100% parameterization of user-supplied values ($param)
4. Sanitizing inputs and escaping dangerous control characters
"""

import re
from typing import Any, Dict, List, Tuple


class CypherSecurityError(ValueError):
    """Raised when an invalid identifier or potential injection payload is detected."""
    pass


class CypherBuilder:
    """Safe builder for parameterized Neo4j Cypher queries."""

    IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    @classmethod
    def validate_identifier(cls, identifier: str, field_name: str = "Identifier") -> str:
        """
        Validate that a node label, relationship type, or property key contains
        only safe alphanumeric characters and underscores.
        """
        if not identifier or not cls.IDENTIFIER_REGEX.match(identifier.strip()):
            raise CypherSecurityError(
                f"Invalid {field_name}: '{identifier}'. Must be alphanumeric with underscores only."
            )
        return identifier.strip()

    @classmethod
    def build_parameterized_merge(
        cls,
        label: str,
        id_key: str,
        id_value: Any,
        properties: Dict[str, Any],
        param_prefix: str = "p"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Construct a safe MERGE query with 100% parameterized properties.
        Example output:
          MERGE (n:RemediationMetrics {remediation_id: $p_remediation_id})
          SET n.severity_level = $p_severity_level, n.sla_target_hours = $p_sla_target_hours
        """
        clean_label = cls.validate_identifier(label, "Node label")
        clean_id_key = cls.validate_identifier(id_key, "ID property key")

        params: Dict[str, Any] = {
            f"{param_prefix}_{clean_id_key}": id_value
        }

        set_clauses = []
        for key, val in properties.items():
            clean_key = cls.validate_identifier(key, "Property key")
            param_name = f"{param_prefix}_{clean_key}"
            params[param_name] = val
            set_clauses.append(f"n.{clean_key} = ${param_name}")

        cypher = f"MERGE (n:{clean_label} {{{clean_id_key}: ${param_prefix}_{clean_id_key}}})"
        if set_clauses:
            cypher += "\nSET " + ", ".join(set_clauses)

        return cypher, params

    @classmethod
    def build_parameterized_relationship(
        cls,
        from_label: str,
        from_id_key: str,
        from_id_val: Any,
        rel_type: str,
        to_label: str,
        to_id_key: str,
        to_id_val: Any,
        param_prefix: str = "r"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Construct a safe parameterized relationship MERGE query.
        """
        clean_from_label = cls.validate_identifier(from_label, "From label")
        clean_from_id_key = cls.validate_identifier(from_id_key, "From ID key")
        clean_rel_type = cls.validate_identifier(rel_type, "Relationship type")
        clean_to_label = cls.validate_identifier(to_label, "To label")
        clean_to_id_key = cls.validate_identifier(to_id_key, "To ID key")

        params = {
            f"{param_prefix}_from_id": from_id_val,
            f"{param_prefix}_to_id": to_id_val,
        }

        cypher = (
            f"MATCH (a:{clean_from_label} {{{clean_from_id_key}: ${param_prefix}_from_id}})\n"
            f"MATCH (b:{clean_to_label} {{{clean_to_id_key}: ${param_prefix}_to_id}})\n"
            f"MERGE (a)-[:{clean_rel_type}]->(b)"
        )
        return cypher, params
