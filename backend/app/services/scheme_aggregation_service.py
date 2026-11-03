# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
services/scheme_aggregation_service.py
======================================
G05-T13: Compatibility Facade for Typed Financial Aggregations.

Materializes aggregated metrics from canonical typed analytical store (financial.db),
with automatic fallback to CSV/chunks in-memory loading when database is unavailable.
Preserves existing API contract and returns typed Pydantic models.
"""

from collections import defaultdict
from datetime import datetime
import glob
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.models.scheme_aggregation import (
    AMCAggregationMetrics,
    AMCAggregationResponse,
    CategoryAggregationMetrics,
    CategoryAggregationResponse,
    DualViewAUMResponse,
    NAVAggregationMetrics,
    NAVAggregationResponse,
    SchemeAggregationMetrics,
    SchemeAggregationRequest,
)
from app.tabular.planner import QueryPlanner
from app.tabular.executor import QueryExecutor
from app.tabular.repository import FinancialDataRepository

logger = logging.getLogger(__name__)


class SchemeAggregationService:
    """
    Compatibility Facade over the canonical typed query engine (G05-T13).
    
    Key responsibilities:
    1. Query verified SQLite analytical store (financial.db) via QueryPlanner & QueryExecutor
    2. Enforce active dataset version isolation (G05-T07)
    3. Provide dual-view responses (plan-level + scheme-level) with cryptographic provenance
    4. Maintain backward compatibility with in-memory CSV/chunks fallback
    """

    def __init__(self, csv_path: Optional[str] = None, use_chunks: bool = True):
        self.use_chunks = use_chunks
        self.df: Optional[pd.DataFrame] = None
        self.df_full: Optional[pd.DataFrame] = None
        self._conn: Optional[sqlite3.Connection] = None
        self.scheme_aggregations = None
        self.chunk_manifest = None
        self.csv_path = None
        self.chunks_dir = None

        # G05: Initialize Typed Financial Repository & Engine
        self.repo = FinancialDataRepository()
        self.planner = QueryPlanner()
        self.executor = QueryExecutor(self.repo)
        self.use_db = False
        self.active_version = None

        try:
            active_ver = self.repo.get_active_version()
            if active_ver:
                with self.repo._get_connection() as conn:
                    cnt = conn.execute(
                        "SELECT COUNT(*) FROM source_rows WHERE dataset_version = ? AND validation_status = 'VALID'",
                        (active_ver,)
                    ).fetchone()[0]
                    if cnt > 0:
                        self.use_db = True
                        self.active_version = active_ver
                        logger.info(
                            "✓ SchemeAggregationService facade active over typed financial.db (version: %s, %d rows)",
                            active_ver, cnt
                        )
        except Exception as exc:
            logger.warning("Could not connect to typed financial.db (%s); fallback to file loading", exc)
            self.use_db = False

        if not self.use_db:
            self._init_legacy_file_loading(csv_path, use_chunks)

    def _init_legacy_file_loading(self, csv_path: Optional[str], use_chunks: bool) -> None:
        """Fallback initialization for CSV / chunk files if DB is uninitialized."""
        project_root = Path(__file__).resolve().parent.parent.parent
        if csv_path is None:
            default_csv = project_root / "data" / "source_docs" / "mutual_fund_data.csv"
            chunks_dir = project_root / "data" / "source_docs" / "chunks"
            if use_chunks and chunks_dir.exists():
                self.chunks_dir = chunks_dir
                self.csv_path = None
            else:
                self.chunks_dir = None
                self.csv_path = default_csv
        else:
            p = Path(csv_path)
            chunks_dir = p.parent / "chunks"
            if use_chunks and chunks_dir.exists():
                self.chunks_dir = chunks_dir
                self.csv_path = None
            else:
                self.chunks_dir = None
                self.csv_path = p

        self._load_data()

    def _add_derived_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add Broad_Category and clean numeric fields across all rows."""
        def _get_broad_category(cat: Any) -> str:
            if not isinstance(cat, str):
                return "Other"
            if "Equity" in cat:
                return "Equity Schemes"
            if "Debt" in cat:
                return "Debt Schemes"
            if "Hybrid" in cat:
                return "Hybrid Schemes"
            if "Other" in cat:
                return "Other Schemes (ETFs & Index Funds)"
            if "Solution" in cat:
                return "Solution Oriented Schemes"
            if "Income" in cat:
                return "Income Schemes"
            return cat

        df['Broad_Category'] = df['Scheme_Category'].apply(_get_broad_category)
        df['Average_AUM_Cr'] = pd.to_numeric(df['Average_AUM_Cr'], errors='coerce')
        df['NAV'] = pd.to_numeric(df['NAV'], errors='coerce')
        return df

    def _init_sqlite(self) -> None:
        """Index full dataset in in-memory SQLite for high-speed deterministic queries."""
        try:
            if self.df_full is not None:
                self._conn = sqlite3.connect(":memory:")
                self.df_full.to_sql("mutual_funds", self._conn, index=False, if_exists="replace")
                with self._conn:
                    self._conn.execute("CREATE INDEX IF NOT EXISTS idx_scheme_name ON mutual_funds(Scheme_Name)")
                    self._conn.execute("CREATE INDEX IF NOT EXISTS idx_amc ON mutual_funds(AMC)")
                    self._conn.execute("CREATE INDEX IF NOT EXISTS idx_broad_cat ON mutual_funds(Broad_Category)")
                    self._conn.execute("CREATE INDEX IF NOT EXISTS idx_scheme_type ON mutual_funds(Scheme_Type)")
                logger.info("✓ Initialized legacy SQLite in-memory index over %d mutual fund rows", len(self.df_full))
        except Exception as e:
            logger.warning("Could not initialize legacy SQLite in-memory index: %s", e)

    def _load_data(self) -> None:
        """Load and preprocess mutual_fund_data from CSV or chunks."""
        try:
            if self.chunks_dir and self.chunks_dir.exists():
                self._load_from_chunks()
            elif self.csv_path and self.csv_path.exists():
                self._load_from_csv()
            else:
                logger.warning("No data source file found: %s", self.csv_path or self.chunks_dir)
        except Exception as e:
            logger.error("Error loading data: %s", e)
            raise

    def _load_from_csv(self) -> None:
        """Load data from single CSV file."""
        logger.info("Loading from CSV: %s", self.csv_path)
        raw_df = pd.read_csv(self.csv_path)
        self.df_full = self._add_derived_columns(raw_df)
        self.df = self.df_full.dropna(subset=['Average_AUM_Cr']).copy()
        self._init_sqlite()
        logger.info("✓ Loaded %d full rows (%d with AUM) from %s", len(self.df_full), len(self.df), self.csv_path)

    def _load_from_chunks(self) -> None:
        """Load data from chunks directory."""
        logger.info("Loading from chunks directory: %s", self.chunks_dir)
        manifest_path = self.chunks_dir / "manifest.json"
        if manifest_path.exists():
            import json
            try:
                with open(manifest_path) as f:
                    self.chunk_manifest = json.load(f)
            except Exception as e:
                logger.warning("Could not load manifest: %s", e)

        chunk_files = sorted(self.chunks_dir.glob('mutual_fund_data_chunk_*.csv'))
        if not chunk_files:
            raise FileNotFoundError(f"No chunk files found in {self.chunks_dir}")

        dfs = []
        for chunk_file in chunk_files:
            df = pd.read_csv(chunk_file)
            dfs.append(df)

        if dfs:
            raw_combined = pd.concat(dfs, ignore_index=True)
            self.df_full = self._add_derived_columns(raw_combined)
            self.df = self.df_full.dropna(subset=['Average_AUM_Cr']).copy()
            self._init_sqlite()
            logger.info("✓ Combined %d chunks into %d full rows (%d with AUM)", len(chunk_files), len(self.df_full), len(self.df))
        else:
            raise ValueError("No valid data loaded from chunks")

    def _aggregate_schemes(self) -> Dict[str, Dict[str, Any]]:
        """Legacy helper: aggregate plan-level data into scheme-level metrics."""
        aggregations = defaultdict(lambda: {
            'aum_values': [],
            'plan_names': [],
            'rows': []
        })
        if self.df is None:
            return aggregations

        for _, row in self.df.iterrows():
            scheme_name = row.get('Scheme_Name', '')
            if pd.isna(scheme_name) or not scheme_name:
                continue
            aum = row.get('Average_AUM_Cr', 0)
            plan_name = row.get('Scheme_NAV_Name', scheme_name)
            aggregations[scheme_name]['aum_values'].append(aum)
            aggregations[scheme_name]['plan_names'].append(plan_name)
            aggregations[scheme_name]['rows'].append(row)

        return aggregations

    # ═══════════════════════════════════════════════════════════════════════
    # Public Facade Methods (G05-T13)
    # ═══════════════════════════════════════════════════════════════════════

    def lookup_exact_nav(self, scheme_code: str, nav_date: str) -> Optional[Dict[str, Any]]:
        """Exact lookup for a scheme's NAV on a specific date (CSV-EXACT-001)."""
        if self.use_db:
            obs = self.repo.lookup_nav_exact(scheme_code, nav_date, dataset_version=self.active_version)
            if obs:
                return {
                    "observation_id": obs.observation_id,
                    "source_row_id": obs.source_row_id,
                    "dataset_version": obs.dataset_version,
                    "scheme_code": obs.scheme_code,
                    "amc_id": obs.amc_id,
                    "scheme_id": obs.scheme_id,
                    "plan_option_id": obs.plan_option_id,
                    "nav_per_unit": str(obs.nav_per_unit),
                    "nav_date": obs.nav_date.isoformat(),
                    "unit": obs.unit.value,
                }
        return None

    def get_top_schemes(
        self,
        limit: int = 10,
        sort_by: str = 'max_aum',
        include_plan_details: bool = True,
        **kwargs
    ) -> DualViewAUMResponse:
        """
        Get top N schemes with dual-view response (scheme-level + plan-level).
        Routes through typed analytical database if available.
        """
        amc_filter = kwargs.get('amc_filter')
        category_filter = kwargs.get('category_filter')
        scheme_type_filter = kwargs.get('scheme_type_filter')
        scheme_filter = kwargs.get('scheme_filter')

        if self.use_db:
            plan = self.planner.create_top_schemes_plan(
                limit=limit,
                sort_by=sort_by,
                amc_filter=amc_filter,
                category_filter=category_filter,
                scheme_type_filter=scheme_type_filter,
                scheme_filter=scheme_filter,
                dataset_version=self.active_version,
            )
            res = self.executor.execute(plan)

            scheme_metrics: List[SchemeAggregationMetrics] = []
            for idx, row in enumerate(res.rows, 1):
                raw_plans = row.get('plan_variants') or ''
                plan_variants_list = [p.strip() for p in raw_plans.split(' | ') if p.strip()]
                m = SchemeAggregationMetrics(
                    scheme_name=str(row.get('scheme_name') or ''),
                    scheme_code=str(row.get('scheme_code') or '') if row.get('scheme_code') else None,
                    amc=str(row.get('amc') or ''),
                    scheme_type=str(row.get('scheme_type') or ''),
                    scheme_category=str(row.get('scheme_category') or ''),
                    max_aum_cr=float(row.get('max_aum_cr') or 0.0),
                    min_aum_cr=float(row.get('min_aum_cr') or 0.0),
                    avg_aum_cr=float(row.get('avg_aum_cr') or 0.0),
                    total_aum_cr=float(row.get('total_aum_cr') or 0.0),
                    plan_count=int(row.get('plan_count') or len(plan_variants_list) or 1),
                    plan_variants=plan_variants_list,
                    latest_nav=float(row['latest_nav']) if row.get('latest_nav') is not None else None,
                    latest_nav_date=str(row['latest_nav_date']) if row.get('latest_nav_date') else None,
                    launch_date=str(row['launch_date']) if row.get('launch_date') else None,
                    closure_date=str(row['closure_date']) if row.get('closure_date') else None,
                    is_active=(row.get('closure_date') is None),
                    data_quarter=str(row.get('data_quarter') or 'January - March 2026'),
                    last_aggregated_at=datetime.utcnow().isoformat() + 'Z',
                    plan_data_completeness=1.0,
                    rank_by_max_aum=idx if sort_by == 'max_aum' else None,
                    rank_by_avg_aum=idx if sort_by == 'avg_aum' else None,
                    rank_by_total_aum=idx if sort_by == 'total_aum' else None,
                )
                scheme_metrics.append(m)

            # Plan-level rankings
            plan_level_data: List[Dict[str, Any]] = []
            if include_plan_details:
                with self.repo._get_connection() as conn:
                    cursor = conn.execute(
                        """
                        SELECT scheme_display_name as scheme_name,
                               plan_option_display_name as plan_name,
                               amc_display_name as amc,
                               ROUND(CAST(aaum_crore AS REAL), 2) as aum_cr,
                               ROUND(CAST(nav_per_unit AS REAL), 2) as nav,
                               scheme_category_raw as scheme_category
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID' AND aaum_crore IS NOT NULL
                        ORDER BY CAST(aaum_crore AS REAL) DESC
                        LIMIT :lim
                        """,
                        {"ver": self.active_version, "lim": limit * 2}
                    )
                    seen = set()
                    for r in cursor.fetchall():
                        pid = f"{r['scheme_name']}_{r['plan_name']}"
                        if pid in seen:
                            continue
                        seen.add(pid)
                        plan_level_data.append({
                            'scheme_name': r['scheme_name'],
                            'plan_name': r['plan_name'],
                            'amc': r['amc'],
                            'aum_cr': float(r['aum_cr']) if r['aum_cr'] is not None else 0.0,
                            'nav': float(r['nav']) if r['nav'] is not None else None,
                            'scheme_category': r['scheme_category'] or '',
                            'rank': len(plan_level_data) + 1,
                        })
                        if len(plan_level_data) >= limit:
                            break

            return DualViewAUMResponse(
                query="Top schemes by Average AUM",
                query_intent="ranking",
                generated_at=datetime.utcnow().isoformat() + 'Z',
                data_period=scheme_metrics[0].data_quarter if scheme_metrics else 'January - March 2026',
                scheme_level_rankings=scheme_metrics,
                plan_level_rankings=plan_level_data,
                total_unique_schemes=len(scheme_metrics),
                total_plan_variants=sum(s.plan_count for s in scheme_metrics),
                scheme_level_count=len(scheme_metrics),
                plan_level_count=len(plan_level_data),
                data_completeness=1.0,
                schemes_with_multiple_plans=sum(1 for s in scheme_metrics if s.plan_count > 1),
                interpretation_guide=self._get_interpretation_guide(sort_by),
            )

        # Fallback to legacy in-memory aggregation
        if self.df is None or len(self.df) == 0:
            raise ValueError("No data loaded. Check CSV path and format.")

        aggregations = self._aggregate_schemes()
        scheme_metrics = []
        for scheme_name, agg_data in aggregations.items():
            aum_values = agg_data['aum_values']
            first_row = agg_data['rows'][0]
            metrics = SchemeAggregationMetrics(
                scheme_name=scheme_name,
                scheme_code=str(first_row.get('Scheme_Code')) if first_row.get('Scheme_Code') is not None else None,
                amc=str(first_row.get('AMC', '')),
                scheme_type=str(first_row.get('Scheme_Type', '')),
                scheme_category=str(first_row.get('Scheme_Category', '')),
                max_aum_cr=float(max(aum_values)),
                min_aum_cr=float(min(aum_values)),
                avg_aum_cr=float(sum(aum_values) / len(aum_values)),
                total_aum_cr=float(sum(aum_values)),
                plan_count=int(len(agg_data['plan_names'])),
                plan_variants=list(agg_data['plan_names']),
                latest_nav=self._safe_float(first_row.get('NAV')),
                latest_nav_date=str(first_row.get('Latest_NAV_Date')) if pd.notna(first_row.get('Latest_NAV_Date')) else None,
                scheme_min_amt=str(first_row.get('Scheme_Min_Amt')) if pd.notna(first_row.get('Scheme_Min_Amt')) else None,
                launch_date=str(first_row.get('Launch_Date')) if pd.notna(first_row.get('Launch_Date')) else None,
                closure_date=str(first_row.get('Closure_Date')) if pd.notna(first_row.get('Closure_Date')) else None,
                is_active=pd.isna(first_row.get('Closure_Date')),
                data_quarter=str(first_row.get('AAUM_Quarter', 'Unknown')),
                last_aggregated_at=datetime.utcnow().isoformat() + 'Z',
                plan_data_completeness=1.0,
            )
            scheme_metrics.append(metrics)

        if amc_filter:
            scheme_metrics = [s for s in scheme_metrics if amc_filter.lower() in s.amc.lower()]
        if category_filter:
            scheme_metrics = [s for s in scheme_metrics if category_filter.lower() in s.scheme_category.lower()]
        if scheme_type_filter:
            scheme_metrics = [s for s in scheme_metrics if scheme_type_filter.lower() in s.scheme_type.lower()]
        if scheme_filter:
            scheme_metrics = [s for s in scheme_metrics if scheme_filter.lower() in s.scheme_name.lower()]

        if sort_by == 'max_aum':
            scheme_metrics.sort(key=lambda x: x.max_aum_cr, reverse=True)
        elif sort_by == 'avg_aum':
            scheme_metrics.sort(key=lambda x: x.avg_aum_cr, reverse=True)
        elif sort_by == 'total_aum':
            scheme_metrics.sort(key=lambda x: x.total_aum_cr, reverse=True)
        elif sort_by == 'plan_count':
            scheme_metrics.sort(key=lambda x: x.plan_count, reverse=True)

        top_schemes = scheme_metrics[:limit]
        for idx, metric in enumerate(top_schemes, 1):
            metric.rank_by_max_aum = idx if sort_by == 'max_aum' else None
            metric.rank_by_avg_aum = idx if sort_by == 'avg_aum' else None
            metric.rank_by_total_aum = idx if sort_by == 'total_aum' else None

        plan_level_data = []
        if include_plan_details:
            plan_level_data = self._get_plan_level_rankings(limit)

        return DualViewAUMResponse(
            query="Top schemes by Average AUM",
            query_intent="ranking",
            generated_at=datetime.utcnow().isoformat() + 'Z',
            data_period=top_schemes[0].data_quarter if top_schemes else 'Unknown',
            scheme_level_rankings=top_schemes,
            plan_level_rankings=plan_level_data,
            total_unique_schemes=len(top_schemes),
            total_plan_variants=sum(s.plan_count for s in top_schemes),
            scheme_level_count=len(top_schemes),
            plan_level_count=len(plan_level_data),
            data_completeness=0.98,
            schemes_with_multiple_plans=sum(1 for s in top_schemes if s.plan_count > 1),
            interpretation_guide=self._get_interpretation_guide(sort_by),
        )

    def get_top_amcs(
        self,
        limit: int = 10,
        sort_by: str = 'total_aum',
        amc_filter: Optional[str] = None,
    ) -> AMCAggregationResponse:
        """
        Get top N AMCs aggregated by total AUM and distinct scheme counts.
        Routes through typed analytical database if available.
        """
        if self.use_db:
            plan = self.planner.create_top_amcs_plan(
                quarter="January - March 2026",
                limit=limit,
                sort_by=sort_by,
                amc_filter=amc_filter,
                dataset_version=self.active_version,
            )
            res = self.executor.execute(plan)

            amc_metrics: List[AMCAggregationMetrics] = []
            for idx, row in enumerate(res.rows, 1):
                amc_metrics.append(
                    AMCAggregationMetrics(
                        amc=str(row["amc"]).strip(),
                        total_aum_cr=round(float(row.get("total_aum_cr") or 0.0), 2),
                        avg_aum_cr=round(float(row.get("avg_aum_cr") or 0.0), 2),
                        distinct_schemes=int(row.get("distinct_schemes") or 0),
                        total_plans=int(row.get("total_plans") or 0),
                        rank=idx,
                    )
                )

            # Count total unique AMCs
            with self.repo._get_connection() as conn:
                tot_unique = conn.execute(
                    "SELECT COUNT(DISTINCT amc_id) FROM source_rows WHERE dataset_version = :ver AND validation_status = 'VALID'",
                    {"ver": self.active_version}
                ).fetchone()[0]

            return AMCAggregationResponse(
                query="Top AMCs by AUM",
                query_intent="amc_ranking",
                generated_at=datetime.utcnow().isoformat() + "Z",
                data_period="January - March 2026",
                amc_rankings=amc_metrics,
                total_unique_amcs=tot_unique,
                interpretation_guide=(
                    "AMC-Level Rankings: Aggregates total AUM, distinct scheme counts, and plan counts "
                    "across all offerings for each Asset Management Company."
                ),
            )

        # Fallback to legacy in-memory aggregation
        if self.df is None or len(self.df) == 0:
            raise ValueError("No data loaded. Check CSV path and format.")

        grouped = self.df.groupby('AMC')
        amc_metrics = []
        for amc_name, group in grouped:
            if pd.isna(amc_name) or not str(amc_name).strip():
                continue
            aum_series = group['Average_AUM_Cr']
            total_aum = float(aum_series.sum())
            avg_aum = float(aum_series.mean()) if len(aum_series) > 0 else 0.0
            distinct_schemes = int(group['Scheme_Name'].dropna().nunique())
            total_plans = len(group)
            amc_metrics.append(
                AMCAggregationMetrics(
                    amc=str(amc_name).strip(),
                    total_aum_cr=round(total_aum, 2),
                    avg_aum_cr=round(avg_aum, 2),
                    distinct_schemes=distinct_schemes,
                    total_plans=total_plans,
                )
            )

        if sort_by == 'total_aum':
            amc_metrics.sort(key=lambda x: x.total_aum_cr, reverse=True)
        elif sort_by == 'distinct_schemes':
            amc_metrics.sort(key=lambda x: x.distinct_schemes, reverse=True)
        elif sort_by == 'avg_aum':
            amc_metrics.sort(key=lambda x: x.avg_aum_cr, reverse=True)
        elif sort_by == 'total_plans':
            amc_metrics.sort(key=lambda x: x.total_plans, reverse=True)
        else:
            amc_metrics.sort(key=lambda x: x.total_aum_cr, reverse=True)

        for idx, metric in enumerate(amc_metrics, 1):
            metric.rank = idx

        if amc_filter:
            top_amcs = [m for m in amc_metrics if amc_filter.lower() in m.amc.lower()][:limit]
        else:
            top_amcs = amc_metrics[:limit]

        return AMCAggregationResponse(
            query="Top AMCs by AUM",
            query_intent="amc_ranking",
            generated_at=datetime.utcnow().isoformat() + "Z",
            data_period="January - March 2026",
            amc_rankings=top_amcs,
            total_unique_amcs=len(amc_metrics),
            interpretation_guide=(
                "AMC-Level Rankings: Aggregates total AUM, distinct scheme counts, and plan counts "
                "across all offerings for each Asset Management Company."
            ),
        )

    def get_dataset_summary(self, scheme_type_filter: Optional[str] = None) -> Dict[str, Any]:
        """Calculates comprehensive dataset-level summary and breakdown."""
        if self.use_db:
            with self.repo._get_connection() as conn:
                if scheme_type_filter:
                    row = conn.execute(
                        """
                        SELECT ROUND(SUM(CASE WHEN aaum_crore IS NOT NULL THEN CAST(aaum_crore AS REAL) ELSE 0 END), 2) as tot_aum,
                               COUNT(DISTINCT scheme_display_name) as tot_schemes,
                               COUNT(DISTINCT amc_id) as tot_amcs,
                               COUNT(*) as tot_folios
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID' AND LOWER(scheme_type) LIKE :stype
                        """,
                        {"ver": self.active_version, "stype": f"%{scheme_type_filter.lower().strip()}%"}
                    ).fetchone()
                    return {
                        "filtered_type": scheme_type_filter,
                        "total_aum_cr": round(float(row["tot_aum"] or 0.0), 2),
                        "distinct_schemes": int(row["tot_schemes"] or 0),
                        "total_amcs": int(row["tot_amcs"] or 0),
                        "total_folios": int(row["tot_folios"] or 0),
                        "data_period": "January - March 2026",
                    }
                else:
                    row = conn.execute(
                        """
                        SELECT ROUND(SUM(CASE WHEN aaum_crore IS NOT NULL THEN CAST(aaum_crore AS REAL) ELSE 0 END), 2) as tot_aum,
                               COUNT(DISTINCT scheme_display_name) as tot_schemes,
                               COUNT(DISTINCT amc_id) as tot_amcs,
                               COUNT(*) as tot_folios
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID'
                        """,
                        {"ver": self.active_version}
                    ).fetchone()

                    breakdown_rows = conn.execute(
                        """
                        SELECT scheme_type,
                               ROUND(SUM(CASE WHEN aaum_crore IS NOT NULL THEN CAST(aaum_crore AS REAL) ELSE 0 END), 2) as tot_aum,
                               COUNT(DISTINCT scheme_display_name) as tot_schemes,
                               COUNT(*) as tot_folios
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID'
                        GROUP BY scheme_type
                        """,
                        {"ver": self.active_version}
                    ).fetchall()
                    types_breakdown = {}
                    for r in breakdown_rows:
                        types_breakdown[str(r["scheme_type"])] = {
                            "total_aum_cr": round(float(r["tot_aum"] or 0.0), 2),
                            "distinct_schemes": int(r["tot_schemes"] or 0),
                            "total_folios": int(r["tot_folios"] or 0),
                        }
                    return {
                        "total_market_aum_cr": round(float(row["tot_aum"] or 0.0), 2),
                        "total_distinct_schemes": int(row["tot_schemes"] or 0),
                        "total_amcs": int(row["tot_amcs"] or 0),
                        "total_folios": int(row["tot_folios"] or 0),
                        "types_breakdown": types_breakdown,
                        "data_period": "January - March 2026",
                    }

        # Legacy fallback
        df_src = self.df_full if self.df_full is not None else self.df
        if df_src is None or len(df_src) == 0:
            raise ValueError("No data loaded.")

        if scheme_type_filter:
            df_filtered = df_src[df_src['Scheme_Type'].str.contains(scheme_type_filter, case=False, na=False)]
            total_aum = float(df_filtered['Average_AUM_Cr'].dropna().sum())
            total_schemes = int(df_filtered['Scheme_Name'].dropna().nunique())
            total_amcs = int(df_filtered['AMC'].dropna().nunique())
            total_folios = len(df_filtered)
            return {
                "filtered_type": scheme_type_filter,
                "total_aum_cr": round(total_aum, 2),
                "distinct_schemes": total_schemes,
                "total_amcs": total_amcs,
                "total_folios": total_folios,
                "data_period": "January - March 2026",
            }

        total_aum = float(df_src['Average_AUM_Cr'].dropna().sum())
        total_schemes = int(df_src['Scheme_Name'].dropna().nunique())
        total_amcs = int(df_src['AMC'].dropna().nunique())
        total_folios = len(df_src)
        types_breakdown = {}
        for st, grp in df_src.groupby('Scheme_Type'):
            types_breakdown[str(st)] = {
                "total_aum_cr": round(float(grp['Average_AUM_Cr'].dropna().sum()), 2),
                "distinct_schemes": int(grp['Scheme_Name'].dropna().nunique()),
                "total_folios": len(grp),
            }
        return {
            "total_market_aum_cr": round(total_aum, 2),
            "total_distinct_schemes": total_schemes,
            "total_amcs": total_amcs,
            "total_folios": total_folios,
            "types_breakdown": types_breakdown,
            "data_period": "January - March 2026",
        }

    def get_category_aum_breakdown(
        self,
        detailed: bool = False,
        query_text: str = "",
    ) -> CategoryAggregationResponse:
        """
        Calculates category-level breakdown of total AUM and scheme counts.
        """
        if self.use_db:
            with self.repo._get_connection() as conn:
                tot_row = conn.execute(
                    """
                    SELECT ROUND(SUM(CASE WHEN aaum_crore IS NOT NULL THEN CAST(aaum_crore AS REAL) ELSE 0 END), 2) as tot_aum,
                           COUNT(DISTINCT scheme_display_name) as tot_schemes,
                           COUNT(*) as tot_folios
                    FROM source_rows
                    WHERE dataset_version = :ver AND validation_status = 'VALID'
                    """,
                    {"ver": self.active_version}
                ).fetchone()
                total_mkt_aum = float(tot_row["tot_aum"] or 0.0)
                total_distinct_schemes = int(tot_row["tot_schemes"] or 0)
                total_folios = int(tot_row["tot_folios"] or 0)

                cat_rows = conn.execute(
                    """
                    SELECT scheme_category_raw as category,
                           COUNT(DISTINCT scheme_display_name) as distinct_schemes,
                           COUNT(*) as total_folios,
                           ROUND(SUM(CASE WHEN aaum_crore IS NOT NULL THEN CAST(aaum_crore AS REAL) ELSE 0 END), 2) as aum_sum
                    FROM source_rows
                    WHERE dataset_version = :ver AND validation_status = 'VALID'
                    GROUP BY scheme_category_raw
                    ORDER BY aum_sum DESC
                    """,
                    {"ver": self.active_version}
                ).fetchall()

                metrics: List[CategoryAggregationMetrics] = []
                for idx, r in enumerate(cat_rows, 1):
                    aum_sum = float(r["aum_sum"] or 0.0)
                    distinct_count = int(r["distinct_schemes"] or 0)
                    pct = (aum_sum / total_mkt_aum * 100.0) if total_mkt_aum > 0 else 0.0
                    avg_per_scheme = (aum_sum / distinct_count) if distinct_count > 0 else 0.0
                    metrics.append(
                        CategoryAggregationMetrics(
                            category=str(r["category"]),
                            distinct_schemes=distinct_count,
                            total_folios=int(r["total_folios"]),
                            total_aum_cr=round(aum_sum, 2),
                            pct_of_total_aum=round(pct, 2),
                            avg_aum_per_scheme_cr=round(avg_per_scheme, 2),
                            rank=idx,
                        )
                    )

                return CategoryAggregationResponse(
                    query=query_text or "Category AUM Breakdown",
                    query_intent="category_aggregation",
                    generated_at=datetime.utcnow().isoformat() + "Z",
                    data_period="January - March 2026",
                    categories=metrics,
                    total_market_aum_cr=round(total_mkt_aum, 2),
                    total_distinct_schemes=total_distinct_schemes,
                    total_folios=total_folios,
                    interpretation_guide=(
                        "Rankings show total Average AUM in ₹ Crores and distinct scheme counts per category. "
                        "Percentages represent market share of total mutual fund assets."
                    ),
                )

        # Legacy fallback
        df_src = self.df_full if self.df_full is not None else self.df
        if df_src is None or len(df_src) == 0:
            raise ValueError("No data loaded.")

        target_col = "Scheme_Category" if detailed else "Broad_Category"
        if target_col not in df_src.columns and target_col == "Broad_Category":
            df_src = self._add_derived_columns(df_src.copy())

        valid_aum_series = df_src["Average_AUM_Cr"].dropna()
        total_mkt_aum = float(valid_aum_series.sum())
        total_distinct_schemes = int(df_src["Scheme_Name"].nunique())
        total_folios = len(df_src)

        records = []
        for cat_name, group in df_src.groupby(target_col):
            aum_sum = float(group["Average_AUM_Cr"].dropna().sum())
            distinct_count = int(group["Scheme_Name"].nunique())
            folio_count = len(group)
            pct = (aum_sum / total_mkt_aum * 100.0) if total_mkt_aum > 0 else 0.0
            avg_per_scheme = (aum_sum / distinct_count) if distinct_count > 0 else 0.0
            records.append({
                "category": str(cat_name),
                "distinct_schemes": distinct_count,
                "total_folios": folio_count,
                "total_aum_cr": round(aum_sum, 2),
                "pct_of_total_aum": round(pct, 2),
                "avg_aum_per_scheme_cr": round(avg_per_scheme, 2),
            })

        records.sort(key=lambda r: r["total_aum_cr"], reverse=True)
        metrics = []
        for idx, r in enumerate(records, 1):
            metrics.append(CategoryAggregationMetrics(
                category=r["category"],
                distinct_schemes=r["distinct_schemes"],
                total_folios=r["total_folios"],
                total_aum_cr=r["total_aum_cr"],
                pct_of_total_aum=r["pct_of_total_aum"],
                avg_aum_per_scheme_cr=r["avg_aum_per_scheme_cr"],
                rank=idx,
            ))

        return CategoryAggregationResponse(
            query=query_text or "Category AUM Breakdown",
            query_intent="category_aggregation",
            generated_at=datetime.utcnow().isoformat() + "Z",
            data_period="January - March 2026",
            categories=metrics,
            total_market_aum_cr=round(total_mkt_aum, 2),
            total_distinct_schemes=total_distinct_schemes,
            total_folios=total_folios,
            interpretation_guide=(
                "Rankings show total Average AUM in ₹ Crores and distinct scheme counts per category. "
                "Percentages represent market share of total mutual fund assets."
            ),
        )

    def get_top_nav_schemes(
        self,
        limit: int = 10,
        scheme_type: Optional[str] = "Open Ended",
        category_keyword: Optional[str] = "Equity",
        plan_keyword: Optional[str] = "Growth",
        exclude_idcw: bool = True,
        sort_order: str = "desc",
        query_text: str = "",
    ) -> NAVAggregationResponse:
        """
        Get top schemes ranked by Net Asset Value (NAV).
        """
        if self.use_db:
            plan = self.planner.create_top_nav_schemes_plan(
                limit=limit,
                scheme_type=scheme_type,
                category_keyword=category_keyword,
                plan_keyword=plan_keyword,
                exclude_idcw=exclude_idcw,
                sort_order=sort_order,
                dataset_version=self.active_version,
            )
            res = self.executor.execute(plan)

            metrics_list: List[NAVAggregationMetrics] = []
            for idx, row in enumerate(res.rows, 1):
                metrics_list.append(
                    NAVAggregationMetrics(
                        scheme_name=str(row.get('scheme_name') or ''),
                        plan_name=str(row.get('plan_name') or row.get('scheme_name') or ''),
                        amc=str(row.get('amc') or ''),
                        nav=float(row['nav']),
                        latest_nav_date=str(row.get('latest_nav_date')) if row.get('latest_nav_date') else None,
                        scheme_type=str(row.get('scheme_type') or ''),
                        scheme_category=str(row.get('scheme_category') or ''),
                        rank=idx,
                    )
                )

            data_period = metrics_list[0].latest_nav_date if metrics_list and metrics_list[0].latest_nav_date else "Unknown"

            return NAVAggregationResponse(
                query=query_text or f"Top schemes by NAV ({sort_order})",
                query_intent="nav_ranking",
                generated_at=datetime.utcnow().isoformat() + "Z",
                data_period=data_period,
                schemes=metrics_list,
                total_matching=len(metrics_list),
                applied_filters=plan.filters,
                interpretation_guide=(
                    f"NAV Ranking: Showing top {len(metrics_list)} schemes sorted by NAV ({sort_order}ending) "
                    "from official mutual fund dataset."
                ),
            )

        # Legacy fallback
        df_src = self.df_full if self.df_full is not None else self.df
        if df_src is None or len(df_src) == 0:
            raise ValueError("No data loaded.")

        df = df_src.copy()
        df['NAV'] = pd.to_numeric(df['NAV'], errors='coerce')
        df = df.dropna(subset=['NAV'])

        applied_filters = {}
        if scheme_type:
            df = df[df['Scheme_Type'].str.contains(scheme_type, case=False, na=False)]
            applied_filters['scheme_type'] = scheme_type

        if category_keyword:
            df = df[df['Scheme_Category'].str.contains(category_keyword, case=False, na=False)]
            applied_filters['category'] = category_keyword

        if plan_keyword:
            df = df[df['Scheme_NAV_Name'].str.contains(plan_keyword, case=False, na=False)]
            applied_filters['plan_keyword'] = plan_keyword

        if exclude_idcw:
            df = df[~df['Scheme_NAV_Name'].str.contains('IDCW|Dividend', case=False, na=False)]
            applied_filters['exclude_idcw'] = True

        total_matching = len(df)
        ascending = (sort_order.lower() == "asc")
        df_sorted = df.sort_values(by='NAV', ascending=ascending).head(limit)

        metrics_list = []
        for idx, (_, row) in enumerate(df_sorted.iterrows(), 1):
            metrics_list.append(
                NAVAggregationMetrics(
                    scheme_name=str(row.get('Scheme_Name', '')),
                    plan_name=str(row.get('Scheme_NAV_Name', row.get('Scheme_Name', ''))),
                    amc=str(row.get('AMC', '')),
                    nav=float(row['NAV']),
                    latest_nav_date=str(row.get('Latest_NAV_Date')) if pd.notna(row.get('Latest_NAV_Date')) else None,
                    scheme_type=str(row.get('Scheme_Type', '')),
                    scheme_category=str(row.get('Scheme_Category', '')),
                    rank=idx,
                )
            )

        data_period = "Unknown"
        if len(df_sorted) > 0 and pd.notna(df_sorted.iloc[0].get('Latest_NAV_Date')):
            data_period = str(df_sorted.iloc[0].get('Latest_NAV_Date'))

        return NAVAggregationResponse(
            query=query_text or f"Top schemes by NAV ({sort_order})",
            query_intent="nav_ranking",
            generated_at=datetime.utcnow().isoformat() + "Z",
            data_period=data_period,
            schemes=metrics_list,
            total_matching=total_matching,
            applied_filters=applied_filters,
            interpretation_guide=(
                f"NAV Ranking: Showing top {len(metrics_list)} schemes sorted by NAV ({sort_order}ending) "
                f"from {total_matching} matching options in the official mutual fund dataset."
            ),
        )

    def get_scheme_type_distribution_by_amc(
        self,
        limit: int = 5,
        sort_by: str = "total_aum",
    ) -> List[Dict[str, Any]]:
        """Return Open/Close/Interval Ended scheme distribution for top N AMCs."""
        if self.use_db:
            with self.repo._get_connection() as conn:
                if sort_by == "distinct_schemes":
                    amc_cursor = conn.execute(
                        """
                        SELECT amc_display_name, COUNT(DISTINCT scheme_display_name) as score
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID' AND aaum_crore IS NOT NULL
                        GROUP BY amc_display_name
                        ORDER BY score DESC, amc_display_name ASC
                        LIMIT :limit
                        """,
                        {"ver": self.active_version, "limit": limit}
                    )
                else:
                    amc_cursor = conn.execute(
                        """
                        SELECT amc_display_name, ROUND(SUM(CAST(aaum_crore AS REAL)), 2) as score
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID' AND aaum_crore IS NOT NULL
                        GROUP BY amc_display_name
                        ORDER BY score DESC, amc_display_name ASC
                        LIMIT :limit
                        """,
                        {"ver": self.active_version, "limit": limit}
                    )
                top_amcs = [r["amc_display_name"] for r in amc_cursor.fetchall()]

                results: List[Dict[str, Any]] = []
                for rank, amc in enumerate(top_amcs, 1):
                    tot_row = conn.execute(
                        """
                        SELECT ROUND(SUM(CAST(aaum_crore AS REAL)), 2) as tot_aum
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID' AND amc_display_name = :amc AND aaum_crore IS NOT NULL
                        """,
                        {"ver": self.active_version, "amc": amc}
                    ).fetchone()
                    total_aum = float(tot_row["tot_aum"] or 0.0)

                    type_rows = conn.execute(
                        """
                        SELECT scheme_type, COUNT(DISTINCT scheme_display_name) as cnt
                        FROM source_rows
                        WHERE dataset_version = :ver AND validation_status = 'VALID' AND amc_display_name = :amc
                        GROUP BY scheme_type
                        """,
                        {"ver": self.active_version, "amc": amc}
                    ).fetchall()

                    total_distinct = sum(r["cnt"] for r in type_rows)
                    breakdown: Dict[str, Dict[str, Any]] = {}
                    for r in type_rows:
                        stype = str(r["scheme_type"] or "Unknown")
                        cnt = int(r["cnt"])
                        pct = round(cnt / total_distinct * 100, 1) if total_distinct > 0 else 0.0
                        breakdown[stype] = {"count": cnt, "pct": pct}

                    results.append({
                        "rank": rank,
                        "amc": str(amc),
                        "total_aum_cr": round(total_aum, 2),
                        "total_distinct_schemes": total_distinct,
                        "scheme_type_breakdown": breakdown,
                    })

                return results

        # Legacy fallback
        if self.df_full is None and self.df is None:
            raise ValueError("No data loaded.")

        df = self.df_full if self.df_full is not None else self.df
        df_aum = df.dropna(subset=["Average_AUM_Cr"]).copy()
        if sort_by == "distinct_schemes":
            amc_order = (
                df_aum.groupby("AMC")["Scheme_Name"]
                .nunique()
                .sort_values(ascending=False)
            )
        else:
            amc_order = (
                df_aum.groupby("AMC")["Average_AUM_Cr"]
                .sum()
                .sort_values(ascending=False)
            )
        top_amcs = amc_order.head(limit).index.tolist()

        results = []
        for rank, amc in enumerate(top_amcs, 1):
            subset = df[df["AMC"] == amc]
            total_aum = float(df_aum[df_aum["AMC"] == amc]["Average_AUM_Cr"].sum())
            type_counts = subset.groupby("Scheme_Type")["Scheme_Name"].nunique().to_dict()
            total_distinct = sum(type_counts.values())

            breakdown = {}
            for stype, count in type_counts.items():
                pct = round(count / total_distinct * 100, 1) if total_distinct > 0 else 0.0
                breakdown[str(stype)] = {"count": int(count), "pct": pct}

            results.append({
                "rank": rank,
                "amc": str(amc),
                "total_aum_cr": round(total_aum, 2),
                "total_distinct_schemes": total_distinct,
                "scheme_type_breakdown": breakdown,
            })

        return results

    def _get_plan_level_rankings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Legacy helper: get top N plan variants by AUM."""
        if self.df is None:
            return []
        df_sorted = self.df.nlargest(limit * 3, 'Average_AUM_Cr')
        plan_rankings = []
        seen_plans = set()
        for _, row in df_sorted.iterrows():
            plan_id = f"{row['Scheme_Name']}_{row['Scheme_NAV_Name']}"
            if plan_id in seen_plans:
                continue
            plan_rankings.append({
                'scheme_name': row['Scheme_Name'],
                'plan_name': row['Scheme_NAV_Name'],
                'amc': row['AMC'],
                'aum_cr': row['Average_AUM_Cr'],
                'nav': self._safe_float(row.get('NAV')),
                'scheme_category': row.get('Scheme_Category', ''),
                'rank': len(plan_rankings) + 1
            })
            seen_plans.add(plan_id)
            if len(plan_rankings) >= limit:
                break
        return plan_rankings

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _get_interpretation_guide(self, sort_by: str) -> str:
        """Generate interpretation guidance for the response."""
        base_guide = (
            "This response provides two complementary views of mutual fund scheme rankings:\n\n"
            "**Scheme-Level Rankings**: Shows aggregated metrics across all plan variants of each scheme.\n\n"
            "**Plan-Level Rankings**: Shows individual plan variants with specific AUM values.\n\n"
        )
        if sort_by == 'max_aum':
            return base_guide + "Sorted by Maximum AUM: Highest-AUM plan variant is featured."
        elif sort_by == 'avg_aum':
            return base_guide + "Sorted by Average AUM across all plan types."
        elif sort_by == 'total_aum':
            return base_guide + "Sorted by Total AUM across all plan variants."
        return base_guide

    def get_data_source_info(self) -> Dict[str, Any]:
        """Get information about data source (repository or files)."""
        if self.use_db:
            return {
                'data_source': 'typed_analytical_repository',
                'repository_db': str(self.repo.db_path),
                'dataset_version': self.active_version,
                'status': 'ACTIVE',
            }
        return {
            'data_source': 'chunks' if self.chunks_dir else 'single_csv',
            'chunks_available': self.chunks_dir is not None,
        }

    def export_scheme_aggregations(self, output_path: str, format: str = 'csv') -> str:
        """Export materialized scheme aggregations."""
        if self.scheme_aggregations is None:
            aggregations = self._aggregate_schemes()
            data = []
            for scheme_name, agg_data in aggregations.items():
                aum_values = agg_data['aum_values']
                first_row = agg_data['rows'][0]
                data.append({
                    'scheme_name': scheme_name,
                    'amc': first_row.get('AMC', ''),
                    'scheme_category': first_row.get('Scheme_Category', ''),
                    'max_aum_cr': max(aum_values) if aum_values else 0,
                    'min_aum_cr': min(aum_values) if aum_values else 0,
                    'avg_aum_cr': sum(aum_values) / len(aum_values) if aum_values else 0,
                    'total_aum_cr': sum(aum_values),
                    'plan_count': len(agg_data['plan_names']),
                    'plan_names': '|'.join(agg_data['plan_names']),
                })
            self.scheme_aggregations = pd.DataFrame(data)

        output_path_p = Path(output_path)
        output_path_p.parent.mkdir(parents=True, exist_ok=True)
        if format == 'csv':
            self.scheme_aggregations.to_csv(output_path_p, index=False)
        elif format == 'parquet':
            self.scheme_aggregations.to_parquet(output_path_p, index=False)
        return str(output_path_p)


# Singleton instance for application use
_service_instance: Optional[SchemeAggregationService] = None


def get_aggregation_service() -> SchemeAggregationService:
    """Get or create singleton instance of SchemeAggregationService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SchemeAggregationService(use_chunks=True)
    return _service_instance


def reset_aggregation_service() -> None:
    """Reset singleton instance (useful for testing)."""
    global _service_instance
    _service_instance = None
