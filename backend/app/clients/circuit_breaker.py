"""
Lightweight Circuit Breaker implementation for inter-service HTTP resilience.
"""
import time
import logging
from typing import Callable, Any

logger = logging.getLogger("app.clients.circuit_breaker")

# Prometheus metrics (optional - will work if prometheus_client is installed)
try:
    from prometheus_client import Gauge, Counter
    
    circuit_breaker_state = Gauge(
        'circuit_breaker_state',
        'Circuit breaker state (0=CLOSED, 1=HALF-OPEN, 2=OPEN)',
        ['service']
    )
    circuit_breaker_failures = Counter(
        'circuit_breaker_failures_total',
        'Total circuit breaker failures',
        ['service']
    )
    circuit_breaker_successes = Counter(
        'circuit_breaker_successes_total',
        'Total circuit breaker successes',
        ['service']
    )
    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0, service_name: str = "unknown"):
        """Initialize a new instance of CircuitBreaker.

        Args:
            failure_threshold (int): The failure threshold.
            recovery_timeout (float): The recovery timeout.
            service_name (str): The service name for metrics.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.service_name = service_name
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self._update_metrics()

    def _update_metrics(self):
        """Update Prometheus metrics."""
        if METRICS_ENABLED:
            state_map = {"CLOSED": 0, "HALF-OPEN": 1, "OPEN": 2}
            circuit_breaker_state.labels(service=self.service_name).set(state_map[self.state])

    def record_success(self):
        """Record success.
        """
        if METRICS_ENABLED:
            circuit_breaker_successes.labels(service=self.service_name).inc()
        self.failure_count = 0
        self.state = "CLOSED"
        self._update_metrics()

    def record_failure(self):
        """Record failure.
        """
        if METRICS_ENABLED:
            circuit_breaker_failures.labels(service=self.service_name).inc()
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                logger.warning(
                    "[CIRCUIT_OPEN] %s circuit breaker opened (failures=%d)",
                    self.service_name,
                    self.failure_count
                )
            self.state = "OPEN"
            self._update_metrics()

    def allow_request(self) -> bool:
        """Allow request.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF-OPEN"
                logger.info("Circuit breaker transitioning to HALF-OPEN for %s", self.service_name)
                self._update_metrics()
                return True
            return False
        return True  # HALF-OPEN allows a trial request
