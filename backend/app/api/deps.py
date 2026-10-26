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
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

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
from app.models.taxonomy import TaxonomyNode, TaxonomyTree

SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"
ALIAS_SEED_PATH = SEEDS_DIR / "entity_aliases.json"
TAXONOMY_SEED_PATH = SEEDS_DIR / "taxonomy.json"


def load_taxonomy() -> TaxonomyTree:
    """Builds the TaxonomyTree from the WS5b seed JSON (nested dict / leaf lists).

    Returns:
        TaxonomyTree: Resulting TaxonomyTree instance.
    """
    if TAXONOMY_SEED_PATH.exists():
        try:
            data = json.loads(TAXONOMY_SEED_PATH.read_text(encoding="utf-8"))
            return TaxonomyTree.build_from_seed(
                data=data,
                version=data.get("version", "1.0"),
                domain=data.get("domain", "AMC"),
            )
        except Exception as exc:
            import logging
            logging.getLogger("app.api.deps").warning("Failed to load taxonomy seed from %s: %s", TAXONOMY_SEED_PATH, exc)
    return TaxonomyTree(
        version="1.0",
        domain="AMC",
        roots=[
            TaxonomyNode(
                node_id="amc",
                name="AMC Root",
                path="AMC",
                level=1,
                parent_path=None
            )
        ]
    )


class Container:
    """Singleton service container, built once in the lifespan handler."""

    def __init__(self) -> None:
        """Initialize a new instance of Container.
        """
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
    """Initialize container.

    Returns:
        Container: Resulting Container instance.
    """
    global _container
    if _container is None:
        _container = Container()
    return _container


def get_container() -> Container:
    """Retrieve container.

    Returns:
        Container: Resulting Container instance.
    """
    global _container
    if _container is None:
        _container = init_container()
    return _container


# ── Auth ─────────────────────────────────────────────────────────────────────
# Deliberately independent of `Container`: login must keep working even if
# Neo4j / the vector store / the LLM provider are unavailable.

_auth_service: "AuthService | None" = None


def get_auth_service() -> "AuthService":
    """FastAPI dependency — returns the process-wide `AuthService` singleton.

    Uses SQL-backed user repository by default (auth_use_database=True).
    Falls back to JSON repository for backward compatibility if needed.

    Returns:
        'AuthService': Resulting 'AuthService' instance.
    """
    global _auth_service
    if _auth_service is None:
        from app.auth.service import AuthService

        settings = get_settings()
        
        # Use database-backed repository by default
        if settings.auth_use_database:
            from app.auth.sql_repository import SqlUserRepository
            from app.core.database import SessionLocal
            repository = SqlUserRepository(session_factory=SessionLocal)
        else:
            # Fallback to JSON repository for backward compatibility
            from app.auth.repository import JSONUserRepository
            repository = JSONUserRepository(Path(settings.auth_users_path)) if settings.auth_users_path else JSONUserRepository()
        
        _auth_service = AuthService(
            repository=repository,
            secret_key=settings.auth_secret_key,
            session_ttl_minutes=settings.auth_session_ttl_minutes,
            session_ttl_minutes_remember=settings.auth_session_ttl_minutes_remember,
        )
    return _auth_service


from app.auth.service import AuthService, AuthenticatedUser


async def get_current_user(
    authorization: Optional[str] = Header(None, description="Bearer token required"),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    """FastAPI dependency that extracts and validates the JWT/session token.
    Enforces mandatory Bearer token authentication (no unverified header fallbacks).

    Raises:
        HTTPException(401): If token is missing, invalid, expired, or revoked
        HTTPException(403): If user account is inactive

    Returns:
        AuthenticatedUser: Verified user identity with username, role, department

    Args:
        authorization (Optional[str]): The authorization.
        auth_service (AuthService): The auth service.
    """
    from app.core.database import SessionLocal
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Pass database session for revocation checking
    db = SessionLocal()
    try:
        user, error = auth_service.resolve_session_with_status(token, db_session=db)
        if error == "inactive_account":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        
        if error == "revoked_token":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user
    finally:
        db.close()


# Type alias for cleaner route signatures
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


async def get_current_user_optional(
    authorization: Optional[str] = Header(None, description="Optional bearer token"),
    auth_service: AuthService = Depends(get_auth_service),
) -> Optional[AuthenticatedUser]:
    """Optional user dependency that returns None instead of raising 401 when unauthenticated.

    Args:
        authorization (Optional[str]): The authorization.
        auth_service (AuthService): The auth service.

    Returns:
        Optional[AuthenticatedUser]: Matching object or record if found, None otherwise.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            user, _ = auth_service.resolve_session_with_status(token)
            if user:
                return user
    return None


OptionalCurrentUser = Annotated[Optional[AuthenticatedUser], Depends(get_current_user_optional)]

