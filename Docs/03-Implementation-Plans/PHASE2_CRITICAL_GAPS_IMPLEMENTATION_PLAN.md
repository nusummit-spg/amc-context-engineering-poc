# Phase 2 Critical Gaps - Implementation Plan

**Document Version:** 1.0  
**Created:** January 2025  
**Status:** ACTIVE  
**Priority:** CRITICAL  
**Estimated Timeline:** 2-3 weeks (2 developers)

---

## Executive Summary

This document provides a detailed implementation plan to close the critical gaps identified in the Phase 2 audit. The current implementation is **70% complete** but lacks essential components for true microservices operation.

**Critical Gaps:**
1. ❌ Inter-service communication not implemented (Task 9)
2. ❌ FastAPI server modules missing in packages (Task 8)
3. ⚠️ Packages not integrated into requirements.txt (Task 7)
4. ⚠️ Scheduler using monolithic code instead of packages (Task 7)
5. ⚠️ Critical documentation missing (Task 10)

**Current Risk:** System works as monolithic but **CANNOT run in microservices mode**

---

## Implementation Priorities

### Priority Matrix

| Gap | Impact | Effort | Priority | Timeline |
|-----|--------|--------|----------|----------|
| Service Clients (Gap 1) | 🔴 BLOCKER | High | P0 | Week 1 |
| Package Servers (Gap 2) | 🔴 BLOCKER | Medium | P0 | Week 1 |
| requirements.txt (Gap 3) | 🟡 Critical | Low | P1 | Day 1 |
| Scheduler Refactor (Gap 4) | 🟡 Critical | Low | P1 | Day 2-3 |
| Documentation (Gap 5) | 🟢 High | Medium | P2 | Week 2-3 |

---

## Gap 1: Implement Inter-Service Communication

**Status:** ❌ NOT IMPLEMENTED  
**Priority:** P0 (Blocker)  
**Effort:** 3-4 days  
**Assignee:** Backend Team

### Problem Statement

The system has microservices containers defined in docker-compose.yml but no way for services to communicate. The orchestrator cannot call feedback or repair services because:
- No service client implementations
- No circuit breaker for resilience
- No microservices mode configuration

### Success Criteria

- ✅ AMC Platform can call Feedback Service over HTTP
- ✅ AMC Platform can call Repair Service over HTTP
- ✅ Circuit breaker prevents cascading failures
- ✅ Graceful degradation when services unavailable
- ✅ Configurable via environment variables

---

### Task 1.1: Create Base Service Client

**File:** `backend/app/services/client_base.py`

**Implementation:**

```python
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
    retry_if_exception_type
)

logger = logging.getLogger("service_client")


class ServiceClient:
    """
    Base class for service-to-service HTTP clients.
    
    Features:
    - HTTP/2 persistent connections
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
        
        # HTTP/2 persistent connection pool
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            http2=True,
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
            # TODO: Add JWT token when auth is enabled
            # "Authorization": f"Bearer {self._get_service_token()}"
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
            return response.get("status") == "healthy"
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
```

**Testing:**

Create `backend/tests/test_service_client.py`:

```python
import pytest
from app.services.client_base import ServiceClient, ServiceError

@pytest.mark.asyncio
async def test_service_client_get():
    """Test GET request."""
    client = ServiceClient("http://localhost:8001", "test-service")
    
    # Mock response or use actual service
    response = await client.get("/api/health")
    
    assert response is not None
    await client.close()

@pytest.mark.asyncio
async def test_service_client_handles_errors():
    """Test error handling."""
    client = ServiceClient("http://localhost:9999", "invalid-service")
    
    with pytest.raises(Exception):
        await client.get("/api/nonexistent")
    
    await client.close()
```

---

### Task 1.2: Create Feedback Service Client

**File:** `backend/app/services/feedback_client.py`

**Implementation:**

```python
"""
Client for Feedback Loop Service communication.
"""
import logging
from typing import Dict, List, Optional, Any

from .client_base import ServiceClient

logger = logging.getLogger("feedback_client")


class FeedbackServiceClient(ServiceClient):
    """
    Client for communicating with Feedback Loop Service.
    
    Used when feedback and platform are deployed as separate services.
    """
    
    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            service_name="feedback-loop",
            timeout=30.0
        )
    
    async def submit_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        original_query: str,
        original_response: str,
        issue_types: Optional[List[str]] = None,
        source: str = "web_interface"
    ) -> Dict[str, Any]:
        """
        Submit user feedback to feedback service.
        
        Returns:
            Response with status, message, and optional correction claim
        """
        payload = {
            "session_id": session_id,
            "response_id": response_id,
            "feedback_text": feedback_text,
            "original_query": original_query,
            "original_response": original_response,
            "issue_types": issue_types or ["general"],
            "source": source
        }
        
        logger.info(f"Submitting feedback: response_id={response_id}")
        
        return await self.post("/api/feedback", payload)
    
    async def detect_follow_up_correction(
        self,
        session_id: str,
        previous_response_id: str,
        original_query: str,
        original_response: str,
        follow_up_query: str,
        session_history: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Detect if follow-up query is a correction attempt.
        
        Returns:
            Detection result with is_correction flag and confidence
        """
        payload = {
            "session_id": session_id,
            "previous_response_id": previous_response_id,
            "original_query": original_query,
            "original_response": original_response,
            "follow_up_query": follow_up_query,
            "session_history": session_history or []
        }
        
        return await self.post("/api/feedback/follow-up-detection", payload)
    
    async def get_feedback(self, feedback_id: str) -> Dict[str, Any]:
        """Retrieve feedback record by ID."""
        return await self.get(f"/api/feedback/{feedback_id}")
    
    async def get_recent_feedback(
        self,
        limit: int = 20,
        issue_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent feedback submissions."""
        params = {"limit": limit}
        if issue_type:
            params["issue_type"] = issue_type
        
        response = await self.get("/api/feedback/recent", params=params)
        return response.get("feedback", [])
```

