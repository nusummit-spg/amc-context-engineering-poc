"""Fail-closed ingress for unreceipted legacy AMC query and graph routes."""
from fastapi import HTTPException
from amc_publication.vector_bridge28 import verified_mode

def reject_legacy_in_verified_mode(*, route: str) -> None:
    """Deny raw FAISS/graph reads while active receipt enforcement is enabled."""
    if verified_mode() == "enforce":
        raise HTTPException(status_code=503,
                            detail=f"{route} unavailable in verified mode; use receipt-bound v2 API")

def require_v2_in_verified_mode(engine: str, *, route: str) -> None:
    """Block legacy, canary and shadow fallback during verified serving."""
    if verified_mode() == "enforce" and engine != "v2":
        raise HTTPException(status_code=503,
                            detail=f"{route} requires QUERY_ENGINE=v2 in verified mode")

def require_verified_tenant(current_user, *, route: str) -> None:
    """Reject unauthenticated serving before opening an SSE response."""
    if verified_mode() == "enforce" and not getattr(current_user, "tenant_id", None):
        raise HTTPException(status_code=403,
                            detail=f"{route} requires an authenticated tenant in verified mode")
