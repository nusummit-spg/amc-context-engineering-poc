"""WS3 — FastAPI application: routing, CORS, structured errors, request logging,
startup wiring (DI container, Qdrant collection, Neo4j schema, ingest worker)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import deps
from backend.app.api.routes import docs, graph, ingest, query, status, taxonomy
from backend.app.config import get_settings
from backend.app.core.errors import AppError, app_error_handler
from backend.app.core.logging import RequestLoggingMiddleware, setup_logging
from backend.app.graph.schema import apply_schema
from backend.app.tasks.queue import ingest_queue

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

    container = deps.init_container()
    container.vector.ensure_collection()
    try:
        await apply_schema(container.graph)
    except Exception as exc:
        logger.warning("Could not apply Neo4j schema at startup (is Neo4j up?): %s", exc)

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
            "graph traversal (Neo4j) + scoped vector search (Qdrant) + Claude synthesis."
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

    for router in (query.router, taxonomy.router, graph.router,
                   docs.router, ingest.router, status.router):
        app.include_router(router, prefix="/api")

    return app


app = create_app()
