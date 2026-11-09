from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from amc_publication.models import Base
from amc_publication.journal import Journal
from amc_publication.integration import ApprovedProposal, queue_verified_approval
from amc_publication.metrics import durable_metrics
from amc_publication.types import Conflict
from amc_publication.faiss_artifacts import FaissGenerationStore


@pytest.fixture
def journal(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(engine)
    return Journal(sessionmaker(bind=engine))


def approved(proposer="p", reviewer="r", status="APPROVED"):
    return ApprovedProposal(proposal_id="P1", tenant="tenant-1", revision=1,
                            proposer_id=proposer, reviewer_id=reviewer, status=status,
                            entity_id="AMC-12", attribute="name", proposed_value="new")


def test_admission_requires_independent_approval(journal):
    with pytest.raises(Conflict):
        queue_verified_approval(journal, approved(reviewer="p"), [])
    with pytest.raises(Conflict):
        queue_verified_approval(journal, approved(status="pending"), [])


def test_approved_admission_is_idempotent(journal):
    p = approved()
    a = queue_verified_approval(journal, p, [])
    assert a == queue_verified_approval(journal, p, [])
    assert durable_metrics(journal.sessions, "tenant-1")["jobs"] == {"queued": 1}


def test_real_faiss_builder_fails_closed_when_dependency_missing(tmp_path):
    class StubEmbedder: pass
    store = FaissGenerationStore(tmp_path, StubEmbedder())
    try:
        import faiss  # noqa
    except ImportError:
        with pytest.raises(RuntimeError, match="faiss-cpu"):
            store.stage("tenant-1", [])


def test_serving_gate_never_trusts_approved_flag(journal, tmp_path):
    from amc_publication.serving import is_serving_eligible
    from amc_publication.worker import PublicationWorker
    from amc_publication.graph import InMemoryGraphPort
    from amc_publication.artifacts import ImmutableSnapshotStore
    p = approved()
    job = queue_verified_approval(journal, p, [{"chunk_id":"x", "tenant_id":"tenant-1", "text":"proof"}])
    args = {"tenant":"tenant-1","status":"ACTIVE","work_id":job,"receipt_id":"claimed"}
    assert not is_serving_eligible(journal.sessions, **args)
    g = InMemoryGraphPort()
    g.seed("tenant-1", "AMC-12", "name", "original")
    out = PublicationWorker(journal, g, ImmutableSnapshotStore(tmp_path / "vec"), simulation_mode=True).run_once()
    assert out["status"] == "published"
    args["receipt_id"] = out["receipt_id"]
    assert is_serving_eligible(journal.sessions, **args)
    assert not is_serving_eligible(journal.sessions, **{**args, "status":"APPROVED"})
    assert not is_serving_eligible(journal.sessions, **{**args, "revoked":True})
    assert not is_serving_eligible(journal.sessions, **{**args, "tenant":"other"})


def test_durable_metrics_capture_published_effects(journal, tmp_path):
    from amc_publication.worker import PublicationWorker
    from amc_publication.graph import InMemoryGraphPort
    from amc_publication.artifacts import ImmutableSnapshotStore
    queue_verified_approval(journal, approved(), [{"chunk_id":"x", "tenant_id":"tenant-1", "text":"proof"}])
    g=InMemoryGraphPort();g.seed("tenant-1","AMC-12","name","old")
    PublicationWorker(journal,g,ImmutableSnapshotStore(tmp_path/"vec"),simulation_mode=True).run_once()
    m=durable_metrics(journal.sessions,"tenant-1")
    assert m["jobs"] == {"published":1}
    assert m["effects"] == {"verified":2}
    assert durable_metrics(journal.sessions,"another")["jobs"] == {}


def test_ci_patch_is_fail_closed_and_idempotent():
    import importlib.util
    script=Path(__file__).resolve().parents[2] / "tools" / "repair_ci_gitleaks.py"
    sp=importlib.util.spec_from_file_location("repair_ci",script)
    mod=importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    baseline="""      - name: Scan for secrets\n        uses: gitleaks/gitleaks-action@v3\n        with:\n          verbose: true\n      - name: Audit requirements\n"""
    changed=mod.apply(baseline)
    assert "docker run --rm" in changed
    assert "--exit-code 1" in changed
    assert "gitleaks-action@v3" not in changed
    assert mod.apply(changed) == changed
    with pytest.raises(ValueError): mod.apply("missing signature")
