"""
Base client for inter-service HTTP communication.
Provides retry logic, HTTP/2 keep-alive, and error handling.
"""
import asyncio
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger("service_client")

try:
    import h2  # noqa: F401
    _HTTP2_SUPPORTED = True
except ImportError:
    _HTTP2_SUPPORTED = False


class ServiceClient:
    """
    Base class for service-to-service HTTP clients.
    
    Features:
    - HTTP/2 persistent connections (when supported)
    - Automatic retry with exponential backoff
    - Request/response logging
    - Correlation ID propagation
    """
    
    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Persistent connection pool
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            http2=_HTTP2_SUPPORTED,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0
            )
        )
    
    def _get_headers(
        self,
        extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build request headers with metadata."""
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": "amc-platform",
            "X-Target-Service": self.service_name,
        }
        
        if extra_headers:
            headers.update(extra_headers)
        
        return headers
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.NetworkError
        )),
        reraise=True
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with automatic retry."""
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        request_headers = self._get_headers(headers)
        
        logger.debug(f"[{self.service_name}] {method} {url}")
        
        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                headers=request_headers
            )
            
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"[{self.service_name}] HTTP {exc.response.status_code}: {exc}"
            )
            raise ServiceError(
                f"{self.service_name} error: {exc.response.text}",
                status_code=exc.response.status_code
            )
        
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning(f"[{self.service_name}] connection error: {exc}")
            raise
        
        except Exception as exc:
            logger.error(f"[{self.service_name}] unexpected error: {exc}")
            raise ServiceError(f"{self.service_name} failed: {str(exc)}")
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """HTTP GET request."""
        return await self._request("GET", endpoint, params=params)
    
    async def post(
        self,
        endpoint: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """HTTP POST request."""
        return await self._request("POST", endpoint, json_data=data)
    
    async def put(
        self,
        endpoint: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """HTTP PUT request."""
        return await self._request("PUT", endpoint, json_data=data)
    
    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """HTTP DELETE request."""
        return await self._request("DELETE", endpoint)
    
    async def health_check(self) -> bool:
        """Check if service is healthy."""
        try:
            response = await self.get("/api/health")
            return response.get("status") in ("healthy", "ok")
        except Exception:
            return False
    
    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()


class ServiceError(Exception):
    """Service communication error."""
    
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
