# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
pipeline_scheduler.py
=====================
Production Data Pipeline Orchestrator.
Coordinates RSS polling, AMFI ingestion, gateway validation, index building,
graph lifecycle enrichment, and staleness drift monitoring into a single execution workflow.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import pandas as pd

import config
import sebi_feed_ingester
import amfi_portal_adapter
import amfi_member_portal
import provenance_ledger

LOG_FILE = config.LOG_DIR / "pipeline_run_log.jsonl"


def run_production_pipeline(mode: str = "incremental") -> Dict[str, Any]:
    """
    Run full production data acquisition and enrichment pipeline.
    """
    t_start = time.perf_counter()
    print("=" * 65, flush=True)
    print("[PRODUCTION PIPELINE] AMC CONTEXT ENGINEERING PIPELINE RUN", flush=True)
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Mode: {mode}", flush=True)
    print("=" * 65, flush=True)

    # Step 1: SEBI RSS Poll
    print("\n[Step 1/5] Polling SEBI RSS Feed...", flush=True)
    sebi_report = sebi_feed_ingester.run_daily_sebi_poll()

    # Step 2: AMFI Portal & Member Portal Ingest
    print("\n[Step 2/5] Ingesting AMFI NAV Feed & Member Inbox...", flush=True)
    nav_df = amfi_portal_adapter.fetch_nav_all()
    inbox_res = amfi_member_portal.ingest_from_member_inbox()

    # Step 3: Incremental Index Build
    print("\n[Step 3/5] Running Incremental Indexing Engine...", flush=True)
    indexed_new = 0
    try:
        import build_index
        build_index.build(rebuild=(mode == "rebuild"))
        indexed_new = 1
    except Exception as exc:
        print(f"  [Pipeline Scheduler] Index build notice: {exc}", flush=True)

    # Step 4: Graph Lifecycle Enrichment
    print("\n[Step 4/5] Running Regulatory Graph Lifecycle Enrichment...", flush=True)
    proposed_edges_count = 0
    try:
        import regulatory_lifecycle_enricher
        all_records = provenance_ledger.get_all_records()
        proposed = regulatory_lifecycle_enricher.detect_and_link_amendments_from_titles(all_records)
        proposed_edges_count = len(proposed)
        print(f"  [Pipeline Scheduler] Created {proposed_edges_count} proposed supersession edges.", flush=True)
    except Exception as exc:
        print(f"  [Pipeline Scheduler] Graph lifecycle notice: {exc}", flush=True)

    # Step 5: Staleness Drift Check (Sample 10)
    print("\n[Step 5/5] Running Staleness Drift Detection...", flush=True)
    drift_report = {}
    try:
        import staleness_monitor
        drift_rep = staleness_monitor.run_drift_check(sample_size=10)
        drift_report = {
            "checked_count": drift_rep.checked_count,
            "drifted_count": drift_rep.drifted_count,
            "not_found_count": drift_rep.not_found_count
        }
    except Exception as exc:
        print(f"  [Pipeline Scheduler] Staleness monitor notice: {exc}", flush=True)

    elapsed = round(time.perf_counter() - t_start, 2)

    summary = {
        "status": "COMPLETED",
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": elapsed,
        "sebi_rss": sebi_report,
        "amfi_nav_records": len(nav_df) if isinstance(nav_df, pd.DataFrame) else 0,
        "inbox_processed": len(inbox_res),
        "proposed_edges_created": proposed_edges_count,
        "drift_report": drift_report
    }

    # Append to JSONL log
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
    except Exception:
        pass

    print("\n" + "=" * 65, flush=True)
    print(f"[COMPLETE] PIPELINE FINISHED IN {elapsed}s", flush=True)
    print("=" * 65, flush=True)
    return summary


if __name__ == "__main__":
    run_production_pipeline()
