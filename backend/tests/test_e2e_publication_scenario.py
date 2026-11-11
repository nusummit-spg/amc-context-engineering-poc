"""GATE02: End-to-end publication scenario test.

Full scenario: submit → claim → graph CAS → readback verify →
vector stage → pointer switch → vector verify → publish receipt →
status check → rollback → issue reopen.

Uses in-memory graph and SQLite.  Run:
    python -m pytest tests/test_e2e_publication_scenario.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from amc_publication.models import (
    Base, PublicationWork, PublicationEffect, PublicationReceipt,
)
from amc_publication.journal import Journal
from amc_publication.graph import InMemoryGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.worker import PublicationWorker
from amc_publication.feedback import FeedbackCausality

def TestWorker(*args, **kwargs):
    return PublicationWorker(*args, simulation_mode=True, **kwargs)

@pytest.fixture
def env(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'e2e.db'}", connect_args={"timeout": 10}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    journal = Journal(sessions, lease_seconds=60)
    graph = InMemoryGraphPort()
    graph.seed("t1", "AMC-1", "display_name", "original")
    store = ImmutableSnapshotStore(tmp_path / "snapshots")
    return sessions, journal, graph, store

def _payload():
    return {
        "entity": "AMC-1",
        "attribute": "display_name",
        "corrected_value": "corrected_name",
        "full_vector_snapshot": [
            {"chunk_id": "c1", "tenant_id": "t1", "text": "fact one"},
            {"chunk_id": "c2", "tenant_id": "t1", "text": "fact two"},
        ],
    }

def test_gate02_full_publish_and_rollback_scenario(env):
    """GATE02: Complete publication lifecycle from submit to rollback to reopen."""
    sessions, journal, graph, store = env

    # Step 1: Submit publication job
    job = journal.submit(
        tenant="t1", key="e2e-1", proposal_id="prop-e2e", revision=1, payload=_payload()
    )
    assert journal.snapshot(job)["status"] == "queued"

    # Step 2: Worker claims and publishes
    out = TestWorker(journal, graph, store).run_once()
    assert out["status"] == "published"
    assert journal.snapshot(job)["status"] == "published"

    # Step 3: Graph was actually updated (verified by independent readback)
    assert graph.read("t1", "AMC-1", "display_name")["value"] == "corrected_name"

    # Step 4: Vector pointer is active
    ptr = journal.pointer("t1")
    assert ptr["generation_id"] is not None

    # Step 5: Receipt exists and is verified
    with sessions() as s:
        receipt = s.scalar(
            select(PublicationReceipt).where(PublicationReceipt.work_id == job)
        )
    assert receipt is not None
    assert receipt.verified

    # Step 6: Feedback issue can be resolved
    fc = FeedbackCausality(sessions)
    assert fc.resolve("t1", "issue-e2e", job, receipt.id)
    assert fc.status("t1", "issue-e2e") == "resolved"

    # Step 7: Request rollback
    journal.request_rollback(job, "t1")
    assert journal.snapshot(job)["status"] == "rollback_pending"

    # Step 8: Worker processes rollback
    out = TestWorker(journal, graph, store).run_once()
    assert out["status"] == "rolled_back"
    assert journal.snapshot(job)["status"] == "rolled_back"

    # Step 9: Graph restored to original
    assert graph.read("t1", "AMC-1", "display_name")["value"] == "original"

    # Step 10: Pointer cleared (first generation)
    ptr = journal.pointer("t1")
    assert ptr["generation_id"] is None

    # Step 11: Feedback issue reopened
    count = fc.reopen_after_rollback("t1", job)
    assert count == 1
    assert fc.status("t1", "issue-e2e") == "needs_review"

def test_gate02_idempotent_replay_after_crash(env):
    """GATE02: Replaying the same job after a simulated crash produces identical effects."""
    _, journal, graph, store = env

    class Crash(BaseException):
        pass

    def crash_at(stage):
        def fp(s):
            if s == stage:
                raise Crash()
        return fp

    job = journal.submit(
        tenant="t1", key="e2e-2", proposal_id="prop-crash", revision=1, payload=_payload()
    )

    # Crash during graph_verified
    with pytest.raises(Crash):
        TestWorker(journal, graph, store, owner="crashed",
                   failpoint=crash_at("graph_verified")).run_once()

    # Expire lease so recovery worker can claim
    from datetime import timedelta
    from amc_publication.models import utcnow
    with env[0].begin() as s:
        s.get(PublicationWork, job).lease_until = utcnow() - timedelta(seconds=1)

    # Recovery worker completes the job
    out = TestWorker(journal, graph, store, owner="recovery").run_once()
    assert out["status"] == "published"
    assert graph.read("t1", "AMC-1", "display_name")["value"] == "corrected_name"
