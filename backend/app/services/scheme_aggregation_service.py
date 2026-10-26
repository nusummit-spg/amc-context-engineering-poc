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

from app.models.scheme_aggregation import (
    SchemeAggregationMetrics,
    DualViewAUMResponse,
    SchemeAggregationRequest
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
        self.df = None
        self.scheme_aggregations = None
        self.chunk_manifest = None
        self._load_data()
    
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
            self.df = pd.read_csv(self.csv_path)
            # Convert Average_AUM_Cr to numeric
            self.df['Average_AUM_Cr'] = pd.to_numeric(
                self.df['Average_AUM_Cr'],
                errors='coerce'
            )
            # Drop rows without valid AUM data
            self.df = self.df.dropna(subset=['Average_AUM_Cr'])
            
            logger.info(f"✓ Loaded {len(self.df)} rows with valid AUM data from {self.csv_path}")
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
                # Convert Average_AUM_Cr to numeric
                df['Average_AUM_Cr'] = pd.to_numeric(
                    df['Average_AUM_Cr'],
                    errors='coerce'
                )
                # Drop rows without valid AUM
                df = df.dropna(subset=['Average_AUM_Cr'])
                
                dfs.append(df)
                total_rows += len(df)
                
                logger.debug(f"  ├─ {chunk_file.name}: {len(df)} rows")
            except Exception as e:
                logger.error(f"Error loading chunk {chunk_file.name}: {e}")
                raise
        
        # Combine all chunks
        if dfs:
            self.df = pd.concat(dfs, ignore_index=True)
            logger.info(f"✓ Combined {len(chunk_files)} chunks into {len(self.df)} rows")
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


# Singleton instance for application use
_service_instance: Optional[SchemeAggregationService] = None


def get_aggregation_service() -> SchemeAggregationService:
    """Get or create singleton instance of SchemeAggregationService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SchemeAggregationService()
    return _service_instance


def reset_aggregation_service() -> None:
    """Reset singleton instance (useful for testing)."""
    global _service_instance
    _service_instance = None

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
