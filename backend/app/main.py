"""WS3 — FastAPI application: routing, CORS, structured errors, request logging,
startup wiring (DI container, Qdrant collection, Neo4j schema, ingest worker)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import deps
from app.api.routes import chat, docs, graph, ingest, query, status, taxonomy
from app.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import RequestLoggingMiddleware, setup_logging
from app.graph.schema import apply_schema
from app.tasks.queue import ingest_queue

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

    for router in (query.router, chat.router, taxonomy.router, graph.router,
                   docs.router, ingest.router, status.router):
        app.include_router(router, prefix="/api")

    return app


app = create_app()
