"""
Unit tests for feedback_loop SQLAlchemy event trigger.
"""
from datetime import datetime, timezone
import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.adapters.sqlite.db_adapter import SQLiteDatabaseAdapter
from feedback_loop.adapters.sqlite.evidence_adapter import SQLiteEvidenceAdapter
from feedback_loop.triggers.feedback_trigger import register_feedback_trigger
from feedback_loop.models import (
    Base,
    ResponseFeedback as ORM_ResponseFeedback,
    QueryEvidence as ORM_QueryEvidence,
)


def test_register_feedback_trigger_after_flush():
    """Test register feedback trigger after flush.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"

    try:
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)
        SessionFactory = sessionmaker(bind=engine)

        config = FeedbackLoopConfig()
        db_adapter = SQLiteDatabaseAdapter(db_url=db_url)
        ev_adapter = SQLiteEvidenceAdapter(db_url=db_url)

        # Register event hook
        register_feedback_trigger(
            session_factory=SessionFactory,
            config=config,
            db_adapter=db_adapter,
            ev_adapter=ev_adapter,
        )

        with SessionFactory() as session:
            # 1. Add QueryEvidence first so the pipeline finds it
            qe = ORM_QueryEvidence(
                response_id="resp_trig_1",
                session_id="sess_trig_1",
                query_text="What is TER?",
                assembled_context_json=[
                    {"chunk_id": "c1", "value": "0.75%", "content": "TER is 0.75%"}
                ],
                synthesis_output_json={"answer": "TER is 0.50%"},
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(qe)
            session.commit()

        with SessionFactory() as session:
            # 2. Add ResponseFeedback - trigger fires on after_flush
            fb = ORM_ResponseFeedback(
                feedback_id="fb_trig_1",
                interaction_id="int_trig_1",
                actor_id="user_trig",
                session_id="sess_trig_1",
                response_id="resp_trig_1",
                turn_number=1,
                selected_categories=["F02"],
                feedback_text="TER should be 0.75% not 0.50%",
                actor_role="reviewer",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(fb)
            session.commit()

        # Verify unified record was created automatically by trigger
        assert db_adapter.unified_record_exists("resp_trig_1") is True

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
