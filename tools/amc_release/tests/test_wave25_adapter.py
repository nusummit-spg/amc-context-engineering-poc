"""Tests for the real Wave 1.9 journal-facing Wave 2.5 queue adapter."""
import importlib.util
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BASE = Path(__file__).resolve().parents[5]
W19_BACKEND = Path(__file__).resolve().parents[3] / 'backend'
if not (W19_BACKEND/'amc_publication/models.py').is_file():
    W19_BACKEND = Path(__file__).resolve().parents[3] / 'test_support/baseline/backend'
if W19_BACKEND.exists():
    sys.path.insert(0, str(W19_BACKEND))
from amc_publication.models import Base, PublicationWork
from amc_publication.types import canonical_bytes

MODULE = Path(__file__).resolve().parents[3] / 'backend/amc_publication/approval_adapter.py'
spec=importlib.util.spec_from_file_location('amc_publication.approval_adapter', MODULE)
approval=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=approval
spec.loader.exec_module(approval)

KEY = 'test-only-please-never-use-in-real-deployment-0123456789'

def body(**overrides):
    b = {'tenant':'acme','proposal_id':'patch-1','approved_revision':3,
         'source_version':'dataset.v3','source_manifest_sha256':'a'*64,
         'complete':True,'documents':[{'chunk_id':'1','tenant_id':'acme','text':'verified text'},
                                      {'chunk_id':'2','tenant_id':'acme','text':'verified text two'}]}
    b.update(overrides)
    return b

def sign(path, payload=None, *, key=KEY):
    b=payload if payload is not None else body()
    mac=hmac.new(key.encode(),canonical_bytes(b),hashlib.sha256).hexdigest()
    path.write_text(json.dumps({'payload':b,'hmac_sha256':mac}),encoding='utf-8')
    return path

def patch(**kw):
    props={'patch_id':'patch-1','tenant_id':'acme','version':3,'status':'APPROVED',
           'entity_id':'entity-1','attribute':'display_name','corrected_value':'new value',
           'provenance':{'proposer_username':'proposer','approver_username':'reviewer'}}
    props.update(kw)
    return SimpleNamespace(**props)

@pytest.fixture
def sessions(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path / "db.sqlite"}')
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine,expire_on_commit=False)
    engine.dispose()

def test_signed_tenant_snapshot_is_accepted(tmp_path):
    o=approval.load_verified_corpus(sign(tmp_path/'test.json'),KEY,tenant='acme',proposal_id='patch-1',revision=3)
    assert o.tenant == 'acme' and len(o.documents)==2 and len(o.file_sha256)==64

def test_real_journal_enqueue_requires_review_and_returns_idempotent_job(tmp_path,sessions):
    file=sign(tmp_path/'snapshot.json')
    actor=SimpleNamespace(username='promoter')
    job1=approval.queue_from_reviewed_patch(sessions=sessions,patch=patch(),actor=actor,snapshot_path=file,signing_key=KEY)
    job2=approval.queue_from_reviewed_patch(sessions=sessions,patch=patch(),actor=actor,snapshot_path=file,signing_key=KEY)
    assert job1==job2
    with sessions() as s:
        row=s.get(PublicationWork,job1)
        assert row.status=='queued' and row.tenant=='acme' and len(row.payload['full_vector_snapshot'])==2
        assert row.approved_revision==3 and row.proposal_id=='patch-1'

@pytest.mark.parametrize('change',[
  {'tenant':'other'},{'proposal_id':'patch-2'},{'approved_revision':2},
  {'complete':False},{'source_version':''},{'source_manifest_sha256':'no'},
  {'documents':[]},{'documents':[{'chunk_id':'x','tenant_id':'other','text':'x'}]},
  {'documents':[{'chunk_id':'dup','tenant_id':'acme','text':'x'},{'chunk_id':'dup','tenant_id':'acme','text':'y'}]},
  {'documents':[{'chunk_id':'x','tenant_id':'acme'}]},
])
def test_invalid_complete_corpus_is_rejected(tmp_path,change):
    signed=sign(tmp_path/'snapshot.json',body(**change))
    with pytest.raises(approval.ApprovalReadinessError):
        approval.load_verified_corpus(signed,KEY,tenant='acme',proposal_id='patch-1',revision=3)

