# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""PV-05 & PV-06 Shadow Pilot and Feature-Flag Promotion/Rollback Drill.

Exercises dynamic engine switching between legacy, v2, and shadow modes,
verifying zero-downtime serving changes and data-plane telemetry truthfulness.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.api import deps
from app.config import get_settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("promotion_drill")


def find_latest_pv_run_dir() -> Path:
    base = root.parent / "logs" / "post-convergence"
    runs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("pv-run-")]
    if runs:
        return sorted(runs, key=lambda x: x.name)[-1]
    new_dir = base / f"pv-run-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    new_dir.mkdir(parents=True, exist_ok=True)
    return new_dir


async def main():
    run_dir = find_latest_pv_run_dir()
    drill_log_file = run_dir / "promotion_rollback_drill.log"
    log_lines = [
        "=== POST-CONVERGENCE PROMOTION & ROLLBACK DRILL (PV-05 / PV-06) ===",
        f"Timestamp: {datetime.utcnow().isoformat()}Z",
        f"Run Directory: {run_dir.name}",
        "",
    ]

    settings = get_settings()
    deps.init_container()
    app = create_app()
    transport = ASGITransport(app=app)

    test_query = "What are the large cap categorization rules under SEBI circular?"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        container = deps.get_container()

        # Step 1: Baseline legacy mode
        os.environ["QUERY_ENGINE"] = "legacy"
        container.settings.query_engine = "legacy"
        resp_status = await client.get("/api/status/data-planes")
        status_data = resp_status.json()
        log_lines.append(f"[Step 1: Baseline Legacy] Serving Engine: {status_data.get('serving_engine')}")
        assert status_data.get("serving_engine") == "legacy"

        resp_query = await client.post("/api/query", json={"query": test_query})
        assert resp_query.status_code == 200
        log_lines.append(f"Legacy POST /api/query -> HTTP {resp_query.status_code} (Trace in payload: {'trace' in resp_query.json()})")

        # Step 2: Shadow mode pilot (PV-05)
        os.environ["QUERY_ENGINE"] = "shadow"
        container.settings.query_engine = "shadow"
        resp_status = await client.get("/api/status/data-planes")
        status_data = resp_status.json()
        log_lines.append(f"[Step 2: Shadow Pilot] Serving Engine: {status_data.get('serving_engine')}")
        assert status_data.get("serving_engine") == "shadow"

        resp_shadow = await client.post("/api/query", json={"query": test_query})
        assert resp_shadow.status_code == 200
        log_lines.append(f"Shadow POST /api/query -> HTTP {resp_shadow.status_code}")

        # Step 3: Staged Promotion to v2 (PV-06)
        os.environ["QUERY_ENGINE"] = "v2"
        container.settings.query_engine = "v2"
        resp_status = await client.get("/api/status/data-planes")
        status_data = resp_status.json()
        log_lines.append(f"[Step 3: Promotion to v2] Serving Engine: {status_data.get('serving_engine')}")
        assert status_data.get("serving_engine") == "v2"

        resp_v2 = await client.post("/api/query", json={"query": test_query})
        assert resp_v2.status_code == 200
        v2_json = resp_v2.json()
        has_v2_trace = "trace" in v2_json or ("hybrid" in v2_json and "trace" in v2_json.get("hybrid", {}))
        log_lines.append(f"v2 POST /api/query -> HTTP {resp_v2.status_code} (Trace present: {has_v2_trace})")
        assert has_v2_trace

        # Step 4: Zero-Downtime Rollback to Legacy
        os.environ["QUERY_ENGINE"] = "legacy"
        container.settings.query_engine = "legacy"
        resp_status = await client.get("/api/status/data-planes")
        status_data = resp_status.json()
        log_lines.append(f"[Step 4: Rollback to Legacy] Serving Engine: {status_data.get('serving_engine')}")
        assert status_data.get("serving_engine") == "legacy"

        resp_rollback = await client.post("/api/query", json={"query": test_query})
        assert resp_rollback.status_code == 200
        log_lines.append(f"Rollback POST /api/query -> HTTP {resp_rollback.status_code}")

        log_lines.append("")
        log_lines.append("=== DRILL STATUS: ALL GATES PASSED (Promotion and Rollback Verified) ===")

    output_text = "\n".join(log_lines)
    drill_log_file.write_text(output_text, encoding="utf-8")
    print(output_text)
    logger.info("Saved promotion_rollback_drill.log successfully to %s", drill_log_file)


if __name__ == "__main__":
    asyncio.run(main())
