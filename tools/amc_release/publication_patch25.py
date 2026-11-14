"""Wave 2.5: guarded corrections for the audited AMC 2026-11-11 source.

Dry-run by default; applies only if all reviewed source anchors match exactly.
Does not create a branch or overwrite a dirty/unknown repository automatically.
If source changed, reject and re-review rather than guessing a patch.
"""
from __future__ import annotations
import difflib
import hashlib
import json
from pathlib import Path
import shutil

REVIEWED_GIT_BLOBS = {
    # Git blob SHA-1 values retrieved from amc-dev at 2c0415c4d23a3338428c8314c869299aa0ab771f.
    'backend/amc_publication/worker.py': '14723e6ffbb90b45ff0ddc904b72f56ee65d56fa',
    'backend/amc_publication/journal.py': '00239d55656df382211d4eb4c5a8e599aaf76d54',
    'backend/app/api/routes/governance.py': '89ff10036522e05ca3f7ae226a0ed972a8c4b82b',
}

class SourceDrift(ValueError):
    pass


def _once(source: str, old: str, new: str, name: str) -> str:
    if source.count(old) != 1:
        raise SourceDrift(f'{name}: expected one reviewed anchor, found {source.count(old)}')
    return source.replace(old, new, 1)


def harden_worker(source: str) -> str:
    """Freeze before-pointer at preparation and require its CAS at activation."""
    if 'W25_FROZEN_VECTOR_PREIMAGE' in source:
        raise SourceDrift('already patched: review existing changes')
    out = _once(source,
        '        self.owner = owner\n',
        '        self.owner = owner if owner != "worker_default" else "worker_" + uuid.uuid4().hex\n',
        'worker unique identity')
    out = _once(out,
        '        vector_snapshot = payload.get("full_vector_snapshot", [])\n',
        '''        vector_snapshot = payload.get("full_vector_snapshot", [])
        # W25_FROZEN_VECTOR_PREIMAGE: freeze before any graph or pointer mutation.
        # On crash replay, Journal.prepare returns the original durable preimage.
        frozen_before = self.journal.pointer(tenant, "vector_faiss")
        if not isinstance(vector_snapshot, list) or not vector_snapshot:
            raise Conflict("complete nonempty corpus is required before graph mutation")
''',
        'corpus and prior pointer')
    out = _once(out,
        '''            self.journal.prepare(claim, kind="vector", target=entity,
                                pre={"generation_id": None}, 
                                post={"generation_id": generation.generation_id, 
                                      "digest": generation.digest, "count": generation.count})''',
        '''            frozen_before = self.journal.prepare(claim, kind="vector", target=entity,
                                pre=frozen_before,
                                post={"generation_id": generation.generation_id,
                                      "digest": generation.digest, "count": generation.count})''',
        'durable generation preimage')
    out = _once(out,
        '            expected = self.journal.pointer(tenant, "vector_faiss")\n',
        '''            # Never refresh the expected pointer after graph mutation: doing so
            # would allow a newer publication to be silently overwritten.
            expected = frozen_before
''',
        'pointer CAS expected')
    # Strong production adapter requirement (the existing root-exists test
    # accepts JSON-only snapshots and cannot prove what an active reader loads).
    out = _once(out,
        '''        # Production worker must have verified FAISS binary for snapshots
        if not simulation_mode:
            # Verify that at least one generation has been staged and verified
            # FAISS binary must exist for production workers
            if not snapshots.root.exists() or not any(snapshots.root.iterdir()):
                raise ValueError("FAISS binary verification required for production worker")''',
        '''        # Fail closed: a populated directory does not prove a FAISS binary
        # exists, that the graph is Neo4j, or that the SERVING reader reloaded.
        if not simulation_mode:
            from .faiss_artifacts import FaissGenerationStore
            from .graph import Neo4jGraphPort
            if not isinstance(snapshots, FaissGenerationStore) or not isinstance(graph, Neo4jGraphPort):
                raise ValueError("production worker requires real FAISS and Neo4j adapters")
            if not callable(serving_probe):
                raise ValueError("production worker requires serving reader generation probe")''',
        'production adapter type checks')
    out = _once(out,
        '                 owner: str = "worker_default", failpoint=None):',
        '                 owner: str = "worker_default", failpoint=None, serving_probe=None):',
        'reader probe parameter')
    out = _once(out,
        '        self.failpoint = failpoint\n',
        '        self.failpoint = failpoint\n        self.serving_probe = serving_probe\n',
        'reader probe binding')
    out = _once(out,
        '''            # Verify vector effect - observed should match what was passed to prepare()
            observed_vector = {"generation_id": generation.generation_id, 
                              "digest": generation.digest, "count": generation.count}
            self.journal.verified(claim, kind="vector", target=entity, observed=observed_vector)''',
        '''            # Verify immutable bytes and active pointer after the CAS.
            self.snapshots.verify(generation, tenant)
            switched = self.journal.pointer(tenant, "vector_faiss")
            if switched["generation_id"] != generation.generation_id or switched["digest"] != generation.digest:
                raise VerificationFailed("active generation pointer readback mismatch")
            observed_vector = {"generation_id": generation.generation_id,
                              "digest": generation.digest, "count": generation.count}
            self.journal.verified(claim, kind="vector", target=entity, observed=observed_vector)
            if self.serving_probe is not None and self.serving_probe(tenant, generation.generation_id, generation.digest) is not True:
                raise VerificationFailed("active serving reader has not loaded verified generation")''',
        'actual vector/read probe')
    # Rollback must compare with *published* pointer, not whatever is current.
    out = _once(out,
        '''        # CAS from current → prior verified generation (or deactivate if no prior).
        self.journal.switch_back(
            claim,
            current_id=current.get("generation_id") or "",
            current_digest=current.get("digest") or "",
            before=before,
        )''',
        '''        # A later publication must never be rolled back by this old job.
        published = dict(_vec.postimage) if _vec else {}
        if not published.get("generation_id") or not published.get("digest"):
            raise Conflict("verified published vector effect required for rollback")
        if before.get("generation_id"):
            # Verify old bytes before reactivating the prior generation.
            self.snapshots.verify_by_digest(before["digest"], tenant)
        if _vec.state == "compensated":
            # Replay after crash: vector pointer and compensation were already
            # committed atomically. Continue graph rollback, not vector reversion.
            if (current.get("generation_id"), current.get("digest")) != (before.get("generation_id"), before.get("digest")):
                raise Conflict("compensated rollback pointer diverged")
        else:
            if (current.get("generation_id"), current.get("digest")) != (published["generation_id"], published["digest"]):
                raise Conflict("active pointer no longer identifies this publication")
            self.journal.switch_back(
                claim,
                current_id=published["generation_id"],
                current_digest=published["digest"],
                before=before,
                vector_target=entity,
            )''',
        'protect later published generation during rollback')
    return out