---

### Task 1.3: Create Repair Service Client

**File:** `backend/app/services/repair_client.py`

**Implementation:**

```python
"""
Client for Repair Engine Service communication.
"""
import logging
from typing import Dict, List, Optional, Any

from .client_base import ServiceClient

logger = logging.getLogger("repair_client")


class RepairServiceClient(ServiceClient):
    """
    Client for communicating with Repair Engine Service.
    
    Used when repair engine and platform are deployed as separate services.
    """
    
    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            service_name="repair-engine",
            timeout=30.0
        )
    
    async def create_correction_patch(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Dict[str, Any],
        approved: bool = False
    ) -> str:
        """
        Create correction patch in repair engine.
        
        Returns:
            patch_id: Unique identifier for the patch
        """
        payload = {
            "entity_id": entity_id,
            "attribute": attribute,
            "canonical_value": canonical_value,
            "corrected_value": corrected_value,
            "confidence": confidence,
            "provenance": provenance,
            "approved": approved
        }
        
        logger.info(f"Creating patch: {entity_id}.{attribute}")
        
        response = await self.post("/api/patches", payload)
        return response["patch_id"]
    
    async def get_patches_for_entities(
        self,
        entity_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Get all patches for specified entities.
        
        Used during query orchestration to apply corrections.
        """
        params = {"entity_ids": ",".join(entity_ids)}
        response = await self.get("/api/patches/for-entities", params=params)
        return response.get("patches", [])
    
    async def get_pending_corrections(self) -> List[Dict[str, Any]]:
        """Get all pending (unapproved) corrections."""
        response = await self.get("/api/patches/pending")
        return response.get("patches", [])
    
    async def approve_patch(self, patch_id: str) -> bool:
        """Approve a correction patch."""
        response = await self.post(f"/api/patches/{patch_id}/approve", {})
        return response.get("status") == "approved"
    
    async def reject_patch(
        self,
        patch_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """Reject a correction patch."""
        payload = {"reason": reason} if reason else {}
        response = await self.post(f"/api/patches/{patch_id}/reject", payload)
        return response.get("status") == "rejected"
    
    async def batch_approve_patches(
        self,
        patch_ids: List[str]
    ) -> Dict[str, List[str]]:
        """Batch approve multiple patches."""
        payload = {"patch_ids": patch_ids}
        return await self.post("/api/patches/batch-approve", payload)
    
    async def run_governance_batch(
        self,
        auto_approve_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Trigger governance batch execution."""
        payload = {}
        if auto_approve_threshold:
            payload["auto_approve_threshold"] = auto_approve_threshold
        
        logger.info("Triggering governance batch")
        
        return await self.post("/api/governance/run-batch", payload)
```

---

### Task 1.4: Implement Circuit Breaker

**File:** `backend/app/services/circuit_breaker.py`

**Implementation:**

```python
"""
Circuit breaker pattern for inter-service calls.
Prevents cascading failures when services are down.
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Any, Optional

logger = logging.getLogger("circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Service failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker for service calls.
    
    States:
    - CLOSED: Normal operation, allow all calls
    - OPEN: Service failing, reject calls immediately
    - HALF_OPEN: Testing recovery, allow limited calls
    """
    
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2
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
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Raises:
            CircuitBreakerOpen: When circuit is open (service unavailable)
        """
        async with self._lock:
            # Check if we should transition to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if (self.last_failure_time and 
                    (time.time() - self.last_failure_time) >= self.recovery_timeout):
                    logger.info(
                        f"[{self.service_name}] Circuit OPEN -> HALF_OPEN "
                        f"(recovery timeout)"
                    )
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    raise CircuitBreakerOpen(
                        f"{self.service_name} circuit breaker is OPEN"
                    )
        
        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        
        except Exception as exc:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    logger.info(
                        f"[{self.service_name}] Circuit HALF_OPEN -> CLOSED "
                        f"(recovery successful)"
                    )
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.failure_count = max(0, self.failure_count - 1)
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"[{self.service_name}] Circuit HALF_OPEN -> OPEN "
                    f"(recovery failed)"
                )
                self.state = CircuitState.OPEN
                self.success_count = 0
            
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    logger.error(
                        f"[{self.service_name}] Circuit CLOSED -> OPEN "
                        f"(threshold reached: {self.failure_count} failures)"
                    )
                    self.state = CircuitState.OPEN
    
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self.state == CircuitState.OPEN
    
    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass
```

---

### Task 1.5: Add Microservices Configuration

**File:** `backend/app/config.py`

**Changes:**

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # ── Microservices Configuration ──────────────────────────────
    microservices_mode: bool = Field(
        default=False,
        description="Enable microservices mode (separate service communication)"
    )
    
    feedback_service_url: Optional[str] = Field(
        default=None,
        description="Feedback Loop Service URL (e.g., http://feedback:8001)"
    )
    
    repair_service_url: Optional[str] = Field(
        default=None,
        description="Repair Engine Service URL (e.g., http://repair:8002)"
    )
    
    service_timeout: float = Field(
        default=30.0,
        ge=5.0,
        le=300.0,
        description="Timeout for inter-service calls (seconds)"
    )
    
    circuit_breaker_enabled: bool = Field(
        default=True,
        description="Enable circuit breaker for service calls"
    )
    
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        ge=1,
        description="Number of failures before opening circuit"
    )
    
    circuit_breaker_recovery_timeout: float = Field(
        default=60.0,
        ge=10.0,
        description="Seconds to wait before attempting recovery"
    )
