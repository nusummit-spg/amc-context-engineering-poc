"""Unit tests validating the 3 fixes for duplicate repairs, skeleton enrichment, and reference backfilling."""

import uuid
import pytest
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.repair_proposals import RepairProposal
from app.schemas.models import (
    EntryRoute,
    RootCause,
    Severity,
    LifecycleStatus,
    RepairTarget,
    _now_iso,
)
from app.feedback.metrics_enrichment import get_metrics_enricher
from app.adapters.feedback_adapters import AMCDatabaseAdapter
from app.services.repair_proposal_service import RepairProposalService
from app.graph.correction_patch_layer import get_correction_patch_layer
import feedback_loop.domain_models as dm


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    try:
        session.rollback()
    except Exception:
        pass
    finally:
        session.close()


def create_test_evidence(db: Session, response_id: str, session_id: str) -> None:
    existing_sess = db.query(ChatSession).filter_by(session_id=session_id).first()
    if not existing_sess:
        chat_sess = ChatSession(session_id=session_id, user_id="test_user")
        db.add(chat_sess)
        db.flush()
    evidence = QueryEvidence(
        response_id=response_id,
        session_id=session_id,
        user_id="test_user",
        query_text="Test query",
        retrieval_mode="contextgraph",
        assembled_context_json={"context": "Test context"},
        synthesis_output_json={"response": "Test response"},
    )
    db.add(evidence)
    db.commit()


