"""
Unit tests for feedback_loop database and evidence adapters.
"""
from datetime import datetime, timezone
import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from feedback_loop.adapters.db import InMemoryDatabaseAdapter
from feedback_loop.adapters.evidence import InMemoryEvidenceAdapter
from feedback_loop.adapters.sqlite.db_adapter import SQLiteDatabaseAdapter
from feedback_loop.adapters.sqlite.evidence_adapter import SQLiteEvidenceAdapter
from feedback_loop.domain_models import (
    EvidenceChunk,
    EvidenceSnapshot,
    FeedbackRecord,
    FeedbackSource,
    FeedbackType,
    FollowUpQuery,
    IngestionStatus,
    RatingType,
    UnifiedEvaluationRecord,
    EntryRoute,
    RootCause,
    Severity,
)
from feedback_loop.models import (
    Base,
    ResponseFeedback as ORM_ResponseFeedback,
    QueryEvidence as ORM_QueryEvidence,
    UnifiedEvaluationRecord as ORM_UnifiedEvaluationRecord,
)


def test_in_memory_database_adapter():
    """Test in memory database adapter.
    """
    adapter = InMemoryDatabaseAdapter()

    row = FeedbackRecord(
        feedback_id="fb_mem_1",
        session_id="s1",
        response_id="r1",
        rating=RatingType.POSITIVE,
        feedback_type=FeedbackType.OTHER,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
    )
    adapter.seed_feedback(row)

    fetched = adapter.fetch_feedback_record("fb_mem_1")
    assert fetched.feedback_id == "fb_mem_1"

    # Status update
    adapter.update_ingestion_status("fb_mem_1", IngestionStatus.SENT)
    updated = adapter.fetch_feedback_record("fb_mem_1")
    assert updated.ingestion_status == IngestionStatus.SENT

    # Write unified record
    eval_rec = UnifiedEvaluationRecord(
        session_id="s1",
        response_id="r1",
        entry_route=EntryRoute.HITL,
        evidence_snapshot_ref="r1",
        root_cause=RootCause.MODEL,
        severity=Severity.MEDIUM,
    )
    adapter.write_unified_record(eval_rec)
    assert adapter.unified_record_exists("r1") is True
    assert adapter.fetch_unified_record("r1") is not None
    assert len(adapter.get_all_unified()) == 1


def test_in_memory_evidence_adapter():
    """Test in memory evidence adapter.
    """
    adapter = InMemoryEvidenceAdapter()

    snapshot = EvidenceSnapshot(
        response_id="r_ev_1",
        original_query="What is TER?",
        response_text="0.5%",
    )
    adapter.seed_snapshot(snapshot)

    assert adapter.validate_response_exists("r_ev_1") is True
    assert adapter.validate_response_exists("unknown") is False

    fetched_snap = adapter.get_evidence_snapshot("r_ev_1")
    assert fetched_snap.original_query == "What is TER?"

    # Follow-ups
    queries = [
        FollowUpQuery(query_id="q1", text="Follow up query", created_at=datetime.now(timezone.utc))
    ]
    adapter.seed_followups("sess_1", queries)
    assert len(adapter.get_followup_activity("sess_1", "r_ev_1", window_minutes=5)) == 1


def test_sqlite_adapters_roundtrip():
    """Test sqlite adapters roundtrip.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"

    try:
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            # Seed ORM Feedback
            orm_fb = ORM_ResponseFeedback(
                feedback_id="fb_sql_1",
                interaction_id="int_sql_1",
                actor_id="user_01",
                session_id="sess_sql_1",
                response_id="resp_sql_1",
                turn_number=1,
                selected_categories=["F02"],
                feedback_text="Exit load is 1% not 0%",
                actor_role="user",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(orm_fb)

            # Seed ORM Evidence
            orm_qe = ORM_QueryEvidence(
                response_id="resp_sql_1",
                session_id="sess_sql_1",
                query_text="What is the exit load?",
                assembled_context_json=[
                    {"chunk_id": "c1", "value": "1%", "content": "Exit load is 1%."}
                ],
                synthesis_output_json={"answer": "Exit load is 0%."},
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(orm_qe)
            session.commit()

        # Test SQLiteDatabaseAdapter
        db_adapter = SQLiteDatabaseAdapter(db_url=db_url)
        fb_record = db_adapter.fetch_feedback_record("fb_sql_1")
        assert fb_record.feedback_id == "fb_sql_1"
        assert fb_record.source == FeedbackSource.ACTIVE
        assert fb_record.notes == "Exit load is 1% not 0%"

        # Test SQLiteEvidenceAdapter
        ev_adapter = SQLiteEvidenceAdapter(db_url=db_url)
        snapshot = ev_adapter.get_evidence_snapshot("resp_sql_1")
        assert snapshot.original_query == "What is the exit load?"
        assert snapshot.response_text == "Exit load is 0%."
        assert len(snapshot.evidence_selected) == 1

        # Test writing unified record via SQLiteDatabaseAdapter
        eval_record = UnifiedEvaluationRecord(
            session_id="sess_sql_1",
            response_id="resp_sql_1",
            entry_route=EntryRoute.HITL,
            feedback_ref="fb_sql_1",
            evidence_snapshot_ref="resp_sql_1",
            root_cause=RootCause.MODEL,
            severity=Severity.HIGH,
        )
        db_adapter.write_unified_record(eval_record)
        assert db_adapter.unified_record_exists("resp_sql_1") is True

    finally:
        try:
            if "engine" in locals():
                engine.dispose()
            if "db_adapter" in locals() and hasattr(db_adapter, "_engine"):
                db_adapter._engine.dispose()
            if "ev_adapter" in locals() and hasattr(ev_adapter, "_engine"):
                ev_adapter._engine.dispose()
        except Exception:
            pass
        if os.path.exists(path):
            try:
                os.unlink(path)
            except Exception:
                pass