@pytest.mark.parametrize('bad',[
 {'status':'PENDING'},{'status':'ACTIVE'}, {'tenant_id':None},{'version':None},
 {'version':0},{'patch_id':None},{'entity_id':None},{'attribute':None},
 {'corrected_value':None},{'provenance':{}},
 {'provenance':{'proposer_username':'same','approver_username':'same'}},
])
def test_unreviewed_or_malformed_patch_never_creates_job(tmp_path,sessions,bad):
    f=sign(tmp_path/'snapshot.json')
    with pytest.raises(approval.ApprovalReadinessError):
        approval.queue_from_reviewed_patch(sessions=sessions,patch=patch(**bad),actor=SimpleNamespace(username='promoter'),snapshot_path=f,signing_key=KEY)
    with sessions() as s:
        assert s.query(PublicationWork).count()==0

def test_promoter_cannot_be_proposer(tmp_path,sessions):
    f=sign(tmp_path/'snapshot.json')
    with pytest.raises(approval.ApprovalReadinessError):
        approval.queue_from_reviewed_patch(sessions=sessions,patch=patch(),actor=SimpleNamespace(username='proposer'),snapshot_path=f,signing_key=KEY)

def test_tampered_signed_snapshot_is_rejected(tmp_path):
    p=sign(tmp_path/'snapshot.json')
    content=json.loads(p.read_text());content['payload']['documents'][0]['text']='tampered';p.write_text(json.dumps(content))
    with pytest.raises(approval.ApprovalReadinessError):
        approval.load_verified_corpus(p,KEY,tenant='acme',proposal_id='patch-1',revision=3)

def test_wrong_or_missing_signing_key(tmp_path):
    p=sign(tmp_path/'snapshot.json')
    for key in ['tiny', 'another-very-different-signing-key-12345678','']:
        with pytest.raises(approval.ApprovalReadinessError):
            approval.load_verified_corpus(p,key,tenant='acme',proposal_id='patch-1',revision=3)

def test_missing_environment_disables_publication(monkeypatch,sessions):
    monkeypatch.delenv('AMC_PUBLICATION_CORPUS_SNAPSHOT',raising=False)
    monkeypatch.delenv('AMC_PUBLICATION_CORPUS_SIGNING_KEY',raising=False)
    with pytest.raises(approval.ApprovalReadinessError):
        approval.queue_from_environment(sessions=sessions,patch=patch(),actor=SimpleNamespace(username='promoter'))

@pytest.mark.skipif(not hasattr(Path,'symlink_to'),reason='symlinks unavailable')
def test_symlink_snapshot_rejected(tmp_path):
    target=sign(tmp_path/'source.json'); alias=tmp_path/'alias.json'
    try: alias.symlink_to(target)
    except OSError: pytest.skip('host disallows symlink')
    with pytest.raises(approval.ApprovalReadinessError):
        approval.load_verified_corpus(alias,KEY,tenant='acme',proposal_id='patch-1',revision=3)


def test_actual_correction_patch_shape_tenant_in_persisted_provenance(tmp_path,sessions):
    f=sign(tmp_path/'snapshot.json')
    real_shape=patch()
    del real_shape.tenant_id  # CorrectionPatch dataclass does not define tenant_id
    real_shape.provenance['tenant_id']='acme'
    work=approval.queue_from_reviewed_patch(sessions=sessions,patch=real_shape,
        actor=SimpleNamespace(username='promoter'),snapshot_path=f,signing_key=KEY)
    with sessions() as s:
        assert s.get(PublicationWork,work).tenant=='acme'


def test_unscoped_correction_patch_never_falls_back_to_default(tmp_path,sessions):
    f=sign(tmp_path/'snapshot.json')
    real_shape=patch();del real_shape.tenant_id
    with pytest.raises(approval.ApprovalReadinessError):
        approval.queue_from_reviewed_patch(sessions=sessions,patch=real_shape,
            actor=SimpleNamespace(username='promoter'),snapshot_path=f,signing_key=KEY)
