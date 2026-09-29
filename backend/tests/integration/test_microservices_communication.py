"""
Integration tests for microservices communication and circuit breaker.
"""
import asyncio
import pytest
from app.services.feedback_client import FeedbackServiceClient
from app.services.repair_client import RepairServiceClient
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

FEEDBACK_URL = "http://localhost:8001"
REPAIR_URL = "http://localhost:8002"


@pytest.mark.asyncio
async def test_feedback_service_health():
    """Test feedback service health check."""
    client = FeedbackServiceClient(FEEDBACK_URL)
    
    is_healthy = await client.health_check()
    # May be False if local container is not actively running, but must not crash
    assert isinstance(is_healthy, bool)
    
    await client.close()


@pytest.mark.asyncio
async def test_repair_service_health():
    """Test repair service health check."""
    client = RepairServiceClient(REPAIR_URL)
    
    is_healthy = await client.health_check()
    assert isinstance(is_healthy, bool)
    
    await client.close()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures():
    """Test circuit breaker opens after threshold failures."""
    breaker = CircuitBreaker(
        service_name="test-service",
        failure_threshold=3,
        recovery_timeout=5.0
    )
    
    async def failing_call():
        raise Exception("Service unavailable")
    
    # Trigger failures
    for _ in range(5):
        try:
            await breaker.call(failing_call)
        except Exception:
            pass
    
    # Circuit should be open
    assert breaker.is_open()
    assert breaker.get_state() == "open"
    
    # Should reject further calls immediately
    with pytest.raises(CircuitBreakerOpen):
        await breaker.call(failing_call)


@pytest.mark.asyncio
async def test_circuit_breaker_closes_on_recovery():
    """Test circuit breaker closes after successful recovery."""
    breaker = CircuitBreaker(
        service_name="test-service",
        failure_threshold=3,
        recovery_timeout=0.3,
        success_threshold=2
    )
    
    async def failing_call():
        raise Exception("Service unavailable")
    
    async def successful_call():
        return "success"
    
    # Open circuit
    for _ in range(5):
        try:
            await breaker.call(failing_call)
        except Exception:
            pass
    
    assert breaker.is_open()
    
    # Wait for recovery timeout
    await asyncio.sleep(0.4)
    
    # Should allow trial call and transition to HALF_OPEN
    result1 = await breaker.call(successful_call)
    assert result1 == "success"
    
    result2 = await breaker.call(successful_call)
    assert result2 == "success"
    
    # Circuit should be closed again
    assert not breaker.is_open()
    assert breaker.get_state() == "closed"
