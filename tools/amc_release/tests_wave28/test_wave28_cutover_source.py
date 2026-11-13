"""Source transformation and fail-closed cutover contracts (not full repo CI)."""
from pathlib import Path
import pytest
from tools.amc_release import active_cutover28 as c
from amc_publication.vector_bridge28 import verified_mode
from amc_publication.serving27 import ServingDenied

VECTOR='''import os
class VectorStore:
    async def search(
        self, query
    ):
        if self._index is None or self._index.ntotal == 0:
            return []
        return [1]
    async def similarity_search(
        self, embedding=None
    ):
        if self._index is None or self._index.ntotal == 0:
            return []
        return [2]
    async def list_documents(
        self
    ):
        docs: dict[str, dict] = {}
        return list(docs.values())
    async def get_document_chunks(
        self, document_id
    ):
        chunks = []
        return chunks
    async def ingest_synthetic_patch_chunk(
        self, patch_id
    ):
        return 1
class UserScopedVectorStore:
    def __init__(self,*args,**kwargs):pass
def get_base_vector_store():return VectorStore()
def get_vector_store(user_id=None,tenant_id=None):
    base = get_base_vector_store()
    return UserScopedVectorStore(base, user_id=user_id, tenant_id=tenant_id)
'''

QUERY='''async def f(container, query, request, current_user):
        hits = await container.orchestrator.traditional_search(query, top_k=request.top_k)
        return hits
'''

ORCH='''import logging
import time
from uuid import uuid4
class QueryMetrics:
    def __init__(self,**kwargs):pass
class Demo:
    async def answer(self,query,track_metrics=False,tenant_id=None):
        t0 = time.perf_counter()
        req_id = str(uuid4())
        metrics = QueryMetrics(request_id=req_id, query=query) if track_metrics else None
        try:
            from app.retrieval.fast_path_interceptor import get_fast_path_interceptor
        except Exception:
            pass
        try:
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version, user_id=user_id, tenant_id=tenant_id)
        except Exception:
            pass
    async def answer_stream(self,query,track_metrics=False,tenant_id=None):
        t0 = time.perf_counter()
        req_id = str(uuid4())
        response_id = f"resp_{req_id[:12]}"
        try:
            from app.retrieval.fast_path_interceptor import get_fast_path_interceptor
        except Exception:
            pass
        try:
            cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version, user_id=user_id, tenant_id=tenant_id)
        except Exception:
            pass
        yield None
    async def _apply_correction_patches(self,entity_ids,context_text):
        applied: list[dict] = []
        if not entity_ids:
            return context_text,applied
        return context_text, applied
'''

@pytest.mark.parametrize('mode',['ENFORCE','enforce ','true','0','disabled','on','Enforce'])
def test_typo_mode_is_never_legacy_fallback(monkeypatch,mode):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE',mode)
    with pytest.raises(ServingDenied):verified_mode()

@pytest.mark.parametrize('mode',['enforce','off'])
def test_only_explicit_supported_modes(monkeypatch,mode):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE',mode)
    assert verified_mode()==mode


def test_source_locked_vector_factory_and_base_read_denial(monkeypatch):
    src=c.vector28(VECTOR)
    assert src.count('legacy FAISS read forbidden')==2
    assert src.count('legacy FAISS metadata read forbidden')==2
    assert 'create_verified_vector_store' in src
    compile(src,'client.py','exec')
    with pytest.raises(c.SourceDrift):c.vector28(src)


def test_exact_traditional_endpoint_tenant_scope():
    new=c.query28(QUERY)
    assert 'W28_TRADITIONAL_TENANT_SCOPE' in new and 'current_user.tenant_id' in new
    compile(new,'query.py','exec')
    with pytest.raises(c.SourceDrift):c.query28(new)


def test_orchestrator_patches_both_answer_paths():
    new=c.orchestrator28(ORCH)
    assert new.count('W28_ORCHESTRATOR_AUTHORITY')==2
    assert new.count("cached_entry = (cache.lookup") == 2
    assert new.count('unverified fast-path disabled') == 2
    assert 'return context_text, applied' in new
    assert "not in ('off','enforce')" in new
    compile(new,'orchestrator.py','exec')
    with pytest.raises(c.SourceDrift):c.orchestrator28(new)


def test_unknown_or_drifted_source_refused():
    variations=[
        (c.vector28, VECTOR.replace('    base = get_base_vector_store()', '    base = None')),
        (c.query28, QUERY.replace('        hits = await container.orchestrator.traditional_search(query, top_k=request.top_k)','        hits = []')),
        (c.orchestrator28, ORCH.replace('        applied: list[dict] = []','        applied = []')),
    ]
    for transform,src in variations:
        with pytest.raises(c.SourceDrift): transform(src)


def test_synthetic_checkout_requires_complete_source(tmp_path):
    (tmp_path/'.git').mkdir()
    with pytest.raises(c.SourceDrift,match='missing'):c.create_plan(tmp_path)


def test_suspicious_git_source_blob_refused(tmp_path):
    (tmp_path/'.git').mkdir()
    for rel in c.TRANSFORM:
        f=tmp_path/rel
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_text('tampered source')
    with pytest.raises(c.SourceDrift,match='required|changed'):c.create_plan(tmp_path)
