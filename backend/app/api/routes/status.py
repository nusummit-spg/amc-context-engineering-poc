# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import json
import os
from pathlib import Path
from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.schemas.api import DataPlanesResponse, HealthResponse

router = APIRouter(prefix="/status", tags=["status"])


def _get_legacy_stats() -> dict:
    meta_path = Path("backend/app/engine/faiss_indexes/amc_master/meta.json")
    if not meta_path.exists():
        meta_path = Path("app/engine/faiss_indexes/amc_master/meta.json")
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return {
                "engine": "legacy_engine",
                "corpus_version": "amc_master_legacy",
                "documents": 18,
                "parents": data.get("num_parents", 386),
                "children": data.get("num_children", 1769),
            }
        except Exception:
            pass
    return {"engine": "legacy_engine", "corpus_version": "amc_master_legacy", "documents": 18}


import asyncio

@router.get("", response_model=HealthResponse)
async def status(container: Container = Depends(get_container)) -> HealthResponse:
    try:
        neo4j_ok = await asyncio.wait_for(container.graph.ping(), timeout=0.8)
    except Exception:
        neo4j_ok = False
    qdrant_ok = container.vector.ping()
    llm_ok = bool(container.settings.groq_api_key)

    modern_chunks = 0
    modern_docs = 0
    if qdrant_ok:
        modern_chunks = container.vector.count()
        modern_docs = len(await container.vector.list_documents()) if modern_chunks else 0

    legacy_stats = _get_legacy_stats()
    modern_stats = {
        "engine": "v2_orchestrator",
        "corpus_version": container.settings.active_corpus_version,
        "documents": modern_docs,
        "chunks": modern_chunks,
    }

    return HealthResponse(
        status="ok" if (neo4j_ok and qdrant_ok) else "degraded",
        neo4j="ok" if neo4j_ok else "error",
        qdrant="ok" if qdrant_ok else "error",
        llm="ok" if llm_ok else "error",
        documents_indexed=modern_docs if container.settings.query_engine == "v2" else legacy_stats.get("documents", 18),
        chunks_indexed=modern_chunks if container.settings.query_engine == "v2" else legacy_stats.get("children", 1769),
        serving_engine=container.settings.query_engine,
        serving_corpus_version=container.settings.active_corpus_version if container.settings.query_engine == "v2" else "amc_master_legacy",
        legacy_index=legacy_stats,
        modern_index=modern_stats,
    )


@router.get("/data-planes", response_model=DataPlanesResponse)
async def data_planes(container: Container = Depends(get_container)) -> DataPlanesResponse:
    modern_chunks = container.vector.count() if container.vector.ping() else 0
    modern_docs = len(await container.vector.list_documents()) if modern_chunks else 0

    legacy_stats = _get_legacy_stats()
    modern_stats = {
        "engine": "v2_orchestrator",
        "corpus_version": container.settings.active_corpus_version,
        "documents": modern_docs,
        "chunks": modern_chunks,
    }

    return DataPlanesResponse(
        serving_engine=container.settings.query_engine,
        serving_corpus_version=container.settings.active_corpus_version if container.settings.query_engine == "v2" else "amc_master_legacy",
        legacy_index=legacy_stats,
        modern_index=modern_stats,
        query_engines_available=["legacy", "v2", "shadow"],
    )
