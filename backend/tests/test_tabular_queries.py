# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_tabular_queries.py
=======================
G05 Assurance Test Suite: Typed Deterministic Financial Queries.

Verifies:
- E01: Exact NAV lookup for scheme code 100033 on 2026-06-29 (922.67 INR_PER_UNIT)
- E02: Total records in snapshot reconciliation (16,245 rows)
- E03: Top 5 AMCs by AAUM with deterministic tie-breaking and proof hash
- E04: Open ended vs close ended distribution for top 5 AMCs
- E05: Ambiguous query handling and candidate choice emission (fail-closed)
- E06: NAV ranking with explicit filters (no silent guessing) and temporal policy
- E07: Non-existent scheme lookup yields NO_MATCH (zero fabricated values)
- SQL injection immunity via parameterized templates
- Version isolation enforcement (stale/unapproved version rejection)
- Illegal aggregation prevention (blocking SUM on NAV per unit)
- SchemeAggregationService compatibility facade (G05-T13)
- FastPathInterceptor exact NAV lookup integration
"""

import asyncio
from decimal import Decimal
from pathlib import Path
import pytest
import sys

# Ensure backend is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.tabular.contracts import AggregationSafety, QueryErrorCode, Unit
from app.tabular.planner import PlanIntent, QueryPlan, QueryPlanner
from app.tabular.executor import QueryExecutor, QueryResult
from app.tabular.repository import FinancialDataRepository
from app.services.scheme_aggregation_service import (
    SchemeAggregationService,
    get_aggregation_service,
    reset_aggregation_service,
)
from app.retrieval.fast_path_interceptor import FastPathInterceptor


@pytest.fixture(scope="module")
def repo():
    return FinancialDataRepository()


@pytest.fixture(scope="module")
def planner():
    return QueryPlanner()


@pytest.fixture(scope="module")
def executor(repo):
    return QueryExecutor(repo)


@pytest.fixture(scope="module")
def service():
    reset_aggregation_service()
    return get_aggregation_service()


class TestG05GoldenQueries:
    """Golden financial correctness tests (03_CSV_EXCEL_SPEC §8)"""

    def test_e01_exact_nav_lookup_golden(self, planner, executor):
        """Case E01: Exact NAV for scheme code 100033 on 2026-06-29 == 922.67."""
        plan = planner.create_exact_nav_plan(
            scheme_code="100033",
            nav_date="2026-06-29",
            dataset_version="v1_baseline",
        )
        is_valid, err = planner.validate_plan(plan)
        assert is_valid, f"Plan validation failed: {err}"

        result = executor.execute(plan)
        assert result.success is True
        assert result.row_count == 1
        assert len(result.rows) == 1

        row = result.rows[0]
        assert str(row["scheme_code"]) == "100033"
        assert str(row["nav_date"]) == "2026-06-29"
        assert Decimal(str(row["nav_per_unit"])) == Decimal("922.67")

        # Provenance verification (G05-T10, G05-T12)
        assert len(result.source_row_ids) == 1
        assert len(result.source_row_ids[0]) == 64  # SHA256 hex string
        assert len(result.result_set_hash) == 64
        assert result.dataset_version == "v1_baseline"
        assert result.unit == Unit.INR_PER_UNIT.value

    def test_e02_record_count_reconciliation(self, planner, executor, repo):
        """Case E02: Total records in snapshot reconciliation equals exactly 16,245."""
        plan = planner.create_scheme_count_plan(dataset_version="v1_baseline")
        result = executor.execute(plan)

        assert result.success is True
        assert len(result.rows) == 1
        total_count = result.rows[0]["count"]
        assert total_count == 16245

        # Check repository summary stats
        stats = repo.get_summary_stats("v1_baseline")
        assert stats["total_source_rows"] == 16245
        assert stats["valid_rows"] == 16245
        assert stats["quarantined_rows"] == 0
        assert stats["nav_observations"] == 14208
        assert stats["aaum_observations"] == 8178

    def test_e03_top_5_amcs_aaum_ranking(self, planner, executor):
        """Case E03: Top 5 AMCs by AAUM in Q1 2026 with deterministic tie-breaking."""
        plan = planner.create_top_amcs_plan(
            quarter="January - March 2026",
            limit=5,
            sort_by="total_aum",
            dataset_version="v1_baseline",
        )
        is_valid, err = planner.validate_plan(plan)
        assert is_valid

        result = executor.execute(plan)
        assert result.success is True
        assert result.row_count == 5

        # Verify descending order
        aums = [float(r["total_aum_cr"]) for r in result.rows]
        assert aums == sorted(aums, reverse=True), "Top AMCs must be sorted descending"
        assert aums[0] > aums[4], "First AMC must have higher AUM than 5th"

        # Check provenance and governance caution
        assert len(result.result_set_hash) == 64
        assert any("AAUM additivity grain pending" in flag for flag in result.ambiguity_flags)

    def test_e04_scheme_type_distribution(self, service):
        """Case E04: Open ended vs close ended scheme distribution for top AMCs."""
        dist = service.get_scheme_type_distribution_by_amc(limit=5, sort_by="total_aum")
        assert isinstance(dist, list)
        assert len(dist) == 5

        for amc_info in dist:
            assert "amc" in amc_info
            assert "total_distinct_schemes" in amc_info
            assert "scheme_type_breakdown" in amc_info
            breakdown = amc_info["scheme_type_breakdown"]
            assert len(breakdown) > 0

            # Sum of percentages should be ~100%
            total_pct = sum(item["pct"] for item in breakdown.values())
            assert 99.0 <= total_pct <= 101.0, f"Percentages must sum to ~100%, got {total_pct}"

    def test_e05_ambiguous_query_handling(self, planner, executor):
        """Case E05: Ambiguous query returns candidate choices instead of guessing (G05-T05)."""
        candidates = ["SBI Nifty 50 ETF", "SBI Small Cap Fund", "SBI Bluechip Fund"]
        plan = planner.create_ambiguous_plan(
            reason="Multiple SBI funds match query; please specify canonical scheme name or code.",
            candidate_choices=candidates,
        )
        is_valid, err = planner.validate_plan(plan)
        assert is_valid is False
        assert QueryErrorCode.AMBIGUOUS_QUERY.value in err

        result = executor.execute(plan)
        assert result.success is False
        assert result.error_code == QueryErrorCode.AMBIGUOUS_QUERY.value
        assert result.candidate_choices == candidates
        assert len(result.rows) == 0

    def test_e06_top_nav_ranking_explicit_filters(self, planner, executor):
        """Case E06: NAV ranking with explicit filters and temporal policy warning (G05-T04, G05-T09)."""
        plan = planner.create_top_nav_schemes_plan(
            limit=5,
            scheme_type="Open Ended",
            category_keyword="Equity",
            sort_order="desc",
            dataset_version="v1_baseline",
        )
        result = executor.execute(plan)
        assert result.success is True
        assert result.row_count == 5

        # Verify sorted descending
        navs = [float(r["nav"]) for r in result.rows]
        assert navs == sorted(navs, reverse=True)

        # G05-T09: Explicit temporal policy warning attached
        assert any("historical as-of comparability" in flag for flag in result.ambiguity_flags)

    def test_e07_no_match_semantics(self, planner, executor):
        """Case E07: Non-existent scheme returns NO_MATCH with zero fabricated values (G05-T14)."""
        plan = planner.create_exact_nav_plan(
            scheme_code="99999999",
            nav_date="2026-06-29",
            dataset_version="v1_baseline",
        )
        result = executor.execute(plan)
        assert result.success is False
        assert result.error_code == QueryErrorCode.NO_MATCH.value
        assert result.row_count == 0
        assert len(result.rows) == 0

    def test_sql_injection_safety(self, planner, executor):
        """G05-T06: Injection strings cannot alter SQL plan or execute commands."""
        malicious_input = "100033' OR '1'='1"
        plan = planner.create_exact_nav_plan(
            scheme_code=malicious_input,
            nav_date="2026-06-29",
            dataset_version="v1_baseline",
        )
        # Parameterized execution treats malicious_input as a literal string
        result = executor.execute(plan)
        assert result.success is False
        assert result.error_code == QueryErrorCode.NO_MATCH.value

    def test_version_isolation(self, planner, executor):
        """G05-T07: Stale or unapproved dataset versions are isolated/rejected."""
        plan = planner.create_exact_nav_plan(
            scheme_code="100033",
            nav_date="2026-06-29",
            dataset_version="v999_unapproved",
        )
        result = executor.execute(plan)
        # Version has 0 rows, so returns NO_MATCH
        assert result.success is False
        assert result.error_code == QueryErrorCode.NO_MATCH.value

    def test_aggregation_safety_blocks_nav_sum(self, planner):
        """G05-T04: Block illegal aggregation (e.g. SUM on NAV per unit)."""
        plan = QueryPlan(
            plan_id="plan_illegal_sum_nav",
            intent=PlanIntent.AGGREGATION,
            metric_id="nav_per_unit",
            target_table="nav_observations",
            compiled_sql="SELECT SUM(CAST(nav_per_unit AS REAL)) FROM nav_observations",
        )
        is_valid, err = planner.validate_plan(plan)
        assert is_valid is False
        assert "ILLEGAL_AGGREGATION" in err


class TestCompatibilityFacade:
    """G05-T13: Verify SchemeAggregationService compatibility facade."""

    def test_facade_top_schemes(self, service):
        """Verify get_top_schemes returns valid DualViewAUMResponse."""
        resp = service.get_top_schemes(limit=5, sort_by="max_aum")
        assert len(resp.scheme_level_rankings) == 5
        assert len(resp.plan_level_rankings) > 0
        assert resp.total_unique_schemes == 5
        assert resp.data_completeness == 1.0

        first = resp.scheme_level_rankings[0]
        assert first.max_aum_cr >= first.min_aum_cr
        assert first.plan_count >= 1

    def test_facade_top_amcs(self, service):
        """Verify get_top_amcs returns valid AMCAggregationResponse."""
        resp = service.get_top_amcs(limit=5, sort_by="total_aum")
        assert len(resp.amc_rankings) == 5
        assert resp.total_unique_amcs > 20
        assert resp.amc_rankings[0].rank == 1
        assert resp.amc_rankings[0].total_aum_cr >= resp.amc_rankings[1].total_aum_cr

    def test_facade_dataset_summary(self, service):
        """Verify get_dataset_summary returns accurate market totals."""
        summary = service.get_dataset_summary()
        assert summary["total_folios"] == 16245
        assert summary["total_distinct_schemes"] > 1000
        assert summary["total_market_aum_cr"] > 1000000
        assert "types_breakdown" in summary
        assert "Open Ended" in summary["types_breakdown"]

    def test_facade_category_breakdown(self, service):
        """Verify get_category_aum_breakdown returns CategoryAggregationResponse."""
        resp = service.get_category_aum_breakdown()
        assert len(resp.categories) > 0
        assert resp.total_folios == 16245
        assert resp.categories[0].rank == 1

    def test_facade_top_nav(self, service):
        """Verify get_top_nav_schemes returns NAVAggregationResponse."""
        resp = service.get_top_nav_schemes(limit=5, sort_order="desc")
        assert len(resp.schemes) == 5
        assert resp.schemes[0].rank == 1
        assert resp.schemes[0].nav >= resp.schemes[1].nav

    def test_facade_exact_nav_lookup(self, service):
        """Verify lookup_exact_nav returns exact Decimal NAV and source anchor."""
        rec = service.lookup_exact_nav("100033", "2026-06-29")
        assert rec is not None
        assert str(rec["scheme_code"]) == "100033"
        assert str(rec["nav_date"]) == "2026-06-29"
        assert Decimal(str(rec["nav_per_unit"])) == Decimal("922.67")
        assert len(rec["source_row_id"]) == 64


class TestFastPathExactNAVIntegration:
    """Verify FastPathInterceptor handles exact NAV lookup deterministically."""

    @pytest.mark.asyncio
    async def test_fast_path_exact_nav_query(self):
        interceptor = FastPathInterceptor()
        query = "What is the NAV for scheme code 100033 on 2026-06-29?"
        resp = await interceptor.intercept(query)

        assert resp is not None
        assert resp.synthesis is not None
        assert "922.67" in resp.synthesis.answer
        assert "100033" in resp.synthesis.answer
        assert resp.synthesis.confidence == "high"
        assert len(resp.synthesis.structured_rows) == 1
        assert resp.synthesis.structured_rows[0]["nav_per_unit"] == "922.67"
