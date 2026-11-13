"""Signed approval -> durable v1.9 journal -> graph/vector/Feedback rollback.
This is real SQLAlchemy/SQLite logic, with simulated graph and JSON artifacts;
it is *not* Neo4j/FAISS/live serving-reader acceptance.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import hmac
import importlib.util
import json
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

W19=Path(__file__).resolve().parents[3] / 'backend'
if not (W19/'amc_publication/models.py').is_file():
    W19=Path(__file__).resolve().parents[3] / 'test_support/baseline/backend'
if W19.exists():sys.path.insert(0,str(W19))
from amc_publication.models import Base,PublicationWork,PublicationReceipt
from amc_publication.graph import InMemoryGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.worker import PublicationWorker
from amc_publication.journal import Journal
from amc_publication.feedback import FeedbackCausality
from amc_publication.types import canonical_bytes

adapter_path=Path(__file__).resolve().parents[3]/'backend/amc_publication/approval_adapter.py'
spec=importlib.util.spec_from_file_location('amc_publication.approval_adapter',adapter_path)
adapter=importlib.util.module_from_spec(spec);sys.modules[spec.name]=adapter;spec.loader.exec_module(adapter)
KEY='test-only-explicit-key-00000000000000000000000'

def patch(prop,revision):
    return SimpleNamespace(patch_id=prop,tenant_id='t',version=revision,status='APPROVED',
        entity_id='ent',attribute='field',corrected_value=f'updated-{revision}',
        provenance={'proposer_username':'proposer','approver_username':'reviewer'})

def corpus(path,prop,rev,docs):
    value={'tenant':'t','proposal_id':prop,'approved_revision':rev,'source_version':f'c{rev}',
            'source_manifest_sha256':hashlib.sha256(f'catalog-{rev}'.encode()).hexdigest(),
            'complete':True,'documents':docs}
    tag=hmac.new(KEY.encode(),canonical_bytes(value),hashlib.sha256).hexdigest()
    path.write_text(json.dumps({'payload':value,'hmac_sha256':tag}))
    return path

def test_signed_approval_publish_feedback_rollback(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'db.sqlite'))
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    j=Journal(sessions)
    g=InMemoryGraphPort();g.seed('t','ent','field','before')
    store=ImmutableSnapshotStore(tmp_path/'artifacts')
    docs=[{'chunk_id':'c1','tenant_id':'t','text':'source evidence 1'},
          {'chunk_id':'c2','tenant_id':'t','text':'source evidence 2'}]
    proposal=patch('p1',1)
    signed=corpus(tmp_path/'corpus.json','p1',1,docs)
    work_id=adapter.queue_from_reviewed_patch(sessions=sessions,patch=proposal,
           actor=SimpleNamespace(username='promoter'),snapshot_path=signed,signing_key=KEY)
    assert j.snapshot(work_id)['status']=='queued'
    out=PublicationWorker(j,g,store,simulation_mode=True).run_once()
    assert out['status']=='published'
    assert j.snapshot(work_id)['status']=='published'
    assert g.read('t','ent','field')=={'value':'updated-1'}
    with sessions() as s:
        receipt=s.query(PublicationReceipt).filter_by(work_id=work_id).one()
    f=FeedbackCausality(sessions)
    assert f.resolve('t','issue1',work_id,receipt.id)
    assert f.status('t','issue1')=='resolved'
    j.request_rollback(work_id,'t')
    assert PublicationWorker(j,g,store,simulation_mode=True).run_once()['status']=='rolled_back'
    assert j.pointer('t')['generation_id'] is None
    assert g.read('t','ent','field')=={'value':'before'}
    assert f.reopen_after_rollback('t',work_id)==1
    assert f.status('t','issue1')=='needs_review'
    engine.dispose()


def test_signed_second_publication_rollback_restores_prior_artifact(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'db.sqlite'))
    Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine,expire_on_commit=False)
    j=Journal(sessions);graph=InMemoryGraphPort();graph.seed('t','ent','field','before')
    store=ImmutableSnapshotStore(tmp_path/'artifacts')
    for rev in (1,2):
        source=corpus(tmp_path/f'p{rev}.json',f'p{rev}',rev,
                     [{'chunk_id':f'c{rev}','tenant_id':'t','text':f'approved data {rev}'}])
        wid=adapter.queue_from_reviewed_patch(sessions=sessions,patch=patch(f'p{rev}',rev),
             actor=SimpleNamespace(username='promoter'),snapshot_path=source,signing_key=KEY)
        assert PublicationWorker(j,graph,store,simulation_mode=True).run_once()['status']=='published'
        if rev==1: first=j.pointer('t')['generation_id']
    second=j.pointer('t')['generation_id']
    assert second != first
    j.request_rollback(wid,'t')
    assert PublicationWorker(j,graph,store,simulation_mode=True).run_once()['status']=='rolled_back'
    assert j.pointer('t')['generation_id']==first
    assert graph.read('t','ent','field')=={'value':'updated-1'}
    engine.dispose()


def test_wrong_corpus_revision_never_queues(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'db.sqlite'))
    Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine,expire_on_commit=False)
    src=corpus(tmp_path/'wrong.json','p1',1,[{'chunk_id':'1','tenant_id':'t','text':'v1'}])
    with pytest.raises(adapter.ApprovalReadinessError):
        adapter.queue_from_reviewed_patch(sessions=sessions,patch=patch('p1',2),
            actor=SimpleNamespace(username='promoter'),snapshot_path=src,signing_key=KEY)
    with sessions() as s:assert s.query(PublicationWork).count()==0
    engine.dispose()
