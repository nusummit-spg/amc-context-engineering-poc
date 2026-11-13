"""AMC orchestration search interface and strict tenant/user scopes."""
import asyncio
from dataclasses import dataclass
import pytest
from amc_publication.vector_bridge28 import VerifiedVectorBridge
from amc_publication.serving27 import ServingDenied

class FakeEmbedding:
    def __init__(self):self.calls=0
    async def embed_async(self, texts):
        self.calls+=1
        return [[1.0,0.0,0.0] for _ in texts]

class FakeReader:
    def __init__(self,hits=None):
        self.calls=[]
        self.hits=hits or []
        self.resolver=self
        self.revoked=False
    def search(self,tenant,vector,limit):
        self.calls.append((tenant,vector,limit))
        if self.revoked:raise ServingDenied('receipt revoked')
        return self.hits
    def resolve_for_serving(self,tenant):
        if self.revoked:raise ServingDenied('revoked')
        return {'tenant':tenant}

def hit(cid='chunk-1',tenant='tenantA',user=None,score=.85,meta=None,tax=None):
    doc={'chunk_id':cid,'tenant_id':tenant,'text':'source text','taxonomy_paths':tax or ['Product/Mutual Funds'],
         'metadata':meta or {'document_id':'doc1'}}
    if user is not None:doc['user_id']=user
    return {'chunk_id':cid,'score':score,'document':doc}

@pytest.fixture
def env():
    reader=FakeReader([hit(),hit('private','tenantA','alice'),hit('external','tenantB')])
    bridge=VerifiedVectorBridge(embedder=FakeEmbedding(),retriever=reader,tenant_id='tenantA',user_id='bob')
    return bridge,reader

@pytest.mark.asyncio
async def test_text_query_returns_shared_tenant_hits_only(env):
    bridge,reader=env
    with pytest.raises(ServingDenied,match='cross-tenant'):
        await bridge.search('fund nav',top_k=5)
    reader.hits=reader.hits[:2]
    result=await bridge.search('fund nav',top_k=5,taxonomy_paths=['Product/Mutual Funds'])
    assert [x['chunk_id'] for x in result]==['chunk-1']
    assert reader.calls[-1][0]=='tenantA' and reader.calls[-1][2]==100

@pytest.mark.asyncio
async def test_explicit_embedding_and_filter(env):
    bridge,reader=env
    reader.hits=[hit('a',meta={'scheme':'A'},score=2.1),hit('b',meta={'scheme':'B'})]
    results=await bridge.similarity_search(embedding=[0,1,0],limit=5,metadata_filter={'scheme':'A'})
    assert len(results)==1 and results[0]['score']==1.0 and results[0]['chunk_id']=='a'
    assert bridge._embedder.calls==0

@pytest.mark.asyncio
async def test_taxonomy_scope_does_not_fallback_to_unrelated(env):
    bridge,reader=env
    reader.hits=[hit('a',tax=['Other']),hit('b',tax=['Product/Mutual Funds'])]
    results=await bridge.search('nav',taxonomy_paths=['Product/Mutual Funds'])
    assert [x['chunk_id'] for x in results]==['b']

@pytest.mark.parametrize('tenant,user', [('tenantB',None),('',None),('tenantA','alice'),(None,'alice')])
@pytest.mark.asyncio
async def test_request_scope_cannot_override_authenticated_identity(env,tenant,user):
    bridge,reader=env
    with pytest.raises(ServingDenied):await bridge.search('x',tenant_id=tenant,user_id=user)

@pytest.mark.asyncio
async def test_unknown_or_missing_tenant_rejected():
    b=VerifiedVectorBridge(embedder=FakeEmbedding(),retriever=FakeReader(),tenant_id=None)
    with pytest.raises(ServingDenied):await b.search('x')

@pytest.mark.parametrize('limit',[0,101,True,-1,1.5])
@pytest.mark.asyncio
async def test_bad_limits_refused(env,limit):
    with pytest.raises(ValueError):await env[0].search('x',top_k=limit)

@pytest.mark.parametrize('query',['',None,{},' '])
@pytest.mark.asyncio
async def test_empty_queries_refused(env,query):
    with pytest.raises(ValueError):await env[0].search(query)

@pytest.mark.asyncio
async def test_unknown_search_kwargs_fail_closed(env):
    with pytest.raises(ServingDenied,match='unreviewed'):await env[0].search('x',unsafe_fallback=True)

@pytest.mark.asyncio
async def test_mismatched_hit_identity_fails(env):
    b,reader=env
    bad=hit()
    bad['chunk_id']='altered'
    reader.hits=[bad]
    with pytest.raises(ServingDenied,match='identity'):await b.search('x')

@pytest.mark.asyncio
async def test_duplicate_hits_fail(env):
    b,reader=env
    reader.hits=[hit(),hit()]
    with pytest.raises(ServingDenied,match='duplicate'):await b.search('x')

@pytest.mark.parametrize('score',[float('nan'),float('inf'),float('-inf')])
@pytest.mark.asyncio
async def test_invalid_scores_fail(env,score):
    b,reader=env
    reader.hits=[hit(score=score)]
    with pytest.raises(ServingDenied,match='nonfinite'):await b.search('x')

@pytest.mark.asyncio
async def test_reader_revoked_during_search_raises(env):
    b,reader=env
    reader.revoked=True
    with pytest.raises(ServingDenied,match='revoked'):await b.search('x')

@pytest.mark.asyncio
async def test_authority_explicit_check(env):
    b,reader=env
    assert (await b.assert_serving_authority('tenantA'))['tenant']=='tenantA'
    reader.revoked=True
    with pytest.raises(ServingDenied):await b.assert_serving_authority('tenantA')

@pytest.mark.asyncio
async def test_no_legacy_pass_through(env):
    b,_=env
    for method in ('client','add_documents','index_chunks','search_raw','_index'):
        with pytest.raises(ServingDenied):getattr(b,method)

@pytest.mark.asyncio
async def test_no_metadata_cross_user_leak(env):
    b,reader=env
    reader.hits=[hit('private','tenantA','alice'),hit('bobchunk','tenantA','bob')]
    result=await b.search('x')
    assert [x['chunk_id'] for x in result]==['bobchunk']

@pytest.mark.asyncio
async def test_still_requires_metadata_tenant_proof(env):
    b,reader=env
    h=hit()
    del h['document']['tenant_id']
    reader.hits=[h]
    with pytest.raises(ServingDenied):await b.search('x')
