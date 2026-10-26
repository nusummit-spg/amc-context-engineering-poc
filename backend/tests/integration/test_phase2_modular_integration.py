"""
End-to-End Integration Suite for Phase 2 Modularization.
Tests:
1. Core adapter instantiation and health.
2. In-process integration of amc_feedback and amc_repair packages.
3. Circuit breaker resilience and recovery under simulated failures.
4. Seamless patch propagation into platform context.
"""
import pytest
from app.core.adapters import (
    create_feedback_config,
    create_repair_config,
    get_feedback_loop,
    get_repair_engine,
)
from app.clients.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

@pytest.mark.asyncio
async def test_modular_adapters_lifecycle():
    feedback_loop = get_feedback_loop()
    repair_engine = get_repair_engine()

    assert feedback_loop is not None
    assert repair_engine is not None

    # Verify feedback loop processing
    claim = await feedback_loop.process_feedback(
        session_id="mod_sess_01",
        response_id="mod_resp_01",
        feedback_text="Axis Bluechip Fund TER is actually 0.82%, not 0.79%",
        original_query="What is the TER of Axis Bluechip Fund?",
        original_response="TER is 0.79%"
    )
    assert claim is not None
    assert claim.attribute == "TER"
    assert claim.asserted_value == "0.82"

    # Verify repair engine hot patch creation and self-healing context injection
    patch = await repair_engine.patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute=claim.attribute,
        corrected_value=claim.asserted_value,
        original_value=claim.rejected_value,
        confidence=claim.confidence,
        auto_approve=True
    )
    assert patch.approved is True

    retrieved_raw = "Fund factsheet lists Axis Bluechip Fund with an expense ratio of 0.79%."
    healed = await repair_engine.patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5"],
        retrieval_context=retrieved_raw
    )
    assert "0.82" in healed
    assert "[CORRECTION PATCH APPLIED" in healed

def test_circuit_breaker_resilience():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2)

    assert cb.allow_request() is True
    # Record 3 failures to trip breaker
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "CLOSED"
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.allow_request() is False

    # Simulate recovery timeout
    import time
    time.sleep(0.25)
    assert cb.allow_request() is True
    assert cb.state == "HALF-OPEN"

    # Success restores to CLOSED
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0
