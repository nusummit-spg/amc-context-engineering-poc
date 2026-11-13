"""Real SQLAlchemy/SQLite tests for upgraded Wave 2.6 pointer CAS.

The PostgreSQL row-lock behavior still requires separate live integration evidence.
"""
from pathlib import Path
import importlib.util
import sys
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from amc_publication.models import Base, GenerationPointer
from amc_publication.types import Conflict
from tools.amc_release.publication_patch26 import harden_journal26
from tools.amc_release.tests.test_wave25_atomic_recovery import journal_class

@pytest.fixture
def session_env(tmp_path):
    # Compose Wave 2.6 on the independently executed Wave 2.5 SQL journal.
    cls=journal_class(tmp_path)
    src=(tmp_path/'journal25.py').read_text()
    hardened=harden_journal26(src)
    new=(tmp_path/'journal26.py');new.write_text(hardened)
    spec=importlib.util.spec_from_file_location('amc_publication.journal26_sqltest',new)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module;spec.loader.exec_module(module)
    eng=create_engine('sqlite:///'+str(tmp_path/'db.sqlite'))
    Base.metadata.create_all(eng)
    sessions=sessionmaker(bind=eng,expire_on_commit=False)
    journal=module.Journal(sessions)
    yield sessions,journal
    eng.dispose()

def payload():
    return {'entity':'ent','attribute':'name','corrected_value':'new',
            'full_vector_snapshot':[{'tenant_id':'t','chunk_id':'1','text':'source'}]}


def test_exact_pointer_readback_and_one_step_replay(session_env):
    sessions,j=session_env
    wid=j.submit(tenant='t',key='k1',proposal_id='p1',revision=1,payload=payload())
    claim=j.claim('worker')
    prior=j.pointer('t')
    j.switch_pointer(claim,namespace='vector_faiss',expected=prior,new_id='g1',digest='d1')
    assert j.pointer('t')=={'generation_id':'g1','digest':'d1','epoch':1}
    j.switch_pointer(claim,namespace='vector_faiss',expected=prior,new_id='g1',digest='d1')
    assert j.pointer('t')['epoch']==1


def test_newer_epoch_with_same_digest_cannot_be_claimed_as_replay(session_env):
    sessions,j=session_env
    wid=j.submit(tenant='t',key='k1',proposal_id='p1',revision=1,payload=payload())
    claim=j.claim('worker')
    prior=j.pointer('t')
    j.switch_pointer(claim,namespace='vector_faiss',expected=prior,new_id='g1',digest='d1')
    with sessions.begin() as s:
        p=s.get(GenerationPointer,('t','vector_faiss'))
        p.epoch=9
    with pytest.raises(Conflict,match='epoch drift'):
        j.switch_pointer(claim,namespace='vector_faiss',expected=prior,new_id='g1',digest='d1')
    assert j.pointer('t')['epoch']==9


def test_cross_generation_cas_conflict_is_fail_closed(session_env):
    sessions,j=session_env
    wid=j.submit(tenant='t',key='k1',proposal_id='p1',revision=1,payload=payload())
    claim=j.claim('worker')
    prior=j.pointer('t')
    j.switch_pointer(claim,namespace='vector_faiss',expected=prior,new_id='g1',digest='d1')
    with pytest.raises(Conflict,match='pointer changed'):
        j.switch_pointer(claim,namespace='vector_faiss',expected=prior,new_id='g2',digest='d2')
    assert j.pointer('t')['generation_id']=='g1'


def test_same_generation_on_new_job_is_idempotent_when_expected_current(session_env):
    sessions,j=session_env
    w1=j.submit(tenant='t',key='k1',proposal_id='p1',revision=1,payload=payload())
    c1=j.claim('first')
    prior=j.pointer('t')
    j.switch_pointer(c1,namespace='vector_faiss',expected=prior,new_id='g1',digest='d1')
    # A no-op snapshot staging can observe the current pointer; the identity is
    # unchanged, so no new epoch should be added for the same immutable bytes.
    current=j.pointer('t')
    j.switch_pointer(c1,namespace='vector_faiss',expected=current,new_id='g1',digest='d1')
    assert j.pointer('t')['epoch']==1
