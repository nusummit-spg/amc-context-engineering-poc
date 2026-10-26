#!/usr/bin/env python
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
scripts/migrate_aum_improvements.py
===================================
Migration script for deploying AUM query improvements.

This script:
1. Verifies all required files are in place
2. Tests the SchemeAggregationService
3. Pre-computes and caches aggregations
4. Validates the dual-view response format
5. Generates deployment report
"""

import sys
import os
from pathlib import Path
import json
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationValidator:
    """Validates and executes AUM improvements migration."""
    
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.backend_root = self.project_root / "backend"
        self.app_root = self.backend_root / "app"
        self.status = {
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
            "errors": [],
            "warnings": [],
            "success": True
        }
    
    def log_check(self, name: str, passed: bool, message: str):
        """Log a check result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} - {name}: {message}")
        self.status["checks"][name] = {
            "passed": passed,
            "message": message
        }
        if not passed:
            self.status["success"] = False
            self.status["errors"].append(f"{name}: {message}")
    
    def log_warning(self, message: str):
        """Log a warning."""
        logger.warning(f"⚠️  WARNING - {message}")
        self.status["warnings"].append(message)
    
    def check_files_exist(self) -> bool:
        """Check that all required files exist."""
        required_files = [
            self.app_root / "engine" / "config.py",
            self.app_root / "models" / "scheme_aggregation.py",
            self.app_root / "services" / "scheme_aggregation_service.py",
            self.app_root / "api" / "routes" / "scheme_aggregation_routes.py",
            self.backend_root / "data" / "source_docs" / "mutual_fund_data.csv",
        ]
        
        logger.info("\n" + "="*80)
        logger.info("CHECKING: Required Files")
        logger.info("="*80)
        
        all_exist = True
        for file_path in required_files:
            exists = file_path.exists()
            relative_path = file_path.relative_to(self.project_root)
            self.log_check(f"File: {relative_path.name}", exists, str(relative_path))
            all_exist = all_exist and exists
        
        return all_exist
    
    def check_config_updated(self) -> bool:
        """Check that CYPHER_MAX_ROWS is updated."""
        logger.info("\n" + "="*80)
        logger.info("CHECKING: Configuration Updates")
        logger.info("="*80)
        
        config_file = self.app_root / "engine" / "config.py"
        try:
            with open(config_file) as f:
                content = f.read()
            
            # Check for updated CYPHER_MAX_ROWS
            has_updated = 'CYPHER_MAX_ROWS = int(os.environ.get("CYPHER_MAX_ROWS", "100"))' in content
            self.log_check(
                "CYPHER_MAX_ROWS updated to 100",
                has_updated,
                "Configuration file updated" if has_updated else "Config not yet updated"
            )
            
            # Check for query-specific limits
            has_query_limits = 'CYPHER_QUERY_LIMITS' in content
            self.log_check(
                "Query-specific limits configured",
                has_query_limits,
                "Query limits defined" if has_query_limits else "Query limits not defined"
            )
            
            return has_updated and has_query_limits
        except Exception as e:
            self.log_check("Configuration check", False, str(e))
            return False
    
    def test_service_import(self) -> bool:
        """Test that the SchemeAggregationService can be imported."""
        logger.info("\n" + "="*80)
        logger.info("CHECKING: Service Import")
        logger.info("="*80)
        
        try:
            sys.path.insert(0, str(self.backend_root))
            from app.services.scheme_aggregation_service import SchemeAggregationService, get_aggregation_service
            self.log_check("SchemeAggregationService import", True, "Service imported successfully")
            return True
        except Exception as e:
            self.log_check("SchemeAggregationService import", False, str(e))
            self.status["errors"].append(f"Import error: {e}")
            return False
    
    def test_service_initialization(self) -> bool:
        """Test that the service can be initialized."""
        logger.info("\n" + "="*80)
        logger.info("CHECKING: Service Initialization")
        logger.info("="*80)
        
        try:
            sys.path.insert(0, str(self.backend_root))
            from app.services.scheme_aggregation_service import SchemeAggregationService
            
            csv_path = self.backend_root / "data" / "source_docs" / "mutual_fund_data.csv"
            service = SchemeAggregationService(csv_path=str(csv_path))
            
            rows_loaded = len(service.df) if service.df is not None else 0
            self.log_check(
                "Service initialization",
                rows_loaded > 0,
                f"Service loaded {rows_loaded} rows from CSV"
            )
            
            return rows_loaded > 0
        except Exception as e:
            self.log_check("Service initialization", False, str(e))
            self.status["errors"].append(f"Initialization error: {e}")
            return False
    
    def test_aggregation(self) -> bool:
        """Test the aggregation functionality."""
        logger.info("\n" + "="*80)
        logger.info("CHECKING: Aggregation Functionality")
        logger.info("="*80)
        
        try:
            sys.path.insert(0, str(self.backend_root))
            from app.services.scheme_aggregation_service import SchemeAggregationService
            
            csv_path = self.backend_root / "data" / "source_docs" / "mutual_fund_data.csv"
            service = SchemeAggregationService(csv_path=str(csv_path))
            
            # Test getting top schemes
            response = service.get_top_schemes(limit=5, sort_by='max_aum')
            
            schemes_returned = len(response.scheme_level_rankings)
            plans_returned = len(response.plan_level_rankings)
            
            success = schemes_returned == 5 and plans_returned > 0
            self.log_check(
                "Top schemes query",
                success,
                f"Returned {schemes_returned} schemes and {plans_returned} plans"
            )
            
            # Verify top scheme is correct
            if schemes_returned > 0:
                top_scheme = response.scheme_level_rankings[0]
                is_sbi_nifty = "SBI Nifty 50 ETF" in top_scheme.scheme_name
                self.log_check(
                    "Top scheme identification",
                    is_sbi_nifty,
                    f"Top scheme: {top_scheme.scheme_name} (AUM: ₹{top_scheme.max_aum_cr:,.2f} Cr)"
                )
                success = success and is_sbi_nifty
            
            return success
        except Exception as e:
            self.log_check("Aggregation test", False, str(e))
            self.status["errors"].append(f"Aggregation error: {e}")
            return False
    
    def test_dual_view_response(self) -> bool:
        """Test the dual-view response format."""
        logger.info("\n" + "="*80)
        logger.info("CHECKING: Dual-View Response Format")
        logger.info("="*80)
        
        try:
            sys.path.insert(0, str(self.backend_root))
            from app.services.scheme_aggregation_service import SchemeAggregationService
            
            csv_path = self.backend_root / "data" / "source_docs" / "mutual_fund_data.csv"
            service = SchemeAggregationService(csv_path=str(csv_path))
            
            response = service.get_top_schemes(limit=10, include_plan_details=True)
            
            # Check response structure
            has_scheme_view = hasattr(response, 'scheme_level_rankings') and len(response.scheme_level_rankings) > 0
            has_plan_view = hasattr(response, 'plan_level_rankings') and len(response.plan_level_rankings) > 0
            has_stats = hasattr(response, 'total_unique_schemes')
            
            self.log_check("Scheme-level view", has_scheme_view, "Scheme rankings available")
            self.log_check("Plan-level view", has_plan_view, "Plan rankings available")
            self.log_check("Statistics", has_stats, "Statistics included")
            
            # Check data quality
            if has_scheme_view and has_stats:
                schemes = response.total_unique_schemes
                plans = response.total_plan_variants
                completeness = response.data_completeness
                
                logger.info(f"  ├─ Unique schemes: {schemes}")
                logger.info(f"  ├─ Total plan variants: {plans}")
                logger.info(f"  ├─ Data completeness: {completeness*100:.1f}%")
                logger.info(f"  └─ Multi-plan schemes: {response.schemes_with_multiple_plans}")
            
            return has_scheme_view and has_plan_view and has_stats
        except Exception as e:
            self.log_check("Dual-view response test", False, str(e))
            self.status["errors"].append(f"Response test error: {e}")
            return False
    
    def cache_aggregations(self) -> bool:
        """Pre-compute and cache aggregations."""
        logger.info("\n" + "="*80)
        logger.info("ACTION: Caching Aggregations")
        logger.info("="*80)
        
        try:
            sys.path.insert(0, str(self.backend_root))
            from app.services.scheme_aggregation_service import SchemeAggregationService
            
            csv_path = self.backend_root / "data" / "source_docs" / "mutual_fund_data.csv"
            service = SchemeAggregationService(csv_path=str(csv_path))
            
            # Create cache directory
            cache_dir = self.backend_root / "cache" / "scheme_aggregations"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Export to CSV and Parquet
            csv_path_out = str(cache_dir / "scheme_aggregations.csv")
            parquet_path_out = str(cache_dir / "scheme_aggregations.parquet")
            
            try:
                csv_result = service.export_scheme_aggregations(csv_path_out, format='csv')
                self.log_check("Cache: CSV export", True, f"Exported to {csv_result}")
            except Exception as e:
                self.log_warning(f"CSV export failed (parquet-only mode): {e}")
            
            try:
                parquet_result = service.export_scheme_aggregations(parquet_path_out, format='parquet')
                self.log_check("Cache: Parquet export", True, f"Exported to {parquet_result}")
            except Exception as e:
                self.log_warning(f"Parquet export failed: {e}")
            
            return True
        except Exception as e:
            self.log_warning(f"Caching failed: {e}")
            return True  # Non-critical
    
    def generate_report(self) -> None:
        """Generate migration report."""
        logger.info("\n" + "="*80)
        logger.info("MIGRATION SUMMARY")
        logger.info("="*80)
        
        # Count check results
        total_checks = len(self.status["checks"])
        passed_checks = sum(1 for c in self.status["checks"].values() if c["passed"])
        
        logger.info(f"\nResults: {passed_checks}/{total_checks} checks passed")
        logger.info(f"Errors: {len(self.status['errors'])}")
        logger.info(f"Warnings: {len(self.status['warnings'])}")
        
        if self.status["errors"]:
            logger.error("\nErrors encountered:")
            for error in self.status["errors"]:
                logger.error(f"  ❌ {error}")
        
        if self.status["warnings"]:
            logger.warning("\nWarnings:")
            for warning in self.status["warnings"]:
                logger.warning(f"  ⚠️  {warning}")
        
        # Final status
        if self.status["success"]:
            logger.info("\n✅ MIGRATION SUCCESSFUL - Ready for deployment")
        else:
            logger.error("\n❌ MIGRATION FAILED - Please resolve errors before deploying")
        
        # Save report
        report_path = self.backend_root / "migration_report.json"
        with open(report_path, 'w') as f:
            json.dump(self.status, f, indent=2)
        logger.info(f"\nReport saved to: {report_path}")
    
    def run(self) -> bool:
        """Execute all migration checks."""
        logger.info("\n" + "#"*80)
        logger.info("# AUM Query Improvements - Migration & Validation")
        logger.info("#"*80)
        logger.info(f"Project Root: {self.project_root}")
        logger.info(f"Timestamp: {self.status['timestamp']}")
        
        # Run all checks
        self.check_files_exist()
        self.check_config_updated()
        self.test_service_import()
        self.test_service_initialization()
        self.test_aggregation()
        self.test_dual_view_response()
        self.cache_aggregations()
        
        # Generate report
        self.generate_report()
        
        return self.status["success"]


def main():
    """Main entry point."""
    validator = MigrationValidator()
    success = validator.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
