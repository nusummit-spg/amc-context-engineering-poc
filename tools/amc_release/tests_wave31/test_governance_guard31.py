"""Source-level legacy-bypass closures plus executable HTTP status contract."""
from __future__ import annotations
from types import SimpleNamespace
import ast
import asyncio
import pytest
from fastapi import HTTPException, status
from tools.amc_release.governance_guard31 import transform, MARKER
from tools.amc_release.publication_patch25 import SourceDrift

SAMPLE='''from fastapi import HTTPException,status
from amc_publication.vector_bridge28 import verified_mode
class PromotionService:
    def __init__(self,db):self.db=db
    async def apply_approved_proposals(self,**kwargs):return {'dangerous_direct_write':True}
def require_approval_role(user):pass
class DemoUser:
    pass
@router.post('/promote')
async def promote_approved_proposals(current_user,db,batch_id=None,proposal_id=None):
    require_approval_role(current_user)
    service = PromotionService(db=db)
    try:
        result = await service.apply_approved_proposals(batch_id=batch_id, proposal_id=proposal_id, db=db)
        return {'status':'success','result':result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
@router.post("/promote/{patch_id}")
async def promote_patch_direct(patch_id):
    return patch_id
'''


def test_guard_is_compilable_and_source_locked():
    s=transform(SAMPLE)
    assert s.count(MARKER)==1
    assert s.count('Legacy direct promotion disabled')==1
    assert "async def promote_patch_direct(patch_id)" in s
    ast.parse(s)
    with pytest.raises(SourceDrift):transform(s)


def test_unexpected_direct_promotion_pattern_is_rejected():
    with pytest.raises(SourceDrift):
        transform(SAMPLE.replace('    service = PromotionService(db=db)', '    service = EvilService(db=db)'))


def test_other_endpoint_is_not_changed():
    old=SAMPLE.split('@router.post("/promote/{patch_id}")')[1]
    new=transform(SAMPLE).split('@router.post("/promote/{patch_id}")')[1]
    assert old==new


def test_guard_requires_reviewed_endpoint_order():
    with pytest.raises(SourceDrift):transform(SAMPLE.replace('@router.post("/promote/{patch_id}")','@router.post("/other")'))


def test_verified_mode_denies_before_service_invocation(monkeypatch):
    from amc_publication import vector_bridge28
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    # Isolate the function under test and make service construction raise if reached.
    source=transform(SAMPLE)
    a=source.index('async def promote_approved_proposals(')
    b=source.index('@router.post("/promote/{patch_id}")',a)
    fn_source=source[a:b]
    class NoService:
        def __init__(self,**kwargs):raise AssertionError('unsafe promotion service was invoked')
    namespace={'require_approval_role':lambda x:None, 'PromotionService':NoService,
               'HTTPException':HTTPException,'status':status,'__name__':'guard31_test'}
    exec(compile(fn_source,'governance.py','exec'),namespace)
    with pytest.raises(HTTPException) as e:
        asyncio.run(namespace['promote_approved_proposals'](object(),object()))
    assert e.value.status_code==503


def test_legacy_off_mode_retains_existing_functionality(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','off')
    source=transform(SAMPLE)
    a=source.index('async def promote_approved_proposals(')
    b=source.index('@router.post("/promote/{patch_id}")',a)
    class StubService:
        def __init__(self, db):pass
        async def apply_approved_proposals(self,**kwargs):return {'legacy':True}
    ns={'require_approval_role':lambda x:None,'PromotionService':StubService,
        'HTTPException':HTTPException,'status':status}
    exec(compile(source[a:b],'test.py','exec'),ns)
    res=asyncio.run(ns['promote_approved_proposals'](object(),object()))
    assert res['status']=='success' and res['result']['legacy'] is True


def test_malformed_mode_fails_closed(monkeypatch):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enyforce')
    source=transform(SAMPLE)
    a=source.index('async def promote_approved_proposals(')
    b=source.index('@router.post("/promote/{patch_id}")',a)
    ns={'require_approval_role':lambda x:None,'PromotionService':lambda **x: None,'HTTPException':HTTPException,'status':status}
    exec(compile(source[a:b],'test.py','exec'),ns)
    with pytest.raises(RuntimeError):
        asyncio.run(ns['promote_approved_proposals'](object(),object()))
