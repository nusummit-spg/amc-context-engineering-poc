# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
run_intent_cache_audit.py
=========================
Deep validation script executing 10 comprehensive intent cache audit steps:
1. Intent Classification & Domain Partitioning
2. Cold Query (Cache Miss) & Structured Storage
3. Exact Match Fast-Path (Stage 1 Fingerprint Probe O(1) Hit)
4. Semantically Paraphrased Match (Stage 2 Vector Cosine Hit >= Threshold)
5. Temporal Guarding (Date Entity Guard prevents stale Q1 vs Q2 false hits)
6. Intent/Domain Boundary Guard (Cross-domain queries cannot cross-contaminate)
7. Stale Data Prevention & TTL Expiry Eviction
8. Selective Domain Invalidation (One domain purged, others preserved)
9. Global Multi-Layer Invalidation (/api/admin/cache/clear)
10. Telemetry & Financial/Carbon Savings Ledger Audit
"""

import os
import sys
import time
import json
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from streamlit_app.intent_cache import (
    IntentAwareCache,
    SavingsLedger,
    classify_domain_intent,
    _extract_date_entities,
    DOMAIN_TTL,
    CACHE_THRESHOLD_BY_INTENT,
)
from app.engine.semantic_cache import SemanticCache
from app.retrieval.cache import SemanticQueryCache

def run_audit():
    print("================================================================================")
    print("       INTENT CACHE DEEP VERIFICATION & AUDIT BENCHMARK")
    print("================================================================================\n")

    audit_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "steps": [],
        "overall_status": "PASSED"
    }

    test_dir = PROJECT_ROOT / "backend" / "logs" / "test_cache"
    test_dir.mkdir(parents=True, exist_ok=True)
    disk_store = str(test_dir / "audit_intent_cache.json")

    cache = IntentAwareCache(shadow_mode=False, disk_path=disk_store)
    cache.clear_all()

    # Helper vectors
    dim = 384
    rng = np.random.RandomState(42)
    base_v = rng.randn(dim).astype(np.float32)
    base_v = base_v / (np.linalg.norm(base_v) + 1e-9)

    # -------------------------------------------------------------
    # Step 1: Intent Classification & Domain Partitioning
    # -------------------------------------------------------------
    print("[Step 1] Validating Intent Classification & Domain Partitioning...")
    q_sebi = "What are SEBI regulations on mutual fund borrowing limits?"
    q_fin = "What was the fund revenue and EBITDA for Q1 FY24?"
    q_esg = "Report carbon emissions and BRSR compliance status"
    q_fund = "Compare expense ratio and TER for flexicap schemes"
    q_gov = "Review board audit committee and ERP corporate governance"

    dom_sebi = classify_domain_intent(q_sebi)
    dom_fin = classify_domain_intent(q_fin)
    dom_esg = classify_domain_intent(q_esg)
    dom_fund = classify_domain_intent(q_fund)
    dom_gov = classify_domain_intent(q_gov)

    step1_ok = (
        dom_sebi == "sebi_regulation" and
        dom_fin == "financial_performance" and
        dom_esg == "esg_sustainability" and
        dom_fund == "fund_performance" and
        dom_gov == "corporate_governance"
    )
    print(f"  -> Classification: SEBI={dom_sebi}, Fin={dom_fin}, ESG={dom_esg}, Fund={dom_fund}, Gov={dom_gov}")
    print(f"  -> Result: {'PASSED' if step1_ok else 'FAILED'}\n")
    audit_results["steps"].append({"step": 1, "name": "Intent Classification", "status": "PASSED" if step1_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 2: Cold Query (Cache Miss) & Structured Storage
    # -------------------------------------------------------------
    print("[Step 2] Testing Cold Query Cache Miss & Storage...")
    t0 = time.perf_counter()
    miss_res = cache.lookup(base_v, "v2_dual_regime_taxonomy", "sebi_regulation", q_sebi)
    lat_miss_ms = (time.perf_counter() - t0) * 1000.0

    step2_ok = (miss_res is None)
    print(f"  -> Cold Lookup: {'MISS (Expected)' if step2_ok else 'UNEXPECTED HIT'} (Latency: {lat_miss_ms:.3f} ms)")

    # Store payload
    cache.store(
        query_vec=base_v,
        query_type="v2_dual_regime_taxonomy",
        domain_intent="sebi_regulation",
        query_text=q_sebi,
        answer="Under SEBI Regulation 44(2), a mutual fund can borrow up to 20% of net assets for max 6 months.",
        provenance=[{"doc": "SEBI_MF_Regulations_1996.pdf", "page": 22}],
        confidence_label="high confidence (verified)",
        confidence_reason="SEBI Regulation 44(2)",
        total_tokens=1950,
        input_tokens_cold=1800,
        output_tokens_cold=150,
        graph_nodes=["Mutual Fund", "Borrowing Limit", "20%"],
        graph_edges=[{"s": "Mutual Fund", "rel": "MAX_BORROWING", "o": "20%"}],
    )
    stored_ok = len(cache._entries_by_domain["sebi_regulation"]) == 1 and os.path.exists(disk_store)
    print(f"  -> Storage & Disk Sync: {'PERSISTED CLEANLY' if stored_ok else 'FAILED'}\n")
    audit_results["steps"].append({"step": 2, "name": "Cold Miss & Store", "status": "PASSED" if (step2_ok and stored_ok) else "FAILED"})

    # -------------------------------------------------------------
    # Step 3: Exact Match Fast-Path (Stage 1 Fingerprint Probe O(1) Hit)
    # -------------------------------------------------------------
    print("[Step 3] Testing Stage 1 Exact Match (O(1) Fingerprint Probe)...")
    t1 = time.perf_counter()
    probe_hit = cache.fingerprint_probe(q_sebi.upper())  # test case-insensitivity
    lat_probe_ms = (time.perf_counter() - t1) * 1000.0

    step3_ok = (probe_hit is not None and "borrow up to 20%" in probe_hit.answer and lat_probe_ms < 10.0)
    print(f"  -> Fingerprint Probe: {'HIT (Expected)' if probe_hit else 'MISS'}")
    print(f"  -> Probe Latency: {lat_probe_ms:.4f} ms (Target < 10ms for O(1) memory lookup)")
    print(f"  -> Answer Verified: {probe_hit.answer[:60]}...\n")
    audit_results["steps"].append({"step": 3, "name": "Stage 1 Fingerprint Probe Hit", "latency_ms": round(lat_probe_ms, 4), "status": "PASSED" if step3_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 4: Semantically Paraphrased Match (Stage 2 Vector Cosine Hit)
    # -------------------------------------------------------------
    print("[Step 4] Testing Stage 2 Semantic Lookup for Paraphrased Query...")
    q_sebi_paraphrase = "What are the restrictions and borrowing limits for mutual fund schemes under SEBI rules?"
    
    # Generate high-similarity vector (cosine sim = 0.97 >= 0.94 threshold)
    noise = np.random.RandomState(88).randn(dim).astype(np.float32)
    noise -= np.dot(noise, base_v) * base_v
    noise /= (np.linalg.norm(noise) + 1e-9)
    sim_target = 0.97
    v_paraphrase = (sim_target * base_v + np.sqrt(1.0 - sim_target**2) * noise).astype(np.float32)

    t2 = time.perf_counter()
    sem_hit = cache.lookup(v_paraphrase, "v2_dual_regime_taxonomy", "sebi_regulation", q_sebi_paraphrase)
    lat_sem_ms = (time.perf_counter() - t2) * 1000.0

    step4_ok = (sem_hit is not None and "borrow up to 20%" in sem_hit.answer)
    print(f"  -> Semantic Lookup: {'HIT (Expected)' if sem_hit else 'MISS'}")
    print(f"  -> Cosine Sim: {float(np.dot(base_v, v_paraphrase)):.3f} >= Threshold {CACHE_THRESHOLD_BY_INTENT['sebi_regulation']}")
    print(f"  -> Semantic Latency: {lat_sem_ms:.3f} ms\n")
    audit_results["steps"].append({"step": 4, "name": "Stage 2 Semantic Lookup Hit", "latency_ms": round(lat_sem_ms, 3), "status": "PASSED" if step4_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 5: Temporal Guarding (Date Entity Guard)
    # -------------------------------------------------------------
    print("[Step 5] Testing Date Entity Guard (Preventing Stale/Wrong Quarter Hits)...")
    q_q1 = "What was the fund dividend distribution in Q1 FY24?"
    q_q2 = "What was the fund dividend distribution in Q2 FY24?"
    v_fin = rng.randn(dim).astype(np.float32)
    v_fin = v_fin / (np.linalg.norm(v_fin) + 1e-9)

    cache.store(
        query_vec=v_fin,
        query_type="direct_lookup",
        domain_intent="financial_performance",
        query_text=q_q1,
        answer="Dividend payout for Q1 FY24 was 1.50 INR per unit.",
        provenance=[],
        confidence_label="high",
        confidence_reason="audited statement",
        total_tokens=1200,
    )

    # Lookup with identical vector but Q2 text: MUST MISS to prevent wrong quarter answer!
    q2_hit = cache.lookup(v_fin, "direct_lookup", "financial_performance", q_q2)
    step5_ok = (q2_hit is None)
    print(f"  -> Date Entity Guard: {'BLOCKED FALSE POSITIVE (Expected)' if step5_ok else 'FALSE HIT DETECTED!'}")
    print(f"  -> Q1 Text Dates: {_extract_date_entities(q_q1)} vs Q2 Text Dates: {_extract_date_entities(q_q2)}\n")
    audit_results["steps"].append({"step": 5, "name": "Date Entity Temporal Guard", "status": "PASSED" if step5_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 6: Intent / Domain Boundary Guard
    # -------------------------------------------------------------
    print("[Step 6] Testing Domain Boundary Isolation...")
    # Lookup the SEBI query inside the financial_performance domain bucket -> MUST MISS
    cross_miss = cache.lookup(base_v, "v2_dual_regime_taxonomy", "financial_performance", q_sebi)
    step6_ok = (cross_miss is None)
    print(f"  -> Cross-Domain Query Isolation: {'SECURE (No Cross-Contamination)' if step6_ok else 'CROSS-DOMAIN LEAK!'}\n")
    audit_results["steps"].append({"step": 6, "name": "Domain Boundary Isolation", "status": "PASSED" if step6_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 7: Stale Data Prevention & TTL Expiry Eviction
    # -------------------------------------------------------------
    print("[Step 7] Testing Stale Data Prevention & TTL Eviction...")
    q_stale = "Short-term credit rating for commercial paper"
    v_stale = rng.randn(dim).astype(np.float32)
    v_stale = v_stale / (np.linalg.norm(v_stale) + 1e-9)

    cache.store(
        query_vec=v_stale,
        query_type="direct_lookup",
        domain_intent="financial_performance",
        query_text=q_stale,
        answer="Rated A1+ as of last review.",
        provenance=[],
        confidence_label="medium",
        confidence_reason="credit bulletin",
        total_tokens=900,
    )

    # Artificially age the entry past its 7-day TTL
    ttl_fin = DOMAIN_TTL["financial_performance"]
    for e in cache._entries_by_domain["financial_performance"]:
        if e.query_text == q_stale:
            e.created_at = time.time() - (ttl_fin + 3600)  # expired by 1 hour

    # Lookup should detect expiration, prune entry, and return None
    ttl_miss = cache.lookup(v_stale, "direct_lookup", "financial_performance", q_stale)
    step7_ok = (ttl_miss is None)
    print(f"  -> Stale TTL Check: {'EXPIRED & EVICTED CLEANLY (Expected)' if step7_ok else 'STALE ENTRY RETURNED!'}\n")
    audit_results["steps"].append({"step": 7, "name": "Stale Data TTL Eviction", "status": "PASSED" if step7_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 8: Selective Domain Invalidation
    # -------------------------------------------------------------
    print("[Step 8] Testing Selective Domain Invalidation...")
    # Invalidate ONLY 'sebi_regulation'
    cache.invalidate_domain("sebi_regulation")
    sebi_empty = len(cache._entries_by_domain["sebi_regulation"]) == 0
    fin_preserved = len(cache._entries_by_domain["financial_performance"]) >= 1

    step8_ok = (sebi_empty and fin_preserved)
    print(f"  -> SEBI Domain Bucket: {'PURGED (0 entries)' if sebi_empty else 'NOT PURGED'}")
    print(f"  -> Financial Domain Bucket: {'PRESERVED INTACT' if fin_preserved else 'ACCIDENTALLY PURGED'}\n")
    audit_results["steps"].append({"step": 8, "name": "Selective Domain Invalidation", "status": "PASSED" if step8_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 9: Global Multi-Layer Invalidation (/api/admin/cache/clear)
    # -------------------------------------------------------------
    print("[Step 9] Testing Global Multi-Tier Invalidation...")
    cache.clear_all()
    all_zero = all(len(entries) == 0 for entries in cache._entries_by_domain.values())
    fp_zero = len(cache._fingerprint_index) == 0

    # Also test EngineSemanticCache clear
    eng_cache = SemanticCache(threshold=0.50)
    eng_cache.store("temp algo query", {"answer": "test"})
    eng_cache.clear()
    eng_zero = (eng_cache.next_id == 0)

    # Also test RetrievalSemanticCache clear
    ret_cache = SemanticQueryCache(dim=384)
    ret_cache.store(base_v, {"answer": "ret_test"})
    ret_cache.clear()
    ret_zero = (ret_cache.count() == 0)

    step9_ok = (all_zero and fp_zero and eng_zero and ret_zero)
    print(f"  -> IntentAwareCache Buckets Cleared: {all_zero}")
    print(f"  -> Engine SemanticCache Cleared: {eng_zero}")
    print(f"  -> Retrieval SemanticQueryCache Cleared: {ret_zero}\n")
    audit_results["steps"].append({"step": 9, "name": "Global Multi-Tier Invalidation", "status": "PASSED" if step9_ok else "FAILED"})

    # -------------------------------------------------------------
    # Step 10: Savings Ledger Telemetry Audit
    # -------------------------------------------------------------
    print("[Step 10] Testing Telemetry & Financial/Carbon Savings Ledger...")
    ledger_path = str(test_dir / "audit_savings_ledger.json")
    ledger = SavingsLedger(disk_path=ledger_path)
    ledger._data = {"total_hits": 0, "total_misses": 0, "tokens_saved_cumulative": 0, "cost_saved_cumulative_usd": 0.0, "co2_saved_grams": 0.0}

    # Simulate 100 cache hits with avg 2,100 tokens saved each
    for _ in range(100):
        ledger.record_hit(tokens_saved=2100, cold_cost_usd=0.0035)
    for _ in range(25):
        ledger.record_miss()

    summary = ledger.summary()
    step10_ok = (
        summary["total_hits"] == 100 and
        summary["total_misses"] == 25 and
        summary["hit_rate_pct"] == 80.0 and
        summary["tokens_saved_cumulative"] == 210000 and
        summary["cost_saved_cumulative_usd"] == 0.35 and
        summary["co2_saved_grams"] == 42.0
    )
    print(f"  -> Total Hits / Misses: {summary['total_hits']} / {summary['total_misses']} (Hit Rate: {summary['hit_rate_pct']}%)")
    print(f"  -> Tokens Saved: {summary['tokens_saved_cumulative']:,} tokens")
    print(f"  -> Cost Saved: ${summary['cost_saved_cumulative_usd']:.4f} USD")
    print(f"  -> CO2 Saved: {summary['co2_saved_grams']:.2f} grams\n")
    audit_results["steps"].append({"step": 10, "name": "Savings Ledger Accounting", "summary": summary, "status": "PASSED" if step10_ok else "FAILED"})

    # Summary
    all_passed = all(s["status"] == "PASSED" for s in audit_results["steps"])
    audit_results["overall_status"] = "PASSED" if all_passed else "FAILED"

    report_path = PROJECT_ROOT / "backend" / "intent_cache_audit_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)

    print("================================================================================")
    print(f"   AUDIT COMPLETE: {'ALL 10 VERIFICATION STEPS PASSED PERFECTLY (10/10)' if all_passed else 'SOME STEPS FAILED'}")
    print(f"   Report saved to: {report_path}")
    print("================================================================================")

if __name__ == '__main__':
    run_audit()
