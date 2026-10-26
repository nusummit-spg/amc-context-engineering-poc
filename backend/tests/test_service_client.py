"""
Unit tests for ServiceClient, FeedbackServiceClient, and RepairServiceClient.
"""
import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.services.client_base import ServiceClient, ServiceError
from app.services.feedback_client import FeedbackServiceClient
from app.services.repair_client import RepairServiceClient


@pytest.mark.asyncio
async def test_service_client_get_success():
    """Test successful GET request."""
    client = ServiceClient("http://test-service:8000", "test-service")

    async def mock_request(*args, **kwargs):
        req = httpx.Request("GET", "http://test-service:8000/api/health")
        return httpx.Response(200, json={"status": "healthy"}, request=req)

    client._client.request = AsyncMock(side_effect=mock_request)

    response = await client.get("/api/health")
    assert response == {"status": "healthy"}
    assert await client.health_check() is True

    await client.close()


@pytest.mark.asyncio
async def test_service_client_post_success():
    """Test successful POST request."""
    client = ServiceClient("http://test-service:8000", "test-service")

    async def mock_request(*args, **kwargs):
        req = httpx.Request("POST", "http://test-service:8000/api/data")
        return httpx.Response(200, json={"status": "created", "id": "123"}, request=req)

    client._client.request = AsyncMock(side_effect=mock_request)

    response = await client.post("/api/data", {"key": "val"})
    assert response.get("status") == "created"
    assert response.get("id") == "123"

    await client.close()


@pytest.mark.asyncio
async def test_service_client_handles_http_errors():
    """Test HTTP error raising ServiceError."""
    client = ServiceClient("http://test-service:8000", "test-service")

    async def mock_request(*args, **kwargs):
        req = httpx.Request("GET", "http://test-service:8000/api/notfound")
        return httpx.Response(404, text="Resource not found", request=req)

    client._client.request = AsyncMock(side_effect=mock_request)

    with pytest.raises(ServiceError) as exc_info:
        await client.get("/api/notfound")

    assert exc_info.value.status_code == 404
    assert "Resource not found" in exc_info.value.message

    await client.close()


@pytest.mark.asyncio
async def test_feedback_client_methods():
    """Test FeedbackServiceClient methods with mocked HTTP responses."""
    client = FeedbackServiceClient("http://feedback-service:8001")

    async def mock_request(method, url, **kwargs):
        req = httpx.Request(method, url)
        if "/api/feedback/follow-up-detection" in str(url):
            return httpx.Response(200, json={"is_correction": True, "confidence": 0.85}, request=req)
        elif "/api/feedback/recent" in str(url):
            return httpx.Response(200, json={"total": 1, "feedback": [{"id": "f1"}]}, request=req)
        elif "/api/feedback/f1" in str(url):
            return httpx.Response(200, json={"id": "f1", "feedback_text": "TER is 0.82%"}, request=req)
        elif "/api/feedback" in str(url):
            return httpx.Response(200, json={"status": "correction_detected", "claim": {"attribute": "TER"}}, request=req)
        return httpx.Response(200, json={"status": "ok"}, request=req)

    client._client.request = AsyncMock(side_effect=mock_request)

    sub_res = await client.submit_feedback(
        session_id="s1",
        response_id="r1",
        feedback_text="TER is 0.82%",
        original_query="What is TER?",
        original_response="TER is 0.79%"
    )
    assert sub_res["status"] == "correction_detected"

    det_res = await client.detect_follow_up_correction(
        session_id="s1",
        previous_response_id="r1",
        original_query="What is TER?",
        original_response="TER is 0.79%",
        follow_up_query="No, it is 0.82%"
    )
    assert det_res["is_correction"] is True

    fb = await client.get_feedback("f1")
    assert fb["id"] == "f1"

    recent = await client.get_recent_feedback(limit=5)
    assert len(recent) == 1

    await client.close()


@pytest.mark.asyncio
async def test_repair_client_methods():
    """Test RepairServiceClient methods with mocked HTTP responses."""
    client = RepairServiceClient("http://repair-service:8002")

    async def mock_request(method, url, **kwargs):
        req = httpx.Request(method, url)
        if "/api/patches/for-entities" in str(url):
            return httpx.Response(200, json={"patches": [{"entity_id": "e1", "attribute": "TER", "confidence": 0.95}]}, request=req)
        elif "/api/patches/pending" in str(url):
            return httpx.Response(200, json={"patches": [{"patch_id": "p1"}]}, request=req)
        elif "/api/patches/p1/approve" in str(url):
            return httpx.Response(200, json={"status": "approved", "patch_id": "p1"}, request=req)
        elif "/api/patches/p1/reject" in str(url):
            return httpx.Response(200, json={"status": "rejected", "patch_id": "p1"}, request=req)
        elif "/api/patches/batch-approve" in str(url):
            return httpx.Response(200, json={"approved": ["p1"], "failed": []}, request=req)
        elif "/api/governance/run-batch" in str(url):
            return httpx.Response(200, json={"status": "completed", "total_evaluated": 5, "approved": 4, "deployed": 4}, request=req)
        elif "/api/patches" in str(url):
            return httpx.Response(200, json={"status": "created", "patch_id": "p1"}, request=req)
        return httpx.Response(200, json={"status": "ok"}, request=req)

    client._client.request = AsyncMock(side_effect=mock_request)

    pid = await client.create_correction_patch(
        entity_id="e1",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.95,
        provenance={"source": "feedback"}
    )
    assert pid == "p1"

    patches = await client.get_patches_for_entities(["e1"])
    assert len(patches) == 1
    assert patches[0]["attribute"] == "TER"

    pending = await client.get_pending_corrections()
    assert len(pending) == 1

    app_res = await client.approve_patch("p1")
    assert app_res is True

    rej_res = await client.reject_patch("p1")
    assert rej_res is True

    batch_app = await client.batch_approve_patches(["p1"])
    assert batch_app["approved"] == ["p1"]

    gov = await client.run_governance_batch(auto_approve_threshold=0.90)
    assert gov["status"] == "completed"
    assert gov["deployed"] == 4

    await client.close()
