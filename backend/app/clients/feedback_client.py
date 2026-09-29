"""
HTTP client for standalone Feedback Loop service with circuit breaker fallback.
"""
import logging
from typing import Any, Dict, Optional
import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

logger = logging.getLogger("app.clients.feedback_client")

class FeedbackServiceClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url.rstrip("/")
        self.breaker = CircuitBreaker()

    async def detect_follow_up(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.breaker.allow_request():
            logger.warning("Feedback service circuit breaker is OPEN, falling back to local processing")
            raise CircuitBreakerOpenException("Feedback service circuit is OPEN")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(f"{self.base_url}/api/feedback/follow-up-detection", json=payload)
                if res.status_code == 200:
                    self.breaker.record_success()
                    return res.json()
                else:
                    self.breaker.record_failure()
                    return None
        except Exception as exc:
            self.breaker.record_failure()
            logger.warning("Failed to call remote feedback service (%s)", exc)
            raise
