# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""FastAPI router for retrieval & efficiency metrics."""
from typing import Optional

from fastapi import APIRouter
from app.core.metrics import get_metrics_store

router = APIRouter(prefix="/metrics", tags=["monitoring"])


@router.get("/summary")
async def get_summary(phase: Optional[str] = None):
    """Returns summary metrics (p50/p99 latency, tokens, cache hit rate)."""
    store = get_metrics_store()
    return store.summary(filter_by_phase=phase if phase and phase != "all" else None)


@router.get("/recent")
async def get_recent(count: int = 100):
    """Returns the last N query metrics records."""
    store = get_metrics_store()
    return [m.to_dict() for m in store.metrics[-count:]]


@router.post("/reset")
async def reset_metrics():
    """Clears collected in-memory metrics (useful between benchmark phases)."""
    store = get_metrics_store()
    store.clear()
    return {"status": "reset", "count": len(store.metrics)}
