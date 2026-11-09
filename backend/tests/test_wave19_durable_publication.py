"""Executable Wave 1.9 assurance tests; SQLite smoke + deterministic fake graph.

Production gates additionally require PostgreSQL and Neo4j/FAISS integration.
"""
import sys
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from amc_publication.models import Base, PublicationWork, PublicationEffect, PublicationReceipt, utcnow
from amc_publication.journal import Journal
from amc_publication.graph import InMemoryGraphPort, Neo4jGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.types import Conflict, LeaseLost, VerificationFailed
from amc_publication.worker import PublicationWorker

def TestWorker(*args, **kwargs):
    return PublicationWorker(*args, simulation_mode=True, **kwargs)


def payload(tenant="t1", value="new", contents=None):
    return {
        "entity": "AMC-1", "attribute": "display_name", "corrected_value": value,
        "full_vector_snapshot": contents if contents is not None else [
            {"chunk_id": "ch-1", "tenant_id": tenant, "text": "Investment facts", "metadata": {"source": "abc"}},
            {"chunk_id": "ch-2", "tenant_id": tenant, "text": "Another fact"},
        ],
    }


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'journal.db'}", connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    journal = Journal(sessions, lease_seconds=60)
    graph = InMemoryGraphPort()
    graph.seed("t1", "AMC-1", "display_name", "old")
    store = ImmutableSnapshotStore(tmp_path / "snapshots")
    return sessions, journal, graph, store


def submit(env, key="p1", p=None, tenant="t1"):
    return env[1].submit(tenant=tenant, key=key, proposal_id="proposal-A",
                         revision=1, payload=p if p is not None else payload(tenant))


def test_publish_requires_both_verified_effects(env):
    job = submit(env)
    out = TestWorker(env[1], env[2], env[3]).run_once()
    assert out["status"] == "published"
    assert env[1].snapshot(job)["status"] == "published"
    with env[0]() as s:
        effects = s.scalars(select(PublicationEffect).where(PublicationEffect.work_id == job)).all()
        receipts = s.scalars(select(PublicationReceipt).where(PublicationReceipt.work_id == job)).all()
    assert {e.kind for e in effects} == {"graph", "vector"}
    assert all(e.state == "verified" and e.verified_at for e in effects)
    assert len(receipts) == 1 and receipts[0].verified
    assert env[2].read("t1", "AMC-1", "display_name") == {"value": "new"}
    ptr = env[1].pointer("t1")
    assert ptr["generation_id"] is not None and ptr["digest"] == receipts[0].generation_digest


def test_idempotent_submission_and_conflicting_payload(env):
    job = submit(env)
    assert submit(env) == job
    with pytest.raises(Conflict): submit(env, p=payload(value="different"))


def test_tenants_have_separate_idempotency_domains(env):
    assert submit(env, "same", tenant="t1") != submit(env, "same", tenant="t2")


def test_rejects_missing_complete_snapshot(env):
    data = payload()
    del data["full_vector_snapshot"]
    with pytest.raises(ValueError): submit(env, p=data)


def test_rejects_cross_tenant_corpus_before_publication(env):
    job = submit(env, p=payload(contents=[{"chunk_id": "x", "tenant_id": "another", "text": "oops"}]))
    result = TestWorker(env[1], env[2], env[3]).run_once()
    assert result["status"] == "retry_scheduled"
    assert env[1].snapshot(job)["status"] == "queued"
    assert env[1].pointer("t1")["generation_id"] is None


def test_rejects_duplicate_chunk_ids(env):
    corpus = [{"chunk_id": "dup", "tenant_id": "t1", "text": "one"},
              {"chunk_id": "dup", "tenant_id": "t1", "text": "two"}]
    submit(env, p=payload(contents=corpus))
    out = TestWorker(env[1], env[2], env[3]).run_once()
    assert out["status"] == "retry_scheduled"


def test_second_worker_cannot_claim_active_lease(env):
    submit(env)
    c = env[1].claim("worker1")
    assert c is not None and c.fence > 0
    assert env[1].claim("worker2") is None


def test_expired_worker_cannot_complete_receipt(env):
    submit(env)
    old = env[1].claim("old")
    with env[0].begin() as s:
        s.get(PublicationWork, old.work_id).lease_until = utcnow() - timedelta(seconds=1)
    new = env[1].claim("new")
    assert new and new.epoch > old.epoch and new.fence > old.fence
    with pytest.raises(LeaseLost): env[1].prepare(old, kind="graph", target="A:val", pre={"value": 1},post={"value": 2})
    with pytest.raises(LeaseLost): env[1].publish(old)


