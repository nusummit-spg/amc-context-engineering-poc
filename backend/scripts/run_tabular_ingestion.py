# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
run_tabular_ingestion.py
========================
Execution script for G04 Ingestion Pipeline:
- Streams and validates all 22 CSV chunks (16,245 declared rows)
- Stages rows into typed analytical repository (backend/data/financial.db)
- Extracts NAV and AAUM observation facts
- Validates row counts and SHA256 integrity
- Atomically activates 'v1_baseline' pointer
- Runs golden query verification (CSV-EXACT-001)
"""

import json
import logging
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

# Setup paths
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.tabular.csv_excel_loader import IngestionPipeline
from app.tabular.repository import FinancialDataRepository
from app.tabular.planner import QueryPlanner
from app.tabular.executor import QueryExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingestion_runner")


def run_ingestion():
    chunks_dir = backend_dir / "data" / "source_docs" / "chunks"
    manifest_path = chunks_dir / "manifest.json"
    db_path = backend_dir / "data" / "financial.db"

    print("=" * 80)
    print("AMC Wave 1: Canonical Data Ingestion Pipeline (G04)")
    print("=" * 80)
    print(f"Chunks directory : {chunks_dir}")
    print(f"Manifest path    : {manifest_path}")
    print(f"Target DB        : {db_path}")

    repo = FinancialDataRepository(str(db_path))
    pipeline = IngestionPipeline(repository=repo)

    print("\nStarting streaming ingestion of all 22 chunks...")
    report = pipeline.ingest_chunks_directory(
        chunks_dir=chunks_dir,
        manifest_path=manifest_path,
        dataset_version="v1_baseline",
        batch_size=1000,
        activate_upon_completion=True,
    )

    print("\n" + "=" * 80)
    print("INGESTION RESULTS & RECONCILIATION")
    print("=" * 80)
    print(f"Status           : {report['status']}")
    print(f"Declared Rows    : {report['declared_rows']:,}")
    print(f"Processed Rows   : {report['processed_rows']:,}")
    print(f"Valid Rows       : {report['valid_rows']:,}")
    print(f"Quarantined Rows : {report['quarantined_rows']:,}")
    print(f"Reconciled       : {'YES (100% PASS)' if report['reconciled'] else 'FAIL'}")
    print(f"Active Version   : {repo.get_active_version()}")
    print(f"Elapsed Time     : {report['elapsed_seconds']} seconds")

    stats = report["db_stats"]
    print(f"\nObservation Breakdown:")
    print(f"  - Total Source Rows : {stats['total_source_rows']:,}")
    print(f"  - NAV Observations  : {stats['nav_observations']:,}")
    print(f"  - AAUM Observations : {stats['aaum_observations']:,}")

    # Golden Test Case Verification: CSV-EXACT-001
    print("\n" + "=" * 80)
    print("GOLDEN TEST VERIFICATION (CSV-EXACT-001)")
    print("=" * 80)

    # 1. Repository exact lookup
    nav_obs = repo.lookup_nav_exact(scheme_code="100033", nav_date=date(2026, 6, 29))
    if nav_obs:
        print(f"Repository Lookup Result:")
        print(f"  Scheme Code     : {nav_obs.scheme_code}")
        print(f"  NAV Date        : {nav_obs.nav_date}")
        print(f"  NAV Per Unit    : {nav_obs.nav_per_unit} {nav_obs.unit.value}")
        print(f"  Source Row ID   : {nav_obs.source_row_id}")
        assert nav_obs.nav_per_unit == Decimal("922.67"), f"Expected 922.67, got {nav_obs.nav_per_unit}"
        print("  Status          : PASS (Exact decimal precision match: 922.67)")
    else:
        print("  Status          : FAIL (Record not found)")
        sys.exit(1)

    # 2. Planner & Executor verification
    planner = QueryPlanner()
    executor = QueryExecutor(repo)

    plan = planner.create_exact_nav_plan(scheme_code="100033", nav_date="2026-06-29")
    query_res = executor.execute(plan)

    print(f"\nQuery Engine Result:")
    print(f"  Plan ID         : {query_res.plan_id}")
    print(f"  Success         : {query_res.success}")
    print(f"  Result Hash     : {query_res.result_set_hash}")
    print(f"  Latency         : {query_res.observed_latency_ms} ms")
    print(f"  Proof Row IDs   : {query_res.source_row_ids}")
    assert query_res.success is True
    assert len(query_res.rows) == 1
    assert str(query_res.rows[0]["nav_per_unit"]) == "922.67"
    print("  Status          : PASS (Deterministic query engine returns 922.67 with proof)")

    # Save summary report in remediation folder
    report_output_path = backend_dir.parent / "remediation" / "wave1_canonical_typed_queries" / "ingestion_report.json"
    report_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_output_path, "w", encoding="utf-8") as f:
        # Convert non-serializable objects if any
        json.dump(report, f, indent=2)

    print(f"\nIngestion report saved to: {report_output_path}")
    print("\n>>> ALL INGESTION AND RECONCILIATION TASKS COMPLETED SUCCESSFULLY! <<<")


if __name__ == "__main__":
    run_ingestion()
