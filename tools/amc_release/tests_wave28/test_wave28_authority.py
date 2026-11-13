"""Durable SQLite acceptance, isolated from historical unpatched fixture."""
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from amc_publication.models import Base,PublicationWork,PublicationEffect,PublicationReceipt,GenerationPointer
from amc_publication.journal import Journal
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.serving28 import ActiveReceiptResolver
from amc_publication.serving27 import ServingDenied
from amc_publication.active_authority28 import ActiveReceiptAuthority,AuthorityPreimage
from amc_publication.types import Conflict

@pytest.fixture
def env(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'auth28.sqlite'))
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    value=(Journal(sessions),sessions,ImmutableSnapshotStore(tmp_path/'snap'))
    yield value
    engine.dispose()

def publish(env, tenant='tenantA', suffix='a', docs=None):
    journal,sessions,store=env
    docs=docs or [{'tenant_id':tenant,'chunk_id':'c'+suffix,'text':'evidence '+suffix}]
    gen=store.stage(tenant,docs)
    wid=journal.submit(tenant=tenant,key='job'+suffix,proposal_id='proposal'+suffix,
            revision=1,payload={'entity':'e'+suffix,'attribute':'NAV','corrected_value':suffix,'full_vector_snapshot':docs})
    claim=journal.claim('worker'+suffix)
    assert claim and claim.work_id==wid
    before=journal.pointer(tenant)
    journal.prepare(claim,kind='vector',target='e'+suffix,pre=before,
        post={'generation_id':gen.generation_id,'digest':gen.digest,'count':gen.count})
    journal.prepare(claim,kind='graph',target='e'+suffix,pre={'value':'old'},post={'value':suffix})
    journal.verified(claim,kind='graph',target='e'+suffix,observed={'value':suffix})
    journal.switch_pointer(claim,namespace='vector_faiss',expected=before,new_id=gen.digest,digest=gen.digest)
    journal.verified(claim,kind='vector',target='e'+suffix,
        observed={'generation_id':gen.generation_id,'digest':gen.digest,'count':gen.count})
    rid=journal.publish(claim)
    return wid,rid,gen

def resolve(env,tenant='tenantA'):
    _,sessions,store=env
    return ActiveReceiptResolver(sessions,store,serving_loader=lambda *x:True).resolve_for_serving(tenant)

def rollback(env,work,tenant='tenantA',suffix='a'):
    j,sessions,store=env
    j.request_rollback(work,tenant)
    claim=j.claim('rollback'+suffix)
    assert claim and claim.work_id==work and claim.mode=='rollback'
    before=j.effect(work,'vector','e'+suffix)['pre']
    post=j.effect(work,'vector','e'+suffix)['post']
    j.switch_back(claim,current_id=post['generation_id'],current_digest=post['digest'],
                  before=before,vector_target='e'+suffix)
    j.compensate(claim,'graph','e'+suffix)
    j.finish_rollback(claim)

def test_active_receipt_bind_and_serving(env):
    wid,rid,gen=publish(env)
    x=resolve(env)
    assert (x.work_id,x.receipt_id,x.generation_id,x.document_count)==(wid,rid,gen.digest,1)
    with env[1]() as s:
        a=s.get(ActiveReceiptAuthority,('tenantA','vector_faiss'))
        assert a.status=='ACTIVE' and a.pointer_epoch==1 and a.suspended_by is None

def test_no_legacy_backfill_is_allowed(env):
    gen=env[2].stage('tenantA',[{'tenant_id':'tenantA','chunk_id':'x','text':'legacy'}])
    with env[1].begin() as s:s.add(GenerationPointer(tenant='tenantA',namespace='vector_faiss',generation_id=gen.digest,artifact_digest=gen.digest,epoch=1))
    with pytest.raises(ServingDenied):resolve(env)

def test_same_generation_new_receipt_has_exact_active_owner(env):
    docs=[{'tenant_id':'tenantA','chunk_id':'same','text':'same bytes'}]
    a,b,gen=publish(env,'tenantA','a',docs)
    c,d,_=publish(env,'tenantA','b',docs)
    x=resolve(env)
    assert x.receipt_id==d and x.work_id==c and x.generation_id==gen.digest
    with pytest.raises(ServingDenied):
        ActiveReceiptResolver(env[1],env[2],serving_loader=lambda *x:True).resolve_for_serving('tenantA',receipt_id=b)

