"""Real SQLite authority replay validation and physical search race denial.
Run with PYTHONPATH=test_support/wave30_fixture/backend:.:backend.
"""
from types import SimpleNamespace
import os
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amc_publication.active_authority28 import (ActiveReceiptAuthority,
    AuthorityPreimage, suspend_before_graph)
from amc_publication.models import Base, GenerationPointer, PublicationEffect
from amc_publication.journal import Journal
from amc_publication.serving27 import ServingDenied, VerifiedServingGeneration
from amc_publication.faiss_reader27 import VerifiedFaissRetriever
from amc_publication.vector_bridge28 import VerifiedVectorBridge
from amc_publication.types import Conflict, sha256_json


@pytest.fixture
def env(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'authority.sqlite'))
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    journal=Journal(sessions)
    job=journal.submit(tenant='T',key='newjob',proposal_id='prop',revision=1,
        payload={'entity':'entity','attribute':'NAV','corrected_value':'42',
                 'full_vector_snapshot':[{'tenant_id':'T','chunk_id':'a','text':'text'}]})
    claim=journal.claim('worker')
    yield sessions,claim
    engine.dispose()


def make_replay(sessions,claim,*,state='SUSPENDED',suspended_by=None,
                old_auth=True,prev_receipt='oldrcpt',ptr_generation='oldgen'):
    with sessions.begin() as s:
        s.add(AuthorityPreimage(work_id=claim.work_id,tenant='T',namespace='vector_faiss',
            previous_generation='oldgen',previous_digest='oldgen',
            previous_work_id='oldjob' if prev_receipt else None,
            previous_receipt_id=prev_receipt))
        if old_auth:
            s.add(ActiveReceiptAuthority(tenant='T',namespace='vector_faiss',
                generation_id='oldgen',digest='oldgen',pointer_epoch=1,
                work_id='oldjob',receipt_id='oldrcpt',
                status=state,suspended_by=suspended_by))
        if ptr_generation:
            s.add(GenerationPointer(tenant='T',namespace='vector_faiss',
                generation_id=ptr_generation,artifact_digest=ptr_generation,epoch=1))


def test_replay_does_not_reactivate_old_active_authority(env):
    sessions,claim=env
    make_replay(sessions,claim,state='ACTIVE')
    with pytest.raises(Conflict,match='no longer owns'):
        with sessions.begin() as s:suspend_before_graph(s,claim)


def test_replay_does_not_override_someone_elses_suspension(env):
    sessions,claim=env
    make_replay(sessions,claim,suspended_by='other-job')
    with pytest.raises(Conflict,match='no longer owns'):
        with sessions.begin() as s:suspend_before_graph(s,claim)


def test_replay_does_not_accept_lost_previous_authority(env):
    sessions,claim=env
    make_replay(sessions,claim,old_auth=False)
    with pytest.raises(Conflict,match='disappeared'):
        with sessions.begin() as s:suspend_before_graph(s,claim)


def test_replay_owns_original_suspension(env):
    sessions,claim=env
    make_replay(sessions,claim,suspended_by=claim.work_id)
    with sessions.begin() as s:suspend_before_graph(s,claim)


def test_replay_rejects_pointer_from_unrelated_generation(env):
    sessions,claim=env
    make_replay(sessions,claim,suspended_by=claim.work_id,ptr_generation='foreign')
    with pytest.raises(Conflict,match='unrelated generation'):
        with sessions.begin() as s:suspend_before_graph(s,claim)


def test_replay_accepts_own_prepared_vector_pointer(env):
    sessions,claim=env
    make_replay(sessions,claim,suspended_by=claim.work_id,ptr_generation='my-new-gen')
    with sessions.begin() as s:
        post={'generation_id':'my-new-gen','digest':'my-new-gen','count':1}
        pre={'generation_id':'oldgen','digest':'oldgen'}
        s.add(PublicationEffect(id='eff_1',work_id=claim.work_id,tenant='T',kind='vector',
            target='entity',preimage=pre,postimage=post,pre_hash=sha256_json(pre),
            post_hash=sha256_json(post),claim_epoch=claim.epoch,state='verified'))
    with sessions.begin() as s:suspend_before_graph(s,claim)


class FakeIndex:
    d=2
    def __init__(self, on_search=lambda:None):self.on_search=on_search
    def search(self, x, count):
        self.on_search()
        return np.array([[0.7]],dtype=float),np.array([[1]],dtype=int)

