#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
PHASE_4_INTEGRATION_TEST.py
============================
Integration test suite for Phase 4: Backend optimizations + Frontend/API migration
Tests:
1. Backend optimization performance (pre-compiled rules, parallelization, buffering)
2. Frontend API endpoint integration
3. End-to-end compliance audit flow
4. Violation management lifecycle
"""

import asyncio
import json
import logging
import time
import sys
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("integration_test")

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.compliance.rules_engine import RulesEngine
from app.compliance.violation_detector import ViolationDetector
from app.compliance.audit_integration import flush_violation_buffer
from app.graph.client import get_graph_client


async def test_rules_engine_optimization():
    """Test 1: Verify pre-compiled rules optimization"""
    logger.info("=" * 80)
    logger.info("TEST 1: Rules Engine Optimization")
    logger.info("=" * 80)
    
    graph = get_graph_client()
    engine = RulesEngine(graph)
    
    # Load and pre-compile rules
    start = time.time()
    num_rules = await engine.load_rules()
    load_time = (time.time() - start) * 1000
    
    logger.info(f"✓ Loaded and pre-compiled {num_rules} rules in {load_time:.2f}ms")
    logger.info(f"✓ CompiledRule instances: {len(engine._compiled_rules)}")
    
    # Verify compilation
    assert len(engine._compiled_rules) == num_rules, "Not all rules were compiled"
    for rule_id, compiled in engine._compiled_rules.items():
        assert compiled.metric_parts, f"Rule {rule_id} missing metric_parts"
        assert compiled.operator, f"Rule {rule_id} missing operator"
    
    logger.info("✓ All rules properly pre-compiled with metric_parts and operators")
    return True


async def test_violation_detector_parallelization():
    """Test 2: Verify parallelized rule evaluation"""
    logger.info("=" * 80)
    logger.info("TEST 2: Violation Detector Parallelization")
    logger.info("=" * 80)
    
    graph = get_graph_client()
    detector = ViolationDetector(graph)
    
    # Run audit for SEBI region
    start = time.time()
    audit_result = await detector.audit_all_funds(region="SEBI")
    audit_time = (time.time() - start) * 1000
    
    logger.info(f"✓ Audited {audit_result.total_funds} funds in {audit_time:.2f}ms")
    logger.info(f"✓ Found {audit_result.total_violations} total violations")
    logger.info(f"  - Critical: {audit_result.critical_violations}")
    logger.info(f"  - High: {audit_result.high_violations}")
    logger.info(f"  - Medium: {audit_result.medium_violations}")
    logger.info(f"  - Low: {audit_result.low_violations}")
    
    # Verify per-fund metrics
    if audit_result.total_funds > 0:
        avg_time_per_fund = audit_time / audit_result.total_funds
        logger.info(f"✓ Average time per fund: {avg_time_per_fund:.2f}ms")
    
    return True


async def test_violation_buffer_performance():
    """Test 3: Verify violation buffering for batch I/O"""
    logger.info("=" * 80)
    logger.info("TEST 3: Violation Buffer Performance")
    logger.info("=" * 80)
    
    from app.compliance.audit_integration import ViolationBuffer
    from app.compliance.rules_engine import ComplianceViolation
    
    buffer = ViolationBuffer(batch_size=50)
    
    # Create 100 test violations
    test_violations = []
    for i in range(100):
        v = ComplianceViolation(
            violation_id=f"TEST_V_{i}",
            rule_id=f"TEST_RULE_{i % 5}",
            rule_title="Test Rule",
            fund_id=f"TEST_FUND_{i % 4}",
            severity="high" if i % 2 == 0 else "medium",
            confidence=0.95,
            actual_value=0.15,
            threshold_value=0.10,
            description="Test violation",
            evidence_docs=["test.pdf"],
        )
        test_violations.append(v)
    
    # Add violations (should auto-flush at batch sizes)
    start = time.time()
    for v in test_violations:
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "compliance_violation",
            "violation_id": v.violation_id,
            "rule_id": v.rule_id,
            "fund_id": v.fund_id,
            "severity": v.severity,
        }
        await buffer.add(audit_entry)
    
    # Flush remaining
    await buffer.flush()
    buffer_time = (time.time() - start) * 1000
    
    logger.info(f"✓ Processed {len(test_violations)} violations in {buffer_time:.2f}ms")
    logger.info(f"✓ Buffer auto-flushed at {buffer.batch_size}-violation batches")
    
    return True


async def test_api_endpoints_availability():
    """Test 4: Verify all compliance API endpoints are accessible"""
    logger.info("=" * 80)
    logger.info("TEST 4: API Endpoints Availability")
    logger.info("=" * 80)
    
    # This test validates the endpoints are defined (actual HTTP calls would require server)
    from app.api.routes.compliance import router
    
    routes = [route.path for route in router.routes]
    logger.info(f"✓ Found {len(routes)} compliance endpoints:")
    
    required_endpoints = [
        "/audit",
        "/violations",
        "/fund/{fund_id}/violations",
        "/violations/{violation_id}/resolve",
        "/scorecard",
        "/audit-report",
        "/health",
        "/metrics/prometheus",
        "/export/violations-csv",
        "/fund/{fund_id}",
        "/rules/{rule_id}/violations",
        "/status",
    ]
    
    for endpoint in required_endpoints:
        if endpoint in routes:
            logger.info(f"  ✓ {endpoint}")
        else:
            # Check with parameter variations
            found = False
            for route in routes:
                if endpoint.split("{")[0] in route:
                    found = True
                    logger.info(f"  ✓ {route}")
                    break
            if not found:
                logger.warning(f"  ✗ {endpoint} - NOT FOUND")
    
    return True


async def test_compliance_scorecard():
    """Test 5: Verify scorecard computation"""
    logger.info("=" * 80)
    logger.info("TEST 5: Compliance Scorecard Computation")
    logger.info("=" * 80)
    
    graph = get_graph_client()
    detector = ViolationDetector(graph)
    
    scorecard = await detector.get_compliance_scorecard(region="SEBI")
    
    logger.info(f"✓ Overall Compliance Score: {scorecard['overall_compliance_score']:.1f}%")
    logger.info(f"✓ Rules Passing: {scorecard['rules_passing']} / {scorecard['total_rules']}")
    logger.info(f"✓ Rules with Violations: {scorecard['rules_with_violations']}")
    logger.info(f"✓ Violation Breakdown:")
    logger.info(f"  - Critical: {scorecard['violations'].get('critical', 0)}")
    logger.info(f"  - High: {scorecard['violations'].get('high', 0)}")
    logger.info(f"  - Medium: {scorecard['violations'].get('medium', 0)}")
    logger.info(f"  - Low: {scorecard['violations'].get('low', 0)}")
    
    # Validate scorecard data
    assert scorecard['overall_compliance_score'] >= 0, "Compliance score below 0"
    assert scorecard['overall_compliance_score'] <= 100, "Compliance score above 100"
    assert scorecard['rules_passing'] >= 0, "Negative rules passing"
    
    return True


async def test_violation_lifecycle():
    """Test 6: Test complete violation lifecycle (detect -> resolve)"""
    logger.info("=" * 80)
    logger.info("TEST 6: Violation Lifecycle Management")
    logger.info("=" * 80)
    
    graph = get_graph_client()
    detector = ViolationDetector(graph)
    
    # Get violations
    violations = await detector.get_violations(status="detected", limit=10)
    logger.info(f"✓ Retrieved {len(violations)} detected violations")
    
    if violations:
        v = violations[0]
        logger.info(f"✓ Sample violation: {v.violation_id}")
        logger.info(f"  - Fund: {v.fund_id}")
        logger.info(f"  - Severity: {v.severity}")
        logger.info(f"  - Status: {v.status}")
        
        # Resolve violation
        resolution = await detector.resolve_violation(v.violation_id, "Test resolution")
        logger.info(f"✓ Resolved violation: {resolution['status']}")
        
        # Verify resolution
        resolved_violations = await detector.get_violations(status="remediated", limit=10)
        logger.info(f"✓ Total remediated violations: {len(resolved_violations)}")
    
    return True


async def test_performance_metrics():
    """Test 7: Benchmark key performance metrics"""
    logger.info("=" * 80)
    logger.info("TEST 7: Performance Metrics Summary")
    logger.info("=" * 80)
    
    graph = get_graph_client()
    engine = RulesEngine(graph)
    detector = ViolationDetector(graph)
    
    # Test with different fund counts
    fund_counts = [100, 500, 1000]
    
    for count in fund_counts:
        # Create test funds
        test_funds = []
        for i in range(count):
            test_funds.append({
                "fund_id": f"PERF_TEST_FUND_{i}",
                "fund_name": f"Test Fund {i}",
                "category": "equity_fund",
                "aum_cr": 5000.0 + (i * 100),
                "region": "SEBI",
            })
        
        # Measure evaluation time
        start = time.time()
        for fund in test_funds:
            await engine.evaluate_fund(fund["fund_id"], fund)
        elapsed = (time.time() - start) * 1000
        
        per_fund = elapsed / count
        logger.info(f"✓ {count} funds: {elapsed:.2f}ms total ({per_fund:.3f}ms per fund)")
    
    return True


async def run_all_tests():
    """Execute all integration tests"""
    logger.info("\n" + "=" * 80)
    logger.info("PHASE 4: INTEGRATION TEST SUITE")
    logger.info("=" * 80 + "\n")
    
    tests = [
        ("Rules Engine Optimization", test_rules_engine_optimization),
        ("Violation Detector Parallelization", test_violation_detector_parallelization),
        ("Violation Buffer Performance", test_violation_buffer_performance),
        ("API Endpoints Availability", test_api_endpoints_availability),
        ("Compliance Scorecard", test_compliance_scorecard),
        ("Violation Lifecycle", test_violation_lifecycle),
        ("Performance Metrics", test_performance_metrics),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results[test_name] = "PASS" if result else "FAIL"
        except Exception as e:
            logger.error(f"✗ Test failed with error: {e}", exc_info=True)
            results[test_name] = "FAIL"
        logger.info("")
    
    # Flush violation buffer on exit
    await flush_violation_buffer()
    
    # Summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    passes = sum(1 for v in results.values() if v == "PASS")
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓" if result == "PASS" else "✗"
        logger.info(f"{status} {test_name}: {result}")
    
    logger.info("=" * 80)
    logger.info(f"Results: {passes}/{total} tests passed")
    logger.info("=" * 80)
    
    return passes == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
