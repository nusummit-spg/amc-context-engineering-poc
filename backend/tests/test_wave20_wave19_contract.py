"""Wave 2.0 ↔ Wave 1.9 integration; requires the Wave 1.9 code installed.

Fails, rather than silently skipping, if amc_publication cannot be imported.
Uses a disposable DB and SIMULATED graph. Never a production release proof.
"""
import sqlite3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pytest

from amc_publication.models import Base
from amc_publication.journal import Journal
from amc_publication.graph import InMemoryGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.worker import PublicationWorker
from amc_publication.feedback import FeedbackCausality
from amc_quality.feedback_audit import FeedbackEvidenceAuditor
from amc_quality.assurance import DurableAssuranceReader


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'publication.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE feedback_issues (
          issue_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), status VARCHAR(30)
        )"""))
        connection.execute(text("INSERT INTO feedback_issues VALUES ('i1','T','reported')"))
        connection.execute(text("INSERT INTO feedback_issues VALUES ('i2','T','resolved')"))
        connection.execute(text("INSERT INTO feedback_issues VALUES ('i3',NULL,'resolved')"))
        connection.execute(text("INSERT INTO feedback_issues VALUES ('i4','OTHER','resolved')"))
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    journal = Journal(sessions)
    graph = InMemoryGraphPort()
    graph.seed("T", "AMC-1", "display_name", "old")
    snapshots = ImmutableSnapshotStore(tmp_path / "snapshots")
    worker = PublicationWorker(journal, graph, snapshots, simulation_mode=True)
    return engine, sessions, journal, worker


def publish(env):
    engine, sessions, journal, worker = env
    job = journal.submit(tenant="T", key="key", proposal_id="proposal_1", revision=1,
                         payload={"entity":"AMC-1", "attribute":"display_name", "corrected_value":"new",
                                  "full_vector_snapshot":[{"chunk_id":"c1", "tenant_id":"T", "text":"known fact"}]})
    result = worker.run_once()
    assert result["status"] == "published"
    return job, result["receipt_id"]


def set_issue(env, issue, status):
    with env[0].begin() as c:
        c.execute(text("UPDATE feedback_issues SET status=:status WHERE issue_id=:issue"),
                  {"issue":issue,"status":status})


def test_unresolved_issue_no_receipt_consistent(env):
    audit = FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "i1")
    assert audit.verdict == "CONSISTENT" and not audit.verified_active


def test_resolved_issue_without_verified_publication_block(env):
    audit = FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "i2")
    assert audit.verdict == "BLOCK"
    assert "ISSUE_CLOSED_WITHOUT_ACTIVE_VERIFIED_PUBLICATION" in audit.reasons


def test_verified_resolution_consistent(env):
    job, receipt = publish(env)
    assert FeedbackCausality(env[1]).resolve("T", "i1", job, receipt)
    set_issue(env, "i1", "resolved")
    audit = FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "i1")
    assert audit.verdict == "CONSISTENT" and audit.verified_active
    assert audit.publication_link_status == "resolved"


def test_roll_back_reopens_evidence_and_blocks_stale_closed_issue(env):
    job, receipt = publish(env)
    assert FeedbackCausality(env[1]).resolve("T", "i1", job, receipt)
    set_issue(env, "i1", "resolved")
    env[2].request_rollback(job, "T")
    assert env[3].run_once()["status"] == "rolled_back"
    assert FeedbackCausality(env[1]).reopen_after_rollback("T", job) == 1
    audit = FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "i1")
    assert audit.verdict == "BLOCK" and not audit.verified_active
    assert "ROLLBACK_ISSUE_NOT_REOPENED" in audit.reasons


def test_roll_back_reopened_issue_consistent(env):
    job, receipt = publish(env)
    assert FeedbackCausality(env[1]).resolve("T", "i1", job, receipt)
    env[2].request_rollback(job, "T")
    assert env[3].run_once()["status"] == "rolled_back"
    FeedbackCausality(env[1]).reopen_after_rollback("T", job)
    set_issue(env, "i1", "reopened")
    a = FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "i1")
    assert a.verdict == "CONSISTENT" and not a.verified_active


def test_unknown_tenant_denied(env):
    assert FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "i4").verdict == "BLOCK"


def test_null_tenant_denied(env):
    assert FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "i3").verdict == "BLOCK"


def test_missing_issue_denied(env):
    assert FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("T", "missing").verdict == "BLOCK"


def test_assurance_empty_reports_unknown(env):
    snapshot = DurableAssuranceReader(env[1]).snapshot("T")
    assert snapshot.operational_readiness == "UNKNOWN"
    assert snapshot.observed_uptime.startswith("UNKNOWN") and snapshot.p95_latency.startswith("UNKNOWN")
    assert snapshot.release_gate == "BLOCK"


def test_assurance_published_receipt_counts(env):
    publish(env)
    snapshot = DurableAssuranceReader(env[1]).snapshot("T")
    assert snapshot.jobs_by_status["published"] == 1
    assert snapshot.receipts == 1
    assert snapshot.effects_by_status["verified"] == 2
    assert snapshot.operational_readiness == "EVIDENCE_PRESENT_NOT_RELEASE_APPROVED"
    assert snapshot.release_gate == "BLOCK"


def test_assurance_tenant_isolation(env):
    publish(env)
    snapshot = DurableAssuranceReader(env[1]).snapshot("OTHER")
    assert snapshot.receipts == 0 and snapshot.jobs_by_status == {}
    assert snapshot.operational_readiness == "UNKNOWN"


def test_assurance_queue_incomplete(env):
    env[2].submit(tenant="T", key="queued", proposal_id="p", revision=1,
                  payload={"entity":"E", "attribute":"display_name", "corrected_value":"X", "full_vector_snapshot":[]})
    snapshot = DurableAssuranceReader(env[1]).snapshot("T")
    assert snapshot.operational_readiness == "INCOMPLETE"


def test_audit_missing_tenant_arguments_fail(env):
    with pytest.raises(ValueError):
        FeedbackEvidenceAuditor(publication_sessions=env[1], issue_sessions=env[1]).audit("", "i1")


def test_assurance_missing_tenant_fail(env):
    with pytest.raises(ValueError):
        DurableAssuranceReader(env[1]).snapshot("")