def harden_journal(source: str) -> str:
    if 'W25_NONEMPTY_CORPUS' in source:
        raise SourceDrift('already patched')
    out = _once(source,
        '''        if not isinstance(payload.get("full_vector_snapshot"), list):
            raise ValueError("full_vector_snapshot must be an explicit COMPLETE corpus list")''',
        '''        if not isinstance(payload.get("full_vector_snapshot"), list) or not payload["full_vector_snapshot"]:
            # W25_NONEMPTY_CORPUS: a graph-only publication cannot produce two
            # verified effects and must not enter the durable queue.
            raise ValueError("full_vector_snapshot must be a nonempty COMPLETE corpus list")''',
        'reject unpublishable graph-only jobs')
    # Persist pointer rollback AND vector compensation in one SQL transaction.
    # A crash after commit must leave a durable checkpoint that replay recognizes.
    out = _once(out,
        'def switch_back(self, claim: Claim, *, current_id: str, current_digest: str, before: dict):',
        'def switch_back(self, claim: Claim, *, current_id: str, current_digest: str, before: dict, vector_target: str | None = None):',
        'atomic vector rollback signature')
    old = '''            row = s.get(GenerationPointer, (claim.tenant, "vector_faiss"))
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
                row.activated_at = utcnow()'''
    new = '''            # W25_ATOMIC_ROLLBACK: effect checkpoint and pointer share one SQL commit.
            if not vector_target:
                raise Conflict("vector effect target required for atomic rollback")
            effect = s.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == claim.work_id,
                PublicationEffect.kind == "vector",
                PublicationEffect.target == vector_target))
            if not effect or effect.tenant != claim.tenant or effect.state not in ("verified", "compensated"):
                raise Conflict("verified vector effect required for pointer rollback")
            if (effect.postimage.get("generation_id"), effect.postimage.get("digest")) != (current_id, current_digest):
                raise Conflict("rollback target does not match published vector effect")
            if (effect.preimage.get("generation_id"), effect.preimage.get("digest")) != (before.get("generation_id"), before.get("digest")):
                raise Conflict("rollback preimage does not match durable effect")
            row = s.get(GenerationPointer, (claim.tenant, "vector_faiss"))
            if effect.state == "compensated":
                # Crash replay: the previous switch committed with this effect.
                current = (row.generation_id, row.artifact_digest) if row else (None, None)
                if current != (before.get("generation_id"), before.get("digest")):
                    raise Conflict("compensated rollback pointer diverged")
                return
            if not row or row.generation_id != current_id or row.artifact_digest != current_digest:
                raise Conflict("active pointer changed since publication; refusing stale rollback")
            if before.get("generation_id") is None:
                s.delete(row)
            else:
                row.generation_id = before["generation_id"]
                row.artifact_digest = before["digest"]
                row.epoch += 1
                row.activated_at = utcnow()
            effect.state = "compensated"'''
    return _once(out,old,new,'atomic rollback durable checkpoint')


