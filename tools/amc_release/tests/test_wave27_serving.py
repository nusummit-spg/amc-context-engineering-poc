"""SQLite + real baseline journal + verified JSON bytes; no live FAISS claim."""
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from amc_publication.models import (Base, PublicationWork, PublicationReceipt,
                                    PublicationEffect, GenerationPointer)
from amc_publication.journal import Journal
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.serving27 import VerifiedGenerationResolver, ServingDenied
from amc_publication.types import Conflict


@pytest.fixture
def env(tmp_path):
    engine = create_engine('sqlite:///'+str(tmp_path/'publication.db'))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine,expire_on_commit=False)
    store = ImmutableSnapshotStore(tmp_path/'immutable')
    ledger = Journal(sessions)
    yield {'sessions':sessions,'journal':ledger,'store':store}
    engine.dispose()


def published(env,tenant='tenant_A',suffix='1',docs=None):
    j=env['journal'];store=env['store'];sessions=env['sessions']
    docs = docs or [{'tenant_id':tenant,'chunk_id':f'chunk-{suffix}','text':'verified evidence '+suffix}]
    gen=store.stage(tenant,docs)
    wid=j.submit(tenant=tenant,key='pub-'+suffix,proposal_id='proposal-'+suffix,revision=1,
        payload={'entity':'entity-'+suffix,'attribute':'name','corrected_value':'new','full_vector_snapshot':docs})
    claim=j.claim('worker-'+suffix)
    assert claim and claim.work_id==wid
    pre=j.pointer(tenant)
    j.prepare(claim,kind='vector',target='entity-'+suffix,pre=pre,
        post={'generation_id':gen.generation_id,'digest':gen.digest,'count':gen.count})
    j.prepare(claim,kind='graph',target='entity-'+suffix,pre={'value':'old'},post={'value':'new'})
    j.verified(claim,kind='graph',target='entity-'+suffix,observed={'value':'new'})
    j.switch_pointer(claim,namespace='vector_faiss',expected=pre,new_id=gen.digest,digest=gen.digest)
    j.verified(claim,kind='vector',target='entity-'+suffix,
               observed={'generation_id':gen.generation_id,'digest':gen.digest,'count':gen.count})
    rid=j.publish(claim)
    return wid,rid,gen


def resolver(env,loader=None):
    return VerifiedGenerationResolver(env['sessions'],env['store'],serving_loader=loader or (lambda *x: True))


def test_real_journal_generation_eligible(env):
    wid,rid,gen=published(env)
    item=resolver(env).resolve_for_serving('tenant_A')
    assert (item.work_id,item.receipt_id,item.digest,item.document_count,item.epoch)==(wid,rid,gen.digest,1,1)


def test_exact_identity_scope(env):
    wid,rid,gen=published(env)
    item=resolver(env).resolve_for_serving('tenant_A',work_id=wid,receipt_id=rid)
    assert item.tenant=='tenant_A'

@pytest.mark.parametrize('tenant',['',None,' ','missing','tenant_B'])
def test_invalid_tenant_fails_closed(env,tenant):
    published(env)
    with pytest.raises(ServingDenied): resolver(env).resolve_for_serving(tenant)

@pytest.mark.parametrize('work,receipt',[('wrong',None),(None,'wrong'),('wrong','wrong'),('',None),(None,'')])
def test_bad_work_receipt_scope_rejected(env,work,receipt):
    published(env)
    with pytest.raises(ServingDenied): resolver(env).resolve_for_serving('tenant_A',work_id=work,receipt_id=receipt)


def test_reader_proof_mandatory(env):
    with pytest.raises(ValueError): VerifiedGenerationResolver(env['sessions'],env['store'],serving_loader=None)


def test_artifact_verifier_mandatory(env):
    with pytest.raises(ValueError): VerifiedGenerationResolver(env['sessions'],object(),serving_loader=lambda *x:True)


def test_reader_not_loaded_fails(env):
    published(env)
    with pytest.raises(ServingDenied,match='not loaded'):resolver(env,lambda *x:False).resolve_for_serving('tenant_A')


def test_pointer_changed_while_reader_loading_fails(env):
    published(env)
    def mutate(*x):
        with env['sessions'].begin() as s:
            p=s.get(GenerationPointer,('tenant_A','vector_faiss'))
            p.epoch += 1
        return True
    with pytest.raises(ServingDenied,match='pointer changed'):resolver(env,mutate).resolve_for_serving('tenant_A')


def test_missing_artifact_fails(env):
    wid,rid,gen=published(env)
    (env['store']._path(gen.digest)/'snapshot.json').unlink()
    with pytest.raises(Exception):resolver(env).resolve_for_serving('tenant_A')


def test_mutated_artifact_fails(env):
    wid,rid,gen=published(env)
    (env['store']._path(gen.digest)/'snapshot.json').write_text('{}')
    with pytest.raises(Exception):resolver(env).resolve_for_serving('tenant_A')