def test_fix1_metrics_enrichment_list_handling(db: Session):
    """Verify that skeleton record with empty list selected_categories enriches without error."""
    resp_id = f"resp_test1_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_test1_{uuid.uuid4().hex[:8]}"
    fb_id = f"fb_{uuid.uuid4().hex[:8]}"

    create_test_evidence(db, resp_id, sess_id)

    feedback = ResponseFeedback(
        feedback_id=fb_id,
        response_id=resp_id,
        interaction_id=f"int_{uuid.uuid4().hex[:8]}",
        session_id=sess_id,
        turn_number=1,
        selected_categories=[],  # List type
        feedback_text=None,
        automated_category=None,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    db.add(feedback)
    db.commit()

    enricher = get_metrics_enricher()
    import asyncio
    success = asyncio.run(enricher.enrich_response(sess_id, resp_id, db=db))
    assert success is True

    # Refresh feedback
    db.refresh(feedback)
    assert feedback.automated_category in ("auto_evaluated", "implicit_positive")
    assert feedback.automated_confidence is not None


def test_fix2_write_unified_record_backfills_existing(db: Session):
    """Verify AMCDatabaseAdapter.write_unified_record backfills unified_record_ref on existing records."""
    resp_id = f"resp_test2_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_test2_{uuid.uuid4().hex[:8]}"
    fb_id = f"fb_{uuid.uuid4().hex[:8]}"

    # 1. Create QueryEvidence and ResponseFeedback without unified_record_ref
    create_test_evidence(db, resp_id, sess_id)

    fb = ResponseFeedback(
        feedback_id=fb_id,
        response_id=resp_id,
        interaction_id=f"int_{uuid.uuid4().hex[:8]}",
        session_id=sess_id,
        turn_number=1,
        selected_categories=[],
        feedback_text="Discrepancy in scheme returns",
        unified_record_ref=None,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    # 2. Existing UnifiedEvaluationRecord already in database
    uer = UnifiedEvaluationRecord(
        session_id=sess_id,
        response_id=resp_id,
        entry_route=EntryRoute.HITL,
        evidence_snapshot_ref=resp_id,
        root_cause=RootCause.KNOWLEDGE,
        severity=Severity.HIGH,
        lifecycle_status=LifecycleStatus.OPEN,
        repair=True,
        repair_target=RepairTarget.GRAPH,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    db.add_all([fb, uer])
    db.commit()

    adapter = AMCDatabaseAdapter(session_factory=SessionLocal)
    domain_rec = dm.UnifiedEvaluationRecord(
        session_id=sess_id,
        response_id=resp_id,
        entry_route=dm.EntryRoute.HITL,
        feedback_ref=fb_id,
        evidence_snapshot_ref=resp_id,
        root_cause=dm.RootCause.KNOWLEDGE,
        severity=dm.Severity.HIGH,
        repair=True,
        repair_target=dm.RepairTarget.GRAPH,
    )

    # Calling write_unified_record when UER already exists
    adapter.write_unified_record(domain_rec)

    # Verify that backfill occurred
    db.refresh(fb)
    qe = db.query(QueryEvidence).filter(QueryEvidence.response_id == resp_id).first()
    assert fb.unified_record_ref == resp_id
    assert qe.unified_record_ref == resp_id


def test_fix3_proposal_and_patch_idempotency(db: Session):
    """Verify that repair proposal and patch layer operations are idempotent."""
    resp_id = f"resp_test3_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_test3_{uuid.uuid4().hex[:8]}"

    create_test_evidence(db, resp_id, sess_id)

    uer = UnifiedEvaluationRecord(
        session_id=sess_id,
        response_id=resp_id,
        entry_route=EntryRoute.HITL,
        evidence_snapshot_ref=resp_id,
        root_cause=RootCause.KNOWLEDGE,
        severity=Severity.HIGH,
        lifecycle_status=LifecycleStatus.OPEN,
        repair=True,
        repair_target=RepairTarget.GRAPH,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    db.add(uer)
    db.commit()

    # 1. Test RepairProposalService deduplication
    proposal_svc = RepairProposalService()
    prop1 = proposal_svc.create_proposal_from_record(uer, db, is_approved=True)
    prop2 = proposal_svc.create_proposal_from_record(uer, db, is_approved=True)

    assert prop1.proposal_id == prop2.proposal_id
    proposals_count = db.query(RepairProposal).filter(RepairProposal.unified_record_ref == resp_id).count()
    assert proposals_count == 1

    # 2. Test CorrectionPatchLayer deduplication
    patch_layer = get_correction_patch_layer()
    entity_id = f"TEST_FUND_{uuid.uuid4().hex[:6]}"
    attr = "expense_ratio"

    res1 = patch_layer.add_correction(
        entity_id=entity_id,
        attribute=attr,
        canonical_value="1.20",
        corrected_value="0.95",
        confidence=0.98,
        approved=False,
    )
    assert res1["status"] in ("created", "reused")

    # Adding exact duplicate patch
    res2 = patch_layer.add_correction(
        entity_id=entity_id,
        attribute=attr,
        canonical_value="1.20",
        corrected_value="0.95",
        confidence=0.98,
        approved=False,
    )
    assert res2["status"] == "reused"
    assert res1["patch_id"] == res2["patch_id"]


@pytest.mark.asyncio
async def test_fix_batch_consumer_verdict_constraint(db: Session, monkeypatch):
    """Verify that BatchEvaluationConsumer normalizes 'PASS' into 'valid' without violating ck_unified_adjudication_verdict."""
    from app.evaluation.batch_consumer import BatchEvaluationConsumer
    resp_id = f"resp_batch_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_batch_{uuid.uuid4().hex[:8]}"

    create_test_evidence(db, resp_id, sess_id)

    uer = UnifiedEvaluationRecord(
        session_id=sess_id,
        response_id=resp_id,
        entry_route=EntryRoute.AUTOMATIC,
        evidence_snapshot_ref=resp_id,
        root_cause=RootCause.KNOWLEDGE,
        severity=Severity.HIGH,
        lifecycle_status=LifecycleStatus.OPEN,
        repair=True,
        repair_target=RepairTarget.GRAPH,
        deterministic_results=None,
        created_at="1999-01-01T00:00:00+00:00",
        updated_at=_now_iso(),
    )
    db.add(uer)
    db.commit()

    consumer = BatchEvaluationConsumer(batch_size=50)

    # Mock router.evaluate to return 'PASS' like Tier 1A / Tier 3 does
    def mock_evaluate(response_id, evidence_pack):
        return {
            "verdict": "PASS",
            "confidence": 0.95,
            "rule_results": [{"rule": "test", "verdict": "PASS"}],
            "gnn_plausibility_score": 0.8,
            "nli_result": {"label": "entailment"},
            "critic_result": {"severity": "safe"},
        }

    monkeypatch.setattr(consumer.router, "evaluate", mock_evaluate)

    processed = await consumer.process_batch(db=db)
    assert processed >= 1

    db.refresh(uer)
    assert uer.adjudication_verdict == "valid"
    assert uer.lifecycle_status in ("resolved", LifecycleStatus.RESOLVED)
