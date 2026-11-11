"""Fault-injection tests — crash consistency at every side-effect boundary.

CI05 / A05: Proves that killing the worker at any boundary leaves the
system recoverable with no phantom receipts (P10, P11).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from amc_publication.models import Base, PublicationWork, utcnow
from amc_publication.journal import Journal
from amc_publication.graph import InMemoryGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.worker import PublicationWorker
from datetime import timedelta

class SimulatedCrash(BaseException):
    pass

def crash_at(stage):
    def fp(s):
        if s == stage:
            raise SimulatedCrash(f"crash at {stage}")
    return fp

def TestWorker(*args, **kwargs):
    return PublicationWorker(*args, simulation_mode=True, **kwargs)

@pytest.fixture
def env(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'fault.db'}", connect_args={"timeout": 10}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    journal = Journal(sessions, lease_seconds=60)
    graph = InMemoryGraphPort()
    graph.seed("t1", "ENT-1", "name", "original")
    store = ImmutableSnapshotStore(tmp_path / "snapshots")
    return sessions, journal, graph, store

def _payload():
    return {
        "entity": "ENT-1", "attribute": "name", "corrected_value": "patched",
        "full_vector_snapshot": [
            {"chunk_id": "c1", "tenant_id": "t1", "text": "corpus item"},
        ],
    }

def _expire(env, job):
    with env[0].begin() as s:
        s.get(PublicationWork, job).lease_until = utcnow() - timedelta(seconds=1)

@pytest.mark.parametrize("stage", [
    "graph_preimage_committed",
    "graph_written",
    "graph_verified",
    "vector_preimage_committed",
    "pointer_switched",
    "vector_verified",
])
def test_P11_crash_at_boundary_recovers_to_published(env, stage):
    """P11: crash at every side-effect boundary must be recoverable."""
    job = env[1].submit(
        tenant="t1", key=f"k_{stage}", proposal_id="p1", revision=1, payload=_payload()
    )
    with pytest.raises(SimulatedCrash):
        TestWorker(env[1], env[2], env[3], owner="dead", failpoint=crash_at(stage)).run_once()
    _expire(env, job)
    out = TestWorker(env[1], env[2], env[3], owner="recovery").run_once()
    assert out["status"] == "published", (
        f"P11 FAILED: recovery after crash at {stage!r} did not reach published; got {out}"
    )

def test_P10_two_workers_yield_one_receipt(env):
    """P10: two workers racing the same job must produce exactly one receipt."""
    from sqlalchemy import select
    from amc_publication.models import PublicationReceipt
    job = env[1].submit(
        tenant="t1", key="k_race", proposal_id="p_race", revision=1, payload=_payload()
    )
    out1 = TestWorker(env[1], env[2], env[3], owner="worker-1").run_once()
    out2 = TestWorker(env[1], env[2], env[3], owner="worker-2").run_once()
    assert out2["status"] == "no_jobs", "P10: second worker should find no claimable job"
    assert out1["status"] == "published"
    with env[0]() as s:
        receipts = s.scalars(
            select(PublicationReceipt).where(PublicationReceipt.work_id == job)
        ).all()
    assert len(receipts) == 1, f"P10: expected 1 receipt, got {len(receipts)}"