def harden_governance(source: str) -> str:
    if 'W25_TRUSTED_APPROVAL_ADAPTER' in source:
        raise SourceDrift('already patched')
    start = '    # PUB01: Enqueue a v2 publication job instead of mutating the graph directly.\n'
    stop = '    log_governance_audit("PROMOTE_QUEUED", patch_id, current_user.username,\n'
    if source.count(start) != 1 or source.count(stop) != 1:
        raise SourceDrift('governance integration block has drifted')
    a, b = source.index(start), source.index(stop)
    if b <= a:
        raise SourceDrift('invalid source positions')
    # All app startup wiring must supply the canonical `SessionLocal` and
    # signed, server-side corpus. Missing config -> HTTP 503, never a fake 202.
    new = '''    # W25_TRUSTED_APPROVAL_ADAPTER: existing journal + reviewed signed corpus.
    # No request-time DDL, anonymous tenant, fabricated approval or empty corpus.
    try:
        from app.core.database import SessionLocal
        from amc_publication.approval_adapter import queue_from_environment
        work_id = queue_from_environment(sessions=SessionLocal, patch=patch, actor=current_user)
    except Exception as exc:
        logger.error("Publication prerequisites failed for %s: %s", patch_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verified publication prerequisites unavailable; no job queued",
        ) from exc

'''
    out = source[:a] + new + source[b:]
    # Reviewer identity was stored only as a dynamic attribute, absent from
    # CorrectionPatch.to_dict(); add it to persisted provenance before save.
    out = _once(out, '        from app.graph.correction_patch_layer import PatchStatus\n        patch.status = PatchStatus.APPROVED\n', '        # W25_REVIEWER_PERSISTENCE: preserve approver after to_dict().\n        patch.provenance = {**(patch.provenance or {}), "approver_username": current_user.username}\n        patch.status = PatchStatus.APPROVED\n', "single approval reviewer persistence")
    out = _once(out, '                # Update status to APPROVED\n                patch.status = PatchStatus.APPROVED\n', '                # W25_REVIEWER_PERSISTENCE_BATCH: serialize approver identity.\n                patch.provenance = {**(patch.provenance or {}), "approver_username": current_user.username}\n                patch.status = PatchStatus.APPROVED\n', "batch approval reviewer persistence")
    return out


def verify_git_blob(path: Path, known_sha: str | None):
    if known_sha:
        if len(known_sha) != 40 or any(c not in '0123456789abcdef' for c in known_sha):
            raise SourceDrift('invalid expected git blob SHA')
        raw = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != known_sha:
            raise SourceDrift(f'{path}: Git blob drift {actual} != {known_sha}')


def build_patch(repo: str | Path, *, expected_blobs: dict | None = None) -> dict:
    root = Path(repo).resolve()
    if not (root / 'backend/amc_publication/worker.py').is_file():
        raise SourceDrift('AMC backend publication source not present')
    expected_blobs = REVIEWED_GIT_BLOBS if expected_blobs is None else expected_blobs
    transformations = {
        'backend/amc_publication/worker.py': harden_worker,
        'backend/amc_publication/journal.py': harden_journal,
        'backend/app/api/routes/governance.py': harden_governance,
    }
    result = {}
    for relative, fn in transformations.items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise SourceDrift(f'{relative}: missing/unsafe source file')
        verify_git_blob(path, expected_blobs.get(relative))
        old = path.read_text(encoding='utf-8')
        new = fn(old)
        compile(new, relative, 'exec')  # Refuse broken Python before writing anything.
        result[relative] = {'original_sha256': hashlib.sha256(old.encode()).hexdigest(),
                            'new_sha256': hashlib.sha256(new.encode()).hexdigest(),
                            'diff': ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                               fromfile='a/'+relative, tofile='b/'+relative)),
                            'new': new}
    return result


def apply(repo: str | Path, *, apply_changes: bool = False,
          expected_blobs: dict | None = None) -> dict:
    patches = build_patch(repo, expected_blobs=expected_blobs)
    summary = {'status': 'DRY_RUN', 'files': {k:{n:v for n,v in x.items() if n != 'new'}
                                               for k,x in patches.items()}}
    if not apply_changes:
        return summary
    root = Path(repo).resolve()
    # Backups first; never overwrite prior backups or partial patch files.
    for relative in patches:
        if (root / (relative+'.wave25.bak')).exists():
            raise SourceDrift('prior backup exists: ' + relative)
    for relative in patches:
        original = root / relative
        shutil.copy2(original, root / (relative+'.wave25.bak'))
    for relative, payload in patches.items():
        original = root / relative
        original.write_text(payload['new'], encoding='utf-8', newline='\n')
    summary['status'] = 'APPLIED_REVIEW_REQUIRED'
    return summary
