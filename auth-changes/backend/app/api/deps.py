# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS3 — Dependency injection: wires the whole stack once at startup and
exposes FastAPI dependencies."""
import json
from pathlib import Path

from app.config import get_settings
from app.core.llm import get_llm_client
from app.extraction.classifier import TaxonomyClassifier
from app.extraction.entities import EntityExtractor
from app.extraction.relationships import RelationshipExtractor
from app.extraction.resolver import EntityResolver
from app.graph.client import get_graph_client
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.context import ContextAssembler
from app.retrieval.intent import IntentClassifier
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.retrieval.synthesizer import Synthesizer
from app.retrieval.traversal import GraphTraversal
from app.schemas.taxonomy import TaxonomyNode, TaxonomyTree

SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"
ALIAS_SEED_PATH = SEEDS_DIR / "entity_aliases.json"
TAXONOMY_SEED_PATH = SEEDS_DIR / "taxonomy.json"


def load_taxonomy() -> TaxonomyTree:
    """Builds the TaxonomyTree from the WS5b seed JSON (nested dict / leaf lists)."""
    data = json.loads(TAXONOMY_SEED_PATH.read_text(encoding="utf-8"))
    return TaxonomyTree.build_from_seed(
        data=data,
        version=data.get("version", "1.0"),
        domain=data.get("domain", "AMC"),
    )


class Container:
    """Singleton service container, built once in the lifespan handler."""

    def __init__(self) -> None:
        from app.vector.client import get_vector_store

        self.settings = get_settings()
        self.taxonomy = load_taxonomy()
        self.llm = get_llm_client()
        self.graph = get_graph_client()
        self.vector = get_vector_store()

        self.resolver = EntityResolver(self.llm, ALIAS_SEED_PATH)
        self.classifier = TaxonomyClassifier(self.llm, self.taxonomy)
        self.entity_extractor = EntityExtractor(self.llm)
        self.relationship_extractor = RelationshipExtractor(self.llm)

        self.pipeline = IngestionPipeline(
            vector_store=self.vector,
            graph_client=self.graph,
            classifier=self.classifier,
            entity_extractor=self.entity_extractor,
            resolver=self.resolver,
            relationship_extractor=self.relationship_extractor,
            alias_seed_path=ALIAS_SEED_PATH,
        )

        self.orchestrator = RetrievalOrchestrator(
            intent_classifier=IntentClassifier(self.llm, self.taxonomy),
            resolver=self.resolver,
            traversal=GraphTraversal(self.graph),
            vector_store=self.vector,
            assembler=ContextAssembler(),
            synthesizer=Synthesizer(self.llm),
        )

        from app.compliance.rules_engine import RulesEngine
        from app.compliance.violation_detector import ViolationDetector
        from app.compliance.agents.orchestrator import ComplianceAgentOrchestrator

        self.rules_engine = RulesEngine(self.graph)
        self.violation_detector = ViolationDetector(self.graph, self.rules_engine)
        self.compliance_orchestrator = ComplianceAgentOrchestrator(self.graph, self.rules_engine)



_container: Container | None = None


def init_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def get_container() -> Container:
    if _container is None:
        raise RuntimeError("Container not initialized — app startup did not run")
    return _container


# ── Auth ─────────────────────────────────────────────────────────────────────
# Deliberately independent of `Container`: login must keep working even if
# Neo4j / the vector store / the LLM provider are unavailable.

_auth_service: "AuthService | None" = None


def get_auth_service() -> "AuthService":
    """FastAPI dependency — returns the process-wide `AuthService` singleton."""
    global _auth_service
    if _auth_service is None:
        from app.auth.repository import JSONUserRepository
        from app.auth.service import AuthService

        settings = get_settings()
        repository = JSONUserRepository(Path(settings.auth_users_path)) if settings.auth_users_path else JSONUserRepository()
        _auth_service = AuthService(
            repository=repository,
            secret_key=settings.auth_secret_key,
            session_ttl_minutes=settings.auth_session_ttl_minutes,
            session_ttl_minutes_remember=settings.auth_session_ttl_minutes_remember,
        )
    return _auth_service


# To protect a future route with the same session token used by /api/auth/me,
# depend on `get_auth_service` directly and resolve the bearer token inline:
#
#     from fastapi import Header, Depends
#     from app.api.deps import get_auth_service
#     from app.auth.service import AuthService
#
#     async def my_route(
#         authorization: str | None = Header(default=None),
#         auth_service: AuthService = Depends(get_auth_service),
#     ):
#         token = (authorization or "").removeprefix("Bearer ").strip()
#         user = auth_service.resolve_session(token)
#         ...
#
# Not wired into any existing route yet — the current app gates access
# client-side after login (see api/routes/auth.py + frontend AppState).
