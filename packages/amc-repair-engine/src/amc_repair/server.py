"""
FastAPI server for Repair Engine Service.
Standalone microservice for correction management and governance.
"""
import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import RepairEngine, RepairConfig
from .adapters.cache import RedisAdapter, MemoryCacheAdapter, MemoryAdapter
from .adapters.graph import Neo4jAdapter, MemoryGraphAdapter

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
                cache_adapter = MemoryCacheAdapter()
        else:
            cache_adapter = MemoryCacheAdapter()
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
    confidence: float = 1.0
    provenance: Dict[str, Any] = {}
    approved: bool = False


class BatchApproveRequest(BaseModel):
    patch_ids: List[str]


class RejectPatchRequest(BaseModel):
    reason: Optional[str] = None


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
        "timestamp": datetime.now(timezone.utc).isoformat()
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
                    "canonical_value": p.canonical_value if p.canonical_value is not None else p.original_value,
                    "corrected_value": p.corrected_value,
                    "confidence": p.confidence,
                    "provenance": p.provenance,
                    "created_at": p.created_at,
                    "expires_at": p.expires_at
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
        
        entity_id_list = [eid.strip() for eid in entity_ids.split(",") if eid.strip()]
        all_patches = []
        
        for entity_id in entity_id_list:
            patches = await engine.patch_layer.get_patches_for_entity(entity_id)
            all_patches.extend(patches)
        
        return {
            "patches": [
                {
                    "patch_id": p.patch_id,
                    "entity_id": p.entity_id,
                    "attribute": p.attribute,
                    "canonical_value": p.canonical_value if p.canonical_value is not None else p.original_value,
                    "corrected_value": p.corrected_value,
                    "confidence": p.confidence,
                    "approved": p.approved
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
async def reject_patch(patch_id: str, request: Optional[RejectPatchRequest] = None):
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
            "deployed": report.deployed if report.deployed > 0 else report.promoted_to_graph,
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
