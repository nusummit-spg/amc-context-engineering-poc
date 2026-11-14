"""Wave 2.6 patch composition: harden Wave 2.5 against recovered/stale effects.

Default: dry-run. Only exact source Git blobs reviewed on amc-dev@2c0415c4
are accepted. This file does not invoke a repository write action.
"""
from __future__ import annotations

from pathlib import Path
import difflib
import hashlib
import shutil

from . import publication_patch25 as w25

SourceDrift = w25.SourceDrift
REVIEWED_GIT_BLOBS = {
    **w25.REVIEWED_GIT_BLOBS,
    'backend/amc_publication/faiss_artifacts.py': '6e4e28165862d6a776764d84e8b1d22f6077876e',
    'backend/amc_publication/status_route.py': '175d16171f2fc62d5c7e3e3c95c9bcc6a66a0b8f',
}


def _once(text: str, original: str, new: str, label: str) -> str:
    return w25._once(text, original, new, label)


def _rewrite_method(source: str, start: str, end: str, transform) -> str:
    if source.count(start) != 1 or source.count(end) != 1:
        raise SourceDrift('expected unique method boundaries for '+start)
    i, j = source.index(start), source.index(end)
    if j <= i:
        raise SourceDrift('invalid method order: '+start)
    return source[:i] + transform(source[i:j]) + source[j:]


def harden_worker26(source: str) -> str:
    if 'W26_DURABLE_GRAPH_PREIMAGE' in source:
        raise SourceDrift('worker already contains Wave 2.6 patch')
    if 'W25_FROZEN_VECTOR_PREIMAGE' not in source:
        raise SourceDrift('Wave 2.5 worker must be applied first')
    source = _once(source,
       '''        self.journal.prepare(claim, kind="graph", target=entity, 
                            pre=preimage, post=postimage)''',
       '''        # W26_DURABLE_GRAPH_PREIMAGE: reuse the FIRST prepared preimage.
        # On replay do not treat an unrelated writer's new value as permission
        # to overwrite that writer's update.
        durable_graph_before = self.journal.prepare(
            claim, kind="graph", target=entity, pre=preimage, post=postimage)''',
       'graph durable effect')
    # Two exact graph CAS calls (simulation and real backend).
    old = 'tenant, entity, attribute, preimage, corrected_value, claim.fence'
    if source.count(old) != 2:
        raise SourceDrift(f'graph CAS: expected exactly two branches, found {source.count(old)}')
    source = source.replace(old, 'tenant, entity, attribute, durable_graph_before, corrected_value, claim.fence')
    source = _once(source,
       '''            self.journal.verified(claim, kind="vector", target=entity, observed=observed_vector)
            if self.serving_probe is not None and self.serving_probe(tenant, generation.generation_id, generation.digest) is not True:
                raise VerificationFailed("active serving reader has not loaded verified generation")''',
       '''            # W26_READER_BEFORE_VERIFIED: external serving-reader evidence
            # must precede the durable vector verification checkpoint.
            if self.serving_probe is not None and self.serving_probe(tenant, generation.generation_id, generation.digest) is not True:
                raise VerificationFailed("active serving reader has not loaded verified generation")
            self.journal.verified(claim, kind="vector", target=entity, observed=observed_vector)''',
       'serving probe before verified effect')
    source = _once(source,
       '''                current_value = self.graph.read(tenant, entity, attribute)
                # Restore graph to preimage value using current value as expected''',
       '''                current_value = self.graph.read(tenant, entity, attribute)
                # W26_GRAPH_ROLLBACK_CAS: reject unrelated graph updates since publication.
                if current_value.get("value") not in (effect.postimage.get("value"), preimage.get("value")):
                    raise Conflict("graph changed after this publication; manual reconciliation required")
                # Restore graph to preimage value using current value as expected''',
       'rollback protects third-party graph updates')
    source = _once(source,
       '''                    preimage.get("value"),  # Restore to preimage
                    claim.fence
                )
        
        # Compensate graph effect''',
       '''                    preimage.get("value"),  # Restore to preimage
                    claim.fence
                )
                if self.graph.read(tenant, entity, attribute).get("value") != preimage.get("value"):
                    raise VerificationFailed("graph rollback readback did not restore original value")
        
        # Compensate graph effect''',
       'rollback independent graph readback')
    return source


