"""
Circuit breaker pattern for inter-service calls with real-time monitoring and alerting.
Prevents cascading failures when services are down.
"""
import asyncio
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
import inspect
import logging
import os
import time
from typing import Callable, Any, Dict, List, Optional
import uuid

logger = logging.getLogger("circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Service failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass


@dataclass
class CircuitBreakerAlert:
    """Alert record dispatched upon circuit breaker state changes."""
    alert_id: str
    service_name: str
    event_type: str  # "TRIPPED_OPEN", "PROBING_HALF_OPEN", "RECOVERED_CLOSED"
    severity: str    # "CRITICAL", "MEDIUM", "INFO"
    previous_state: str
    current_state: str
    failure_count: int
    timestamp: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Global registry of active circuit breakers across the platform
_circuit_breakers: Dict[str, "CircuitBreaker"] = {}


def get_circuit_breaker(service_name: str) -> Optional["CircuitBreaker"]:
    """Retrieve registered circuit breaker for a service."""
    return _circuit_breakers.get(service_name)


def get_all_circuit_breakers() -> Dict[str, "CircuitBreaker"]:
    """Retrieve all registered circuit breakers."""
    return dict(_circuit_breakers)


def clear_circuit_breakers():
    """Clear registry (primarily for testing)."""
    _circuit_breakers.clear()


class CircuitBreaker:
    """
    Circuit breaker for service calls with alerting and telemetry.
    
    States:
    - CLOSED: Normal operation, allow all calls
    - OPEN: Service failing, reject calls immediately
    - HALF_OPEN: Testing recovery, allow limited calls
    """
    
    def __init__(
        self,
        service_name: str = "service",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
        on_state_change: Optional[Callable[[CircuitBreakerAlert], Any]] = None,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        # Monitoring, telemetry, and alerting
        self.total_calls: int = 0
        self.successful_calls: int = 0
        self.failed_calls: int = 0
        self.total_trips: int = 0
        self.last_state_change: float = time.time()
        self._state_history: List[Dict[str, Any]] = []
        self._alerts: List[CircuitBreakerAlert] = []
        self._listeners: List[Callable[[CircuitBreakerAlert], Any]] = []
        
        if on_state_change:
            self._listeners.append(on_state_change)
        
        # Register in global registry
        _circuit_breakers[service_name] = self

    def add_listener(self, listener: Callable[[CircuitBreakerAlert], Any]):
        """Register a callback listener for circuit breaker state alerts."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def _emit_alert(
        self,
        event_type: str,
        severity: str,
        previous_state: CircuitState,
        new_state: CircuitState,
        message: str
    ):
        """Construct alert and notify all registered listeners."""
        alert = CircuitBreakerAlert(
            alert_id=f"CB_ALT_{uuid.uuid4().hex[:8]}",
            service_name=self.service_name,
            event_type=event_type,
            severity=severity,
            previous_state=previous_state.value,
            current_state=new_state.value,
            failure_count=self.failure_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
            message=message,
        )
        self._alerts.append(alert)
        self._state_history.append({
            "timestamp": alert.timestamp,
            "from_state": previous_state.value,
            "to_state": new_state.value,
            "reason": message,
            "failures": self.failure_count,
        })
        
        # Dispatch to callbacks
        for listener in self._listeners:
            try:
                res = listener(alert)
                if inspect.isawaitable(res):
                    asyncio.create_task(res)
            except Exception as cb_err:
                logger.error("Error executing circuit breaker listener: %s", cb_err)

        # Dispatch to external webhook if configured
        webhook_url = os.getenv("CIRCUIT_BREAKER_ALERT_WEBHOOK_URL")
        if webhook_url:
            self._dispatch_webhook(alert, webhook_url)

    def _dispatch_webhook(self, alert: CircuitBreakerAlert, webhook_url: str):
        """Asynchronously post alert payload to configured webhook URL."""
        async def _post():
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(webhook_url, json=alert.to_dict())
            except Exception as exc:
                logger.warning(
                    f"[{self.service_name}] Failed to post alert to webhook {webhook_url}: {exc}"
                )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_post())
        except RuntimeError:
            pass

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Raises:
            CircuitBreakerOpen: When circuit is open (service unavailable)
        """
        async with self._lock:
            self.total_calls += 1
            # Check if we should transition to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if (self.last_failure_time and 
                    (time.time() - self.last_failure_time) >= self.recovery_timeout):
                    logger.info(
                        f"[{self.service_name}] Circuit OPEN -> HALF_OPEN (recovery timeout probe)"
                    )
                    prev = self.state
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.last_state_change = time.time()
                    self._emit_alert(
                        event_type="PROBING_HALF_OPEN",
                        severity="MEDIUM",
                        previous_state=prev,
                        new_state=self.state,
                        message=f"{self.service_name} circuit breaker is probing recovery in HALF_OPEN state."
                    )
                else:
                    raise CircuitBreakerOpen(
                        f"{self.service_name} circuit breaker is OPEN"
                    )
        
        # Execute function
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                call_res = func(*args, **kwargs)
                if inspect.isawaitable(call_res):
                    result = await call_res
                else:
                    result = call_res
            await self._on_success()
            return result
        
        except Exception as exc:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self.successful_calls += 1
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    logger.info(
                        f"[{self.service_name}] Circuit HALF_OPEN -> CLOSED (recovery successful)"
                    )
                    prev = self.state
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.last_state_change = time.time()
                    self._emit_alert(
                        event_type="RECOVERED_CLOSED",
                        severity="INFO",
                        previous_state=prev,
                        new_state=self.state,
                        message=f"{self.service_name} service recovered successfully. Circuit breaker CLOSED."
                    )
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self.failed_calls += 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"[{self.service_name}] Circuit HALF_OPEN -> OPEN (recovery probe failed)"
                )
                prev = self.state
                self.state = CircuitState.OPEN
                self.success_count = 0
                self.total_trips += 1
                self.last_state_change = time.time()
                self._emit_alert(
                    event_type="TRIPPED_OPEN",
                    severity="CRITICAL",
                    previous_state=prev,
                    new_state=self.state,
                    message=f"{self.service_name} recovery probe failed. Circuit breaker tripped back to OPEN."
                )
            
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    logger.error(
                        f"[{self.service_name}] Circuit CLOSED -> OPEN "
                        f"(threshold reached: {self.failure_count} failures)"
                    )
                    prev = self.state
                    self.state = CircuitState.OPEN
                    self.total_trips += 1
                    self.last_state_change = time.time()
                    self._emit_alert(
                        event_type="TRIPPED_OPEN",
                        severity="CRITICAL",
                        previous_state=prev,
                        new_state=self.state,
                        message=f"{self.service_name} failure threshold reached ({self.failure_count} failures). "
                                f"Circuit breaker tripped to OPEN. Traffic failing over to local fallback."
                    )
    
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self.state == CircuitState.OPEN
    
    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value

    def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent alert history."""
        return [a.to_dict() for a in self._alerts[-limit:]]

    def get_metrics(self) -> Dict[str, Any]:
        """Telemetry snapshot for dashboards and Prometheus monitoring."""
        return {
            "service_name": self.service_name,
            "state": self.state.value,
            "state_code": 0 if self.state == CircuitState.CLOSED else (1 if self.state == CircuitState.HALF_OPEN else 2),
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "total_trips": self.total_trips,
            "consecutive_failures": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout,
            "last_failure_timestamp": (
                datetime.fromtimestamp(self.last_failure_time, tz=timezone.utc).isoformat()
                if self.last_failure_time else None
            ),
            "last_state_change": datetime.fromtimestamp(self.last_state_change, tz=timezone.utc).isoformat(),
            "recent_alerts_count": len(self._alerts),
        }
