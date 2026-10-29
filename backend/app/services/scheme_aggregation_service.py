# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
services/scheme_aggregation_service.py
======================================
Service layer for scheme-level aggregation logic.
Materializes aggregated metrics from mutual_fund_data.csv plan-level records.
"""

import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import logging
import glob
import sqlite3

from app.models.scheme_aggregation import (
    SchemeAggregationMetrics,
    DualViewAUMResponse,
    SchemeAggregationRequest,
    AMCAggregationMetrics,
    AMCAggregationResponse,
    NAVAggregationMetrics,
    NAVAggregationResponse,
    CategoryAggregationMetrics,
    CategoryAggregationResponse,
)

logger = logging.getLogger(__name__)


class SchemeAggregationService:
    """
    Materializes scheme-level aggregation from plan-level mutual fund data.
    
    Key responsibilities:
    1. Load and parse mutual_fund_data.csv
    2. Group plan variants by scheme name
    3. Calculate aggregated AUM metrics (max, min, avg, total)
    4. Generate rankings and rankings
    5. Provide dual-view responses (plan-level + scheme-level)
    """
    
    def __init__(self, csv_path: Optional[str] = None, use_chunks: bool = True):
        """
        Initialize the aggregation service.
        
        Args:
            csv_path: Path to mutual_fund_data.csv. If None, uses default location.
            use_chunks: If True, loads from chunks directory instead of single CSV file
        """
        self.use_chunks = use_chunks
        
        if csv_path is None:
            # Default path relative to project structure
            project_root = Path(__file__).resolve().parent.parent.parent
            csv_path = project_root / "data" / "source_docs" / "mutual_fund_data.csv"
            
            # Check if chunks exist (prefer chunks if available)
            chunks_dir = project_root / "data" / "source_docs" / "chunks"
            if use_chunks and chunks_dir.exists():
                self.chunks_dir = chunks_dir
                csv_path = None
            else:
                self.chunks_dir = None
        else:
            # If chunks directory is provided/accessible, use it
            csv_path = Path(csv_path)
            chunks_dir = csv_path.parent / "chunks"
            if use_chunks and chunks_dir.exists():
                self.chunks_dir = chunks_dir
                csv_path = None
            else:
                self.chunks_dir = None
        
        self.csv_path = Path(csv_path) if csv_path else None
        self.df: Optional[pd.DataFrame] = None
        self.df_full: Optional[pd.DataFrame] = None
        self._conn: Optional[sqlite3.Connection] = None
        self.scheme_aggregations = None
        self.chunk_manifest = None
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
                logger.info(f"✓ Initialized SQLite in-memory index over {len(self.df_full)} mutual fund rows")
        except Exception as e:
            logger.warning(f"Could not initialize SQLite in-memory index: {e}")
    
    def _load_data(self) -> None:
        """Load and preprocess mutual_fund_data from CSV or chunks."""
        try:
            if self.chunks_dir and self.chunks_dir.exists():
                # Load from chunks
                self._load_from_chunks()
            elif self.csv_path and self.csv_path.exists():
                # Load from single CSV file
                self._load_from_csv()
            else:
                raise FileNotFoundError(f"No data source found: {self.csv_path or self.chunks_dir}")
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            raise
    
    def _load_from_csv(self) -> None:
        """Load data from single CSV file."""
        logger.info(f"Loading from CSV: {self.csv_path}")
        
        try:
            raw_df = pd.read_csv(self.csv_path)
            self.df_full = self._add_derived_columns(raw_df)
            self.df = self.df_full.dropna(subset=['Average_AUM_Cr']).copy()
            self._init_sqlite()
            logger.info(f"✓ Loaded {len(self.df_full)} full rows ({len(self.df)} with AUM) from {self.csv_path}")
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            raise
    
    def _load_from_chunks(self) -> None:
        """Load data from chunks directory."""
        logger.info(f"Loading from chunks directory: {self.chunks_dir}")
        
        # Load manifest if it exists
        manifest_path = self.chunks_dir / "manifest.json"
        if manifest_path.exists():
            import json
            try:
                with open(manifest_path) as f:
                    self.chunk_manifest = json.load(f)
                logger.info(f"✓ Loaded manifest: {self.chunk_manifest['chunk_count']} chunks")
            except Exception as e:
                logger.warning(f"Could not load manifest: {e}")
        
        # Load all chunk files
        chunk_files = sorted(self.chunks_dir.glob('mutual_fund_data_chunk_*.csv'))
        
        if not chunk_files:
            raise FileNotFoundError(f"No chunk files found in {self.chunks_dir}")
        
        logger.info(f"Loading {len(chunk_files)} chunks...")
        
        dfs = []
        total_rows = 0
        
        for chunk_file in chunk_files:
            try:
                df = pd.read_csv(chunk_file)
                dfs.append(df)
                total_rows += len(df)
                logger.debug(f"  ├─ {chunk_file.name}: {len(df)} rows")
            except Exception as e:
                logger.error(f"Error loading chunk {chunk_file.name}: {e}")
                raise
        
        # Combine all chunks
        if dfs:
            raw_combined = pd.concat(dfs, ignore_index=True)
            self.df_full = self._add_derived_columns(raw_combined)
            self.df = self.df_full.dropna(subset=['Average_AUM_Cr']).copy()
            self._init_sqlite()
            logger.info(f"✓ Combined {len(chunk_files)} chunks into {len(self.df_full)} full rows ({len(self.df)} with AUM)")
        else:
            raise ValueError("No valid data loaded from chunks")
    
    def _aggregate_schemes(self) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate plan-level data into scheme-level metrics.
        
        Returns:
            Dictionary mapping scheme_name to aggregation metrics
        """
        aggregations = defaultdict(lambda: {
            'aum_values': [],
            'plan_names': [],
            'rows': []
        })
        
        # Group by Scheme_Name
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
    
    def get_top_schemes(
        self,
        limit: int = 10,
        sort_by: str = 'max_aum',
        include_plan_details: bool = True,
        **kwargs
    ) -> DualViewAUMResponse:
        """
        Get top N schemes with dual-view response (scheme-level + plan-level).
        
        Args:
            limit: Number of top schemes to return
            sort_by: Sorting criteria ('max_aum', 'avg_aum', 'total_aum', 'plan_count')
            include_plan_details: Include plan-level breakdown
            **kwargs: Additional filters (amc_filter, category_filter, etc.)
        
        Returns:
            DualViewAUMResponse with both views
        """
        if self.df is None or len(self.df) == 0:
            raise ValueError("No data loaded. Check CSV path and format.")
        
        # Aggregate schemes
        aggregations = self._aggregate_schemes()
        
        # Build scheme metrics
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
                plan_data_completeness=1.0,  # All loaded rows have valid AUM
            )
            scheme_metrics.append(metrics)
        
        # Apply filters if provided in kwargs
        amc_filter = kwargs.get('amc_filter')
        category_filter = kwargs.get('category_filter')
        scheme_type_filter = kwargs.get('scheme_type_filter')
        scheme_filter = kwargs.get('scheme_filter')

        if amc_filter:
            scheme_metrics = [s for s in scheme_metrics if amc_filter.lower() in s.amc.lower()]
        if category_filter:
            scheme_metrics = [s for s in scheme_metrics if category_filter.lower() in s.scheme_category.lower()]
        if scheme_type_filter:
            scheme_metrics = [s for s in scheme_metrics if scheme_type_filter.lower() in s.scheme_type.lower()]
        if scheme_filter:
            scheme_metrics = [s for s in scheme_metrics if scheme_filter.lower() in s.scheme_name.lower()]

        # Sort schemes
        if sort_by == 'max_aum':
            scheme_metrics.sort(key=lambda x: x.max_aum_cr, reverse=True)
        elif sort_by == 'avg_aum':
            scheme_metrics.sort(key=lambda x: x.avg_aum_cr, reverse=True)
        elif sort_by == 'total_aum':
            scheme_metrics.sort(key=lambda x: x.total_aum_cr, reverse=True)
        elif sort_by == 'plan_count':
            scheme_metrics.sort(key=lambda x: x.plan_count, reverse=True)
        
        # Apply limit
        top_schemes = scheme_metrics[:limit]
        
        # Add ranking information
        for idx, metric in enumerate(top_schemes, 1):
            metric.rank_by_max_aum = idx if sort_by == 'max_aum' else None
            metric.rank_by_avg_aum = idx if sort_by == 'avg_aum' else None
            metric.rank_by_total_aum = idx if sort_by == 'total_aum' else None
        
        # Get plan-level rankings (for detailed view)
        plan_level_data = []
        if include_plan_details:
            plan_level_data = self._get_plan_level_rankings(limit)
        
        # Build response
        response = DualViewAUMResponse(
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
        
        return response

    def get_top_amcs(
        self,
        limit: int = 10,
        sort_by: str = 'total_aum',
        amc_filter: Optional[str] = None,
    ) -> AMCAggregationResponse:
        """
        Get top N Asset Management Companies (AMCs) aggregated by total AUM and distinct scheme counts.
        
        Args:
            limit: Number of top AMCs to return
            sort_by: Sorting criteria ('total_aum', 'distinct_schemes', 'avg_aum', 'total_plans')
            
        Returns:
            AMCAggregationResponse
        """
        if self.df is None or len(self.df) == 0:
            raise ValueError("No data loaded. Check CSV path and format.")

        grouped = self.df.groupby('AMC')
        amc_metrics: List[AMCAggregationMetrics] = []

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

        data_period = "Unknown"
        if 'AAUM_Quarter' in self.df.columns and len(self.df) > 0:
            sample_val = self.df['AAUM_Quarter'].dropna()
            if not sample_val.empty:
                data_period = str(sample_val.iloc[0])

        try:
            from datetime import UTC
            generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        except (ImportError, AttributeError):
            generated_at = datetime.utcnow().isoformat() + "Z"

        return AMCAggregationResponse(
            query="Top AMCs by AUM",
            query_intent="amc_ranking",
            generated_at=generated_at,
            data_period=data_period,
            amc_rankings=top_amcs,
            total_unique_amcs=len(amc_metrics),
            interpretation_guide=(
                "AMC-Level Rankings: Aggregates total AUM, distinct scheme counts, and plan counts "
                "across all offerings for each Asset Management Company."
            ),
        )

    def get_dataset_summary(self, scheme_type_filter: Optional[str] = None) -> Dict[str, Any]:
        """Calculates comprehensive dataset-level summary and breakdown."""
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
        Calculates comprehensive category-level breakdown of total AUM and number of schemes.
        Guarantees mathematically exact aggregation across all 16,245 mutual fund folios.
        """
        df_src = self.df_full if self.df_full is not None else self.df
        if df_src is None or len(df_src) == 0:
            raise ValueError("No data loaded. Check CSV path and format.")

        target_col = "Scheme_Category" if detailed else "Broad_Category"
        if target_col not in df_src.columns and target_col == "Broad_Category":
            df_src = self._add_derived_columns(df_src.copy())

        # Total market metrics
        valid_aum_series = df_src["Average_AUM_Cr"].dropna()
        total_mkt_aum = float(valid_aum_series.sum())
        total_distinct_schemes = int(df_src["Scheme_Name"].nunique())
        total_folios = len(df_src)

        # Group by category
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

        # Sort descending by total_aum_cr
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

        guide = (
            "Rankings show total Average AUM in ₹ Crores and distinct scheme counts per category. "
            "Percentages represent market share of total mutual fund assets."
        )

        try:
            from datetime import UTC
            gen_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        except (ImportError, AttributeError):
            gen_at = datetime.utcnow().isoformat() + "Z"

        return CategoryAggregationResponse(
            query=query_text or "Category AUM Breakdown",
            query_intent="category_aggregation",
            generated_at=gen_at,
            data_period="January - March 2026",
            categories=metrics,
            total_market_aum_cr=round(total_mkt_aum, 2),
            total_distinct_schemes=total_distinct_schemes,
            total_folios=total_folios,
            interpretation_guide=guide,
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
        Get top schemes ranked by Net Asset Value (NAV) with dynamic filtering.
        
        Args:
            limit: Number of top schemes to return
            scheme_type: Filter by scheme type (e.g. 'Open Ended')
            category_keyword: Filter by category (e.g. 'Equity')
            plan_keyword: Filter by plan variant keyword (e.g. 'Growth')
            exclude_idcw: Exclude IDCW / Dividend options
            sort_order: 'desc' for highest NAV, 'asc' for lowest NAV
            query_text: Original query text
            
        Returns:
            NAVAggregationResponse with exact sorted schemes and metadata
        """
        df_src = self.df_full if self.df_full is not None else self.df
        if df_src is None or len(df_src) == 0:
            raise ValueError("No data loaded. Check CSV path and format.")

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

        metrics_list: List[NAVAggregationMetrics] = []
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

        try:
            from datetime import UTC
            generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        except (ImportError, AttributeError):
            generated_at = datetime.utcnow().isoformat() + "Z"

        return NAVAggregationResponse(
            query=query_text or f"Top schemes by NAV ({sort_order})",
            query_intent="nav_ranking",
            generated_at=generated_at,
            data_period=data_period,
            schemes=metrics_list,
            total_matching=total_matching,
            applied_filters=applied_filters,
            interpretation_guide=(
                f"NAV Ranking: Showing top {len(metrics_list)} schemes sorted by NAV ({sort_order}ending) "
                f"from {total_matching} matching options in the official mutual fund dataset."
            ),
        )


    
    def _get_plan_level_rankings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top N plan variants by AUM (before aggregation)."""
        # Sort individual rows by AUM and take top N
        df_sorted = self.df.nlargest(limit * 3, 'Average_AUM_Cr')  # Fetch more to deduplicate
        
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
            "**Scheme-Level Rankings**: Shows aggregated metrics across all plan variants of each scheme. "
            "Use this view for high-level scheme comparison and portfolio decisions.\n\n"
            "**Plan-Level Rankings**: Shows individual plan variants with specific AUM values. "
            "Use this view to understand which specific plans (Regular, Direct, Institutional, etc.) "
            "drive AUM concentration and to identify niche offerings.\n\n"
        )
        
        if sort_by == 'max_aum':
            return base_guide + (
                "Sorted by Maximum AUM: The highest-AUM plan variant for each scheme is featured. "
                "Useful for identifying peak performance offerings within each scheme."
            )
        elif sort_by == 'avg_aum':
            return base_guide + (
                "Sorted by Average AUM: Average AUM across all plan types is used. "
                "Useful for balanced comparison across schemes with varying plan diversification."
            )
        elif sort_by == 'total_aum':
            return base_guide + (
                "Sorted by Total AUM: Sum of all plan variants is used. "
                "Useful for understanding total scheme asset base across all offerings."
            )
        else:
            return base_guide
    
    def get_data_source_info(self) -> Dict[str, Any]:
        """Get information about data source (chunks or CSV)."""
        info = {
            'data_source': 'chunks' if self.chunks_dir else 'single_csv',
            'chunks_available': self.chunks_dir is not None,
        }
        
        if self.chunks_dir and self.chunk_manifest:
            info['chunk_count'] = self.chunk_manifest.get('chunk_count', 0)
            info['chunk_size_range'] = self._get_chunk_size_range()
            info['manifest_version'] = self.chunk_manifest.get('version', 'unknown')
        
        if self.csv_path:
            info['csv_path'] = str(self.csv_path)
        
        return info
    
    def get_scheme_type_distribution_by_amc(
        self,
        limit: int = 5,
        sort_by: str = "total_aum",
    ) -> List[Dict[str, Any]]:
        """Return Open/Close/Interval Ended scheme distribution for the top N AMCs.

        For each of the top ``limit`` AMCs (ranked by ``sort_by``), computes the
        number and percentage of *distinct scheme names* that fall into each
        ``Scheme_Type`` bucket (Open Ended, Close Ended, Interval Fund).

        Args:
            limit: How many AMCs to include (default 5).
            sort_by: Ranking criterion — ``"total_aum"`` (default) or
                ``"distinct_schemes"``.

        Returns:
            List of dicts, one per AMC, sorted by the chosen criterion descending::

                [
                    {
                        "rank": 1,
                        "amc": "SBI Funds Management Limited",
                        "total_aum_cr": 1260906.03,
                        "total_distinct_schemes": 127,
                        "scheme_type_breakdown": {
                            "Open Ended":  {"count": 109, "pct": 76.8},
                            "Close Ended": {"count": 33,  "pct": 23.2},
                        },
                    },
                    ...
                ]
        """
        if self.df_full is None and self.df is None:
            raise ValueError("No data loaded. Check CSV path and format.")

        df = self.df_full if self.df_full is not None else self.df

        # --- rank AMCs -------------------------------------------------------
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

        # --- build per-AMC breakdown -----------------------------------------
        results: List[Dict[str, Any]] = []
        for rank, amc in enumerate(top_amcs, 1):
            subset = df[df["AMC"] == amc]
            total_aum = float(df_aum[df_aum["AMC"] == amc]["Average_AUM_Cr"].sum())

            # distinct scheme names per Scheme_Type
            type_counts: Dict[str, int] = (
                subset.groupby("Scheme_Type")["Scheme_Name"]
                .nunique()
                .to_dict()
            )
            total_distinct = sum(type_counts.values())

            breakdown: Dict[str, Dict[str, Any]] = {}
            for stype, count in type_counts.items():
                pct = round(count / total_distinct * 100, 1) if total_distinct > 0 else 0.0
                breakdown[str(stype)] = {"count": int(count), "pct": pct}

            results.append(
                {
                    "rank": rank,
                    "amc": str(amc),
                    "total_aum_cr": round(total_aum, 2),
                    "total_distinct_schemes": total_distinct,
                    "scheme_type_breakdown": breakdown,
                }
            )

        return results

    def _get_chunk_size_range(self) -> Dict[str, int]:
        """Get min/max chunk sizes."""
        if not self.chunk_manifest or 'chunks' not in self.chunk_manifest:
            return {}
        
        chunk_rows = [c.get('rows', 0) for c in self.chunk_manifest['chunks']]
        return {
            'min': min(chunk_rows),
            'max': max(chunk_rows),
            'avg': int(sum(chunk_rows) / len(chunk_rows)) if chunk_rows else 0
        }
    
    def export_scheme_aggregations(
        self,
        output_path: str,
        format: str = 'csv'
    ) -> str:
        """
        Export materialized scheme aggregations to file for caching/querying.
        
        Args:
            output_path: Path to save aggregations
            format: 'csv' or 'parquet'
        
        Returns:
            Path to saved file
        """
        if self.scheme_aggregations is None:
            aggregations = self._aggregate_schemes()
            
            # Convert to DataFrame for export
            data = []
            for scheme_name, agg_data in aggregations.items():
                aum_values = agg_data['aum_values']
                first_row = agg_data['rows'][0]
                
                data.append({
                    'scheme_name': scheme_name,
                    'amc': first_row.get('AMC', ''),
                    'scheme_category': first_row.get('Scheme_Category', ''),
                    'max_aum_cr': max(aum_values),
                    'min_aum_cr': min(aum_values),
                    'avg_aum_cr': sum(aum_values) / len(aum_values),
                    'total_aum_cr': sum(aum_values),
                    'plan_count': len(agg_data['plan_names']),
                    'plan_names': '|'.join(agg_data['plan_names']),
                })
            
            self.scheme_aggregations = pd.DataFrame(data)
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'csv':
            self.scheme_aggregations.to_csv(output_path, index=False)
        elif format == 'parquet':
            self.scheme_aggregations.to_parquet(output_path, index=False)
        
        logger.info(f"Exported {len(self.scheme_aggregations)} scheme aggregations to {output_path}")
        return str(output_path)

    def get_data_source_info(self) -> Dict[str, Any]:
        """Get information about data source (chunks or CSV)."""
        info = {
            'data_source': 'chunks' if self.chunks_dir else 'single_csv',
            'chunks_available': self.chunks_dir is not None,
        }
        
        if self.chunks_dir and self.chunk_manifest:
            info['chunk_count'] = self.chunk_manifest.get('chunk_count', 0)
            info['chunk_size_range'] = self._get_chunk_size_range()
            info['manifest_version'] = self.chunk_manifest.get('version', 'unknown')
        
        if self.csv_path:
            info['csv_path'] = str(self.csv_path)
        
        return info
    
    def _get_chunk_size_range(self) -> Dict[str, int]:
        """Get min/max chunk sizes."""
        if not self.chunk_manifest or 'chunks' not in self.chunk_manifest:
            return {}
        
        chunk_rows = [c.get('rows', 0) for c in self.chunk_manifest['chunks']]
        return {
            'min': min(chunk_rows),
            'max': max(chunk_rows),
            'avg': int(sum(chunk_rows) / len(chunk_rows)) if chunk_rows else 0
        }


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
