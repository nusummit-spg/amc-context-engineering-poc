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
from .logging import (
    setup_repair_logging,
    get_repair_logger,
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
)

# Configure logging
setup_repair_logging()
logger = get_repair_logger("server")

# Create FastAPI app
app = FastAPI(
    title="AMC Repair Engine Service",
    description="Microservice for correction patches and governance",
    version="0.1.0"
)

# Global repair engine instance
_repair_engine: Optional[RepairEngine] = None


def get_repair_engine() -> RepairEngine:
    """Get or create repair engine singleton.

    Returns:
        RepairEngine: Resulting RepairEngine instance.
    """
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
    entity_id: Optional[str] = "unknown_entity"
    attribute: Optional[str] = "general"
    canonical_value: Any = None
    corrected_value: Any = None
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
    """Health check endpoint.

    Returns:
        Result of the operation.
    """
    return {
        "status": "healthy",
        "service": "repair-engine",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.on_event("startup")
async def startup_event():
    """Startup event.
    """
    log_step_info(logger, "SERVER_STARTUP", "AMC Repair Engine Service initialized on port %s", os.getenv("PORT", "8002"))


@app.post("/api/patches")
async def create_patch(request: CreatePatchRequest):
    """Create a correction patch.

    Args:
        request (CreatePatchRequest): FastAPI request instance.

    Returns:
        Result of the operation.
    """
    try:
        log_step_info(
            logger,
            "PATCH_CREATE_REQUEST",
            "Creating patch for entity=%s attr=%s corrected=%s (approved=%s)",
            request.entity_id,
            request.attribute,
            request.corrected_value,
            request.approved,
        )
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
        
        log_step_info(logger, "PATCH_CREATED", "Patch %s created successfully for entity=%s", patch_id, request.entity_id)
        
        return {
            "status": "created",
            "patch_id": patch_id
        }
    
    except Exception as exc:
        log_step_error(logger, "PATCH_CREATE_ERROR", "Create patch error for entity=%s: %s", request.entity_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/patches/pending")
async def get_pending_patches():
    """Get all pending (unapproved) patches.

    Returns:
        The requested pending patches.
    """
    try:
        log_step_info(logger, "PATCH_PENDING_REQUEST", "Fetching all pending correction patches")
        engine = get_repair_engine()
        
        patches = await engine.get_pending_corrections()
        log_step_info(logger, "PATCH_PENDING_RESPONSE", "Retrieved %d pending patches", len(patches))
        
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
        log_step_error(logger, "PATCH_PENDING_ERROR", "Get pending patches error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/patches/for-entities")
async def get_patches_for_entities(entity_ids: str):
    """Get patches for specified entities (comma-separated IDs).

    Args:
        entity_ids (str): Collection or list of entity ids.

    Returns:
        The requested patches for entities.
    """
    try:
        log_step_info(logger, "ENTITY_PATCHES_QUERY", "Querying patches for entities: %s", entity_ids)
        engine = get_repair_engine()
        
        entity_id_list = [eid.strip() for eid in entity_ids.split(",") if eid.strip()]
        all_patches = []
        
        for entity_id in entity_id_list:
            patches = await engine.patch_layer.get_patches_for_entity(entity_id)
            all_patches.extend(patches)
        
        seen_ids = set()
        unique_patches = []
        for p in all_patches:
            if p.patch_id not in seen_ids:
                seen_ids.add(p.patch_id)
                unique_patches.append(p)

        log_step_info(logger, "ENTITY_PATCHES_RESPONSE", "Found %d unique patches for entities", len(unique_patches))
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
                for p in unique_patches
            ]
        }
    
    except Exception as exc:
        log_step_error(logger, "ENTITY_PATCHES_ERROR", "Get patches for entities error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/patches/{patch_id}")
async def get_patch_by_id(patch_id: str):
    """Get details of a specific patch by ID.

    Args:
        patch_id (str): Unique identifier of the patch.

    Returns:
        The requested patch by id.
    """
    try:
        log_step_info(logger, "PATCH_GET_REQUEST", "Fetching patch details for %s", patch_id)
        engine = get_repair_engine()
        
        patch = await engine.patch_layer.get_patch(patch_id)
        
        if not patch:
            log_step_warning(logger, "PATCH_GET_NOT_FOUND", "Patch %s not found", patch_id)
            raise HTTPException(status_code=404, detail=f"Patch {patch_id} not found")
        
        log_step_info(logger, "PATCH_GET_SUCCESS", "Retrieved patch %s for entity %s", patch_id, patch.entity_id)
        return {
            "patch_id": patch.patch_id,
            "entity_id": patch.entity_id,
            "attribute": patch.attribute,
            "canonical_value": patch.canonical_value if patch.canonical_value is not None else patch.original_value,
            "corrected_value": patch.corrected_value,
            "confidence": patch.confidence,
            "provenance": patch.provenance,
            "approved": patch.approved,
            "created_at": patch.created_at,
            "expires_at": patch.expires_at,
            "version": getattr(patch, "version", 1),
            "supersedes_patch_id": getattr(patch, "supersedes_patch_id", None),
            "superseded_by_patch_id": getattr(patch, "superseded_by_patch_id", None),
            "conflict_resolution_reason": getattr(patch, "conflict_resolution_reason", None),
            "source_type": getattr(patch, "source_type", "user_feedback"),
        }
    
    except HTTPException:
        raise
    except Exception as exc:
        log_step_error(logger, "PATCH_GET_ERROR", "Get patch by ID error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/patches/{patch_id}/approve")
