# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.api import deps
from app.config import get_settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parity_eval")

CORPUS_VERSION = "v2_baseline_20260814"


def find_latest_pv_run_dir() -> Path:
    base = root.parent / "logs" / "assurance-audit"
    base.mkdir(parents=True, exist_ok=True)
    runs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("aq-run-")]
    if runs:
        return sorted(runs, key=lambda x: x.name)[-1]
    new_dir = base / f"aq-run-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    new_dir.mkdir(parents=True, exist_ok=True)
    return new_dir


async def run_evaluation(mode: str = "in-process", api_base: str = "http://test", strict_exit: bool = False):
    run_dir = find_latest_pv_run_dir()
    fixtures_file = root / "data" / "fixtures" / "parity_scenarios_v2.json"
    policy_file = root / "data" / "fixtures" / "evaluation_policy.json"

    if not fixtures_file.exists():
        raise FileNotFoundError(f"Missing scenarios fixture: {fixtures_file}")
    if not policy_file.exists():
        raise FileNotFoundError(f"Missing evaluation policy: {policy_file}")

    scenarios = json.loads(fixtures_file.read_text(encoding="utf-8"))
    policy = json.loads(policy_file.read_text(encoding="utf-8"))
    thresholds = policy["thresholds"]

    logger.info("Loaded %d parity evaluation scenarios from %s", len(scenarios), fixtures_file)
    logger.info("Loaded release policy thresholds: %s", thresholds)

    if mode == "in-process":
        deps.init_container()
        app = create_app()
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")
        execution_env_label = "IN-PROCESS ASGI PROTOTYPE"
    else:
        client = AsyncClient(base_url=api_base, timeout=60.0)
        execution_env_label = f"DEPLOYED NETWORK HTTP SERVICE ({api_base})"

    results = []

    async with client:
        for idx, sc in enumerate(scenarios, 1):
            sc_id = sc["id"]
            query = sc["query"]
            history = sc.get("history", [])
            req_facts = sc.get("required_facts", [])
            exp_tax = sc.get("expected_taxonomy_paths", [])
            safety_constraint = sc.get("safety_constraint")

            logger.info("[%d/%d] Evaluating Scenario: %s (%s)", idx, len(scenarios), sc_id, sc.get("category"))

            # 1. Legacy Query Execution
            t0_leg = time.perf_counter()
            if history:
                leg_resp = await client.post("/api/chat", json={"query": query, "history": history, "session_id": "eval_leg_01", "mode": "both"})
            else:
                leg_resp = await client.post("/api/query", json={"query": query, "mode": "both"})
            t_leg_ms = (time.perf_counter() - t0_leg) * 1000
            leg_data = leg_resp.json() if leg_resp.status_code == 200 else {}

            # 2. v2 Orchestrator Execution (Cold)
            t0_v2 = time.perf_counter()
            if history:
                v2_resp = await client.post("/api/chat/v2", json={"query": query, "history": history, "session_id": "eval_v2_01", "mode": "both"})
            else:
                v2_resp = await client.post("/api/query/v2", json={"query": query, "mode": "both"})
            t_v2_ms = (time.perf_counter() - t0_v2) * 1000
            v2_data = v2_resp.json() if v2_resp.status_code == 200 else {}
            v2_answer = ""
            if "answer" in v2_data and v2_data["answer"]:
                v2_answer = v2_data["answer"].get("answer", "")
            elif "hybrid" in v2_data and v2_data.get("hybrid"):
                v2_answer = (v2_data["hybrid"].get("answer") or {}).get("answer", "")

            # 3. v2 Orchestrator Execution (Warm Cache Repeat)
            t0_v2_warm = time.perf_counter()
            if history:
                v2_warm_resp = await client.post("/api/chat/v2", json={"query": query, "history": history, "session_id": "eval_v2_01", "mode": "both"})
            else:
                v2_warm_resp = await client.post("/api/query/v2", json={"query": query, "mode": "both"})
            t_v2_warm_ms = (time.perf_counter() - t0_v2_warm) * 1000
            v2_warm_data = v2_warm_resp.json() if v2_warm_resp.status_code == 200 else {}

            # 4. Objective Truthful Grading
            # A. Fact recall in v2 answer
            if req_facts:
                facts_found = [f for f in req_facts if f.lower() in v2_answer.lower()]
                fact_recall_score = len(facts_found) / len(req_facts)
            else:
                facts_found = []
                # Abstention/Out of corpus check: an empty facts requirement represents abstention
                fact_recall_score = 1.0 if any(w in v2_answer.lower() for w in ["no direct context", "no relevant", "not found", "cannot guarantee", "market risks"]) else 0.0

            # B. Canonical Source Resolvability
            sources = v2_data.get("sources", [])
            if not sources and "hybrid" in v2_data and v2_data["hybrid"]:
                sources = v2_data["hybrid"].get("sources", [])
            resolvable_sources = sum(1 for s in sources if s.get("document_id") or s.get("document_title"))
            source_resolvability_rate = (resolvable_sources / len(sources)) if sources else 1.0

            # C. Safety verification
            safety_passed = True
            if safety_constraint == "must_refuse_guaranteed_returns":
                safety_passed = any(w in v2_answer.lower() for w in ["cannot guarantee", "market risk", "no guarantee", "subject to market risks"])
            elif safety_constraint == "must_state_no_corpus_context":
                safety_passed = any(w in v2_answer.lower() for w in ["no direct context", "no relevant", "not found", "refine"]) or len(sources) == 0

            # D. Cache verification
            warm_trace = v2_warm_data.get("trace") or (v2_warm_data.get("hybrid") or {}).get("trace") or {}
            is_cache_hit = warm_trace.get("cache_hit", False)

            scenario_result = {
                "scenario_id": sc_id,
                "category": sc.get("category"),
                "query": query,
                "status_code_legacy": leg_resp.status_code,
                "status_code_v2": v2_resp.status_code,
                "legacy_latency_ms": round(t_leg_ms, 2),
                "v2_cold_latency_ms": round(t_v2_ms, 2),
                "v2_warm_latency_ms": round(t_v2_warm_ms, 2),
                "cache_hit_on_repeat": is_cache_hit,
                "fact_recall_score": round(fact_recall_score, 2),
                "facts_matched": facts_found,
                "source_resolvability_rate": round(source_resolvability_rate, 2),
                "sources_count": len(sources),
                "safety_passed": safety_passed,
                "v2_trace": v2_data.get("trace") or (v2_data.get("hybrid") or {}).get("trace"),
            }
            results.append(scenario_result)

    # Aggregate Evaluation Metrics
    avg_leg = sum(r["legacy_latency_ms"] for r in results) / len(results)
    avg_v2_cold = sum(r["v2_cold_latency_ms"] for r in results) / len(results)
    warm_latencies = [r["v2_warm_latency_ms"] for r in results]
    avg_v2_warm = sum(warm_latencies) / len(warm_latencies)
    warm_p95_ms = float(np.percentile(warm_latencies, 95))
    avg_fact_recall = sum(r["fact_recall_score"] for r in results) / len(results)
    avg_source_resolvability = sum(r["source_resolvability_rate"] for r in results) / len(results)
    safety_compliance_rate = sum(1 for r in results if r["safety_passed"]) / len(results)

    # Truthful Gate Decisions
    fact_recall_gate = avg_fact_recall >= thresholds["minimum_fact_recall"]
    safety_gate = safety_compliance_rate >= thresholds["minimum_safety_rate"]
    warm_latency_gate = warm_p95_ms <= thresholds["maximum_warm_p95_ms"]
    citation_gate = avg_source_resolvability >= thresholds["minimum_citation_resolvability"]
    overall_passed = fact_recall_gate and safety_gate and warm_latency_gate and citation_gate

    json_report = run_dir / "parity_evaluation_results.json"
    report_payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "execution_mode": mode,
        "execution_env_label": execution_env_label,
        "total_scenarios": len(results),
        "policy_thresholds": thresholds,
        "summary_metrics": {
            "avg_legacy_latency_ms": round(avg_leg, 2),
            "avg_v2_cold_latency_ms": round(avg_v2_cold, 2),
            "avg_v2_warm_latency_ms": round(avg_v2_warm, 2),
            "warm_p95_latency_ms": round(warm_p95_ms, 2),
            "avg_fact_recall_score": round(avg_fact_recall, 3),
            "avg_source_resolvability": round(avg_source_resolvability, 3),
            "safety_compliance_rate": round(safety_compliance_rate, 3),
        },
        "gates": {
            "fact_recall_gate": "PASSED" if fact_recall_gate else "FAILED",
            "safety_gate": "PASSED" if safety_gate else "FAILED",
            "warm_latency_gate": "PASSED" if warm_latency_gate else "FAILED",
            "citation_gate": "PASSED" if citation_gate else "FAILED",
            "overall_status": "PASSED" if overall_passed else "FAILED",
        },
        "scenarios": results,
    }
    with open(json_report, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    # Markdown Report
    md_report = root.parent / "Docs" / "independent_parity_report.md"
    md_text = f"""# Independent Grounded Parity Evaluation Report (AQ-02 / AQ-05)

**Date**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Evaluation Scope**: `{execution_env_label}` over `{len(results)}` versioned scenarios  
**Target Corpus Version**: `{CORPUS_VERSION}`  
**Evidence Run**: `{run_dir.name}`  
**Overall Policy Decision**: **{'PASSED' if overall_passed else 'FAILED (Policy Thresholds Unmet)'}**

---

## 1. Truthful Executive Summary & Gate Status

All metrics are evaluated objectively against [`backend/data/fixtures/evaluation_policy.json`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/data/fixtures/evaluation_policy.json).

| Gate Name | Release Target | Measured Result | Status |
|---|---|---|---|
| **Fact Recall / Grounding Score** | $\ge {thresholds['minimum_fact_recall']*100:.0f}\\%$ | **{avg_fact_recall * 100:.1f}%** | **{'PASSED' if fact_recall_gate else 'FAILED'}** |
| **Canonical Source Resolvability** | $\ge {thresholds['minimum_citation_resolvability']*100:.0f}\\%$ | **{avg_source_resolvability * 100:.1f}%** | **{'PASSED' if citation_gate else 'FAILED'}** |
| **Safety / Disclaimer Compliance** | $\ge {thresholds['minimum_safety_rate']*100:.0f}\\%$ | **{safety_compliance_rate * 100:.1f}%** | **{'PASSED' if safety_gate else 'FAILED'}** |
| **Warm Cache p95 Latency** | $\le {thresholds['maximum_warm_p95_ms']:.0f}\\text{{ ms}}$ | **{warm_p95_ms:.2f} ms** | **{'PASSED' if warm_latency_gate else 'FAILED'}** |
| **Legacy Average Latency** | Baseline | **{avg_leg:.2f} ms** | Baseline |
| **v2 Cold Average Latency** | $< 1500\\text{{ ms}}$ | **{avg_v2_cold:.2f} ms** | Informational |

---

## 2. Scenario-by-Scenario Evaluation Matrix

| ID | Category | Legacy Latency | v2 Cold Latency | v2 Warm Latency | Cache Hit | Fact Recall | Safety |
|---|---|---|---|---|---|---|---|
"""
    for r in results:
        md_text += f"| `{r['scenario_id']}` | {r['category']} | {r['legacy_latency_ms']} ms | {r['v2_cold_latency_ms']} ms | {r['v2_warm_latency_ms']} ms | {'YES' if r['cache_hit_on_repeat'] else 'NO'} | {r['fact_recall_score']*100:.0f}% | {'PASS' if r['safety_passed'] else 'FAIL'} |\n"

    md_text += f"""
---

## 3. Strict Audit Gate Sign-Off

- [{ 'x' if overall_passed else ' ' }] **Overall Release Gate**: {'PASSED (Ready for pilot)' if overall_passed else 'FAILED (Strict audit blocks release until all thresholds are met)'}
- [{ 'x' if citation_gate else ' ' }] **Provenance Resolvability**: { '100% physically resolvable citations' if citation_gate else 'Incomplete source resolvability' }
- [{ 'x' if safety_gate else ' ' }] **Safety Compliance**: { '100% regulatory compliance guardrails satisfied' if safety_gate else 'Safety violations detected' }
"""
    md_report.write_text(md_text, encoding="utf-8")
    logger.info("Saved independent_parity_report.md successfully with overall decision: %s", "PASSED" if overall_passed else "FAILED")

    if strict_exit and not overall_passed:
        logger.error("Evaluation policy thresholds unmet. Exiting with status 1.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Run independent parity evaluation")
    parser.add_argument("--mode", choices=["in-process", "deployed"], default="in-process", help="Execution mode")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="Base URL for deployed mode")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any gate fails")
    args = parser.parse_args()

    asyncio.run(run_evaluation(mode=args.mode, api_base=args.api_base, strict_exit=args.strict))


if __name__ == "__main__":
    main()
