from dataclasses import dataclass
import pytest
from amc_publication.request_fence29 import VerifiedOrchestratorFence29
from amc_publication.serving27 import ServingDenied

@dataclass
class Generation:
    tenant:str='alpha'
    generation_id:str='a'*64
    digest:str='a'*64
    epoch:int=3
    work_id:str='pub-1'
    receipt_id:str='rcpt-1'

class Reader:
    def __init__(self):self.g=Generation();self.calls=0
    async def assert_serving_authority(self,tenant):
        self.calls+=1
        if tenant!=getattr(self.g,'tenant',tenant):raise ServingDenied('tenant')
        return self.g

class Delegate:
    def __init__(self,reader):self.reader=reader;self.actions=[];self.mutate=False
    async def answer(self,*a,**k):
        self.actions.append('answer')
        if self.mutate:self.reader.g=Generation(epoch=4)
        return {'answer':'ok'}
    async def traditional_search(self,*a,**k):
        self.actions.append('traditional')
        if self.mutate:self.reader.g=Generation(receipt_id='other')
        return [{'chunk_id':'a'}]
    async def answer_stream(self,*a,**k):
        self.actions.append('stream')
        yield {'type':'answer_chunk','text':'first'}
        if self.mutate:self.reader.g=Generation(work_id='replaced')
        yield {'type':'complete'}

@pytest.fixture
def pair(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    r=Reader();d=Delegate(r)
    return VerifiedOrchestratorFence29(d,r),r,d

@pytest.mark.asyncio
async def test_answer_pins_receipt_before_after(pair):
    g,r,d=pair
    assert await g.answer('q',tenant_id='alpha')=={'answer':'ok'}
    assert r.calls==2

@pytest.mark.asyncio
async def test_answer_revoked_during_build_is_rejected(pair):
    g,r,d=pair;d.mutate=True
    with pytest.raises(ServingDenied):await g.answer('q',tenant_id='alpha')

@pytest.mark.asyncio
async def test_traditional_path_receipt_replacement_rejected(pair):
    g,r,d=pair;d.mutate=True
    with pytest.raises(ServingDenied):await g.traditional_search('q',tenant_id='alpha')

@pytest.mark.asyncio
async def test_stream_buffered_and_verified(pair):
    g,r,d=pair
    events=[x async for x in g.answer_stream('q',tenant_id='alpha')]
    assert [x['type'] for x in events]==['answer_chunk','complete']
    assert r.calls>=4

@pytest.mark.asyncio
async def test_stream_rejects_before_first_frame_if_revoked(pair):
    g,r,d=pair;d.mutate=True
    items=[]
    with pytest.raises(ServingDenied):
        async for frame in g.answer_stream('q',tenant_id='alpha'):items.append(frame)
    assert items==[]

@pytest.mark.asyncio
async def test_stream_overflow_denied(pair):
    g,r,d=pair;g.MAX_BYTES=10
    with pytest.raises(ServingDenied,match='buffered'):
        async for _ in g.answer_stream('q',tenant_id='alpha'):pass

@pytest.mark.asyncio
async def test_stream_rechecks_during_frame_delivery(pair):
    g,r,d=pair
    itr=g.answer_stream('q',tenant_id='alpha')
    first=await anext(itr)
    assert first['type']=='answer_chunk'
    r.g=Generation(epoch=10)
    with pytest.raises(ServingDenied):await anext(itr)

@pytest.mark.parametrize('route',['answer','traditional_search','answer_stream'])
@pytest.mark.asyncio
async def test_missing_tenant_blocks_all_routes(pair,route):
    g,r,d=pair
    with pytest.raises(ServingDenied):
        value=getattr(g,route)('q')
        if route=='answer_stream':[x async for x in value]
        else:await value
    assert d.actions==[]

@pytest.mark.asyncio
async def test_legacy_mode_remains_compatible(monkeypatch,pair):
    g,r,d=pair
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','off')
    assert await g.answer('q')=={'answer':'ok'}
    assert r.calls==0
    assert [x async for x in g.answer_stream('q')]

@pytest.mark.asyncio
async def test_unknown_mode_denied(monkeypatch,pair):
    g,r,d=pair
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','ENFORCE')
    with pytest.raises(ServingDenied):await g.answer('q',tenant_id='alpha')

@pytest.mark.asyncio
async def test_invalid_generation_identity_denied(pair):
    g,r,d=pair;r.g={'tenant':'alpha'}
    with pytest.raises(ServingDenied):await g.answer('q',tenant_id='alpha')