def harden_journal26(source: str) -> str:
    if 'W26_POINTER_ROW_LOCK' in source:
        raise SourceDrift('journal already has Wave 2.6 patch')
    if 'W25_ATOMIC_ROLLBACK' not in source:
        raise SourceDrift('Wave 2.5 journal must be applied first')
    def transform(segment: str) -> str:
        segment = _once(segment,
           '''            row = s.get(GenerationPointer, (claim.tenant, namespace))''',
           '''            # W26_POINTER_ROW_LOCK: serialize concurrent switch attempts on PostgreSQL.
            # A missing row is protected by PK uniqueness; PostgreSQL must be tested.
            row = s.get(GenerationPointer, (claim.tenant, namespace),
                        with_for_update=True, populate_existing=True)''',
           'locked pointer row')
        segment = _once(segment,
           '''            if cur["generation_id"] == new_id and cur["digest"] == digest:
                # Replay after crash: already switched to our generation.
                return''',
           '''            if cur["generation_id"] == new_id and cur["digest"] == digest:
                # Repeated identical snapshot or a one-step replay after a crash.
                # A later generation cycle (same digest, newer epoch) is not ours.
                if cur == expected or cur["epoch"] == expected.get("epoch", -100) + 1:
                    return
                raise Conflict("active pointer epoch drift on replay; refusing false ownership")''',
           'idempotent pointer replay epoch')
        return segment
    return _rewrite_method(source, '    def switch_pointer(', '    def publish(', transform)


def harden_governance26(source: str) -> str:
    if 'W26_ACCEPTED_JSON' in source:
        raise SourceDrift('governance already contains Wave 2.6 patch')
    if 'W25_TRUSTED_APPROVAL_ADAPTER' not in source:
        raise SourceDrift('Wave 2.5 governance must be applied first')
    old = '''    # Return 202 Accepted — the worker will verify effects before publishing.
    raise HTTPException(
        status_code=status.HTTP_202_ACCEPTED,
        detail={
            "message": "Publication intent queued. Worker will verify graph/vector effects.",
            "work_id": work_id,
            "status_url": f"/api/publication/status/{work_id}",
        },
    )'''
    new = '''    # W26_ACCEPTED_JSON: 202 is a successful HTTP response, never an exception.
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Publication intent queued. Worker will verify graph/vector effects.",
            "work_id": work_id,
            "status_url": f"/api/publication/status/{work_id}",
        },
    )'''
    out = _once(source, old, new, 'proper accepted HTTP response')
    # Bind the existing governance route to independently reconciled full corpus.
    return _once(out, 'from amc_publication.approval_adapter import queue_from_environment',
        'from amc_publication.approval_catalog26 import queue_from_environment_26 as queue_from_environment',
        'catalog proof admission')


def harden_faiss26(source: str) -> str:
    """Retain staged-file durability without Unix-only directory fsync on Windows."""
    if 'W26_FAISS_WINDOWS_PORTABLE' in source:
        raise SourceDrift('FAISS source already patched')
    source = _once(source,
       '''            for f in stage.iterdir():
                with f.open("rb") as fh:
                    os.fsync(fh.fileno())''',
       '''            for f in stage.iterdir():
                # W26_FAISS_WINDOWS_PORTABLE: Windows _commit can require a
                # writable file handle. Files have already been fully written.
                with f.open("rb+") as fh:
                    fh.flush()
                    os.fsync(fh.fileno())''',
       'Windows file sync')
    source = _once(source,
       '''            fd = os.open(dest.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)''',
       '''            # Directory fsync is not portable to Windows; file checksums and
            # readback are still mandatory before any pointer activation.
            if os.name != "nt":
                fd = os.open(dest.parent, os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)''',
       'OS-specific directory fsync')
    return source


