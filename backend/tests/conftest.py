# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
conftest.py
===========
Centralized pytest configuration and shared fixtures for all tests.

Provides:
- Database session management with proper isolation
- Test data factories for consistent test data creation
- Automatic cleanup and FK constraint satisfaction
- Shared fixtures for repair service tests
"""

import pytest
import uuid
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, SessionLocal
from app.graph.correction_patch_layer import get_correction_patch_layer

logger = logging.getLogger("pytest")


# ────────────────────────────────────────────────────────────────────────────
# Database Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db_engine():
    """
    Create test database engine with in-memory SQLite.
    
    Uses StaticPool to keep connection open for test session.
    Enables FK constraints explicitly (SQLite disables by default).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Enable FK constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Create all tables
    Base.metadata.create_all(engine)
    logger.info("✅ Test database created with FK constraints enabled")
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(engine)
    logger.info("✅ Test database cleaned up")


@pytest.fixture(scope="function")
def db(db_engine):
    """
    Provide a fresh database session for each test.
    
    - Automatically rolls back changes after test
    - Ensures complete isolation between tests
    - Prevents data pollution
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)(bind=connection)
    
    yield session
    
    # Rollback all changes
    try:
        transaction.rollback()
    except Exception as exc:
        logger.debug("Transaction rollback error (expected): %s", exc)
    
    session.close()
    connection.close()


# ────────────────────────────────────────────────────────────────────────────
# Test Data Factory
# ────────────────────────────────────────────────────────────────────────────

class TestDataFactory:
    """Factory for creating consistent test data with FK constraint satisfaction."""
    
    def __init__(self, session: Session):
        self.db = session
    
    def create_evidence(
        self,
        response_id: str,
        session_id: str = None,
        query_text: str = "Test query",
        retrieval_mode: str = "contextgraph",
        assembled_context_json: dict = None,
        synthesis_output_json: dict = None,
    ):
        """
        Create a QueryEvidence record.
        
        Args:
            response_id: Response ID (PK)
            session_id: Session ID (auto-generated if None)
            query_text: Query text
            retrieval_mode: Retrieval mode (default: contextgraph)
            assembled_context_json: Context (auto-generated if None)
            synthesis_output_json: Response (auto-generated if None)
        
        Returns:
            QueryEvidence object
        """
        from app.schemas.query_evidence_table import QueryEvidence
        
        if session_id is None:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"
        
        if assembled_context_json is None:
            assembled_context_json = {"context": "Test context"}
        
        if synthesis_output_json is None:
            synthesis_output_json = {"response": "Test response"}
        
        evidence = QueryEvidence(
            response_id=response_id,
            session_id=session_id,
            query_text=query_text,
            retrieval_mode=retrieval_mode,
            assembled_context_json=assembled_context_json,
            synthesis_output_json=synthesis_output_json,
        )
        
        self.db.add(evidence)
        self.db.flush()  # Flush to DB without committing
        logger.debug("✅ Created QueryEvidence: %s", response_id)
        return evidence
    
    def create_unified_record(
        self,
        response_id: str,
        session_id: str = None,
        repair: bool = True,
        root_cause: str = None,
        severity: str = None,
        dissatisfaction_evidence: dict = None,
        **kwargs
    ):
        """
        Create a UnifiedEvaluationRecord with proper FK constraints.
        
        Automatically creates QueryEvidence first to satisfy FK.
        
        Args:
            response_id: Response ID (PK part)
            session_id: Session ID (auto-generated if None)
            repair: Whether repair is needed (default: True)
            root_cause: Root cause (default: knowledge)
            severity: Severity level (default: high)
            dissatisfaction_evidence: Evidence JSON
            **kwargs: Additional fields
        
        Returns:
            UnifiedEvaluationRecord object
        """
        from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
        from app.schemas.models import (
            EntryRoute,
            RootCause,
            Severity,
            LifecycleStatus,
            RepairTarget,
            AdjudicationVerdict,
        )
        
        if session_id is None:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Create QueryEvidence first (FK requirement)
        self.create_evidence(response_id, session_id=session_id)
        
        # Step 2: Create UnifiedEvaluationRecord
        record = UnifiedEvaluationRecord(
            session_id=session_id,
            response_id=response_id,
            entry_route=EntryRoute.HITL,
            evidence_snapshot_ref=response_id,  # FK to QueryEvidence
            root_cause=RootCause.KNOWLEDGE if root_cause is None else RootCause(root_cause),
            severity=Severity.HIGH if severity is None else Severity(severity),
            lifecycle_status=LifecycleStatus.OPEN,
            repair=repair,
            repair_target=RepairTarget.VECTOR if repair else None,
            dissatisfaction_evidence_json=dissatisfaction_evidence or {},
            adjudication_verdict=AdjudicationVerdict.VALID if kwargs.get("adjudication_verdict") is None else kwargs.get("adjudication_verdict"),
            adjudication_confidence=0.95,
            **{k: v for k, v in kwargs.items() if k not in ["adjudication_verdict"]}
        )
        
        self.db.add(record)
        self.db.flush()
        logger.debug("✅ Created UnifiedEvaluationRecord: %s (repair=%s)", response_id, repair)
        return record


@pytest.fixture(scope="function")
def test_factory(db: Session) -> TestDataFactory:
    """Provide test data factory for consistent test data creation."""
    factory = TestDataFactory(db)
    logger.debug("✅ Test data factory initialized")
    yield factory


# ────────────────────────────────────────────────────────────────────────────
# Patch Layer Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def clean_patch_layer():
    """
    Provide a clean patch layer for each test.
    
    - Clears all patches before test
    - Clears all patches after test
    - Ensures test isolation
    """
    layer = get_correction_patch_layer()
    layer.clear_all()
    logger.debug("✅ Patch layer cleared (pre-test)")
    
    yield layer
    
    layer.clear_all()
    logger.debug("✅ Patch layer cleared (post-test)")


# ────────────────────────────────────────────────────────────────────────────
# Pytest Configuration
# ────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow"
    )


@pytest.fixture(scope="session", autouse=True)
def setup_test_logging():
    """Setup logging for tests."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger.info("=" * 80)
    logger.info("🧪 PYTEST SESSION STARTED")
    logger.info("=" * 80)
    
    yield
    
    logger.info("=" * 80)
    logger.info("✅ PYTEST SESSION COMPLETED")
    logger.info("=" * 80)
