"""
HTTP client for standalone Repair Engine service with circuit breaker fallback.
"""
import asyncio
import hashlib
import logging
from typing import Any, Dict, List, Optional, Set
import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

logger = logging.getLogger("app.clients.repair_client")

class RepairServiceClient:
    def __init__(self, base_url: str = "http://localhost:8002"):
        """Initialize a new instance of RepairServiceClient.

        Args:
            base_url (str): The base url.
        """
        self.base_url = base_url.rstrip("/")
        self.breaker = CircuitBreaker(service_name="repair_service")
        self._pending_requests: Set[str] = set()  # Deduplication
        self._lock = asyncio.Lock()

    def _task_hash(self, issue_id: str, canonical_query: str) -> str:
        """Generate deterministic hash for deduplication.

        Args:
            issue_id (str): Unique identifier of the issue.
            canonical_query (str): The canonical query.

        Returns:
            str: Hash string for deduplication.
        """
        return hashlib.sha256(f"{issue_id}:{canonical_query}".encode()).hexdigest()[:16]

    async def get_pending_patches(self) -> List[Dict[str, Any]]:
        """Retrieve pending patches.

        Returns:
            List[Dict[str, Any]]: List of resulting items or records.
        """
        if not self.breaker.allow_request():
            logger.warning("Repair service circuit breaker is OPEN")
            raise CircuitBreakerOpenException("Repair service circuit is OPEN")

        try:
            # Use explicit timeouts for all phases
            timeout = httpx.Timeout(
                connect=5.0,   # Time to establish connection
                read=10.0,     # Time to read response body
                write=5.0,     # Time to send request body
                pool=5.0,      # Time to acquire connection from pool
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.get(f"{self.base_url}/api/patches/pending")
                if res.status_code == 200:
                    self.breaker.record_success()
                    return res.json()
                else:
                    self.breaker.record_failure()
                    logger.warning("Repair service HTTP %d: %s", res.status_code, res.text[:200])
                    return []
        except httpx.TimeoutException as timeout_exc:
            self.breaker.record_failure()
            logger.error("Repair service timeout: %s", timeout_exc)
            raise CircuitBreakerOpenException("Repair service timeout")
        except Exception as exc:
            self.breaker.record_failure()
            logger.warning("Failed to call remote repair service (%s)", exc)
            raise

    async def approve_patch(self, patch_id: str) -> bool:
        """Approve patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if not self.breaker.allow_request():
            raise CircuitBreakerOpenException("Repair service circuit is OPEN")

        try:
            timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(f"{self.base_url}/api/patches/{patch_id}/approve")
                if res.status_code == 200:
                    self.breaker.record_success()
                    return True
                else:
                    self.breaker.record_failure()
                    logger.warning("Approve patch HTTP %d: %s", res.status_code, res.text[:200])
                    return False
        except httpx.TimeoutException as timeout_exc:
            self.breaker.record_failure()
            logger.error("Approve patch timeout: %s", timeout_exc)
            raise CircuitBreakerOpenException("Repair service timeout")
        except Exception as exc:
            self.breaker.record_failure()
            raise

    async def create_repair_task(
        self,
        issue_id: str,
        canonical_query: str,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
        contributor_count: int = 1,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a repair task in the standalone Repair Engine service.
        If the remote service is unavailable or circuit is open, creates a local repair task
        via CorrectionPatchLayer fallback.

        Args:
            issue_id (str): Unique identifier of the issue.
            canonical_query (str): The canonical query.
            primary_entities (Optional[List[str]]): Collection or list of primary entities.
            taxonomy_paths (Optional[List[str]]): Collection or list of taxonomy paths.
            contributor_count (int): The contributor count.
            provenance (Optional[Dict[str, Any]]): The provenance.

        Returns:
            str: Resulting str instance.
        """
        # Deduplication check
        task_hash = self._task_hash(issue_id, canonical_query)
        
        async with self._lock:
            if task_hash in self._pending_requests:
                logger.warning("Duplicate repair task detected for issue_id=%s, skipping", issue_id)
                return f"task_duplicate_{task_hash}"
            self._pending_requests.add(task_hash)
        
        try:
            if self.breaker.allow_request():
                try:
                    entity_id = (primary_entities[0] if primary_entities else f"issue_{issue_id}").strip()
                    payload = {
                        "entity_id": entity_id,
                        "attribute": "regulatory_fact",
                        "canonical_value": canonical_query,
                        "corrected_value": f"Pending repair for query: {canonical_query}",
                        "confidence": 0.9,
                        "provenance": provenance or {
                            "issue_id": issue_id,
                            "contributor_count": contributor_count,
                            "taxonomy_paths": taxonomy_paths or [],
                        },
                        "approved": False,
                    }
                    
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
                    
                    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        res = await client.post(
                            f"{self.base_url}/api/patches",
                            json=payload,
                            headers=headers
                        )
                        
                        # Validate Content-Type before parsing
                        content_type = res.headers.get("content-type", "")
                        if res.status_code in (200, 201):
                            if "application/json" not in content_type.lower():
                                logger.error(
                                    "Repair service returned non-JSON response (Content-Type: %s): %s",
                                    content_type,
                                    res.text[:200]
                                )
                                self.breaker.record_failure()
                            else:
                                try:
                                    data = res.json()
                                    
                                    # Validate response structure
                                    if not isinstance(data, dict):
                                        logger.error("Repair service response is not a dict: %s", type(data))
                                        self.breaker.record_failure()
                                    else:
                                        patch_id = data.get("patch_id") or data.get("task_id")
                                        if patch_id:
                                            self.breaker.record_success()
                                            return f"task_{patch_id}" if not patch_id.startswith("task_") else patch_id
                                        logger.warning("Repair service response missing patch_id/task_id: %s", data)
                                
                                except Exception as json_exc:
                                    logger.error("Repair service returned invalid JSON: %s", json_exc)
                                    self.breaker.record_failure()
                        else:
                            self.breaker.record_failure()
                            logger.warning("Repair service HTTP %d: %s", res.status_code, res.text[:200])
                
                except httpx.TimeoutException as timeout_exc:
                    self.breaker.record_failure()
                    logger.warning("Remote repair service timeout: %s", timeout_exc)
                except Exception as exc:
                    self.breaker.record_failure()
                    logger.info(
                        "Remote repair service at %s unavailable (%s). Falling back to local repair task generator.",
                        self.base_url,
                        exc,
                    )
            
            # Fallback to local (only if remote not attempted or failed)
            return self._create_local_repair_task(
                issue_id=issue_id,
                canonical_query=canonical_query,
                primary_entities=primary_entities,
                taxonomy_paths=taxonomy_paths,
                contributor_count=contributor_count,
                provenance=provenance,
            )
        finally:
            async with self._lock:
                self._pending_requests.discard(task_hash)

    def _create_local_repair_task(
        self,
        issue_id: str,
        canonical_query: str,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
        contributor_count: int = 1,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Local in-memory / shadow graph patch creation fallback.

        Args:
            issue_id (str): Unique identifier of the issue.
            canonical_query (str): The canonical query.
            primary_entities (Optional[List[str]]): Collection or list of primary entities.
            taxonomy_paths (Optional[List[str]]): Collection or list of taxonomy paths.
            contributor_count (int): The contributor count.
            provenance (Optional[Dict[str, Any]]): The provenance.

        Returns:
            str: Resulting str instance.
        """
        try:
            from app.graph.correction_patch_layer import get_correction_patch_layer
            patch_layer = get_correction_patch_layer()
            entity_id = (primary_entities[0] if primary_entities else f"issue_{issue_id}").strip()
            patch_id = patch_layer.add_correction(
                entity_id=entity_id,
                attribute="regulatory_fact",
                canonical_value=canonical_query,
                corrected_value=f"Pending repair for query: {canonical_query}",
                confidence=0.9,
                provenance=provenance or {
                    "issue_id": issue_id,
                    "contributor_count": contributor_count,
                    "taxonomy_paths": taxonomy_paths or [],
                },
                approved=False,
            )
            return f"task_{patch_id}"
        except Exception as local_exc:
            logger.debug("Local patch layer fallback note: %s", local_exc)
            import uuid
            return f"task_rep_{uuid.uuid4().hex[:12]}"

    def create_repair_task_sync(
        self,
        issue_id: str,
        canonical_query: str,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
        contributor_count: int = 1,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Synchronous version for direct sync route/service invocation.

        Args:
            issue_id (str): Unique identifier of the issue.
            canonical_query (str): The canonical query.
            primary_entities (Optional[List[str]]): Collection or list of primary entities.
            taxonomy_paths (Optional[List[str]]): Collection or list of taxonomy paths.
            contributor_count (int): The contributor count.
            provenance (Optional[Dict[str, Any]]): The provenance.

        Returns:
            str: Resulting str instance.
        """
        if self.breaker.allow_request():
            try:
                entity_id = (primary_entities[0] if primary_entities else f"issue_{issue_id}").strip()
                payload = {
                    "entity_id": entity_id,
                    "attribute": "regulatory_fact",
                    "canonical_value": canonical_query,
                    "corrected_value": f"Pending repair for query: {canonical_query}",
                    "confidence": 0.9,
                    "provenance": provenance or {
                        "issue_id": issue_id,
                        "contributor_count": contributor_count,
                        "taxonomy_paths": taxonomy_paths or [],
                    },
                    "approved": False,
                }
                from app.core.logging import request_id_ctx, session_id_ctx
                request_id = request_id_ctx.get("")
                session_id = session_id_ctx.get("")
                headers = {"Content-Type": "application/json"}
                if request_id:
                    headers["X-Request-ID"] = request_id
                    headers["X-Trace-ID"] = request_id
                if session_id:
                    headers["X-Session-ID"] = session_id

                with httpx.Client(timeout=2.0) as client:
                    res = client.post(f"{self.base_url}/api/patches", json=payload, headers=headers)
                    if res.status_code in (200, 201):
                        self.breaker.record_success()
                        data = res.json()
                        patch_id = data.get("patch_id") or data.get("task_id")
                        if patch_id:
                            return f"task_{patch_id}" if not patch_id.startswith("task_") else patch_id
                    else:
                        self.breaker.record_failure()
            except Exception as exc:
                self.breaker.record_failure()
                logger.info(
                    "Remote repair service at %s unavailable (%s). Using local task generator.",
                    self.base_url,
                    exc,
                )

        return self._create_local_repair_task(
            issue_id=issue_id,
            canonical_query=canonical_query,
            primary_entities=primary_entities,
            taxonomy_paths=taxonomy_paths,
            contributor_count=contributor_count,
            provenance=provenance,
        )


_repair_service_client: Optional[RepairServiceClient] = None


def get_repair_service_client() -> RepairServiceClient:
    """Retrieve repair service client.

    Returns:
        RepairServiceClient: Resulting RepairServiceClient instance.
    """
    global _repair_service_client
    if _repair_service_client is None:
        import os
        base_url = os.getenv("REPAIR_ENGINE_URL", "http://localhost:8002")
        _repair_service_client = RepairServiceClient(base_url=base_url)
    return _repair_service_client

