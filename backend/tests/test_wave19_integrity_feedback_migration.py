"""Additional contract tests for feedback causality, source integrity and DDL."""
from pathlib import Path
import sys
import importlib.util
from hashlib import sha256

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations

from amc_publication.models import Base
from amc_publication.journal import Journal
from amc_publication.worker import PublicationWorker
from amc_publication.graph import InMemoryGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.feedback import FeedbackCausality
from amc_publication.integrity import verify_source_manifest
from amc_publication.types import Conflict, VerificationFailed


def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    journal = Journal(sessions)
    graph = InMemoryGraphPort()
    graph.seed("T", "ABC", "display_name", "old")
    artifacts = ImmutableSnapshotStore(tmp_path / "artifacts")
    data = {"entity": "ABC", "attribute": "display_name", "corrected_value": "good",
            "full_vector_snapshot": [{"chunk_id": "x", "tenant_id": "T", "text": "good"}]}
    work_id = journal.submit(tenant="T", key="idempotent", proposal_id="proposal", revision=1, payload=data)
    return journal, graph, artifacts, sessions, work_id


def test_feedback_requires_actual_verified_receipt(tmp_path):
    journal, graph, artifacts, sessions, job = setup(tmp_path)
    f = FeedbackCausality(sessions)
    assert not f.resolve("T", "feedback-1", job, "nonexistent")
    result = PublicationWorker(journal, graph, artifacts, simulation_mode=True).run_once()
    assert result["status"] == "published"
    assert not f.resolve("other-tenant", "feedback-1", job, result["receipt_id"])
    assert f.resolve("T", "feedback-1", job, result["receipt_id"])
    assert f.status("T", "feedback-1") == "resolved"
    assert f.status("other-tenant", "feedback-1") == "unlinked"


def test_feedback_resolution_reopens_when_rollback_verified(tmp_path):
    journal, graph, artifacts, sessions, job = setup(tmp_path)
    result = PublicationWorker(journal, graph, artifacts, simulation_mode=True).run_once()
    f = FeedbackCausality(sessions)
    assert f.resolve("T", "fb-7", job, result["receipt_id"])
    journal.request_rollback(job, "T")
    assert PublicationWorker(journal, graph, artifacts, simulation_mode=True).run_once()["status"] == "rolled_back"
    assert f.reopen_after_rollback("T", job) == 1
    assert f.status("T", "fb-7") == "needs_review"
    assert not f.is_verified_active("T", job, result["receipt_id"])


def test_feedback_resolution_conflicting_receipt_not_allowed(tmp_path):
    journal, graph, artifacts, sessions, job = setup(tmp_path)
    first = PublicationWorker(journal, graph, artifacts, simulation_mode=True).run_once()
    f = FeedbackCausality(sessions)
    assert f.resolve("T", "fb-1", job, first["receipt_id"])
    later_payload = {"entity": "ABC", "attribute": "display_name", "corrected_value": "later",
                     "full_vector_snapshot": [{"chunk_id": "later", "tenant_id": "T", "text": "later"}]}
    second_job = journal.submit(tenant="T", key="later-key", proposal_id="proposal-2", revision=1,
                                payload=later_payload)
    second = PublicationWorker(journal, graph, artifacts, simulation_mode=True).run_once()
    assert second["status"] == "published"
    with pytest.raises(Conflict):
        f.resolve("T", "fb-1", second_job, second["receipt_id"])
    assert f.status("T", "fb-1") == "resolved"


def test_manifest_recomputes_real_bytes(tmp_path):
    p = tmp_path / "input.csv"
    data = b"amc,aaum\nABC,12.50\n"
    p.write_bytes(data)
    chunks = [{"start": 0, "end": 7, "sha256": sha256(data[:7]).hexdigest()},
              {"start": 7, "end": len(data), "sha256": sha256(data[7:]).hexdigest()}]
    digest = sha256(data).hexdigest()
    assert verify_source_manifest(p, expected_sha256=digest, chunks=chunks, expected_byte_count=len(data))["chunks"] == 2
    p.write_bytes(data.replace(b"ABC", b"XYZ"))
    with pytest.raises(VerificationFailed): verify_source_manifest(p, expected_sha256=digest, chunks=chunks)


def test_manifest_catches_gaps_and_truncated_chunks(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"abc")
    d = sha256(b"abc").hexdigest()
    with pytest.raises(VerificationFailed): verify_source_manifest(p, expected_sha256=d, chunks=[])
    with pytest.raises(VerificationFailed): verify_source_manifest(p, expected_sha256=d, chunks=[{"start":1,"end":3,"sha256":sha256(b"bc").hexdigest()}])


def test_migration_012_matches_sqlalchemy_models(tmp_path):
    """Execute additive Alembic DDL against disposable SQLite, then downgrade."""
    mig = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "012_wave19_durable_publication.py"
    spec = importlib.util.spec_from_file_location("wave19_ddl", mig)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    engine = create_engine(f"sqlite:///{tmp_path/'migration.db'}")
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op = Operations(ctx)
        mod.upgrade()
        metadata = Base.metadata
        inspector = inspect(conn)
        for t in metadata.tables:
            assert t in inspector.get_table_names(), t
            actual = {c["name"] for c in inspector.get_columns(t)}
            expected = set(metadata.tables[t].columns.keys())
            assert actual == expected, (t, actual.symmetric_difference(expected))
        mod.downgrade()
        assert "publication_work_v2" not in inspect(conn).get_table_names()