def test_graph_preparation_suspends_previous_servable_generation(env):
    publish(env)
    j,sessions,store=env
    docs=[{'tenant_id':'tenantA','chunk_id':'c2','text':'next'}]
    wid=j.submit(tenant='tenantA',key='next',proposal_id='next',revision=1,
        payload={'entity':'e2','attribute':'NAV','corrected_value':2,'full_vector_snapshot':docs})
    claim=j.claim('new-worker')
    j.prepare(claim,kind='graph',target='e2',pre={'value':1},post={'value':2})
    with pytest.raises(ServingDenied):resolve(env)
    with sessions() as s:
        assert s.get(ActiveReceiptAuthority,('tenantA','vector_faiss')).suspended_by==wid
        assert s.get(AuthorityPreimage,wid).previous_receipt_id is not None

def test_rollback_removes_first_generation_authority(env):
    wid,rid,gen=publish(env)
    rollback(env,wid)
    with pytest.raises(ServingDenied):resolve(env)
    with env[1]() as s:
        assert s.get(ActiveReceiptAuthority,('tenantA','vector_faiss')) is None
        assert s.get(GenerationPointer,('tenantA','vector_faiss')) is None

def test_rollback_restores_previous_exact_receipt_only_after_completion(env):
    wid1,rid1,gen1=publish(env,'tenantA','a')
    wid2,rid2,gen2=publish(env,'tenantA','b')
    j,sessions,store=env
    j.request_rollback(wid2,'tenantA')
    with pytest.raises(ServingDenied):resolve(env)
    claim=j.claim('rollback-b')
    before=j.effect(wid2,'vector','eb')['pre']
    j.switch_back(claim,current_id=gen2.digest,current_digest=gen2.digest,before=before,vector_target='eb')
    # Even after pointer restoration, graph compensation not complete: no answer.
    with pytest.raises(ServingDenied):resolve(env)
    j.compensate(claim,'graph','eb')
    j.finish_rollback(claim)
    x=resolve(env)
    assert (x.work_id,x.receipt_id,x.generation_id)==(wid1,rid1,gen1.digest)
    assert x.epoch>=2

def test_forged_old_receipt_cannot_be_restored(env):
    wid1,rid1,gen1=publish(env,'tenantA','a')
    wid2,rid2,gen2=publish(env,'tenantA','b')
    j,sessions,_=env
    j.request_rollback(wid2,'tenantA')
    claim=j.claim('rollback-b')
    pre=j.effect(wid2,'vector','eb')['pre']
    j.switch_back(claim,current_id=gen2.digest,current_digest=gen2.digest,before=pre,vector_target='eb')
    j.compensate(claim,'graph','eb')
    with sessions.begin() as s:s.get(PublicationReceipt,rid1).verified=False
    with pytest.raises(Conflict,match='previous authority'):j.finish_rollback(claim)
    with pytest.raises(ServingDenied):resolve(env)

def test_tenant_isolation_and_wrong_identity(env):
    wid,rid,gen=publish(env,'tenantA','a')
    with pytest.raises(ServingDenied):resolve(env,'tenantB')
    with pytest.raises(ServingDenied):ActiveReceiptResolver(env[1],env[2],serving_loader=lambda *x:True).resolve_for_serving('tenantA',work_id='other')

def test_pointer_epoch_tamper_refuses_serving(env):
    publish(env)
    with env[1].begin() as s:s.get(GenerationPointer,('tenantA','vector_faiss')).epoch+=1
    with pytest.raises(ServingDenied):resolve(env)

def test_receipt_revocation_after_load_is_denied(env):
    wid,rid,gen=publish(env)
    def revoke(*args):
        with env[1].begin() as s:s.get(PublicationReceipt,rid).verified=False
        return True
    with pytest.raises(ServingDenied):ActiveReceiptResolver(env[1],env[2],serving_loader=revoke).resolve_for_serving('tenantA')

def test_authority_row_missing_blocks_serving_even_with_valid_receipt(env):
    publish(env)
    with env[1].begin() as s:s.delete(s.get(ActiveReceiptAuthority,('tenantA','vector_faiss')))
    with pytest.raises(ServingDenied):resolve(env)

def test_old_authority_work_rolled_back_fails_closed(env):
    wid,rid,gen=publish(env)
    with env[1].begin() as s:s.get(PublicationWork,wid).status='rolled_back'
    with pytest.raises(ServingDenied):resolve(env)
