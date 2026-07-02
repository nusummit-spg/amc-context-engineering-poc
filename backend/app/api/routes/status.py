"""WS3 — /status endpoint: health of all dependencies + index counts."""
from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.schemas.api import HealthResponse

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=HealthResponse)
async def status(container: Container = Depends(get_container)) -> HealthResponse:
    neo4j_ok = await container.graph.ping()
    qdrant_ok = container.vector.ping()
    llm_ok = bool(container.settings.anthropic_api_key)

    docs = 0
    chunks = 0
    if qdrant_ok:
        chunks = container.vector.count()
        docs = len(await container.vector.list_documents()) if chunks else 0

    return HealthResponse(
        status="ok" if (neo4j_ok and qdrant_ok) else "degraded",
        neo4j="up" if neo4j_ok else "down",
        qdrant="up" if qdrant_ok else "down",
        llm="configured" if llm_ok else "missing_api_key",
        documents_indexed=docs,
        chunks_indexed=chunks,
    )
