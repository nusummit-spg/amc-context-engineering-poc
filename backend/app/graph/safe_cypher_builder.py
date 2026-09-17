# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
safe_cypher_builder.py
======================
Parameterized Cypher query builder preventing injection attacks for feedback evaluation.
All user-controlled inputs are whitelist-validated and parameter-bound.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from app.graph.cypher_validators import (
    CypherSecurityError,
    VALID_ATTRIBUTES,
    VALID_LABELS,
    VALID_REL_TYPES,
    validate_entity_id,
    validate_attribute,
    validate_label,
    validate_relationship_type
)
from app.graph.cypher_audit_log import CypherAuditLogger

logger = logging.getLogger("app.graph.safe_cypher")


class SafeCypherBuilder:
    """
    Parameterized Cypher query builder preventing injection attacks.
    Zero string concatenation for user-controlled data.
    """

    VALID_ATTRIBUTES = VALID_ATTRIBUTES
    VALID_LABELS = VALID_LABELS
    VALID_REL_TYPES = VALID_REL_TYPES

    def __init__(
        self,
        session: Any,
        max_rows: int = 100,
        timeout_seconds: int = 10,
        audit_logger: Optional[CypherAuditLogger] = None
    ):
        self.session = session
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
        self.audit_logger = audit_logger or CypherAuditLogger.get_logger()

    def validate_entity_id(self, entity_id: str) -> str:
        return validate_entity_id(entity_id)

    def validate_attribute(self, attribute: str) -> str:
        return validate_attribute(attribute)

    def validate_label(self, label: str) -> str:
        return validate_label(label)

    def get_entity_facts(
        self,
        entity_id: str,
        fact_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve facts for an entity using a safe parameterized query.
        """
        safe_entity_id = self.validate_entity_id(entity_id)
        safe_fact_type = self.validate_attribute(fact_type) if fact_type else None

        query = """
        MATCH (e:Entity)
        WHERE (e.dedup_key = $entity_id OR e.isin = $entity_id OR e.text = $entity_id)
        MATCH (e)-[:HAS_FACT]->(f:Fact)
        WHERE $fact_type IS NULL OR f.attribute = $fact_type
        RETURN 
            f.attribute AS attribute,
            f.value AS value,
            f.source AS source,
            f.effective_date AS effective_date,
            f.confidence AS confidence
        ORDER BY f.effective_date DESC
        LIMIT $limit
        """

        result_limit = min(limit or self.max_rows, self.max_rows)
        params = {
            "entity_id": safe_entity_id,
            "fact_type": safe_fact_type,
            "limit": result_limit
        }

        start_time = datetime.utcnow()
        try:
            result = self.session.run(
                query,
                parameters=params,
                timeout=self.timeout_seconds
            )
            rows = [dict(record) for record in result]
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.audit_logger.log_query(
                query_method="get_entity_facts",
                parameters={"entity_id": safe_entity_id, "fact_type": safe_fact_type, "limit": result_limit},
                rows_returned=len(rows),
                duration_ms=duration_ms
            )
            return rows

        except Exception as exc:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.audit_logger.log_query(
                query_method="get_entity_facts",
                parameters={"entity_id": safe_entity_id, "fact_type": safe_fact_type, "limit": result_limit},
                rows_returned=0,
                duration_ms=duration_ms,
                error=str(exc)
            )
            logger.error("SafeCypher failed: get_entity_facts | entity=%s | error=%s", safe_entity_id, exc)
            raise

    def compare_entity_attributes(
        self,
        entity_ids: List[str],
        attributes: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Compare specific attributes across multiple entities safely.
        """
        if not entity_ids:
            return []
        if len(entity_ids) > 10:
            raise CypherSecurityError("Maximum 10 entities allowed for comparison")

        safe_entity_ids = [self.validate_entity_id(eid) for eid in entity_ids]
        safe_attributes = [self.validate_attribute(attr) for attr in attributes]

        query = """
        UNWIND $entity_ids AS entity_id
        MATCH (e:Entity)
        WHERE (e.dedup_key = entity_id OR e.isin = entity_id OR e.text = entity_id)
        MATCH (e)-[:HAS_FACT]->(f:Fact)
        WHERE f.attribute IN $attributes
        RETURN 
            entity_id,
            e.text AS entity_name,
            f.attribute AS attribute,
            f.value AS value,
            f.source AS source,
            f.effective_date AS effective_date
        ORDER BY entity_id, f.attribute
        """

        params = {
            "entity_ids": safe_entity_ids,
            "attributes": safe_attributes
        }

        start_time = datetime.utcnow()
        try:
            result = self.session.run(
                query,
                parameters=params,
                timeout=self.timeout_seconds
            )
            rows = [dict(record) for record in result]
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.audit_logger.log_query(
                query_method="compare_entity_attributes",
                parameters={"entities_count": len(safe_entity_ids), "attributes": safe_attributes},
                rows_returned=len(rows),
                duration_ms=duration_ms
            )
            return rows

        except Exception as exc:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.audit_logger.log_query(
                query_method="compare_entity_attributes",
                parameters={"entities_count": len(safe_entity_ids), "attributes": safe_attributes},
                rows_returned=0,
                duration_ms=duration_ms,
                error=str(exc)
            )
            logger.error("SafeCypher failed: compare_entity_attributes | error=%s", exc)
            raise

    def get_correction_candidates(
        self,
        entity_id: str,
        attribute: str,
        feedback_value: Any
    ) -> Dict[str, Any]:
        """
        Retrieve current canonical value vs feedback-asserted value for correction evaluation.
        """
        safe_entity_id = self.validate_entity_id(entity_id)
        safe_attribute = self.validate_attribute(attribute)

        query = """
        MATCH (e:Entity)
        WHERE (e.dedup_key = $entity_id OR e.isin = $entity_id OR e.text = $entity_id)
        MATCH (e)-[:HAS_FACT]->(f:Fact {attribute: $attribute})
        RETURN 
            f.value AS canonical_value,
            f.source AS canonical_source,
            f.effective_date AS canonical_effective_date,
            f.confidence AS canonical_confidence
        ORDER BY f.effective_date DESC
        LIMIT 1
        """

        params = {
            "entity_id": safe_entity_id,
            "attribute": safe_attribute
        }

        start_time = datetime.utcnow()
        try:
            result = self.session.run(
                query,
                parameters=params,
                timeout=self.timeout_seconds
            )
            record = result.single()
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.audit_logger.log_query(
                query_method="get_correction_candidates",
                parameters={"entity_id": safe_entity_id, "attribute": safe_attribute},
                rows_returned=1 if record else 0,
                duration_ms=duration_ms
            )

            if not record:
                return {
                    "entity_id": safe_entity_id,
                    "attribute": safe_attribute,
                    "canonical_value": None,
                    "canonical_source": None,
                    "canonical_effective_date": None,
                    "canonical_confidence": None,
                    "feedback_asserted_value": feedback_value,
                    "mismatch": None,
                    "error": "No canonical value found"
                }

            if hasattr(record, "data") and callable(record.data):
                canonical = record.data()
            elif isinstance(record, dict):
                canonical = record
            else:
                canonical = dict(record)

            mismatch = str(canonical.get("canonical_value")).strip() != str(feedback_value).strip()
            return {
                "entity_id": safe_entity_id,
                "attribute": safe_attribute,
                "canonical_value": canonical.get("canonical_value"),
                "canonical_source": canonical.get("canonical_source"),
                "canonical_effective_date": canonical.get("canonical_effective_date"),
                "canonical_confidence": canonical.get("canonical_confidence"),
                "feedback_asserted_value": feedback_value,
                "mismatch": mismatch
            }

        except Exception as exc:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.audit_logger.log_query(
                query_method="get_correction_candidates",
                parameters={"entity_id": safe_entity_id, "attribute": safe_attribute},
                rows_returned=0,
                duration_ms=duration_ms,
                error=str(exc)
            )
            logger.error("SafeCypher failed: get_correction_candidates | error=%s", exc)
            raise