class FakeFAISS:
    @staticmethod
    def normalize_L2(m):pass

class FakeStore:
    @staticmethod
    def _imports():return FakeFAISS,np

class FakeResolver:
    def __init__(self, change=None):
        self.gen=VerifiedServingGeneration('T','d'*64,'d'*64,4,'work','receipt',1)
        self.binding=('d'*64,'d'*64,4,'work','receipt')
        self.change=change
    def resolve_for_serving(self, tenant, **kw):return self.gen
    def _pointer(self,tenant):return ('d'*64,'d'*64,4)
    def _receipt(self,*args):return ('work','receipt',1)
    def _authority(self,tenant):
        if self.change=='suspend':raise ServingDenied('authority suspended')
        if self.change=='replace':return ('z'*64,'z'*64,5,'new-work','new-receipt')
        return self.binding


def make_retriever(on_search=None, with_authority=True):
    retriever=VerifiedFaissRetriever.__new__(VerifiedFaissRetriever)
    res=FakeResolver()
    if not with_authority:
        res._authority=None
    idx=FakeIndex(on_search or (lambda:None))
    retriever.resolver=res
    retriever.store=FakeStore()
    retriever._loaded={'T':('d'*64,'d'*64,idx,[{'chunk_id':'c1','tenant_id':'T','text':'x'}])}
    return retriever


def test_faiss_fails_if_suspended_during_physical_search(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    r=make_retriever()
    r._loaded['T'][2].on_search=lambda:setattr(r.resolver,'change','suspend')
    with pytest.raises(ServingDenied,match='suspended'):
        r.search('T',[.2,.8])


def test_faiss_fails_if_receipt_replaced_during_physical_search(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    r=make_retriever()
    r._loaded['T'][2].on_search=lambda:setattr(r.resolver,'change','replace')
    with pytest.raises(ServingDenied,match='changed'):
        r.search('T',[.2,.8])


def test_faiss_does_not_accept_legacy_resolver_in_enforced_mode(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    r=make_retriever(with_authority=False)
    with pytest.raises(ServingDenied,match='resolver missing'):
        r.search('T',[.2,.8])


def test_faiss_valid_unchanged_authority_produces_hit(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    r=make_retriever()
    out=r.search('T',[.2,.8])
    assert len(out)==1 and out[0]['chunk_id']=='c1'

class BridgeReader:
    def __init__(self):
        self.binding=('d'*64,'d'*64,4,'work','receipt')
        self.resolver=self
        self.on_search=lambda:None
    def _authority(self,tenant):
        if self.binding is None:raise ServingDenied('revoked')
        return self.binding
    def search(self,tenant,embedding,*,limit):
        self.on_search()
        return [{'chunk_id':'c1','score':.9,'document':{'tenant_id':'T','chunk_id':'c1','text':'x'}}]

@pytest.mark.asyncio
async def test_bridge_stale_hits_not_returned_after_authority_replaced(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    reader=BridgeReader()
    reader.on_search=lambda:setattr(reader,'binding',('e'*64,'e'*64,5,'work2','receipt2'))
    bridge=VerifiedVectorBridge(embedder=None,retriever=reader,tenant_id='T')
    with pytest.raises(ServingDenied,match='changed'):
        await bridge.similarity_search(embedding=[.1,.2])

@pytest.mark.asyncio
async def test_bridge_stale_hits_not_returned_after_authority_revoked(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    reader=BridgeReader()
    reader.on_search=lambda:setattr(reader,'binding',None)
    bridge=VerifiedVectorBridge(embedder=None,retriever=reader,tenant_id='T')
    with pytest.raises(ServingDenied,match='revoked'):
        await bridge.similarity_search(embedding=[.1,.2])

@pytest.mark.asyncio
async def test_bridge_accepts_stable_authority(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    bridge=VerifiedVectorBridge(embedder=None,retriever=BridgeReader(),tenant_id='T')
    out=await bridge.similarity_search(embedding=[.1,.2])
    assert [x['chunk_id'] for x in out]==['c1']

@pytest.mark.asyncio
async def test_bridge_fails_when_resolver_cannot_attest_authority(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    reader=BridgeReader()
    reader.resolver=SimpleNamespace()
    bridge=VerifiedVectorBridge(embedder=None,retriever=reader,tenant_id='T')
    with pytest.raises(ServingDenied,match='probe required'):
        await bridge.similarity_search(embedding=[.1,.2])