async def approve_patch(patch_id: str):
    """Approve a correction patch and create shadow graph overlay.

    Args:
        patch_id (str): Unique identifier of the patch.

    Returns:
        Result of the operation.
    """
    try:
        log_step_info(logger, "PATCH_APPROVE_REQUEST", "Approving patch %s", patch_id)
        engine = get_repair_engine()
        
        patch = await engine.patch_layer.get_patch(patch_id)
        success = await engine.approve_correction(patch_id)
        
        if not success:
            log_step_warning(logger, "PATCH_APPROVE_NOT_FOUND", "Patch %s not found for approval", patch_id)
            raise HTTPException(status_code=404, detail="Patch not found")
        
        if patch:
            try:
                await engine.graph.create_shadow_patch(
                    entity_id=patch.entity_id,
                    patch_id=patch.patch_id,
                    attribute=patch.attribute,
                    value=patch.corrected_value,
                )
                log_step_info(logger, "SHADOW_GRAPH_LINK", "Shadow graph linked for patch %s on %s", patch_id, patch.entity_id)
            except Exception as shadow_exc:
                log_step_debug(logger, "SHADOW_GRAPH_NOTICE", "Shadow patch link notice: %s", shadow_exc)

        log_step_info(logger, "PATCH_APPROVED", "Patch approved successfully: %s", patch_id)
        
        return {
            "status": "approved",
            "patch_id": patch_id
        }
    
    except HTTPException:
        raise
    except Exception as exc:
        log_step_error(logger, "PATCH_APPROVE_ERROR", "Approve patch error for %s: %s", patch_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/patches/{patch_id}/reject")
async def reject_patch(patch_id: str, request: Optional[RejectPatchRequest] = None):
    """Reject a correction patch and cleanup shadow graph overlay.

    Args:
        patch_id (str): Unique identifier of the patch.
        request (Optional[RejectPatchRequest]): FastAPI request instance.

    Returns:
        Result of the operation.
    """
    try:
        log_step_info(logger, "PATCH_REJECT_REQUEST", "Rejecting patch %s", patch_id)
        engine = get_repair_engine()
        
        try:
            await engine.graph.delete_shadow_patch(patch_id)
        except Exception:
            pass

        success = await engine.reject_correction(patch_id)
        
        if not success:
            log_step_warning(logger, "PATCH_REJECT_NOT_FOUND", "Patch %s not found for rejection", patch_id)
            raise HTTPException(status_code=404, detail="Patch not found")
        
        log_step_info(logger, "PATCH_REJECTED", "Patch rejected successfully: %s", patch_id)
        
        return {
            "status": "rejected",
            "patch_id": patch_id
        }
    
    except HTTPException:
        raise
    except Exception as exc:
        log_step_error(logger, "PATCH_REJECT_ERROR", "Reject patch error for %s: %s", patch_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/patches/batch-approve")
async def batch_approve(request: BatchApproveRequest):
    """Batch approve multiple patches.

    Args:
        request (BatchApproveRequest): FastAPI request instance.

    Returns:
        Result of the operation.
    """
    try:
        log_step_info(logger, "BATCH_APPROVE_REQUEST", "Batch approving %d patches", len(request.patch_ids))
        engine = get_repair_engine()
        
        results = {"approved": [], "failed": []}
        
        for patch_id in request.patch_ids:
            success = await engine.approve_correction(patch_id)
            if success:
                results["approved"].append(patch_id)
            else:
                results["failed"].append(patch_id)
        
        log_step_info(logger, "BATCH_APPROVE_COMPLETE", "Batch approve: %d approved, %d failed", len(results["approved"]), len(results["failed"]))
        
        return results
    
    except Exception as exc:
        log_step_error(logger, "BATCH_APPROVE_ERROR", "Batch approve error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/governance/run-batch")
async def run_governance_batch(request: GovernanceBatchRequest = GovernanceBatchRequest()):
    """Run governance batch to promote approved corrections.

    Args:
        request (GovernanceBatchRequest): FastAPI request instance.

    Returns:
        Result of the operation.
    """
    try:
        log_step_info(logger, "GOVERNANCE_RUN_START", "Running governance batch promotion cycle...")
        engine = get_repair_engine()
        
        report = await engine.run_governance_batch(
            auto_approve_threshold=request.auto_approve_threshold
        )
        
        log_step_info(
            logger,
            "GOVERNANCE_RUN_COMPLETE",
            "Governance batch complete: total=%d approved=%d promoted=%d rejected=%d review=%d",
            report.total_evaluated,
            report.approved,
            report.deployed if report.deployed > 0 else report.promoted_to_graph,
            report.rejected,
            report.needs_review,
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
        log_step_error(logger, "GOVERNANCE_RUN_ERROR", "Governance batch error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/governance/promote/{patch_id}")
async def promote_patch_to_graph(patch_id: str):
    """Promote a specific patch directly to canonical Neo4j graph and retire shadow patch.

    Args:
        patch_id (str): Unique identifier of the patch.

    Returns:
        Result of the operation.
    """
    try:
        log_step_info(logger, "GOVERNANCE_PROMOTE_REQUEST", "Promoting patch %s directly to canonical graph", patch_id)
        engine = get_repair_engine()
        success = await engine.promote_patch(patch_id)
        if not success:
            log_step_warning(logger, "GOVERNANCE_PROMOTE_FAILED", "Patch %s not found or failed to promote", patch_id)
            raise HTTPException(status_code=404, detail="Patch not found or failed to promote")
        
        log_step_info(logger, "GOVERNANCE_PROMOTED", "Patch %s canonically promoted to graph", patch_id)
        return {
            "status": "promoted",
            "patch_id": patch_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as exc:
        log_step_error(logger, "GOVERNANCE_PROMOTE_ERROR", "Promote patch error for %s: %s", patch_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global _repair_engine
    if _repair_engine:
        await _repair_engine.close()
        log_step_info(logger, "SERVER_SHUTDOWN", "Repair engine closed successfully")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
