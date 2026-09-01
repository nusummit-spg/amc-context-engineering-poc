# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS3 — FastAPI application: routing, CORS, structured errors, request logging,
startup wiring (DI container, Qdrant collection, Neo4j schema, ingest worker).
Phase 4: Serves React SPA frontend + compliance APIs."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.api import deps
from app.api.routes import admin, chat, compliance, docs, feedback, files, graph, ingest, query, sessions, status, taxonomy
from app.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import RequestLoggingMiddleware, setup_logging
from app.db.feedback import get_feedback_store
from app.graph.schema import apply_schema
from app.tasks.queue import ingest_queue

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

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
        get_feedback_store().init_db()
        logger.info("Feedback SQLite store ready")
    except Exception as exc:
        logger.warning("Could not initialize feedback store: %s", exc)

    ingest_queue.bind_pipeline(container.pipeline)
    ingest_queue.start()
    logger.info("%s started (env=%s)", settings.app_name, settings.environment)

    yield

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
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(AppError, app_error_handler)

    for router in (admin.router, query.router, chat.router, sessions.router, taxonomy.router, graph.router,
                   docs.router, ingest.router, status.router, compliance.router, feedback.router, files.router):
        app.include_router(router, prefix="/api")

    # Also register files router at /files for direct links
    app.include_router(files.router, prefix="")

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
