# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""PV-01 Environment Preflight & Validation Script.

Verifies interpreter, virtual environment, dependencies, Neo4j connectivity,
and target corpus storage before executing post-convergence validation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("preflight")


def compute_file_sha256(filepath: Path) -> str:
    if not filepath.exists():
        return "missing"
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def main():
    run_id = f"aq-run-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    log_dir = root.parent / "logs" / "assurance-audit" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)

    # 1. Environment & Subprocess Viability Check (AQ-01)
    py_version = sys.version
    py_exec = sys.executable
    os_info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }

    test_subp = subprocess.run(
        [py_exec, "-c", "import sys, faiss, neo4j, fastapi; print(f'SUBPROCESS_OK:{sys.version}')"],
        capture_output=True,
        text=True,
    )
    if test_subp.returncode != 0:
        raise RuntimeError(f"Python launcher failed to execute test subprocess: {test_subp.stderr}")

    # 2. Pip Freeze
    pip_freeze_raw = ""
    try:
        pip_freeze_raw = subprocess.check_output([py_exec, "-m", "pip", "freeze"], text=True)
    except Exception as exc:
        pip_freeze_raw = f"Error running pip freeze: {exc}"

    freeze_file = log_dir / "requirements-freeze.txt"
    freeze_file.write_text(pip_freeze_raw, encoding="utf-8")

    # 3. Requirements Check
    req_file = root / "requirements.txt"
    req_sha = compute_file_sha256(req_file)

    # 4. Target Corpus Files
    corpus_version = "v2_baseline_20260814"
    vector_dir = root / "data" / "vector_store" / corpus_version
    index_faiss = vector_dir / "index.faiss"
    payloads_json = vector_dir / "payloads.json"
    ledger_file = root / "data" / "corpora" / corpus_version / "ledger.json"

    vector_status = {
        "corpus_version": corpus_version,
        "vector_dir_exists": vector_dir.exists(),
        "index_faiss_exists": index_faiss.exists(),
        "index_faiss_bytes": index_faiss.stat().st_size if index_faiss.exists() else 0,
        "payloads_json_exists": payloads_json.exists(),
        "payloads_json_bytes": payloads_json.stat().st_size if payloads_json.exists() else 0,
        "ledger_exists": ledger_file.exists(),
        "ledger_entries_count": len(json.loads(ledger_file.read_text(encoding="utf-8"))) if ledger_file.exists() else 0,
    }

    # 5. Neo4j Ping
    from app.config import get_settings
    from neo4j import GraphDatabase
    settings = get_settings()
    neo4j_status = "error"
    neo4j_nodes = 0
    try:
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        with driver.session(database=settings.neo4j_database) as s:
            rec = s.run("RETURN 1 AS ok").single()
            if rec and rec["ok"] == 1:
                neo4j_status = "ok"
                count_res = s.run("MATCH (n) RETURN count(n) AS c").single()
                neo4j_nodes = count_res["c"] if count_res else 0
        driver.close()
    except Exception as exc:
        neo4j_status = f"error: {exc}"

    preflight_data = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "python_executable": py_exec,
        "python_version": py_version,
        "os_info": os_info,
        "requirements_txt_sha256": req_sha,
        "neo4j": {
            "uri": settings.neo4j_uri,
            "database": settings.neo4j_database,
            "status": neo4j_status,
            "total_nodes": neo4j_nodes,
        },
        "target_corpus": vector_status,
        "active_serving_engine": settings.query_engine,
        "active_corpus_version": settings.active_corpus_version,
    }

    preflight_file = log_dir / "environment_preflight.json"
    preflight_file.write_text(json.dumps(preflight_data, indent=2), encoding="utf-8")

    logger.info("Preflight validation complete for run %s", run_id)
    logger.info("Artifacts saved -> %s", log_dir)
    print(json.dumps(preflight_data, indent=2))
    return run_id


if __name__ == "__main__":
    main()