def harden_status_route26(source: str) -> str:
    """P0: authenticated tenant/role scope, no cross-tenant job enumeration."""
    if 'W26_TENANT_SCOPED_STATUS' in source:
        raise SourceDrift('status route already patched')
    out = _once(source,
      'def _get_job_status(work_id: str, sessions) -> Dict[str, Any]:',
      'def _get_job_status(work_id: str, sessions, *, tenant: str) -> Dict[str, Any]:',
      'tenant-parameterized status inspection')
    out = _once(out,
      '    snapshot = journal.snapshot(work_id)\n    if snapshot is None:',
      '    if not tenant:\n        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant identity required")\n    snapshot = journal.snapshot(work_id)\n    # W26_TENANT_SCOPED_STATUS: never reveal another tenant’s job.\n    if snapshot is None or snapshot.get("tenant") != tenant:',
      'cross-tenant 404')
    out = _once(out,
      '                PublicationEffect.work_id == work_id\n            )',
      '                PublicationEffect.work_id == work_id,\n                PublicationEffect.tenant == tenant\n            )',
      'effect tenant filter')
    out = _once(out,
      '                PublicationReceipt.work_id == work_id\n            )',
      '                PublicationReceipt.work_id == work_id,\n                PublicationReceipt.tenant == tenant\n            )',
      'receipt tenant filter')
    out = _once(out,
      '        "last_error": snapshot.get("last_error"),',
      '        "error_present": bool(snapshot.get("last_error")),',
      'redact internal failure text')
    out = _once(out,
      'def get_publication_status(work_id: str) -> Dict[str, Any]:',
      'def get_publication_status(work_id: str, current_user: CurrentUser) -> Dict[str, Any]:',
      'JWT required status endpoint')
    out = _once(out,
      '    from app.core.database import SessionLocal\n    return _get_job_status(work_id, SessionLocal)',
      '''    from app.core.database import SessionLocal
    # Role and tenant are derived from the authenticated session, NEVER query
    # parameters or X-User-Role headers. Missing tenant -> 403, no fallback.
    role = str(getattr(current_user, "role", "")).lower().strip().replace(" ", "_")
    tenant = getattr(current_user, "tenant_id", None)
    if role not in {"admin", "compliance_officer", "reviewer"} or not tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="authorized tenant-scoped reviewer required")
    return _get_job_status(work_id, SessionLocal, tenant=tenant)''',
      'JWT tenant and role guard')
    out = _once(out,
      'from fastapi import APIRouter, Depends, HTTPException, status',
      'from fastapi import APIRouter, Depends, HTTPException, status\nfrom app.api.deps import CurrentUser',
      'JWT dependency import')
    return out


def build_patch(repo: str | Path, *, expected_blobs: dict | None = None) -> dict:
    """Read all expected files and compute every diff without writing any."""
    # Wave 2.5 builder is the strict baseline source validator.
    first = w25.build_patch(repo, expected_blobs=expected_blobs)
    transformations = {
        'backend/amc_publication/worker.py': harden_worker26,
        'backend/amc_publication/journal.py': harden_journal26,
        'backend/app/api/routes/governance.py': harden_governance26,
    }
    root = Path(repo).resolve()
    expected_blobs = REVIEWED_GIT_BLOBS if expected_blobs is None else expected_blobs
    result = {}
    for rel, fn in transformations.items():
        original = (root/rel).read_text(encoding='utf-8')
        revised = fn(first[rel]['new'])
        compile(revised,rel,'exec')
        result[rel] = {
            'original_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'new_sha256': hashlib.sha256(revised.encode()).hexdigest(),
            'diff': ''.join(difflib.unified_diff(original.splitlines(True),revised.splitlines(True),
                    fromfile='a/'+rel,tofile='b/'+rel)),
            'new': revised,
        }
    # Two additional exact-Git-blob reviewed sources.
    for relative, transform in (
        ('backend/amc_publication/faiss_artifacts.py', harden_faiss26),
        ('backend/amc_publication/status_route.py', harden_status_route26),
    ):
        path=root/relative
        if path.is_symlink() or not path.is_file():
            raise SourceDrift('required reviewed source missing or unsafe: '+relative)
        w25.verify_git_blob(path, expected_blobs.get(relative))
        original=path.read_text(encoding='utf-8')
        revised=transform(original)
        compile(revised,relative,'exec')
        result[relative]={'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'new_sha256':hashlib.sha256(revised.encode()).hexdigest(),
            'diff':''.join(difflib.unified_diff(original.splitlines(True),revised.splitlines(True),
                      fromfile='a/'+relative,tofile='b/'+relative)),
            'new':revised}
    return result


def apply(repo: str | Path, *, apply_changes: bool = False, expected_blobs: dict | None = None) -> dict:
    patches = build_patch(repo, expected_blobs=expected_blobs)
    summary={'status':'DRY_RUN', 'files':{k:{x:v for x,v in d.items() if x!='new'} for k,d in patches.items()}}
    if not apply_changes:
        return summary
    root=Path(repo).resolve()
    for rel in patches:
        if (root/(rel+'.wave26.bak')).exists():
            raise SourceDrift('Wave 2.6 backup already exists: '+rel)
    for rel in patches:
        shutil.copy2(root/rel, root/(rel+'.wave26.bak'))
    for rel, data in patches.items():
        (root/rel).write_text(data['new'],encoding='utf-8',newline='\n')
    summary['status']='APPLIED_REVIEW_REQUIRED'
    return summary
