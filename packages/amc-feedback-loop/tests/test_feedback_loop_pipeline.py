"""
Tests for feedback_loop core pipeline and end-to-end orchestration.
"""
from datetime import datetime, timezone
import pytest

from feedback_loop import FeedbackLoopConfig, start_feedback_loop
from feedback_loop.adapters import InMemoryDatabaseAdapter, InMemoryEvidenceAdapter
from feedback_loop.domain_models import (
    EvidenceChunk,
    EvidenceSnapshot,
    FeedbackRecord,
    FeedbackSource,
    FeedbackType,
    FollowUpQuery,
    IngestionStatus,
    RatingType,
    RootCause,
    Severity,
    EntryRoute,
)
from feedback_loop.ingest import IngestService


@pytest.fixture
def test_setup():
    """Test setup.

    Returns:
        Result of the operation.
    """
    config = FeedbackLoopConfig()
    db = InMemoryDatabaseAdapter()
    evidence = InMemoryEvidenceAdapter()
    return config, db, evidence


def test_active_feedback_pipeline_model_root_cause(test_setup):
    """Test active feedback pipeline model root cause.

    Args:
        test_setup: The test setup.
    """
    config, db, evidence = test_setup
    feedback_id = "fb_001"
    session_id = "sess_001"
    response_id = "resp_001"

    # Seed feedback record
    sample_feedback = FeedbackRecord(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
        entity_name="HDFC Top 100 Fund",
        notes="NAV is wrong. Actual NAV is 150.25 not 120.00",
        ingestion_status=IngestionStatus.PENDING,
    )
    db.seed_feedback(sample_feedback)

    # Seed evidence
    sample_snapshot = EvidenceSnapshot(
        response_id=response_id,
        original_query="What is the NAV of HDFC Top 100 Fund?",
        response_text="The NAV is 120.00.",
        entity_name="HDFC Top 100 Fund",
        evidence_selected=[
            EvidenceChunk(
                chunk_id="chk_01",
                value="150.25",
                source_version="v1",
                content="HDFC Top 100 Fund NAV is 150.25.",
            )
        ],
    )
    evidence.seed_snapshot(sample_snapshot)

    # Trigger feedback loop
    success = start_feedback_loop(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        source="active",
        config=config,
        db=db,
        evidence_adapter=evidence,
    )

    assert success is True
    assert db.unified_record_exists(response_id) is True

    record = db.fetch_feedback_record(feedback_id)
    assert record.ingestion_status == IngestionStatus.SENT

    eval_rec = db.fetch_unified_record(response_id)
    assert eval_rec is not None
    assert eval_rec.response_id == response_id
    assert eval_rec.entry_route == EntryRoute.HITL
    assert eval_rec.root_cause == RootCause.MODEL
    assert eval_rec.severity == Severity.HIGH


def test_active_feedback_compliance_root_cause(test_setup):
    """Test active feedback compliance root cause.

    Args:
        test_setup: The test setup.
    """
    config, db, evidence = test_setup
    feedback_id = "fb_comp_01"
    session_id = "sess_comp_01"
    response_id = "resp_comp_01"

    sample_feedback = FeedbackRecord(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
        entity_name="SEBI Regulation Fund",
        notes="SEBI regulation statutory compliance breach here.",
        ingestion_status=IngestionStatus.PENDING,
    )
    db.seed_feedback(sample_feedback)

    sample_snapshot = EvidenceSnapshot(
        response_id=response_id,
        original_query="Does this follow SEBI guidelines?",
        response_text="Yes, SEBI compliance is verified.",
        entity_name="SEBI Regulation Fund",
        evidence_selected=[
            EvidenceChunk(
                chunk_id="chk_comp",
                value="Compliance guidelines",
                source_version="v1",
                content="SEBI statutory limits.",
            )
        ],
    )
    evidence.seed_snapshot(sample_snapshot)

    success = start_feedback_loop(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        source="active",
        config=config,
        db=db,
        evidence_adapter=evidence,
    )

    assert success is True
    eval_rec = db.fetch_unified_record(response_id)
    assert eval_rec is not None
    assert eval_rec.root_cause == RootCause.COMPLIANCE
    assert eval_rec.severity == Severity.CRITICAL


