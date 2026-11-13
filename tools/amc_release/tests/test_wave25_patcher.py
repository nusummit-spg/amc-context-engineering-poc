"""Anchor/transaction/drift contract for current source-aware Wave 2.5 fixes."""
import importlib.util
from pathlib import Path
import shutil
import sys
import pytest

ROOT=Path(__file__).resolve().parents[3]
MODULE=ROOT/'tools/amc_release/publication_patch25.py'
spec=importlib.util.spec_from_file_location('publication_patch25', MODULE)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

WORKER = '''import uuid
class PublicationWorker:
    def __init__(self, snapshots, graph, simulation_mode,
                 owner: str = "worker_default", failpoint=None):
        self.owner = owner
        self.failpoint = failpoint
        self.snapshots = snapshots
        self.graph = graph
        self.serving_probe = serving_probe
        # Production worker must have verified FAISS binary for snapshots
        if not simulation_mode:
            # Verify that at least one generation has been staged and verified
            # FAISS binary must exist for production workers
            if not snapshots.root.exists() or not any(snapshots.root.iterdir()):
                raise ValueError("FAISS binary verification required for production worker")
    def process(self, payload, tenant, entity, claim):
        vector_snapshot = payload.get("full_vector_snapshot", [])
        if vector_snapshot:
            generation = self.snapshots.stage(tenant, vector_snapshot)
            self.journal.prepare(claim, kind="vector", target=entity,
                                pre={"generation_id": None}, 
                                post={"generation_id": generation.generation_id, 
                                      "digest": generation.digest, "count": generation.count})
        if vector_snapshot:
            expected = self.journal.pointer(tenant, "vector_faiss")
            self.journal.switch_pointer(claim, namespace="vector_faiss", expected=expected,
                                        new_id=generation.digest, digest=generation.digest)
            # Verify vector effect - observed should match what was passed to prepare()
            observed_vector = {"generation_id": generation.generation_id, 
                              "digest": generation.digest, "count": generation.count}
            self.journal.verified(claim, kind="vector", target=entity, observed=observed_vector)
    def rollback(self, claim, tenant, entity, current, before, _vec):
        # CAS from current → prior verified generation (or deactivate if no prior).
        self.journal.switch_back(
            claim,
            current_id=current.get("generation_id") or "",
            current_digest=current.get("digest") or "",
            before=before,
        )
'''

JOURNAL = '''class Journal:
    def submit(self, payload):
        if not isinstance(payload.get("full_vector_snapshot"), list):
            raise ValueError("full_vector_snapshot must be an explicit COMPLETE corpus list")
    def switch_back(self, claim: Claim, *, current_id: str, current_digest: str, before: dict):
        with self.sessions.begin() as s:
            self._require(s, claim)
            row = s.get(GenerationPointer, (claim.tenant, "vector_faiss"))
            if not row or row.generation_id != current_id or row.artifact_digest != current_digest:
                raise Conflict(
                    "active pointer changed since publication; "
                    "manual rollback reconciliation required"
                )
            if before.get("generation_id") is None:
                # First-ever generation: deactivate explicitly by removing the row.
                s.delete(row)
            else:
                # Restore to the previous verified generation via CAS.
                row.generation_id = before["generation_id"]
                row.artifact_digest = before["digest"]
                row.epoch += 1
                row.activated_at = utcnow()
'''

GOVERNANCE = '''def approve(patch, PatchStatus, current_user):
        # B01: Transition to APPROVED state only
        from app.graph.correction_patch_layer import PatchStatus
        patch.status = PatchStatus.APPROVED

def batch_approve(patch, PatchStatus, current_user):
                # Update status to APPROVED
                patch.status = PatchStatus.APPROVED

def promote(patch, current_user, db, patch_id, status, HTTPException, logger, log_governance_audit):
    # PUB01: Enqueue a v2 publication job instead of mutating the graph directly.
    work_id = 'invalid-placeholder'
    log_governance_audit("PROMOTE_QUEUED", patch_id, current_user.username,
                         {"work_id": work_id})
    return work_id
'''

@pytest.fixture
def staged(tmp_path):
    files = {'backend/amc_publication/worker.py':WORKER,
             'backend/amc_publication/journal.py':JOURNAL,
             'backend/app/api/routes/governance.py':GOVERNANCE}
    for name,contents in files.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents)
    return tmp_path