class SimulatedCrash(BaseException):
    pass


def crash(at):
    def f(stage):
        if stage == at:
            raise SimulatedCrash()
    return f


def expire_job(env, job):
    with env[0].begin() as s:
        row = s.get(PublicationWork, job)
        row.lease_until = utcnow() - timedelta(seconds=1)


@pytest.mark.parametrize("point", ["graph_preimage_committed", "graph_written", "graph_verified",
                                   "vector_preimage_committed", "pointer_switched", "vector_verified"])
def test_crash_at_every_boundary_recovers_with_same_effects(env, point):
    job = submit(env)
    with pytest.raises(SimulatedCrash):
        TestWorker(env[1], env[2], env[3], owner="dead", failpoint=crash(point)).run_once()
    assert env[1].snapshot(job)["status"] == "leased"
    expire_job(env, job)
    out = TestWorker(env[1], env[2], env[3], owner="recovery").run_once()
    assert out["status"] == "published", out
    with env[0]() as s:
        e = s.scalars(select(PublicationEffect).where(PublicationEffect.work_id == job)).all()
    assert len(e) == 2
    assert env[2].read("t1", "AMC-1", "display_name") == {"value": "new"}


def test_rollback_restores_previous_graph_and_deactivates_first_vector_generation(env):
    job = submit(env)
    assert TestWorker(env[1], env[2], env[3]).run_once()["status"] == "published"
    env[1].request_rollback(job, "t1")
    out = TestWorker(env[1], env[2], env[3]).run_once()
    assert out["status"] == "rolled_back", out
    assert env[1].pointer("t1")["generation_id"] is None
    assert env[2].read("t1", "AMC-1", "display_name") == {"value": "old"}
    assert env[1].snapshot(job)["status"] == "rolled_back"


def test_rollback_retries_after_crash_between_pointer_and_graph(env):
    job = submit(env)
    TestWorker(env[1], env[2], env[3]).run_once()
    env[1].request_rollback(job, "t1")
    with pytest.raises(SimulatedCrash):
        TestWorker(env[1], env[2], env[3], failpoint=crash("vector_rollback_committed")).run_once()
    expire_job(env, job)
    assert TestWorker(env[1], env[2], env[3], owner="retry").run_once()["status"] == "rolled_back"
    assert env[2].read("t1", "AMC-1", "display_name")["value"] == "old"


def test_rollback_cannot_affect_other_tenant(env):
    job = submit(env)
    TestWorker(env[1], env[2], env[3]).run_once()
    with pytest.raises(Conflict): env[1].request_rollback(job, "t2")


def test_graph_cas_blocks_unrelated_update(env):
    submit(env)
    env[2].seed("t1", "AMC-1", "display_name", "changed-by-other")
    out = TestWorker(env[1], env[2], env[3]).run_once()
    assert out["status"] == "published"  # legitimate observed preimage is current value
    # Subsequent stale application with a lower fence is rejected.
    with pytest.raises(Conflict):
        env[2].compare_and_set("t1", "AMC-1", "display_name", {"value": "old"}, "wrong", 0)


def test_snapshot_tampering_is_detected(env):
    gen = env[3].stage("t1", payload()["full_vector_snapshot"])
    snap = env[3]._path(gen.digest) / "snapshot.json"
    snap.write_text('{"tenant":"t1","documents":[]}', encoding="utf-8")
    with pytest.raises(VerificationFailed): env[3].verify(gen, "t1")


def test_graph_field_allowlist_fail_closed():
    with pytest.raises(ValueError): Neo4jGraphPort(object(), allowed_attributes=None)
    port = Neo4jGraphPort(object(), allowed_attributes={"display_name"})
    with pytest.raises(ValueError): port._field("display_name` SET n.password='x")
    with pytest.raises(ValueError): port._field("unapproved_field")


def test_cannot_publish_job_without_effects(env):
    submit(env)
    claim = env[1].claim("test")
    with pytest.raises(Conflict): env[1].publish(claim)


def test_conflicting_generation_pointer_fails_closed(env):
    job = submit(env)
    claim = env[1].claim("test")
    env[1].prepare(claim, kind="vector", target="vector_faiss",pre={"generation_id":"not-current","digest":None,"epoch":0},post={"generation_id":"new","digest":"abc"})
    with pytest.raises(Conflict): env[1].switch_pointer(claim,namespace="vector_faiss",expected={"generation_id":"not-current","digest":None,"epoch":0},new_id="new",digest="abc")


def test_production_worker_refuses_unverified_json_snapshot(env):
    with pytest.raises(ValueError, match="FAISS binary"):
        PublicationWorker(env[1], env[2], env[3])
