# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
cypher_validator.py
===================
Security and safety validation for automated Cypher mutations proposed by the repair engine.
Blocks hazardous DDL/DML patterns and guards regulatory protected properties.
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

logger = logging.getLogger("app.services.cypher_validator")


class CypherValidator:
    """Validate Cypher mutations for safety before queuing or execution."""

    # Prohibited operations that could alter schema or cause unbounded deletion
    DENY_LIST = [
        r"\bDROP\s+INDEX\b",
        r"\bDROP\s+CONSTRAINT\b",
        r"\bCREATE\s+INDEX\b",
        r"\bCREATE\s+CONSTRAINT\b",
        r"\bDELETE\b(?![^(]*\bWHERE\b)",  # DELETE without WHERE
        r"\bDETACH\s+DELETE\b(?![^(]*\bWHERE\b)",
    ]

    # Compliance-sensitive fields that cannot be removed
    PROTECTED_FIELDS = [
        "confidence_level",
        "source_authority",
        "effective_date",
        "compliance_flag",
        "regulatory_tag",
    ]

    def validate(self, cypher: str) -> Tuple[bool, str]:
        """Validate Cypher mutation.

        Returns:
            (is_safe, reason)

        Args:
            cypher (str): The cypher.
        """
        # Check deny-list patterns
        for pattern in self.DENY_LIST:
            if re.search(pattern, cypher, re.IGNORECASE):
                return False, f"Denied: Contains prohibited operation: {pattern}"

        # Check for REMOVE on protected fields
        remove_pattern = r"\bREMOVE\s+\w+\.(\w+)"
        for match in re.finditer(remove_pattern, cypher, re.IGNORECASE):
            field = match.group(1)
            if field in self.PROTECTED_FIELDS:
                return False, f"Denied: Cannot REMOVE protected field: {field}"

        # Check for SET on protected fields (warn only, don't block)
        set_pattern = r"\bSET\s+\w+\.(\w+)\s*="
        warnings = []
        for match in re.finditer(set_pattern, cypher, re.IGNORECASE):
            field = match.group(1)
            if field in self.PROTECTED_FIELDS:
                warnings.append(f"Warning: Modifying protected field: {field}")

        if warnings:
            return True, "; ".join(warnings)

        return True, "Validation passed"

    def extract_affected_nodes(self, cypher: str) -> List[str]:
        """Extract entity IDs or names from MATCH clauses.

        Args:
            cypher (str): The cypher.

        Returns:
            List[str]: List of resulting items or records.
        """
        match_id_pattern = r"MATCH\s+\([^)]*\{id:\s*['\"]?([^'\"}\s]+)"
        matches = re.findall(match_id_pattern, cypher, re.IGNORECASE)
        if not matches:
            match_name_pattern = r"MATCH\s+\([^)]*\{name:\s*['\"]?([^'\"}\s]+)"
            matches = re.findall(match_name_pattern, cypher, re.IGNORECASE)
        return list(set(matches))


# Global singleton
_validator = CypherValidator()


def get_cypher_validator() -> CypherValidator:
    """Retrieve global CypherValidator instance.

    Returns:
        CypherValidator: Resulting CypherValidator instance.
    """
    return _validator
