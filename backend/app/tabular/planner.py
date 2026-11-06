# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
planner.py
==========
G05: Typed Deterministic Query Planner.

Tasks:
- G05-T01: Intent classification and validation (EXACT_LOOKUP, AGGREGATION, RANKING, DISTRIBUTION, COUNT)
- G05-T02: QueryPlan schema with strict parameterization and validation
- G05-T03: Parse exact key, date and period constraints
- G05-T04: Explicit filter and grouping inference policy (no silent guessing)
- G05-T05: Ambiguity detection and candidate choice emission (AMBIGUOUS_QUERY)
- G05-T06: Compile only whitelisted SQL templates with bound parameters
- G05-T09: Enforce temporal comparison policies (same-date / same-quarter rules)
- G05-T10: Metric registry validation against METRIC_REGISTRY_V1
- G05-T11: Stable tie-breaking rules
"""

from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.tabular.contracts import (
    AggregationSafety,
    METRIC_REGISTRY_V1,
    QueryErrorCode,
    Unit,
)

ALLOWED_FILTER_COLUMNS = {
    "scheme_code": "scheme_code",
    "scheme_name": "scheme_display_name",
    "amc_name": "amc_display_name",
    "amc_id": "amc_id",
    "scheme_type": "scheme_type",
    "scheme_category": "scheme_category_raw",
    "nav_date": "nav_date",
    "aaum_quarter": "aaum_quarter",
    "dataset_version": "dataset_version",
}

ALLOWED_GROUP_BY_COLUMNS = {
    "amc_id",
    "amc_display_name",
    "scheme_type",
    "scheme_category_raw",
    "aaum_quarter",
    "nav_date",
    "scheme_display_name",
}

ALLOWED_SORT_ORDERS = {"ASC", "DESC"}


class PlanIntent(str, Enum):
    """Authoritative query intents for tabular data (G05-T01)"""
    EXACT_LOOKUP = "EXACT_LOOKUP"
    AGGREGATION = "AGGREGATION"
    RANKING = "RANKING"
    DISTRIBUTION = "DISTRIBUTION"
    COUNT = "COUNT"
    AMBIGUOUS = "AMBIGUOUS"


class QueryPlan(BaseModel):
    """Validated structured execution plan for financial queries (G05-T02)"""
    plan_id: str
    intent: PlanIntent
    metric_id: str
    target_table: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    group_by: List[str] = Field(default_factory=list)
    order_by: Optional[str] = None
    order_desc: bool = True
    limit: Optional[int] = None
    dataset_version: Optional[str] = None
    unit: Optional[str] = None
    
    # Validation & Governance
    steward_approved: bool = False
    aggregation_safety: Optional[str] = None
    ambiguity_flags: List[str] = Field(default_factory=list)
    candidate_choices: List[str] = Field(default_factory=list)
    compiled_sql: Optional[str] = None
    sql_parameters: Dict[str, Any] = Field(default_factory=dict)


class QueryPlanner:
    """Compiles and validates financial questions into safe QueryPlans."""

    def __init__(self, metric_registry: Optional[Dict[str, Any]] = None):
        self.registry = metric_registry or METRIC_REGISTRY_V1

    def create_exact_nav_plan(
        self,
        scheme_code: str,
        nav_date: str,
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """Create exact NAV lookup plan for scheme + date (G05-T03, G05-T09)."""
        clean_code = str(scheme_code).strip()
        clean_date = str(nav_date).strip()
        plan_id = f"plan_nav_exact_{clean_code}_{clean_date}"
        metric_def = self.registry.get("nav_per_unit")

        filters = {
            "scheme_code": clean_code,
            "nav_date": clean_date,
        }

        sql = """
        SELECT observation_id, source_row_id, dataset_version,
               scheme_code, amc_id, scheme_id, plan_option_id,
               nav_per_unit, nav_date
        FROM nav_observations
        WHERE dataset_version = :dataset_version
          AND scheme_code = :scheme_code
          AND nav_date = :nav_date
        LIMIT 1
        """

        params = {
            "scheme_code": clean_code,
            "nav_date": clean_date,
        }
        if dataset_version:
            params["dataset_version"] = dataset_version

        return QueryPlan(
            plan_id=plan_id,
            intent=PlanIntent.EXACT_LOOKUP,
            metric_id="nav_per_unit",
            target_table="nav_observations",
            filters=filters,
            dataset_version=dataset_version,
            unit=Unit.INR_PER_UNIT.value,
            steward_approved=metric_def.steward_approved if metric_def else True,
            aggregation_safety=AggregationSafety.NO_AGGREGATION.value,
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_top_amcs_plan(
        self,
        quarter: str = "January - March 2026",
        limit: int = 10,
        sort_by: str = "total_aum",
        amc_filter: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """
        Create ranking plan for AMCs by AAUM or scheme count (G05-T10, G05-T11).
        Enforces deterministic tie-breaking (order by total_aum_cr DESC, amc_id ASC).
        """
        metric_def = self.registry.get("aaum_crore")
        steward_approved = metric_def.steward_approved if metric_def else False
        ambiguity_flags = []
        if not steward_approved:
            ambiguity_flags.append(
                "CAUTION: AAUM additivity grain pending final steward signoff (G03-T05). Result is dataset-derived."
            )

        sort_column_map = {
            "total_aum": "total_aum_cr",
            "distinct_schemes": "distinct_schemes",
            "avg_aum": "avg_aum_cr",
            "total_plans": "total_plans",
        }
        order_col = sort_column_map.get(sort_by, "total_aum_cr")

        where_clauses = [
            "dataset_version = :dataset_version",
            "validation_status = 'VALID'",
            "aaum_crore IS NOT NULL",
        ]
        params: Dict[str, Any] = {
            "limit": max(1, min(100, limit)),
        }
        if dataset_version:
            params["dataset_version"] = dataset_version

        if quarter:
            where_clauses.append("aaum_quarter = :quarter")
            params["quarter"] = quarter

        if amc_filter:
            where_clauses.append("LOWER(amc_display_name) LIKE :amc_filter")
            params["amc_filter"] = f"%{amc_filter.lower().strip()}%"

        where_sql = " AND ".join(where_clauses)

        # F02: Use Decimal-safe aggregation via Python-side calculation
        # SQL returns raw values; Decimal conversion happens in executor.py
        sql = f"""
        SELECT amc_id, 
               amc_display_name as amc,
               COUNT(DISTINCT scheme_display_name) as distinct_schemes,
               COUNT(*) as total_plans,
               aaum_crore as total_aum_cr,
               aaum_crore as avg_aum_cr
        FROM source_rows
        WHERE {where_sql}
        GROUP BY amc_id, amc_display_name
        ORDER BY {order_col} DESC, amc_id ASC
        LIMIT :limit
        """

        return QueryPlan(
            plan_id=f"plan_top_amcs_{sort_by}_{limit}",
            intent=PlanIntent.RANKING,
            metric_id="aaum_crore",
            target_table="source_rows",
            filters={"aaum_quarter": quarter, "amc_filter": amc_filter} if amc_filter else {"aaum_quarter": quarter},
            group_by=["amc_id", "amc_display_name"],
            order_by=order_col,
            order_desc=True,
            limit=limit,
            dataset_version=dataset_version,
            unit=Unit.INR_CRORE.value,
            steward_approved=steward_approved,
            aggregation_safety=AggregationSafety.PENDING_APPROVAL.value,
            ambiguity_flags=ambiguity_flags,
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_top_schemes_plan(
        self,
        limit: int = 10,
        sort_by: str = "max_aum",
        amc_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        scheme_type_filter: Optional[str] = None,
        scheme_filter: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """
        Create ranking plan for schemes aggregated by plan variants.
        Provides dual-view scheme metrics.
        """
        where_clauses = [
            "dataset_version = :dataset_version",
            "validation_status = 'VALID'",
            "aaum_crore IS NOT NULL",
        ]
        params: Dict[str, Any] = {
            "limit": max(1, min(100, limit)),
        }
        if dataset_version:
            params["dataset_version"] = dataset_version

        if amc_filter:
            where_clauses.append("LOWER(amc_display_name) LIKE :amc_filter")
            params["amc_filter"] = f"%{amc_filter.lower().strip()}%"
        if category_filter:
            where_clauses.append("LOWER(scheme_category_raw) LIKE :cat_filter")
            params["cat_filter"] = f"%{category_filter.lower().strip()}%"
        if scheme_type_filter:
            where_clauses.append("LOWER(scheme_type) LIKE :type_filter")
            params["type_filter"] = f"%{scheme_type_filter.lower().strip()}%"
        if scheme_filter:
            where_clauses.append("LOWER(scheme_display_name) LIKE :sch_filter")
            params["sch_filter"] = f"%{scheme_filter.lower().strip()}%"

        sort_map = {
            "max_aum": "max_aum_cr",
            "avg_aum": "avg_aum_cr",
            "total_aum": "total_aum_cr",
            "plan_count": "plan_count",
        }
        order_col = sort_map.get(sort_by, "max_aum_cr")

        where_sql = " AND ".join(where_clauses)

        sql = f"""
        SELECT scheme_display_name as scheme_name,
               scheme_code,
               amc_display_name as amc,
               scheme_type,
               scheme_category_raw as scheme_category,
               aaum_crore as max_aum_cr,
               aaum_crore as min_aum_cr,
               aaum_crore as avg_aum_cr,
               aaum_crore as total_aum_cr,
               COUNT(*) as plan_count,
               GROUP_CONCAT(plan_option_display_name, ' | ') as plan_variants,
               nav_per_unit as latest_nav,
               nav_date as latest_nav_date,
               launch_date as launch_date,
               closure_date as closure_date,
               aaum_quarter as data_quarter,
               source_row_id
        FROM source_rows
        WHERE {where_sql}
        GROUP BY scheme_display_name
        ORDER BY {order_col} DESC, scheme_display_name ASC
        LIMIT :limit
        """

        return QueryPlan(
            plan_id=f"plan_top_schemes_{sort_by}_{limit}",
            intent=PlanIntent.RANKING,
            metric_id="aaum_crore",
            target_table="source_rows",
            filters={
                "amc_filter": amc_filter,
                "category_filter": category_filter,
                "scheme_type_filter": scheme_type_filter,
                "scheme_filter": scheme_filter,
            },
            group_by=["scheme_display_name"],
            order_by=order_col,
            order_desc=True,
            limit=limit,
            dataset_version=dataset_version,
            unit=Unit.INR_CRORE.value,
            steward_approved=False,
            aggregation_safety=AggregationSafety.PENDING_APPROVAL.value,
            ambiguity_flags=["CAUTION: AAUM additivity across plan options pending steward review (G03-T05)."],
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_top_nav_schemes_plan(
        self,
        limit: int = 10,
        scheme_type: Optional[str] = None,
        category_keyword: Optional[str] = None,
        plan_keyword: Optional[str] = None,
        exclude_idcw: bool = False,
        sort_order: str = "desc",
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """
        Create plan for schemes ranked by NAV (G05-T04, G05-T09).
        G05-T04: Disallows default filters unless explicitly requested!
        G05-T09: Flags cross-date comparability if NAV dates differ.
        """
        where_clauses = [
            "dataset_version = :dataset_version",
            "validation_status = 'VALID'",
            "nav_per_unit IS NOT NULL",
        ]
        params: Dict[str, Any] = {
            "limit": max(1, min(100, limit)),
        }
        if dataset_version:
            params["dataset_version"] = dataset_version

        applied_filters: Dict[str, Any] = {}
        if scheme_type:
            where_clauses.append("LOWER(scheme_type) LIKE :stype")
            params["stype"] = f"%{scheme_type.lower().strip()}%"
            applied_filters["scheme_type"] = scheme_type

        if category_keyword:
            where_clauses.append("LOWER(scheme_category_raw) LIKE :cat")
            params["cat"] = f"%{category_keyword.lower().strip()}%"
            applied_filters["category_keyword"] = category_keyword

        if plan_keyword:
            where_clauses.append("LOWER(plan_option_display_name) LIKE :plan")
            params["plan"] = f"%{plan_keyword.lower().strip()}%"
            applied_filters["plan_keyword"] = plan_keyword

        if exclude_idcw:
            where_clauses.append(
                "LOWER(plan_option_display_name) NOT LIKE '%idcw%' AND LOWER(plan_option_display_name) NOT LIKE '%dividend%'"
            )
            applied_filters["exclude_idcw"] = True

        sort_dir = "ASC" if sort_order.lower() == "asc" else "DESC"
        where_sql = " AND ".join(where_clauses)

        sql = f"""
        SELECT scheme_display_name as scheme_name,
               plan_option_display_name as plan_name,
               amc_display_name as amc,
               nav_per_unit as nav,
               nav_date as latest_nav_date,
               scheme_type,
               scheme_category_raw as scheme_category,
               source_row_id
        FROM source_rows
        WHERE {where_sql}
        ORDER BY nav_per_unit {sort_dir}, scheme_code ASC
        LIMIT :limit
        """

        ambiguity_flags = [
            "CAUTION: Net Asset Values reflect observation dates in the dataset; cross-date rankings assume historical as-of comparability (G03-T06)."
        ]

        return QueryPlan(
            plan_id=f"plan_top_nav_{sort_dir}_{limit}",
            intent=PlanIntent.RANKING,
            metric_id="nav_per_unit",
            target_table="source_rows",
            filters=applied_filters,
            order_by="nav",
            order_desc=(sort_dir == "DESC"),
            limit=limit,
            dataset_version=dataset_version,
            unit=Unit.INR_PER_UNIT.value,
            steward_approved=True,
            aggregation_safety=AggregationSafety.NO_AGGREGATION.value,
            ambiguity_flags=ambiguity_flags,
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_dataset_summary_plan(
        self,
        scheme_type_filter: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """Create plan for dataset-wide metrics and scheme-type summary."""
        where_clauses = [
            "dataset_version = :dataset_version",
            "validation_status = 'VALID'",
        ]
        params: Dict[str, Any] = {}
        if dataset_version:
            params["dataset_version"] = dataset_version

        if scheme_type_filter:
            where_clauses.append("LOWER(scheme_type) LIKE :stype")
            params["stype"] = f"%{scheme_type_filter.lower().strip()}%"

        where_sql = " AND ".join(where_clauses)

        sql = f"""
        SELECT COUNT(*) as total_folios,
               COUNT(DISTINCT scheme_display_name) as distinct_schemes,
               COUNT(DISTINCT amc_id) as total_amcs,
               aaum_crore as total_market_aum_cr
        FROM source_rows
        WHERE {where_sql}
        """

        return QueryPlan(
            plan_id="plan_dataset_summary",
            intent=PlanIntent.AGGREGATION,
            metric_id="aaum_crore",
            target_table="source_rows",
            filters={"scheme_type_filter": scheme_type_filter} if scheme_type_filter else {},
            dataset_version=dataset_version,
            unit=Unit.INR_CRORE.value,
            steward_approved=True,
            aggregation_safety=AggregationSafety.SUMMABLE.value,
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_category_aum_breakdown_plan(
        self,
        detailed: bool = False,
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """Create category breakdown plan."""
        group_col = "scheme_category_raw" if detailed else "scheme_category_raw"
        params: Dict[str, Any] = {}
        if dataset_version:
            params["dataset_version"] = dataset_version

        sql = f"""
        SELECT {group_col} as category,
               COUNT(DISTINCT scheme_display_name) as distinct_schemes,
               COUNT(*) as total_folios,
               aaum_crore as total_aum_cr
        FROM source_rows
        WHERE dataset_version = :dataset_version
          AND validation_status = 'VALID'
        GROUP BY {group_col}
        ORDER BY total_aum_cr DESC
        """

        return QueryPlan(
            plan_id="plan_category_breakdown",
            intent=PlanIntent.DISTRIBUTION,
            metric_id="aaum_crore",
            target_table="source_rows",
            group_by=[group_col],
            order_by="total_aum_cr",
            order_desc=True,
            dataset_version=dataset_version,
            unit=Unit.INR_CRORE.value,
            steward_approved=True,
            aggregation_safety=AggregationSafety.SUMMABLE.value,
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_scheme_type_distribution_plan(
        self,
        limit: int = 5,
        sort_by: str = "total_aum",
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """Create plan for scheme type distribution by AMC."""
        params: Dict[str, Any] = {
            "limit": max(1, min(50, limit)),
        }
        if dataset_version:
            params["dataset_version"] = dataset_version

        sql = """
        SELECT amc_id, amc_display_name, scheme_type,
               COUNT(DISTINCT scheme_display_name) as scheme_count,
               aaum_crore as aum_cr
        FROM source_rows
        WHERE dataset_version = :dataset_version
          AND validation_status = 'VALID'
        GROUP BY amc_id, amc_display_name, scheme_type
        ORDER BY amc_id, scheme_type
        """

        return QueryPlan(
            plan_id=f"plan_scheme_type_dist_{limit}",
            intent=PlanIntent.DISTRIBUTION,
            metric_id="scheme_count",
            target_table="source_rows",
            group_by=["amc_id", "scheme_type"],
            limit=limit,
            dataset_version=dataset_version,
            unit=Unit.COUNT.value,
            steward_approved=True,
            aggregation_safety=AggregationSafety.SUMMABLE.value,
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_scheme_count_plan(
        self,
        filters: Optional[Dict[str, Any]] = None,
        group_by: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> QueryPlan:
        """Create a plan to count schemes or records (G05-T11)."""
        filters = filters or {}
        params: Dict[str, Any] = {}
        where_clauses = ["dataset_version = :dataset_version"]

        if dataset_version:
            params["dataset_version"] = dataset_version

        for k, v in filters.items():
            col = ALLOWED_FILTER_COLUMNS.get(k.lower())
            if col and v is not None:
                param_key = f"filter_{col}"
                where_clauses.append(f"{col} = :{param_key}")
                params[param_key] = v

        where_sql = " AND ".join(where_clauses)

        if group_by and group_by in ALLOWED_GROUP_BY_COLUMNS:
            sql = f"""
            SELECT {group_by}, COUNT(*) as count
            FROM source_rows
            WHERE {where_sql} AND validation_status = 'VALID'
            GROUP BY {group_by}
            ORDER BY count DESC
            """
            intent = PlanIntent.DISTRIBUTION
            gb = [group_by]
        else:
            sql = f"""
            SELECT COUNT(*) as count
            FROM source_rows
            WHERE {where_sql} AND validation_status = 'VALID'
            """
            intent = PlanIntent.COUNT
            gb = []

        return QueryPlan(
            plan_id="plan_scheme_count",
            intent=intent,
            metric_id="scheme_count",
            target_table="source_rows",
            filters=filters,
            group_by=gb,
            dataset_version=dataset_version,
            unit=Unit.COUNT.value,
            steward_approved=True,
            aggregation_safety=AggregationSafety.SUMMABLE.value,
            compiled_sql=sql.strip(),
            sql_parameters=params,
        )

    def create_ambiguous_plan(
        self,
        reason: str,
        candidate_choices: List[str],
        metric_id: str = "ambiguous",
    ) -> QueryPlan:
        """Create an explicit AMBIGUOUS_QUERY plan returning candidates (G05-T05)."""
        return QueryPlan(
            plan_id=f"plan_ambiguous_{len(candidate_choices)}",
            intent=PlanIntent.AMBIGUOUS,
            metric_id=metric_id,
            target_table="source_rows",
            ambiguity_flags=[reason],
            candidate_choices=candidate_choices,
            steward_approved=False,
            compiled_sql=None,
        )

    def validate_plan(self, plan: QueryPlan) -> Tuple[bool, Optional[str]]:
        """Validate safety rules against MetricRegistry (G05-T03, G05-T04)."""
        if plan.intent == PlanIntent.AMBIGUOUS:
            msg = plan.ambiguity_flags[0] if plan.ambiguity_flags else "Query is ambiguous"
            return False, f"{QueryErrorCode.AMBIGUOUS_QUERY.value}: {msg}"

        metric_def = self.registry.get(plan.metric_id)
        if not metric_def and plan.metric_id not in ("record_count", "scheme_count", "aaum_crore", "nav_per_unit"):
            return False, f"{QueryErrorCode.UNSUPPORTED_METRIC.value}: Metric '{plan.metric_id}' not in MetricRegistry"

        # Aggregation safety check (G05-T04: block illegal SUM on NAV per unit)
        if metric_def:
            if metric_def.aggregation_safety == AggregationSafety.NO_AGGREGATION and plan.intent in (
                PlanIntent.AGGREGATION,
            ):
                return False, f"ILLEGAL_AGGREGATION: Metric '{plan.metric_id}' has NO_AGGREGATION policy"

        return True, None


__all__ = [
    "PlanIntent",
    "QueryPlan",
    "QueryPlanner",
    "ALLOWED_FILTER_COLUMNS",
    "ALLOWED_GROUP_BY_COLUMNS",
]
