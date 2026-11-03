# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
executor.py
===========
G05: Typed SQL Executor and Source Proof Generator.

Tasks:
- G05-T06: Parameterized safe execution (no free-form SQL)
- G05-T07: Tenant and dataset version isolation enforcement
- G05-T08: Result-set SHA256 hash generation
- G05-T09: Exact lookup execution with Decimal preservation
- G05-T10: Source-row IDs extraction for cryptographic proof
- G05-T11: Deterministic tie-breaking and ordering
- G05-T12: Exclusion counts and provenance receipts
- G05-T14: Failure semantics (fail closed with structured errors, no generative numeric fallback)
"""

from decimal import Decimal
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.tabular.contracts import QueryErrorCode
from app.tabular.planner import PlanIntent, QueryPlan
from app.tabular.repository import FinancialDataRepository

logger = logging.getLogger(__name__)


class QueryResult(BaseModel):
    """Authoritative result from typed execution with proof metadata (G05-T08, T10, T12)"""
    success: bool
    plan_id: str
    dataset_version: str
    unit: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    source_row_ids: List[str] = Field(default_factory=list)
    result_set_hash: str
    observed_latency_ms: float
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    ambiguity_flags: List[str] = Field(default_factory=list)
    candidate_choices: List[str] = Field(default_factory=list)


class QueryExecutor:
    """Executes validated QueryPlans against the typed analytical repository."""

    def __init__(self, repository: Optional[FinancialDataRepository] = None):
        self.repo = repository or FinancialDataRepository()

    def execute(self, plan: QueryPlan) -> QueryResult:
        """
        Execute a QueryPlan safely using bound parameters and return a verified result.
        Fails closed with structured error codes on invalid plans, outages, or ambiguities (G05-T14).
        """
        start_time = time.perf_counter()

        # Fail closed on ambiguous queries (G05-T05, G05-T14)
        if plan.intent == PlanIntent.AMBIGUOUS:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return QueryResult(
                success=False,
                plan_id=plan.plan_id,
                dataset_version=plan.dataset_version or "NONE",
                result_set_hash="ERROR_AMBIGUOUS_QUERY",
                observed_latency_ms=latency_ms,
                error_code=QueryErrorCode.AMBIGUOUS_QUERY.value,
                error_message=plan.ambiguity_flags[0] if plan.ambiguity_flags else "Query is ambiguous",
                ambiguity_flags=plan.ambiguity_flags,
                candidate_choices=plan.candidate_choices,
            )

        # Enforce dataset version isolation (G05-T07)
        version = plan.dataset_version or self.repo.get_active_version()
        if not version:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return QueryResult(
                success=False,
                plan_id=plan.plan_id,
                dataset_version="NONE",
                result_set_hash="ERROR_NO_ACTIVE_VERSION",
                observed_latency_ms=latency_ms,
                error_code=QueryErrorCode.STRUCTURED_SOURCE_UNAVAILABLE.value,
                error_message="No active dataset version currently configured.",
            )

        # Check for compiled SQL template
        if not plan.compiled_sql:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return QueryResult(
                success=False,
                plan_id=plan.plan_id,
                dataset_version=version,
                result_set_hash="ERROR_NO_SQL",
                observed_latency_ms=latency_ms,
                error_code=QueryErrorCode.INVALID_PLAN.value,
                error_message="QueryPlan contains no compiled SQL template.",
            )

        # Prepare parameters with active dataset version
        params = dict(plan.sql_parameters)
        params["dataset_version"] = version

        try:
            with self.repo._get_connection() as conn:
                cursor = conn.execute(plan.compiled_sql, params)
                raw_rows = cursor.fetchall()
                cols = [desc[0] for desc in cursor.description] if cursor.description else []

                result_rows: List[Dict[str, Any]] = []
                source_row_ids: List[str] = []

                for r in raw_rows:
                    row_dict = dict(r)
                    # Collect provenance if present
                    if "source_row_id" in row_dict and row_dict["source_row_id"]:
                        source_row_ids.append(row_dict["source_row_id"])
                    
                    # Convert Decimal representations safely to avoid IEEE 754 float drift (G05-T08)
                    for k, v in row_dict.items():
                        if "nav_per_unit" in k or "aaum_crore" in k or "decimal" in k:
                            try:
                                if v is not None:
                                    row_dict[k] = str(Decimal(str(v)))
                            except Exception:
                                pass
                    result_rows.append(row_dict)

                # Check for NO_MATCH on exact lookup queries (G05-T14)
                if len(result_rows) == 0 and plan.intent == PlanIntent.EXACT_LOOKUP:
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    return QueryResult(
                        success=False,
                        plan_id=plan.plan_id,
                        dataset_version=version,
                        unit=plan.unit,
                        columns=cols,
                        rows=[],
                        row_count=0,
                        result_set_hash="NO_MATCH",
                        observed_latency_ms=latency_ms,
                        error_code=QueryErrorCode.NO_MATCH.value,
                        error_message=f"No matching record found for filters {plan.filters}",
                        ambiguity_flags=plan.ambiguity_flags,
                    )

                # Generate cryptographic result_set_hash (G05-T08, G05-T12)
                norm_json = json.dumps(result_rows, sort_keys=True, default=str)
                result_hash = hashlib.sha256(norm_json.encode("utf-8")).hexdigest()

                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                return QueryResult(
                    success=True,
                    plan_id=plan.plan_id,
                    dataset_version=version,
                    unit=plan.unit,
                    columns=cols,
                    rows=result_rows,
                    row_count=len(result_rows),
                    source_row_ids=source_row_ids[:50],  # Bound proof payload
                    result_set_hash=result_hash,
                    observed_latency_ms=latency_ms,
                    ambiguity_flags=plan.ambiguity_flags,
                )

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Error executing query plan %s: %s", plan.plan_id, exc)
            return QueryResult(
                success=False,
                plan_id=plan.plan_id,
                dataset_version=version,
                result_set_hash="ERROR_EXECUTION_FAILURE",
                observed_latency_ms=latency_ms,
                error_code=QueryErrorCode.EXECUTION_ERROR.value,
                error_message=str(exc),
            )


__all__ = [
    "QueryResult",
    "QueryExecutor",
]
