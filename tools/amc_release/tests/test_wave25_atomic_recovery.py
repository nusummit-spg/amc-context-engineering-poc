"""Exercise the Wave 2.5 atomic SQL rollback with the real Wave 1.9 models.

Reconstruct only the current GitHub `switch_back` method over the earlier
independent Journal in a disposable module; patch it, then execute SQLite SQL.
This is *not* a checkout of the full latest repository or PostgreSQL test.
"""
import importlib.util
import sys
from pathlib import Path
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

W19 = Path(__file__).resolve().parents[3] / 'backend'
if not (W19/'amc_publication/models.py').is_file():
    W19 = Path(__file__).resolve().parents[3] / 'test_support/baseline/backend'
if W19.exists(): sys.path.insert(0,str(W19))
from amc_publication.models import Base, PublicationEffect, PublicationWork, utcnow
from amc_publication.types import Conflict

TEST_DIR=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('publication_patch25',TEST_DIR.parent/'publication_patch25.py')
patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
from tools.amc_release.tests.test_wave25_patcher import JOURNAL


def journal_class(tmp_path):
    # On the target repository, old source may already be patched; these tests
    # intentionally use the supplied Wave 1.9 fixture as independent baseline.
    source=(TEST_DIR/'fixtures/journal_reference_1_9.py.txt').read_text(encoding='utf-8')
    modern=JOURNAL[JOURNAL.index('    def switch_back('):]
    start=source.index('    def switch_back(')
    end=source.index('    def compensate(',start)
    rewritten=source[:start]+modern+'\n'+source[end:]
    updated=patcher.harden_journal(rewritten)
    file=tmp_path/'journal25.py'
    file.write_text(updated)
    spec=importlib.util.spec_from_file_location('amc_publication.journal25_temp',file)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module.Journal


def _payload():
    return {'entity':'entity','attribute':'name','corrected_value':'new',
            'full_vector_snapshot':[{'chunk_id':'one','tenant_id':'tenant','text':'complete'}]}

@pytest.fixture
def env(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'db.sqlite'))
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    Journal=journal_class(tmp_path)
    yield sessions,Journal(sessions,lease_seconds=5)
    engine.dispose()


def setup_publication(env):
    sessions,j=env
    work_id=j.submit(tenant='tenant',key='id1',proposal_id='proposal1',revision=1,payload=_payload())
    claim=j.claim('pub-worker')
    j.prepare(claim,kind='graph',target='entity',pre={'value':'old'},post={'value':'new'})
    j.verified(claim,kind='graph',target='entity',observed={'value':'new'})
    prior=j.pointer('tenant')
    j.prepare(claim,kind='vector',target='entity',pre=prior,post={'generation_id':'g1','digest':'d1'})
    j.switch_pointer(claim,namespace='vector_faiss',expected=prior,new_id='g1',digest='d1')
    j.verified(claim,kind='vector',target='entity',observed={'generation_id':'g1','digest':'d1'})
    j.publish(claim)
    j.request_rollback(work_id,'tenant')
    rb=j.claim('rollback-1')
    return work_id,rb


def test_first_rollback_is_atomic_and_crash_replay_idempotent(env):
    sessions,j=env
    work,claim=setup_publication(env)
    j.switch_back(claim,current_id='g1',current_digest='d1',before={'generation_id':None,'digest':None,'epoch':0},vector_target='entity')
    assert j.pointer('tenant')['generation_id'] is None
    with sessions() as s:
        effect=s.scalar(select(PublicationEffect).where(PublicationEffect.work_id==work,PublicationEffect.kind=='vector'))
        assert effect.state == 'compensated'
        record=s.get(PublicationWork,work)
        record.lease_until=utcnow()-timedelta(seconds=1)
        s.commit()
    replay=j.claim('rollback-2')
    assert replay.mode=='rollback'
    j.switch_back(replay,current_id='g1',current_digest='d1',before={'generation_id':None,'digest':None,'epoch':0},vector_target='entity')
    j.compensate(replay,'graph','entity')
    j.finish_rollback(replay)
    assert j.snapshot(work)['status']=='rolled_back'


def test_wrong_rollback_target_has_no_effect(env):
    sessions,j=env
    work,claim=setup_publication(env)
    with pytest.raises(Conflict):
        j.switch_back(claim,current_id='other',current_digest='other',before={'generation_id':None,'digest':None,'epoch':0},vector_target='entity')
    assert j.pointer('tenant')['generation_id']=='g1'


def test_wrong_preimage_fails_atomically(env):
    sessions,j=env
    work,claim=setup_publication(env)
    with pytest.raises(Conflict):
        j.switch_back(claim,current_id='g1',current_digest='d1',before={'generation_id':'malicious','digest':'evil'},vector_target='entity')
    assert j.pointer('tenant')['generation_id']=='g1'
    with sessions() as s:
        effect=s.scalar(select(PublicationEffect).where(PublicationEffect.work_id==work,PublicationEffect.kind=='vector'))
        assert effect.state=='verified'


def test_invalid_missing_vector_target_is_blocked(env):
    sessions,j=env
    _,claim=setup_publication(env)
    with pytest.raises(Conflict):
        j.switch_back(claim,current_id='g1',current_digest='d1',before={'generation_id':None,'digest':None,'epoch':0})
    assert j.pointer('tenant')['generation_id']=='g1'


def test_empty_corpus_cannot_enter_publication_queue(env):
    sessions,j=env
    broken=_payload();broken['full_vector_snapshot']=[]
    with pytest.raises(ValueError,match='nonempty'):
        j.submit(tenant='tenant',key='broken',proposal_id='p',revision=1,payload=broken)
    with sessions() as s:
        assert s.query(PublicationWork).count()==0
