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
        """Initialize a new instance of FeedbackServiceClient.

        Args:
            base_url (str): The base url.
        """
        self.base_url = base_url.rstrip("/")
        self.breaker = CircuitBreaker(service_name="feedback_service")

    async def detect_follow_up(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Detect follow up.

        Args:
            payload (Dict[str, Any]): Request or event payload.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing result data or status.
        """
        if not self.breaker.allow_request():
            logger.warning("Feedback service circuit breaker is OPEN, falling back to local processing")
            raise CircuitBreakerOpenException("Feedback service circuit is OPEN")

        try:
            # Get trace ID from context for propagation
            from app.core.logging import request_id_ctx, session_id_ctx
            request_id = request_id_ctx.get("")
            session_id = session_id_ctx.get("")
            
            headers = {
                "Content-Type": "application/json",
            }
            if request_id:
                headers["X-Request-ID"] = request_id
                headers["X-Trace-ID"] = request_id
            if session_id:
                headers["X-Session-ID"] = session_id
            
            # Use explicit timeouts for all phases
            timeout = httpx.Timeout(
                connect=5.0,   # Time to establish connection
                read=10.0,     # Time to read response body
                write=5.0,     # Time to send request body
                pool=5.0,      # Time to acquire connection from pool
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(
                    f"{self.base_url}/api/feedback/follow-up-detection",
                    json=payload,
                    headers=headers
                )
                
                # Validate Content-Type before parsing
                content_type = res.headers.get("content-type", "")
                if res.status_code == 200:
                    if "application/json" not in content_type.lower():
                        logger.error(
                            "Feedback service returned non-JSON response (Content-Type: %s): %s",
                            content_type,
                            res.text[:200]
                        )
                        self.breaker.record_failure()
                        return None
                    
                    try:
                        data = res.json()
                        self.breaker.record_success()
                        return data
                    except Exception as json_exc:
                        logger.error("Feedback service returned invalid JSON: %s", json_exc)
                        self.breaker.record_failure()
                        return None
                else:
                    self.breaker.record_failure()
                    logger.warning("Feedback service HTTP %d: %s", res.status_code, res.text[:200])
                    return None
        except httpx.TimeoutException as timeout_exc:
            self.breaker.record_failure()
            logger.error("Feedback service timeout: %s", timeout_exc)
            raise CircuitBreakerOpenException("Feedback service timeout")
        except Exception as exc:
            self.breaker.record_failure()
            logger.warning("Failed to call remote feedback service (%s)", exc)
            raise
