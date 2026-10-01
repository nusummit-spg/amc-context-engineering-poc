# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

"""WS3 — FastAPI application: routing, CORS, structured errors, request logging,
startup wiring (DI container, Qdrant collection, Neo4j schema, ingest worker).
Phase 4: Serves React SPA frontend + compliance APIs."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.api import deps
from app.api.middleware import RateLimitMiddleware, ValidationMiddleware
from app.api.routes import (
    admin, auth, chat, compliance, docs, feedback, files, governance, graph, ingest, metrics, query, review_queue, sessions, status, taxonomy
)
from app.config import get_settings
from app.core.errors import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import RequestLoggingMiddleware, setup_logging

from app.graph.schema import apply_schema
from app.tasks.queue import ingest_queue
from app.tasks.scheduler import get_scheduler
from app.core.database import init_db
from app.api.routes import feedback_evaluation
from app.api.routes import audit


logger = logging.getLogger("app")



@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        log_file=settings.log_file,
        enable_file_logging=settings.enable_file_logging,
    )

    # Initialize SQLite database
    # Creates the tables if they don't exist, and applies any schema migrations
    init_db()

    container = deps.init_container()
    # Fast check if Neo4j is available before applying schema/rules
    neo4j_up = False
    try:
        driver = container.graph._get_driver()
        await asyncio.wait_for(driver.verify_connectivity(), timeout=5.0)
        neo4j_up = True
        logger.info("Connected to Neo4j successfully (bolt://localhost:7687)")
    except Exception as exc:
        logger.warning("Neo4j not reachable at startup (%s) - running in vector/FAISS fallback mode", exc)

    if neo4j_up:
        try:
            await apply_schema(container.graph)
        except Exception as exc:
            logger.warning("Could not apply Neo4j schema at startup: %s", exc)

        # Deploy AMC Compliance Graph Schema
        try:
            from app.graph.compliance_schema import deploy_compliance_schema
            await deploy_compliance_schema(container.graph)
        except Exception as exc:
            logger.warning("Could not deploy compliance schema at startup: %s", exc)

        # Seed AMC Compliance Rules & Regulations
        try:
            from app.ingestion.compliance_rules_ingester import seed_compliance_data
            await seed_compliance_data(container.graph)
            await container.rules_engine.load_rules()
            logger.info("Compliance rules and fund schemes initialized successfully")
        except Exception as exc:
            logger.warning("Could not seed compliance rules at startup: %s", exc)

    # Eagerly load the FAISS index, the sentence-transformer embedder, and the
    # cross-encoder reranker — all lazy singletons only triggered inside
    # .retrieve(). Without this, the model-load cost lands silently on
    # whichever real request happens to be first after a deploy/restart, and
    # the /docs health check (which never touches the store) reports
    # "healthy" long before the app can actually serve a query at normal
    # speed. rerank=True here forces both models to load in one warmup call.
    try:
        store = query._store()
        store.retrieve("startup warmup", top_k_children=1, rerank=True)
        logger.info("FAISS store + embedder + reranker warmed up at startup")
    except Exception as exc:
        logger.warning("Could not warm up FAISS store at startup: %s", exc)

    # Pre-warm semantic cache and entity resolver models
    try:
        from app.engine import config as engine_config
        if engine_config.ENABLE_SEMANTIC_CACHE_WARMUP:
            from app.engine.semantic_cache import get_cache
            cache = get_cache()
            logger.info("Semantic cache initialized and warmed up at startup")
    except Exception as exc:
        logger.warning("Could not initialize semantic cache at startup: %s", exc)

    # Initialize feedback store schema
    try:
        logger.info("Feedback store now uses centralized data.db (single source of truth)")
    except Exception as exc:
        logger.warning("Could not initialize feedback store: %s", exc)

    # Start autonomous background scheduler
    scheduler = get_scheduler()
    try:
        scheduler.start()
        logger.info("Background TaskScheduler wired into FastAPI lifespan")
    except Exception as exc:
        logger.warning("Could not start background scheduler: %s", exc)

    # Initialize modular packages (amc-feedback-loop & amc-repair-engine)
    try:
        from app.core.adapters import get_feedback_loop, get_repair_engine
        app.state.feedback_loop = get_feedback_loop()
        app.state.repair_engine = get_repair_engine()
        logger.info("Modular packages (amc-feedback-loop, amc-repair-engine) wired into app.state")
    except Exception as exc:
        logger.warning("Could not initialize modular packages: %s", exc)

    # Start passive feedback background tasks
    if getattr(settings, "passive_feedback_enabled", True):
        try:
            from app.feedback.session_manager import start_session_manager
            from app.feedback.timeout_processor import start_timeout_processor
            await start_session_manager()
            await start_timeout_processor()
            logger.info("Passive feedback background tasks started")
        except Exception as exc:
            logger.warning("Could not start passive feedback tasks: %s", exc)

    ingest_queue.bind_pipeline(container.pipeline)
    ingest_queue.start()
    logger.info("%s started (env=%s)", settings.app_name, settings.environment)

    yield

    # Stop passive feedback background tasks & timers
    try:
        from app.feedback.timeout_processor import stop_timeout_processor
        from app.feedback.session_manager import stop_session_manager
        from app.feedback.feedback_timer import get_feedback_timer_manager
        await stop_timeout_processor()
        await stop_session_manager()
        await get_feedback_timer_manager().stop_all()
        logger.info("Passive feedback background tasks and timers stopped")
    except Exception as exc:
        logger.warning("Error stopping passive feedback tasks or timers: %s", exc)

    try:
        if hasattr(app.state, "feedback_loop") and app.state.feedback_loop:
            await app.state.feedback_loop.close()
        if hasattr(app.state, "repair_engine") and app.state.repair_engine:
            await app.state.repair_engine.close()
    except Exception as exc:
        logger.warning("Error closing modular package adapters: %s", exc)

    try:
        scheduler.stop()
    except Exception as exc:
        logger.warning("Error stopping scheduler: %s", exc)

    await ingest_queue.stop()
    await container.graph.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Taxonomy-scoped hybrid retrieval backend for the AMC demo: "
            "graph traversal (Neo4j) + scoped vector search (FAISS) + Groq synthesis."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ValidationMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    for router in (auth.router, admin.router, query.router, chat.router, sessions.router, taxonomy.router, graph.router,
                   docs.router, ingest.router, status.router, compliance.router, feedback.router, review_queue.router, governance.router, files.router, metrics.router):
        app.include_router(router, prefix="/api")


    # Direct response quality alias endpoint
    @app.get("/api/responses/{response_id}/quality-score", tags=["feedback"])
    async def get_response_quality_direct(response_id: str):
        from app.compliance.metrics_store import get_metrics_store
        return get_metrics_store().get_response_quality(response_id=response_id)

    @app.get("/health", tags=["status"])
    @app.get("/api/health", tags=["status"])
    async def root_health(container: deps.Container = Depends(deps.get_container)):
        from app.api.routes.status import health as status_health
        return await status_health(container=container)

    @app.get("/api/health/passive-feedback", tags=["status"])
    async def passive_feedback_health():
        """Health check and status inspection for the passive feedback system."""
        from app.feedback.session_manager import get_session_manager
        sm = get_session_manager()
        return {
            "status": "healthy" if settings.passive_feedback_enabled else "disabled",
            "session_count": len(sm._sessions),
            "timeout_seconds": sm.timeout_seconds,
            "cleanup_interval": sm.cleanup_interval,
            "enabled": settings.passive_feedback_enabled,
        }

    @app.get("/metrics/dashboard", tags=["monitoring"], include_in_schema=False)
    async def root_metrics_dashboard():
        from app.api.routes.metrics import get_dashboard
        return await get_dashboard()

    # Also register files router at /files for direct links
    app.include_router(files.router, prefix="")


    app.include_router(feedback_evaluation.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    
    # Phase 4: Serve React frontend (check mf-context-engine/dist first, then frontend/dist)
    mf_engine_dir = Path(__file__).parent.parent.parent / "mf-context-engine" / "dist"
    legacy_frontend_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"
    frontend_dir = mf_engine_dir if mf_engine_dir.exists() else legacy_frontend_dir
    
    if frontend_dir.exists():
        logger.info(f"React frontend found at {frontend_dir}, mounting static files")
        
        index_html = frontend_dir / "index.html"

        # Serve index.html with no-cache headers so browser always fetches the
        # latest HTML (which has up-to-date hashed JS/CSS filenames after each build).
        # This prevents the "blank white page" caused by stale cached index.html
        # referencing old asset hashes that no longer exist on disk.
        @app.get("/", include_in_schema=False)
        async def serve_index():
            return FileResponse(
                index_html,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        # Also handle SPA client-side routes (e.g. /chat, /admin) — return index.html
        # so the React Router can take over. This avoids 404s on direct URL navigation.
        # NOTE: FastAPI matches more-specific routes (like /api/...) BEFORE this catch-all,
        # so API endpoints are not shadowed by this handler.
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/") or full_path == "api":
                return JSONResponse(status_code=404, content={"detail": f"API endpoint /{full_path} not found"})
            # Serve actual files from the frontend dist directory if they exist
            file_path = frontend_dir / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            # Fall back to index.html for all SPA client-side routes
            # (API routes are matched before this catch-all since they're registered earlier)
            return FileResponse(
                index_html,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        # Mount assets directory — these are served by both the serve_spa route above
        # (via file_path.exists() check) and this explicit mount for efficiency
        assets_dir = frontend_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        
        # Mount remaining static files (favicon, icons, etc.)
        app.mount("/static-files", StaticFiles(directory=frontend_dir), name="static-files")
    else:
        logger.warning(f"React frontend not found at {frontend_dir}. To use React frontend:")
        logger.warning("  1. cd mf-context-engine && npm install && npm run build")
        logger.warning("  2. Restart backend server")
        logger.warning("For now, API-only mode enabled. Visit http://localhost:8000/docs for API docs.")

    return app
    
app = create_app()