def test_passive_feedback_dissatisfaction_conversion(test_setup):
    """Test passive feedback dissatisfaction conversion.

    Args:
        test_setup: The test setup.
    """
    config, db, evidence = test_setup
    feedback_id = "fb_pass_01"
    session_id = "sess_pass_01"
    response_id = "resp_pass_01"

    # Passive feedback has no user notes
    sample_feedback = FeedbackRecord(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        rating=RatingType.UNRATED,
        feedback_type=FeedbackType.SILENT_ACCEPT,
        source=FeedbackSource.PASSIVE,
        received_at=datetime.now(timezone.utc),
        entity_name="Nippon India Small Cap",
        notes=None,
        ingestion_status=IngestionStatus.PENDING,
    )
    db.seed_feedback(sample_feedback)

    sample_snapshot = EvidenceSnapshot(
        response_id=response_id,
        original_query="What is the AUM of Nippon India Small Cap?",
        response_text="The AUM is 35000 Cr.",
        entity_name="Nippon India Small Cap",
        evidence_selected=[],
    )
    evidence.seed_snapshot(sample_snapshot)

    # Seed follow-up activity that triggers dissatisfaction
    # 1. High cosine similarity / re-query
    # 2. Correction pattern keywords ("No, that's wrong")
    evidence.seed_followups(
        session_id=session_id,
        queries=[
            FollowUpQuery(
                query_id="q_followup_1",
                text="No that's wrong, what is the actual AUM of Nippon India Small Cap?",
                created_at=datetime.now(timezone.utc),
            )
        ],
    )

    success = start_feedback_loop(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        source="passive",
        config=config,
        db=db,
        evidence_adapter=evidence,
    )

    assert success is True
    eval_rec = db.fetch_unified_record(response_id)
    assert eval_rec is not None
    assert eval_rec.entry_route == EntryRoute.DISSATISFACTION_CONVERTED


def test_duplicate_response_skipping(test_setup):
    """Test duplicate response skipping.

    Args:
        test_setup: The test setup.
    """
    config, db, evidence = test_setup
    feedback_id_1 = "fb_dup_01"
    feedback_id_2 = "fb_dup_02"
    session_id = "sess_dup"
    response_id = "resp_dup"

    fb1 = FeedbackRecord(
        feedback_id=feedback_id_1,
        session_id=session_id,
        response_id=response_id,
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
        notes="Wrong number",
    )
    db.seed_feedback(fb1)

    fb2 = FeedbackRecord(
        feedback_id=feedback_id_2,
        session_id=session_id,
        response_id=response_id,
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
        notes="Still wrong number",
    )
    db.seed_feedback(fb2)

    evidence.seed_snapshot(
        EvidenceSnapshot(
            response_id=response_id,
            original_query="What is TER?",
            response_text="TER is 1.0%",
        )
    )

    # First ingest succeeds
    res1 = start_feedback_loop(
        feedback_id=feedback_id_1,
        session_id=session_id,
        response_id=response_id,
        source="active",
        config=config,
        db=db,
        evidence_adapter=evidence,
    )
    assert res1 is True

    # Second ingest on the same response_id is identified as already processed / duplicate
    res2 = start_feedback_loop(
        feedback_id=feedback_id_2,
        session_id=session_id,
        response_id=response_id,
        source="active",
        config=config,
        db=db,
        evidence_adapter=evidence,
    )
    assert res2 is False


def test_retry_sweep(test_setup):
    """Test retry sweep.

    Args:
        test_setup: The test setup.
    """
    config, db, evidence = test_setup
    feedback_id = "fb_retry_01"
    session_id = "sess_retry_01"
    response_id = "resp_retry_01"

    # Seed pending record
    sample_feedback = FeedbackRecord(
        feedback_id=feedback_id,
        session_id=session_id,
        response_id=response_id,
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
        notes="Wrong info",
        ingestion_status=IngestionStatus.PENDING,
    )
    db.seed_feedback(sample_feedback)

    evidence.seed_snapshot(
        EvidenceSnapshot(
            response_id=response_id,
            original_query="Test query",
            response_text="Test response",
        )
    )

    ingest_svc = IngestService(config, db, evidence)
    summary = ingest_svc.retry_sweep(older_than_minutes=0)

    assert summary["attempted"] == 1
    assert summary["succeeded"] == 1
    assert summary["failed"] == 0
    assert db.unified_record_exists(response_id) is True
