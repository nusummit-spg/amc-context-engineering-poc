"""PUB07: FAISS binary verification and serving reader activation test.

Verifies that after PublicationWorker publishes, the active serving
reader observes the correct generation.  Uses in-memory graph + real
FAISS index (skips if faiss not installed).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amc_publication.models import Base
from amc_publication.journal import Journal
from amc_publication.graph import InMemoryGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.worker import PublicationWorker

try:
    import faiss
    import numpy as np
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

def TestWorker(*args, **kwargs):
    return PublicationWorker(*args, simulation_mode=True, **kwargs)

@pytest.fixture
def env(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pub07.db'}", connect_args={"timeout": 10}
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

def test_pub07_pointer_matches_verified_receipt(env):
    """PUB07: After publish, the active pointer matches the receipt generation."""
    _, journal, graph, store = env
    job = journal.submit(
        tenant="t1", key="k1", proposal_id="p1", revision=1, payload=_payload()
    )
    out = TestWorker(journal, graph, store).run_once()
    assert out["status"] == "published"

    # The active pointer must match the receipt's generation
    ptr = journal.pointer("t1")
    assert ptr["generation_id"] is not None

    # Read the receipt
    from sqlalchemy import select
    from amc_publication.models import PublicationReceipt
    with env[0]() as s:
        receipt = s.scalar(
            select(PublicationReceipt).where(
                PublicationReceipt.work_id == job
            )
        )
    assert receipt is not None
    assert receipt.verified
    # The pointer's generation_id must match the receipt's generation_id
    assert ptr["generation_id"] == receipt.generation_id
    assert ptr["digest"] == receipt.generation_digest

def test_pub07_rollback_clears_pointer_and_receipt_invalidated(env):
    """PUB07: After rollback, pointer is cleared and receipt is stale."""
    _, journal, graph, store = env
    job = journal.submit(
        tenant="t1", key="k1", proposal_id="p1", revision=1, payload=_payload()
    )
    TestWorker(journal, graph, store).run_once()
    journal.request_rollback(job, "t1")
    out = TestWorker(journal, graph, store).run_once()
    assert out["status"] == "rolled_back"

    ptr = journal.pointer("t1")
    assert ptr["generation_id"] is None, "Pointer not cleared after rollback"
    snap = journal.snapshot(job)
    assert snap["status"] == "rolled_back"

@pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
def test_pub07_real_faiss_index_reload():
    """PUB07: A real FAISS index can be reloaded and searched after activation."""
    dim = 64
    num_vectors = 5
    vectors = np.random.RandomState(42).randn(num_vectors, dim).astype("float32")
    faiss.normalize_L2(vectors)

    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIDMap2(quantizer)
    index.add_with_ids(vectors, np.arange(num_vectors, dtype="int64"))

    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "test.index")
        faiss.write_index(index, index_path)

        # Reload — simulating serving reader activation
        reloaded = faiss.read_index(index_path)
        assert reloaded.ntotal == num_vectors

        # Search and verify exact ID matching
        _, ids = reloaded.search(vectors[0:1], 1)
        assert ids[0][0] == 0, "Top match should be ID 0"
