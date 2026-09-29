"""
HTTP client for standalone Repair Engine service with circuit breaker fallback.
"""
import logging
from typing import Any, Dict, List, Optional
import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

logger = logging.getLogger("app.clients.repair_client")

class RepairServiceClient:
    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url.rstrip("/")
        self.breaker = CircuitBreaker()

    async def get_pending_patches(self) -> List[Dict[str, Any]]:
        if not self.breaker.allow_request():
            logger.warning("Repair service circuit breaker is OPEN")
            raise CircuitBreakerOpenException("Repair service circuit is OPEN")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/patches/pending")
                if res.status_code == 200:
                    self.breaker.record_success()
                    return res.json()
                else:
                    self.breaker.record_failure()
                    return []
        except Exception as exc:
            self.breaker.record_failure()
            logger.warning("Failed to call remote repair service (%s)", exc)
            raise

    async def approve_patch(self, patch_id: str) -> bool:
        if not self.breaker.allow_request():
            raise CircuitBreakerOpenException("Repair service circuit is OPEN")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(f"{self.base_url}/api/patches/{patch_id}/approve")
                if res.status_code == 200:
                    self.breaker.record_success()
                    return True
                else:
                    self.breaker.record_failure()
                    return False
        except Exception as exc:
            self.breaker.record_failure()
            raise
