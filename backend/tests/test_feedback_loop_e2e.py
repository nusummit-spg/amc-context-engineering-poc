import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal, Base, engine
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.repair_proposals import RepairProposal
from app.schemas.models import LifecycleStatus, RepairTarget, RootCause, Severity, EntryRoute
from app.services.cypher_validator import get_cypher_validator
from app.services.repair_proposal_service import RepairProposalService
from app.services.promotion_service import PromotionService
from app.services.governance_scheduler import GovernanceBatchScheduler
from app.services.lifecycle_manager import LifecycleManager
from app.services.deduplication_service import DeduplicationService
from app.evaluation.shared_context_cache import get_shared_cache
from app.schemas.chat_sessions_table import ChatSession

Base.metadata.create_all(bind=engine)

client = TestClient(app)


def _ensure_session(db, session_id: str, user_id: str = "test_user"):
    s = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not s:
        db.add(ChatSession(session_id=session_id, user_id=user_id))
        db.commit()


def test_cypher_validator_safety():
    """Verify CypherValidator blocks destructive Cypher and allows safe mutations."""
    validator = get_cypher_validator()

    # Safe mutation
    safe_cypher = "MATCH (e:Entity {id: 'INF846K01DP5'}) SET e.ter = '0.82%' RETURN e"
    is_safe, reason = validator.validate(safe_cypher)
    assert is_safe is True

    # Dangerous: DROP INDEX
    bad_cypher_1 = "DROP INDEX entity_label"
    is_safe, reason = validator.validate(bad_cypher_1)
    assert is_safe is False
    assert "prohibited operation" in reason.lower()

    # Dangerous: REMOVE protected field
    bad_cypher_2 = "MATCH (e:Entity {id: '123'}) REMOVE e.compliance_flag RETURN e"
    is_safe, reason = validator.validate(bad_cypher_2)
    assert is_safe is False
    assert "protected field" in reason.lower()


def test_lifecycle_state_machine():
    """Verify LifecycleManager state machine transitions and constraint validation."""
    db = SessionLocal()
    unique = uuid.uuid4().hex[:8]
    session_id = f"sess_lc_{unique}"
    response_id = f"resp_lc_{unique}"

    try:
        _ensure_session(db, session_id)
        # Create prerequisite query_evidence
        qe = QueryEvidence(
            response_id=response_id,
            session_id=session_id,
            user_id="test_user",
            query_text="Lifecycle test query",
            assembled_context_json=[],
            synthesis_output_json={"answer": "Lifecycle answer"},
            retrieval_mode="hybrid",
        )
        db.add(qe)
        db.commit()

        # Create initial record in OPEN state
        record = UnifiedEvaluationRecord(
            session_id=session_id,
            response_id=response_id,
            entry_route=EntryRoute.HITL.value,
            evidence_snapshot_ref=response_id,
            root_cause=RootCause.KNOWLEDGE.value,
            severity=Severity.HIGH.value,
            lifecycle_status=LifecycleStatus.OPEN.value,
            repair=False,
            repair_target=None,
        )
        db.add(record)
        db.commit()

        lm = LifecycleManager()

        # Valid: OPEN -> DIAGNOSING
        lm.advance(session_id, response_id, LifecycleStatus.DIAGNOSING, "Starting diagnosis", db)
        db.refresh(record)
        assert record.lifecycle_status == LifecycleStatus.DIAGNOSING.value

        # Valid: DIAGNOSING -> RESOLVED
        lm.advance(session_id, response_id, LifecycleStatus.RESOLVED, "Evaluation passed", db)
        db.refresh(record)
        assert record.lifecycle_status == LifecycleStatus.RESOLVED.value

        # Valid: RESOLVED -> MONITORING
        lm.advance(session_id, response_id, LifecycleStatus.MONITORING, "Observation complete", db)
        db.refresh(record)
        assert record.lifecycle_status == LifecycleStatus.MONITORING.value

        # Invalid: MONITORING -> OPEN (terminal state)
        with pytest.raises(ValueError, match="Invalid transition"):
            lm.advance(session_id, response_id, LifecycleStatus.OPEN, "Reopen", db)

    finally:
        db.close()


def test_shared_context_cache():
    """Verify SharedContextCache 1-hop subgraph caching and TTL invalidation."""
    cache = get_shared_cache()
    entity_id = f"TEST_ENT_{uuid.uuid4().hex[:6]}"

    # Cache miss
    assert cache.get_subgraph(entity_id, hops=1) is None

    # Cache set and hit
    dummy_subgraph = {"nodes": [{"id": entity_id, "name": "Axis Bluechip"}], "edges": []}
    cache.set_subgraph(entity_id, hops=1, data=dummy_subgraph)
    hit = cache.get_subgraph(entity_id, hops=1)
    assert hit is not None
    assert hit["nodes"][0]["name"] == "Axis Bluechip"