def test_harden_worker_freezes_durable_original_pointer():
    a=mod.harden_worker(WORKER)
    assert 'W25_FROZEN_VECTOR_PREIMAGE' in a
    assert 'pre=frozen_before' in a
    assert 'expected = frozen_before' in a
    assert 'published["generation_id"]' in a
    assert 'active pointer no longer identifies this publication' in a
    assert 'production worker requires real FAISS and Neo4j adapters' in a
    assert 'active serving reader has not loaded verified generation' in a
    assert 'self.owner = owner if owner != "worker_default"' in a
    compile(a,'worker.py','exec')

def test_harden_journal_rejects_empty_full_snapshot(staged):
    src=(staged/'backend/amc_publication/journal.py').read_text()
    a=mod.harden_journal(src)
    assert 'W25_NONEMPTY_CORPUS' in a
    assert 'W25_ATOMIC_ROLLBACK' in a
    assert 'not payload["full_vector_snapshot"]' in a
    compile(a,'journal.py','exec')

def test_governance_requires_server_signed_corpus_not_create_all():
    a=mod.harden_governance(GOVERNANCE)
    assert 'W25_TRUSTED_APPROVAL_ADAPTER' in a
    assert 'W25_REVIEWER_PERSISTENCE:' in a
    assert 'W25_REVIEWER_PERSISTENCE_BATCH:' in a
    assert 'queue_from_environment(sessions=SessionLocal' in a
    assert '503' in a or 'HTTP_503_SERVICE_UNAVAILABLE' in a
    assert 'work_id = \'invalid-placeholder\'' not in a
    compile(a,'governance.py','exec')

def test_apply_default_is_dry_run_and_source_unchanged(staged):
    orig=(staged/'backend/amc_publication/worker.py').read_bytes()
    out=mod.apply(staged,expected_blobs={})
    assert out['status']=='DRY_RUN' and len(out['files'])==3
    assert (staged/'backend/amc_publication/worker.py').read_bytes()==orig
    assert not list(staged.rglob('*.bak'))

def test_apply_creates_backups_and_no_inplace_second_run(staged):
    out=mod.apply(staged,apply_changes=True,expected_blobs={})
    assert out['status']=='APPLIED_REVIEW_REQUIRED'
    assert (staged/'backend/amc_publication/worker.py.wave25.bak').exists()
    assert 'W25_FROZEN_VECTOR_PREIMAGE' in (staged/'backend/amc_publication/worker.py').read_text()
    with pytest.raises(mod.SourceDrift): mod.apply(staged,apply_changes=True,expected_blobs={})

def test_partial_source_drift_refuses_all_writes(staged):
    p=staged/'backend/amc_publication/journal.py'
    p.write_text(p.read_text().replace('full_vector_snapshot must be an explicit COMPLETE corpus list','different message'))
    orig=(staged/'backend/amc_publication/worker.py').read_bytes()
    with pytest.raises(mod.SourceDrift):mod.apply(staged,apply_changes=True,expected_blobs={})
    assert (staged/'backend/amc_publication/worker.py').read_bytes()==orig
    assert not list(staged.rglob('*.wave25.bak'))

def test_missing_source_is_fail_closed(staged):
    (staged/'backend/app/api/routes/governance.py').unlink()
    with pytest.raises(mod.SourceDrift): mod.apply(staged,expected_blobs={})

def test_git_blob_integrity_matches_then_blocks_modified_source(staged):
    path=staged/'backend/amc_publication/journal.py'
    import hashlib
    raw=path.read_bytes(); digest=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    mod.verify_git_blob(path,digest)
    path.write_bytes(raw+b'# unsafe change\n')
    with pytest.raises(mod.SourceDrift):mod.verify_git_blob(path,digest)

def test_invalid_git_blob_rejected(staged):
    with pytest.raises(mod.SourceDrift):mod.verify_git_blob(staged/'backend/amc_publication/worker.py','short')

def test_default_pinned_baseline_rejects_simulated_source(staged):
    with pytest.raises(mod.SourceDrift, match='Git blob drift'):
        mod.apply(staged)

def test_duplicate_anchor_is_rejected():
    with pytest.raises(mod.SourceDrift):mod.harden_worker(WORKER+WORKER)
