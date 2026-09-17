# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
cypher_validators.py
====================
Whitelist and complexity validators for Neo4j Cypher queries.
Enforces domain whitelists and structural boundaries to prevent injection and DoS.
"""

from typing import Set
import re


class CypherSecurityError(ValueError):
    """Raised when a query fails security or whitelist validation."""
    pass


# Whitelist: valid entity attributes for AMC domain
VALID_ATTRIBUTES: Set[str] = {
    "TER", "NAV", "AUM", "expense_ratio", "5yr_return", 
    "3yr_return", "1yr_return", "inception_date", "fund_manager",
    "benchmark", "risk_grade", "exit_load", "minimum_investment"
}

# Whitelist: valid entity types/labels
VALID_LABELS: Set[str] = {
    "Entity", "ISIN", "FUND", "REGULATOR", "SCHEME_CLASS",
    "AMC", "BENCHMARK_INDEX", "MUTUAL_FUND_SCHEME_NAME", "Fact"
}

# Whitelist: valid relationship types
VALID_REL_TYPES: Set[str] = {
    "HAS_FACT", "HAS_BENCHMARK", "MANAGED_BY", "REGULATED_BY",
    "GOVERNS", "BELONGS_TO", "COMPARED_WITH", "SUPERSEDES", "AMENDS"
}

_WRITE_KEYWORDS_PATTERN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH\s+DELETE|SET|REMOVE|DROP|ALTER|LOAD\s+CSV)\b",
    re.I
)
_CALL_KEYWORD_PATTERN = re.compile(r"\bCALL\b", re.I)


def validate_entity_id(entity_id: str) -> str:
    """
    Validate entity ID format.
    Accepts:
      - ISIN: 12 chars alphanumeric (e.g., INF846K01DP5)
      - Dedup key format: label::text (e.g., FUND::axis_bluechip)
      - Generic alphanumeric with underscores/hyphens (1 to 100 chars)
    """
    if not entity_id or not isinstance(entity_id, str):
        raise CypherSecurityError(f"Invalid entity_id: {entity_id}")

    entity_id_clean = entity_id.strip()

    # ISIN format: 2 letters country code + 9 alphanumeric + 1 check digit
    if re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', entity_id_clean):
        return entity_id_clean

    # Dedup key format (label::text)
    if re.match(r'^[a-zA-Z_]+::[a-zA-Z0-9_\s\-]+$', entity_id_clean):
        return entity_id_clean

    # Generic safe identifier
    if re.match(r'^[a-zA-Z0-9_\-]{1,100}$', entity_id_clean):
        return entity_id_clean

    raise CypherSecurityError(
        f"Entity ID '{entity_id}' failed whitelist validation. "
        "Allowed: ISIN format, dedup_key format, or alphanumeric with _-"
    )


def validate_attribute(attribute: str) -> str:
    """Validate attribute name against whitelist (case-sensitive check)."""
    if not attribute or not isinstance(attribute, str):
        raise CypherSecurityError(f"Invalid attribute: {attribute}")
    
    attr_clean = attribute.strip()
    if attr_clean not in VALID_ATTRIBUTES:
        # Check case-insensitive match for common attributes like 'ter' -> 'TER'
        upper_match = {a.upper(): a for a in VALID_ATTRIBUTES}
        if attr_clean.upper() in upper_match:
            return upper_match[attr_clean.upper()]
        raise CypherSecurityError(
            f"Attribute '{attribute}' not in whitelist. Allowed: {sorted(VALID_ATTRIBUTES)}"
        )
    return attr_clean


def validate_label(label: str) -> str:
    """Validate node label against whitelist."""
    if not label or not isinstance(label, str):
        raise CypherSecurityError(f"Invalid label: {label}")
    
    label_clean = label.strip()
    if label_clean not in VALID_LABELS:
        raise CypherSecurityError(
            f"Label '{label}' not in whitelist. Allowed: {sorted(VALID_LABELS)}"
        )
    return label_clean


def validate_relationship_type(rel_type: str) -> str:
    """Validate relationship type against whitelist."""
    if not rel_type or not isinstance(rel_type, str):
        raise CypherSecurityError(f"Invalid relationship type: {rel_type}")
    
    rel_clean = rel_type.strip()
    if rel_clean not in VALID_REL_TYPES:
        raise CypherSecurityError(
            f"Relationship type '{rel_type}' not in whitelist. Allowed: {sorted(VALID_REL_TYPES)}"
        )
    return rel_clean


def validate_query_complexity(cypher: str, max_match: int = 3, max_optional_match: int = 2) -> None:
    """
    Validate that an ad-hoc or LLM Cypher query satisfies complexity restrictions:
    1. Single statement (no semicolons mid-string)
    2. No write keywords (CREATE, MERGE, DELETE, DROP, SET, REMOVE)
    3. Maximum MATCH clauses <= max_match
    4. Maximum OPTIONAL MATCH clauses <= max_optional_match
    5. No UNION queries
    """
    cypher_clean = cypher.strip().rstrip(";")
    if ";" in cypher_clean:
        raise CypherSecurityError("Multiple Cypher statements not allowed.")

    if _WRITE_KEYWORDS_PATTERN.search(cypher_clean):
        raise CypherSecurityError("Write operations are strictly prohibited.")

    if "UNION" in cypher_clean.upper():
        raise CypherSecurityError("UNION queries are not supported.")

    # Count clauses
    match_count = len(re.findall(r"\bMATCH\b", cypher_clean, re.I))
    optional_match_count = len(re.findall(r"\bOPTIONAL\s+MATCH\b", cypher_clean, re.I))

    if optional_match_count > max_optional_match:
        raise CypherSecurityError(
            f"Query exceeds max OPTIONAL MATCH clauses: {optional_match_count} > {max_optional_match}"
        )

    standalone_match_count = match_count - optional_match_count
    if standalone_match_count > max_match:
        raise CypherSecurityError(
            f"Query exceeds max MATCH clauses: {standalone_match_count} > {max_match}"
        )
