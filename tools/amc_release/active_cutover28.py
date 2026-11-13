"""Wave 2.8 source-locked integration patch: authority, vector read cutover, bypass closure.

Run only after Wave 2.6/2.7 patchers on a reviewed feature branch.
All edits are dry-run by default; source drift raises an error. This tool is not
an assurance that production services were exercised.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from .publication_patch25 import SourceDrift, _once
from .app_wiring27 import git_blob

REVIEWED_BASE = '2c0415c4d23a3338428c8314c869299aa0ab771f'
UNCHANGED_BLOBS = {
 'backend/app/vector/client.py':'f32c6154a18daceab4584d18e317c6abe6142304',
 'backend/app/retrieval/orchestrator.py':'c1275a913e0f6f64e21e9b667550b3bfdececa7d',
 'backend/app/api/routes/query.py':'a0e4c7d2ddf3155723e29a74783d5ea3fde1a912',
}


def journal28(src: str) -> str:
    if 'W28_ACTIVE_RECEIPT_AUTHORITY' in src:raise SourceDrift('Wave 2.8 journal already applied')
    if 'W26_POINTER_ROW_LOCK' not in src or 'W25_ATOMIC_ROLLBACK' not in src:
        raise SourceDrift('Wave 2.5/2.6 publication journal required')
    s=_once(src,
        'from .types import Claim, Conflict, LeaseLost, PublicationError, sha256_json',
        'from .types import Claim, Conflict, LeaseLost, PublicationError, sha256_json\n'
        '# W28_ACTIVE_RECEIPT_AUTHORITY: register sidecar schema and atomic helpers.\n'
        'from .active_authority28 import (suspend_before_graph, bind_published,\n'
        '    suspend_rollback, restore_after_rollback)',
        'import authority schema')
    # Original preimage and authority revocation must be durable before graph CAS.
    s=_once(s,
        '            s.add(PublicationEffect(\n',
        '            if kind == "graph":\n'
        '                suspend_before_graph(s, claim)\n'
        '            s.add(PublicationEffect(\n',
        'block serving before graph mutation')
    s=_once(s,
        '            s.add(receipt)\n            row.status, row.owner, row.lease_until, row.last_error = "published", None, None, None',
        '            s.add(receipt)\n            s.flush()\n'
        '            bind_published(s, claim, receipt)\n'
        '            row.status, row.owner, row.lease_until, row.last_error = "published", None, None, None',
        'atomic receipt/authority binding')
    s=_once(s,
        '            row.status = "rollback_pending"\n            row.last_error = "ROLLBACK_REQUESTED"',
        '            suspend_rollback(s, tenant=tenant, work_id=job_id)\n'
        '            row.status = "rollback_pending"\n            row.last_error = "ROLLBACK_REQUESTED"',
        'revoke serving before rollback')
    s=_once(s,
        '            row.status, row.owner, row.lease_until = "rolled_back", None, None',
        '            # Keep serving suspended until BOTH graph and vector compensated.\n'
        '            restore_after_rollback(s, claim)\n'
        '            row.status, row.owner, row.lease_until = "rolled_back", None, None',
        'final rollback / authority restoration atomicity')
    return s


def vector28(src: str) -> str:
    if 'W28_VERIFIED_READ_CUTOVER' in src:raise SourceDrift('already applied')
    a='''    base = get_base_vector_store()
    return UserScopedVectorStore(base, user_id=user_id, tenant_id=tenant_id)'''
    b='''    # W28_VERIFIED_READ_CUTOVER: explicit opt-in, never silently fall back.
    from amc_publication.vector_bridge28 import verified_mode
    if verified_mode() == 'enforce':
        from amc_publication.vector_bridge28 import create_verified_vector_store
        return create_verified_vector_store(base_client=get_base_vector_store(),
                                            user_id=user_id, tenant_id=tenant_id)
    base = get_base_vector_store()
    return UserScopedVectorStore(base, user_id=user_id, tenant_id=tenant_id)'''
    out=_once(src,a,b,'factory verified reader cutover')
    # Block direct underlying legacy readers when verified mode is active.
    # Per-method segment anchors avoid accidentally touching other conditionals.
    for method,end in [('    async def search(\n','    async def similarity_search(\n'),
                       ('    async def similarity_search(\n','    async def list_documents(\n')]:
        # The first search/similarity_search pair belong to VectorStore,
        # not UserScopedVectorStore. Protect the two base read methods.
        if out.count(method) < 1 or end not in out:
            raise SourceDrift('reviewed vector read method missing: '+method)
        begin=out.index(method)
        stop=out.index(end,begin+len(method))
        segment=out[begin:stop]
        old='        if self._index is None or self._index.ntotal == 0:\n'
        segment=_once(segment,old,
            "        from amc_publication.vector_bridge28 import verified_mode\n"
            "        if verified_mode() == 'enforce':\n"
            "            raise RuntimeError('legacy FAISS read forbidden in verified serving mode')\n" + old,
            'legacy reader blockade '+method)
        out=out[:begin]+segment+out[stop:]
    # Metadata and chunk listing are also read paths, not exempt from receipt authority.
    for method,end,anchor in [
        ('    async def list_documents(\n','    async def get_document_chunks(\n',
         '        docs: dict[str, dict] = {}\n'),
        ('    async def get_document_chunks(\n','    async def ingest_synthetic_patch_chunk(\n',
         '        chunks = []\n'),
    ]:
        if method not in out or end not in out:
            raise SourceDrift('reviewed vector metadata read method missing: '+method)
        start=out.index(method)
        stop=out.index(end,start+len(method))
        segment=out[start:stop]
        replacement=("        from amc_publication.vector_bridge28 import verified_mode\n"
          "        if verified_mode() == 'enforce':\n"
          "            raise RuntimeError('legacy FAISS metadata read forbidden in verified mode')\n"+anchor)
        segment=_once(segment,anchor,replacement,'legacy metadata/read blockade')
        out=out[:start]+segment+out[stop:]
    return out


def query28(src: str) -> str:
    if 'W28_TRADITIONAL_TENANT_SCOPE' in src:raise SourceDrift('already applied')
    return _once(src,
        '        hits = await container.orchestrator.traditional_search(query, top_k=request.top_k)',
        '''        # W28_TRADITIONAL_TENANT_SCOPE: traditional RAG is not exempt from tenant authority.
        hits = await container.orchestrator.traditional_search(
            query, top_k=request.top_k,
            user_id=current_user.username if current_user else None,
            tenant_id=current_user.tenant_id if current_user else None)''',
        'traditional route authenticates vector tenant')


def orchestrator28(src: str) -> str:
    if 'W28_ORCHESTRATOR_AUTHORITY' in src:raise SourceDrift('already applied')
    s=_once(src,'import logging\n','import logging\nimport os\n', 'import os for verified gate')
    # All non-refusal synthesis must check actual generation authority first.
    for old in (
        '        t0 = time.perf_counter()\n        req_id = str(uuid4())\n        metrics = QueryMetrics(request_id=req_id, query=query) if track_metrics else None',
        '        t0 = time.perf_counter()\n        req_id = str(uuid4())\n        response_id = f"resp_{req_id[:12]}"',
    ):
        prefix='''        # W28_ORCHESTRATOR_AUTHORITY: no cache/patch/graph answer without an active receipt.
        if os.environ.get('AMC_VERIFIED_SERVING_MODE','off') not in ('off','enforce'):
            raise ValueError('invalid verified serving mode')
        if os.environ.get('AMC_VERIFIED_SERVING_MODE','off') == 'enforce':
            from amc_publication.serving27 import ServingDenied
            if not isinstance(tenant_id, str) or not tenant_id.strip():
                raise ServingDenied('authenticated tenant required for AMC serving')
            if not callable(getattr(self._vector, 'assert_serving_authority', None)):
                raise ServingDenied('retrieval container uses an unverified vector store')
            await self._vector.assert_serving_authority(tenant_id)
'''
        s=_once(s,old,prefix+old,'orchestrator authority before cache/graph')
    # LOCAL FIX: baseline orchestrator.py has TWO reviewed fast-path imports (non-stream + stream).
    # Guard both; require exactly two so any further drift still fails closed.
    _fp='            from app.retrieval.fast_path_interceptor import get_fast_path_interceptor'
    if s.count(_fp)!=2:
        raise SourceDrift(f'disable unbound pre-retrieval fast-path: expected two reviewed anchors, found {s.count(_fp)}')
    s=s.replace(_fp,
        '''            if os.environ.get('AMC_VERIFIED_SERVING_MODE','off') == 'enforce':
                raise RuntimeError('unverified fast-path disabled in authority mode')
'''+_fp)
    lookup='cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version, user_id=user_id, tenant_id=tenant_id)'
    if s.count(lookup)!=2:raise SourceDrift('expected exactly two sync/stream cache lookups')
    s=s.replace(lookup,
        "cached_entry = (cache.lookup(effective_query, corpus_version=self._corpus_version, user_id=user_id, tenant_id=tenant_id)\n"
        "                            if os.environ.get('AMC_VERIFIED_SERVING_MODE','off') != 'enforce' else None)")
    s=_once(s,
        '        applied: list[dict] = []\n        if not entity_ids:',
        '''        applied: list[dict] = []
        if os.environ.get('AMC_VERIFIED_SERVING_MODE','off') == 'enforce':
            # Shadow patches have no current durable active receipt authority.
            return context_text, applied
        if not entity_ids:''',
        'disable unverified correction overlays')
    return s

TRANSFORM={
 'backend/amc_publication/journal.py':journal28,
 'backend/app/vector/client.py':vector28,
 'backend/app/api/routes/query.py':query28,
 'backend/app/retrieval/orchestrator.py':orchestrator28,
}

def create_plan(repo:Path):
    repo=repo.resolve()
    if not (repo/'.git').is_dir():raise SourceDrift('requires a full git checkout')
    patches={}
    for rel,transform in TRANSFORM.items():
        f=repo/rel
        if not f.is_file() or f.is_symlink():raise SourceDrift(f'missing or symlink source: {rel}')
        raw=f.read_bytes()
        if rel in UNCHANGED_BLOBS and git_blob(raw)!=UNCHANGED_BLOBS[rel]:
            raise SourceDrift(f'reviewed {rel} changed; rebase and re-review')
        old=raw.decode('utf-8')
        new=transform(old)
        compile(new,rel,'exec')
        patches[rel]=(raw,new.encode('utf-8'))
    return patches


def patch(repo:Path,*,apply=False):
    repo=repo.resolve()
    changes=create_plan(repo)
    report={'status':'DRY_RUN','files':{rel:{'before':hashlib.sha256(a).hexdigest(),
        'after':hashlib.sha256(b).hexdigest(),
        'diff':''.join(difflib.unified_diff(a.decode().splitlines(True),b.decode().splitlines(True),
             fromfile='a/'+rel,tofile='b/'+rel))}for rel,(a,b) in changes.items()}}
    if not apply:return report
    backups=[]; written=[]
    try:
        for rel in changes:
            original=repo/rel;backup=repo/(rel+'.wave28.bak')
            if backup.exists():raise SourceDrift('backup exists: '+str(backup))
        for rel,(old,_) in changes.items():
            f=repo/rel;b=repo/(rel+'.wave28.bak')
            b.parent.mkdir(parents=True,exist_ok=True)
            b.write_bytes(old);backups.append(b)
        for rel,(old,new) in changes.items():
            f=repo/rel
            if f.read_bytes()!=old:raise SourceDrift('concurrent source change: '+rel)
            f.write_bytes(new);written.append((f,old))
    except BaseException:
        for f,old in written:f.write_bytes(old)
        raise
    report['status']='PATCHED_REVIEW_REQUIRED'
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    x=parser.parse_args()
    try:
        result=patch(x.repo,apply=x.apply)
        print(json.dumps(result,indent=2))
    except (SourceDrift,OSError,UnicodeError) as exc:
        print(json.dumps({'status':'BLOCK','reason':str(exc)}))
        return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
