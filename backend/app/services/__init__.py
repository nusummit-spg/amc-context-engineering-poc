"""
Inter-service clients and resilience patterns.
"""
from .client_base import ServiceClient, ServiceError
from .feedback_client import FeedbackServiceClient
from .repair_client import RepairServiceClient
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpen,
    CircuitBreakerAlert,
    get_circuit_breaker,
    get_all_circuit_breakers,
    clear_circuit_breakers,
)

__all__ = [
    "ServiceClient",
    "ServiceError",
    "FeedbackServiceClient",
    "RepairServiceClient",
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerOpen",
    "CircuitBreakerAlert",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "clear_circuit_breakers",
]