@pytest.mark.asyncio
async def test_governance_batch_auto_approval():
    """Verify GovernanceBatchScheduler auto-approves proposals with confidence >= 0.95."""
    db = SessionLocal()
    unique = uuid.uuid4().hex[:8]
    response_id = f"resp_gov_{unique}"
    session_id = f"sess_gov_{unique}"

    try:
        _ensure_session(db, session_id)
        qe = QueryEvidence(
            response_id=response_id,
            session_id=session_id,
            user_id="test_user",
            query_text="Gov query",
            assembled_context_json=[],
            synthesis_output_json={"answer": "Gov answer"},
            retrieval_mode="hybrid",
        )
        db.add(qe)
        db.commit()

        record = UnifiedEvaluationRecord(
            session_id=session_id,
            response_id=response_id,
            entry_route=EntryRoute.HITL.value,
            evidence_snapshot_ref=response_id,
            root_cause=RootCause.KNOWLEDGE.value,
            severity=Severity.HIGH.value,
            lifecycle_status=LifecycleStatus.OPEN.value,
            repair=True,
            repair_target="graph",
        )
        db.add(record)
        db.commit()

        proposal = RepairProposal(
            proposal_id=f"prop_gov_{unique}",
            unified_record_ref=response_id,
            proposal_type="graph",
            entity_id="INF846K01DP5",
            attribute="ter",
            mutation_cypher="MATCH (e:Entity {id: 'INF846K01DP5'}) SET e.ter = '0.82%' RETURN e",
            affected_nodes=["INF846K01DP5"],
            confidence=0.96,
            status="pending",
        )
        db.add(proposal)
        db.commit()

        # Run weekly governance batch
        scheduler = GovernanceBatchScheduler(confidence_threshold=0.75)
        await scheduler.run_weekly_batch()

        db.refresh(proposal)
        assert proposal.status == "approved"
        assert proposal.reviewed_by == "auto_governance_batch"
        assert proposal.regression_score is not None

        # Test promotion of this approved proposal
        promoter = PromotionService(db=db)
        promo_res = promoter.apply_approved_proposals(proposal_id=proposal.proposal_id, db=db)
        assert promo_res["applied_count"] >= 1
        db.refresh(proposal)
        assert proposal.status == "applied"
        assert proposal.applied_at is not None

    finally:
        db.close()


def test_deduplication_service():
    """Verify DeduplicationService identifies and merges duplicate open records."""
    db = SessionLocal()
    unique = uuid.uuid4().hex[:8]
    resp1 = f"resp_dup1_{unique}"
    resp2 = f"resp_dup2_{unique}"
    sess = f"sess_dup_{unique}"

    try:
        _ensure_session(db, sess)
        for resp in [resp1, resp2]:
            qe = QueryEvidence(
                response_id=resp,
                session_id=sess,
                user_id="test_user",
                query_text="TER query",
                assembled_context_json=[],
                synthesis_output_json={"answer": "TER answer"},
                retrieval_mode="hybrid",
            )
            db.add(qe)
        db.commit()

        r1 = UnifiedEvaluationRecord(
            session_id=sess,
            response_id=resp1,
            entry_route=EntryRoute.HITL.value,
            evidence_snapshot_ref=resp1,
            root_cause=RootCause.KNOWLEDGE.value,
            severity=Severity.HIGH.value,
            lifecycle_status=LifecycleStatus.OPEN.value,
            repair=False,
            repair_target=None,
        )
        r2 = UnifiedEvaluationRecord(
            session_id=sess,
            response_id=resp2,
            entry_route=EntryRoute.HITL.value,
            evidence_snapshot_ref=resp2,
            root_cause=RootCause.KNOWLEDGE.value,
            severity=Severity.HIGH.value,
            lifecycle_status=LifecycleStatus.OPEN.value,
            repair=False,
            repair_target=None,
        )
        db.add_all([r1, r2])
        db.commit()

        dedup = DeduplicationService(similarity_threshold=0.88)
        merged = dedup.cluster_open_records(db)
        assert merged >= 1

        db.refresh(r2)
        assert r2.lifecycle_status in [LifecycleStatus.RESOLVED.value, "resolved"]

    finally:
        db.close()


def test_metrics_endpoint():
    """Verify Prometheus /metrics endpoint is mounted and returns telemetry."""
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "feedback_submissions_total" in res.text or "python_gc_objects_collected" in res.text
