"""
Unit and integration tests for Circuit Breaker real-time monitoring and alerting.
"""
import asyncio
import pytest
from app.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpen,
    CircuitBreakerAlert,
    get_circuit_breaker,
    get_all_circuit_breakers,
    clear_circuit_breakers,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes.metrics import router as metrics_router

test_app = FastAPI()
test_app.include_router(metrics_router, prefix="/api")


@pytest.fixture(autouse=True)
def clean_registry():
    clear_circuit_breakers()
    yield
    clear_circuit_breakers()


@pytest.mark.asyncio
async def test_circuit_breaker_emits_alerts_on_trip():
    """Verify that tripping the breaker emits a CRITICAL alert to registered listeners."""
    dispatched_alerts: list[CircuitBreakerAlert] = []

    def alert_listener(alert: CircuitBreakerAlert):
        dispatched_alerts.append(alert)

    cb = CircuitBreaker(
        service_name="payment-service",
        failure_threshold=3,
        recovery_timeout=1.0,
        on_state_change=alert_listener,
    )

    async def faulty_operation():
        raise ConnectionResetError("Connection dropped")

    # Induce 3 failures to trigger the breaker
    for _ in range(3):
        try:
            await cb.call(faulty_operation)
        except ConnectionResetError:
            pass

    assert cb.is_open()
    assert cb.total_trips == 1
    assert len(dispatched_alerts) == 1

    alert = dispatched_alerts[0]
    assert alert.service_name == "payment-service"
    assert alert.event_type == "TRIPPED_OPEN"
    assert alert.severity == "CRITICAL"
    assert alert.previous_state == "closed"
    assert alert.current_state == "open"
    assert alert.failure_count == 3
    assert "failure threshold reached" in alert.message


@pytest.mark.asyncio
async def test_circuit_breaker_emits_alerts_on_recovery():
    """Verify state alerts through OPEN -> HALF_OPEN -> CLOSED cycle."""
    dispatched_alerts: list[CircuitBreakerAlert] = []

    cb = CircuitBreaker(
        service_name="auth-service",
        failure_threshold=2,
        recovery_timeout=0.2,
        success_threshold=1,
    )
    cb.add_listener(lambda a: dispatched_alerts.append(a))

    async def fail_call():
        raise TimeoutError("Auth timeout")

    async def good_call():
        return {"status": "ok"}

    # 1. Trip breaker to OPEN
    for _ in range(2):
        try:
            await cb.call(fail_call)
        except TimeoutError:
            pass

    assert cb.state == CircuitState.OPEN
    assert len(dispatched_alerts) == 1
    assert dispatched_alerts[0].event_type == "TRIPPED_OPEN"

    # Wait for recovery timeout
    await asyncio.sleep(0.25)

    # 2. Probe call in HALF_OPEN -> transitions to CLOSED on success
    res = await cb.call(good_call)
    assert res == {"status": "ok"}
    assert cb.state == CircuitState.CLOSED

    # Should have recorded PROBING_HALF_OPEN and RECOVERED_CLOSED
    event_types = [a.event_type for a in dispatched_alerts]
    assert "PROBING_HALF_OPEN" in event_types
    assert "RECOVERED_CLOSED" in event_types

    recovered_alert = [a for a in dispatched_alerts if a.event_type == "RECOVERED_CLOSED"][0]
    assert recovered_alert.severity == "INFO"
    assert recovered_alert.current_state == "closed"


def test_circuit_breaker_metrics_endpoint():
    """Verify /metrics/circuit-breakers and Prometheus telemetry."""
    cb = CircuitBreaker(
        service_name="repair-engine-monitored",
        failure_threshold=5,
        recovery_timeout=30.0,
    )

    client = TestClient(test_app)

    # 1. Test /metrics/circuit-breakers
    resp = client.get("/api/metrics/circuit-breakers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    names = [b["service_name"] for b in data["circuit_breakers"]]
    assert "repair-engine-monitored" in names

    target_b = [b for b in data["circuit_breakers"] if b["service_name"] == "repair-engine-monitored"][0]
    assert target_b["state"] == "closed"
    assert target_b["state_code"] == 0
    assert target_b["total_trips"] == 0

    # 2. Test /metrics/summary includes circuit_breakers
    summary_resp = client.get("/api/metrics/summary")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert "circuit_breakers" in summary_data
    assert "repair-engine-monitored" in summary_data["circuit_breakers"]

    # 3. Test /metrics/prometheus exports gauges
    prom_resp = client.get("/api/metrics/prometheus")
    assert prom_resp.status_code == 200
    prom_text = prom_resp.text
    assert 'amc_circuit_breaker_state{service="repair-engine-monitored"} 0' in prom_text
    assert 'amc_circuit_breaker_trips_total{service="repair-engine-monitored"} 0' in prom_text