def test_missing_verified_receipt_fails(env):
    wid,rid,gen=published(env)
    with env['sessions'].begin() as s:
        s.get(PublicationReceipt,rid).verified=False
    with pytest.raises(ServingDenied):resolver(env).resolve_for_serving('tenant_A')


def test_job_failed_or_rolled_back_cannot_serve(env):
    wid,rid,gen=published(env)
    for bad in ('failed','rolled_back','rollback_pending','leased'):
        with env['sessions'].begin() as s:s.get(PublicationWork,wid).status=bad
        with pytest.raises(ServingDenied):resolver(env).resolve_for_serving('tenant_A')


def test_effect_not_verified_fails(env):
    wid,rid,gen=published(env)
    with env['sessions'].begin() as s:
        graph=s.scalar(select(PublicationEffect).where(PublicationEffect.work_id==wid,PublicationEffect.kind=='graph'))
        graph.state='prepared'
    with pytest.raises(ServingDenied):resolver(env).resolve_for_serving('tenant_A')


def test_graph_hash_tamper_fails(env):
    wid,rid,gen=published(env)
    with env['sessions'].begin() as s:s.get(PublicationReceipt,rid).graph_hash='0'*64
    with pytest.raises(ServingDenied):resolver(env).resolve_for_serving('tenant_A')


def test_vector_count_mismatch_fails(env):
    wid,rid,gen=published(env)
    with env['sessions'].begin() as s:
        effect=s.scalar(select(PublicationEffect).where(PublicationEffect.work_id==wid,PublicationEffect.kind=='vector'))
        effect.postimage={**effect.postimage,'count':90}
        from amc_publication.types import sha256_json
        effect.post_hash=sha256_json(effect.postimage)
    with pytest.raises(ServingDenied):resolver(env).resolve_for_serving('tenant_A')


def test_pointer_without_published_receipt_fails(env):
    gen=env['store'].stage('tenant_A',[{'tenant_id':'tenant_A','chunk_id':'z','text':'x'}])
    with env['sessions'].begin() as s:
        s.add(GenerationPointer(tenant='tenant_A',namespace='vector_faiss',generation_id=gen.digest,
                                artifact_digest=gen.digest,epoch=1))
    with pytest.raises(ServingDenied):resolver(env).resolve_for_serving('tenant_A')


def test_initial_activation_probe_does_not_claim_publication(env):
    gen=env['store'].stage('tenant_A',[{'tenant_id':'tenant_A','chunk_id':'z','text':'x'}])
    with env['sessions'].begin() as s:
        s.add(GenerationPointer(tenant='tenant_A',namespace='vector_faiss',generation_id=gen.digest,
                                artifact_digest=gen.digest,epoch=1))
    subject=resolver(env)
    assert subject.probe_activation('tenant_A',gen.digest,gen.digest) is True
    with pytest.raises(ServingDenied):subject.resolve_for_serving('tenant_A')


def test_activation_probe_stale_digest_fails(env):
    _,_,gen=published(env)
    with pytest.raises(ServingDenied):resolver(env).probe_activation('tenant_A','f'*64,'f'*64)


def test_activation_probe_failed_loader_fails(env):
    _,_,gen=published(env)
    with pytest.raises(ServingDenied):resolver(env,lambda *x:False).probe_activation('tenant_A',gen.digest,gen.digest)


def test_ambiguous_two_published_receipts_same_generation_fails(env):
    wid,rid,gen=published(env)
    # Another legitimate publication can share the same immutable content-addressed generation.
    with env['sessions'].begin() as s:
        first=s.get(PublicationWork,wid)
        copy=PublicationWork(id='dup_work',tenant='tenant_A',idempotency_key='dup',proposal_id='dup',
            approved_revision=1,payload_hash=first.payload_hash,payload=first.payload,status='published')
        s.add(copy)
        s.flush()
        s.add(PublicationReceipt(id='dup_receipt',work_id=copy.id,tenant='tenant_A',
             graph_hash=s.get(PublicationReceipt,rid).graph_hash,
             generation_id=gen.generation_id,generation_digest=gen.digest,verified=True))
        old=s.scalars(select(PublicationEffect).where(PublicationEffect.work_id==wid)).all()
        for e in old:
            s.add(PublicationEffect(id='dup_'+e.id,work_id=copy.id,tenant='tenant_A',kind=e.kind,
                target=e.target,preimage=e.preimage,postimage=e.postimage,pre_hash=e.pre_hash,
                post_hash=e.post_hash,state=e.state,claim_epoch=e.claim_epoch,verified_at=e.verified_at))
    with pytest.raises(ServingDenied,match='unique'):resolver(env).resolve_for_serving('tenant_A')
    assert resolver(env).resolve_for_serving('tenant_A',work_id=wid,receipt_id=rid).receipt_id==rid


def test_receipt_removed_midvalidation_fails(env):
    wid,rid,gen=published(env)
    def revoke(*x):
        with env['sessions'].begin() as s:s.get(PublicationReceipt,rid).verified=False
        return True
    with pytest.raises(ServingDenied):resolver(env,revoke).resolve_for_serving('tenant_A')