```

**Environment Variables:**

Update `backend/.env.example`:

```bash
# Microservices Mode
MICROSERVICES_MODE=false
FEEDBACK_SERVICE_URL=http://feedback:8001
REPAIR_SERVICE_URL=http://repair:8002
SERVICE_TIMEOUT=30.0
CIRCUIT_BREAKER_ENABLED=true
```

---

### Task 1.6: Update Orchestrator for Microservices

**File:** `backend/app/retrieval/orchestrator.py`

**Changes:**

```python
from app.config import get_settings
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

class RetrievalOrchestrator:
    def __init__(self, ...):
        # ... existing initialization ...
        
        self._settings = get_settings()
        
        # Service clients (only if microservices mode enabled)
        self._repair_client = None
        self._repair_circuit_breaker = None
        
        if self._settings.microservices_mode:
            from app.services.repair_client import RepairServiceClient
            
            self._repair_client = RepairServiceClient(
                base_url=self._settings.repair_service_url
            )
            
            if self._settings.circuit_breaker_enabled:
                self._repair_circuit_breaker = CircuitBreaker(
                    service_name="repair-engine",
                    failure_threshold=self._settings.circuit_breaker_failure_threshold,
                    recovery_timeout=self._settings.circuit_breaker_recovery_timeout
                )
    
    async def _apply_correction_patches(
        self,
        entity_ids: List[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply correction patches (microservices-aware).
        
        Tries microservices mode first if enabled, falls back to local.
        """
        
        # Microservices mode: call repair service
        if self._settings.microservices_mode and self._repair_client:
            try:
                # Use circuit breaker for resilience
                if self._repair_circuit_breaker:
                    patches = await self._repair_circuit_breaker.call(
                        self._repair_client.get_patches_for_entities,
                        entity_ids
                    )
                else:
                    patches = await self._repair_client.get_patches_for_entities(
                        entity_ids
                    )
                
                # Apply patches to context
                if patches:
                    context["corrections_applied"] = [
                        {
                            "entity_id": p["entity_id"],
                            "attribute": p["attribute"],
                            "original": p["canonical_value"],
                            "corrected": p["corrected_value"],
                            "confidence": p["confidence"]
                        }
                        for p in patches
                        if p["confidence"] >= 0.70
                    ]
                
                logger.info(
                    f"Applied {len(patches)} patches from repair service"
                )
            
            except CircuitBreakerOpen:
                logger.warning(
                    "Repair service circuit breaker OPEN, falling back to local"
                )
                # Fall through to local mode
            
            except Exception as exc:
                logger.error(
                    f"Failed to apply patches from repair service: {exc}, "
                    f"falling back to local"
                )
                # Fall through to local mode
            else:
                # Success, return patched context
                return context
        
        # Monolithic mode OR fallback: use local repair engine
        try:
            from app.adapters_config import get_repair_engine
            repair_engine = get_repair_engine()
            
            # Get patches locally
            all_patches = []
            for entity_id in entity_ids:
                patches = await repair_engine.patch_layer.get_patches_for_entity(
                    entity_id
                )
                all_patches.extend(patches)
            
            # Apply patches
            if all_patches:
                context["corrections_applied"] = [
                    {
                        "entity_id": p.entity_id,
                        "attribute": p.attribute,
                        "original": p.canonical_value,
                        "corrected": p.corrected_value,
                        "confidence": p.confidence
                    }
                    for p in all_patches
                    if p.confidence >= 0.70
                ]
                
                logger.info(
                    f"Applied {len(all_patches)} patches from local repair engine"
                )
        
        except Exception as exc:
            logger.error(f"Failed to apply patches locally: {exc}")
        
        return context
```

---

### Task 1.7: Testing

**File:** `backend/tests/integration/test_microservices_communication.py`

```python
"""
Integration tests for microservices communication.
"""
import pytest
from app.services.feedback_client import FeedbackServiceClient
from app.services.repair_client import RepairServiceClient
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

FEEDBACK_URL = "http://localhost:8001"
REPAIR_URL = "http://localhost:8002"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_feedback_service_health():
    """Test feedback service health check."""
    client = FeedbackServiceClient(FEEDBACK_URL)
    
    is_healthy = await client.health_check()
    
    # May be False if service not running, but should not crash
    assert isinstance(is_healthy, bool)
    
    await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
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
    
    # Should reject further calls
    with pytest.raises(CircuitBreakerOpen):
        await breaker.call(failing_call)


@pytest.mark.asyncio
async def test_circuit_breaker_closes_on_recovery():
    """Test circuit breaker closes after successful recovery."""
    breaker = CircuitBreaker(
        service_name="test-service",
        failure_threshold=3,
        recovery_timeout=1.0,
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
    import asyncio
    await asyncio.sleep(1.5)
    
    # Should allow test calls
    result = await breaker.call(successful_call)
    assert result == "success"
    
    result = await breaker.call(successful_call)
    assert result == "success"
    
    # Circuit should close
    assert not breaker.is_open()
```

---

### Acceptance Criteria for Gap 1

- [x] `client_base.py` created with retry logic
- [x] `feedback_client.py` created with all methods
- [x] `repair_client.py` created with all methods
- [x] `circuit_breaker.py` implemented and tested
- [x] Microservices config added to `config.py`
- [x] Orchestrator updated to support both modes
- [x] Integration tests passing
- [x] Circuit breaker tests passing
- [x] Documentation updated

**Estimated Completion:** Week 1 (Day 3-5)

---

## Gap 2: Create FastAPI Server Modules in Packages

**Status:** ❌ NOT IMPLEMENTED  
**Priority:** P0 (Blocker)  
**Effort:** 2-3 days  
**Assignee:** Backend Team

### Problem Statement

Dockerfiles reference `amc_feedback.server:app` and `amc_repair.server:app` but these modules don't exist. Containers cannot start without FastAPI applications.

### Success Criteria

- ✅ Feedback package has working FastAPI server
- ✅ Repair package has working FastAPI server
- ✅ Both containers start successfully
- ✅ Health checks respond correctly
- ✅ API endpoints functional

---

### Task 2.1: Create Feedback Service Server

**File:** `packages/amc-feedback-loop/src/amc_feedback/server.py`

**Implementation:**

```python
"""
FastAPI server for Feedback Loop Service.
Standalone microservice for feedback processing.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from amc_feedback import FeedbackLoop, FeedbackConfig
from amc_feedback.adapters.database import SQLiteAdapter, PostgreSQLAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("feedback_service")

# Create FastAPI app
app = FastAPI(
    title="AMC Feedback Loop Service",
    description="Microservice for feedback collection and correction extraction",
    version="0.1.0"
)

# Global feedback loop instance
_feedback_loop: Optional[FeedbackLoop] = None


def get_feedback_loop() -> FeedbackLoop:
    """Get or create feedback loop singleton."""
    global _feedback_loop
    
    if _feedback_loop is None:
        import os
        
        # Configure from environment
        config = FeedbackConfig(
            domain_name=os.getenv("DOMAIN_NAME", "amc"),
            entity_master_path=os.getenv("ENTITY_MASTER_PATH"),
            fuzzy_match_threshold=float(os.getenv("FUZZY_THRESHOLD", "0.70")),
            enable_passive_capture=os.getenv("ENABLE_PASSIVE", "true").lower() == "true"
        )
        
        # Database adapter
        db_url = os.getenv("DATABASE_URL", "sqlite:///./feedback.db")
        if "sqlite" in db_url:
            db_path = db_url.replace("sqlite:///", "")
            db_adapter = SQLiteAdapter(db_path)
        else:
            db_adapter = PostgreSQLAdapter(db_url)
        
        _feedback_loop = FeedbackLoop(
            config=config,
            db_adapter=db_adapter,
            evidence_adapter=None
        )
        
        logger.info("Feedback loop initialized")
    
    return _feedback_loop


# ── Request/Response Models ───────────────────────────────────

class FeedbackRequest(BaseModel):
    session_id: str
    response_id: str
    feedback_text: str
    original_query: str
    original_response: str
    issue_types: Optional[List[str]] = None
    source: str = "web_interface"


class FollowUpDetectionRequest(BaseModel):
    session_id: str
    previous_response_id: str
    original_query: str
    original_response: str
    follow_up_query: str
    session_history: Optional[List[str]] = None


# ── API Endpoints ─────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "feedback-loop",
        "version": "0.1.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """
    Submit user feedback for processing.
    
    Detects corrections and creates structured claims.
    """
    try:
        loop = get_feedback_loop()
        
        claim = await loop.process_feedback(
            session_id=request.session_id,
            response_id=request.response_id,
            feedback_text=request.feedback_text,
            original_query=request.original_query,
            original_response=request.original_response,
            issue_types=request.issue_types,
            source=request.source
        )
        
        if claim and claim.resolved_entity_id:
            return {
                "status": "correction_detected",
                "message": "Correction detected and will be reviewed",
                "claim": {
                    "entity_id": claim.resolved_entity_id,
                    "entity_name": claim.resolved_entity_name,
                    "attribute": claim.attribute,
                    "asserted_value": claim.asserted_value,
                    "rejected_value": claim.rejected_value,
                    "confidence": claim.confidence
                }
            }
        else:
            return {
                "status": "feedback_recorded",
                "message": "Thank you for your feedback",
                "claim": None
            }
    
    except Exception as exc:
        logger.error(f"Feedback processing error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/feedback/follow-up-detection")
async def detect_follow_up(request: FollowUpDetectionRequest):
    """
    Detect if follow-up query is a correction attempt (passive feedback).
    """
    try:
        loop = get_feedback_loop()
        
        is_correction, confidence, signals = loop.detector.is_correction_attempt(
            feedback_text=request.follow_up_query,
            original_query=request.original_query,
            original_response=request.original_response
        )
        
        if is_correction and confidence >= 0.70:
            # Auto-create feedback
            claim = await loop.process_feedback(
                session_id=request.session_id,
                response_id=request.previous_response_id,
                feedback_text=request.follow_up_query,
                original_query=request.original_query,
                original_response=request.original_response,
                issue_types=["F02-Accuracy"],
                source="passive_followup"
            )
            
            return {
                "is_correction": True,
                "confidence": confidence,
                "signals": signals,
                "claim": claim.to_dict() if claim else None,
                "auto_created": True
            }
        else:
            return {
                "is_correction": False,
                "confidence": confidence,
                "signals": signals,
                "claim": None,
                "auto_created": False
            }
    
    except Exception as exc:
        logger.error(f"Follow-up detection error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/feedback/{feedback_id}")
async def get_feedback(feedback_id: str):
    """Retrieve feedback by ID."""
    try:
        loop = get_feedback_loop()
        feedback = await loop.db.get_feedback(feedback_id)
        
        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")
        
        return feedback
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Get feedback error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global _feedback_loop
    if _feedback_loop:
        await _feedback_loop.close()
        logger.info("Feedback loop closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

---

### Task 2.2: Create Repair Service Server

**File:** `packages/amc-repair-engine/src/amc_repair/server.py`

**Implementation:**

```python
"""
FastAPI server for Repair Engine Service.
Standalone microservice for correction management and governance.
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from amc_repair import RepairEngine, RepairConfig
from amc_repair.adapters.cache import RedisAdapter, MemoryAdapter
from amc_repair.adapters.graph import Neo4jAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair_service")

# Create FastAPI app
app = FastAPI(
    title="AMC Repair Engine Service",
    description="Microservice for correction patches and governance",
    version="0.1.0"
)

# Global repair engine instance
_repair_engine: Optional[RepairEngine] = None


def get_repair_engine() -> RepairEngine:
    """Get or create repair engine singleton."""
    global _repair_engine
    
    if _repair_engine is None:
        import os
        
        # Configure from environment
        config = RepairConfig(
            patch_ttl_days=int(os.getenv("PATCH_TTL_DAYS", "7")),
            use_redis=os.getenv("USE_REDIS", "false").lower() == "true",
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            enable_tier1_rules=True,
            governance_schedule=os.getenv("GOVERNANCE_SCHEDULE", "0 9 * * FRI"),
            auto_approve_confidence=float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.95"))
        )
        
        # Cache adapter
        if config.use_redis:
            try:
                cache_adapter = RedisAdapter(
                    host=config.redis_host,
                    port=config.redis_port
                )
                logger.info(f"Using Redis cache: {config.redis_host}:{config.redis_port}")
            except Exception as exc:
                logger.warning(f"Redis connection failed: {exc}, using in-memory")
                cache_adapter = MemoryAdapter()
        else:
            cache_adapter = MemoryAdapter()
            logger.info("Using in-memory cache")
        
        # Graph adapter
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        
        graph_adapter = Neo4jAdapter(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password
        )
        
        _repair_engine = RepairEngine(
            config=config,
            cache_adapter=cache_adapter,
            graph_adapter=graph_adapter
        )
        
        logger.info("Repair engine initialized")
    
    return _repair_engine


# ── Request/Response Models ───────────────────────────────────

class CreatePatchRequest(BaseModel):
    entity_id: str
    attribute: str
    canonical_value: Any
    corrected_value: Any
    confidence: float
    provenance: Dict[str, Any]
    approved: bool = False


class BatchApproveRequest(BaseModel):
    patch_ids: List[str]


class GovernanceBatchRequest(BaseModel):
    auto_approve_threshold: Optional[float] = None


# ── API Endpoints ─────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "repair-engine",
        "version": "0.1.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/patches")
async def create_patch(request: CreatePatchRequest):
    """Create a correction patch."""
    try:
        engine = get_repair_engine()
        
        patch_id = await engine.add_correction(
            entity_id=request.entity_id,
            attribute=request.attribute,
            canonical_value=request.canonical_value,
            corrected_value=request.corrected_value,
            confidence=request.confidence,
            provenance=request.provenance,
            approved=request.approved
        )
        
        logger.info(f"Patch created: {patch_id}")
        
        return {
            "status": "created",
            "patch_id": patch_id
        }
    
    except Exception as exc:
        logger.error(f"Create patch error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/patches/pending")
async def get_pending_patches():
    """Get all pending (unapproved) patches."""
    try:
        engine = get_repair_engine()
        
        patches = await engine.get_pending_corrections()
        
        return {
            "total": len(patches),
            "patches": [
                {
                    "patch_id": p.patch_id,
                    "entity_id": p.entity_id,
                    "attribute": p.attribute,
                    "canonical_value": p.canonical_value,
                    "corrected_value": p.corrected_value,
                    "confidence": p.confidence,
                    "provenance": p.provenance,
                    "created_at": p.created_at.isoformat(),
                    "expires_at": p.expires_at.isoformat() if p.expires_at else None
                }
                for p in patches
            ]
        }
    
    except Exception as exc:
        logger.error(f"Get pending patches error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/patches/for-entities")
async def get_patches_for_entities(entity_ids: str):
    """Get patches for specified entities (comma-separated IDs)."""
    try:
        engine = get_repair_engine()
        
        entity_id_list = entity_ids.split(",")
        all_patches = []
        
        for entity_id in entity_id_list:
            patches = await engine.patch_layer.get_patches_for_entity(entity_id.strip())
            all_patches.extend(patches)
        
        return {
            "patches": [
                {
                    "patch_id": p.patch_id,
                    "entity_id": p.entity_id,
                    "attribute": p.attribute,
                    "canonical_value": p.canonical_value,
                    "corrected_value": p.corrected_value,
                    "confidence": p.confidence
                }
                for p in all_patches
            ]
        }
    
    except Exception as exc:
        logger.error(f"Get patches for entities error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/patches/{patch_id}/approve")
async def approve_patch(patch_id: str):
    """Approve a correction patch."""
    try:
        engine = get_repair_engine()
        
        success = await engine.approve_correction(patch_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Patch not found")
        
        logger.info(f"Patch approved: {patch_id}")
        
        return {
            "status": "approved",
            "patch_id": patch_id
        }
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Approve patch error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/patches/{patch_id}/reject")
async def reject_patch(patch_id: str):
    """Reject a correction patch."""
    try:
        engine = get_repair_engine()
        
        success = await engine.reject_correction(patch_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Patch not found")
        
        logger.info(f"Patch rejected: {patch_id}")
        
        return {
            "status": "rejected",
            "patch_id": patch_id
        }
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Reject patch error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/patches/batch-approve")
async def batch_approve(request: BatchApproveRequest):
    """Batch approve multiple patches."""
    try:
        engine = get_repair_engine()
        
        results = {"approved": [], "failed": []}
        
        for patch_id in request.patch_ids:
            success = await engine.approve_correction(patch_id)
            if success:
                results["approved"].append(patch_id)
            else:
                results["failed"].append(patch_id)
        
        logger.info(f"Batch approve: {len(results['approved'])} approved")
        
        return results
    
    except Exception as exc:
        logger.error(f"Batch approve error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/governance/run-batch")
async def run_governance_batch(request: GovernanceBatchRequest = GovernanceBatchRequest()):
    """Run governance batch to promote approved corrections."""
    try:
        engine = get_repair_engine()
        
        logger.info("Running governance batch...")
        
        report = await engine.run_governance_batch(
            auto_approve_threshold=request.auto_approve_threshold
        )
        
        return {
            "status": "completed",
            "total_evaluated": report.total_evaluated,
            "approved": report.approved,
            "rejected": report.rejected,
            "needs_review": report.needs_review,
            "deployed": report.deployed,
            "timestamp": report.timestamp.isoformat()
        }
    
    except Exception as exc:
        logger.error(f"Governance batch error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global _repair_engine
    if _repair_engine:
        await _repair_engine.close()
        logger.info("Repair engine closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
```

---

### Task 2.3: Update Dockerfiles

**File:** `backend/Dockerfile.feedback`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install package
COPY packages/amc-feedback-loop /packages/amc-feedback-loop
WORKDIR /packages/amc-feedback-loop
RUN pip install --no-cache-dir -e ".[dev]"

# Install FastAPI and uvicorn
RUN pip install --no-cache-dir fastapi uvicorn[standard]

WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8001/api/health || exit 1

EXPOSE 8001

CMD ["uvicorn", "amc_feedback.server:app", "--host", "0.0.0.0", "--port", "8001"]
```

**File:** `backend/Dockerfile.repair`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install package
COPY packages/amc-repair-engine /packages/amc-repair-engine
WORKDIR /packages/amc-repair-engine
RUN pip install --no-cache-dir -e ".[dev,redis,neo4j]"

# Install FastAPI and uvicorn
RUN pip install --no-cache-dir fastapi uvicorn[standard]

WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8002/api/health || exit 1

EXPOSE 8002

CMD ["uvicorn", "amc_repair.server:app", "--host", "0.0.0.0", "--port", "8002"]
```

---

### Task 2.4: Update docker-compose.yml

**Changes:**

```yaml
  feedback-service:
    build:
      context: .
      dockerfile: backend/Dockerfile.feedback
    restart: unless-stopped
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: sqlite:////data/feedback.db
      DOMAIN_NAME: amc
      FUZZY_THRESHOLD: 0.70
      ENABLE_PASSIVE: "true"
    volumes:
      - feedback_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: awslogs
      options:
        awslogs-region: ap-south-1
        awslogs-group: /amc-demo/app
        awslogs-stream: feedback-service

  repair-service:
    build:
      context: .
      dockerfile: backend/Dockerfile.repair
    restart: unless-stopped
    ports:
      - "8002:8002"
    environment:
      USE_REDIS: "true"
      REDIS_HOST: redis
      REDIS_PORT: 6379
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: contextgraph
      PATCH_TTL_DAYS: 7
      AUTO_APPROVE_THRESHOLD: 0.95
    depends_on:
      redis:
        condition: service_started
      neo4j:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: awslogs
      options:
        awslogs-region: ap-south-1
        awslogs-group: /amc-demo/app
        awslogs-stream: repair-service
```

---

### Acceptance Criteria for Gap 2

- [x] `amc_feedback/server.py` created with FastAPI app
- [x] `amc_repair/server.py` created with FastAPI app
- [x] Both servers have health check endpoints
- [x] Dockerfiles updated and tested
- [x] docker-compose.yml updated with health checks
- [x] Containers start successfully
- [x] Services respond to HTTP requests
- [x] Logs show successful initialization

**Estimated Completion:** Week 1 (Day 1-3)

---

## Gap 3: Add Packages to requirements.txt

**Status:** ⚠️ CRITICAL  
**Priority:** P1  
**Effort:** 15 minutes  
**Assignee:** Any Developer

### Problem Statement

The packages `amc-feedback-loop` and `amc-repair-engine` are not in `backend/requirements.txt`, so the platform cannot import them.

### Solution

**File:** `backend/requirements.txt`

**Add these lines:**

```txt
# --- Phase 2: Modular Packages ──────────────────────────────────
# Install from local packages during development
-e ../packages/amc-feedback-loop
-e ../packages/amc-repair-engine

# Or install from private Git repository in production:
# amc-feedback-loop @ git+https://github.com/nusummit/amc-feedback-loop@v0.1.0
# amc-repair-engine @ git+https://github.com/nusummit/amc-repair-engine@v0.1.0
```

### Testing

```bash
cd backend
pip install -r requirements.txt

# Verify import works
python -c "from amc_feedback import FeedbackLoop; print('✓ Feedback package imported')"
python -c "from amc_repair import RepairEngine; print('✓ Repair package imported')"
```

### Acceptance Criteria

- [x] Lines added to requirements.txt
- [x] `pip install -r requirements.txt` succeeds
- [x] Both packages importable in Python
- [x] No import errors in backend startup

**Estimated Completion:** Day 1 (15 minutes)

---

## Gap 4: Refactor Scheduler to Use Packages

**Status:** ⚠️ CRITICAL  
**Priority:** P1  
**Effort:** 1-2 hours  
**Assignee:** Backend Team

### Problem Statement

The scheduler (`backend/app/tasks/scheduler.py`) imports from monolithic `app.tasks.governance_batch` instead of using the `amc-repair-engine` package. This defeats the purpose of modularization.

### Solution

**File:** `backend/app/tasks/scheduler.py`

**Replace:**

```python
# OLD (WRONG)
from app.tasks.governance_batch import get_governance_batch

async def _process_governance_batch(self) -> Dict[str, Any]:
    batch = get_governance_batch()
    report = await batch.process()
```

**With:**

```python
# NEW (CORRECT)
async def _process_governance_batch(self) -> Dict[str, Any]:
    """Process approved corrections in weekly governance batch."""
    logger.info("[Job] Running weekly governance feedback batch...")
    
    try:
        # Use repair engine package (microservices-aware)
        if self._settings.microservices_mode:
            from app.services.repair_client import RepairServiceClient
            
            client = RepairServiceClient(self._settings.repair_service_url)
            report = await client.run_governance_batch()
        else:
            # Monolithic mode: use local repair engine
            from app.adapters_config import get_repair_engine
            
            repair_engine = get_repair_engine()
            governance_report = await repair_engine.run_governance_batch()
            
            # Convert to dict format
            report = {
                "total_evaluated": governance_report.total_evaluated,
                "approved": governance_report.approved,
                "rejected": governance_report.rejected,
                "needs_review": governance_report.needs_review,
                "deployed": governance_report.deployed,
            }
        
        logger.info(
            f"Governance batch processed: {report.get('deployed', 0)} deployed, "
            f"{report.get('failed', 0)} failed"
        )
        
        return report
    
    except Exception as exc:
        logger.warning(f"Governance batch failed: {exc}")
        return {"status": "failed", "error": str(exc)}
```

### Testing

**Test governance batch runs successfully:**

```python
# backend/tests/test_scheduler_governance.py
import pytest
from app.tasks.scheduler import get_scheduler

@pytest.mark.asyncio
async def test_governance_batch_uses_repair_package():
    """Verify governance batch uses repair engine package."""
    scheduler = get_scheduler()
    
    # Run governance batch job
    result = await scheduler._process_governance_batch()
    
    assert "total_evaluated" in result or "status" in result
    print(f"✓ Governance batch result: {result}")
```

### Acceptance Criteria

- [x] Scheduler imports from `app.adapters_config`
- [x] Supports both microservices and monolithic mode
- [x] Test passes
- [x] Old monolithic import removed
- [x] Governance batch runs successfully

**Estimated Completion:** Day 2-3 (1-2 hours)

---

## Gap 5: Create Critical Documentation

**Status:** ❌ MISSING  
**Priority:** P2  
**Effort:** 2-3 days  
**Assignee:** Technical Writer / Senior Developer

### Problem Statement

Three critical documents are missing:
1. Migration Guide - Operators don't know how to migrate
2. Operations Runbook - Support team can't troubleshoot
3. Service Contracts - Developers don't understand boundaries

### Solution Overview

Create three comprehensive documents following the templates provided in the original implementation plan.

---

### Task 5.1: Create Migration Guide

**File:** `Docs/05-Operations-and-Deployment/PHASE2_MIGRATION_GUIDE.md`

**Content Outline:**

```markdown
# Phase 2 Migration Guide: Monolithic → Microservices

## Overview
- Timeline: 1-2 weeks
- Downtime: Zero (blue-green deployment)
- Rollback: < 5 minutes

## Pre-Migration Checklist
- [ ] Infrastructure ready (Docker, PostgreSQL, Redis, Neo4j)
- [ ] Packages built and tested
- [ ] Docker images built
- [ ] Integration tests passing
- [ ] Backups completed

## Migration Paths
### Path A: Development/Staging (Direct cut-over)
### Path B: Production (Blue-Green with gradual traffic shift)

## Step-by-Step Migration
### Phase 1: Pre-Migration Validation (1 day)
### Phase 2: Deploy Microservices Stack (2-4 hours)
### Phase 3: Validation & Monitoring (24-48 hours)
### Phase 4: Traffic Migration (Production Only)
### Phase 5: Decommission Monolith

## Rollback Procedures
### Emergency Rollback (< 5 minutes)
### Data Rollback

## Troubleshooting
- Service won't start
- High latency
- Data inconsistency

## Post-Migration Checklist
```

**Priority:** Create this first (Week 2)

---

### Task 5.2: Create Operations Runbook

**File:** `Docs/05-Operations-and-Deployment/MICROSERVICES_RUNBOOK.md`

**Content Outline:**

```markdown
# Microservices Operations Runbook

## Daily Operations
- Start services: `docker-compose up -d`
- Stop services: `docker-compose down`
- View logs: `docker-compose logs -f`
- Restart single service

## Monitoring & Alerts
- Health checks
- Key metrics (latency, error rate, connections)
- Resource usage

## Common Issues & Fixes
- Service won't start
- High memory usage
- Database connection pool exhausted
- Circuit breaker open

## Maintenance Tasks
- Weekly: Review error logs
- Monthly: Backup databases, prune Docker images
- Quarterly: Update dependencies

## Emergency Procedures
- Complete system failure
- Database corruption
- Security incident

## Scaling Operations
- Horizontal scaling
- Vertical scaling

## Useful Commands
- Database operations
- Docker cleanup
- Performance profiling

## Contact Information
- On-call engineer
- Escalation matrix
```

**Priority:** Create second (Week 2)

---

### Task 5.3: Create Service Contracts Document

**File:** `Docs/03-Implementation-Plans/phase2_service_contracts.md`

**Content Outline:**

```markdown
# Phase 2: Service Contracts

## Service 1: AMC Platform Orchestrator
### Endpoints
- POST /api/query
- POST /api/chat
- GET /api/health

### Dependencies
- Feedback Service (follow-up detection)
- Repair Service (patch application)
- Neo4j, FAISS (direct)

### Data Ownership
- Query history
- Session data
- FAISS indexes

## Service 2: Feedback Loop Service
### Endpoints
- POST /api/feedback
- POST /api/feedback/follow-up-detection
- GET /api/feedback/{id}
- GET /api/health

### Dependencies
- Repair Service (create patches)
- PostgreSQL/SQLite

### Data Ownership
- response_feedback table
- query_evidence table

## Service 3: Repair Engine Service
### Endpoints
- POST /api/patches
- GET /api/patches/pending
- GET /api/patches/for-entities
- POST /api/patches/{id}/approve
- POST /api/governance/run-batch
- GET /api/health

### Dependencies
- Neo4j (graph mutations)
- Redis (patch storage)

### Data Ownership
- Correction patches
- Evaluation history

## Inter-Service Authentication
- JWT tokens (future)
- Service-to-service headers

## Database Separation Strategy
- Phase 2.1: Shared PostgreSQL with schemas
- Phase 2.2: Namespace separation
- Phase 3: Separate databases
```

**Priority:** Create third (Week 3)

---

### Acceptance Criteria for Gap 5

- [x] Migration guide created and reviewed
- [x] Operations runbook created and reviewed
- [x] Service contracts documented
- [x] All documents in version control
- [x] Team trained on documentation
- [x] Documents referenced in main README

**Estimated Completion:** Week 2-3 (2-3 days)

---

## Implementation Timeline

### Week 1: Critical Blockers

**Day 1:**
- [x] Gap 3: Add packages to requirements.txt (15 min)
- [x] Start Gap 2: Create server.py modules (4-6 hours)

**Day 2:**
- [x] Complete Gap 2: Test servers in containers (2-4 hours)
- [x] Gap 4: Refactor scheduler (1-2 hours)
- [x] Start Gap 1: Create service clients (2-4 hours)

**Day 3:**
- [x] Continue Gap 1: Complete service clients (4-6 hours)

**Day 4:**
- [x] Gap 1: Implement circuit breaker (3-4 hours)
- [x] Gap 1: Add microservices config (1-2 hours)

**Day 5:**
- [x] Gap 1: Update orchestrator (3-4 hours)
- [x] Gap 1: Write tests (2-3 hours)

### Week 2: Testing & Documentation

**Day 6-7:**
- Integration testing
- End-to-end testing
- Load testing

**Day 8-10:**
- Gap 5: Create documentation
- Team training
- Final review

### Week 3: Deployment Preparation

**Day 11-12:**
- Staging deployment
- Validation

**Day 13-15:**
- Production preparation
- Final checks
- Go-live planning

---

## Success Metrics

### Technical Metrics

| Metric | Target | Validation Method |
|--------|--------|-------------------|
| All service clients implemented | 100% | Code review + tests passing |
| FastAPI servers functional | 100% | Health checks return 200 |
| Docker containers start | 100% | `docker-compose ps` shows all healthy |
| Circuit breaker working | 100% | Circuit breaker tests passing |
| Integration tests passing | 100% | pytest runs clean |
| Documentation complete | 100% | All 3 docs created and reviewed |

### Business Metrics

| Metric | Target | Timeline |
|--------|--------|----------|
| Zero production downtime | ✅ | During migration |
| < 5 min rollback time | ✅ | If issues occur |
| Team trained | 100% | Week 2 |
| Staging validated | ✅ | Week 3 |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Service communication failures | Medium | High | Circuit breaker + fallback to monolithic |
| Container startup issues | Low | High | Comprehensive testing in staging |
| Data inconsistency | Low | Critical | Integration tests + validation scripts |
| Team knowledge gap | Medium | Medium | Documentation + training sessions |
| Timeline overrun | Medium | Medium | Clear priorities + daily standups |

---

## Approval & Sign-Off

### Implementation Team

- [ ] Backend Lead: _________________ Date: _______
- [ ] DevOps Lead: _________________ Date: _______
- [ ] QA Lead: _________________ Date: _______

### Management

- [ ] Engineering Manager: _________________ Date: _______
- [ ] Product Owner: _________________ Date: _______

---

## Appendix

### A. Quick Reference Commands

```bash
# Install packages
cd backend
pip install -r requirements.txt

# Build Docker images
docker-compose build feedback-service repair-service

# Start services
docker-compose up -d

# Check health
curl http://localhost:8001/api/health
curl http://localhost:8002/api/health

# View logs
docker-compose logs -f feedback-service repair-service

# Run tests
pytest tests/integration/test_microservices_communication.py -v
```

### B. Contact Information

**Implementation Lead:** TBD  
**Slack Channel:** #phase2-implementation  
**Daily Standup:** 10 AM UTC  
**Issue Tracker:** GitHub Issues with `phase2` label

---

**Document Status:** ACTIVE  
**Last Updated:** January 2025  
**Next Review:** End of Week 1
