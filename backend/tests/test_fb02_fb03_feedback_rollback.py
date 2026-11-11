"""FB02/FB03: Feedback publication link convergence and rollback reopen tests.

FB02: Issue status must converge with durable receipt after restart.
FB03: Rollback must reopen the linked issue and invalidate serving.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from amc_publication.models import Base, FeedbackPublicationLink
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
        f"sqlite:///{tmp_path / 'fb.db'}", connect_args={"timeout": 10}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    journal = Journal(sessions, lease_seconds=60)
    graph = InMemoryGraphPort()
    graph.seed("t1", "AMC-1", "display_name", "old")
    store = ImmutableSnapshotStore(tmp_path / "snapshots")
    return sessions, journal, graph, store

def _payload():
    return {
        "entity": "AMC-1",
        "attribute": "display_name",
        "corrected_value": "new",
        "full_vector_snapshot": [
            {"chunk_id": "c1", "tenant_id": "t1", "text": "fact one"},
            {"chunk_id": "c2", "tenant_id": "t1", "text": "fact two"},
        ],
    }

def test_fb02_resolve_after_verified_publication(env):
    """FB02: FeedbackCausality.resolve succeeds after verified PUBLISHED work."""
    _, journal, graph, store = env
    job = journal.submit(
        tenant="t1", key="k1", proposal_id="p1", revision=1, payload=_payload()
    )
    out = TestWorker(journal, graph, store).run_once()
    assert out["status"] == "published"

    # Get receipt ID
    from amc_publication.models import PublicationReceipt
    with env[0]() as s:
        receipt = s.scalar(
            select(PublicationReceipt).where(PublicationReceipt.work_id == job)
        )
    assert receipt is not None

    fc = FeedbackCausality(env[0])
    resolved = fc.resolve("t1", "issue-1", job, receipt.id)
    assert resolved, "FeedbackCausality.resolve should succeed after verified publication"
    assert fc.status("t1", "issue-1") == "resolved"

def test_fb02_cannot_resolve_with_wrong_tenant(env):
    """FB02: Cross-tenant resolution must fail."""
    _, journal, graph, store = env
    job = journal.submit(
        tenant="t1", key="k1", proposal_id="p1", revision=1, payload=_payload()
    )
    TestWorker(journal, graph, store).run_once()

    from amc_publication.models import PublicationReceipt
    with env[0]() as s:
        receipt = s.scalar(
            select(PublicationReceipt).where(PublicationReceipt.work_id == job)
        )

    fc = FeedbackCausality(env[0])
    # Wrong tenant must fail
    resolved = fc.resolve("WRONG_TENANT", "issue-1", job, receipt.id)
    assert not resolved

def test_fb02_cannot_resolve_unpublished_work(env):
    """FB02: Cannot resolve if work is not yet published."""
    _, journal, graph, store = env
    job = journal.submit(
        tenant="t1", key="k1", proposal_id="p1", revision=1, payload=_payload()
    )
    # Don't run the worker — work is still queued
    fc = FeedbackCausality(env[0])
    resolved = fc.resolve("t1", "issue-1", job, "fake_receipt_id")
    assert not resolved, "Should not resolve with unpublished work"

def test_fb03_rollback_reopens_issue(env):
    """FB03: After rollback, linked issue status changes from resolved to needs_review."""
    _, journal, graph, store = env
    job = journal.submit(
        tenant="t1", key="k1", proposal_id="p1", revision=1, payload=_payload()
    )
    TestWorker(journal, graph, store).run_once()

    from amc_publication.models import PublicationReceipt
    with env[0]() as s:
        receipt = s.scalar(
            select(PublicationReceipt).where(PublicationReceipt.work_id == job)
        )

    fc = FeedbackCausality(env[0])
    fc.resolve("t1", "issue-1", job, receipt.id)
    assert fc.status("t1", "issue-1") == "resolved"

    # Now roll back
    journal.request_rollback(job, "t1")
    out = TestWorker(journal, graph, store).run_once()
    assert out["status"] == "rolled_back"

    # Reopen
    count = fc.reopen_after_rollback("t1", job)
    assert count == 1, f"Expected 1 reopened issue, got {count}"
    assert fc.status("t1", "issue-1") == "needs_review"
